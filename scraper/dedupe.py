"""Duplicity napříč portály: stejná chata nabízená na víc portálech.

Data v databázi zůstávají beze změny (každá nabídka má vlastní záznam, cenu a odkaz).
Tenhle krok jen najde skupiny záznamů, které jsou s velkou jistotou tentýž objekt,
a uloží je do `docs/data/duplicity.json`; web je pak zobrazí jako jednu kartu.

Pravidla jsou záměrně přísná – raději nesloučit, než sloučit dvě různé chaty:
1. e-chalupy.cz × cs-chalupy.cz (oba mají GPS): do ~80 m, stejná kapacita, stejný počet ložnic
   (pokud jsou oba známé) a navzájem jednoznačná shoda (žádný další kandidát téhož portálu).
2. chata.cz (bez GPS) × ostatní: stejný název (bez dovětku za " - "), stejná obec, stejná kapacita,
   shodný počet ložnic (pokud jsou oba známé) a jednoznačná shoda.
3. Skupina nikdy neobsahuje dva záznamy téhož portálu (to by mohly být různé jednotky v jednom objektu).

Spuštění: python -m scraper.dedupe
"""
from __future__ import annotations

import json
import math
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "docs" / "data"
OUT_NAME = "duplicity.json"
MAX_DIST_M = 80
PRIORITY = {"e-chalupy.cz": 0, "cs-chalupy.cz": 1, "chata.cz": 2}     # pořadí odkazů na kartě


def _plain(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def title_key(title: str) -> str:
    """Název bez dovětku za ' - ' (např. 'Chata Monika - Adršpach' -> 'chata monika')."""
    return _plain(re.split(r"\s+[-–—]\s+", title or "", maxsplit=1)[0])


def obec_key(location: str) -> str:
    return _plain((location or "").split(",")[0])


def _dist_m(a: dict, b: dict) -> float:
    lat = math.radians((a["lat"] + b["lat"]) / 2)
    dy = (a["lat"] - b["lat"]) * 111_320
    dx = (a["lon"] - b["lon"]) * 111_320 * math.cos(lat)
    return math.hypot(dx, dy)


def _same_size(a: dict, b: dict) -> bool:
    if a.get("capacity") is None or a.get("capacity") != b.get("capacity"):
        return False
    ba, bb = a.get("bedrooms"), b.get("bedrooms")
    return ba is None or bb is None or ba == bb


class _Groups:
    """Union-find, který odmítne sloučení, kdyby ve skupině byly dva záznamy téhož portálu."""

    def __init__(self, items: dict):
        self.items = items
        self.parent = {i: i for i in items}
        self.sources = {i: {items[i]["source"]} for i in items}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return True
        if self.sources[ra] & self.sources[rb]:
            return False
        self.parent[rb] = ra
        self.sources[ra] |= self.sources[rb]
        return True

    def groups(self) -> list[list[str]]:
        out = defaultdict(list)
        for i in self.items:
            out[self.find(i)].append(i)
        return [g for g in out.values() if len(g) > 1]


def _unique_pairs(cands: dict[str, list[str]], items: dict) -> list[tuple[str, str]]:
    """Dvojice, kde je shoda jednoznačná na obě strany (každý má jediného kandidáta z daného portálu)."""
    def per_source(ids):
        d = defaultdict(list)
        for i in ids:
            d[items[i]["source"]].append(i)
        return d
    pairs = []
    for a, bs in cands.items():
        for src, lst in per_source(bs).items():
            if len(lst) != 1:
                continue
            b = lst[0]
            back = per_source(cands.get(b, [])).get(items[a]["source"], [])
            if back == [a] and a < b:
                pairs.append((a, b))
    return pairs


def find_groups(listings: list[dict]) -> list[list[str]]:
    items = {x["id"]: x for x in listings}
    g = _Groups(items)

    # 1) GPS: e-chalupy × cs-chalupy
    grid = defaultdict(list)
    for i, x in items.items():
        p = x.get("gps")
        if p and x.get("capacity") is not None:
            grid[(round(p["lat"] / 0.001), round(p["lon"] / 0.001))].append(i)
    cands: dict[str, list[str]] = defaultdict(list)
    for (cy, cx), ids in grid.items():
        near = [j for dy in (-1, 0, 1) for dx in (-1, 0, 1) for j in grid.get((cy + dy, cx + dx), [])]
        for a in ids:
            for b in near:
                if a != b and items[a]["source"] != items[b]["source"] and _same_size(items[a], items[b]) \
                        and _dist_m(items[a]["gps"], items[b]["gps"]) <= MAX_DIST_M:
                    cands[a].append(b)
    for a, b in _unique_pairs(cands, items):
        g.union(a, b)

    # 2) chata.cz (bez GPS): název + obec + kapacita
    index = defaultdict(list)
    for i, x in items.items():
        if x["source"] != "chata.cz":
            index[(title_key(x["title"]), obec_key(x.get("location")), x.get("capacity"))].append(i)
    chata_by_key = defaultdict(list)
    for i, x in items.items():
        if x["source"] == "chata.cz" and x.get("capacity") is not None:
            chata_by_key[(title_key(x["title"]), obec_key(x.get("location")), x["capacity"])].append(i)
    for key, cs in chata_by_key.items():
        if len(cs) != 1 or not key[0]:               # dvě chata.cz se stejným klíčem = nejednoznačné
            continue
        c = cs[0]
        match = [j for j in index.get(key, []) if _same_size(items[c], items[j])]
        by_src = defaultdict(list)
        for j in match:
            by_src[items[j]["source"]].append(j)
        for lst in by_src.values():
            if len(lst) == 1:                         # u každého portálu jediný kandidát
                g.union(c, lst[0])

    out = []
    for grp in g.groups():
        out.append(sorted(grp, key=lambda i: (PRIORITY.get(items[i]["source"], 9), i)))
    return sorted(out)


def load_all(data_dir: Path) -> list[dict]:
    items = {}
    for p in sorted(Path(data_dir).glob("*.json")):
        if p.name in ("index.json", "mapa-cr.json", OUT_NAME):
            continue
        try:
            s = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(s, dict) and "region" in s and isinstance(s.get("listings"), list):
            for x in s["listings"]:
                items.setdefault(x["id"], x)
    return list(items.values())


def main(data_dir: Path = DATA_DIR) -> int:
    listings = load_all(data_dir)
    groups = find_groups(listings)
    by = {x["id"]: x["source"] for x in listings}
    kinds = defaultdict(int)
    for grp in groups:
        kinds[" + ".join(sorted({by[i].split(".")[0] for i in grp}))] += 1
    out = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "groups": groups}
    (Path(data_dir) / OUT_NAME).write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"[dedupe] nabídek {len(listings)}, skupin duplicit {len(groups)} ({dict(kinds)}); "
          f"po sloučení {len(listings) - sum(len(g) - 1 for g in groups)} unikátních")
    return 0


if __name__ == "__main__":
    sys.exit(main())
