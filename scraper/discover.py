"""Zjištění všech oblastí na portálech a porovnání s naší databází.

Nic nestahuje ani nepřepisuje, jen čte a vypíše tabulky (do logu i do
GITHUB_STEP_SUMMARY). Účel: nemuset oblasti vyjmenovávat ručně - běh sám
najde, které oblasti portály mají a které nám v databázi chybí.

Spuštění: python -m scraper.discover  (workflow "Discover areas")
"""

import collections
import json
import os
import sys
from pathlib import Path

import requests

from scraper.profiles import chata_cz, cs_chalupy, e_chalupy

DATA_DIR = Path(__file__).parent.parent / "docs" / "data"
# Rozsah kódů area_NNNNN k prozkoumání (naše známé jsou 19640-19655).
E_AREA_RANGE = range(19600, 19700)


def load_db() -> dict[str, list[dict]]:
    out = {}
    for f in sorted(DATA_DIR.glob("*.json")):
        if f.name in ("index.json", "mapa-cr.json"):
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(d, dict) and "listings" in d:
            out[d.get("region", f.stem)] = d["listings"]
    return out


def probe_e_chalupy() -> list[dict]:
    """Projde area kódy a vrátí ty, které mají nabídky (název + počet)."""
    rows = []
    for n in E_AREA_RANGE:
        area_id = f"area_{n}"
        try:
            r = requests.get(e_chalupy.API_URL, headers=e_chalupy.HEADERS,
                             params={"destinations": area_id, "limit": 1, "offset": 0}, timeout=20)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError) as exc:
            rows.append({"id": area_id, "error": str(exc)[:60]})
            continue
        total = (data.get("total") or {}).get("value") or 0
        items = data.get("items") or []
        if not total or not items:
            continue
        a1 = ((items[0].get("area") or {}).get("title") or "").strip()
        a2 = ((items[0].get("area2") or {}).get("title") or "").strip()
        rows.append({"id": area_id, "total": total, "ex_area": a1, "ex_area2": a2})
    return rows


def probe_cs_chalupy() -> list[dict]:
    rows = []
    for reg in cs_chalupy._load_regions():
        try:
            _, total = cs_chalupy._fetch_region_page(reg["slug"], 1, None)
        except requests.RequestException:
            total = None
        rows.append({"name": reg["name"], "slug": reg["slug"], "total": total})
    return rows


def probe_chata() -> dict:
    base = {"Where": "", "Distance": 0, "Adults": 2, "GuestsType": "TwoAdults",
            "RoomAmountType": "More", "SortingType": "Regio"}
    return {
        "typ chaty a chalupy": chata_cz._total_for({**base, "AccType": chata_cz.ACC_TYPE_CHATY_CHALUPY}),
        "všechny typy": chata_cz._total_for(base),
    }


def md_table(header: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def main() -> int:
    db = load_db()
    static_ids = {v: k for k, v in e_chalupy.STATIC_AREA_IDS.items()}  # area_id -> náš region
    db_counts = {reg: collections.Counter(l["source"] for l in ls) for reg, ls in db.items()}
    parts = ["# Pokrytí oblastí\n"]

    # --- e-chalupy.cz ---
    er = probe_e_chalupy()
    rows, missing = [], 0
    for r in er:
        if "error" in r:
            rows.append([r["id"], "chyba", r["error"], "", "", ""])
            continue
        ours = static_ids.get(r["id"])
        have = db_counts.get(ours, {}).get("e-chalupy.cz", 0) if ours else 0
        status = "ano" if ours else "**CHYBÍ**"
        if not ours:
            missing += r["total"]
        rows.append([r["id"], r["ex_area2"] or r["ex_area"] or "?", r["total"], ours or "-", have, status])
    parts.append("## e-chalupy.cz (area kódy 19600–19699)\n")
    parts.append(md_table(["kód", "oblast (z ukázkové nabídky)", "na portálu", "náš region", "u nás", "pokryto"], rows))
    parts.append(f"\nCelkem nabídek v oblastech, které nemáme: **{missing}**\n")

    # --- cs-chalupy.cz ---
    cr = probe_cs_chalupy()
    cs_db = collections.Counter()
    for ls in db.values():
        for l in ls:
            if l["source"] == "cs-chalupy.cz":
                cs_db[(l.get("location") or "").rsplit(",", 1)[-1].strip()] += 1
    rows = [[r["name"], r["slug"], r["total"], cs_db.get(r["name"], 0)] for r in cr]
    parts.append("## cs-chalupy.cz\n")
    parts.append(md_table(["oblast", "slug", "na portálu", "u nás (po odfiltrování typů)"], rows))

    # --- chata.cz ---
    parts.append("\n## chata.cz (celá ČR bez lokality)\n")
    ch = probe_chata()
    ch_db = sum(c.get("chata.cz", 0) for c in db_counts.values())
    parts.append(md_table(["dotaz", "na portálu"], [[k, v] for k, v in ch.items()] + [["u nás (součet po regionech)", ch_db]]))

    text = "\n".join(parts)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
