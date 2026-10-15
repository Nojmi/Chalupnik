from scraper.dedupe import find_groups, title_key, obec_key


def L(id_, source, title="Chata", loc="Obec, Region", cap=8, bed=3, gps=None):
    return {"id": id_, "source": source, "title": title, "location": loc, "capacity": cap, "bedrooms": bed, "gps": gps}


G = {"lat": 50.0, "lon": 15.0}


def test_gps_pair_across_portals_merges():
    g = find_groups([L("e:1", "e-chalupy.cz", "Chata A", gps=G), L("c:1", "cs-chalupy.cz", "Úplně jiný název", gps={"lat": 50.0004, "lon": 15.0004})])
    assert g == [["e:1", "c:1"]]


def test_different_capacity_or_far_away_does_not_merge():
    assert find_groups([L("e:1", "e-chalupy.cz", gps=G), L("c:1", "cs-chalupy.cz", cap=9, gps=G)]) == []
    assert find_groups([L("e:1", "e-chalupy.cz", gps=G), L("c:1", "cs-chalupy.cz", gps={"lat": 50.01, "lon": 15.0})]) == []


def test_bedrooms_mismatch_blocks_unknown_allows():
    assert find_groups([L("e:1", "e-chalupy.cz", bed=2, gps=G), L("c:1", "cs-chalupy.cz", bed=3, gps=G)]) == []
    assert find_groups([L("e:1", "e-chalupy.cz", bed=None, gps=G), L("c:1", "cs-chalupy.cz", bed=3, gps=G)]) == [["e:1", "c:1"]]


def test_ambiguous_same_portal_units_not_merged():
    """Dva apartmány téhož portálu na jednom místě se stejnou kapacitou: nevíme, který je který."""
    items = [L("e:1", "e-chalupy.cz", gps=G), L("e:2", "e-chalupy.cz", gps=G), L("c:1", "cs-chalupy.cz", gps=G)]
    assert find_groups(items) == []


def test_chata_matches_by_title_obec_capacity():
    items = [L("e:1", "e-chalupy.cz", "Chata Monika - Adršpach", "Adršpach, Východní Čechy", 8, 3, G),
             L("h:1", "chata.cz", "Chata Monika", "Adršpach, Broumovsko", 8, 3)]
    assert find_groups(items) == [["e:1", "h:1"]]


def test_chata_different_place_or_capacity_not_merged():
    e = L("e:1", "e-chalupy.cz", "Chata Babeta", "Jevišovice, Jižní Morava", 12, 4, G)
    assert find_groups([e, L("h:1", "chata.cz", "Chata Babeta", "Teplice nad Metují, Broumovsko", 12, 4)]) == []
    assert find_groups([e, L("h:1", "chata.cz", "Chata Babeta", "Jevišovice, Jižní Morava", 6, 4)]) == []


def test_group_never_has_two_of_same_portal():
    items = [L("e:1", "e-chalupy.cz", "Chata X", "Obec, A", 8, 3, G), L("c:1", "cs-chalupy.cz", "Chata X", "Obec, A", 8, 3, G),
             L("h:1", "chata.cz", "Chata X", "Obec, A", 8, 3), L("h:2", "chata.cz", "Chata X", "Obec, A", 8, 3)]
    for grp in find_groups(items):
        assert len(grp) == len({i.split(":")[0] for i in grp})


def test_keys():
    assert title_key("Chata Monika - Adršpach") == "chata monika"
    assert title_key("Chalupa U Bikárů") == title_key("chalupa u bikaru")
    assert obec_key("Čeřínek, Vysočina") == "cerinek"
