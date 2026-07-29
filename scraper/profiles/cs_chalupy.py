"""
Profil pro cs-chalupy.cz.

Poznámky k portálu (podrobný recon viz chalupnik-projekt-shrnuti.md,
sekce 6; některé detaily níže byly zjištěny/opraveny až při psaní tohoto
souboru živým fetchem, označeno IMPLEMENTACE):

- Server-rendered HTML, žádné JSON API pro výpis. Model "kontakt na
  majitele bez provize" - žádná cena na kartě výpisu, cena je jen na
  detailu (sekce #cenik).
- **KLÍČOVÁ PAST (potvrzeno reconem): server-side typový filtr
  (pretty URL slug "chaty-a-chalupy"/"sruby-a-roubenky" i `typ[]=`
  query parametr) je nespolehlivý/nefunkční - tiše spadá na "bez
  filtru". Řešení: stahujeme CELÝ region bez typového filtru a typ
  určujeme lokálně z breadcrumb (`#path strong`, text tvaru
  "chalupa č. 3C-053") - to je portálem kanonizovaná kategorie,
  spolehlivější než title tag i než marketingový název. Ponecháváme
  jen TARGET_TYPES (chata/chalupa/srub/roubenka) - whitelist, ne
  blacklist, protože nechceme omylem propustit nový/neznámý typ.**
- Lokalita je pretty URL segment (`/<region-slug>`) - portál má jen
  13 regionů ČR + 4 SK (mnohem hrubší dělení než chata.cz/e-chalupy).
  Žádné JSON autocomplete API jako u chata.cz - seznam regionů (název
  -> slug) se parsuje ze sidebar checkboxů (`input[name="oblast[]"]`),
  přítomných na KAŽDÉ stránce portálu včetně homepage - _load_regions()
  fetchne homepage jednou na začátku běhu (analogie k chata.cz
  AutocompleteRegions, ale bez JSON endpointu).
- Stránkování: `?p=N&of=<total>`. `of=` je celkový počet nalezených
  objektů PRO CELÝ DOTAZ (konstantní napříč stránkami, ne offset).
  IMPLEMENTACE: `of=` parametr a `p=` se posílají jen od druhé stránky
  dál - první stránka (bez parametrů) vrací nadpis "Nalezené objekty
  (N) dle filtru" (`h3.objekt-count`), odkud se `total` čte; stránky
  2+ tenhle nadpis nemají vůbec (ověřeno živě), proto se `total`
  získává výhradně z první stránky a further stránky se řídí jen
  přítomností/nepřítomností karet (žádná spoléhá na pevný PageSize -
  ověřeno 48 karet/stránka na Šumavě, ale radši se neriskuje, kdyby
  se to na jiném regionu lišilo).
  IMPLEMENTACE: na Šumavě (129 objektů) žádná "druhá širší regionální
  sekce" s vlastním počtem nebyla nalezena (na rozdíl od doc TODO
  poznámky v shrnutí, možná se to týkalo starší verze webu nebo jiné
  situace) - stránka má jen JEDEN `h3.objekt-count` nadpis a karty
  jsou napříč všemi stránkami unikátní (ověřeno přes kódy objektů,
  0 duplicit na 129 nabídkách). Pro jistotu se přesto parsuje jen
  PRVNÍ `h3.objekt-count`/`div.objekt-list` sada na stránce (`select`
  bere všechny karty na aktuální stránce, ne napříč sekcemi).
- Karta výpisu (`div.objekt-list`): kód (`p.kod`), kapacita
  (`p.luzka`, "max. N osob"), ložnice/koupelny/wc jako počty ikon
  (`li.png-bed`/`png-koupelna`/`png-wc`, text "Nx"), internet/pes jako
  binární ikony (`li.png-wifi`, `li.png-dog`/`png-dog-no` - "-no"
  sufix i tady znamená NE, stejná konvence jako chata.cz). Chybějící
  `li` (ne "-no" varianta) = žádná data, ne NE (35/48 karet na Šumavě
  nemá `p.rating` vůbec - hodnocení je opravdu volitelné pole).
- Detail URL je přímo `href` na kartě (`h2 a`) - kompletní absolutní
  URL, žádné skládání z fragmentů potřeba.
- **Ceník (`#cenik table.cenik-basic`) - cena NEZÁVISÍ na termínu**,
  vždy přítomná bez nutnosti posílat datum. Řádky mají sezónu
  (`td.sezona strong`, jen na první řádce daného sezónního bloku -
  následující "isSibling" řádky sezónu dědí), cenu, typ ceny
  (`td.typ` - NENÍ konzistentně "Objekt / noc", živě pozorováno i
  "Osoba / noc", "Objekt / týden", "Objekt / pobyt", "Apartmán / noc",
  "Přistýlka / noc", "Dítě / noc") a poznámku.
  **IMPLEMENTACE - KRITICKÁ OPRAVA reconu: řádek "Celoročně" NENÍ
  spolehlivě "hlavní cena za objekt".** Ověřeno na konkrétním
  protipříkladu (3C-017, "Chalupa Šumava - Teplá Vltava - Borová
  Lada"): jediný řádek se sezónou "Celoročně" má typ "Přistýlka / noc"
  za 300 Kč (příplatek za přistýlku, ne cena pobytu) - naivní výběr
  "první řádek s Celoročně" by vrátil zavádějící cenu 300 Kč místo
  reálné ~1800 Kč/noc za apartmán. Řešení: řádky s typem obsahujícím
  "přistýlka" nebo "dítě" (vedlejší/doplňkové sazby, ne základní cena)
  se z výběru hlavní ceny VYLOUČÍ, teprve mezi zbylými kandidáty se
  hledá "Celoročně" -> "Mimosezóna" -> první kandidátní řádek. Celý
  ceník (všechny řádky) se ukládá do `raw_extra["cenik"]` beze ztráty,
  vybraný "hlavní" řádek je jen `Listing.price`/`price_unit`.
- **Vybavení (`#popis table.popis-tabulka`)** - řádky `<tr><td><strong>
  Label:</strong></td><td>hodnota</td></tr>`, parsováno jako dict
  label -> text. Klíčové řádky "Vybavení objektu - vnitřní:" a
  "- venkovní:" jsou čárkami oddělený text (ověřeno bohaté na 6+
  živých detailech napříč regiony/typy - konzistentně bohatší než
  e-chalupy.cz/chata.cz, žádný enrichment fetch není potřeba).
  Tokeny se canonicalizují na sdílený slovník napříč portály
  (`docs/index.html` checkboxy - viz AMENITY_KEYWORDS), nerozpoznané
  tokeny se ponechají jako raw text v amenities (neškodí, jen
  nematchnou žádný filtr checkbox).
  "Domácí zvíře:" řádek má TŘI stavy (ANO/NE/"Pouze po dohodě" -
  jemnější než binární ikona na kartě) - "se psem" se do amenities
  přidá jen při jednoznačném ANO, celý text jde navíc do
  `raw_extra["domaci_zvire"]`.
  Ostatní řádky (Rozložení ložnic, WC, Koupelny, Bezbariérový objekt,
  Kouření v objektu, Vzdálenosti, Aktivity v okolí, Objekt k pronájmu)
  jdou do `raw_extra["popis_detaily"]` beze ztráty.
- **JSON-LD (`@type: LodgingBusiness`)** použito jen pro adresu/GPS/
  telefon/hodnocení do `raw_extra`. `priceRange` se NEPOUŽÍVÁ jako
  zdroj `Listing.price` - ověřeno, že se přepočítává na jinou jednotku
  než ceníková tabulka (JSON-LD "350 - 550 Kč osoba / noc" vs.
  ceníková tabulka 390 Kč/os./noc - blízké, ale ne identické; jinde
  v shrnutí byl pozorován i výraznější rozpor). Ceníková tabulka
  zůstává jediný zdroj pravdy pro cenu.
- **entire_property**: portál na rozdíl od chata.cz nemá pozorovaný
  žádný signál pro "celý objekt vs. jen část/pokoj" (žádné units/rooms
  koncept v datech, model je "kontakt na majitele" pro jeden konkrétní
  objekt). Ponecháno `None` (neznámo), princip "chybějící pole
  neblokuje" - viz shrnutí sekce 7.
- **likely_apartment**: jediný ověřený signál je "apartmán" v title
  (analogie k e-chalupy/chata.cz, ale tady bez units/rooms strukturální
  varianty - portál žádnou takovou strukturu nevystavuje). Příklad
  protipříkladu z reconu ("Apartmánová chalupa..." s breadcrumb typem
  "chalupa") potvrzuje, že se NEJEDNÁ o důvod k vyřazení z výsledků,
  jen k varovnému štítku - stejný princip jako u ostatních portálů.
- Lokalita se do `Listing.location` ukládá jako název regionu
  (z `_load_regions()`), `raw_extra["location_prefiltered"] = True`
  (server už scopoval fetch podle regionu) - `filters.py` tohle pole
  respektuje a nedělá navíc fuzzy textový match (viz `matches()`).
- criteria `min_capacity`/`min_bedrooms`/`max_price`/`date_from`/
  `date_to` se NEPOUŽÍVAJÍ - cena na cs-chalupy.cz nezávisí na termínu
  (na rozdíl od chata.cz) a filtrování kapacity/ložnic/ceny necháváme
  na filters.py/frontendu, stejně jako u ostatních dvou portálů.
"""

import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from scraper.models import Listing

SOURCE_NAME = "cs-chalupy.cz"
BASE_URL = "https://www.cs-chalupy.cz"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

MAX_PAGES = 40  # bezpečnostní strop na stránkovací smyčku
MAX_LISTINGS = 2000  # bezpečnostní strop, největší region má řádově stovky

# Breadcrumb "<typ> č. <kód>" - jen tyto typy chceme (whitelist, ne
# blacklist - viz docstring modulu). Odpovídá portálovému sidebar
# seskupení "Chaty a chalupy" (chata/chalupa) + "Sruby a roubenky".
TARGET_TYPES = {"chata", "chalupa", "srub", "roubenka"}

# Typy cenových řádků, které NIKDY nejsou hlavní cena za pobyt (vedlejší/
# doplňkové sazby) - viz docstring modulu, past s "Celoročně"/Přistýlka.
PRICE_ROW_EXCLUDE_KEYWORDS = ("přistýlka", "dítě")

# Raw token (z "Vybavení objektu - vnitřní/venkovní") -> kanonický název
# sdílený s e-chalupy.cz/chata.cz (viz docs/index.html checkboxy).
# Substring match na lowercase tokenu, první shoda vyhrává. Tokeny bez
# shody se ponechají jako raw text (neškodí, jen nematchnou filtr).
AMENITY_KEYWORDS: list[tuple[str, str]] = [
    ("vířivka", "vířivka"),
    ("sauna", "sauna"),
    ("krb", "krb"),
    ("wifi", "wifi"),
    ("myčka", "myčka nádobí"),
    ("lednič", "lednička"),
    ("lednice", "lednička"),
    ("klimatizace", "klimatizace"),
    ("televiz", "televize"),
    ("bazén", "bazén"),
    ("společenská místnost", "společenská místnost"),
    ("pískoviště", "pískoviště"),
    ("ohniště", "ohniště"),
    ("gril", "gril"),
]

PRICE_RE = re.compile(r"([\d\s\xa0]+)\s*Kč")
CAPACITY_RE = re.compile(r"(\d+)\s*osob")
COUNT_RE = re.compile(r"(\d+)")
BREADCRUMB_TYPE_RE = re.compile(r"^(.+?)\s+č\.")
OBJEKT_COUNT_RE = re.compile(r"\((\d+)\)")


def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _parse_price(text: str | None) -> float | None:
    if not text:
        return None
    match = PRICE_RE.search(text)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    return float(digits) if digits else None


def _load_regions() -> list[dict]:
    """Sidebar `input[name="oblast[]"]` je na každé stránce portálu -
    parsujeme z homepage (jednorázově, na začátku search())."""
    response = requests.get(f"{BASE_URL}/", headers=HEADERS, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")

    regions = []
    seen_slugs = set()
    for checkbox in soup.select('input[name="oblast[]"]'):
        slug = checkbox.get("data-url")
        if not slug or slug in seen_slugs:
            continue
        span = checkbox.find_next("span")
        name = span.get_text(strip=True) if span else slug
        regions.append({"name": name, "slug": slug})
        seen_slugs.add(slug)
    return regions


def _resolve_region_slug(location: str, regions: list[dict]) -> str | None:
    norm_loc = _slugify(location)
    if not norm_loc:
        return None

    for region in regions:
        if region["slug"] == norm_loc:
            return region["slug"]

    for region in regions:
        if norm_loc in region["slug"]:
            return region["slug"]

    return None


def _fetch_region_page(slug: str, page: int, total: int | None) -> tuple[list, int | None]:
    params = {} if page == 1 else {"p": page, "of": total}
    response = requests.get(f"{BASE_URL}/{slug}", params=params, headers=HEADERS, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")

    total_found = None
    heading = soup.select_one("h3.objekt-count")
    if heading:
        match = OBJEKT_COUNT_RE.search(heading.get_text())
        if match:
            total_found = int(match.group(1))

    cards = soup.select("div.objekt-list")
    return cards, total_found


def _fetch_all_cards(slug: str) -> list:
    cards: list = []
    page = 1
    total = None
    while True:
        page_cards, total_found = _fetch_region_page(slug, page, total)
        if total_found is not None:
            total = total_found
        if not page_cards:
            break
        cards.extend(page_cards)
        if total is not None and len(cards) >= total:
            break
        page += 1
        if page > MAX_PAGES or len(cards) >= MAX_LISTINGS:
            break
    return cards


def _extract_code_title_url(card) -> tuple[str | None, str, str]:
    link = card.select_one("h2 a")
    title = link.get_text(strip=True) if link else "Bez názvu"
    url = link["href"] if link and link.get("href") else BASE_URL

    code = None
    kod_el = card.select_one("p.kod")
    if kod_el:
        code = kod_el.get_text(strip=True)
    return code, title, url


def _extract_capacity(card) -> int | None:
    luzka_el = card.select_one("p.luzka")
    if not luzka_el:
        return None
    match = CAPACITY_RE.search(luzka_el.get_text())
    return int(match.group(1)) if match else None


def _extract_room_counts(card) -> dict:
    counts = {}
    for cls, key in (("png-bed", "bedrooms"), ("png-koupelna", "bathrooms"), ("png-wc", "wc")):
        el = card.select_one(f"li.{cls}")
        if not el:
            continue
        match = COUNT_RE.search(el.get_text())
        if match:
            counts[key] = int(match.group(1))
    return counts


def _extract_icon_amenities(card) -> list[str]:
    amenities = []
    if card.select_one("li.png-wifi"):
        amenities.append("wifi")
    if card.select_one("li.png-dog") and not card.select_one("li.png-dog-no"):
        amenities.append("se psem")
    return amenities


def _extract_rating(card) -> dict | None:
    block = card.select_one("p.rating")
    if not block:
        return None
    strong = block.select_one("strong")
    count_link = block.select_one("a")
    value_text = strong.get_text(" ", strip=True) if strong else ""
    value_match = re.search(r"[\d.,]+", value_text)
    return {
        "value": value_match.group(0) if value_match else None,
        "count_text": count_link.get_text(strip=True) if count_link else None,
    }


def _extract_location(card) -> str | None:
    addr = card.select_one("addr")
    if not addr:
        return None
    text = addr.get_text(" ", strip=True)
    return text.replace("mapa", "").strip()


def _parse_card(card) -> Listing:
    code, title, url = _extract_code_title_url(card)
    room_counts = _extract_room_counts(card)

    return Listing(
        source=SOURCE_NAME,
        title=title,
        location=_extract_location(card) or "",
        url=url,
        capacity=_extract_capacity(card),
        bedrooms=room_counts.get("bedrooms"),
        price=None,  # doplněno v _apply_detail (ceník je jen na detailu)
        price_unit=None,
        amenities=_extract_icon_amenities(card),
        image_url=None,
        entire_property=None,  # portál nemá pozorovaný signál, viz docstring
        likely_apartment="apartmán" in title.lower(),
        raw_extra={
            "code": code,
            "bathrooms": room_counts.get("bathrooms"),
            "wc": room_counts.get("wc"),
            "rating": _extract_rating(card),
        },
    )


def _extract_type(detail_soup: BeautifulSoup) -> str | None:
    el = detail_soup.select_one("#path strong")
    if not el:
        return None
    match = BREADCRUMB_TYPE_RE.match(el.get_text(strip=True))
    return match.group(1).strip().lower() if match else None


def _extract_price(detail_soup: BeautifulSoup) -> tuple[float | None, str | None, list[dict]]:
    table = detail_soup.select_one("#cenik table.cenik-basic")
    if not table:
        return None, None, []

    rows = []
    current_season = None
    for tr in table.select("tr"):
        tds = tr.select("td")
        if len(tds) < 3:
            continue
        season_el = tds[0].select_one("strong")
        if season_el:
            current_season = season_el.get_text(strip=True)
        cena_text = tds[1].get_text(" ", strip=True)
        typ = tds[2].get_text(" ", strip=True)
        poznamka = tds[3].get_text(" ", strip=True) if len(tds) > 3 else ""
        rows.append({
            "sezona": current_season,
            "cena": cena_text,
            "cena_hodnota": _parse_price(cena_text),
            "typ": typ,
            "poznamka": poznamka,
        })

    if not rows:
        return None, None, rows

    candidates = [
        r for r in rows
        if r["cena_hodnota"] is not None
        and not any(kw in (r["typ"] or "").lower() for kw in PRICE_ROW_EXCLUDE_KEYWORDS)
    ] or [r for r in rows if r["cena_hodnota"] is not None]

    if not candidates:
        return None, None, rows

    chosen = next((r for r in candidates if r["sezona"] and "celoroč" in r["sezona"].lower()), None)
    if not chosen:
        chosen = next((r for r in candidates if r["sezona"] and "mimosez" in r["sezona"].lower()), None)
    if not chosen:
        chosen = candidates[0]

    return chosen["cena_hodnota"], chosen["typ"].lower() if chosen["typ"] else None, rows


def _parse_popis_table(detail_soup: BeautifulSoup) -> dict[str, str]:
    table = detail_soup.select_one("#popis table.popis-tabulka")
    if not table:
        return {}
    details = {}
    for tr in table.select("tr"):
        label_el = tr.select_one("td strong")
        tds = tr.select("td")
        if not label_el or len(tds) < 2:
            continue
        label = label_el.get_text(strip=True).rstrip(":")
        value = tds[1].get_text(" ", strip=True)
        details[label] = value
    return details


def _canonicalize_amenity(raw_token: str) -> str:
    lowered = raw_token.strip().lower()
    if lowered == "tv":
        return "televize"
    for keyword, canonical in AMENITY_KEYWORDS:
        if keyword in lowered:
            return canonical
    return raw_token.strip()


def _extract_amenities_and_details(detail_soup: BeautifulSoup) -> tuple[list[str], dict]:
    details = _parse_popis_table(detail_soup)

    amenities: list[str] = []
    for key in ("Vybavení objektu - vnitřní", "Vybavení objektu - venkovní"):
        raw = details.get(key, "")
        for token in raw.split(","):
            token = token.strip()
            if not token:
                continue
            canonical = _canonicalize_amenity(token)
            if canonical and canonical not in amenities:
                amenities.append(canonical)

    pet_text = details.get("Domácí zvíře", "")
    if pet_text.lower().startswith("ano") and "se psem" not in amenities:
        amenities.append("se psem")

    popis_detaily = {
        k: v for k, v in details.items()
        if k not in ("Vybavení objektu - vnitřní", "Vybavení objektu - venkovní")
    }

    return amenities, {"domaci_zvire": pet_text or None, "popis_detaily": popis_detaily}


def _extract_jsonld(detail_soup: BeautifulSoup) -> dict:
    import json

    for script in detail_soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except (TypeError, ValueError):
            continue
        if data.get("@type") != "LodgingBusiness":
            continue
        address = data.get("address") or {}
        geo = data.get("geo") or {}
        rating = data.get("aggregateRating") or {}
        return {
            "address": {
                "street": address.get("streetAddress"),
                "locality": address.get("addressLocality"),
                "region": address.get("addressRegion"),
                "postal_code": address.get("postalCode"),
            },
            "gps": {"lat": geo.get("latitude"), "lng": geo.get("longitude")} if geo else None,
            "telephone": data.get("telephone"),
            "rating": {
                "value": rating.get("ratingValue"),
                "review_count": rating.get("reviewCount"),
            } if rating else None,
            "image": data.get("image"),
        }
    return {}


def _apply_detail(listing: Listing) -> bool:
    """Fetch detailu, doplní typ/cenu/vybavení/JSON-LD data.
    Vrací False, pokud nabídka nepatří do TARGET_TYPES (má se zahodit)."""
    try:
        response = requests.get(listing.url, headers=HEADERS, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return False

    soup = BeautifulSoup(response.text, "lxml")

    listing_type = _extract_type(soup)
    if listing_type not in TARGET_TYPES:
        return False

    price, price_unit, cenik_rows = _extract_price(soup)
    amenities, popis_extra = _extract_amenities_and_details(soup)
    jsonld = _extract_jsonld(soup)

    listing.price = price
    listing.price_unit = price_unit
    for amenity in amenities:
        if amenity not in listing.amenities:
            listing.amenities.append(amenity)
    if not listing.image_url and jsonld.get("image"):
        listing.image_url = jsonld["image"]

    listing.raw_extra.update({
        "type": listing_type,
        "cenik": cenik_rows,
        **popis_extra,
        "address": jsonld.get("address"),
        "gps": jsonld.get("gps"),
        "telephone": jsonld.get("telephone"),
        "jsonld_rating": jsonld.get("rating"),
    })
    return True


def search(criteria: dict) -> list[Listing]:
    location = (criteria.get("location") or "").strip()

    regions = _load_regions()
    slug = None
    region_name = None
    if location:
        slug = _resolve_region_slug(location, regions)
        if slug:
            region_name = next((r["name"] for r in regions if r["slug"] == slug), slug)

    if location and not slug:
        # Lokalitu se nepodařilo přeřadit na žádný z ~17 regionů portálu -
        # radši nic nevracet, než spustit scraping celého katalogu
        # (2167 objektů * per-listing detail fetch by bylo neúměrně
        # nákladné pro neshodu). Analogie k tomu, že region zůstává
        # "povinný" vstup i u ostatních profilů (shrnutí sekce 4/5).
        return []

    cards = _fetch_all_cards(slug) if slug else []

    listings = [_parse_card(card) for card in cards]
    for listing in listings:
        listing.location = region_name or listing.location
        listing.raw_extra["location_prefiltered"] = True

    # min_capacity/min_bedrooms/max_price/date_from/date_to se záměrně
    # neposílají do dotazu (cena na cs-chalupy.cz na termínu nezávisí,
    # ostatní kritéria necháváme na filters.py/frontendu - stejně jako
    # e-chalupy.cz a chata.cz).
    kept: list[Listing] = []
    for listing in listings:
        if _apply_detail(listing):
            kept.append(listing)

    return kept
