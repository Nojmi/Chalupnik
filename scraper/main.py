import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from scraper.filters import filter_listings
from scraper.profiles import ALL_PROFILES


def read_criteria() -> dict:
    amenities_raw = os.environ.get("CRIT_AMENITIES", "")
    amenities = [a.strip() for a in amenities_raw.split(",") if a.strip()]

    return {
        "location": os.environ.get("CRIT_LOCATION", "").strip() or None,
        "min_capacity": os.environ.get("CRIT_MIN_CAPACITY", "").strip() or None,
        "min_bedrooms": os.environ.get("CRIT_MIN_BEDROOMS", "").strip() or None,
        "max_price": os.environ.get("CRIT_MAX_PRICE", "").strip() or None,
        "amenities": amenities,
        "date_from": os.environ.get("CRIT_DATE_FROM", "").strip() or None,
        "date_to": os.environ.get("CRIT_DATE_TO", "").strip() or None,
    }


def main() -> None:
    criteria = read_criteria()
    all_listings = []
    errors = []

    for profile_fn in ALL_PROFILES:
        name = getattr(profile_fn, "__module__", str(profile_fn))
        try:
            results = profile_fn(criteria)
            all_listings.extend(results)
        except Exception as exc:
            errors.append({"profile": name, "error": str(exc)})
            print(f"[ERROR] {name}: {exc}", file=sys.stderr)

    matched = filter_listings(all_listings, criteria)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "criteria": criteria,
        "total_found": len(all_listings),
        "total_matched": len(matched),
        "errors": errors,
        "listings": [l.to_dict() for l in matched],
    }

    out_path = Path(__file__).parent.parent / "results" / "latest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(matched)} listings to {out_path}")


if __name__ == "__main__":
    main()
