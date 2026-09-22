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
MIN_VERKOOPPRIJS = 10.00
MIN_VERTROUWEN = 70

UITSLUITEN = [
    "bank", "bankstel", "hoekbank", "stoel", "tafel",
    "eettafel", "bureau", "bed", "matras", "kast",
    "kledingkast", "tuinset", "tuinbank", "pallet",
    "wasmachine", "droger", "koelkast", "vriezer",
    "vaatwasser", "piano", "grote tv", "televisie",
    "airco montage", "montage", "installatie", "reparatie",
    "klus", "dienst", "service", "vervoer", "verhuizen",
    "ophalen", "afvoer"
]

INTERESSANT = [
    "iphone", "ipad", "samsung", "apple", "sony", "canon",
    "nikon", "camera", "lens", "objectief", "playstation",
    "ps4", "ps5", "xbox", "nintendo", "switch", "game",
    "games", "controller", "lego", "pokemon", "hot wheels",
    "nike", "adidas", "air jordan", "dyson", "logitech",
    "jbl", "bose", "garmin", "casio", "gopro", "dji",
    "koptelefoon", "speaker", "gereedschap", "boormachine",
    "verrekijker", "collectie", "verzameling"
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


def interessante_titel(titel):

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


def zoekwoorden(titel):

    woorden = []

    tekst = titel.lower()

    for woord in INTERESSANT:
        if woord in tekst:
            woorden.append(woord)

    if not woorden:
        simpele = re.findall(
            r"[a-zA-Z0-9]+",
            tekst
        )

        woorden = [
            woord for woord in simpele
            if len(woord) >= 4
        ][:4]

    return woorden


async def vergelijkbare_prijzen(page, titel):

    woorden = zoekwoorden(titel)

    if not woorden:
        return []

    zoekterm = " ".join(woorden[:4])

    url = (
        "https://www.marktplaats.nl/q/"
        + quote(zoekterm)
    )

    print(
        f"   🔎 Vergelijken: {zoekterm}"
    )

    try:

        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=45000
        )

        await page.wait_for_timeout(5000)

    except Exception as e:
        print("   ⚠️ Vergelijking mislukt")
        return []

    links = await page.locator(
        'a[href*="/v/"]'
    ).all()

    prijzen = []

    for link in links[:40]:

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

            for prijs in gevonden[:1]:

                waarde = float(
                    prijs.replace(",", ".")
                )

                # Extreem hoge of lage prijzen negeren
                if 1 <= waarde <= 5000:
                    prijzen.append(waarde)

        except:
            pass

    return prijzen[:20]


def bereken_vertrouwen(
    titel,
    aankoopprijs,
    vergelijkbare
):

    if not vergelijkbare:
        return 0

    vertrouwen = 35

    # Meer vergelijkbare advertenties = meer vertrouwen
    if len(vergelijkbare) >= 3:
        vertrouwen += 15

    if len(vergelijkbare) >= 5:
        vertrouwen += 10

    if len(vergelijkbare) >= 8:
        vertrouwen += 5

    # Bekend product / merk
    if interessante_titel(titel):
        vertrouwen += 15

    # Gratis spullen zijn iets onzekerder
    if aankoopprijs == 0:
        vertrouwen -= 5

    return min(95, vertrouwen)


def bereken_score(
    titel,
    aankoopprijs,
    verkoopprijs,
    vertrouwen
):

    score = 20

    if aankoopprijs == 0:
        score += 25

    elif aankoopprijs <= 2:
        score += 20

    else:
        score += 10

    if interessante_titel(titel):
        score += 20

    if verkoopprijs >= max(
        aankoopprijs * 3,
        20
    ):
        score += 15

    elif verkoopprijs >= aankoopprijs * 2:
        score += 10

    if vertrouwen >= 80:
        score += 10

    return min(score, 100)


async def controleer_deal(
    page,
    advertentie
):

    titel = advertentie["titel"]
    prijs = advertentie["prijs"]

    if prijs is None:
        return None

    if prijs > MAX_PRIJS:
        return None

    if uitgesloten(titel):
        return None

    # We willen geen totaal willekeurige spullen
    if not interessante_titel(titel):
        return None

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

    verkoopprijs = median(
        vergelijkbare
    )

    vertrouwen = bereken_vertrouwen(
        titel,
        prijs,
        vergelijkbare
    )

    score = bereken_score(
        titel,
        prijs,
        verkoopprijs,
        vertrouwen
    )

    # Minimaal dubbele waarde
    if prijs == 0:
        dubbele_waarde = (
            verkoopprijs >= MIN_VERKOOPPRIJS
        )
    else:
        dubbele_waarde = (
            verkoopprijs >= prijs * 2
        )

    if not dubbele_waarde:
        print(
            f"   ❌ Geen 2x waarde: {titel}"
        )
        return None

    if verkoopprijs < MIN_VERKOOPPRIJS:
        return None

    if vertrouwen < MIN_VERTROUWEN:
        print(
            f"   ❌ Vertrouwen te laag: "
            f"{vertrouwen}% - {titel}"
        )
        return None

    winst = verkoopprijs - prijs

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

        advertenties = await zoek_advertenties(
            page
        )

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
