"""Určení kraje nabídky z GPS souřadnic.

Hranice krajů jsou ve `scraper/kraje_gps.json` (zjednodušené, přesnost ~200 m,
zdroj: github.com/siwekm/czech-geojson, data INSPIRE / ČÚZK). Slouží jen
pipeline; web dostává už hotové pole `kraj`.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

# Krátké názvy shodné s `short` v docs/data/mapa-cr.json (web podle nich páruje mapu)
SHORT = {
    "CZ0100000000": "Praha", "CZ0200000000": "Středočeský", "CZ0310000000": "Jihočeský",
    "CZ0320000000": "Plzeňský", "CZ0410000000": "Karlovarský", "CZ0420000000": "Ústecký",
    "CZ0510000000": "Liberecký", "CZ0520000000": "Královéhradecký", "CZ0530000000": "Pardubický",
    "CZ0630000000": "Vysočina", "CZ0640000000": "Jihomoravský", "CZ0710000000": "Olomoucký",
    "CZ0720000000": "Zlínský", "CZ0800000000": "Moravskoslezský",
}


@lru_cache(maxsize=1)
def _regions() -> list:
    path = Path(__file__).with_name("kraje_gps.json")
    out = []
    for k in json.loads(path.read_text(encoding="utf-8")):
        rings = []
        for ring in k["rings"]:
            xs = [p[0] for p in ring]
            ys = [p[1] for p in ring]
            rings.append((min(xs), min(ys), max(xs), max(ys), ring))
        out.append((SHORT[k["id"]], rings))
    return out


def _inside(lon: float, lat: float, ring: list) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def kraj_for(gps: Optional[dict]) -> Optional[str]:
    """Krátký název kraje (např. "Liberecký") nebo None, když bod není v ČR."""
    if not isinstance(gps, dict):
        return None
    try:
        lat, lon = float(gps["lat"]), float(gps["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    for name, rings in _regions():          # Praha je první, takže přebije Středočeský
        for x0, y0, x1, y1, ring in rings:
            if x0 <= lon <= x1 and y0 <= lat <= y1 and _inside(lon, lat, ring):
                return name
    return None
