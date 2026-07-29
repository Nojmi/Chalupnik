"""
Profil pro chata.cz.

Poznámky k portálu (podrobný recon viz chalupnik-projekt-shrnuti.md,
sekce 5):
- Žádné centrální JSON API jako u e-chalupy - hybrid. Lokalita se
  překládá na interní (LocationId, LocationType) přes JSON AJAX
  endpoint `Autocomplete/<text>` (text je součást CESTY URL, ne query
  parametr; funguje bez cookies/session - ověřeno). Samotný výpis
  nabídek (`vyhledavani/`) je server-rendered HTML, parsuje se přes
  BeautifulSoup.
- `Autocomplete/<text>` vrací napříč typy lokalit (LocationType 3=okres,
  4=obec, 6=region). Preferujeme přesný region (6), jinak bereme první
  výsledek (portál sám řadí podle relevance).
- Region jako vstup zůstává (analogie k e-chalupy), i když u chata.cz
  žádný limit výsledků na dotaz nebyl pozorován (objem je řádově menší
  než e-chalupy - největší region má ~90 nabídek, ne limit, ale
  konzistence s ostatními profily a předvídatelné chování).
- `&page=N` je normální GET parametr, `#totalitems` hidden input na
  první stránce dává celkový počet - iterujeme, dokud
  `(page-1)*PageSize < totalitems`.
- `AccType=2|3|6|7|8|11|18|25|27` omezuje na kategorii "Chaty a
  chalupy" (portál kromě toho nabízí i apartmány/penziony/hotely/ATC,
  což je mimo scope projektu) - posíláme napevno, ne podle criteria.
- Vířivka/sauna/krb (vnitřní i venkovní) mají na kartě výpisu NULOVÉ
  textové i ikonové pokrytí - `sec-ikonky` blok je obsahuje jen pro:
  zvíře, internet, vyžití pro děti, bazén, lyžárna/kolárna, parkování,
  povlečení, oplocení (viz ICON_AMENITIES). Jediné textové výskyty
  "sauna"/"krb"/"vířivka" na kartě pocházejí z `alt` atributů fotek ve
  fotogalerii (popisky jako "Finská sauna") - nespolehlivé, silně
  podhodnocené proti sidebaru (ověřeno na Šumavě). Řešení: server-side
  `Equipment*=true` query parametry (EquipmentWhirpool/EquipmentSauna/
  EquipmentFireplaceIndoor/EquipmentFireplaceOutdoor) vrací přesně
  stejná čísla jako sidebar (100% shoda, ověřeno) - obohacujeme stejně
  jako e-chalupy dělá s `filters=<id>` (viz EQUIPMENT_QUERY_PARAMS a
  _enrich_amenities). "krb" slučuje vnitřní + venkovní pod jeden tag,
  stejně jako e-chalupy.
- `distributePersons`/`hasPrice` hidden inputy (spolehlivý signál pro
  entire_property) existují JEN na detailu nabídky, ne na kartě výpisu
  (ověřeno - nulový výskyt v celé výpis stránce). Proto se pro
  entire_property dotahuje detail stránka každé nabídky zvlášť (přes
  `detail_objekt_url_*` hidden input) - o(N) requestů navíc, přijatelné
  vzhledem k malým objemům na chata.cz (desítky, ne tisíce nabídek na
  region).
- `detail_objekt_url_*` hidden input na kartě je spolehlivý zdroj
  detail URL (portál nekonzistentně střídá prefix `/chalupa/` a
  `/ubytovani/` u stejného regionu) - nikdy nestavět URL ručně.
- Cena se na kartě zobrazí jen s vyplněným FromDate/ToDate/Adults -
  jinak jen tlačítko "ZJISTIT CENU" bez čísla. I s vyplněným termínem
  je BĚŽNÉ, že většina nabídek v sezóně skončí jako "Termín je obsazen"
  nebo "restricted" (min. počet nocí / jen SO-SO pobyty) místo reálné
  ceny - to je legitimní dostupnost, ne bug. Jednonoční víkendový dotaz
  na Šumavě (33 nabídek) vrátil 0 reálných cen (všechno restricted),
  týdenní SO-SO dotaz 4 z 31 (zbytek obsazeno). Proto výchozí termín
  (když date_from/date_to chybí v criteria) je týden od nejbližší
  soboty (DEFAULT_STAY_NIGHTS), ne jen víkend - výrazně vyšší šance na
  reálnou cenu. Cena na kartě je CELKOVÁ za pobyt (ne za noc) -
  price_unit proto ukládáme jako "pobyt N nocí", ne "noc".
- Karta může mít víc bloků `sec-price` (víc rezervovatelných
  jednotek/pokojů na objekt, každý s vlastním `roomID` v odkazu) -
  ukládáme všechny do raw_extra["rooms"], jako Listing.price bereme
  první nalezenou reálnou cenu.
- min_capacity/min_bedrooms/max_price se (stejně jako u e-chalupy)
  NEPOSÍLAJÍ do dotazu - filtrování necháváme na filters.py/frontendu.
  Adults pro cenový dotaz je proto fixní (2), nezávislé na
  min_capacity criteria (to by nechtěně omezovalo dostupnost pokojů).
"""

import re
from datetime import date, timedelta
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from scraper.models import Listing

SOURCE_NAME = "chata.cz"
BASE_URL = "https://www.chata.cz"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}
AJAX_HEADERS = dict(HEADERS, **{
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
})

PAGE_SIZE = 50
MAX_LISTINGS = 2000  # bezpečnostní strop, reálné regiony mají řádově desítky-nízké stovky
MAX_PAGES = 40  # bezpečnostní strop na stránkovací smyčku

ACC_TYPE_CHATY_CHALUPY = "2|3|6|7|8|11|18|25|27"
DEFAULT_STAY_NIGHTS = 7

# CSS třída ikony v sec-ikonky (bez _disabled sufixu = "ano") -> název vybavení.
# POZOR: vířivka/sauna/krb tu záměrně NEJSOU - na kartě nemají žádnou
# ikonu vůbec (viz docstring modulu), řeší se přes EQUIPMENT_QUERY_PARAMS.
ICON_AMENITIES: dict[str, str] = {
    "zvire": "pes",
    "wifi": "internet",
    "vyziti-deti": "vyžití pro děti",
    "bazen": "bazén",
    "lyzarna-kolarna": "lyžárna/kolárna",
    "parking": "parkování",
    "povleceni": "povlečení",
    "oploceni": "oplocení",
}

# Vybavení bez ikonového/textového projevu na kartě -> server-side
# Equipment*=true query parametr(y), viz docstring modulu.
EQUIPMENT_QUERY_PARAMS: dict[str, tuple[str, ...]] = {
    "vířivka": ("EquipmentWhirpool",),
    "sauna": ("EquipmentSauna",),
    "krb": ("EquipmentFireplaceIndoor", "EquipmentFireplaceOutdoor"),
}

PRICE_RE = re.compile(r"([\d\s\xa0]+)\s*Kč")


def _default_dates() -> tuple[str, str]:
    """Nejbližší sobota + DEFAULT_STAY_NIGHTS dní, formát DD.MM.YYYY."""
    today = date.today()
    days_ahead = (5 - today.weekday()) % 7 or 7
    saturday = today + timedelta(days=days_ahead)
    end = saturday + timedelta(days=DEFAULT_STAY_NIGHTS)
    return saturday.strftime("%d.%m.%Y"), end.strftime("%d.%m.%Y")


def _iso_to_chata_date(iso_str: str) -> str:
    return date.fromisoformat(iso_str).strftime("%d.%m.%Y")


def _resolve_location(location: str) -> tuple[int, int] | None:
    """Autocomplete/<text> -> (LocationId, LocationType), region (6) preferovaně."""
    url = f"{BASE_URL}/Autocomplete/{quote(location)}"
    try:
        response = requests.get(url, headers=AJAX_HEADERS, timeout=15)
        response.raise_for_status()
        results = response.json()
    except (requests.RequestException, ValueError):
        return None

    if not results:
        return None

    for item in results:
        if item.get("LocationType") == 6 and item.get("LocationId") is not None:
            return item["LocationId"], item["LocationType"]

    first = results[0]
    if first.get("LocationId") is not None and first.get("LocationType") is not None:
        return first["LocationId"], first["LocationType"]
    return None


def _fetch_page(params: dict) -> tuple[BeautifulSoup, int]:
    response = requests.get(f"{BASE_URL}/vyhledavani/", params=params, headers=HEADERS, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    total_input = soup.select_one("#totalitems")
    try:
        total_items = int(total_input["value"]) if total_input else 0
    except (TypeError, ValueError):
        total_items = 0
    return soup, total_items


def _fetch_all_cards(params: dict) -> list:
    cards: list = []
    page = 1
    total_items = None
    while total_items is None or (page - 1) * PAGE_SIZE < total_items:
        soup, total_items = _fetch_page({**params, "PageSize": PAGE_SIZE, "page": page})
        page_cards = soup.select("div.product")
        if not page_cards:
            break
        cards.extend(page_cards)
        page += 1
        if page > MAX_PAGES or len(cards) >= MAX_LISTINGS:
            break
    return cards


def _extract_code_title(card) -> tuple[str | None, str]:
    link = card.select_one("a.ppv")
    title = link.get_text(strip=True) if link else "Bez názvu"
    code = None
    link_id = link.get("id", "") if link else ""
    if link_id.startswith("odkaz_"):
        code = link_id[len("odkaz_"):]
    return code, title


def _extract_location(card) -> str:
    marker = card.select_one("img[src*='placeholder-filled-point']")
    if not marker:
        return ""
    span = marker.find_next("span")
    if not span:
        return ""
    parts = [a.get_text(strip=True) for a in span.select("a")]
    return ", ".join(parts)


def _extract_detail_url(card) -> str:
    hidden = card.select_one("input[id^='detail_objekt_url_']")
    if hidden and hidden.get("value"):
        return hidden["value"]
    link = card.select_one("a.ppv")
    return link["href"] if link and link.get("href") else BASE_URL


def _extract_capacity_bedrooms(card) -> tuple[int | None, int | None]:
    capacity = None
    bedrooms = None
    for block in card.select(".sec-kapacita"):
        text = block.get_text(" ", strip=True)
        match = re.search(r"(\d+)", text)
        if not match:
            continue
        if "kapacita" in text.lower():
            capacity = int(match.group(1))
        elif "pokoj" in text.lower():
            bedrooms = int(match.group(1))
    return capacity, bedrooms


def _parse_price(text: str | None) -> float | None:
    if not text:
        return None
    match = PRICE_RE.search(text)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    return float(digits) if digits else None


def _extract_rooms(card) -> list[dict]:
    """
    Každý .sec-price blok = jedna rezervovatelná jednotka (pokoj/apartmá/
    celý objekt). Objekt bez vyplněného termínu nebo bez dostupnosti
    nemá číselnou cenu - to je očekávané, ne chyba parsování.
    """
    rooms = []
    for block in card.select(".sec-price"):
        name_el = block.select_one(".nazevj")
        name = name_el.get_text(strip=True) if name_el else None
        classes = block.get("class") or []

        if block.select_one(".obsazeno"):
            rooms.append({"name": name, "status": "obsazeno", "price": None})
            continue

        if "restricted" in classes:
            restrictions = [r.get_text(" ", strip=True) for r in block.select(".restrikce")]
            rooms.append({"name": name, "status": "restricted", "price": None, "restrictions": restrictions})
            continue

        price_el = block.select_one("big")
        price = _parse_price(price_el.get_text()) if price_el else None

        room_id = None
        link = block.select_one("a[href*='roomID=']")
        if link and link.get("href"):
            match = re.search(r"roomID=(\d+)", link["href"])
            if match:
                room_id = int(match.group(1))

        avail_el = block.select_one(".pokoje")
        rooms.append({
            "name": name,
            "status": "available" if price is not None else "unknown",
            "price": price,
            "room_id": room_id,
            "availability": avail_el.get_text(strip=True) if avail_el else None,
        })
    return rooms


def _extract_icon_amenities(card) -> tuple[list[str], dict]:
    amenities: list[str] = []
    tooltips: dict = {}
    icon_block = card.select_one(".sec-ikonky")
    if not icon_block:
        return amenities, tooltips

    for img in icon_block.select("img[src*='/design/vypis/']"):
        match = re.search(r"/design/vypis/([\w\-]+?)(_disabled)?\.png", img.get("src", ""))
        if not match:
            continue
        stub, disabled = match.group(1), match.group(2)
        name = ICON_AMENITIES.get(stub)
        if not name or disabled:
            continue
        if name not in amenities:
            amenities.append(name)

        tooltip_img = img.find_next_sibling("img", attrs={"alt": "Upřesnění"})
        if tooltip_img and tooltip_img.get("data-tooltip"):
            tooltips[name] = tooltip_img["data-tooltip"]

    return amenities, tooltips


def _extract_rating(card) -> dict | None:
    block = card.select_one(".sec-hodnoceni")
    if not block or block.select_one(".no_text"):
        return None
    value_el = block.select_one(".modry_box span")
    if not value_el:
        return None
    word_el = block.select_one(".txt_hodnoceni")
    count_el = block.select_one("a.hodnoceni")
    return {
        "value": value_el.get_text(strip=True),
        "word": word_el.get_text(strip=True) if word_el else None,
        "count_text": count_el.get_text(strip=True) if count_el else None,
    }


def _extract_badges(card) -> list[dict]:
    badges = []
    for span in card.select(".indikatory .indicator"):
        badges.append({
            "text": span.get_text(strip=True),
            "title": span.get("title"),
            "class": " ".join(span.get("class", [])),
        })
    return badges


def _extract_image_url(card) -> str | None:
    """
    První swiper-slide je obvykle titulní foto (plná URL v src), další
    jsou lazy-loaded (data-src). Pokud je titulním "slidem" jen ikonka
    videa (např. /img/video_znak.png - relativní cesta, objekt má místo
    fotky video), přeskočí se na první slide s plnou http(s) URL.
    """
    for image_el in card.select(".swiper-slide img"):
        src = image_el.get("data-src") or image_el.get("src")
        if src and src.startswith("http"):
            return src

    image_el = card.select_one(".swiper-slide img")
    if not image_el:
        return None
    src = image_el.get("data-src") or image_el.get("src")
    if src and src.startswith("/"):
        return f"{BASE_URL}{src}"
    return src


def _parse_card(card, nights: int) -> Listing:
    code, title = _extract_code_title(card)
    rooms = _extract_rooms(card)
    icon_amenities, tooltips = _extract_icon_amenities(card)
    capacity, bedrooms = _extract_capacity_bedrooms(card)

    priced_rooms = [r for r in rooms if r.get("price") is not None]
    price = priced_rooms[0]["price"] if priced_rooms else None

    return Listing(
        source=SOURCE_NAME,
        title=title,
        location=_extract_location(card),
        url=_extract_detail_url(card),
        capacity=capacity,
        bedrooms=bedrooms,
        price=price,
        price_unit=f"pobyt {nights} nocí" if price is not None else None,
        amenities=icon_amenities,
        image_url=_extract_image_url(card),
        entire_property=None,  # doplněno v _apply_entire_property (detail stránka)
        likely_apartment=False,
        raw_extra={
            "code": code,
            "rooms": rooms,
            "rating": _extract_rating(card),
            "badges": _extract_badges(card),
            "equipment_tooltips": tooltips,
        },
    )


def _fetch_equipment_codes(base_params: dict, equipment_param: str) -> set[str]:
    codes: set[str] = set()
    query = {**base_params, equipment_param: "true"}
    for card in _fetch_all_cards(query):
        code, _ = _extract_code_title(card)
        if code:
            codes.add(code)
    return codes


def _enrich_amenities(listings: list[Listing], base_params: dict) -> None:
    by_code = {l.raw_extra["code"]: l for l in listings if l.raw_extra.get("code")}
    if not by_code:
        return

    for amenity_name, equipment_params in EQUIPMENT_QUERY_PARAMS.items():
        matched_codes: set[str] = set()
        for equipment_param in equipment_params:
            matched_codes |= _fetch_equipment_codes(base_params, equipment_param)

        for code in matched_codes & by_code.keys():
            listing = by_code[code]
            if amenity_name not in listing.amenities:
                listing.amenities.append(amenity_name)


def _fetch_entire_property(detail_url: str) -> bool | None:
    """distributePersons=false -> jedna propočítaná cena za celý objekt (entire=True).
    distributePersons=true -> nutno vybrat konkrétní pokoj(e) (entire=False)."""
    try:
        response = requests.get(detail_url, headers=HEADERS, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return None
    soup = BeautifulSoup(response.text, "lxml")
    el = soup.select_one("#distributePersons")
    if not el or el.get("value") is None:
        return None
    return el["value"].strip().lower() != "true"


def _apply_entire_property(listings: list[Listing]) -> None:
    for listing in listings:
        listing.entire_property = _fetch_entire_property(listing.url)


def search(criteria: dict) -> list[Listing]:
    location = (criteria.get("location") or "").strip()

    params: dict = {
        "Where": location,
        "Distance": 0,
        "Adults": 2,
        "GuestsType": "TwoAdults",
        "RoomAmountType": "More",
        "SortingType": "Regio",
        "AccType": ACC_TYPE_CHATY_CHALUPY,
    }

    location_resolved = False
    if location:
        resolved = _resolve_location(location)
        if resolved:
            params["Autocomplete.LocationId"], params["Autocomplete.LocationType"] = resolved
            location_resolved = True

    date_from = criteria.get("date_from")
    date_to = criteria.get("date_to")
    if date_from and date_to:
        params["FromDate"] = _iso_to_chata_date(date_from)
        params["ToDate"] = _iso_to_chata_date(date_to)
        nights = (date.fromisoformat(date_to) - date.fromisoformat(date_from)).days
    else:
        params["FromDate"], params["ToDate"] = _default_dates()
        nights = DEFAULT_STAY_NIGHTS

    cards = _fetch_all_cards(params)
    listings = [_parse_card(card, nights) for card in cards]
    for listing in listings:
        listing.raw_extra["location_prefiltered"] = location_resolved

    # min_capacity/min_bedrooms/max_price se záměrně neposílají do dotazu -
    # filtrování necháváme na filters.py/frontendu (stejně jako e-chalupy).
    _enrich_amenities(listings, params)
    _apply_entire_property(listings)

    return listings
