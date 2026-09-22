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
# PRIJS OMZETTEN
# ============================================================

def euro_naar_float(tekst):
    if not tekst:
        return None

    tekst = tekst.strip()
    tekst = tekst.replace("€", "")
    tekst = tekst.replace("\xa0", " ")
    tekst = tekst.strip()

    match = re.search(r"\d[\d.,]*", tekst)

    if not match:
        return None

    waarde = match.group(0)

    # 1.500,00 -> 1500.00
    if "." in waarde and "," in waarde:
        waarde = waarde.replace(".", "")
        waarde = waarde.replace(",", ".")

    # 4,50 -> 4.50
    elif "," in waarde:
        waarde = waarde.replace(",", ".")

    # 1.500 -> 1500
    elif "." in waarde:
        delen = waarde.split(".")

        if len(delen) == 2 and len(delen[1]) == 3:
            waarde = waarde.replace(".", "")

    try:
        return float(waarde)
    except ValueError:
        return None


def vind_europrijzen(tekst):
    if not tekst:
        return []

    patronen = [
        r"€\s*\d[\d.,]*",
        r"\d[\d.,]*\s*€",
    ]

    gevonden = []

    for patroon in patronen:
        for match in re.findall(patroon, tekst):
            prijs = euro_naar_float(match)

            if prijs is not None and prijs not in gevonden:
                gevonden.append(prijs)

    return gevonden


# ============================================================
# TITEL SCHOONMAKEN
# ============================================================

ROMMEL_IN_TITEL = [
    "bewaren in mijn favorieten",
    "details",
    "ophalen",
    "verzenden",
    "nieuw",
    "zo goed als nieuw",
]


def schone_titel(tekst):
    if not tekst:
        return ""

    titel = re.sub(r"\s+", " ", tekst).strip()

    patronen = [
        r"\d[\d.,]*\s*€.*$",
        r"€\s*\d[\d.,]*.*$",
        r"\d[\d.,]*details.*$",
        r"details.*$",
        r"bewaren in mijn favorieten.*$",
        r"ophalen.*$",
        r"verzenden.*$",
    ]

    for patroon in patronen:
        titel = re.sub(
            patroon,
            "",
            titel,
            flags=re.IGNORECASE
        )

    for woord in ROMMEL_IN_TITEL:
        titel = re.sub(
            re.escape(woord),
            "",
            titel,
            flags=re.IGNORECASE
        )

    titel = re.sub(r"\s+", " ", titel).strip()

    return titel


# ============================================================
# DIENSTEN / NIET-PRODUCTEN
# ============================================================

DIENSTEN = [
    "dienst",
    "diensten",
    "service",
    "services",
    "installatie",
    "montage",
    "reparatie",
    "repareren",
    "onderhoud",
    "schoonmaak",
    "vervoer",
    "transport",
    "koerier",
    "verhuis",
    "verhuizing",
    "klusjesman",
    "klusbedrijf",
    "timmerman",
    "loodgieter",
    "elektricien",
    "schilder",
    "stucadoor",
    "tuinman",
    "tuinonderhoud",
    "fotograaf",
    "fotografie",
    "videografie",
    "website",
    "webdesign",
    "marketing",
    "advertentie",
    "cursus",
    "opleiding",
    "training",
    "les",
    "bijles",
    "coaching",
    "consult",
    "advies",
    "adviesgesprek",
    "abonnement",
    "lidmaatschap",
    "reservering",
    "evenement",
    "event",
    "tickets",
    "kaartjes",
    "vakantie",
    "overnachting",
    "oppas",
    "hondenuitlaat",
    "hondenopvang",
    "kattenoppas",
    "babysit",
    "belastingaangifte",
    "boekhouding",
    "accountancy",
]


def is_dienst(tekst):
    tekst = tekst.lower()

    for woord in DIENSTEN:
        if re.search(r"\b" + re.escape(woord) + r"\b", tekst):
            return True

    return False


# ============================================================
# GROTE PRODUCTEN UITSLUITEN
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
    "hoekzetel",
    "salontafel",
    "boekenkast",
]


def uitgesloten(tekst):
    tekst = tekst.lower()

    return any(
        woord in tekst
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
    "koptelefoon",
    "speaker",
    "bluetooth",
    "controller",
    "game",
]


def interessant(tekst):
    tekst = tekst.lower()

    return any(
        woord in tekst
        for woord in INTERESSANT
    )


# ============================================================
# PRODUCTCONTROLE
# ============================================================

def geldig_product(tekst):
    if not tekst:
        return False

    tekst_lower = tekst.lower()

    if is_dienst(tekst_lower):
        return False

    if uitgesloten(tekst_lower):
        return False

    verboden = [
        "op aanvraag",
        "prijs op aanvraag",
        "offerte",
        "vanaf €",
        "vanaf ",
        "per uur",
        "per dag",
        "per maand",
        "per week",
        "te huur",
        "huurprijs",
        "lease",
        "actie",
        "korting",
        "webshop",
        "winkel",
        "bestel",
        "leverbaar",
        "voorraad",
        "beperkte voorraad",
        "neem contact",
        "contacteer",
    ]

    for woord in verboden:
        if woord in tekst_lower:
            return False

    return True


# ============================================================
# ADVERTENTIEKAARTEN
# ============================================================

def advertentiekaarten(page, maximale_aankoopprijs=None):

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

            tekst_lower = tekst.lower()

            if "bieden" in tekst_lower:
                continue

            if "ruilen" in tekst_lower:
                continue

            if "op aanvraag" in tekst_lower:
                continue

            if not geldig_product(tekst):
                continue

            prijzen = vind_europrijzen(tekst)

            if not prijzen:
                continue

            prijs = None

            for gevonden_prijs in prijzen:

                if maximale_aankoopprijs is None:
                    prijs = gevonden_prijs
                    break

                if gevonden_prijs <= maximale_aankoopprijs:
                    prijs = gevonden_prijs
                    break

            if prijs is None:
                continue

            titel = schone_titel(tekst)

            if not titel:
                continue

            if maximale_aankoopprijs is not None:
                if not interessant(titel):
                    continue

            kaarten.append({
                "url": href,
                "tekst": tekst,
                "titel": titel,
                "prijs": prijs,
            })

        except Exception:
            continue

    unieke = {}

    for kaart in kaarten:
        unieke[kaart["url"]] = kaart

    return list(unieke.values())


# ============================================================
# VERKOOPPRIJZEN ZOEKEN
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

        kaarten = advertentiekaarten(
            page,
            maximale_aankoopprijs=None
        )

        prijzen = []

        for kaart in kaarten:
            prijs = kaart["prijs"]

            if prijs <= 0:
                continue

            prijzen.append(prijs)

        return prijzen[:20]

    except Exception:
        return []


# ============================================================
# VERKOOPPRIJS SCHATTEN
# ============================================================

def schat_verkoopprijs(prijzen):

    if not prijzen:
        return None

    normale_prijzen = [
        prijs
        for prijs in prijzen
        if prijs > 0
    ]

    if not normale_prijzen:
        return None

    return round(
        statistics.median(normale_prijzen),
        2
    )


# ============================================================
# DISCORD
# ============================================================

def stuur_discord(kaart, verkoopprijs, score):

    aankoopprijs = kaart["prijs"]

    if verkoopprijs is None:
        winst = None
    else:
        winst = verkoopprijs - aankoopprijs

    if winst is None:
        winst_tekst = "Onbekend"
    else:
        winst_tekst = f"€{winst:.2f}"

    if verkoopprijs is None:
        verkoop_tekst = "Onbekend"
    else:
        verkoop_tekst = f"€{verkoopprijs:.2f}"

    bericht = (
        "🔥 **MOGELIJKE MARKTPLAATS DEAL**\n\n"
        f"**{kaart['titel']}**\n\n"
        f"💰 Aankoop: **€{aankoopprijs:.2f}**\n"
        f"📈 Geschatte verkoop: **{verkoop_tekst}**\n"
        f"💵 Mogelijke winst: **{winst_tekst}**\n"
        f"⭐ Deal score: **{score}/10**\n\n"
        f"🔗 {kaart['url']}"
    )

    try:
        response = requests.post(
            DISCORD_WEBHOOK,
            json={"content": bericht},
            timeout=15
        )

        print(
            "Discord:",
            response.status_code
        )

    except Exception as fout:
        print(
            "Discord fout:",
            fout
        )


# ============================================================
# DEAL SCORE
# ============================================================

def bereken_score(aankoopprijs, verkoopprijs):

    if verkoopprijs is None:
        return 0

    winst = verkoopprijs - aankoopprijs

    if winst <= 0:
        return 0

    verhouding = winst / max(aankoopprijs, 0.01)

    if winst >= 50 and verhouding >= 5:
        return 10

    if winst >= 30 and verhouding >= 5:
        return 9

    if winst >= 20 and verhouding >= 4:
        return 8

    if winst >= 15 and verhouding >= 3:
        return 7

    if winst >= 10 and verhouding >= 2:
        return 6

    if winst >= 5:
        return 5

    return 4


# ============================================================
# HOOFDPROGRAMMA
# ============================================================

def main():

    print("====================================")
    print("MARKTPLAATS DEALBOT")
    print("====================================")
    print(f"📍 Postcode: {POSTCODE}")
    print(f"📏 Afstand: {AFSTAND / 1000:.1f} km")
    print(f"💰 Maximale aankoopprijs: €{MAX_PRIJS:.2f}")
    print()

    gevonden_deals = []

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page()

        for zoekterm in ZOEKTERMEN:

            print(
                f"🔎 Zoeken naar: {zoekterm}"
            )

            url = (
                "https://www.marktplaats.nl/q/"
                + quote(zoekterm)
                + "/"
                f"?postcode={POSTCODE}"
                f"&distanceMeters={AFSTAND}"
                f"&priceCentsTo={int(MAX_PRIJS * 100)}"
            )

            try:

                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=30000
                )

                page.wait_for_timeout(2000)

                kaarten = advertentiekaarten(
                    page,
                    maximale_aankoopprijs=MAX_PRIJS
                )

                print(
                    f"   📦 {len(kaarten)} kandidaten"
                )

                for kaart in kaarten:

                    if len(gevonden_deals) >= MAX_KANDIDATEN:
                        break

                    if any(
                        bestaande["url"] == kaart["url"]
                        for bestaande in gevonden_deals
                    ):
                        continue

                    gevonden_deals.append(kaart)

            except Exception as fout:

                print(
                    f"   ❌ Fout bij {zoekterm}: {fout}"
                )

        print()
        print(
            f"📦 Totaal kandidaten: {len(gevonden_deals)}"
        )
        print()

        for kaart in gevonden_deals:

            print(
                f"💡 {kaart['titel']} - "
                f"€{kaart['prijs']:.2f}"
            )

            zoekterm = kaart["titel"]

            verkoopprijzen = zoek_verkoopprijzen(
                page,
                zoekterm
            )

            print(
                f"   Vergelijkbare prijzen: "
                f"{verkoopprijzen}"
            )

            verkoopprijs = schat_verkoopprijs(
                verkoopprijzen
            )

            score = bereken_score(
                kaart["prijs"],
                verkoopprijs
            )

            print(
                f"   Geschatte verkoop: "
                f"{verkoopprijs}"
            )

            print(
                f"   Score: {score}/10"
            )

            if score >= 5:

                stuur_discord(
                    kaart,
                    verkoopprijs,
                    score
                )

                print(
                    "   ✅ Naar Discord gestuurd"
                )

            else:

                print(
                    "   ⏭️ Geen sterke deal"
                )

            print()

        browser.close()

    print("====================================")
    print("KLAAR")
    print("====================================")


if __name__ == "__main__":
    main()
