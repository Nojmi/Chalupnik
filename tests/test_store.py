"""Testy slučování, čerstvosti a indexu regionů."""
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scraper import store as st

FIXTURE = Path(__file__).parent / "fixtures" / "run_sample.json"


@pytest.fixture()
def run():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def fresh_store():
    return st.empty_store("krkonose", "Krkonoše")


def listing_by_id(store, lid):
    return next(x for x in store["listings"] if x["id"] == lid)


def synthetic_run(source, n, when="2026-09-01T10:00:00+00:00", errors=None):
    """Umělý běh s n nabídkami jednoho zdroje."""
    return {
        "generated_at": when,
        "criteria": {"location": "Krkonoše", "min_capacity": None, "min_bedrooms": None,
                     "max_price": None, "amenities": []},
        "errors": errors or [],
        "listings": [{"source": source, "title": f"Chata {i}", "location": "X",
                      "url": f"https://www.e-chalupy.cz/x-o{i}", "capacity": 8, "bedrooms": 3,
                      "price": 3000.0, "price_unit": "objekt za noc", "amenities": [],
                      "image_url": None, "entire_property": None, "likely_apartment": False,
                      "raw_extra": {"id": i}} for i in range(n)],
    }


# --- první naplnění -----------------------------------------------------------
def test_first_merge_adds_everything(run):
    s = fresh_store()
    rep = st.merge_run(s, run)
    assert (rep.added, rep.updated, rep.marked_missing) == (6, 0, 0)
    assert len(s["listings"]) == 6
    assert all(x["first_seen"] == x["last_seen"] == "2026-07-29" for x in s["listings"])
    assert all(x["seen_in_last_run"] for x in s["listings"])
    assert all(s["sources_updated"][k] == run["generated_at"] for k in st.ALL_SOURCES)
    assert s["last_updated"] == run["generated_at"]


def test_merge_is_idempotent(run):
    s = fresh_store()
    st.merge_run(s, run)
    snapshot = copy.deepcopy(s["listings"])
    rep = st.merge_run(s, run)
    assert (rep.added, rep.updated, rep.marked_missing) == (0, 6, 0)
    assert s["listings"] == snapshot


# --- zmizelé nabídky a ceny -----------------------------------------------------
def test_missing_listing_is_kept_but_flagged(run):
    s = fresh_store()
    st.merge_run(s, run)
    run2 = copy.deepcopy(run)
    run2["generated_at"] = "2026-08-20T09:00:00+00:00"
    run2["listings"] = [x for x in run2["listings"] if x["title"] != "Chalupa Máca"]
    rep = st.merge_run(s, run2)
    gone = listing_by_id(s, "chata.cz:CZ6516")
    assert rep.marked_missing == 1 and len(s["listings"]) == 6
    assert gone["seen_in_last_run"] is False
    assert gone["last_seen"] == "2026-07-29" and gone["first_seen"] == "2026-07-29"
    kept = listing_by_id(s, "chata.cz:CZ8633")
    assert kept["seen_in_last_run"] is True and kept["last_seen"] == "2026-08-20"
    assert kept["first_seen"] == "2026-07-29"


def test_returning_listing_becomes_seen_again(run):
    s = fresh_store()
    st.merge_run(s, run)
    run2 = copy.deepcopy(run)
    run2["generated_at"] = "2026-08-20T09:00:00+00:00"
    run2["listings"] = run2["listings"][:3]
    st.merge_run(s, run2)
    run3 = copy.deepcopy(run)
    run3["generated_at"] = "2026-09-05T09:00:00+00:00"
    st.merge_run(s, run3)
    assert all(x["seen_in_last_run"] for x in s["listings"])


def test_old_price_survives_when_new_run_has_no_price(run):
    """chata.cz často cenu nevrátí ("Termín je obsazen") – stará známá cena se nesmí ztratit."""
    s = fresh_store()
    st.merge_run(s, run)
    run2 = copy.deepcopy(run)
    run2["generated_at"] = "2026-08-20T09:00:00+00:00"
    for x in run2["listings"]:
        if x["title"] == "Chalupa Máca":
            x["price"], x["price_unit"] = None, ""
    st.merge_run(s, run2)
    m = listing_by_id(s, "chata.cz:CZ6516")
    assert m["price_per_night_from"] == 4749
    assert m["price_as_of"] == "2026-07-29"            # ukazuje stáří ceny, ne stáří běhu
    assert m["price_term"] == {"from": "2026-08-01", "to": "2026-08-08"}
    assert m["last_seen"] == "2026-08-20"


def test_new_price_replaces_old(run):
    s = fresh_store()
    st.merge_run(s, run)
    run2 = copy.deepcopy(run)
    run2["generated_at"] = "2026-08-20T09:00:00+00:00"
    for x in run2["listings"]:
        if x["title"] == "Roubenka Jílové":
            x["price"] = 3500.0
    st.merge_run(s, run2)
    r = listing_by_id(s, "e-chalupy.cz:542")
    assert r["price_per_night_from"] == 3500 and r["price_as_of"] == "2026-08-20"


# --- zdroje: chyby a částečné běhy ---------------------------------------------------
def test_failed_source_is_left_untouched(run):
    s = fresh_store()
    st.merge_run(s, run)
    before = copy.deepcopy(listing_by_id(s, "chata.cz:CZ8633"))
    run2 = copy.deepcopy(run)
    run2["generated_at"] = "2026-08-20T09:00:00+00:00"
    run2["errors"] = [{"profile": "scraper.profiles.chata_cz", "error": "HTTP 500"}]   # tvar z main.py
    run2["listings"] = [x for x in run2["listings"] if x["source"] != "chata.cz"]
    rep = st.merge_run(s, run2)
    assert listing_by_id(s, "chata.cz:CZ8633") == before
    assert listing_by_id(s, "chata.cz:CZ8633")["seen_in_last_run"] is True
    assert s["sources_updated"]["chata.cz"] == "2026-07-29T16:55:21.185979+00:00"
    assert s["sources_updated"]["e-chalupy.cz"] == "2026-08-20T09:00:00+00:00"
    assert any("chata.cz" in w for w in rep.warnings)


def test_partial_run_with_sources_only_touches_those_sources(run):
    """Lokální běh jen e-chalupy.cz nesmí označit chata.cz/cs-chalupy.cz jako zmizelé."""
    s = fresh_store()
    st.merge_run(s, run)
    run2 = copy.deepcopy(run)
    run2["generated_at"] = "2026-08-20T09:00:00+00:00"
    run2["listings"] = [x for x in run2["listings"] if x["source"] == "e-chalupy.cz"]
    st.merge_run(s, run2, sources=("e-chalupy.cz",))
    assert all(x["seen_in_last_run"] for x in s["listings"])
    assert s["sources_updated"]["e-chalupy.cz"].startswith("2026-08-20")
    assert s["sources_updated"]["chata.cz"].startswith("2026-07-29")


def test_listings_from_unlisted_sources_are_ignored(run):
    s = fresh_store()
    st.merge_run(s, run, sources=("e-chalupy.cz",))
    assert {x["source"] for x in s["listings"]} == {"e-chalupy.cz"}


def test_suspiciously_small_run_does_not_mark_missing():
    """Tichý fallback / blokace: běh vrátí 5 nabídek místo 40 – nic se nesmí 'smazat'."""
    s = fresh_store()
    st.merge_run(s, synthetic_run("e-chalupy.cz", 40))
    rep = st.merge_run(s, synthetic_run("e-chalupy.cz", 5, when="2026-09-10T10:00:00+00:00"))
    active = [x for x in s["listings"] if x["seen_in_last_run"]]
    assert len(active) == 40 and rep.marked_missing == 0
    assert s["sources_updated"]["e-chalupy.cz"].startswith("2026-09-01")   # nepovažuje se za aktualizovaný
    assert any("jen 5 nabídek oproti 40" in w for w in rep.warnings)


def test_small_region_dropping_is_not_suspicious():
    """Pod prahem MIN_BASELINE se běžné kolísání bere jako normální."""
    s = fresh_store()
    st.merge_run(s, synthetic_run("e-chalupy.cz", 10))
    rep = st.merge_run(s, synthetic_run("e-chalupy.cz", 2, when="2026-09-10T10:00:00+00:00"))
    assert rep.marked_missing == 8 and not rep.warnings


# --- ochrany --------------------------------------------------------------------
def test_filtered_run_is_rejected(run):
    s = fresh_store()
    run["criteria"]["min_capacity"] = 10
    with pytest.raises(st.StoreError):
        st.merge_run(s, run)
    assert s["listings"] == []


def test_run_without_location_is_rejected(run):
    run["criteria"]["location"] = ""
    with pytest.raises(st.StoreError):
        st.region_of(run)


def test_prune_removes_long_gone_listings():
    s = fresh_store()
    st.merge_run(s, synthetic_run("e-chalupy.cz", 4, when="2026-01-01T10:00:00+00:00"))
    run2 = synthetic_run("e-chalupy.cz", 3, when="2026-09-01T10:00:00+00:00")   # chybí Chata 3
    rep = st.merge_run(s, run2)
    assert rep.pruned == 1 and len(s["listings"]) == 3


# --- čerstvost ---------------------------------------------------------------------
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("days,status", [(0, "fresh"), (14, "fresh"), (15, "aging"),
                                         (30, "aging"), (31, "stale"), (200, "stale")])
def test_freshness_thresholds(days, status):
    ts = (NOW - timedelta(days=days)).isoformat()
    f = st.freshness(ts, now=NOW)
    assert f["status"] == status and f["age_days"] == days


def test_freshness_empty():
    assert st.freshness(None, now=NOW) == {"status": "empty", "age_days": None}


# --- soubory, index ------------------------------------------------------------------
def test_slugify():
    assert st.slugify("Krkonoše") == "krkonose"
    assert st.slugify("Český ráj") == "cesky-raj"
    assert st.slugify("  Jizerské hory ") == "jizerske-hory"


def test_merge_file_roundtrip_and_index(tmp_path, run):
    run_path = tmp_path / "latest.json"
    run_path.write_text(json.dumps(run, ensure_ascii=False), encoding="utf-8")
    data = tmp_path / "data"
    rep = st.merge_file(run_path, data)
    assert rep.added == 6
    f = data / "krkonose.json"
    assert f.exists() and not list(data.glob("*.tmp"))
    text = f.read_text(encoding="utf-8")
    assert "Krkonoše" in text and "\\u" not in text             # čitelná čeština, ne escapy
    idx = json.loads((data / "index.json").read_text(encoding="utf-8"))
    assert idx["regions"][0]["region"] == "krkonose"
    assert idx["regions"][0]["listing_count"] == idx["regions"][0]["active_count"] == 6
    assert "status" not in idx["regions"][0]                    # čerstvost počítá až web


def test_dry_run_writes_nothing(tmp_path, run):
    run_path = tmp_path / "latest.json"
    run_path.write_text(json.dumps(run, ensure_ascii=False), encoding="utf-8")
    st.merge_file(run_path, tmp_path / "data", dry_run=True)
    assert not (tmp_path / "data").exists()


def test_saved_listings_sorted_by_id_for_stable_diffs(tmp_path, run):
    run_path = tmp_path / "latest.json"
    run_path.write_text(json.dumps(run, ensure_ascii=False), encoding="utf-8")
    st.merge_file(run_path, tmp_path / "data")
    ids = [x["id"] for x in st.load_store(tmp_path / "data" / "krkonose.json")["listings"]]
    assert ids == sorted(ids)


def test_cli_status_and_errors(tmp_path, run, capsys):
    run_path = tmp_path / "latest.json"
    run_path.write_text(json.dumps(run, ensure_ascii=False), encoding="utf-8")
    assert st.main(["merge", str(run_path), "--data-dir", str(tmp_path / "d")]) == 0
    assert st.main(["status", "--data-dir", str(tmp_path / "d")]) == 0
    assert "Krkonoše" in capsys.readouterr().out
    run["criteria"]["max_price"] = 5000
    run_path.write_text(json.dumps(run, ensure_ascii=False), encoding="utf-8")
    assert st.main(["merge", str(run_path), "--data-dir", str(tmp_path / "d")]) == 2
    assert st.main(["merge", str(run_path), "--sources", "neco.cz"]) == 2


@pytest.mark.parametrize("errors,expected", [
    ([{"profile": "scraper.profiles.e_chalupy", "error": "boom"}], {"e-chalupy.cz"}),
    ([{"profile": "scraper.profiles.cs_chalupy", "error": "x"},
      {"profile": "scraper.profiles.chata_cz", "error": "y"}], {"cs-chalupy.cz", "chata.cz"}),
    (["[chata.cz] HTTP 500"], {"chata.cz"}),
    ([], set()),
    (None, set()),
    ([{"profile": "scraper.profiles.neznamy", "error": "x"}], set()),
])
def test_failed_sources_formats(errors, expected):
    assert st.failed_sources(errors) == expected


# --- update_database (volá se z main.py, nesmí nikdy shodit běh) -----------------------
def _write_run(tmp_path, run):
    p = tmp_path / "latest.json"
    p.write_text(json.dumps(run, ensure_ascii=False), encoding="utf-8")
    return p


def test_update_database_success(tmp_path, run, capsys):
    rep = st.update_database(_write_run(tmp_path, run), tmp_path / "data")
    assert rep.added == 6 and (tmp_path / "data" / "krkonose.json").exists()
    assert "region krkonose" in capsys.readouterr().out


def test_update_database_skips_filtered_run_without_raising(tmp_path, run, capsys):
    run["criteria"]["amenities"] = ["bazén"]
    assert st.update_database(_write_run(tmp_path, run), tmp_path / "data") is None
    assert "[DATABASE] přeskočeno" in capsys.readouterr().out
    assert not (tmp_path / "data").exists()


def test_update_database_skips_run_without_location(tmp_path, run, capsys):
    run["criteria"]["location"] = None
    assert st.update_database(_write_run(tmp_path, run), tmp_path / "data") is None
    assert "lokalit" in capsys.readouterr().out


def test_update_database_survives_corrupt_region_file(tmp_path, run, capsys):
    data = tmp_path / "data"
    data.mkdir()
    (data / "krkonose.json").write_text("{ rozbitý json", encoding="utf-8")
    assert st.update_database(_write_run(tmp_path, run), data) is None
    assert "[DATABASE] chyba" in capsys.readouterr().err
    assert (data / "krkonose.json").read_text(encoding="utf-8") == "{ rozbitý json"   # nepřepsáno
