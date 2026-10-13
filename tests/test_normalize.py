"""Testy normalizace na reálných záznamech z results/latest.json (Krkonoše, 29. 7. 2026).

Fixture `run_sample.json` obsahuje 6 nabídek: 2× e-chalupy.cz, 2× chata.cz, 2× cs-chalupy.cz.
Druhý záznam e-chalupy.cz byl v ukázce useknutý, proto nemá raw_extra (záměrně –
ověřuje odvození ID z URL).
"""
import json
from pathlib import Path

import pytest

from scraper.normalize import (build_price, canonical_amenities, normalize_listing,
                               per_night, unit_info)

FIXTURE = Path(__file__).parent / "fixtures" / "run_sample.json"
RUN_DATE = "2026-07-29"


@pytest.fixture(scope="module")
def sample():
    run = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return {x["title"]: x for x in run["listings"]}


def norm(sample, title):
    return normalize_listing(sample[title], RUN_DATE)


# --- e-chalupy.cz ----------------------------------------------------------
def test_echalupy_id_price_gps(sample):
    n = norm(sample, "Roubenka Jílové")
    assert n["id"] == "e-chalupy.cz:542"
    assert (n["price_per_night_from"], n["price_per_night_to"]) == (3429, 3429)
    assert n["price_estimated"] is False
    assert n["price_as_of"] == RUN_DATE
    assert n["price_term"] is None
    assert n["gps"] == {"lat": 50.6704164, "lon": 15.2873283}
    assert n["okres"] is None
    assert n["bedrooms"] is None                       # chybějící údaj zůstává None


def test_echalupy_amenities_deduplicated(sample):
    n = norm(sample, "Roubenka Jílové")
    assert n["amenities"].count("se psem") == 1        # "mazlíčci vítáni" + "se psem"
    assert "mazlíčci vítáni" not in n["amenities"]
    assert "pro děti" in n["amenities"] and "bazén" in n["amenities"]
    assert "mazlíčci vítáni" in n["raw_extra"]["amenities_original"]


def test_echalupy_id_from_url_when_raw_extra_missing(sample):
    n = norm(sample, "Wellness chata - roubenka")
    assert n["id"] == "e-chalupy.cz:4257"
    assert n["gps"] is None
    assert "oplocení" in n["amenities"] and "oploceno" not in n["amenities"]


# --- chata.cz --------------------------------------------------------------
def test_chata_price_per_night_and_term(sample):
    n = norm(sample, "Chalupa Chaloupka Harrachov")
    assert n["id"] == "chata.cz:CZ8633"
    assert n["price_per_night_from"] == n["price_per_night_to"] == 5500   # 38 500 / 7
    assert n["price_term"] == {"from": "2026-08-01", "to": "2026-08-08"}
    assert n["price"] == 38500.0 and n["price_unit"] == "pobyt 7 nocí"    # původní pole beze změny


def test_chata_url_has_no_stale_dates(sample):
    n = norm(sample, "Chalupa Chaloupka Harrachov")
    assert n["url"] == ("https://www.chata.cz/chalupa/krkonose/harrachov/"
                        "chalupa-chaloupka-harrachov-CZ8633/")


def test_chata_second_listing(sample):
    n = norm(sample, "Chalupa Máca")
    assert n["id"] == "chata.cz:CZ6516"
    assert n["price_per_night_from"] == 4749                              # 33 243 / 7
    assert "pro děti" in n["amenities"] and "vyžití pro děti" not in n["amenities"]


# --- cs-chalupy.cz ---------------------------------------------------------
def test_cs_first_listing_season_range_and_location(sample):
    n = norm(sample, "Dvě chalupy se saunou - Paseky - Krkonoše")
    assert n["id"] == "cs-chalupy.cz:5C-010"
    # léto 24 000/7, mimosezóna 10 000/2 (víkend), zima 33 000/7, Vánoce 24 000/7, Silvestr 48 000/7
    assert n["price_per_night_from"] == 3429
    assert n["price_per_night_to"] == 6857
    assert n["location"] == "Sklenařice, Krkonoše"
    assert n["okres"] == "Semily"
    assert n["gps"] == {"lat": 50.7032403, "lon": 15.3891769}             # texty -> čísla
    assert n["price"] == 10000.0                                          # původní pole beze změny


def test_cs_amenities_neoplocen_is_not_fence_and_aliases(sample):
    n = norm(sample, "Dvě chalupy se saunou - Paseky - Krkonoše")
    assert "oplocení" not in n["amenities"]            # "neoplocený objekt" NENÍ oplocení
    assert not any("oplocen" in a for a in n["amenities"])
    assert "lyžárna/kolárna" in n["amenities"]         # z "sklad pro kola/ lyže"
    assert "pro děti" in n["amenities"]                # z "dětské hřiště"
    assert n["amenities"].count("se psem") == 1


def test_cs_second_listing(sample):
    n = norm(sample, "Chalupa Krkonoše - sauna a kachlová kamna")
    assert n["id"] == "cs-chalupy.cz:5C-016"
    # nejlevnější: mimosezóna 55 000/7 = 7 857; nejdražší: Silvestr/Vánoce 100 000/7 = 14 286
    assert (n["price_per_night_from"], n["price_per_night_to"]) == (7857, 14286)
    assert n["location"] == "Černý Důl, Krkonoše" and n["okres"] == "Trutnov"
    assert "oplocení" in n["amenities"]                # z "oplocený objekt"


def test_cs_raw_extra_drops_phone_and_keeps_rest(sample):
    n = norm(sample, "Dvě chalupy se saunou - Paseky - Krkonoše")
    assert "telephone" not in n["raw_extra"]
    assert "jsonld_rating" not in n["raw_extra"]
    assert len(n["raw_extra"]["cenik"]) == 5
    assert set(n["raw_extra"]["popis_detaily"]) == {"Rozložení ložnic", "Vzdálenosti"}


# --- obecné vlastnosti -----------------------------------------------------
def test_all_ids_unique_and_prefixed(sample):
    ids = [normalize_listing(x, RUN_DATE)["id"] for x in sample.values()]
    assert len(set(ids)) == 6
    assert all(i.split(":")[0] in {"e-chalupy.cz", "chata.cz", "cs-chalupy.cz"} for i in ids)


def test_input_is_not_mutated(sample):
    before = json.dumps(sample["Chalupa Máca"], sort_keys=True)
    normalize_listing(sample["Chalupa Máca"], RUN_DATE)
    assert json.dumps(sample["Chalupa Máca"], sort_keys=True) == before


def test_idempotent(sample):
    once = normalize_listing(sample["Chalupa Máca"], RUN_DATE)
    twice = normalize_listing(once, "2030-01-01")
    assert twice == once


# --- ceny: okrajové případy ---------------------------------------------------
def test_per_person_price_is_estimate_times_capacity():
    assert per_night(500, "Osoba / noc", "", 10) == (5000, True, "osoba")
    assert per_night(500, "Osoba / noc", "", None) is None            # bez kapacity nehádat


def test_extra_beds_and_children_rows_ignored():
    assert per_night(300, "Přistýlka / noc", "", 5) is None
    assert per_night(200, "Dítě / noc", "", 5) is None


def test_unknown_or_missing_price_never_crashes():
    assert per_night(None, "Objekt / noc", "", 5) is None
    assert per_night(1000, "něco divného", "", 5) is None
    assert per_night(1000, "Objekt / pobyt", "", 5) is None           # počet nocí neznámý
    out = build_price({"source": "e-chalupy.cz", "price": None, "price_unit": ""}, {})
    assert out["price_per_night_from"] is None and out["price_per_night_to"] is None


def test_cs_apartment_case_ignores_extra_bed_row_and_flags_apartment():
    """Past z projektu (3C-017): "Celoročně" = přistýlka 300 Kč nesmí být hlavní cena."""
    d = {"source": "cs-chalupy.cz", "capacity": 8, "price": 300.0, "price_unit": "Přistýlka / noc"}
    extra = {"cenik": [
        {"sezona": "Celoročně", "cena_hodnota": 300.0, "typ": "Přistýlka / noc", "poznamka": ""},
        {"sezona": "Sezóna LÉTO", "cena_hodnota": 1800.0, "typ": "Apartmán / noc", "poznamka": ""},
    ]}
    out = build_price(d, extra)
    assert (out["price_per_night_from"], out["price_per_night_to"]) == (1800, 1800)
    assert "apartmán" in out["price_note"]


@pytest.mark.parametrize("unit,note,expected", [
    ("objekt za noc", "", 1),
    ("pobyt 7 nocí", "", 7),
    ("Objekt / týden", "Min. nocí: 7", 7),
    ("Objekt / víkend", "Min. nocí: 2, cena za 1 chalupu", 2),
    ("Objekt / víkend", "", 2),
    ("Objekt / pobyt", "Min. nocí: 3, objekt na 3 noci", 3),
])
def test_unit_nights(unit, note, expected):
    assert unit_info(unit, note)[0] == expected


def test_canonical_unknown_amenity_passes_through():
    assert canonical_amenities(["  Koupací   SUD ", "sauna", "sauna", ""]) == ["koupací sud", "sauna"]
    assert canonical_amenities(None) == []


# --- pasti zjištěné na skutečných datech (1 293 nabídek, Krkonoše) -------------------
def _cs(cenik, capacity=12, price=None, unit=""):
    return build_price({"source": "cs-chalupy.cz", "capacity": capacity, "price": price,
                        "price_unit": unit}, {"cenik": cenik})


def _row(sezona, cena, typ, poznamka=""):
    return {"sezona": sezona, "cena_hodnota": cena, "typ": typ, "poznamka": poznamka}


def test_zero_price_on_request_is_ignored():
    """5C-106: Silvestr 0 Kč "cena na dotaz" nesmí udělat cenu od 0."""
    out = _cs([_row("Sezóna LÉTO", 3950.0, "Objekt / noc"),
               _row("SILVESTR", 0.0, "Objekt / noc", "cena na dotaz"),
               _row("Sezóna ZIMA", 6950.0, "Objekt / noc")], capacity=30)
    assert (out["price_per_night_from"], out["price_per_night_to"]) == (3950, 6950)


def test_per_person_weekend_price_is_not_multiplied():
    """5C-058: "Osoba / víkend" 15 000 × 12 osob by dalo nesmyslných 90 000 Kč za noc."""
    out = _cs([_row("Sezóna LÉTO", 30000.0, "Objekt / týden"),
               _row("Sezóna ZIMA", 15000.0, "Osoba / víkend")], capacity=12)
    assert (out["price_per_night_from"], out["price_per_night_to"]) == (4286, 4286)
    assert out["price_estimated"] is False


def test_room_prices_do_not_drag_object_price_down():
    """5C-218: pokoj za 1 590 Kč nesmí být "od" cena celé chalupy."""
    out = _cs([_row("Sezóna LÉTO", 45990.0, "Objekt / týden", "Min. nocí: 7"),
               _row("Mimosezóna", 19990.0, "Objekt / víkend", "Min. nocí: 2"),
               _row("Mimosezóna", 1590.0, "3 - lůžk. pokoj / noc", "Min. nocí: 2")], capacity=22)
    assert out["price_per_night_from"] == 6570        # 45 990 / 7
    assert out["price_per_night_to"] == 9995          # 19 990 / 2
    assert out["price_note"] is None


def test_person_per_night_is_used_only_when_no_object_rows():
    """5C-072: jen "Osoba / noc" (děti a přistýlky se ignorují) -> odhad × kapacita."""
    out = _cs([_row("Sezóna LÉTO", 430.0, "Osoba / noc", "Platí při pobytu na 7 nocí."),
               _row("Sezóna LÉTO", 330.0, "Dítě / noc", "Dítě 6 - 12 let"),
               _row("Sezóna LÉTO", 300.0, "Dítě / pobyt", "Dítě do 2 let"),
               _row("Sezóna ZIMA", 350.0, "Osoba / noc")], capacity=18)
    assert (out["price_per_night_from"], out["price_per_night_to"]) == (6300, 7740)
    assert out["price_estimated"] is True


def test_object_rows_beat_person_rows():
    out = _cs([_row("A", 7000.0, "Objekt / noc"), _row("B", 300.0, "Osoba / noc")], capacity=20)
    assert (out["price_per_night_from"], out["price_per_night_to"]) == (7000, 7000)
    assert out["price_estimated"] is False


def test_only_apartment_and_room_rows_are_flagged():
    out = _cs([_row("A", 1800.0, "Apartmán / noc"), _row("B", 1200.0, "Pokoj / noc")])
    assert (out["price_per_night_from"], out["price_per_night_to"]) == (1200, 1800)
    assert "apartmán" in out["price_note"] and "pokoj" in out["price_note"]


def test_rows_with_empty_type_are_skipped():
    out = _cs([_row("A", 5000.0, ""), _row("B", 4000.0, "Objekt / noc")])
    assert out["price_per_night_from"] == 4000


def test_implausibly_low_price_is_ignored():
    """5C-005: "Velikonoce 20 Kč / pobyt, min. 4 noci" je překlep na portálu (5 Kč za noc)."""
    out = _cs([_row("Mimosezóna", 30000.0, "Objekt / týden", "Min. nocí: 7"),
               _row("Velikonoce", 20.0, "Objekt / pobyt", "Min. nocí: 4")], capacity=14)
    assert out["price_per_night_from"] == 4286


def test_real_world_amenity_variants():
    assert canonical_amenities(["částečně oplocený objekt", "oploceno"]) == ["oplocení"]
    assert canonical_amenities(["dětský kout (hračky)"]) == ["dětský kout (hračky)", "pro děti"]
