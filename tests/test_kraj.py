from scraper.kraj import kraj_for


def test_known_points():
    assert kraj_for({"lat": 50.0755, "lon": 14.4378}) == "Praha"
    assert kraj_for({"lat": 50.6104, "lon": 15.6096}) in ("Královéhradecký", "Liberecký")
    assert kraj_for({"lat": 49.7475, "lon": 13.3776}) == "Plzeňský"          # Plzeň
    assert kraj_for({"lat": 49.31, "lon": 14.15}) == "Jihočeský"             # Písek
    assert kraj_for({"lat": 49.1951, "lon": 16.6068}) == "Jihomoravský"      # Brno
    assert kraj_for({"lat": 49.5938, "lon": 17.2509}) == "Olomoucký"         # Olomouc


def test_outside_or_missing():
    assert kraj_for(None) is None
    assert kraj_for({"lat": 48.2, "lon": 16.37}) is None                     # Vídeň
    assert kraj_for({"lat": "x", "lon": 1}) is None


def test_index_ignores_foreign_json(tmp_path):
    """Ve složce docs/data leží i mapa-cr.json – index se z ní nesmí pokusit číst oblast."""
    import json
    from scraper.store import build_index
    (tmp_path / "mapa-cr.json").write_text(json.dumps({"w": 600, "kraje": []}), encoding="utf-8")
    (tmp_path / "krkonose.json").write_text(json.dumps({
        "region": "krkonose", "region_label": "Krkonoše", "listings": [
            {"id": "a", "gps": {"lat": 50.6104, "lon": 15.6096}, "seen_in_last_run": True}]}), encoding="utf-8")
    idx = build_index(tmp_path)
    assert [r["region"] for r in idx["regions"]] == ["krkonose"]
    assert sum(idx["regions"][0]["kraje"].values()) == 1


def test_cs_chalupy_alias_jizni_morava():
    from scraper.profiles.cs_chalupy import _resolve_region_slug
    regs = [{"name": "Jižní a střední Morava", "slug": "jizni-a-stredni-morava"},
            {"name": "Jižní Čechy", "slug": "jizni-cechy"}]
    assert _resolve_region_slug("Jižní Morava", regs) == "jizni-a-stredni-morava"
    assert _resolve_region_slug("Jižní Čechy", regs) == "jizni-cechy"
