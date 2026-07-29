"""
Profil pro e-chalupy.cz.

Poznámky k portálu:
- Výpis nabídek na e-chalupy.cz je server-rendered HTML se stránkováním
  přes ?p=N — žádné /vyhledavani/properties s offset/limit (to jsme si
  ověřili, vrací 404). Skutečné JSON API existuje, ale na jiné doméně:
  https://api-pub.e-chalupy.cz/properties (destinations, persons,
  bedrooms, limit, offset). Nikde v JS bundlech stránky se nevolá -
  objeveno ruční sondou, ne z network logu - ale je veřejné, nevyžaduje
  auth ani speciální hlavičky a vrací mnohem čistší data než HTML.
- Odpověď: {"items": [...], "total": {"value": N, "relation": "eq"|"gte"},
  "mapBounds": {...}, "aggs": {...}}. Konec stránkování pozná se podle
  items == [] (HTTP zůstává 200). "relation" je "eq" jakmile jsou
  aplikované filtry (destinations/persons/bedrooms), "gte" jen u
  neomezeného celostátního dotazu (ES limit na přesné počítání ~10000).
- Lokalita se do API zadává jako interní kód (destinations=area_19640),
  ne jako text. Žádné veřejné API na "text -> area kód" jsme nenašli
  (autocomplete v searchBox.js má data staticky předgenerovaná).
  Proto z lokality děláme "slug" a natáhneme lehkou HTML stránku
  https://e-chalupy.cz/<slug> - v ní je vždy inline
  window.dataSearchBoxSelectedData s destinations[0].id. Když stránka
  neexistuje (404) nebo parsing selže, hledáme bez destinations (JSON
  API na rozdíl od staré HTML cesty i tak vrátí neprázdné výsledky).
- Jedna položka v "items": title, slug, id (-> detail URL
  https://www.e-chalupy.cz/<slug>-o<id>, ověřeno), tagsFeatured
  (kapacita + počet ložnic jako text, např. "chalupa 5 osob",
  "2 ložnice" - u objektů s víc jednotkami místo toho "2 apartmány +
  3 pokoje" apod., bez jednoznačné kapacity/ložnic - stejné omezení
  mělo i staré HTML parsování), tags (vybavení, už čistě oddělené od
  kapacity/ložnic - žádný regex na rozlišení není potřeba), area (obec)
  + area2 (region - odpovídá zadané lokalitě), price ("od 2 500 Kč"),
  priceLabel, images[].src (-> https://e-chalupy.cz/foto/<src>,
  ověřeno), gps, rating, reviews.
- Regex na kapacitu/ložnice ověřen na ~2500 reálných nabídkách (Krušné
  hory, Šumava, Krkonoše): žádná kolize (žádný tag nematchne obě
  regexy současně, např. "3 apartmány" nematchne ani jednu - správně,
  není to ani kapacita ani ložnice).
- "Pronajímá se celé" (entire_property): žádné bool pole přímo v
  odpovědi není (přestože filtr "entireProperty" existuje ve
  vyhledávacím formuláři portálu), ale item["units"] to spolehlivě
  strukturálně kóduje - ověřeno na stejném vzorku ~2500 nabídek:
    - units.items je list (víc samostatných jednotek) -> False
    - units.header text obsahuje "pronajímá celý"          -> True
    - units.header text obsahuje "samostatná část"         -> False
      (pronajímá se jen část objektu, může být přítomen majitel)
    - jinak (typicky prázdný header, žádné items)           -> None
  Žádná kolize mezi těmito třemi vzory na testovaném vzorku.
- Celostátní dotaz (bez destinations) jsme zkoušeli - API se natvrdo
  zastaví přesně na offset=10000 (items začne vracet [], total.value
  zůstává navždy zaseklé na {"value": 10000, "relation": "gte"}).
  Je to defaultní ES/OpenSearch max_result_window strop, ne líný
  odhad - žádným stránkováním se přes něj nedostaneme. Proto
  destinations (lokalita) zůstává povinná/doporučená - jednotlivé
  regiony mají řádově stovky až nízké tisíce nabídek (největší
  pozorovaný: Jižní Čechy 2224), hluboko pod stropem.
- persons/bedrooms se do API dotazu NEPOSÍLAJÍ - stahujeme kompletní
  (byť lokalitou omezená) data a filtrování podle kapacity/ložnic/
  ceny necháváme čistě na filters.py a frontendu. Jeden fetch regionu
  tak pokryje libovolnou kombinaci těchto kritérií bez nutnosti
  nového dotazu na API.
- Vybavení z volného textu (tags) je pro některá klíčová slova
  nespolehlivé - ověřeno na Šumavě (1200 nabídek) proti webovému
  filtru portálu (dataSearchBoxfiltersCounter + funkční query param
  filters=<id>, který vrací přesně stejná čísla jako ten čítač):
    - "se psem" a "společenská místnost" jsou v tags VŽDY 0x, přestože
      přes polovinu nabídek je reálně má (655, resp. 594 podle
      filters=72/10) - tahle dvě jsou textem nezjistitelná úplně.
    - "bazén" text pokrývá jen 75 % (156 vs. 207 přes filters=65).
    - "krb" text naopak textem OVERcountuje (622 vs. 494 jen za
      filters=7 vnitřní), protože slučuje vnitřní i venkovní krb do
      jednoho tagu - proto se sjednocuje s OBĚMA ID (7 vnitřní + 30
      venkovní), ať se nic neztratí.
    - vířivka (37), sauna (11), na samotě (40) sedí textem přesně
      (100 %), u lesa (42) skoro přesně (93 %).
  Filter ID nejsou pole na položce v odpovědi (žádné "amenityIds" v
  items[] není) - jde jen o query parametr (filters=<id>), který
  vrátí množinu ID nabídek. Pro každé z těchto vybavení proto
  stahujeme ID-množinu zvlášť (stránkovaně) a sjednocujeme ji
  s textovými tagy při stavbě amenities.
  "Parkování" nemá na portálu žádné odpovídající filtr ID vůbec -
  zůstává čistě textové. "entire_property" (filters=84, "Pouze celé
  objekty") jsme cíleně NEpoužili navzdory dostupnosti - namátková
  kontrola ukázala nabídku s units.header "Pronajímá se samostatná
  část" (jasně NE celý objekt), kterou filters=84 přesto zahrnuje,
  takže sémantika toho filtru na webu neodpovídá tomu, co název
  napovídá - units pole zůstává spolehlivější zdroj pravdy.
- Dalších 8 vybavení (myčka nádobí, lednička, klimatizace, televize,
  wifi, pískoviště, ohniště, gril) je stejně jako "se psem" čistě
  ID-only - 0% textové pokrytí na celém Šumava vzorku (1200 nabídek).
  Taky obohacujeme přes filters=<id>.
- ID-obohacovací fetch (_fetch_filter_id_set) používá vlastní vyšší
  limit (ENRICH_LIMIT=1000, ne PAGE_SIZE=200 jako hlavní dotaz) -
  změřeno na Jižní Čechy (16 vybavení, největší pozorovaný region):
  s limit=200 by to bylo ~100 dodatečných requestů (~70s), s limit=1000
  jen 44 requestů (~33s). Hlavní dotaz na listingy zůstává na
  PAGE_SIZE=200 beze změny (tam limit=1000 nebyl testován/potřeba).
- likely_apartment: portálová kategorie "type" (id item['type']['id'])
  není spolehlivý indikátor - i uvnitř filters=4 ("Chaty a chalupy")
  jsme našli položky s item['type']['title']=="Apartmán". Signál proto
  skládáme ze tří nezávislých textových zdrojů (title, tagsFeatured/
  units.items podtituly, priceLabel) - ověřeno na Šumavě: 598/1200
  (50 %) matchne aspoň jednu podmínku, není to okrajový jev.
  Pozn.: "osob(a/u)" v priceLabel samo o sobě nemusí nutně znamenat
  rozparcelovaný objekt - i legitimní celé chalupy občas cenují za
  osobu místo za objekt - je to nejslabší ze tří signálů.
"""

import json
import re
import sys
import unicodedata

import requests

from scraper.models import Listing

SOURCE_NAME = "e-chalupy.cz"
BASE_URL = "https://e-chalupy.cz"
API_URL = "https://api-pub.e-chalupy.cz/properties"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

CAPACITY_RE = re.compile(r"(\d+)\s*osob")
BEDROOMS_RE = re.compile(r"(\d+)\s*lo[žz]nic")
PRICE_RE = re.compile(r"([\d\s]+)\s*K[čc]")

PAGE_SIZE = 200
ENRICH_LIMIT = 1000
MAX_LISTINGS = 5000

DESTINATION_RE = re.compile(r"window\.dataSearchBoxSelectedData\s*=\s*(\{.*?\});")

# Předresolvované slug -> area_XXXXX pro portálem nabízených 11 "oblíbených
# destinací" (hlavní navigace na e-chalupy.cz homepage, submenu2/items).
# DŮVOD: `e-chalupy.cz/<slug>` (HTML stránka použitá v _resolve_area_id())
# dostává z GitHub Actions runnerů 403 Forbidden - stejná blokace jako
# u hlavního API popsaná v shrnutí sekce 4, ale zjištěno, že se týká JEN
# tohohle HTML resolvování, ne `api-pub.e-chalupy.cz` (ten 403 nedává,
# funguje z Actions bez problému). Bez fungujícího area kódu search()
# tiše spadne na celostátní dotaz (MAX_LISTINGS strop, viz search()) a
# location matching pak zbytečně zahodí většinu výsledků (ověřeno na
# Actions run 30470703299 - 5138 nalezeno / jen 434 po filtru misto
# ~1000+ při správně scopovaném dotazu).
# Tahle tabulka se používá PŘEDNOSTNĚ (viz _resolve_area_id) - obchází
# blokovaný endpoint úplně pro těchto 11 regionů, jak lokálně, tak na
# Actions. Pro cokoliv mimo tenhle seznam zůstává živé HTML resolvování
# jako fallback (funguje lokálně, na Actions degraduje na celostátní
# hledání + diagnostický log - viz _resolve_area_id).
# Resolvováno ručně z domácí sítě 29. 7. 2026 - pokud se area kódy na
# portálu časem změní, tahle tabulka zestárne tiše (fallback na živé
# resolvování se ale pořád uplatní, jen o resolvovaný region přijde
# přednost). Revalidovat, pokud počty pro tyhle regiony začnou vypadat
# podezřele nízké/nulové.
STATIC_AREA_IDS: dict[str, str] = {
    "sumava": "area_19647",
    "jeseniky": "area_19651",
    "beskydy": "area_19652",
    "krkonose": "area_19643",
    "jizni-morava": "area_19653",
    "cesky-raj": "area_19644",
    "jizerske-hory": "area_19642",
    "jizni-cechy": "area_19646",
    "krusne-hory": "area_19640",
    "vysocina": "area_19649",
    "orlicke-hory": "area_19650",
}

# Kanonický název vybavení -> ID filtru/filtrů na portálu (viz docstring
# modulu). "krb" má dvě ID (vnitřní + venkovní), protože náš text-tag je
# slučuje do jednoho tagu a nechceme o tuhle informaci přijít.
AMENITY_FILTER_IDS: dict[str, tuple[int, ...]] = {
    "bazén": (65,),
    "vířivka": (37,),
    "sauna": (11,),
    "krb": (7, 30),
    "na samotě": (40,),
    "u lesa": (42,),
    "se psem": (72,),
    "společenská místnost": (10,),
    "myčka nádobí": (19,),
    "lednička": (21,),
    "klimatizace": (18,),
    "televize": (9,),
    "wifi": (8,),
    "pískoviště": (67,),
    "ohniště": (31,),
    "gril": (29,),
}


def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _resolve_area_id(location: str) -> str | None:
    """Text -> area_XXXXX. Nejdřív STATIC_AREA_IDS (obchází endpoint
    blokovaný na GitHub Actions, viz komentář u té konstanty), teprve
    pak best-effort živé HTML resolvování.

    Diagnostický print na stderr při selhání živého resolvování -
    žádný krok tu není povinný (search() má fallback na celostátní
    dotaz bez destinations), takže selhání samo o sobě nezpůsobí
    [ERROR] v main.py a bez logu by bylo neviditelné. Viz shrnutí
    sekce 4 - historicky 403 z GitHub Actions, potvrzeno, že se to
    pořád děje (jen na tomhle konkrétním HTML endpointu)."""
    slug = _slugify(location)
    if not slug:
        return None

    if slug in STATIC_AREA_IDS:
        return STATIC_AREA_IDS[slug]

    try:
        response = requests.get(f"{BASE_URL}/{slug}", headers=HEADERS, timeout=20)
    except requests.RequestException as exc:
        print(f"[e-chalupy.cz] area lookup pro '{slug}' selhal (request exception): {exc}", file=sys.stderr)
        return None

    if response.status_code != 200:
        print(f"[e-chalupy.cz] area lookup pro '{slug}' selhal (HTTP {response.status_code})", file=sys.stderr)
        return None

    match = DESTINATION_RE.search(response.text)
    if not match:
        print(f"[e-chalupy.cz] area lookup pro '{slug}': dataSearchBoxSelectedData nenalezeno v HTML (délka {len(response.text)} znaků)", file=sys.stderr)
        return None

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        print(f"[e-chalupy.cz] area lookup pro '{slug}': JSON parse selhal: {exc}", file=sys.stderr)
        return None

    destinations = data.get("destinations") or []
    for dest in destinations:
        if dest.get("slug") == slug and dest.get("id"):
            return dest["id"]
    if destinations and destinations[0].get("id"):
        return destinations[0]["id"]

    print(f"[e-chalupy.cz] area lookup pro '{slug}': destinations pole prázdné/bez id", file=sys.stderr)
    return None


def _extract_capacity_bedrooms(tags_featured: list[str]) -> tuple[int | None, int | None]:
    capacity = None
    bedrooms = None
    for tag in tags_featured:
        cap_match = CAPACITY_RE.search(tag)
        bed_match = BEDROOMS_RE.search(tag)
        if cap_match:
            capacity = int(cap_match.group(1))
        if bed_match:
            bedrooms = int(bed_match.group(1))
    return capacity, bedrooms


def _extract_price(price_text: str | None) -> float | None:
    if not price_text:
        return None
    match = PRICE_RE.search(price_text)
    if not match:
        return None
    return float(match.group(1).replace(" ", ""))


def _extract_entire_property(units: dict | None) -> tuple[bool | None, str]:
    """Returns (entire_property, header_text_used) - header kept for raw_extra/debugging."""
    if not units:
        return None, ""

    if isinstance(units.get("items"), list) and units["items"]:
        return False, ""

    header = units.get("header") or {}
    header_text = header.get("desktop") or header.get("mobile") or ""
    if "pronajímá celý" in header_text:
        return True, header_text
    if "samostatná část" in header_text:
        return False, header_text
    return None, header_text


def _extract_likely_apartment(item: dict) -> bool:
    """
    Nabídka spadající pod typ "Chaty a chalupy", ale ve skutečnosti
    patrně jen apartmán/pokoj (ne celý objekt) - ověřeno na Šumavě,
    50 % (598/1200) nabídek matchne aspoň jednu z těchto tří podmínek:
      - název obsahuje "apartmán"
      - tagsFeatured nebo units.items podtituly obsahují "apartmán"
      - priceLabel je "apartmán"/"osob(a/u)" místo "objekt"
    """
    title = (item.get("title") or "").lower()
    if "apartmán" in title:
        return True

    tags_featured = item.get("tagsFeatured") or []
    if any("apartmán" in t.lower() for t in tags_featured):
        return True

    units_items = (item.get("units") or {}).get("items")
    if isinstance(units_items, list):
        if any("apartmán" in (u.get("title") or "").lower() for u in units_items):
            return True

    price_label = (item.get("priceLabel") or "").lower()
    if "apartmán" in price_label or "osob" in price_label:
        return True

    return False


def _parse_item(item: dict) -> Listing:
    slug = item.get("slug", "")
    item_id = item.get("id")
    url = f"https://www.e-chalupy.cz/{slug}-o{item_id}" if slug and item_id else BASE_URL

    area = item.get("area") or {}
    area2 = item.get("area2") or {}
    area_title = (area.get("title") or "").strip()
    area2_title = (area2.get("title") or "").strip()
    location = ", ".join(t for t in (area_title, area2_title) if t)

    capacity, bedrooms = _extract_capacity_bedrooms(item.get("tagsFeatured") or [])
    entire_property, units_header = _extract_entire_property(item.get("units"))

    images = item.get("images") or []
    image_url = f"{BASE_URL}/foto/{images[0]['src']}" if images and images[0].get("src") else None

    return Listing(
        source=SOURCE_NAME,
        title=item.get("title", "Bez názvu"),
        location=location,
        url=url,
        capacity=capacity,
        bedrooms=bedrooms,
        price=_extract_price(item.get("price")),
        price_unit=item.get("priceLabel"),
        amenities=list(item.get("tags") or []),
        image_url=image_url,
        entire_property=entire_property,
        likely_apartment=_extract_likely_apartment(item),
        raw_extra={
            "id": item_id,
            "tags_featured": item.get("tagsFeatured") or [],
            "area_title": area_title,
            "area_slug": area.get("slug"),
            "area2_title": area2_title,
            "area2_slug": area2.get("slug"),
            "gps": item.get("gps"),
            "rating": item.get("rating"),
            "reviews": item.get("reviews"),
            "units_header": units_header,
        },
    )


def _fetch_filter_id_set(base_params: dict, filter_id: int) -> set[int]:
    """Vrátí množinu ID nabídek, které portál sám řadí pod daný filtr ID."""
    ids: set[int] = set()
    offset = 0
    while offset < MAX_LISTINGS:
        response = requests.get(
            API_URL,
            headers=HEADERS,
            params={**base_params, "filters": filter_id, "limit": ENRICH_LIMIT, "offset": offset},
            timeout=30,
        )
        response.raise_for_status()
        items = response.json().get("items") or []
        if not items:
            break
        ids.update(item["id"] for item in items if item.get("id") is not None)
        offset += ENRICH_LIMIT
    return ids


def _enrich_amenities_from_filters(listings: list[Listing], base_params: dict) -> None:
    """
    Doplní listing.amenities o vybavení potvrzené přes server-side
    filters=<id>, i když se odpovídající slovo v tags vůbec nevyskytuje
    jako text (viz docstring modulu - "se psem"/"společenská místnost"
    jsou v tags vždy 0x navzdory stovkám reálných shod).
    """
    by_id = {l.raw_extra["id"]: l for l in listings if l.raw_extra.get("id") is not None}
    if not by_id:
        return

    for amenity_name, filter_ids in AMENITY_FILTER_IDS.items():
        matched_ids: set[int] = set()
        for filter_id in filter_ids:
            matched_ids |= _fetch_filter_id_set(base_params, filter_id)

        for item_id in matched_ids & by_id.keys():
            listing = by_id[item_id]
            if not any(amenity_name in a.lower() for a in listing.amenities):
                listing.amenities.append(amenity_name)


def search(criteria: dict) -> list[Listing]:
    params = {}

    location = criteria.get("location")
    if location:
        area_id = _resolve_area_id(location)
        if area_id:
            params["destinations"] = area_id
        else:
            print(f"[e-chalupy.cz] '{location}' se nepodařilo přeložit na area kód - hledám bez destinations (celostátně, viz MAX_LISTINGS strop)", file=sys.stderr)

    # min_capacity/min_bedrooms/max_price se záměrně neposílají do API -
    # stahujeme kompletní data pro lokalitu a tahle kritéria filtrujeme
    # až v filters.py/frontendu (viz poznámky v docstringu modulu).

    listings: list[Listing] = []
    offset = 0
    while offset < MAX_LISTINGS:
        response = requests.get(
            API_URL,
            headers=HEADERS,
            params={**params, "limit": PAGE_SIZE, "offset": offset},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        items = data.get("items") or []
        if not items:
            break

        listings.extend(_parse_item(item) for item in items)
        offset += PAGE_SIZE

    _enrich_amenities_from_filters(listings, params)

    return listings
