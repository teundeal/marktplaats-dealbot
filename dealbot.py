import os
import re
import statistics
import requests

from urllib.parse import quote
from playwright.sync_api import sync_playwright


# ============================================================
# INSTELLINGEN
# ============================================================

POSTCODE = "3116"
AFSTAND = 8000
MAX_PRIJS = 5.00

DISCORD_WEBHOOK = os.environ["DISCORD_WEBHOOK"]

ZOEKTERMEN = [
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

MAX_KANDIDATEN = 15


# ============================================================
# PRIJS HERKENNEN
# ============================================================

def euro_naar_float(tekst):
    """
    Zet Nederlandse europrijzen correct om.

    Voorbeelden:
    €1.500       -> 1500.00
    €1.250,00    -> 1250.00
    €950,00      -> 950.00
    €15.000,50   -> 15000.50
    €4,50        -> 4.50
    €5           -> 5.00
    """

    if not tekst:
        return None

    tekst = tekst.strip()
    tekst = tekst.replace("€", "")
    tekst = tekst.replace("\xa0", " ")
    tekst = tekst.strip()

    # Alleen cijfers, punt en komma toestaan
    match = re.search(r"\d[\d.,]*", tekst)

    if not match:
        return None

    waarde = match.group(0)

    # Nederlandse notatie:
    #
    # 1.500      = 1500
    # 1.500,50   = 1500.50
    # 4,50       = 4.50
    #
    # Als er zowel punt als komma aanwezig zijn,
    # is de laatste komma de decimaal.
    if "." in waarde and "," in waarde:
        waarde = waarde.replace(".", "")
        waarde = waarde.replace(",", ".")

    # Alleen komma:
    elif "," in waarde:
        waarde = waarde.replace(",", ".")

    # Alleen punt:
    elif "." in waarde:
        delen = waarde.split(".")

        # Bijvoorbeeld 1.500 = duizendvijfhonderd
        if len(delen) == 2 and len(delen[1]) == 3:
            waarde = waarde.replace(".", "")

        # Bijvoorbeeld 1.50 = 1,50
        else:
            waarde = waarde.replace(".", ".")

    try:
        return float(waarde)
    except ValueError:
        return None


def vind_europrijzen(tekst):
    """
    Vind eurobedragen in tekst en zet ze om naar getallen.
    """

    if not tekst:
        return []

    patronen = [
        r"€\s*\d[\d.,]*",
        r"\d[\d.,]*\s*€",
    ]

    gevonden = []

    for patroon in patronen:
        matches = re.findall(patroon, tekst)

        for match in matches:
            prijs = euro_naar_float(match)

            if prijs is not None:
                gevonden.append(prijs)

    # Dubbele bedragen verwijderen
    resultaat = []

    for prijs in gevonden:
        if prijs not in resultaat:
            resultaat.append(prijs)

    return resultaat


# ============================================================
# TITEL
# ============================================================

def schone_titel(titel):
    if not titel:
        return "Onbekende advertentie"

    titel = re.sub(r"\s+", " ", titel)
    titel = re.sub(r"\d+,\d{2}Details.*$", "", titel, flags=re.IGNORECASE)
    titel = re.sub(r"\d+,\d{2}.*$", "", titel)

    return titel.strip()


# ============================================================
# UITSLUITINGEN
# ============================================================

UITGESLOTEN = [
    "hoekbank",
    "bank",
    "bed",
    "matras",
    "kast",
    "tafel",
    "eettafel",
    "stoel",
    "bureau",
    "dressoir",
    "wasmachine",
    "droger",
    "koelkast",
    "vriezer",
    "vaatwasser",
    "grote tv",
    "televisie",
    "tv meubel",
    "kastje",
    "tuinset",
    "loungeset",
    "trampoline",
]


def uitgesloten(titel):
    titel_lower = titel.lower()

    return any(
        woord in titel_lower
        for woord in UITGESLOTEN
    )


# ============================================================
# INTERESSANTE PRODUCTEN
# ============================================================

INTERESSANT = [
    "camera",
    "sony",
    "canon",
    "nikon",
    "fujifilm",
    "leica",
    "panasonic",
    "lumix",
    "lens",
    "objectief",
    "iphone",
    "samsung",
    "ipad",
    "macbook",
    "nintendo",
    "playstation",
    "xbox",
    "lego",
    "pokemon",
    "hot wheels",
    "modelauto",
    "horloge",
    "omega",
    "rolex",
    "seiko",
    "casio",
    "breitling",
    "gereedschap",
    "makita",
    "bosch",
    "dewalt",
    "milwaukee",
    "dji",
    "gopro",
    "garmin",
    "airpods",
    "headphones",
]


def interessant(titel):
    titel_lower = titel.lower()

    return any(
        woord in titel_lower
        for woord in INTERESSANT
    )


# ============================================================
# ADVERTENTIEKAARTEN
# ============================================================

def advertentiekaarten(page):

    kaarten = []

    links = page.locator('a[href*="/v/"]')

    aantal = links.count()

    for i in range(aantal):

        try:
            link = links.nth(i)

            href = link.get_attribute("href")

            if not href:
                continue

            if not href.startswith("http"):
                href = "https://www.marktplaats.nl" + href

            tekst = link.inner_text(timeout=3000)

            if not tekst:
                continue

            tekst = re.sub(r"\s+", " ", tekst).strip()

            prijzen = vind_europrijzen(tekst)

            if not prijzen:
                continue

            # Zoek een prijs die daadwerkelijk op de kaart staat.
            #
            # BELANGRIJK:
            # prijzen zoals €1.500 worden nu correct als 1500
            # gelezen en dus NIET meer als €1,50.

            prijs = None

            for gevonden_prijs in prijzen:
                if gevonden_prijs >= 0:
                    prijs = gevonden_prijs
                    break

            if prijs is None:
                continue

            kaarten.append({
                "url": href,
                "tekst": tekst,
                "prijs": prijs,
            })

        except Exception:
            continue

    # Dubbelen verwijderen
    unieke = {}

    for kaart in kaarten:
        unieke[kaart["url"]] = kaart

    return list(unieke.values())


# ============================================================
# VERGELIJKBARE PRIJZEN
# ============================================================

def zoek_verkoopprijzen(page, zoekterm):

    zoekterm = zoekterm.strip()

    if not zoekterm:
        return []

    url = (
        "https://www.marktplaats.nl/q/"
        + quote(zoekterm)
        + "/"
    )

    try:
        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=30000
        )

        page.wait_for_timeout(2000)

    except Exception:
        return []

    kaarten = advertentiekaarten(page)

    prijzen = []

    for kaart in kaarten:

        prijs = kaart["prijs"]

        # Alleen normale verkoopprijzen gebruiken
        if prijs is None:
            continue

        # Extreme prijzen kunnen verkeerde parserresultaten zijn
        if prijs <= 0:
            continue

        if prijs > 100000:
            continue

        prijzen.append(prijs)

    return prijzen


# ============================================================
# SCHATTING VERKOOPPRIJS
# ============================================================

def schat_verkoopprijs(prijzen):

    if len(prijzen) < 3:
        return None

    prijzen = sorted(prijzen)

    # Extreem lage bedragen verwijderen.
    #
    # Dit voorkomt bijvoorbeeld dat €1,50 accessoires
    # de waarde van een camera compleet omlaag trekken.

    normale_prijzen = [
        p for p in prijzen
        if p >= 5
    ]

    if len(normale_prijzen) < 3:
        return None

    # Gebruik mediaan / middelste gedeelte
    mediaan = statistics.median(normale_prijzen)

    return round(mediaan, 2)


# ============================================================
# DISCORD
# ============================================================

def stuur_discord(
    titel,
    koopprijs,
    verkoopprijs,
    winst,
    url,
    zoekterm,
    vertrouwen
):

    bericht = (
        "🔥 **MOGELIJKE MARKTPLAATS DEAL**\n\n"
        f"📦 **{titel}**\n\n"
        f"💰 Koopprijs: **€{koopprijs:.2f}**\n"
        f"💵 Geschatte verkoopprijs: **€{verkoopprijs:.2f}**\n"
        f"📈 Mogelijke winst: **€{winst:.2f}**\n"
        f"🎯 Vertrouwen: **{vertrouwen}%**\n"
        f"🔎 Zoekterm: {zoekterm}\n\n"
        f"🔗 [Advertentie openen]({url})"
    )

    try:

        response = requests.post(
            DISCORD_WEBHOOK,
            json={
                "content": bericht
            },
            timeout=15
        )

        if response.status_code in [200, 204]:
            print("📲 Deal naar Discord gestuurd.")
        else:
            print(
                "❌ Discord fout:",
                response.status_code,
                response.text[:300]
            )

    except Exception as e:
        print("❌ Discord verbinding mislukt:", e)


# ============================================================
# HOOFDPROGRAMMA
# ============================================================

def main():

    print("🚀 Marktplaats dealbot gestart")
    print(f"📍 Postcode: {POSTCODE}")
    print(f"📏 Afstand: {AFSTAND / 1000:.1f} km")
    print(f"💰 Maximale aankoopprijs: €{MAX_PRIJS:.2f}")
    print()

    kandidaten = []

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            viewport={
                "width": 1440,
                "height": 1000
            },
            locale="nl-NL"
        )

        # ====================================================
        # ZOEKEN
        # ====================================================

        for zoekterm in ZOEKTERMEN:

            print(f"🔎 Zoeken naar: {zoekterm}")

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
                    timeout=30000
                )

                page.wait_for_timeout(2000)

            except Exception as e:

                print("   ❌ Zoekfout:", e)
                continue

            kaarten = advertentiekaarten(page)

            goedkope = []

            for kaart in kaarten:

                prijs = kaart["prijs"]

                if prijs is None:
                    continue

                # Alleen echte prijzen tot €5
                if prijs <= MAX_PRIJS:

                    goedkope.append(kaart)

            print(
                f"   💰 Advertenties <= €5: "
                f"{len(goedkope)}"
            )

            for kaart in goedkope:

                titel = schone_titel(
                    kaart["tekst"]
                )

                if uitgesloten(titel):
                    continue

                if not interessant(titel):
                    continue

                kandidaten.append({
                    "url": kaart["url"],
                    "titel": titel,
                    "koopprijs": kaart["prijs"],
                    "zoekterm": zoekterm,
                })

        # ====================================================
        # DUBBELE ADVERTENTIES VERWIJDEREN
        # ====================================================

        unieke = {}

        for kandidaat in kandidaten:

            unieke[kandidaat["url"]] = kandidaat

        kandidaten = list(unieke.values())

        print()
        print(
            f"📦 {len(kandidaten)} echte advertenties "
            f"<= €{MAX_PRIJS:.0f} gevonden."
        )

        # Maximaal aantal controleren
        kandidaten = kandidaten[:MAX_KANDIDATEN]

        print(
            f"🔍 We controleren maximaal "
            f"{len(kandidaten)} kandidaten."
        )

        mogelijke_deals = []

        # ====================================================
        # ADVERTENTIES CONTROLEREN
        # ====================================================

        for nummer, kandidaat in enumerate(
            kandidaten,
            start=1
        ):

            titel = kandidaat["titel"]
            koopprijs = kandidaat["koopprijs"]
            url = kandidaat["url"]

            print()
            print(
                f"➡️ Controle {nummer}/"
                f"{len(kandidaten)}: {titel}"
            )

            print(
                f"   💰 Koopprijs uit zoekresultaatkaart: "
                f"€{koopprijs:.2f}"
            )

            # Zoektermen voor vergelijking
            vergelijking = titel[:80]

            print(
                f"   🔎 Vergelijken met: "
                f"{vergelijking}"
            )

            prijzen = zoek_verkoopprijzen(
                page,
                vergelijking
            )

            print(
                f"   📈 Vergelijkbare verkoopprijzen: "
                f"{prijzen}"
            )

            verkoopprijs = schat_verkoopprijs(
                prijzen
            )

            if verkoopprijs is None:

                print(
                    "   ❌ Te weinig betrouwbare "
                    "vergelijkingen."
                )

                continue

            print(
                f"   💵 Geschatte verkoopprijs: "
                f"€{verkoopprijs:.2f}"
            )

            winst = verkoopprijs - koopprijs

            # Alleen minimaal 2x waarde
            if verkoopprijs < koopprijs * 2:

                print(
                    "   ❌ Minder dan 2x "
                    "aankoopprijs."
                )

                continue

            # Vertrouwen bepalen
            if len(prijzen) >= 10:
                vertrouwen = 90
            elif len(prijzen) >= 6:
                vertrouwen = 80
            elif len(prijzen) >= 4:
                vertrouwen = 70
            else:
                vertrouwen = 60

            print("   🔥 DEAL!")

            mogelijke_deals.append({
                "titel": titel,
                "koopprijs": koopprijs,
                "verkoopprijs": verkoopprijs,
                "winst": winst,
                "url": url,
                "zoekterm": kandidaat["zoekterm"],
                "vertrouwen": vertrouwen,
            })

        # ====================================================
        # DISCORD MELDINGEN
        # ====================================================

        print()
        print(
            f"🔥 {len(mogelijke_deals)} "
            f"mogelijke deals gevonden."
        )

        for deal in mogelijke_deals:

            stuur_discord(
                titel=deal["titel"],
                koopprijs=deal["koopprijs"],
                verkoopprijs=deal["verkoopprijs"],
                winst=deal["winst"],
                url=deal["url"],
                zoekterm=deal["zoekterm"],
                vertrouwen=deal["vertrouwen"],
            )

        browser.close()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
```
