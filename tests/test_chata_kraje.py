import json

import pytest

from scraper import chata_kraje
from scraper.profiles import chata_cz
from scraper.store import kraj_of, load_store, save_store, build_index


def _listing(code, **extra):
    return {"source": "chata.cz", "title": f"Chata {code}", "location": "Obec, Region", "url": f"https://www.chata.cz/chalupa/x/{code}/",
            "capacity": 6, "bedrooms": 3, "price": None, "price_unit": None, "amenities": [], "image_url": None,
            "entire_property": True, "likely_apartment": False, "raw_extra": {"code": code, **extra}}


def _store(tmp_path, name, listings):
    from scraper.store import empty_store
    from scraper.normalize import normalize_listing
    st = empty_store(name, name)
    st["listings"] = [{"first_seen": "2026-10-14", "last_seen": "2026-10-14", "seen_in_last_run": True,
                       **normalize_listing(l, "2026-10-14")} for l in listings]
    save_store(tmp_path / f"{name}.json", st)


def test_kraj_of_prefers_gps_then_hint():
    assert kraj_of({"gps": {"lat": 49.7475, "lon": 13.3776}, "raw_extra": {"kraj_hint": "Jihočeský"}}) == "Plzeňský"
    assert kraj_of({"gps": None, "raw_extra": {"kraj_hint": "Plzeňský"}}) == "Plzeňský"
    assert kraj_of({"gps": None, "raw_extra": {}}) is None


def test_annotate_sets_kraj_and_counts_in_index(tmp_path):
    _store(tmp_path, "sumava", [_listing("CZ1"), _listing("CZ2")])
    assert chata_kraje.annotate_existing(tmp_path, {"CZ1": "Plzeňský"}) == 1
    s = load_store(tmp_path / "sumava.json")
    by = {x["id"]: x for x in s["listings"]}
    assert by["chata.cz:CZ1"]["kraj"] == "Plzeňský"
    assert by["chata.cz:CZ2"]["kraj"] is None
    assert build_index(tmp_path)["regions"][0]["kraje"] == {"Plzeňský": 1}
    assert chata_kraje.annotate_existing(tmp_path, {"CZ1": "Plzeňský"}) == 0       # podruhé beze změny


def test_gap_goes_to_ostatni_and_is_dropped_once_covered(tmp_path):
    _store(tmp_path, "sumava", [_listing("CZ1")])
    index = {"CZ1": "Plzeňský", "CZ9": "Plzeňský"}
    assert chata_kraje.covered_codes(tmp_path) == {"CZ1"}
    n, removed = chata_kraje.fill_gap(tmp_path, [_listing("CZ9")], index)
    assert (n, removed) == (1, 0)
    o = load_store(tmp_path / "ostatni.json")
    assert o["listings"][0]["kraj"] == "Plzeňský" and o["listings"][0]["seen_in_last_run"]
    # CZ9 mezitím pokryla oblast -> z ostatních zmizí (ne "zmizelá", rovnou pryč, ať se nezdvojuje)
    _store(tmp_path, "jizni-cechy", [_listing("CZ9")])
    n, removed = chata_kraje.fill_gap(tmp_path, [], index)
    assert (n, removed) == (0, 1)
    # ostatni se do covered nepočítá (jinak by se vlastní nabídky nikdy neobnovily)
    assert chata_kraje.covered_codes(tmp_path) == {"CZ1", "CZ9"}


def test_failed_fetch_does_not_mark_ostatni_missing(tmp_path):
    index = {"CZ9": "Plzeňský"}
    chata_kraje.fill_gap(tmp_path, [_listing("CZ9")], index)
    chata_kraje.fill_gap(tmp_path, [], index, merge=False)
    assert load_store(tmp_path / "ostatni.json")["listings"][0]["seen_in_last_run"] is True


class _R:
    def __init__(self, data): self._d = data
    def raise_for_status(self): pass
    def json(self): return self._d


def test_resolve_kraj_exact_match_type_2(monkeypatch):
    items = [{"LocationId": 5, "LocationType": 4, "Name": "Plzeň"},
             {"LocationId": 11, "LocationType": 2, "Name": "kraj Plzeňský"}]
    monkeypatch.setattr(chata_cz.requests, "get", lambda *a, **k: _R(items))
    assert chata_cz.resolve_kraj("Plzeňský") == (11, 2, "kraj Plzeňský")


def test_resolve_kraj_not_found_returns_none(monkeypatch, capsys):
    monkeypatch.setattr(chata_cz.requests, "get", lambda *a, **k: _R([{"LocationId": 3, "LocationType": 6, "Name": "Plzeňsko"}]))
    assert chata_cz.resolve_kraj("Plzeňský") is None
    assert "nenalezena" in capsys.readouterr().out


def test_all_kraje_match_scraper_kraj_names():
    from scraper.kraj import SHORT
    assert set(chata_cz.KRAJE) == set(SHORT.values())
