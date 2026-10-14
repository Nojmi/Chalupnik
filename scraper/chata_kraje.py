"""chata.cz po krajích: přidělí kraj nabídkám a doplní ty, které žádná naše oblast nepokrývá.

Proč: karta na chata.cz nemá GPS, takže kraj z GPS nelze určit a nabídky chata.cz se v pohledu
„Podle krajů" neukázaly vůbec. A oblasti chata.cz se k našim oblastem hledají podle jmen, takže
část republiky (např. Plzeňský kraj) se nestáhla nikdy. Portál ale umí hledat přímo po krajích
(LocationType 2), takže:

1. projdeme všech 14 krajů (jen seznam kódů, rychle),
2. každé nabídce chata.cz v databázi dopíšeme `raw_extra.kraj_hint` (a tím i `kraj`),
3. kódy, které v žádné oblasti nejsou, stáhneme celé (ceny, vybavení, ...) do regionu `ostatni`.

Spouští se na konci každého workflow `Scrape listings`: `python -m scraper.chata_kraje`.
Nic nemaže: nabídka z regionu `ostatni` se odstraní jen tehdy, když ji mezitím pokryla oblast.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from scraper.profiles import chata_cz
from scraper.store import empty_store, load_store, merge_run, save_store, write_index

SOURCE = chata_cz.SOURCE_NAME
OSTATNI = "ostatni"
OSTATNI_LABEL = "Ostatní nabídky"
DATA_DIR = Path(__file__).parent.parent / "docs" / "data"


def _region_files(data_dir: Path) -> list[Path]:
    out = []
    for p in sorted(Path(data_dir).glob("*.json")):
        if p.name in ("index.json", "mapa-cr.json", f"{OSTATNI}.json"):
            continue
        s = load_store(p)
        if isinstance(s, dict) and "listings" in s and "region" in s:
            out.append(p)
    return out


def _code(listing: dict) -> str | None:
    if listing.get("source") != SOURCE:
        return None
    return (listing.get("raw_extra") or {}).get("code") or str(listing.get("id", "")).split(":", 1)[-1] or None


def covered_codes(data_dir: Path) -> set[str]:
    """Kódy chata.cz, které už má některá oblast (region `ostatni` se nepočítá)."""
    codes: set[str] = set()
    for p in _region_files(data_dir):
        for x in load_store(p)["listings"]:
            c = _code(x)
            if c:
                codes.add(c)
    return codes


def annotate_existing(data_dir: Path, index: dict[str, str]) -> int:
    """Doplní `raw_extra.kraj_hint` nabídkám chata.cz ve všech regionech. Vrací počet změněných."""
    changed = 0
    for p in _region_files(data_dir) + [Path(data_dir) / f"{OSTATNI}.json"]:
        store = load_store(p)
        if not store:
            continue
        dirty = False
        for x in store["listings"]:
            c = _code(x)
            kraj = index.get(c) if c else None
            if kraj and (x.get("raw_extra") or {}).get("kraj_hint") != kraj:
                x.setdefault("raw_extra", {})["kraj_hint"] = kraj
                dirty = True
                changed += 1
        if dirty:
            save_store(p, store)
    return changed


def fill_gap(data_dir: Path, listings: list[dict], index: dict[str, str], merge: bool = True) -> tuple[int, int]:
    """Uloží nabídky mimo oblasti do regionu `ostatni`. Vrací (v regionu nyní, odstraněno protože už je pokryla oblast)."""
    target = Path(data_dir) / f"{OSTATNI}.json"
    store = load_store(target) or empty_store(OSTATNI, OSTATNI_LABEL)
    now = datetime.now(timezone.utc).isoformat()
    for x in listings:
        c = (x.get("raw_extra") or {}).get("code")
        if c in index:
            x["raw_extra"]["kraj_hint"] = index[c]
    run = {"generated_at": now, "criteria": {"location": OSTATNI_LABEL}, "errors": [], "listings": listings}
    if merge and (listings or store["listings"]):
        merge_run(store, run, sources=(SOURCE,))
    covered = covered_codes(data_dir)
    before = len(store["listings"])
    store["listings"] = [x for x in store["listings"] if _code(x) not in covered]
    removed = before - len(store["listings"])
    if store["listings"] or target.exists():
        save_store(target, store)
    write_index(data_dir)
    return len(store["listings"]), removed


def main() -> int:
    data_dir = DATA_DIR
    index: dict[str, str] = {}
    rows = []
    resolved_by_kraj: dict[str, tuple] = {}
    for short in chata_cz.KRAJE:
        try:
            info = chata_cz.fetch_kraj_codes(short)
        except Exception as exc:                     # síťová chyba jednoho kraje nesmí shodit ostatní
            print(f"::warning::chata.cz kraj {short}: {exc}", file=sys.stderr)
            rows.append((short, None, 0))
            continue
        if not info:
            print(f"::warning::chata.cz: kraj {short} se nepodařilo určit (viz výpis výše)", file=sys.stderr)
            rows.append((short, None, 0))
            continue
        resolved_by_kraj[short] = info["resolved"]
        for c in info["codes"]:
            index[c] = short
        rows.append((short, info["total"], len(info["codes"])))
        print(f"[chata.cz kraj] {short}: portál hlásí {info['total']}, načteno kódů {len(info['codes'])}")

    if not index:
        print("::error::chata.cz po krajích: žádný kraj se nepodařilo načíst, nic se nemění", file=sys.stderr)
        return 1

    changed = annotate_existing(data_dir, index)
    covered = covered_codes(data_dir)
    gap_codes = {c for c in index if c not in covered}
    print(f"[chata.cz kraj] kraj doplněn u {changed} nabídek; v databázi chybí {len(gap_codes)} kódů z {len(index)}")

    gap_listings: list[dict] = []
    if gap_codes:
        for short, resolved in resolved_by_kraj.items():
            need = {c for c in gap_codes if index[c] == short}
            if not need:
                continue
            try:
                found = chata_cz.search_kraj(short, resolved)
            except Exception as exc:
                print(f"::warning::chata.cz kraj {short}: doplnění selhalo: {exc}", file=sys.stderr)
                continue
            gap_listings.extend(l.to_dict() for l in found if l.raw_extra.get("code") in need)
            print(f"[chata.cz kraj] {short}: doplněno {sum(1 for l in found if l.raw_extra.get('code') in need)} z {len(need)} chybějících")

    # normalizace (id, ceny, ...) proběhne uvnitř merge_run
    in_ostatni, removed = fill_gap(data_dir, gap_listings, index, merge=bool(gap_listings) or not gap_codes)
    print(f"[chata.cz kraj] region 'Ostatní nabídky': {in_ostatni} nabídek (odstraněno {removed}, už je pokryla oblast)")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        lines = ["### chata.cz po krajích", "", "| Kraj | Portál hlásí | Načteno kódů | V databázi mimo oblasti |", "|---|---:|---:|---:|"]
        for short, total, n in rows:
            miss = sum(1 for c in gap_codes if index.get(c) == short)
            lines.append(f"| {short} | {total if total is not None else '❌ nenalezen'} | {n} | {miss} |")
        with open(summary, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
