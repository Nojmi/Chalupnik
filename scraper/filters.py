from scraper.models import Listing


def matches(listing: Listing, criteria: dict) -> bool:
    """
    Return True if *listing* satisfies all non-empty criteria.

    Missing fields on the listing (None) are treated as a pass —
    they do NOT block the listing from appearing in results.
    """
    location = criteria.get("location")
    if location and listing.location is not None:
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
