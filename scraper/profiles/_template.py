# HOW TO ADD A NEW PORTAL
# ========================
# 1. Make screenshots of:
#    a) The search/filter form (inputs, selects, checkboxes, date pickers)
#    b) A listing results page (card/row structure, pagination)
#    c) The raw HTML of both pages (DevTools → Elements or View Source)
#
# 2. Copy this file to scraper/profiles/<portal_slug>.py
#    e.g. scraper/profiles/chatacentrum.py
#
# 3. Fill in BASE_URL and implement search() by:
#    - Sending the appropriate GET/POST request with criteria mapped to the
#      portal's own query parameters (check the form's action and field names)
#    - Parsing the HTML with BeautifulSoup to extract Listing fields
#    - Handling pagination (follow "next page" links until exhausted or a
#      reasonable page cap, e.g. 10 pages)
#
# 4. Register the profile in scraper/profiles/__init__.py (see that file).
#
# 5. Test locally:
#    CRIT_LOCATION="Šumava" python scraper/main.py
#
# IMPORTANT: This file is intentionally NOT registered in ALL_PROFILES.
# It is only a reference template and will never be called by the scraper.

from scraper.models import Listing

BASE_URL = "https://example-portal.cz"


def search(criteria: dict) -> list[Listing]:
    """
    Fetch listings from the portal matching *criteria*.

    criteria keys (all optional, may be None or empty string):
        location       str   – free-text location / region
        min_capacity   int   – minimum number of guests
        min_bedrooms   int   – minimum number of bedrooms
        max_price      float – maximum price per night in CZK
        amenities      list  – amenity slugs the listing must have
        date_from      str   – ISO date "YYYY-MM-DD"
        date_to        str   – ISO date "YYYY-MM-DD"

    Returns a list of Listing objects (unfiltered — scraper/filters.py
    handles client-side filtering after all profiles have been queried).
    """
    listings: list[Listing] = []

    # TODO: map criteria to portal-specific query parameters
    params = {
        "location": criteria.get("location", ""),
        # "guests": criteria.get("min_capacity"),
        # "from":   criteria.get("date_from"),
        # "to":     criteria.get("date_to"),
    }

    # TODO: fetch and parse pages
    # import requests
    # from bs4 import BeautifulSoup
    # resp = requests.get(f"{BASE_URL}/search", params=params, timeout=15)
    # resp.raise_for_status()
    # soup = BeautifulSoup(resp.text, "lxml")
    # for card in soup.select(".listing-card"):
    #     listings.append(Listing(
    #         source="example-portal",
    #         title=card.select_one("h2").get_text(strip=True),
    #         location=card.select_one(".location").get_text(strip=True),
    #         url=BASE_URL + card.select_one("a")["href"],
    #         capacity=int(card.select_one(".guests").get_text(strip=True)),
    #         ...
    #     ))

    return listings
