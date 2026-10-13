"""Normalizace nabídek ze scraperů do jednotného schématu (v1).

Vstup:  jedna nabídka ve tvaru, v jakém ji dnes ukládá `results/latest.json`
        (dict z `dataclasses.asdict(Listing)`).
Výstup: stejná nabídka + pole potřebná pro regionální databázi:
        id, okres, gps, price_per_night_from/to, price_estimated,
        price_as_of, price_term, price_note.

Žádná síť, žádné závislosti mimo standardní knihovnu. Původní pole
(`price`, `price_unit`, `amenities`, ...) zůstávají zachována, aby stávající
frontend dál fungoval; mění se jen:
  * `amenities`  -> sjednocené názvy (původní text v raw_extra.amenities_original)
  * `url`        -> u chata.cz bez parametrů termínu (ty by časem zastaraly)
  * `location`   -> u cs-chalupy.cz doplněna obec (portál dává jen region)
  * `raw_extra`  -> bez telefonních čísel a velkých popisů
"""
from __future__ import annotations

import copy
import hashlib
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import parse_qs, urlsplit, urlunsplit

SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Vybavení – sjednocení názvů napříč portály
# ---------------------------------------------------------------------------
# Klíč = původní text (malými písmeny, jednoduché mezery),
# hodnota = seznam kanonických názvů ([] = nejde o vybavení, zahodit).
AMENITY_ALIASES: dict[str, list[str]] = {
    # oplocení
    "oploceno": ["oplocení"],
    "oplocení": ["oplocení"],
    "oplocený objekt": ["oplocení"],
    "částečně oplocen": ["oplocení"],
    "zcela oplocen": ["oplocení"],
    "částečně oplocený objekt": ["oplocení"],
    "zcela oplocený objekt": ["oplocení"],
    "bez oplocení": [],
    "volné prostranství (neoplocený objekt)": [],
    "neoplocený objekt": [],
    # děti
    "pro děti": ["pro děti"],
    "vyžití pro děti": ["pro děti"],
    "dětské hřiště": ["dětské hřiště", "pro děti"],
    "dětský kout (hračky)": ["dětský kout (hračky)", "pro děti"],
    # zvířata
    "mazlíčci vítáni": ["se psem"],
    "se psem": ["se psem"],
    "domácí zvíře": ["se psem"],
    # kola / lyže
    "sklad pro kola/ lyže": ["lyžárna/kolárna"],
    "sklad pro kola/lyže": ["lyžárna/kolárna"],
    "lyžárna/kolárna": ["lyžárna/kolárna"],
    # ostatní drobné varianty
    "internet - wifi": ["wifi"],
    "internet": ["wifi"],
    "wifi": ["wifi"],
    "tv": ["televize"],
    "televize": ["televize"],
    "lednice": ["lednička"],
    "lednička": ["lednička"],
}


def canonical_amenities(items: Optional[list]) -> list[str]:
    """Sjednotí názvy vybavení, odstraní duplicity, zachová pořadí.

    Neznámé položky projdou beze změny (jen malá písmena a čisté mezery),
    takže se žádné vybavení neztratí.
    """
    out: list[str] = []
    for raw in items or []:
        key = " ".join(str(raw).split()).lower()
        if not key:
            continue
        for name in AMENITY_ALIASES.get(key, [key]):
            if name not in out:
                out.append(name)
    return out


# ---------------------------------------------------------------------------
# Ceny – přepočet na noc
# ---------------------------------------------------------------------------
_NIGHTS_RE = re.compile(r"(\d+)\s*noc")
_MIN_NIGHTS_RE = re.compile(r"min\.?\s*noc\w*\s*:?\s*(\d+)")


# Cena celého objektu pod touto hranicí za noc je téměř jistě překlep na portálu
# (skutečný příklad: "Velikonoce 20 Kč / pobyt, min. 4 noci" => 5 Kč za noc).
MIN_PLAUSIBLE_PER_NIGHT = 100


def unit_info(unit: str, note: str = "") -> tuple[Optional[int], str]:
    """Z textu typu ceny vrátí (počet nocí, základ ceny).

    základ: "objekt" | "osoba" | "apartmán" | "pokoj" | "extra" (přistýlka, dítě)
    počet nocí: None = nelze určit (cena se pak nepřepočítává, nic se nehádá)
    """
    low = " ".join((unit or "").lower().split())
    note_low = " ".join((note or "").lower().split())

    if "přistýl" in low or "dít" in low:
        basis = "extra"
    elif re.search(r"\bosob", low):
        basis = "osoba"
    elif "apartm" in low:
        basis = "apartmán"
    elif "pokoj" in low or "lůž" in low:
        basis = "pokoj"
    else:
        basis = "objekt"

    def _from_note() -> Optional[int]:
        m = _NIGHTS_RE.search(note_low) or _MIN_NIGHTS_RE.search(note_low)
        return int(m.group(1)) if m else None

    m = _NIGHTS_RE.search(low)
    if m:                                    # "pobyt 7 nocí"
        nights: Optional[int] = int(m.group(1))
    elif "týd" in low or "tyd" in low:       # "objekt / týden"
        nights = 7
    elif "víkend" in low:                    # "objekt / víkend" (pá–ne = 2 noci)
        nights = _from_note() or 2
    elif "pobyt" in low:                     # "objekt / pobyt" – počet nocí v poznámce
        nights = _from_note()
    elif "noc" in low:                       # "objekt za noc", "osoba / noc"
        nights = 1
    else:
        nights = None
    return nights, basis


def per_night(price: Optional[float], unit: str, note: str,
              capacity: Optional[int]) -> Optional[tuple[int, bool, str]]:
    """(cena za noc za celý objekt, je_odhad, základ) nebo None."""
    if price is None or price <= 0:          # 0 = "cena na dotazu" apod.
        return None
    nights, basis = unit_info(unit, note)
    if basis == "extra" or not nights or nights <= 0:
        return None
    value = float(price) / nights
    estimated = False
    if basis == "osoba":
        # cena za osobu se uznává jen za noc ("Osoba / víkend" nebo "/ pobyt" je dvojznačná)
        if nights != 1 or not capacity:
            return None
        value *= capacity            # předpoklad plné obsazenosti
        estimated = True
    if value < MIN_PLAUSIBLE_PER_NIGHT:
        return None
    return int(round(value)), estimated, basis


def build_price(d: dict, extra: dict) -> dict:
    """Vypočte cenová pole. Chybějící/nečitelná cena = samé None (nic se neschová)."""
    capacity = d.get("capacity")
    results: list[tuple[int, bool, str]] = []

    if d.get("source") == "cs-chalupy.cz":
        # cs-chalupy má sezónní ceník – použijeme všechny řádky -> rozpětí
        for row in extra.get("cenik") or []:
            r = per_night(row.get("cena_hodnota"), row.get("typ") or "",
                          row.get("poznamka") or "", capacity)
            if r:
                results.append(r)

    if not results:
        r = per_night(d.get("price"), d.get("price_unit") or "", "", capacity)
        if r:
            results.append(r)

    # Pořadí důvěry: cena za celý objekt > odhad z ceny za osobu a noc > cena za apartmán/pokoj.
    # Nižší úroveň se použije jen tehdy, když vyšší žádný řádek nemá (jinak by cena pokoje
    # za 1 590 Kč stáhla "od" ceny celé chalupy dolů).
    chosen: list[tuple[int, bool, str]] = []
    for tier in (("objekt",), ("osoba",), ("apartmán", "pokoj")):
        chosen = [r for r in results if r[2] in tier]
        if chosen:
            break

    if not chosen:
        return {"price_per_night_from": None, "price_per_night_to": None,
                "price_estimated": False, "price_note": None}

    values = [r[0] for r in chosen]
    notes: list[str] = []
    parts = sorted({r[2] for r in chosen} & {"apartmán", "pokoj"})
    if parts:
        notes.append("cena za " + " / ".join(parts) + ", ne za celý objekt")
    if any(r[1] for r in chosen):
        notes.append("přepočteno z ceny za osobu při plné kapacitě (odhad)")
    return {
        "price_per_night_from": min(values),
        "price_per_night_to": max(values),
        "price_estimated": any(r[1] for r in chosen),
        "price_note": "; ".join(notes) or None,
    }


def _iso_from_cz(text: str) -> Optional[str]:
    try:
        return datetime.strptime(text, "%d.%m.%Y").date().isoformat()
    except (TypeError, ValueError):
        return None


def price_term(url: str) -> Optional[dict]:
    """Termín, ke kterému cena platí (chata.cz ho má v URL: FromDate/ToDate)."""
    qs = parse_qs(urlsplit(url or "").query)
    start = _iso_from_cz((qs.get("FromDate") or [""])[0])
    end = _iso_from_cz((qs.get("ToDate") or [""])[0])
    if start and end:
        return {"from": start, "to": end}
    return None


# ---------------------------------------------------------------------------
# Identita, URL, poloha
# ---------------------------------------------------------------------------
_ID_PATTERNS = {
    "e-chalupy.cz": re.compile(r"-o(\d+)$"),
    "chata.cz": re.compile(r"-((?:CZ|SK)\d+)$"),
    "cs-chalupy.cz": re.compile(r"\.([0-9A-Za-z]+-\d+)\.html$"),
}


def clean_url(source: str, url: str) -> str:
    """chata.cz: odstranit parametry termínu (zastarají). Ostatní beze změny."""
    if source == "chata.cz" and url:
        p = urlsplit(url)
        return urlunsplit((p.scheme, p.netloc, p.path, "", ""))
    return url


def make_id(source: str, extra: dict, url: str) -> str:
    """Stabilní ID `portál:nativní_id`. Preferuje ID z raw_extra, jinak z URL."""
    native: Any = None
    if source == "e-chalupy.cz":
        native = extra.get("id")
    elif source in ("chata.cz", "cs-chalupy.cz"):
        native = extra.get("code")

    if not native:
        path = urlsplit(url or "").path.rstrip("/")
        pat = _ID_PATTERNS.get(source)
        m = pat.search(path) if pat else None
        native = m.group(1) if m else None

    if not native:   # poslední záchrana: otisk čisté URL (stabilní mezi běhy)
        base = clean_url(source, url or "")
        native = "u" + hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]
    return f"{source}:{native}"


def _num(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_gps(extra: dict) -> Optional[dict]:
    g = extra.get("gps")
    if not isinstance(g, dict):
        return None
    lat = _num(g.get("lat"))
    lon = _num(g.get("lon", g.get("lng")))
    if lat is None or lon is None:
        return None
    return {"lat": lat, "lon": lon}


def _trim_raw_extra(extra: dict) -> dict:
    out = copy.deepcopy(extra)
    out.pop("telephone", None)       # osobní údaje majitelů neukládáme
    out.pop("jsonld_rating", None)
    detail = out.get("popis_detaily")
    if isinstance(detail, dict):     # velký popis; necháme jen užitečné
        keep = ("Rozložení ložnic", "Vzdálenosti")
        out["popis_detaily"] = {k: v for k, v in detail.items() if k in keep}
    return out


# ---------------------------------------------------------------------------
# Hlavní vstup
# ---------------------------------------------------------------------------
def normalize_listing(listing: dict, run_date: str) -> dict:
    """Vrátí novou, normalizovanou kopii nabídky. Idempotentní."""
    if "id" in listing and "price_per_night_from" in listing:
        return copy.deepcopy(listing)

    d = copy.deepcopy(listing)
    extra = d.get("raw_extra") or {}
    src = d.get("source") or ""
    original_url = d.get("url") or ""

    price = build_price(d, extra)
    address = extra.get("address") if isinstance(extra.get("address"), dict) else {}

    location = d.get("location") or ""
    if src == "cs-chalupy.cz" and location and "," not in location:
        obec = (address.get("locality") or "").strip()
        if obec and obec.lower() != location.lower():
            location = f"{obec}, {location}"

    new_extra = _trim_raw_extra(extra)
    new_extra["amenities_original"] = list(d.get("amenities") or [])

    out: dict = {"id": make_id(src, extra, original_url)}
    out.update(d)
    out["location"] = location
    out["url"] = clean_url(src, original_url)
    out["amenities"] = canonical_amenities(d.get("amenities"))
    out["raw_extra"] = new_extra
    out["okres"] = (address.get("region") or None) if src == "cs-chalupy.cz" else None
    out["gps"] = extract_gps(extra)
    out.update(price)
    out["price_as_of"] = run_date if price["price_per_night_from"] is not None else None
    out["price_term"] = price_term(original_url)
    return out
