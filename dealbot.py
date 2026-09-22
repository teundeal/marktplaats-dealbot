import os
import re
import statistics
import requests
from playwright.sync_api import sync_playwright

DISCORD_WEBHOOK = os.environ["DISCORD_WEBHOOK"]

POSTCODE = "3116"
AFSTAND = "8000"
MAX_PRIJS = 500  # €5 in centen

# Brede zoekopdrachten zodat we niet tientallen keren hoeven te zoeken
ZOEKOPDRACHTEN = [
    "elektronica",
    "telefoon",
    "camera",
    "game",
    "lego",
    "pokemon",
    "nike",
    "adidas",
    "horloge",
    "modelauto",
]

# Dingen die we absoluut niet willen
UITSLUITEN = [
    "bank",
    "bankstel",
    "hoekbank",
    "stoel",
    "tafel",
    "eettafel",
    "bed",
    "kast",
    "bureau",
    "matras",
    "wasmachine",
    "droger",
    "koelkast",
    "vriezer",
    "vaatwasser",
    "televisie",
    "tv",
    "airco",
    "service",
    "montage",
    "reparatie",
    "klus",
    "verhuizing",
]

# Dingen die vaak interessant zijn voor doorverkoop
INTERESSANT = [
    "iphone",
    "ipad",
    "samsung",
    "sony",
    "canon",
    "nikon",
    "camera",
    "lens",
    "objectief",
    "playstation",
    "ps4",
    "ps5",
    "xbox",
    "nintendo",
    "switch",
    "game",
    "controller",
    "lego",
    "pokemon",
    "nike",
    "adidas",
    "air jordan",
    "dyson",
    "logitech",
    "jbl",
    "bose",
    "garmin",
    "casio",
    "gopro",
    "dji",
    "koptelefoon",
    "speaker",
    "gereedschap",
    "boormachine",
    "verrekijker",
    "horloge",
    "modelauto",
    "burago",
    "ferrari",
    "mercedes",
    "bmw",
    "porsche",
    "nokia",
    "tablet",
    "toetsenbord",
    "muis",
]


def prijs_uit_tekst(tekst):
    """Probeert een prijs uit een tekst te halen."""
    patronen = [
        r"€\s?(\d+(?:[.,]\d{1,2})?)",
        r"(\d+(?:[.,]\d{1,2})?)\s?€",
    ]

    for patroon in patronen:
        match = re.search(patroon, tekst)
        if match:
            try:
                return float(match.group(1).replace(",", "."))
            except:
                pass

    return None


def uitgesloten(titel):
    titel = titel.lower()

    return any(woord in titel for woord in UITSLUITEN)


def interessant(titel):
    titel = titel.lower()

    return any(woord in titel for woord in INTERESSANT)


def vergelijkbare_prijzen(page, zoekterm):
    """
    Zoekt maximaal 5 vergelijkbare advertenties.
    Daardoor blijft de bot snel.
    """

    url = (
        "https://www.marktplaats.nl/q/"
        + requests.utils.quote(zoekterm)
        + "/?postcode="
        + POSTCODE
        + "&distanceMeters="
        + AFSTAND
    )

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(1000)

        prijzen = []

        teksten = page.locator("body").inner_text()

        for match in re.findall(r"€\s?(\d+(?:[.,]\d{1,2})?)", teksten):
            try:
                prijs = float(match.replace(",", "."))

                # Alleen normale tweedehandsprijzen
                if 5 < prijs < 5000:
                    prijzen.append(prijs)
            except:
                pass

        # Uniek maken en maximaal 10 prijzen gebruiken
        prijzen = sorted(set(prijzen))[:10]

        return prijzen

    except:
        return []


def discord_stuur(deals):
    if not deals:
        print("🔥 0 mogelijke deals gevonden.")
        return

    for deal in deals:
        bericht = (
            "🔥 **MOGELIJKE MARKTPLAATS DEAL**\n\n"
            f"**{deal['titel']}**\n"
            f"💰 Koopprijs: €{deal['koopprijs']:.2f}\n"
            f"💵 Geschatte verkoop: €{deal['verkoopprijs']:.2f}\n"
            f"📈 Mogelijke winst: €{deal['winst']:.2f}\n"
            f"🎯 Vertrouwen: {deal['vertrouwen']}%\n"
            f"📊 Vergelijkbare advertenties: {deal['vergelijkingen']}\n\n"
            f"🔗 {deal['url']}"
        )

        requests.post(
            DISCORD_WEBHOOK,
            json={"content": bericht},
            timeout=10
        )


def main():

    advertenties = {}

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print("🔎 Marktplaats zoeken...")

        # Slechts 10 zoekopdrachten
        for zoekterm in ZOEKOPDRACHTEN:

            url = (
                "https://www.marktplaats.nl/q/"
                + requests.utils.quote(zoekterm)
                + "/?postcode="
                + POSTCODE
                + "&distanceMeters="
                + AFSTAND
                + "&priceCentsTo="
                + str(MAX_PRIJS)
            )

            try:
                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=15000
                )

                page.wait_for_timeout(700)

                links = page.locator("a").evaluate_all(
                    """els => els.map(a => ({
                        href: a.href,
                        text: a.innerText
                    }))"""
                )

                for link in links:

                    href = link.get("href", "")
                    titel = link.get("text", "").strip()

                    if "/v/" not in href:
                        continue

                    if not titel:
                        continue

                    # Unieke advertenties
                    advertenties[href] = titel

            except Exception as e:
                print("⚠️ Zoekfout:", zoekterm)

        print(f"📦 {len(advertenties)} unieke advertenties gevonden.")

        deals = []

        # We bekijken maximaal 25 advertenties
        kandidaten = list(advertenties.items())[:25]

        for i, (url, titel) in enumerate(kandidaten, 1):

            print(f"➡️ Controle {i}/{len(kandidaten)}: {titel[:60]}")

            titel_lower = titel.lower()

            # Grote spullen / diensten meteen overslaan
            if uitgesloten(titel):
                continue

            # Alleen advertenties met enige kans
            if not interessant(titel):
                continue

            # Advertentie openen om echte prijs te vinden
            try:
                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=12000
                )

                page.wait_for_timeout(500)

                tekst = page.locator("body").inner_text()

                koopprijs = prijs_uit_tekst(tekst)

                if koopprijs is None:
                    # Waarschijnlijk gratis
                    if "gratis" in tekst.lower():
                        koopprijs = 0
                    else:
                        continue

                if koopprijs > 5:
                    continue

            except:
                continue

            # Zoek vergelijkbare advertenties
            zoekwoorden = titel.split()

            # Gebruik alleen de eerste paar woorden
            zoekterm = " ".join(zoekwoorden[:4])

            print(f"   🔎 Vergelijken: {zoekterm}")

            prijzen = vergelijkbare_prijzen(page, zoekterm)

            if len(prijzen) < 3:
                print("   ❌ Te weinig vergelijkingen")
                continue

            verkoopprijs = statistics.median(prijzen)

            # Gratis spullen moeten minimaal ongeveer €10 waard zijn
            if koopprijs == 0:
                if verkoopprijs < 10:
                    continue
            else:
                if verkoopprijs < koopprijs * 2:
                    continue

            # Vertrouwen berekenen
            vertrouwen = 70

            if len(prijzen) >= 5:
                vertrouwen += 10

            if len(prijzen) >= 8:
                vertrouwen += 10

            vertrouwen = min(95, vertrouwen)

            if vertrouwen < 70:
                continue

            winst = verkoopprijs - koopprijs

            deals.append({
                "titel": titel,
                "koopprijs": koopprijs,
                "verkoopprijs": verkoopprijs,
                "winst": winst,
                "vertrouwen": vertrouwen,
                "vergelijkingen": len(prijzen),
                "url": url,
            })

        browser.close()

    # Beste deals eerst
    deals.sort(
        key=lambda x: x["winst"],
        reverse=True
    )

    print(f"🔥 {len(deals)} mogelijke deals gevonden.")

    discord_stuur(deals)


if __name__ == "__main__":
    main()
