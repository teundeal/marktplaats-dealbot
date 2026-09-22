import asyncio
import re
import requests
import os
from urllib.parse import urljoin
from playwright.async_api import async_playwright

MARKTPLAATS_URL = (
    "https://www.marktplaats.nl/q/gratis/"
    "#PriceCentsTo:500|distanceMeters:8000|postcode:3116"
)

DISCORD_WEBHOOK = os.environ["DISCORD_WEBHOOK"]

MAX_PRIJS = 5

UITSLUITEN = [
    "bank", "bankstel", "hoekbank", "stoel", "tafel",
    "eettafel", "bureau", "bed", "matras", "kast",
    "kledingkast", "tuinset", "tuinbank", "pallet",
    "wasmachine", "droger", "koelkast", "vriezer",
    "vaatwasser", "piano", "grote tv", "televisie",
    "airco montage", "montage", "installatie", "reparatie",
    "klus", "dienst", "service", "vervoer"
]

INTERESSANT = [
    "iphone", "ipad", "samsung", "apple", "sony", "canon",
    "nikon", "camera", "lens", "objectief", "playstation",
    "ps4", "ps5", "xbox", "nintendo", "switch", "game",
    "games", "controller", "lego", "pokemon", "hot wheels",
    "nike", "adidas", "air jordan", "dyson", "logitech",
    "jbl", "bose", "garmin", "casio", "gopro", "dji",
    "koptelefoon", "speaker", "gereedschap", "accu",
    "boormachine", "verrekijker", "collectie", "verzameling"
]


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


def zoek_prijs(tekst):

    if "gratis" in tekst.lower():
        return 0.0

    gevonden = re.findall(
        r"€\s*([0-9]+(?:[.,][0-9]{1,2})?)",
        tekst
    )

    if not gevonden:
        return 0.0

    try:
        return float(gevonden[0].replace(",", "."))
    except:
        return 0.0


def bereken_score(titel, prijs):

    tekst = titel.lower()
    score = 20

    if prijs == 0:
        score += 25
    elif prijs <= 2:
        score += 20
    else:
        score += 10

    for woord in INTERESSANT:
        if woord in tekst:
            score += 10

    return min(score, 100)


def geschatte_verkoopprijs(titel, prijs):

    tekst = titel.lower()

    if any(x in tekst for x in [
        "iphone", "ipad", "playstation", "ps5",
        "ps4", "xbox", "nintendo switch"
    ]):
        return 25

    if any(x in tekst for x in [
        "camera", "lens", "objectief", "sony",
        "canon", "nikon", "gopro", "dji"
    ]):
        return 30

    if any(x in tekst for x in [
        "lego", "pokemon", "hot wheels", "air jordan"
    ]):
        return 20

    if any(x in tekst for x in [
        "nike", "adidas"
    ]):
        return 15

    if any(x in tekst for x in [
        "jbl", "bose", "speaker", "koptelefoon", "logitech"
    ]):
        return 15

    if any(x in tekst for x in [
        "gereedschap", "boormachine"
    ]):
        return 15

    if prijs == 0:
        return 10

    return max(prijs * 2, 10)


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
        "Dagtopper"
    ]

    for woord in verwijder:
        titel = titel.replace(woord, "")

    return " ".join(titel.split()).strip()


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
        print("❌ Marktplaats fout:", e)
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

            if href in bekende_links:
                continue

            bekende_links.add(href)

            titel = maak_titel_schoon(titel)

            if len(titel) < 3:
                continue

            prijs = zoek_prijs(titel)

            advertenties.append({
                "titel": titel,
                "prijs": prijs,
                "link": href
            })

        except:
            pass

    return advertenties


def controleer_deal(advertentie):

    titel = advertentie["titel"]
    prijs = advertentie["prijs"]
    tekst = titel.lower()

    if prijs > MAX_PRIJS:
        return None

    for woord in UITSLUITEN:
        if woord in tekst:
            return None

    score = bereken_score(titel, prijs)

    if score < 40:
        return None

    verkoopprijs = geschatte_verkoopprijs(
        titel,
        prijs
    )

    winst = verkoopprijs - prijs

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


async def main():

    print()
    print("======================================")
    print("   MARKTPLAATS DEALBOT")
    print("======================================")
    print("📍 Zoekgebied: 8 km rond 3116")
    print("💰 Maximum aankoop: €5")
    print()

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page()

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

            print()
            print("🔥 DEAL:", deal["titel"])
            print("💰 Aankoop:", f"€{deal['prijs']:.2f}")
            print("💵 Verkoop:", f"€{deal['verkoopprijs']:.2f}")
            print("📈 Winst:", f"€{deal['winst']:.2f}")
            print("⭐ Score:", deal["score"])
            print("🎯 Kans:", f"{deal['kans']}%")

            stuur_discord(
                deal["titel"],
                deal["prijs"],
                deal["verkoopprijs"],
                deal["winst"],
                deal["score"],
                deal["kans"],
                deal["link"]
            )

        await browser.close()

        print()
        print("✅ Zoekronde klaar.")


if __name__ == "__main__":
    asyncio.run(main())
