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
MAX_AFSTAND_KM = 8
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

MAX_KANDIDATEN = 20


# ============================================================
# PRIJS HERKENNEN
# ============================================================

def euro_naar_float(tekst):
    if not tekst:
        return None

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

    prijzen = []

    for patroon in patronen:
        gevonden = re.findall(patroon, tekst)

        for item in gevonden:
            prijs = euro_naar_float(item)

            if prijs is not None and prijs not in prijzen:
                prijzen.append(prijs)

    return prijzen


# ============================================================
# TITEL SCHOONMAKEN
# ============================================================

def schone_titel(tekst):
    if not tekst:
        return ""

    tekst = re.sub(r"\s+", " ", tekst).strip()

    # Veelvoorkomende Marktplaats-rommel verwijderen
    tekst = re.sub(
        r"Bewaren in Mijn Favorieten",
        "",
        tekst,
        flags=re.IGNORECASE
    )

    tekst = re.sub(
        r"Details.*$",
        "",
        tekst,
        flags=re.IGNORECASE
    )

    tekst = re.sub(
        r"Ophalen.*$",
        "",
        tekst,
        flags=re.IGNORECASE
    )

    tekst = re.sub(
        r"Verzenden.*$",
        "",
        tekst,
        flags=re.IGNORECASE
    )

    # Prijs en alles erna verwijderen
    tekst = re.sub(
        r"€\s*\d[\d.,]*.*$",
        "",
        tekst
    )

    tekst = re.sub(
        r"\d[\d.,]*\s*€.*$",
        "",
        tekst
    )

    return re.sub(r"\s+", " ", tekst).strip()


# ============================================================
# DIENSTEN
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
    "cursus",
    "opleiding",
    "training",
    "bijles",
    "coaching",
    "consult",
    "advies",
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
# GROTE / ONHANDIGE SPULLEN
# ============================================================

UITGESLOTEN = [
    "hoekbank",
    "bankstel",
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
    "televisie",
    "grote tv",
    "tv meubel",
    "kastje",
    "tuinset",
    "loungeset",
    "trampoline",
    "hoekzetel",
    "salontafel",
    "boekenkast",
    "massagestoel",
    "fitnessapparaat",
]


def is_groot_spul(tekst):
    tekst = tekst.lower()

    return any(
        woord in tekst
        for woord in UITGESLOTEN
    )


# ============================================================
# PROMOTIES / TOPADVERTENTIES
# ============================================================

VERBODEN = [
    "topadvertentie",
    "bezoek website",
    "op aanvraag",
    "prijs op aanvraag",
    "offerte",
    "vanaf ",
    "per uur",
    "per dag",
    "per maand",
    "per week",
    "te huur",
    "huurprijs",
    "lease",
    "webshop",
    "winkel",
    "bestel",
    "leverbaar",
    "voorraad",
    "neem contact",
    "contacteer",
    "bel voor",
    "whatsapp voor",
    "afspraak",
]


def is_promotie_of_dienst(tekst):
    laag = tekst.lower()

    if is_dienst(laag):
        return True

    for woord in VERBODEN:
        if woord in laag:
            return True

    return False


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


def is_interessant(titel):
    titel = titel.lower()

    return any(
        woord in titel
        for woord in INTERESSANT
    )


# ============================================================
# AFSTAND HERKENNEN
# ============================================================

def vind_afstand(tekst):
    if not tekst:
        return None

    patronen = [
        r"(\d+(?:[.,]\d+)?)\s*km",
        r"(\d+(?:[.,]\d+)?)\s*km afstand",
    ]

    for patroon in patronen:
        match = re.search(
            patroon,
            tekst.lower()
        )

        if match:
            waarde = match.group(1)
            waarde = waarde.replace(",", ".")

            try:
                return float(waarde)
            except ValueError:
                pass

    return None


# ============================================================
# ADVERTENTIES UITLEZEN
# ============================================================

def lees_advertenties(page):

    advertenties = []

    links = page.locator('a[href*="/v/"]')

    aantal = links.count()

    print(
        f"   🔗 {aantal} advertentielinks gevonden"
    )

    urls_al_gezien = set()

    for i in range(aantal):

        try:

            link = links.nth(i)

            href = link.get_attribute("href")

            if not href:
                continue

            if not href.startswith("http"):
                href = (
                    "https://www.marktplaats.nl"
                    + href
                )

            if href in urls_al_gezien:
                continue

            urls_al_gezien.add(href)

            tekst = link.inner_text(
                timeout=3000
            )

            if not tekst:
                continue

            tekst = re.sub(
                r"\s+",
                " ",
                tekst
            ).strip()

            laag = tekst.lower()

            # Bieden/ruilen is geen vaste aankoopprijs
            if "bieden" in laag:
                continue

            if "ruilen" in laag:
                continue

            # Diensten/promoties eruit
            if is_promotie_of_dienst(tekst):
                continue

            # Grote spullen eruit
            if is_groot_spul(tekst):
                continue

            prijzen = vind_europrijzen(tekst)

            if not prijzen:
                continue

            # Zoek een prijs die maximaal €5 is
            aankoopprijs = None

            for prijs in prijzen:

                if 0 <= prijs <= MAX_PRIJS:
                    aankoopprijs = prijs
                    break

            if aankoopprijs is None:
                continue

            titel = schone_titel(tekst)

            if not titel:
                continue

            # Alleen interessante producten
            if not is_interessant(titel):
                continue

            afstand = vind_afstand(tekst)

            advertenties.append({
                "url": href,
                "titel": titel,
                "prijs": aankoopprijs,
                "afstand": afstand,
                "tekst": tekst,
            })

        except Exception:
            continue

    return advertenties


# ============================================================
# VERKOOPPRIJZEN
# ============================================================

def zoek_verkoopprijzen(page, zoekterm):

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

        page.wait_for_timeout(1500)

        advertenties = lees_vergelijkbare_advertenties(
            page
        )

        prijzen = []

        for advertentie in advertenties:

            prijs = advertentie["prijs"]

            if prijs > 0:
                prijzen.append(prijs)

        return prijzen[:20]

    except Exception as fout:

        print(
            "   ⚠️ Verkoopprijs zoeken mislukt:",
            fout
        )

        return []


def lees_vergelijkbare_advertenties(page):

    resultaten = []

    links = page.locator(
        'a[href*="/v/"]'
    )

    aantal = links.count()

    urls = set()

    for i in range(aantal):

        try:

            link = links.nth(i)

            href = link.get_attribute("href")

            if not href:
                continue

            if not href.startswith("http"):
                href = (
                    "https://www.marktplaats.nl"
                    + href
                )

            if href in urls:
                continue

            urls.add(href)

            tekst = link.inner_text(
                timeout=3000
            )

            if not tekst:
                continue

            tekst = re.sub(
                r"\s+",
                " ",
                tekst
            ).strip()

            laag = tekst.lower()

            if "bieden" in laag:
                continue

            if "ruilen" in laag:
                continue

            if is_promotie_of_dienst(tekst):
                continue

            prijzen = vind_europrijzen(tekst)

            if not prijzen:
                continue

            prijs = prijzen[0]

            if prijs <= 0:
                continue

            resultaten.append({
                "prijs": prijs,
                "tekst": tekst,
            })

        except Exception:
            continue

    return resultaten


# ============================================================
# VERKOOPPRIJS SCHATTEN
# ============================================================

def schat_verkoopprijs(prijzen):

    if not prijzen:
        return None

    prijzen = [
        p for p in prijzen
        if p > 0
    ]

    if not prijzen:
        return None

    # Extreme uitschieters zoveel mogelijk verwijderen
    if len(prijzen) >= 4:

        mediaan = statistics.median(
            prijzen
        )

        prijzen = [
            p for p in prijzen
            if p <= mediaan * 3
        ]

    if not prijzen:
        return None

    return round(
        statistics.median(prijzen),
        2
    )


# ============================================================
# DEAL SCORE
# ============================================================

def bereken_score(
    aankoopprijs,
    verkoopprijs
):

    if verkoopprijs is None:
        return 0

    winst = (
        verkoopprijs
        - aankoopprijs
    )

    if winst <= 0:
        return 0

    verhouding = (
        winst
        / max(aankoopprijs, 0.01)
    )

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
# DISCORD
# ============================================================

def stuur_discord(
    advertentie,
    verkoopprijs,
    score
):

    aankoop = advertentie["prijs"]

    if verkoopprijs is None:
        winst = None
    else:
        winst = (
            verkoopprijs
            - aankoop
        )

    if verkoopprijs is None:
        verkoop_tekst = "Onbekend"
    else:
        verkoop_tekst = (
            f"€{verkoopprijs:.2f}"
        )

    if winst is None:
        winst_tekst = "Onbekend"
    else:
        winst_tekst = (
            f"€{winst:.2f}"
        )

    afstand = advertentie["afstand"]

    if afstand is None:
        afstand_tekst = "Niet gevonden"
    else:
        afstand_tekst = (
            f"{afstand:.1f} km"
        )

    bericht = (
        "🔥 **MOGELIJKE MARKTPLAATS DEAL**\n\n"
        f"**{advertentie['titel']}**\n\n"
        f"💰 Aankoop: **€{aankoop:.2f}**\n"
        f"📈 Geschatte verkoop: **{verkoop_tekst}**\n"
        f"💵 Mogelijke winst: **{winst_tekst}**\n"
        f"📍 Afstand: **{afstand_tekst}**\n"
        f"⭐ Deal score: **{score}/10**\n\n"
        f"🔗 {advertentie['url']}"
    )

    try:

        response = requests.post(
            DISCORD_WEBHOOK,
            json={
                "content": bericht
            },
            timeout=15
        )

        print(
            "   Discord:",
            response.status_code
        )

    except Exception as fout:

        print(
            "   ❌ Discord fout:",
            fout
        )


# ============================================================
# HOOFDPROGRAMMA
# ============================================================

def main():

    print("====================================")
    print("MARKTPLAATS DEALBOT")
    print("====================================")
    print(
        f"📍 Postcode: {POSTCODE}"
    )
    print(
        f"📏 Maximale afstand: {MAX_AFSTAND_KM} km"
    )
    print(
        f"💰 Maximale aankoopprijs: €{MAX_PRIJS:.2f}"
    )
    print()

    gevonden = []

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            locale="nl-NL"
        )

        # ====================================================
        # ZOEKEN
        # ====================================================

        for zoekterm in ZOEKTERMEN:

            print(
                f"🔎 Zoeken naar: {zoekterm}"
            )

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

                advertenties = lees_advertenties(
                    page
                )

                print(
                    f"   📦 {len(advertenties)} goedkope producten gevonden"
                )

                for advertentie in advertenties:

                    if len(gevonden) >= MAX_KANDIDATEN:
                        break

                    if any(
                        a["url"]
                        == advertentie["url"]
                        for a in gevonden
                    ):
                        continue

                    gevonden.append(
                        advertentie
                    )

            except Exception as fout:

                print(
                    f"   ❌ Zoekfout: {fout}"
                )

        print()
        print(
            f"📦 Totaal gevonden: {len(gevonden)}"
        )
        print()

        # ====================================================
        # VERKOOPWAARDE CONTROLEREN
        # ====================================================

        for advertentie in gevonden:

            print(
                "------------------------------------"
            )

            print(
                f"💡 {advertentie['titel']}"
            )

            print(
                f"💰 Aankoop: €{advertentie['prijs']:.2f}"
            )

            zoekterm = advertentie["titel"]

            verkoopprijzen = zoek_verkoopprijzen(
                page,
                zoekterm
            )

            print(
                "📊 Vergelijkbare prijzen:",
                verkoopprijzen
            )

            verkoopprijs = schat_verkoopprijs(
                verkoopprijzen
            )

            print(
                "📈 Geschatte verkoop:",
                verkoopprijs
            )

            score = bereken_score(
                advertentie["prijs"],
                verkoopprijs
            )

            print(
                f"⭐ Score: {score}/10"
            )

            # Alleen echte interessante deals
            if score >= 5:

                stuur_discord(
                    advertentie,
                    verkoopprijs,
                    score
                )

                print(
                    "   ✅ Deal naar Discord gestuurd"
                )

            else:

                print(
                    "   ⏭️ Geen sterke deal"
                )

        browser.close()

    print()
    print("====================================")
    print("KLAAR")
    print("====================================")


if __name__ == "__main__":
    main()
