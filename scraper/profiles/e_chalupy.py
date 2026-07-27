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
"""

import json
import re
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
MAX_LISTINGS = 1000

DESTINATION_RE = re.compile(r"window\.dataSearchBoxSelectedData\s*=\s*(\{.*?\});")


def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _resolve_area_id(location: str) -> str | None:
    """Best-effort text -> area_XXXXX lookup via the region's HTML page."""
    slug = _slugify(location)
    if not slug:
        return None

    response = requests.get(f"{BASE_URL}/{slug}", headers=HEADERS, timeout=20)
    if response.status_code != 200:
        return None

    match = DESTINATION_RE.search(response.text)
    if not match:
        return None

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None

    destinations = data.get("destinations") or []
    for dest in destinations:
        if dest.get("slug") == slug and dest.get("id"):
            return dest["id"]
    if destinations and destinations[0].get("id"):
        return destinations[0]["id"]
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
        },
    )


def search(criteria: dict) -> list[Listing]:
    params = {}

    location = criteria.get("location")
    if location:
        area_id = _resolve_area_id(location)
        if area_id:
            params["destinations"] = area_id

    if criteria.get("min_capacity"):
        params["persons"] = criteria["min_capacity"]
    if criteria.get("min_bedrooms"):
        params["bedrooms"] = criteria["min_bedrooms"]

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

    return listings
