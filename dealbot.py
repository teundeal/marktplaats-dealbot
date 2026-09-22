import asyncio
import re
import requests
import os
from urllib.parse import urljoin, quote
from statistics import median
from playwright.async_api import async_playwright

MARKTPLAATS_URL = (
    "https://www.marktplaats.nl/q/gratis/"
    "#PriceCentsTo:500|distanceMeters:8000|postcode:3116"
)

DISCORD_WEBHOOK = os.environ["DISCORD_WEBHOOK"]

MAX_PRIJS = 5.00
MIN_VERKOOPWAARDE = 10.00
MIN_VERTROUWEN = 70

UITSLUITEN = [
    "bank", "bankstel", "hoekbank", "stoel", "tafel",
    "eettafel", "bureau", "bed", "matras", "kast",
    "kledingkast", "tuinset", "tuinbank", "pallet",
    "wasmachine", "droger", "koelkast", "vriezer",
    "vaatwasser", "piano", "grote tv", "televisie",
    "airco", "montage", "installatie", "reparatie",
    "klus", "dienst", "service", "vervoer", "verhuizen",
    "afvoer", "grond", "tegels", "klinkers", "stenen"
]

INTERESSANT = [
    "iphone", "ipad", "samsung", "apple", "sony", "canon",
    "nikon", "camera", "lens", "objectief", "playstation",
    "ps4", "ps5", "xbox", "nintendo", "switch", "game",
    "games", "controller", "lego", "pokemon", "hot wheels",
    "nike", "adidas", "air jordan", "dyson", "logitech",
    "jbl", "bose", "garmin", "casio", "gopro", "dji",
    "koptelefoon", "speaker", "gereedschap", "boormachine",
    "verrekijker", "horloge", "watch", "collectie",
    "verzameling", "modelauto", "burago", "ferrari",
    "mercedes", "bmw", "porsche", "nokia", "tablet",
    "monitor", "toetsenbord", "muis", "printer"
]


def stuur_discord(deal):

    bericht = {
        "content": (
            "🚨 **MOGELIJKE MARKTPLAATS DEAL** 🚨\n\n"
            f"**{deal['titel']}**\n\n"
            f"💰 Aankoop: **€{deal['prijs']:.2f}**\n"
            f"💵 Geschatte verkoop: **€{deal['verkoopprijs']:.2f}**\n"
            f"📈 Mogelijke winst: **€{deal['winst']:.2f}**\n"
            f"⭐ Deal score: **{deal['score']}/100**\n"
            f"🎯 Vertrouwen: **{deal['vertrouwen']}%**\n"
            f"🔎 Vergelijkbare advertenties: **{deal['vergelijkbare']}**\n\n"
            f"🔗 {deal['link']}"
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


def zoek_prijs(tekst):

    if "gratis" in tekst.lower():
        return 0.0

    gevonden = re.findall(
        r"€\s*([0-9]+(?:[.,][0-9]{1,2})?)",
        tekst
    )

    if not gevonden:
        return None

    try:
        return float(gevonden[0].replace(",", "."))
    except:
        return None


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


def uitgesloten(titel):

    tekst = titel.lower()

    return any(
        woord in tekst
        for woord in UITSLUITEN
    )


def bevat_interessant_woord(titel):

    tekst = titel.lower()

    return any(
        woord in tekst
        for woord in INTERESSANT
    )


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

            advertenties.append({
                "titel": titel,
                "prijs": zoek_prijs(titel),
                "link": href
            })

        except:
            pass

    return advertenties


def maak_zoekterm(titel):

    woorden = re.findall(
        r"[a-zA-Z0-9]+",
        titel.lower()
    )

    # Veelvoorkomende nutteloze woorden verwijderen
    stopwoorden = {
        "gratis", "nieuw", "gebruikte", "gebruikt",
        "mooie", "mooie", "zeer", "goede", "goed",
        "te", "koop", "af", "halen", "voor"
    }

    woorden = [
        woord
        for woord in woorden
        if len(woord) >= 3
        and woord not in stopwoorden
    ]

    # Bekende merk/productwoorden krijgen voorrang
    bekende = [
        woord for woord in woorden
        if woord in INTERESSANT
    ]

    if bekende:
        return " ".join(bekende[:3])

    return " ".join(woorden[:3])


async def vergelijkbare_prijzen(page, titel):

    zoekterm = maak_zoekterm(titel)

    if not zoekterm:
        return []

    url = (
        "https://www.marktplaats.nl/q/"
        + quote(zoekterm)
    )

    print(f"   🔎 Vergelijken: {zoekterm}")

    try:

        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=45000
        )

        await page.wait_for_timeout(5000)

    except:
        print("   ⚠️ Vergelijking mislukt")
        return []

    links = await page.locator(
        'a[href*="/v/"]'
    ).all()

    prijzen = []

    for link in links[:50]:

        try:

            tekst = await link.inner_text()

            if not tekst:
                continue

            tekst_lower = tekst.lower()

            if any(
                woord in tekst_lower
                for woord in UITSLUITEN
            ):
                continue

            gevonden = re.findall(
                r"€\s*([0-9]+(?:[.,][0-9]{1,2})?)",
                tekst
            )

            if not gevonden:
                continue

            waarde = float(
                gevonden[0].replace(",", ".")
            )

            if 1 <= waarde <= 5000:
                prijzen.append(waarde)

        except:
            pass

    return prijzen


def bereken_vertrouwen(
    titel,
    vergelijkbare
):

    aantal = len(vergelijkbare)

    if aantal < 3:
        return 0

    vertrouwen = 50

    if aantal >= 5:
        vertrouwen += 10

    if aantal >= 8:
        vertrouwen += 10

    if aantal >= 12:
        vertrouwen += 5

    if bevat_interessant_woord(titel):
        vertrouwen += 10

    return min(95, vertrouwen)


def bereken_score(
    titel,
    prijs,
    verkoopprijs,
    vertrouwen
):

    score = 30

    if prijs == 0:
        score += 20
    elif prijs <= 2:
        score += 15
    else:
        score += 10

    if bevat_interessant_woord(titel):
        score += 15

    if prijs > 0 and verkoopprijs >= prijs * 3:
        score += 15
    elif prijs > 0 and verkoopprijs >= prijs * 2:
        score += 10

    if vertrouwen >= 80:
        score += 10

    return min(score, 100)


async def controleer_deal(page, advertentie):

    titel = advertentie["titel"]
    prijs = advertentie["prijs"]

    if prijs is None:
        return None

    if prijs > MAX_PRIJS:
        return None

    if uitgesloten(titel):
        return None

    # Nu NIET meer verplicht een bekend merk te hebben.
    vergelijkbare = await vergelijkbare_prijzen(
        page,
        titel
    )

    if len(vergelijkbare) < 3:
        print(
            f"   ❌ Te weinig vergelijkbare advertenties: "
            f"{titel}"
        )
        return None

    verkoopprijs = median(vergelijkbare)

    vertrouwen = bereken_vertrouwen(
        titel,
        vergelijkbare
    )

    # Gratis spullen moeten minimaal ongeveer €10 waard zijn.
    if prijs == 0:
        dubbele_waarde = (
            verkoopprijs >= MIN_VERKOOPWAARDE
        )
    else:
        dubbele_waarde = (
            verkoopprijs >= prijs * 2
        )

    if not dubbele_waarde:
        print(
            f"   ❌ Minder dan 2x waarde: {titel}"
        )
        return None

    if verkoopprijs < MIN_VERKOOPWAARDE:
        return None

    if vertrouwen < MIN_VERTROUWEN:
        print(
            f"   ❌ Vertrouwen te laag: "
            f"{vertrouwen}% - {titel}"
        )
        return None

    winst = verkoopprijs - prijs

    score = bereken_score(
        titel,
        prijs,
        verkoopprijs,
        vertrouwen
    )

    return {
        "titel": titel,
        "prijs": prijs,
        "verkoopprijs": verkoopprijs,
        "winst": winst,
        "score": score,
        "vertrouwen": vertrouwen,
        "vergelijkbare": len(vergelijkbare),
        "link": advertentie["link"]
    }


async def main():

    print()
    print("======================================")
    print("       MARKTPLAATS DEALBOT")
    print("======================================")
    print("📍 Zoekgebied: 8 km rond 3116")
    print("💰 Maximum aankoop: €5")
    print("📈 Minimaal: 2x verwachte waarde")
    print("🎯 Minimaal vertrouwen: 70%")
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

            deal = await controleer_deal(
                page,
                advertentie
            )

            if deal:
                deals.append(deal)

        print()
        print(
            f"🔥 {len(deals)} mogelijke deals gevonden."
        )

        for deal in deals:

            print()
            print(
                "🔥 DEAL:",
                deal["titel"]
            )
            print(
                "💰 Aankoop:",
                f"€{deal['prijs']:.2f}"
            )
            print(
                "💵 Verkoop:",
                f"€{deal['verkoopprijs']:.2f}"
            )
            print(
                "📈 Winst:",
                f"€{deal['winst']:.2f}"
            )
            print(
                "⭐ Score:",
                deal["score"]
            )
            print(
                "🎯 Vertrouwen:",
                f"{deal['vertrouwen']}%"
            )

            stuur_discord(deal)

        await browser.close()

        print()
        print("✅ Zoekronde klaar.")


if __name__ == "__main__":
    asyncio.run(main())
