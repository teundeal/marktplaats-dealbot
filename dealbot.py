import asyncio
import re
import requests
import os
from urllib.parse import urljoin, quote
from statistics import median
from playwright.async_api import async_playwright

DISCORD_WEBHOOK = os.environ["DISCORD_WEBHOOK"]

POSTCODE = "3116"
AFSTAND = "8000"
MAX_PRIJS = 5.00
MIN_VERTROUWEN = 70
MIN_VERKOOPWAARDE = 10.00

# Zoekopdrachten die kleine spullen kunnen opleveren.
ZOEKOPDRACHTEN = [
    "gratis",
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
    "muis"
]

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
    "verhuizen",
    "afvoer",
    "grond",
    "tegels",
    "klinkers",
    "stenen"
]


def prijs_uit_tekst(tekst):

    if "gratis" in tekst.lower():
        return 0.0

    gevonden = re.findall(
        r"€\s*([0-9]+(?:[.,][0-9]{1,2})?)",
        tekst
    )

    if not gevonden:
        return None

    try:
        return float(
            gevonden[0].replace(",", ".")
        )
    except:
        return None


def titel_schoonmaken(titel):

    verwijderen = [
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

    for woord in verwijderen:
        titel = titel.replace(
            woord,
            ""
        )

    return " ".join(
        titel.split()
    ).strip()


def uitgesloten(titel):

    tekst = titel.lower()

    return any(
        woord in tekst
        for woord in UITSLUITEN
    )


def zoek_url(zoekterm):

    basis = (
        "https://www.marktplaats.nl/q/"
        + quote(zoekterm)
        + "/"
    )

    return (
        basis
        + f"?postcode={POSTCODE}"
        + f"&distanceMeters={AFSTAND}"
        + "&priceCentsTo=500"
    )


async def zoek_marktplaats(page, zoekterm):

    url = zoek_url(zoekterm)

    print(
        f"🔎 Zoekopdracht: {zoekterm}"
    )

    try:

        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        await page.wait_for_timeout(4000)

    except Exception as e:

        print(
            f"⚠️ Zoekopdracht mislukt: {zoekterm}"
        )

        return []

    links = await page.locator(
        'a[href*="/v/"]'
    ).all()

    resultaten = []

    for link in links:

        try:

            titel = await link.inner_text()
            href = await link.get_attribute(
                "href"
            )

            if not titel or not href:
                continue

            href = urljoin(
                "https://www.marktplaats.nl",
                href
            )

            titel = titel_schoonmaken(
                titel
            )

            if len(titel) < 3:
                continue

            prijs = prijs_uit_tekst(
                titel
            )

            if prijs is None:
                continue

            if prijs > MAX_PRIJS:
                continue

            if uitgesloten(titel):
                continue

            resultaten.append({
                "titel": titel,
                "prijs": prijs,
                "link": href
            })

        except:
            pass

    return resultaten


async def verzamel_advertenties(page):

    alle_advertenties = {}
    
    for zoekterm in ZOEKOPDRACHTEN:

        resultaten = await zoek_marktplaats(
            page,
            zoekterm
        )

        for advertentie in resultaten:

            link = advertentie["link"]

            if link not in alle_advertenties:

                alle_advertenties[
                    link
                ] = advertentie

    return list(
        alle_advertenties.values()
    )


def zoekwoorden(titel):

    woorden = re.findall(
        r"[a-zA-Z0-9]+",
        titel.lower()
    )

    stopwoorden = {
        "gratis",
        "nieuw",
        "gebruikte",
        "gebruikt",
        "mooie",
        "zeer",
        "goede",
        "goed",
        "voor",
        "te",
        "koop",
        "af",
        "halen"
    }

    woorden = [
        woord
        for woord in woorden
        if len(woord) >= 3
        and woord not in stopwoorden
    ]

    return woorden[:4]


async def vergelijkbare_prijzen(
    page,
    titel
):

    woorden = zoekwoorden(
        titel
    )

    if not woorden:
        return []

    zoekterm = " ".join(
        woorden
    )

    url = zoek_url(
        zoekterm
    )

    print(
        f"   📊 Vergelijken: {zoekterm}"
    )

    try:

        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=45000
        )

        await page.wait_for_timeout(4000)

    except:

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

            if uitgesloten(tekst):
                continue

            gevonden = re.findall(
                r"€\s*([0-9]+(?:[.,][0-9]{1,2})?)",
                tekst
            )

            if not gevonden:
                continue

            waarde = float(
                gevonden[0].replace(
                    ",",
                    "."
                )
            )

            if 1 <= waarde <= 5000:

                prijzen.append(
                    waarde
                )

        except:
            pass

    return prijzen


def bereken_vertrouwen(
    titel,
    aantal
):

    if aantal < 3:
        return 0

    vertrouwen = 50

    if aantal >= 5:
        vertrouwen += 10

    if aantal >= 8:
        vertrouwen += 10

    if aantal >= 12:
        vertrouwen += 5

    return min(
        vertrouwen,
        95
    )


def stuur_discord(deal):

    bericht = {
        "content": (
            "🚨 **MOGELIJKE MARKTPLAATS DEAL** 🚨\n\n"
            f"**{deal['titel']}**\n\n"
            f"💰 Aankoop: **€{deal['prijs']:.2f}**\n"
            f"💵 Geschatte verkoop: **€{deal['verkoopprijs']:.2f}**\n"
            f"📈 Mogelijke winst: **€{deal['winst']:.2f}**\n"
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

        print(
            "✅ Discord melding verstuurd"
        )

    else:

        print(
            "❌ Discord fout:",
            response.status_code
        )


async def controleer_deal(
    page,
    advertentie
):

    titel = advertentie["titel"]
    prijs = advertentie["prijs"]

    vergelijkbare = await vergelijkbare_prijzen(
        page,
        titel
    )

    if len(vergelijkbare) < 3:

        print(
            f"   ❌ Te weinig prijsdata: {titel}"
        )

        return None

    verkoopprijs = median(
        vergelijkbare
    )

    vertrouwen = bereken_vertrouwen(
        titel,
        len(vergelijkbare)
    )

    if prijs == 0:

        geldig = (
            verkoopprijs >= MIN_VERKOOPWAARDE
        )

    else:

        geldig = (
            verkoopprijs >= prijs * 2
        )

    if not geldig:

        print(
            f"   ❌ Geen 2x waarde: {titel}"
        )

        return None

    if vertrouwen < MIN_VERTROUWEN:

        print(
            f"   ❌ Vertrouwen {vertrouwen}%: "
            f"{titel}"
        )

        return None

    winst = (
        verkoopprijs - prijs
    )

    return {
        "titel": titel,
        "prijs": prijs,
        "verkoopprijs": verkoopprijs,
        "winst": winst,
        "vertrouwen": vertrouwen,
        "vergelijkbare": len(
            vergelijkbare
        ),
        "link": advertentie["link"]
    }


async def main():

    print()
    print(
        "======================================"
    )
    print(
        "       MARKTPLAATS DEALBOT"
    )
    print(
        "======================================"
    )
    print(
        "📍 Zoekgebied: 8 km rond 3116"
    )
    print(
        "💰 Maximum aankoop: €5"
    )
    print(
        "📈 Minimaal: 2x verwachte waarde"
    )
    print(
        "🎯 Minimaal vertrouwen: 70%"
    )
    print()

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page()

        advertenties = await verzamel_advertenties(
            page
        )

        print()
        print(
            f"📦 {len(advertenties)} unieke "
            f"advertenties gevonden."
        )

        deals = []

        for advertentie in advertenties:

            deal = await controleer_deal(
                page,
                advertentie
            )

            if deal:

                deals.append(
                    deal
                )

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
                "🎯 Vertrouwen:",
                f"{deal['vertrouwen']}%"
            )

            stuur_discord(
                deal
            )

        await browser.close()

        print()
        print(
            "✅ Zoekronde klaar."
        )


if __name__ == "__main__":

    asyncio.run(main())
