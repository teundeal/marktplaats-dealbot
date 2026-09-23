import os
import re
import statistics
import requests
from urllib.parse import quote, urlparse
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# =========================
# INSTELLINGEN
# =========================

POSTCODE = "3116"
MAX_AFSTAND_KM = 10
MAX_PRIJS = 10.00

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

# Maximaal aantal advertentiepagina's dat per zoekterm echt wordt geopend.
# Dit voorkomt dat GitHub Actions extreem lang bezig is.
MAX_DETAIL_PER_ZOEKTERM = 12

# Maximaal aantal deals dat één run kan versturen
MAX_DEALS_PER_RUN = 10


# =========================
# HULPFUNCTIES
# =========================

def is_echte_marktplaats_link(href):
    """Controleert of een link echt naar een Marktplaats-advertentie gaat."""

    if not href:
        return False

    try:
        parsed = urlparse(href)
        host = parsed.netloc.lower()

        if host not in ("marktplaats.nl", "www.marktplaats.nl"):
            return False

        if "/v/" not in parsed.path:
            return False

        return True

    except Exception:
        return False


def volledige_url(href):
    if href.startswith("http://") or href.startswith("https://"):
        return href

    if href.startswith("/"):
        return "https://www.marktplaats.nl" + href

    return "https://www.marktplaats.nl/" + href


def parse_euro(tekst):
    """
    Zet Nederlandse bedragen om naar floats.

    Voorbeelden:
    €1.500      -> 1500
    €1.250,00   -> 1250
    €4,50       -> 4.50
    €95         -> 95
    """

    if not tekst:
        return None

    tekst = tekst.replace("\xa0", " ")

    patronen = [
        r"€\s*([0-9]{1,3}(?:\.[0-9]{3})+(?:,[0-9]{1,2})?)",
        r"€\s*([0-9]+(?:,[0-9]{1,2})?)",
    ]

    for patroon in patronen:
        match = re.search(patroon, tekst)

        if match:
            waarde = match.group(1)

            if "." in waarde and "," in waarde:
                waarde = waarde.replace(".", "").replace(",", ".")

            elif "." in waarde:
                delen = waarde.split(".")

                if len(delen[-1]) == 3:
                    waarde = waarde.replace(".", "")

            elif "," in waarde:
                waarde = waarde.replace(",", ".")

            try:
                return float(waarde)
            except ValueError:
                pass

    return None


def vind_alle_prijzen(tekst):
    """Vindt alle eurobedragen in tekst."""

    if not tekst:
        return []

    tekst = tekst.replace("\xa0", " ")

    matches = re.findall(
        r"€\s*[0-9]{1,3}(?:\.[0-9]{3})*(?:,[0-9]{1,2})?",
        tekst
    )

    resultaten = []

    for match in matches:
        prijs = parse_euro(match)

        if prijs is not None:
            resultaten.append(prijs)

    return resultaten


def vind_afstand(tekst):
    """
    Probeert de afstand van de advertentie te vinden.

    Voorbeelden:
    2 km
    7,5 km
    Afstand 3 km
    """

    if not tekst:
        return None

    patronen = [
        r"(?:afstand|distance)[^\d]{0,30}(\d+(?:[.,]\d+)?)\s*km",
        r"(\d+(?:[.,]\d+)?)\s*km\s*(?:afstand|distance)?",
    ]

    for patroon in patronen:
        matches = re.findall(patroon, tekst, flags=re.IGNORECASE)

        if matches:
            try:
                return float(matches[0].replace(",", "."))
            except ValueError:
                pass

    return None


def titel_schoonmaken(titel):
    if not titel:
        return "Onbekende advertentie"

    titel = re.sub(r"\s+", " ", titel)
    return titel.strip()


# =========================
# FILTERS
# =========================

VERBODEN_DIENSTEN = [
    "reparatie",
    "repareren",
    "installatie",
    "installeren",
    "montage",
    "onderhoud",
    "service",
    "diensten",
    "klus",
    "klussen",
    "bedrijf",
    "aannemer",
    "verhuur",
    "te huur",
    "fotograaf",
    "fotografie",
    "schilder",
    "schilderen",
    "transport",
    "koerier",
    "schoonmaak",
    "schoonmaken",
    "training",
    "cursus",
    "les",
    "coaching",
    "bemiddeling",
    "taxi",
    "auto detailing",
    "detailing",
    "website maken",
    "webdesign",
]


VERBODEN_GROOT = [
    "bank",
    "hoekbank",
    "sofa",
    "eettafel",
    "tafel",
    "bureau",
    "kast",
    "bed",
    "matras",
    "ledikant",
    "stoel",
    "fauteuil",
    "bureaustoel",
    "dressoir",
    "boekenkast",
    "tv meubel",
    "televisiemeubel",
    "wasmachine",
    "droger",
    "vaatwasser",
    "koelkast",
    "vriezer",
    "diepvries",
    "oven",
    "fornuis",
    "caravan",
    "aanhanger",
    "scooter",
    "brommer",
    "motor",
    "auto",
    "fiets",
    "bakfiets",
    "e-bike",
    "elektrische fiets",
    "tweewieler",
    "trampoline",
    "zwembad",
    "schutting",
    "tuinhuis",
]


VERBODEN_PROMOTIE = [
    "catawiki",
    "auction",
    "veiling",
    "veilinghuis",
    "bied mee",
    "biedingen",
    "webshop",
    "bestel online",
    "online bestellen",
    "actie",
    "nieuw in doos",
    "winkel",
    "groothandel",
]


INTERESSANTE_PRODUCTEN = [
    "iphone",
    "ipad",
    "samsung",
    "xiaomi",
    "google pixel",
    "sony",
    "canon",
    "nikon",
    "fujifilm",
    "panasonic",
    "lumix",
    "gopro",
    "camera",
    "lens",
    "objectief",
    "playstation",
    "ps4",
    "ps5",
    "xbox",
    "nintendo",
    "switch",
    "gameboy",
    "pokemon",
    "lego",
    "duplo",
    "hot wheels",
    "modelauto",
    "burago",
    "maisto",
    "majorette",
    "casio",
    "g shock",
    "seiko",
    "citizen",
    "horloge",
    "airpods",
    "koptelefoon",
    "speaker",
    "bluetooth",
    "jbl",
    "logitech",
    "keyboard",
    "toetsenbord",
    "muis",
    "ssd",
    "hdd",
    "ram",
    "geheugen",
    "arduino",
    "raspberry",
    "electronics",
    "gereedschap",
    "bosch",
    "makita",
    "dewalt",
]


def is_service(titel):
    tekst = titel.lower()

    return any(term in tekst for term in VERBODEN_DIENSTEN)


def is_groot_spul(titel):
    tekst = titel.lower()

    return any(term in tekst for term in VERBODEN_GROOT)


def is_promotie(titel):
    tekst = titel.lower()

    return any(term in tekst for term in VERBODEN_PROMOTIE)


def is_interessant_product(titel):
    tekst = titel.lower()

    return any(term in tekst for term in INTERESSANTE_PRODUCTEN)


# =========================
# TITEL VAN ADVERTENTIE
# =========================

def vind_titel(page, fallback="Onbekende advertentie"):

    # Eerst H1 proberen
    try:
        h1 = page.locator("h1").first

        if h1.count() > 0:
            tekst = h1.inner_text(timeout=3000).strip()

            if tekst:
                return titel_schoonmaken(tekst)

    except Exception:
        pass

    # Daarna OpenGraph titel
    try:
        og = page.locator('meta[property="og:title"]').first

        if og.count() > 0:
            content = og.get_attribute("content")

            if content:
                return titel_schoonmaken(content)

    except Exception:
        pass

    return titel_schoonmaken(fallback)


# =========================
# PRIJS VAN ADVERTENTIE
# =========================

def vind_prijs_op_advertentie(page, body_text):
    """
    Probeert eerst prijs-elementen te vinden.
    Daarna wordt de tekst van de advertentie gebruikt.

    Bieden wordt bewust genegeerd.
    """

    # Als het een biedadvertentie is, geen vaste aankoopprijs.
    bied_woorden = [
        "bieden",
        "doe een bod",
        "vanafprijs",
        "veiling",
    ]

    eerste_stuk = body_text[:5000].lower()

    if any(woord in eerste_stuk for woord in bied_woorden):
        return None

    # Mogelijke prijs-elementen
    selectors = [
        '[data-testid*="price"]',
        '[class*="price"]',
        '[class*="Price"]',
    ]

    for selector in selectors:

        try:
            elementen = page.locator(selector)

            aantal = min(elementen.count(), 10)

            for i in range(aantal):

                try:
                    tekst = elementen.nth(i).inner_text(timeout=1500)

                    prijs = parse_euro(tekst)

                    if prijs is not None and prijs >= 0:
                        return prijs

                except Exception:
                    continue

        except Exception:
            continue

    # Fallback: zoek bedragen in de body.
    prijzen = vind_alle_prijzen(body_text)

    # Kleine bedragen zijn niet automatisch de prijs.
    # We kiezen het eerste bedrag dat niet duidelijk bij verzending hoort.
    regels = body_text.splitlines()

    for regel in regels:

        regel_lower = regel.lower()

        if "verzend" in regel_lower:
            continue

        if "servicekosten" in regel_lower:
            continue

        if "kosten koper" in regel_lower:
            continue

        prijs = parse_euro(regel)

        if prijs is not None:
            return prijs

    if prijzen:
        return prijzen[0]

    return None


# =========================
# ADVERTENTIE OPENEN
# =========================

def controleer_advertentie(page, url, kaart_titel=""):
    """
    Opent de individuele Marktplaats-advertentie
    en controleert prijs + afstand + filters.
    """

    print()
    print("🔍 Advertentie controleren:")
    print(url)

    try:
        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=30000
        )

    except PlaywrightTimeoutError:
        print("   ⚠️ Pagina laadt te langzaam")
        return None

    except Exception as e:
        print(f"   ⚠️ Fout bij openen: {e}")
        return None

    try:
        page.wait_for_timeout(1200)
    except Exception:
        pass

    try:
        body_text = page.locator("body").inner_text(timeout=10000)
    except Exception:
        print("   ⚠️ Tekst kon niet worden gelezen")
        return None

    body_lower = body_text.lower()

    # Externe/promo pagina's uitsluiten
    if "catawiki" in body_lower:
        print("   ⛔ Catawiki/promotie uitgesloten")
        return None

    titel = vind_titel(page, kaart_titel)

    print(f"   🏷️ Titel: {titel}")

    # Filters op titel
    if is_service(titel):
        print("   ⛔ Dienst/service")
        return None

    if is_groot_spul(titel):
        print("   ⛔ Groot/zwaar product")
        return None

    if is_promotie(titel):
        print("   ⛔ Promotie/veiling")
        return None

    if not is_interessant_product(titel):
        print("   ⏭️ Niet in interessante productcategorie")
        return None

    # PRIJS
    prijs = vind_prijs_op_advertentie(page, body_text)

    if prijs is None:
        print("   ⚠️ Geen vaste prijs gevonden")
        return None

    print(f"   💰 Prijs gevonden: €{prijs:.2f}")

    if prijs > MAX_PRIJS:
        print(f"   ⛔ Te duur (> €{MAX_PRIJS:.2f})")
        return None

    # AFSTAND
    afstand = vind_afstand(body_text)

    if afstand is None:
        print("   ⚠️ Afstand niet gevonden → advertentie overgeslagen")
        return None

    print(f"   📍 Afstand gevonden: {afstand:.1f} km")

    if afstand > MAX_AFSTAND_KM:
        print(f"   ⛔ Te ver weg (> {MAX_AFSTAND_KM} km)")
        return None

    print("   ✅ Voldoet aan prijs + afstand + productfilters")

    return {
        "titel": titel,
        "prijs": prijs,
        "afstand": afstand,
        "url": url,
    }


# =========================
# ZOEKRESULTATEN
# =========================

def vind_advertentielinks(page, zoekterm):

    zoek_url = (
        "https://www.marktplaats.nl/q/"
        + quote(zoekterm)
        + "/?postcode="
        + POSTCODE
        + "&distanceMeters=10000"
        + "&priceCentsTo=10000"
    )

    print()
    print(f"🔎 Zoeken naar: {zoekterm}")
    print(f"   🔗 {zoek_url}")

    try:
        page.goto(
            zoek_url,
            wait_until="domcontentloaded",
            timeout=30000
        )

    except PlaywrightTimeoutError:
        print("   ⚠️ Zoekpagina laadt te langzaam")
        return []

    except Exception as e:
        print(f"   ⚠️ Zoekfout: {e}")
        return []

    try:
        page.wait_for_timeout(2000)
    except Exception:
        pass

    links = {}

    # Eerst alle links ophalen
    try:
        alle_links = page.locator("a")

        aantal = alle_links.count()

        print(f"   🔗 {aantal} links op de pagina gevonden")

        for i in range(aantal):

            try:
                element = alle_links.nth(i)

                href = element.get_attribute("href")

                if not href:
                    continue

                # Absolute URL
                url = volledige_url(href)

                # Alleen Marktplaats
                if not is_echte_marktplaats_link(url):
                    continue

                # URL opschonen
                url = url.split("?")[0]

                if url in links:
                    continue

                try:
                    kaart_titel = element.inner_text(timeout=1000).strip()
                except Exception:
                    kaart_titel = ""

                links[url] = kaart_titel

            except Exception:
                continue

    except Exception as e:
        print(f"   ⚠️ Links uitlezen mislukt: {e}")

    print(f"   📦 {len(links)} echte Marktplaats-links gevonden")

    # Debuggen als Marktplaats weer iets anders gebruikt
    if len(links) == 0:

        print("   ⚠️ Geen advertentielinks gevonden.")

        try:
            html = page.content()

            # Kijk of /v/ überhaupt in de HTML staat
            aantal_v = html.count("/v/")

            print(
                f"   🔎 '/v/' komt {aantal_v} keer voor in de HTML"
            )

            # Kijk ook of marktplaats advertentie-url's voorkomen
            if "marktplaats.nl/v/" in html:
                print(
                    "   ℹ️ /v/ staat wel in HTML, "
                    "maar werd niet als normale link gevonden."
                )

        except Exception:
            pass

    return list(links.items())

# =========================
# VERKOOPWAARDE SCHATTEN
# =========================

def zoek_verkoopprijzen(page, titel):

    zoek_url = (
        "https://www.marktplaats.nl/q/"
        + quote(titel)
        + "/"
    )

    try:
        page.goto(
            zoek_url,
            wait_until="domcontentloaded",
            timeout=20000
        )

        page.wait_for_timeout(700)

    except Exception:
        return []

    prijzen = []

    try:
        body = page.locator("body").inner_text(timeout=5000)

        for regel in body.splitlines():

            regel_lower = regel.lower()

            if "verzend" in regel_lower:
                continue

            if "servicekosten" in regel_lower:
                continue

            prijs = parse_euro(regel)

            if prijs is None:
                continue

            # Extreme prijzen negeren
            if 0.50 <= prijs <= 10000:
                prijzen.append(prijs)

    except Exception:
        pass

    return prijzen


def schat_verkoopprijs(page, aankoopprijs, titel):

    prijzen = zoek_verkoopprijzen(page, titel)

    if not prijzen:
        return None

    # Extreme uitschieters eruit
    redelijke = [
        prijs
        for prijs in prijzen
        if aankoopprijs * 1.5 <= prijs <= 5000
    ]

    if not redelijke:
        redelijke = prijzen

    if not redelijke:
        return None

    # Neem mediaan zodat één extreem bedrag minder invloed heeft
    verkoopprijs = statistics.median(redelijke)

    return round(verkoopprijs, 2)


# =========================
# DEAL SCORE
# =========================

def bereken_score(aankoopprijs, verkoopprijs):

    if verkoopprijs is None:
        return 0

    winst = verkoopprijs - aankoopprijs

    if winst <= 0:
        return 0

    percentage = winst / max(aankoopprijs, 0.01)

    if winst >= 100 and percentage >= 5:
        return 10

    if winst >= 50 and percentage >= 4:
        return 9

    if winst >= 25 and percentage >= 3:
        return 8

    if winst >= 15 and percentage >= 2:
        return 7

    if winst >= 10:
        return 6

    if winst >= 5:
        return 5

    return 3


# =========================
# DISCORD
# =========================

def stuur_discord(deal):

    aankoop = deal["prijs"]
    verkoop = deal["verkoopprijs"]
    winst = verkoop - aankoop
    score = deal["score"]

    bericht = (
        "🚨 **MOGELIJKE MARKTPLAATS DEAL**\n\n"
        f"**{deal['titel']}**\n\n"
        f"💰 Koopprijs: **€{aankoop:.2f}**\n"
        f"📈 Geschatte verkoopprijs: **€{verkoop:.2f}**\n"
        f"💵 Mogelijke winst: **€{winst:.2f}**\n"
        f"⭐ Deal score: **{score}/10**\n"
        f"📍 Afstand: **{deal['afstand']:.1f} km**\n\n"
        f"🔗 {deal['url']}"
    )

    try:

        response = requests.post(
            DISCORD_WEBHOOK,
            json={
                "content": bericht
            },
            timeout=15
        )

        if response.status_code in (200, 204):
            print("   📲 Discord-melding verstuurd")
        else:
            print(
                f"   ⚠️ Discord fout: "
                f"{response.status_code}"
            )

    except Exception as e:
        print(f"   ⚠️ Discord fout: {e}")


# =========================
# HOOFDPROGRAMMA
# =========================

def main():

    print("======================================")
    print("   MARKTPLAATS DEALBOT")
    print("======================================")
    print(f"📍 Postcode: {POSTCODE}")
    print(f"📏 Max afstand: {MAX_AFSTAND_KM} km")
    print(f"💰 Max aankoopprijs: €{MAX_PRIJS:.2f}")
    print("======================================")

    deals = []
    geziene_urls = set()

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        search_page = browser.new_page()

        detail_page = browser.new_page()

        for zoekterm in ZOEKTERMEN:

            links = vind_advertentielinks(
                search_page,
                zoekterm
            )

            gecontroleerd = 0

            for url, kaart_titel in links:

                if gecontroleerd >= MAX_DETAIL_PER_ZOEKTERM:
                    break

                if url in geziene_urls:
                    continue

                geziene_urls.add(url)

                gecontroleerd += 1

                advertentie = controleer_advertentie(
                    detail_page,
                    url,
                    kaart_titel
                )

                if not advertentie:
                    continue

                # Verkoopprijs schatten
                print("   🔎 Verkoopprijs zoeken...")

                verkoopprijs = schat_verkoopprijs(
                    search_page,
                    advertentie["prijs"],
                    advertentie["titel"]
                )

                if verkoopprijs is None:
                    print("   ⚠️ Geen betrouwbare verkoopprijs gevonden")
                    continue

                advertentie["verkoopprijs"] = verkoopprijs

                winst = verkoopprijs - advertentie["prijs"]

                advertentie["score"] = bereken_score(
                    advertentie["prijs"],
                    verkoopprijs
                )

                print(
                    f"   📈 Geschatte verkoopprijs: "
                    f"€{verkoopprijs:.2f}"
                )

                print(
                    f"   💵 Mogelijke winst: "
                    f"€{winst:.2f}"
                )

                print(
                    f"   ⭐ Score: "
                    f"{advertentie['score']}/10"
                )

                # Alleen echte winstdeals
                if winst <= 0:
                    print("   ⛔ Geen winst")
                    continue

                deals.append(advertentie)

                # Beste deals eerst
                deals.sort(
                    key=lambda x: (
                        x["score"],
                        x["verkoopprijs"] - x["prijs"]
                    ),
                    reverse=True
                )

                if len(deals) > MAX_DEALS_PER_RUN:
                    deals = deals[:MAX_DEALS_PER_RUN]

            print(
                f"   📊 Klaar met zoekterm: {zoekterm}"
            )

        browser.close()

    print()
    print("======================================")
    print("RESULTAAT")
    print("======================================")

    if not deals:
        print("❌ Geen geschikte deals gevonden.")
        return

    for deal in deals:

        print(
            f"🔥 {deal['titel']} | "
            f"€{deal['prijs']:.2f} → "
            f"€{deal['verkoopprijs']:.2f} | "
            f"winst €{deal['verkoopprijs'] - deal['prijs']:.2f} | "
            f"{deal['afstand']:.1f} km | "
            f"score {deal['score']}/10"
        )

        stuur_discord(deal)


if __name__ == "__main__":
    main()
