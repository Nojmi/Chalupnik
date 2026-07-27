import re
import unicodedata

from scraper.models import Listing


def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def matches(listing: Listing, criteria: dict) -> bool:
    """
    Return True if *listing* satisfies all non-empty criteria.

    Missing fields on the listing (None) are treated as a pass —
    they do NOT block the listing from appearing in results.
    """
    location = criteria.get("location")
    if location and listing.location is not None:
        area_slug = listing.raw_extra.get("area2_slug")
        if area_slug:
            # Profile resolved an exact region/area code (e.g. e-chalupy.cz's
            # area2) - compare slugs precisely instead of a fuzzy substring
            # match against the human-readable location text.
            if _slugify(location) != area_slug:
                return False
        elif listing.raw_extra.get("location_prefiltered"):
            # Profile already scoped the fetch by location server-side but
            # didn't give us a slug to compare exactly - trust it.
            pass
        else:
            if location.lower() not in listing.location.lower():
                return False

    min_capacity = criteria.get("min_capacity")
    if min_capacity and listing.capacity is not None:
        if listing.capacity < int(min_capacity):
            return False

    min_bedrooms = criteria.get("min_bedrooms")
    if min_bedrooms and listing.bedrooms is not None:
        if listing.bedrooms < int(min_bedrooms):
            return False

    max_price = criteria.get("max_price")
    if max_price and listing.price is not None:
        if listing.price > float(max_price):
            return False

    required_amenities = criteria.get("amenities") or []
    if required_amenities and listing.amenities is not None:
        listing_amenities_lower = [a.lower() for a in listing.amenities]
        for req in required_amenities:
            if req.lower() not in listing_amenities_lower:
                return False

    return True


def filter_listings(listings: list[Listing], criteria: dict) -> list[Listing]:
    return [l for l in listings if matches(l, criteria)]
