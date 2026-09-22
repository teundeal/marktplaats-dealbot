import os
import re
import statistics
import requests
from urllib.parse import quote
from playwright.sync_api import sync_playwright

DISCORD_WEBHOOK = os.environ["DISCORD_WEBHOOK"]

POSTCODE = "3116"
AFSTAND = "8000"
MAX_PRIJS = 5.00

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


def euro_naar_float(waarde):
    waarde = waarde.replace("€", "").replace(" ", "").strip()

    # Nederlandse bedragen:
    # 4,95 -> 4.95
    # 1.250,00 -> 1250.00
    if "," in waarde:
        waarde = waarde.replace(".", "")
        waarde = waarde.replace(",", ".")

    try:
        return float(waarde)
    except:
        return None


def vind_europrijzen(tekst):
    gevonden = re.findall(
        r"€\s*([0-9]+(?:[.,][0-9]{1,2})?)",
        tekst
    )

    prijzen = []

    for waarde in gevonden:
        prijs = euro_naar_float(waarde)

        if prijs is not None:
            prijzen.append(prijs)

    return prijzen


def schone_titel(titel):
    titel = titel.replace("\n", " ")
    titel = re.sub(r"\s+", " ", titel)

    titel = re.sub(
        r"€\s*[0-9]+(?:[.,][0-9]{1,2})?",
        "",
        titel
    )

    titel = titel.replace(
        "Bewaren in Mijn Favorieten", ""
    )

    titel = titel.replace(
        "Bewaren in mijn favorieten", ""
    )

    titel = re.sub(r"\s+", " ", titel)

    return titel.strip(" -|")


def uitgesloten(titel):
    tekst = titel.lower()
    return any(woord in tekst for woord in UITSLUITEN)


def interessant(titel):
    tekst = titel.lower()
    return any(woord in tekst for woord in INTERESSANT)


def advertentiekaarten(page):
    """
    Leest advertenties rechtstreeks uit de zoekresultaten.

    BELANGRIJK:
    We zoeken de prijs binnen dezelfde kaart als de advertentie.
    We gebruiken NIET de laagste prijs van de pagina.
    """

    advertenties = []

    links = page.locator("a[href*='/v/']")

    aantal = links.count()

    for i in range(aantal):

        try:
            link = links.nth(i)

            href = link.get_attribute("href")

            if not href:
                continue

            if "/v/" not in href:
                continue

            # Eerst de tekst van de link zelf proberen.
            try:
                linktekst = link.inner_text(
                    timeout=1000
                )
            except:
                linktekst = ""

            # Zoek een geschikte ouder/container.
            container = link

            beste_tekst = linktekst

            for niveau in range(1, 8):

                try:
                    ouder = link.locator(
                        "xpath=" + "/.." * niveau
                    )

                    tekst = ouder.inner_text(
                        timeout=1000
                    )

                    tekst = re.sub(
                        r"\s+",
                        " ",
                        tekst
                    ).strip()

                    if not tekst:
                        continue

                    # We willen een container die:
                    # - een prijs bevat
                    # - niet gigantisch veel tekst bevat
                    if "€" in tekst and len(tekst) < 1500:
                        container = ouder
                        beste_tekst = tekst
                        break

                except:
                    continue

            if not beste_tekst:
                continue

            tekst = beste_tekst

            # Bieden = geen vaste aankoopprijs
            if re.search(
                r"\bbieden\b",
                tekst,
                re.IGNORECASE
            ):
                continue

            # Op aanvraag = geen vaste prijs
            if re.search(
                r"op aanvraag",
                tekst,
                re.IGNORECASE
            ):
                continue

            # ------------------------------------------------
            # PRIJS UIT DE ADVERTENTIEKAART HALEN
            # ------------------------------------------------

            prijzen = vind_europrijzen(tekst)

            if not prijzen:
                continue

            # Verwijder prijzen die duidelijk bij verzending
            # horen. We kijken naar de tekst rondom de prijs.
            echte_prijzen = []

            for match in re.finditer(
                r"€\s*[0-9]+(?:[.,][0-9]{1,2})?",
                tekst
            ):

                prijs = euro_naar_float(
                    match.group(0)
                )

                if prijs is None:
                    continue

                omgeving = tekst[
                    max(0, match.start() - 100):
                    match.end() + 100
                ].lower()

                if "verzend" in omgeving:
                    continue

                if "verzending" in omgeving:
                    continue

                if "verzendkosten" in omgeving:
                    continue

                echte_prijzen.append(prijs)

            if not echte_prijzen:
                continue

            # De eerste niet-verzendprijs is de advertentieprijs.
            prijs = echte_prijzen[0]

            # HIER wordt de harde filter toegepast.
            # Alles boven €5 komt NIET in de kandidatenlijst.
            if prijs > MAX_PRIJS:
                continue

            if prijs < 0:
                continue

            titel = schone_titel(tekst)

            # Haal bekende UI-onderdelen uit titel
            titel = re.split(
                r"\bDetails\b|\bOphalen\b|\bVerzenden\b",
                titel,
                flags=re.IGNORECASE
            )[0].strip()

            if not titel:
                continue

            if len(titel) > 180:
                titel = titel[:180].rsplit(
                    " ",
                    1
                )[0]

            if uitgesloten(titel):
                continue

            if not interessant(titel):
                continue

            if href.startswith("/"):
                href = (
                    "https://www.marktplaats.nl"
                    + href
                )

            advertenties.append({
                "url": href,
                "titel": titel,
                "koopprijs": prijs,
            })

        except Exception:
            continue

    # Dubbelen verwijderen
    uniek = {}

    for advertentie in advertenties:
        uniek[advertentie["url"]] = advertentie

    return list(uniek.values())


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
            timeout=15000
        )

        page.wait_for_timeout(700)

        kaarten = advertentiekaarten(
            page
        )

        prijzen = []

        for advertentie in kaarten:

            # Alleen normale verkoopprijzen.
            prijs = advertentie["koopprijs"]

            if prijs > 5 and prijs <= 2000:
                prijzen.append(prijs)

        # Voor vergelijkingen willen we geen
        # dubbele prijzen.
        prijzen = sorted(set(prijzen))

        return prijzen[:15]

    except Exception:
        return []


def zoek_verkoopprijzen(page, zoekterm):

    url = (
        "https://www.marktplaats.nl/q/"
        + quote(zoekterm)
        + "/"
    )

    try:

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=15000
        )

        page.wait_for_timeout(700)

        # Hier gebruiken we een aparte parser omdat
        # advertentiekaarten() alleen advertenties <= €5
        # teruggeeft.
        links = page.locator(
            "a[href*='/v/']"
        )

        prijzen = []

        for i in range(
            min(links.count(), 60)
        ):

            try:

                link = links.nth(i)

                href = link.get_attribute(
                    "href"
                )

                if not href:
                    continue

                tekst = ""

                # Zoek oudercontainer
                for niveau in range(1, 8):

                    try:

                        ouder = link.locator(
                            "xpath=" + "/.." * niveau
                        )

                        kandidaat = ouder.inner_text(
                            timeout=1000
                        )

                        kandidaat = re.sub(
                            r"\s+",
                            " ",
                            kandidaat
                        ).strip()

                        if (
                            "€" in kandidaat
                            and len(kandidaat) < 1500
                        ):
                            tekst = kandidaat
                            break

                    except:
                        continue

                if not tekst:
                    continue

                if re.search(
                    r"\bbieden\b",
                    tekst,
                    re.IGNORECASE
                ):
                    continue

                # Prijzen in dezelfde kaart
                matches = list(
                    re.finditer(
                        r"€\s*[0-9]+(?:[.,][0-9]{1,2})?",
                        tekst
                    )
                )

                for match in matches:

                    prijs = euro_naar_float(
                        match.group(0)
                    )

                    if prijs is None:
                        continue

                    omgeving = tekst[
                        max(0, match.start() - 100):
                        match.end() + 100
                    ].lower()

                    # Verzendkosten overslaan
                    if "verzend" in omgeving:
                        continue

                    if 5 < prijs <= 2000:
                        prijzen.append(prijs)

                        # Eerste normale prijs
                        break

            except:
                continue

        return sorted(prijzen)[:20]

    except Exception:
        return []


def stuur_discord(deals):

    if not deals:
        print(
            "🔥 0 mogelijke deals gevonden."
        )
        return

    for deal in deals:

        bericht = (
            "🔥 **MOGELIJKE DEAL**\n\n"
            f"**{deal['titel']}**\n"
            f"💰 Koopprijs: "
            f"€{deal['koopprijs']:.2f}\n"
            f"💵 Geschatte verkoop: "
            f"€{deal['verkoopprijs']:.2f}\n"
            f"📈 Mogelijke winst: "
            f"€{deal['winst']:.2f}\n"
            f"🎯 Vertrouwen: "
            f"{deal['vertrouwen']}%\n"
            f"📊 Vergelijkingen: "
            f"{deal['vergelijkingen']}\n\n"
            f"🔗 {deal['url']}"
        )

        try:

            response = requests.post(
                DISCORD_WEBHOOK,
                json={
                    "content": bericht
                },
                timeout=10
            )

            if response.status_code in (
                200,
                204
            ):
                print(
                    "📲 Deal naar Discord gestuurd."
                )

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

    kandidaten = {}

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page()

        print(
            "🚀 Marktplaats dealbot gestart"
        )

        print(
            f"📍 Postcode: {POSTCODE}"
        )

        print(
            f"📏 Afstand: {AFSTAND / 1000:.1f} km"
        )

        print(
            f"💰 Maximale aankoopprijs: "
            f"€{MAX_PRIJS:.2f}"
        )

        # ==========================================
        # ZOEKEN
        # ==========================================

        for zoekterm in ZOEKOPDRACHTEN:

            print(
                f"\n🔎 Zoeken naar: {zoekterm}"
            )

            url = (
                "https://www.marktplaats.nl/q/"
                + quote(zoekterm)
                + "/?postcode="
                + POSTCODE
                + "&distanceMeters="
                + str(AFSTAND)
            )

            try:

                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=15000
                )

                page.wait_for_timeout(800)

                advertenties = advertentiekaarten(
                    page
                )

                print(
                    f"   💰 Advertenties <= €5: "
                    f"{len(advertenties)}"
                )

                for advertentie in advertenties:

                    kandidaten[
                        advertentie["url"]
                    ] = advertentie

            except Exception as e:

                print(
                    f"⚠️ Zoekfout bij "
                    f"'{zoekterm}': "
                    f"{str(e)[:100]}"
                )

        print(
            f"\n📦 {len(kandidaten)} echte "
            f"advertenties <= €5 gevonden."
        )

        # ==========================================
        # MAXIMAAL 20 CONTROLEREN
        # ==========================================

        lijst = list(
            kandidaten.values()
        )[:20]

        print(
            f"🔍 We controleren maximaal "
            f"{len(lijst)} kandidaten."
        )

        deals = []

        for nummer, advertentie in enumerate(
            lijst,
            1
        ):

            titel = advertentie["titel"]
            koopprijs = advertentie["koopprijs"]
            url = advertentie["url"]

            print(
                f"\n➡️ Controle "
                f"{nummer}/{len(lijst)}: "
                f"{titel[:80]}"
            )

            print(
                f"   💰 Koopprijs uit "
                f"zoekresultaatkaart: "
                f"€{koopprijs:.2f}"
            )

            # ======================================
            # EXTRA VEILIGHEID
            # ======================================

            if koopprijs > MAX_PRIJS:

                print(
                    "   ❌ FOUT: prijs boven €5. "
                    "Advertentie wordt overgeslagen."
                )

                continue

            try:

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

                prijzen = zoek_verkoopprijzen(
                    page,
                    zoekterm
                )

                if len(prijzen) < 3:

                    print(
                        "   ❌ Te weinig "
                        "betrouwbare vergelijkingen."
                    )

                    continue

                verkoopprijs = statistics.median(
                    prijzen
                )

                print(
                    f"   📈 Vergelijkbare "
                    f"verkoopprijzen: "
                    f"{[round(p, 2) for p in prijzen]}"
                )

                print(
                    f"   💵 Geschatte verkoopprijs: "
                    f"€{verkoopprijs:.2f}"
                )

                # ======================================
                # DEALREGELS
                # ======================================

                if koopprijs == 0:

                    if verkoopprijs < 10:

                        print(
                            "   ❌ Gratis maar "
                            "te weinig waarde."
                        )

                        continue

                else:

                    if verkoopprijs < koopprijs * 2:

                        print(
                            "   ❌ Minder dan "
                            "2x aankoopprijs."
                        )

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

                deals.append({
                    "titel": titel,
                    "koopprijs": koopprijs,
                    "verkoopprijs": verkoopprijs,
                    "winst": winst,
                    "vertrouwen": vertrouwen,
                    "vergelijkingen": len(prijzen),
                    "url": url,
                })

                print(
                    f"   🔥 DEAL!"
                )

            except Exception as e:

                print(
                    "   ⚠️ Advertentie "
                    "overgeslagen:",
                    str(e)[:150]
                )

        browser.close()

    # ==========================================
    # RESULTAAT
    # ==========================================

    deals.sort(
        key=lambda deal: deal["winst"],
        reverse=True
    )

    print(
        f"\n🔥 {len(deals)} mogelijke "
        f"deals gevonden."
    )

    stuur_discord(deals)


if __name__ == "__main__":
    main()
