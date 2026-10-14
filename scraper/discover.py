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


def _e_ids(area_id: str) -> set[str]:
    """Všechna ID nabídek, která portál vrací pro daný area kód."""
    ids: set[str] = set()
    offset = 0
    while offset < 5000:
        r = requests.get(e_chalupy.API_URL, headers=e_chalupy.HEADERS,
                         params={"destinations": area_id, "limit": 1000, "offset": offset}, timeout=30)
        r.raise_for_status()
        items = r.json().get("items") or []
        if not items:
            break
        ids.update(str(i["id"]) for i in items if i.get("id") is not None)
        offset += 1000
    return ids


def probe_e_chalupy() -> list[dict]:
    """Projde area kódy a vrátí ty, které mají nabídky (název, počet, ID nabídek)."""
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
        try:
            ids = _e_ids(area_id)
        except requests.RequestException:
            ids = set()
        rows.append({"id": area_id, "total": total, "ex_area": a1, "ex_area2": a2, "ids": ids})
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
    # Porovnáváme konkrétní ID nabídek (ne jen počty): "chybí" = nabídky, které
    # portál pro daný kód vrací a my je v databázi nemáme.
    code_to_region = {}
    for region, value in e_chalupy.STATIC_AREA_IDS.items():
        for code in ([value] if isinstance(value, str) else value):
            code_to_region[code] = region
    db_e_ids = {str(l["raw_extra"].get("id")) for ls in db.values() for l in ls if l["source"] == "e-chalupy.cz"}
    er = probe_e_chalupy()
    rows, all_missing = [], set()
    for r in er:
        if "error" in r:
            rows.append([r["id"], "chyba", r["error"], "", "", ""])
            continue
        missing = r["ids"] - db_e_ids
        all_missing |= missing
        region = code_to_region.get(r["id"], "-")
        status = "ano" if not missing else f"**CHYBÍ {len(missing)}**"
        rows.append([r["id"], r["ex_area2"] or r["ex_area"] or "?", r["total"], region,
                     len(r["ids"] & db_e_ids), status])
    parts.append("## e-chalupy.cz (area kódy 19600–19699, porovnání podle ID nabídek)\n")
    parts.append(md_table(["kód", "oblast (z ukázkové nabídky)", "na portálu", "náš region", "z toho máme", "chybí"], rows))
    parts.append(f"\nUnikátních nabídek na e-chalupy.cz, které v databázi chybí: **{len(all_missing)}** "
                 f"(v databázi je jich {len(db_e_ids)})\n")

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
