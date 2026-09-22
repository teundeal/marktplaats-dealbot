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

# PRIJS

# ============================================================

def euro_naar_float(tekst):
if not tekst:
return None

```
tekst = tekst.strip()
tekst = tekst.replace("€", "")
tekst = tekst.replace("\xa0", " ")

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
```

def vind_europrijzen(tekst):
if not tekst:
return []

```
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
```

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

```
titel = re.sub(r"\s+", " ", tekst).strip()

# Alles na deze Marktplaats-elementen verwijderen
patronen = [
    r"\d[\d.,]*\s*€.*$",
    r"€\s*\d[\d.,]*.*$",
    r"\d[\d.,]*Details.*$",
    r"Details.*$",
    r"Bewaren in Mijn Favorieten.*$",
    r"Bewaren in mijn favorieten.*$",
    r"Ophalen.*$",
    r"Verzenden.*$",
]

for patroon in patronen:
    titel = re.sub(
        patroon,
        "",
        titel,
        flags=re.IGNORECASE
    )

# Bekende Marktplaats-rommel verwijderen
for woord in ROMMEL_IN_TITEL:
    titel = re.sub(
        re.escape(woord),
        "",
        titel,
        flags=re.IGNORECASE
    )

titel = re.sub(r"\s+", " ", titel).strip()

return titel
```

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

```
for woord in DIENSTEN:
    if re.search(
        r"\b" + re.escape(woord) + r"\b",
        tekst
    ):
        return True

return False
```

# ============================================================

# UITGESLOTEN GROTE PRODUCTEN

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

```
return any(
    woord in tekst
    for woord in UITGESLOTEN
)
```

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

```
return any(
    woord in tekst
    for woord in INTERESSANT
)
```

# ============================================================

# PRODUCTCONTROLE

# ============================================================

def geldig_product(tekst):
if not tekst:
return False

```
tekst_lower = tekst.lower()

# Diensten uitsluiten
if is_dienst(tekst_lower):
    return False

# Grote spullen uitsluiten
if uitgesloten(tekst_lower):
    return False

# Advertenties / promoties uitsluiten
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
```

# ============================================================

# ADVERTENTIEKAARTEN

# ============================================================

def advertentiekaarten(page):

```
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

        tekst = re.sub(
            r"\s+",
            " ",
            tekst
        ).strip()

        # Bieden / ruilen / aanvraag niet als vaste prijs behandelen
        tekst_lower = tekst.lower()

        if "bieden" in tekst_lower:
            continue

        if "ruilen" in tekst_lower:
            continue

        if "op aanvraag" in tekst_lower:
            continue

        # Dienst/productcontrole
        if not geldig_product(tekst):
            continue

        prijzen = vind_europrijzen(tekst)

        if not prijzen:
            continue

        prijs = None

        for gevonden_prijs in prijzen:

            # Alleen prijzen die werkelijk binnen
            # onze aankoopgrens liggen.
            if gevonden_prijs <= MAX_PRIJS:
                prijs = gevonden_prijs
                break

        if prijs is None:
            continue

        titel = schone_titel(tekst)

        if not titel:
            continue

        # Titel moet iets nuttigs bevatten
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

# Dubbelen verwijderen
unieke = {}

for kaart in kaarten:
    unieke[kaart["url"]] = kaart

return list(unieke.values())
```

# ============================================================

# VERGELIJKBARE PRIJZEN

# ============================================================

def zoek_verkoopprijzen(page, zoekterm):

```
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
        url
