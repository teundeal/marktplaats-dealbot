import asyncio
import re
import requests
from urllib.parse import urljoin
from playwright.async_api import async_playwright


# =========================
# INSTELLINGEN
# =========================

MARKTPLAATS_URL = (
    "https://www.marktplaats.nl/q/gratis/"
    "#PriceCentsTo:500|distanceMeters:8000|postcode:3116"
)

DISCORD_WEBHOOK = "HIER_JOUW_WEBHOOK"

MAX_PRIJS = 5
CONTROLE_INTERVAL = 300  # 5 minuten


# Woorden waarmee we grote/onhandige spullen overslaan
UITSLUITEN = [
    "bank",
    "bankstel",
    "hoekbank",
    "stoel",
    "tafel",
    "eettafel",
    "bureau",
    "bed",
    "matras",
    "kast",
    "kledingkast",
    "tuinset",
    "tuinbank",
    "pallet",
    "wasmachine",
    "droger",
    "koelkast",
    "vriezer",
    "vaatwasser",
    "piano",
    "grote tv",
    "televisie",
    "airco montage",
    "montage",
    "installatie",
    "reparatie",
    "klus",
    "dienst",
    "service",
    "vervoer",
]


# Dingen die interessant kunnen zijn om goedkoop te kopen
INTERESSANT = [
    "iphone",
    "ipad",
    "samsung",
    "apple",
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
    "games",
    "controller",
    "lego",
    "pokemon",
    "hot wheels",
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
    "accu",
    "boormachine",
    "verrekijker",
    "collectie",
    "verzameling",
]


# =========================
# DISCORD
# =========================

def stuur_discord(titel, prijs, verkoopprijs, winst, score, kans, link):

    bericht = {
        "content": (
            "🚨 **MOGELIJKE MARKTPLAATS DEAL** 🚨\n\n"
            f"**{titel}**\n\n"
            f"💰 Aankoop: **€{prijs:.2f}**\n"
            f"💵 Geschatte verkoop: **€{verkoopprijs:.2f}**\n"
            f"📈 Mogelijke winst: **€{winst:.2f}**\n"
            f"⭐ Deal score: **{score}/100**\n"
            f"🎯 Verkoopkans: **{kans}% (schatting)**\n\n"
            f"🔗 {link}"
        )
    }

    try:
        response = requests.post(
            DISCORD_WEBHOOK,
            json=bericht,
            timeout=15
        )

        if response.status_code in [200, 204]:
            print("✅ Discord melding verstuurd")
        else:
            print("❌ Discord fout:", response.status_code)
            print(response.text)

    except Exception as e:
        print("❌ Discord verbinding mislukt:", e)


# =========================
# PRIJS
# =========================

def zoek_prijs(tekst):

    tekst_lower = tekst.lower()

    if "gratis" in tekst_lower:
        return 0.0

    gevonden = re.findall(
        r"€\s*([0-9]+(?:[.,][0-9]{1,2})?)",
        tekst
    )

    if not gevonden:
        return None

    try:
        prijs = gevonden[0].replace(",", ".")
        return float(prijs)
    except:
        return None


# =========================
# SCORE
# =========================

def bereken_score(titel, prijs):

    tekst = titel.lower()

    score = 20

    # Gratis is interessant
    if prijs == 0:
        score += 25

    # Lage prijs
    elif prijs <= 2:
        score += 20

    elif prijs <= 5:
        score += 10

    # Interessante producten
    for woord in INTERESSANT:
        if woord in tekst:
            score += 10

    # Maximaal 100
    return min(score, 100)


# =========================
# VERKOOPPRIJS SCHATTING
# =========================

def geschatte_verkoopprijs(titel, prijs):

    tekst = titel.lower()

    # Globale schattingen
    if any(x in tekst for x in [
        "iphone",
        "ipad",
        "playstation",
        "ps5",
        "ps4",
        "xbox",
        "nintendo switch",
    ]):
        return 25

    if any(x in tekst for x in [
        "camera",
        "lens",
        "objectief",
        "sony",
        "canon",
        "nikon",
        "gopro",
        "dji",
    ]):
        return 30

    if any(x in tekst for x in [
        "lego",
        "pokemon",
        "hot wheels",
        "air jordan",
    ]):
        return 20

    if any(x in tekst for x in [
        "nike",
        "adidas",
    ]):
        return 15

    if any(x in tekst for x in [
        "jbl",
        "bose",
        "speaker",
        "koptelefoon",
        "logitech",
    ]):
        return 15

    if any(x in tekst for x in [
        "gereedschap",
        "boormachine",
    ]):
        return 15

    # Algemene kleine spullen
    if prijs == 0:
        return 10

    return max(prijs * 2, 10)


# =========================
# TITEL OPSCHONEN
# =========================

def maak_titel_schoon(titel):

    verwijder = [
        "Bewaren in Mijn Favorieten",
        "Details",
        "Gratis",
        "Gebruikt",
        "Zo goed als nieuw",
        "Nieuw",
        "Ophalen",
        "Verzenden",
        "Vandaag",
        "Dagtopper",
    ]

    for woord in verwijder:
        titel = titel.replace(woord, "")

    titel = " ".join(titel.split())

    return titel.strip()


# =========================
# ADVERTENTIES OPHALEN
# =========================

async def zoek_advertenties(page):

    print("🔎 Marktplaats controleren...")

    try:
        await page.goto(
            MARKTPLAATS_URL,
            wait_until="domcontentloaded",
            timeout=60000
        )

        await page.wait_for_timeout(8000)

    except Exception as e:
        print("❌ Marktplaats kon niet worden geopend:", e)
        return []

    links = await page.locator(
        'a[href*="/v/"]'
    ).all()

    advertenties = []
    bekende_links = set()

    for link in links:

        try:

            titel = await link.inner_text()
            href = await link.get_attribute("href")

            if not titel or not href:
                continue

            href = urljoin(
                "https://www.marktplaats.nl",
                href
            )

            # Alleen echte advertentielinks
            if "/v/" not in href:
                continue

            # Dubbele advertenties overslaan
            if href in bekende_links:
                continue

            bekende_links.add(href)

            titel = maak_titel_schoon(titel)

            if len(titel) < 3:
                continue

            prijs = zoek_prijs(titel)

            # Soms staat de prijs niet in de linktekst.
            # Omdat de zoekpagina al maximaal €5 filtert,
            # behandelen we onbekende prijs als 0 voor verdere beoordeling.
            if prijs is None:
                prijs = 0.0

            advertenties.append({
                "titel": titel,
                "prijs": prijs,
                "link": href
            })

        except:
            pass

    return advertenties


# =========================
# DEAL CONTROLEREN
# =========================

def controleer_deal(advertentie):

    titel = advertentie["titel"]
    prijs = advertentie["prijs"]

    tekst = titel.lower()

    # Te duur
    if prijs > MAX_PRIJS:
        return None

    # Grote spullen / diensten uitsluiten
    for woord in UITSLUITEN:
        if woord in tekst:
            return None

    score = bereken_score(
        titel,
        prijs
    )

    # Alleen voldoende interessante deals
    if score < 40:
        return None

    verkoopprijs = geschatte_verkoopprijs(
        titel,
        prijs
    )

    winst = verkoopprijs - prijs

    # Verkoopkans is alleen een ruwe schatting
    kans = min(
        95,
        35 + score // 2
    )

    return {
        "titel": titel,
        "prijs": prijs,
        "verkoopprijs": verkoopprijs,
        "winst": winst,
        "score": score,
        "kans": kans,
        "link": advertentie["link"]
    }


# =========================
# HOOFDPROGRAMMA
# =========================

async def main():

    reeds_gemeld = set()

    print()
    print("======================================")
    print("   MARKTPLAATS DEALBOT")
    print("======================================")
    print()
    print("📍 Zoekgebied: 8 km rond 3116")
    print("💰 Maximum aankoop: €5")
    print("📱 Discord: actief")
    print()
    print("Bot gestart!")
    print()

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=False
        )

        page = await browser.new_page()

        while True:

            advertenties = await zoek_advertenties(page)

            print(
                f"📦 {len(advertenties)} unieke advertenties gevonden."
            )

            deals = []

            for advertentie in advertenties:

                deal = controleer_deal(
                    advertentie
                )

                if deal:
                    deals.append(deal)

            print(
                f"🔥 {len(deals)} mogelijke deals gevonden."
            )

            for deal in deals:

                link = deal["link"]

                if link in reeds_gemeld:
                    continue

                reeds_gemeld.add(link)

                print()
                print("🔥 DEAL:")
                print(
                    "Titel:",
                    deal["titel"]
                )
                print(
                    "Aankoop:",
                    f"€{deal['prijs']:.2f}"
                )
                print(
                    "Verkoop:",
                    f"€{deal['verkoopprijs']:.2f}"
                )
                print(
                    "Winst:",
                    f"€{deal['winst']:.2f}"
                )
                print(
                    "Score:",
                    deal["score"]
                )
                print(
                    "Verkoopkans:",
                    f"{deal['kans']}%"
                )
                print(
                    "Link:",
                    deal["link"]
                )

                stuur_discord(
                    deal["titel"],
                    deal["prijs"],
                    deal["verkoopprijs"],
                    deal["winst"],
                    deal["score"],
                    deal["kans"],
                    deal["link"]
                )

            print()
            print(
                f"⏱️ Volgende controle over "
                f"{CONTROLE_INTERVAL // 60} minuten..."
            )
            print()

            await asyncio.sleep(
                CONTROLE_INTERVAL
            )


if __name__ == "__main__":
    asyncio.run(main())