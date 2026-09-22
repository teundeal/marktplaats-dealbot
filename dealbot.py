import os
import re
import statistics
import requests

from urllib.parse import quote, urlparse
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
# PRIJS
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

    if "." in waarde and "," in waarde:
        waarde = waarde.replace(".", "")
        waarde = waarde.replace(",", ".")

    elif "," in waarde:
        waarde = waarde.replace(",", ".")

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
        for item in re.findall(patroon, tekst):
            prijs = euro_naar_float(item)

            if prijs is not None and prijs not in prijzen:
                prijzen.append(prijs)

    return prijzen


# ============================================================
# TITEL
# ============================================================

def schone_titel(tekst):
    if not tekst:
        return ""

    tekst = re.sub(r"\s+", " ", tekst).strip()

    rommel = [
        r"Bewaren in Mijn Favorieten",
        r"Details.*$",
        r"Ophalen.*$",
        r"Verzenden.*$",
        r"€\s*\d[\d.,]*.*$",
        r"\d[\d.,]*\s*€.*$",
    ]

    for patroon in rommel:
        tekst = re.sub(
            patroon,
            "",
            tekst,
            flags=re.IGNORECASE
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
    "problemen",
    "computerhulp",
    "hulp aan huis",
]


def is_dienst(tekst):
    tekst = tekst.lower()

    for woord in DIENSTEN:
        if re.search(
            r"\b" + re.escape(woord) + r"\b",
            tekst
        ):
            return True

    return False


# ============================================================
# GROTE SPULLEN
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
    "fiets",
    "brommer",
    "scooter",
    "motor",
    "auto",
    "caravan",
    "aanhanger",
]


def is_groot_spul(tekst):
    tekst = tekst.lower()

    return any(
        woord in tekst
        for woord in UITGESLOTEN
    )


# ============================================================
# PROMOTIES / EXTERNE SITES
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
    "catawiki",
    "catawiki.com",
    "auction",
    "veiling",
    "bied mee",
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
    "game",
    "controller",

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
]


def is_interessant(titel):
    titel = titel.lower()

    return any(
        woord in titel
        for woord in INTERESSANT
    )


# ============================================================
# MARKTPLAATS LINK CONTROLEREN
# ============================================================

def is_echte_marktplaats_link(href):
    if not href:
        return False

    try:
        parsed = urlparse(href)
        host = parsed.netloc.lower()

        if host.startswith("www."):
            host = host[4:]

        if host != "marktplaats.nl":
            return False

        if "/v/" not in parsed.path:
            return False

        return True

    except Exception:
        return False


# ============================================================
# AFSTAND
# ============================================================

def vind_afstand(tekst):
    if not tekst:
        return None

    patronen = [
        r"(\d+(?:[.,]\d+)?)\s*km\s*afstand",
        r"(\d+(?:[.,]\d+)?)\s*km",
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
# ADVERTENTIES LEZEN
# ============================================================

def lees_advertenties(page):

    advertenties = []

    links = page.locator(
        'a[href*="/v/"]'
    )

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

            # =================================================
            # ALLEEN ECHTE MARKTPLAATS LINKS
            # =================================================

            if not is_echte_marktplaats_link(href):

                print(
                    "   🚫 Externe link overgeslagen:",
                    href[:100]
                )

                continue

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

            # =================================================
            # CATAWIKI / EXTERNE PROMOTIES
            # =================================================

            if "catawiki" in laag:
                print(
                    "   🚫 Catawiki overgeslagen"
                )
                continue

            # =================================================
            # BIEDEN / RUILEN
            # =================================================

            if "bieden" in laag:
                continue

            if "ruilen" in laag:
                continue

            # =================================================
            # DIENSTEN / PROMOTIES
            # =================================================

            if is_promotie_of_dienst(tekst):
                continue

            # =================================================
            # GROTE SPULLEN
            # =================================================

            if is_groot_spul(tekst):
                continue

            # =================================================
            # AFSTAND
            # =================================================

            afstand = vind_afstand(tekst)

            # Geen afstand = niet betrouwbaar genoeg
            if afstand is None:
                continue

            # Buiten 8 km = overslaan
            if afstand > MAX_AFSTAND_KM:
                continue

            # =================================================
            # PRIJS
            # =================================================

            prijzen = vind_europrijzen(tekst)

            if not prijzen:
                continue

            aankoopprijs = None

            for prijs in prijzen:

                if 0 <= prijs <= MAX_PRIJS:

                    aankoopprijs = prijs
                    break

            if aankoopprijs is None:
                continue

            # =================================================
            # TITEL
            # =================================================

            titel = schone_titel(tekst)

            if not titel:
                continue

            if not is_interessant(titel):
                continue

            # =================================================
            # OPSLAAN
            # =================================================

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
# VERKOOPPRIJZEN ZOEKEN
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

        advertenties = (
            lees_vergelijkbare_advertenties(
                page
            )
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


# ============================================================
# VERGELIJKBARE ADVERTENTIES
# ============================================================

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

            # Alleen Marktplaats
            if not is_echte_marktplaats_link(
                href
            ):
                continue

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

            if "catawiki" in laag:
                continue

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

    # Extreme uitschieters verwijderen
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

    bericht = (
        "🔥 **MOGELIJKE MARKTPLAATS DEAL**\n\n"
        f"**{advertentie['titel']}**\n\n"
        f"💰 Aankoop: **€{aankoop:.2f}**\n"
        f"📈 Geschatte verkoop: **{verkoop_tekst}**\n"
        f"💵 Mogelijke winst: **{winst_tekst}**\n"
        f"📍 Afstand: **{afstand:.1f} km**\n"
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

                advertenties = (
                    lees_advertenties(page)
                )

                print(
                    f"   📦 {len(advertenties)} "
                    f"echte goedkope producten gevonden"
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
                f"💰 Aankoop: "
                f"€{advertentie['prijs']:.2f}"
            )

            print(
                f"📍 Afstand: "
                f"{advertentie['afstand']:.1f} km"
            )

            verkoopprijzen = (
                zoek_verkoopprijzen(
                    page,
                    advertentie["titel"]
                )
            )

            print(
                "📊 Vergelijkbare prijzen:",
                verkoopprijzen
            )

            verkoopprijs = (
                schat_verkoopprijs(
                    verkoopprijzen
                )
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
