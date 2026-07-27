"""
Profil pro e-chalupy.cz.

Poznámky k portálu:
- Výsledky hledání jsou vykreslené na serveru, takže stačí requests +
  BeautifulSoup (ověřit při testování - pokud výpis prázdný, může být
  potřeba Playwright).
- Lokalita se ve vyhledávací URL zadává jako interní kód (area_19640),
  ne jako text. Portál ale má i samostatné stránky podle obce/regionu
  (https://e-chalupy.cz/tisa, /krusne-hory apod.) - z lokality děláme
  "slug" (malá písmena, bez diakritiky, mezery -> pomlčky) a zkusíme
  tuhle stránku. Když neexistuje (404), spadneme na obecné vyhledávání
  bez lokality - filtrování podle lokality pak dodělá filters.py.
- Karta nabídky: div.item.c-property > .top .tl a.title (název+odkaz),
  .area a.location (lokalita), .tags .tag.tag-sm (typ+kapacita, ložnice
  a vybavení smíchané dohromady - rozlišujeme přes regex), .price (cena,
  může být prázdná u nabídek s víc objekty).
"""

import re
import unicodedata
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scraper.models import Listing

SOURCE_NAME = "e-chalupy.cz"
BASE_URL = "https://e-chalupy.cz"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ChalupnikBot/1.0; +https://github.com/Nojmi/Chalupnik)"
}

CAPACITY_RE = re.compile(r"(\d+)\s*osob")
BEDROOMS_RE = re.compile(r"(\d+)\s*lo[žz]nic")
PRICE_RE = re.compile(r"([\d\s]+)\s*K[čc]")


def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _build_search_url(criteria: dict) -> str:
    params = []
    if criteria.get("min_capacity"):
        params.append(f"persons={criteria['min_capacity']}")
    if criteria.get("min_bedrooms"):
        params.append(f"bedrooms={criteria['min_bedrooms']}")
    if criteria.get("date_from") and criteria.get("date_to"):
        params.append(f"dates={criteria['date_from']}to{criteria['date_to']}")

    query = ("?" + "&".join(params)) if params else ""

    location = criteria.get("location")
    if location:
        slug = _slugify(location)
        return f"{BASE_URL}/{slug}{query}"

    return f"{BASE_URL}/vyhledavani{query}"


def _parse_card(card) -> Listing:
    title_el = card.select_one(".top .tl a.title")
    title = title_el.get_text(strip=True) if title_el else "Bez názvu"
    url = urljoin(BASE_URL, title_el["href"]) if title_el and title_el.has_attr("href") else BASE_URL

    location_links = card.select(".area a.location")
    location = " - ".join(a.get_text(strip=True) for a in location_links) if location_links else ""

    tag_texts = [t.get_text(strip=True) for t in card.select(".tags .tag.tag-sm")]

    capacity = None
    bedrooms = None
    amenities = []
    for tag in tag_texts:
        cap_match = CAPACITY_RE.search(tag)
        bed_match = BEDROOMS_RE.search(tag)
        if cap_match:
            capacity = int(cap_match.group(1))
        elif bed_match:
            bedrooms = int(bed_match.group(1))
        else:
            amenities.append(tag)

    price = None
    price_unit = None
    price_el = card.select_one(".price")
    if price_el:
        price_text = price_el.get_text(" ", strip=True)
        price_match = PRICE_RE.search(price_text)
        if price_match:
            price = float(price_match.group(1).replace(" ", ""))
            price_unit = "za noc" if "noc" in price_text else None

    return Listing(
        source=SOURCE_NAME,
        title=title,
        location=location,
        url=url,
        capacity=capacity,
        bedrooms=bedrooms,
        price=price,
        price_unit=price_unit,
        amenities=amenities,
        raw_extra={"tags": tag_texts},
    )


def search(criteria: dict) -> list[Listing]:
    url = _build_search_url(criteria)
    response = requests.get(url, headers=HEADERS, timeout=20)

    if response.status_code == 404 and criteria.get("location"):
        fallback_criteria = dict(criteria)
        fallback_criteria["location"] = None
        url = _build_search_url(fallback_criteria)
        response = requests.get(url, headers=HEADERS, timeout=20)

    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")

    cards = soup.select(".property-list .item.c-property")
    return [_parse_card(card) for card in cards]
