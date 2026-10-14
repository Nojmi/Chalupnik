from scraper.filters import matches
from scraper.models import Listing


def _l(slug, prefiltered):
    extra = {"area2_slug": slug}
    if prefiltered:
        extra["location_prefiltered"] = True
    return Listing(source="e-chalupy.cz", title="x", location="Obec, Podoblast", url="u", raw_extra=extra)


def test_prefiltered_listing_from_subarea_is_kept():
    assert matches(_l("sumava-bavorsky-les", True), {"location": "Šumava"})


def test_without_prefilter_slug_must_match():
    assert not matches(_l("sumava-bavorsky-les", False), {"location": "Šumava"})
    assert matches(_l("sumava", False), {"location": "Šumava"})
