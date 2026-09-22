import os
import re
import statistics
import requests
from urllib.parse import quote
from playwright.sync_api import sync_playwright

DISCORD_WEBHOOK = os.environ["DISCORD_WEBHOOK"]

POSTCODE = "3116"
AFSTAND = "8000"
MAX_PRIJS = 5

ZOEKOPDRACHTEN = [
    "elektronica",
    "telefoon",
    "camera",
    "game",
    "lego",
    "pokemon",
    "schoenen",
    "horloge",
    "modelauto",
    "gereedschap",
]

UITSLUITEN = [
    "bank", "bankstel", "hoekbank", "stoel", "tafel",
    "eettafel", "bed", "kast", "bureau", "matras",
    "wasmachine", "droger", "koelkast", "vriezer",
    "vaatwasser", "televisie", "tv", "airco", "piano",
    "orgel", "stelling", "pallet", "service", "montage",
    "reparatie", "installatie", "adviseur", "gezocht",
    "inkoop", "verhuur", "bedrijf", "zakelijk", "offerte",
    "klus",
]

INTERESSANT = [
    "iphone", "ipad", "samsung", "galaxy", "sony", "canon",
    "nikon", "camera", "lens", "objectief", "playstation",
    "ps4", "ps5", "xbox", "nintendo", "switch", "game",
    "controller", "lego", "pokemon", "nike", "adidas",
    "jordan", "dyson", "logitech", "jbl", "bose", "garmin",
    "casio", "gopro", "dji", "koptelefoon", "headset",
    "speaker", "boormachine", "gereedschap", "verrekijker",
    "horloge", "modelauto", "burago", "ferrari", "mercedes",
    "bmw", "porsche", "nokia", "tablet", "toetsenbord",
    "muis", "router", "ssd", "hdd", "arduino", "raspberry",
]


def schone_titel(titel):
    rommel = [
        "Bewaren in Mijn Favorieten",
        "Bewaren in mijn favorieten",
    ]

    for stuk in rommel:
        titel = titel.replace(stuk, "")

    titel = re.sub(r"\s+", " ", titel)

    return titel.strip()


def uitgesloten(titel):
    tekst = titel.lower()
    return any(woord in tekst for woord in UITSLUITEN)


def interessant(titel):
    tekst = titel.lower()
    return any(woord in tekst for woord in INTERESSANT)


def echte_advertentieprijs(page):
    """
    Probeert alleen de daadwerkelijke vraagprijs van de advertentie
    te vinden.

    Verzendkosten worden NIET gebruikt.
    'Bieden' wordt overgeslagen.
    """

    try:
        # Eerst kijken naar duidelijke prijs-elementen.
        mogelijke_selectors = [
            '[data-testid*="price"]',
            '[class*="price"]',
            '[class*="Price"]',
        ]

        teksten = []

        for selector in mogelijke_selectors:

            try:
                elementen = page.locator(selector).all_inner_texts()

                for tekst in elementen:
                    tekst = tekst.strip()

                    if tekst:
                        teksten.append(tekst)

            except Exception:
                pass

        # Dubbele teksten verwijderen.
        uniek = []

        for tekst in teksten:
            if tekst not in uniek:
                uniek.append(tekst)

        # Zoek naar een echte prijs.
        for tekst in uniek:

            laag = tekst.lower()

            if "bieden" in laag:
                continue

            if "vanaf" in laag:
                continue

            matches = re.findall(
                r"€\s*([0-9]+(?:[.,][0-9]{1,2})?)",
                tekst
            )

            for waarde in matches:

                try:
                    prijs = float(
                        waarde.replace(",", ".")
                    )

                    # Alleen een echte advertentieprijs
                    # onder of gelijk aan €5.
                    if 0 <= prijs <= MAX_PRIJS:
                        return prijs

                except ValueError:
                    pass

        # Tweede methode:
        # kijk naar de zichtbare tekst bovenaan de advertentie,
        # maar negeer verzendkosten.
        body = page.locator("body").inner_text()

        regels = [
            regel.strip()
            for regel in body.splitlines()
            if regel.strip()
        ]

        for i, regel in enumerate(regels[:100]):

            laag = regel.lower()

            if "bieden" in laag:
                continue

            if "verzending" in laag:
                continue

            if "verzendkosten" in laag:
                continue

            if "ophalen" in laag and i + 1 < len(regels):

                volgende = regels[i + 1]

                match = re.search(
                    r"€\s*([0-9]+(?:[.,][0-9]{1,2})?)",
                    volgende
                )

                if match:

                    try:
                        prijs = float(
                            match.group(1).replace(",", ".")
                        )

                        if 0 <= prijs <= MAX_PRIJS:
                            return prijs

                    except ValueError:
                        pass

        return None

    except Exception:
        return None


def zoek_vergelijkbare_prijzen(page, zoekterm):

    url = (
        "https://www.marktplaats.nl/q/"
        + quote(zoekterm)
        + "/"
    )

    try:

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=12000
        )

        page.wait_for_timeout(600)

        tekst = page.locator("body").inner_text()

        gevonden = re.findall(
            r"€\s*([0-9]+(?:[.,][0-9]{1,2})?)",
            tekst
        )

        prijzen = []

        for waarde in gevonden:

            try:

                prijs = float(
                    waarde.replace(",", ".")
                )

                if 5 <= prijs <= 2000:
                    prijzen.append(prijs)

            except ValueError:
                pass

        return sorted(set(prijzen))[:10]

    except Exception:
        return []


def stuur_discord(deals):

    if not deals:

        print("🔥 0 mogelijke deals gevonden.")

        return

    for deal in deals:

        bericht = (
            "🔥 **MOGELIJKE DEAL**\n\n"
            f"**{deal['titel']}**\n"
            f"💰 Koopprijs: €{deal['koopprijs']:.2f}\n"
            f"💵 Geschatte verkoop: €{deal['verkoopprijs']:.2f}\n"
            f"📈 Mogelijke winst: €{deal['winst']:.2f}\n"
            f"🎯 Vertrouwen: {deal['vertrouwen']}%\n"
            f"📊 Vergelijkingen: {deal['vergelijkingen']}\n\n"
            f"🔗 {deal['url']}"
        )

        try:

            response = requests.post(
                DISCORD_WEBHOOK,
                json={"content": bericht},
                timeout=10
            )

            if response.status_code in (200, 204):
                print("📲 Deal naar Discord gestuurd.")
            else:
                print(
                    "⚠️ Discord fout:",
                    response.status_code
                )

        except Exception as e:

            print(
                "⚠️ Discord fout:",
                e
            )


def main():

    advertenties = {}

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page()

        print("🔎 Marktplaats zoeken...")

        # ----------------------------------
        # ADVERTENTIES VERZAMELEN
        # ----------------------------------

        for zoekterm in ZOEKOPDRACHTEN:

            url = (
                "https://www.marktplaats.nl/q/"
                + quote(zoekterm)
                + "/?postcode="
                + POSTCODE
                + "&distanceMeters="
                + AFSTAND
                + "&priceCentsTo="
                + str(MAX_PRIJS * 100)
            )

            try:

                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=15000
                )

                page.wait_for_timeout(700)

                links = page.locator("a").evaluate_all(
                    """
                    els => els.map(a => ({
                        href: a.href,
                        text: a.innerText
                    }))
                    """
                )

                for item in links:

                    href = item.get(
                        "href",
                        ""
                    )

                    titel = item.get(
                        "text",
                        ""
                    ).strip()

                    if "/v/" not in href:
                        continue

                    titel = schone_titel(titel)

                    if not titel:
                        continue

                    if uitgesloten(titel):
                        continue

                    if not interessant(titel):
                        continue

                    advertenties[href] = titel

            except Exception:

                print(
                    f"⚠️ Zoekfout bij '{zoekterm}'"
                )

        print(
            f"📦 {len(advertenties)} interessante advertenties gevonden."
        )

        # ----------------------------------
        # KANDIDATEN CONTROLEREN
        # ----------------------------------

        kandidaten = list(
            advertenties.items()
        )[:20]

        print(
            f"🔍 We controleren maximaal "
            f"{len(kandidaten)} kandidaten."
        )

        deals = []

        for nummer, (url, titel) in enumerate(
            kandidaten,
            1
        ):

            print(
                f"➡️ Controle {nummer}/"
                f"{len(kandidaten)}: "
                f"{titel[:70]}"
            )

            try:

                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=12000
                )

                page.wait_for_timeout(700)

                # BELANGRIJK:
                # alleen de echte advertentieprijs.
                koopprijs = echte_advertentieprijs(
                    page
                )

                if koopprijs is None:

                    print(
                        "   ❌ Geen betrouwbare koopprijs."
                    )

                    continue

                if koopprijs > MAX_PRIJS:

                    print(
                        f"   ❌ Te duur: €{koopprijs:.2f}"
                    )

                    continue

                print(
                    f"   💰 Echte koopprijs: "
                    f"€{koopprijs:.2f}"
                )

                # ----------------------------------
                # VERGELIJKBARE PRODUCTEN
                # ----------------------------------

                woorden = re.findall(
                    r"[A-Za-z0-9]+",
                    titel
                )

                zoekwoorden = [
                    woord
                    for woord in woorden
                    if len(woord) >= 3
                ]

                zoekterm = " ".join(
                    zoekwoorden[:4]
                )

                if not zoekterm:
                    continue

                print(
                    f"   🔎 Vergelijken met: "
                    f"{zoekterm}"
                )

                prijzen = zoek_vergelijkbare_prijzen(
                    page,
                    zoekterm
                )

                if len(prijzen) < 3:

                    print(
                        "   ❌ Te weinig "
                        "vergelijkbare prijzen."
                    )

                    continue

                verkoopprijs = statistics.median(
                    prijzen
                )

                # Gratis producten moeten
                # minimaal €10 waard zijn.
                if koopprijs == 0:

                    if verkoopprijs < 10:
                        continue

                else:

                    if verkoopprijs < koopprijs * 2:
                        continue

                vertrouwen = 70

                if len(prijzen) >= 5:
                    vertrouwen += 10

                if len(prijzen) >= 8:
                    vertrouwen += 10

                vertrouwen = min(
                    vertrouwen,
                    95
                )

                winst = (
                    verkoopprijs
                    - koopprijs
                )

                deals.append(
                    {
                        "titel": titel,
                        "koopprijs": koopprijs,
                        "verkoopprijs": verkoopprijs,
                        "winst": winst,
                        "vertrouwen": vertrouwen,
                        "vergelijkingen": len(prijzen),
                        "url": url,
                    }
                )

                print(
                    f"   🔥 DEAL! "
                    f"Geschatte verkoop: "
                    f"€{verkoopprijs:.2f}"
                )

            except Exception as e:

                print(
                    "   ⚠️ Advertentie "
                    "overgeslagen."
                )

        browser.close()

    # Hoogste geschatte winst eerst.
    deals.sort(
        key=lambda deal: deal["winst"],
        reverse=True
    )

    print(
        f"🔥 {len(deals)} mogelijke deals gevonden."
    )

    stuur_discord(deals)


if __name__ == "__main__":
    main()
