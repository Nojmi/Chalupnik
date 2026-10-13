"""Regionální databáze nabídek: slučování běhů scraperu, čerstvost, index.

Princip: každý běh scraperu (`results/latest.json`) se SLOUČÍ do souboru
`data/<region>.json`. Nabídky se nepřepisují od nuly:
  * nová nabídka se přidá,
  * známá se aktualizuje (`first_seen` zůstává),
  * zmizelá se jen označí `seen_in_last_run: false` (nemaže se),
  * chybějící cena se nepřepíše starou známou cenou.

Použití z příkazové řádky (z kořene repozitáře):
    python -m scraper.store merge results/latest.json
    python -m scraper.store merge results/latest.json --sources e-chalupy.cz --dry-run
    python -m scraper.store index
    python -m scraper.store status
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from scraper.normalize import SCHEMA_VERSION, normalize_listing

ALL_SOURCES = ("e-chalupy.cz", "chata.cz", "cs-chalupy.cz")

FRESH_DAYS = 14        # do 14 dní včetně = čerstvé
STALE_DAYS = 30        # 15–30 = doporučit aktualizaci, nad 30 = zastaralé
PRUNE_DAYS = 180       # zmizelé nabídky se po tolika dnech opravdu smažou
MIN_RATIO = 0.5        # běh s <50 % dřívějšího počtu nabídek je podezřelý
MIN_BASELINE = 20      # ...ale jen u zdrojů, které dřív měly aspoň tolik nabídek

# Filtry, které by do databáze propustily jen ČÁST nabídek regionu.
RESTRICTIVE_CRITERIA = ("min_capacity", "min_bedrooms", "max_price", "amenities")

PRICE_FIELDS = ("price_per_night_from", "price_per_night_to", "price_estimated",
                "price_as_of", "price_term", "price_note")


class StoreError(Exception):
    """Chyba, kvůli které se databáze nesmí měnit."""


# ---------------------------------------------------------------------------
# Pomocné funkce
# ---------------------------------------------------------------------------
def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def freshness(last_updated: Optional[str], now: Optional[datetime] = None) -> dict:
    """{"status": fresh|aging|stale|empty, "age_days": int|None} podle prahů 14/30 dní."""
    if not last_updated:
        return {"status": "empty", "age_days": None}
    now = now or datetime.now(timezone.utc)
    age = max((now - _parse_dt(last_updated)).days, 0)
    if age <= FRESH_DAYS:
        status = "fresh"
    elif age <= STALE_DAYS:
        status = "aging"
    else:
        status = "stale"
    return {"status": status, "age_days": age}


def empty_store(slug: str, label: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "region": slug,
        "region_label": label,
        "last_updated": None,
        "sources_updated": {s: None for s in ALL_SOURCES},
        "listings": [],
    }


def load_store(path: Path) -> Optional[dict]:
    path = Path(path)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_store(path: Path, store: dict) -> None:
    """Atomický zápis (dočasný soubor + přejmenování), stabilní pořadí pro čisté git diffy."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    store["listings"] = sorted(store["listings"], key=lambda x: x["id"])
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(store, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, path)


def region_of(run: dict) -> tuple[str, str]:
    label = ((run.get("criteria") or {}).get("location") or "").strip()
    slug = slugify(label)
    if not slug:
        raise StoreError("Běh nemá vyplněnou lokalitu (criteria.location) – "
                         "nelze určit, do kterého regionu patří.")
    return slug, label


def check_criteria(criteria: dict) -> None:
    used = [k for k in RESTRICTIVE_CRITERIA if (criteria or {}).get(k)]
    if used:
        raise StoreError(
            "Běh byl omezen filtry (" + ", ".join(used) + ") – obsahuje jen část regionu "
            "a v databázi by označil ostatní nabídky za zmizelé. Do databáze patří jen "
            "běhy bez těchto filtrů (filtruje se až na webu).")


# main.py ukládá chyby jako {"profile": "scraper.profiles.chata_cz", "error": "..."}
PROFILE_MODULES = {
    "e_chalupy": "e-chalupy.cz",
    "chata_cz": "chata.cz",
    "cs_chalupy": "cs-chalupy.cz",
}


def failed_sources(errors: list, sources=ALL_SOURCES) -> set[str]:
    """Zdroje, jejichž profil skončil chybou.

    Pozná jak tvar z main.py (`{"profile": "scraper.profiles.chata_cz", ...}`),
    tak textovou chybu, ve které je přímo název portálu.
    """
    failed: set[str] = set()
    for e in errors or []:
        text = e.get("profile", "") if isinstance(e, dict) else ""
        text = f"{text} {e}"
        for module, src in PROFILE_MODULES.items():
            if module in text:
                failed.add(src)
        for src in ALL_SOURCES:
            if src in text:
                failed.add(src)
    return failed & set(sources)


# ---------------------------------------------------------------------------
# Slučování
# ---------------------------------------------------------------------------
@dataclass
class MergeReport:
    region: str
    added: int = 0
    updated: int = 0
    marked_missing: int = 0
    pruned: int = 0
    warnings: list = field(default_factory=list)
    per_source: dict = field(default_factory=dict)

    def summary(self) -> str:
        lines = [f"region {self.region}: +{self.added} nových, {self.updated} aktualizováno, "
                 f"{self.marked_missing} označeno jako zmizelé, {self.pruned} smazáno"]
        for src, info in self.per_source.items():
            lines.append(f"  {src}: {info['in_run']} v běhu, dříve aktivních {info['previous_active']}"
                         f" -> {info['state']}")
        lines += [f"  ⚠ {w}" for w in self.warnings]
        return "\n".join(lines)


def merge_run(store: dict, run: dict, sources=ALL_SOURCES, prune_days: int = PRUNE_DAYS,
              min_ratio: float = MIN_RATIO) -> MergeReport:
    """Sloučí běh scraperu (`latest.json`) do `store`. Mění `store` na místě."""
    check_criteria(run.get("criteria") or {})
    run_time = run.get("generated_at") or datetime.now(timezone.utc).isoformat()
    run_date = run_time[:10]
    sources = tuple(sources)

    report = MergeReport(region=store["region"])
    failed = failed_sources(run.get("errors"), sources)

    # 1) normalizace příchozích nabídek jen z povolených zdrojů, bez duplicit
    incoming: dict[str, dict] = {}
    for raw in run.get("listings") or []:
        if raw.get("source") not in sources:
            continue
        n = normalize_listing(raw, run_date)
        incoming[n["id"]] = n

    existing = {x["id"]: x for x in store["listings"]}

    # 2) které zdroje smíme považovat za "kompletně projité"
    mark_missing_for: set[str] = set()
    for src in sources:
        in_run = sum(1 for n in incoming.values() if n["source"] == src)
        prev_active = sum(1 for x in store["listings"]
                          if x["source"] == src and x.get("seen_in_last_run"))
        if src in failed:
            state = "chyba zdroje – beze změny"
            report.warnings.append(f"{src}: běh skončil chybou, zdroj se neaktualizuje jako kompletní.")
        elif prev_active >= MIN_BASELINE and in_run < prev_active * min_ratio:
            state = "podezřele málo – zmizelé se neoznačují"
            report.warnings.append(
                f"{src}: v běhu jen {in_run} nabídek oproti {prev_active} dříve; "
                "nabídky se doplnily, ale zmizelé se neoznačují a zdroj se nepovažuje za "
                "aktualizovaný. Zkontrolujte log (tichý fallback na celostátní hledání?).")
        else:
            state = "OK"
            mark_missing_for.add(src)
        report.per_source[src] = {"in_run": in_run, "previous_active": prev_active, "state": state}

    # 3) přidání / aktualizace
    for nid, new in incoming.items():
        old = existing.get(nid)
        if old is None:
            rec = {"id": nid, "first_seen": run_date, "last_seen": run_date,
                   "seen_in_last_run": True}
            rec.update({k: v for k, v in new.items() if k != "id"})
            existing[nid] = rec
            report.added += 1
        else:
            rec = {"id": nid, "first_seen": old.get("first_seen", run_date),
                   "last_seen": run_date, "seen_in_last_run": True}
            rec.update({k: v for k, v in new.items() if k != "id"})
            if rec.get("price_per_night_from") is None and old.get("price_per_night_from") is not None:
                for k in PRICE_FIELDS:       # stará známá cena je lepší než žádná
                    rec[k] = old.get(k)
            existing[nid] = rec
            report.updated += 1

    # 4) zmizelé nabídky (jen u zdrojů, které se kompletně projely)
    cutoff = date.fromisoformat(run_date) - timedelta(days=prune_days)
    for nid in list(existing):
        x = existing[nid]
        if nid in incoming or x["source"] not in mark_missing_for:
            continue
        if x.get("seen_in_last_run"):
            report.marked_missing += 1
        x["seen_in_last_run"] = False
        if date.fromisoformat(x["last_seen"]) < cutoff:
            del existing[nid]
            report.pruned += 1

    store["listings"] = list(existing.values())

    # 5) časy aktualizace po zdrojích
    for s in ALL_SOURCES:
        store["sources_updated"].setdefault(s, None)
    for src in mark_missing_for:
        store["sources_updated"][src] = run_time
    stamps = [v for v in store["sources_updated"].values() if v]
    store["last_updated"] = max(stamps, key=_parse_dt) if stamps else None
    store["schema_version"] = SCHEMA_VERSION
    return report


# ---------------------------------------------------------------------------
# Index regionů (pro výběr regionu na webu)
# ---------------------------------------------------------------------------
def build_index(data_dir: Path) -> dict:
    """Stav čerstvosti se do indexu záměrně neukládá – web ho musí počítat v okamžiku zobrazení."""
    regions = []
    for p in sorted(Path(data_dir).glob("*.json")):
        if p.name == "index.json":
            continue
        s = load_store(p)
        if not s:
            continue
        regions.append({
            "region": s["region"],
            "region_label": s.get("region_label") or s["region"],
            "file": p.name,
            "listing_count": len(s["listings"]),
            "active_count": sum(1 for x in s["listings"] if x.get("seen_in_last_run")),
            "last_updated": s.get("last_updated"),
            "sources_updated": s.get("sources_updated", {}),
        })
    return {"schema_version": SCHEMA_VERSION, "regions": regions}


def write_index(data_dir: Path) -> dict:
    idx = build_index(data_dir)
    path = Path(data_dir) / "index.json"
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(idx, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, path)
    return idx


# ---------------------------------------------------------------------------
# Příkazová řádka
# ---------------------------------------------------------------------------
def merge_file(run_path: Path, data_dir: Path, sources=ALL_SOURCES,
               prune_days: int = PRUNE_DAYS, dry_run: bool = False) -> MergeReport:
    with Path(run_path).open(encoding="utf-8") as f:
        run = json.load(f)
    slug, label = region_of(run)
    target = Path(data_dir) / f"{slug}.json"
    store = load_store(target) or empty_store(slug, label)
    report = merge_run(store, run, sources=sources, prune_days=prune_days)
    if not dry_run:
        save_store(target, store)
        write_index(data_dir)
    return report


def update_database(run_path: Path, data_dir: Path, sources=ALL_SOURCES) -> Optional[MergeReport]:
    """Bezpečné volání z `scraper/main.py`: nikdy nevyhodí výjimku.

    `results/latest.json` je v tu chvíli už zapsaný, takže problém s databází
    nesmí shodit celý běh – jen se vypíše do logu (v Actions je vidět).
    """
    try:
        report = merge_file(Path(run_path), Path(data_dir), sources)
    except StoreError as exc:
        print(f"[DATABASE] přeskočeno: {exc}")
        return None
    except Exception as exc:  # poškozený soubor, zápis na disk apod.
        print(f"[DATABASE] chyba, databáze nebyla změněna: {exc}", file=sys.stderr)
        return None
    print(report.summary())
    return report


def _cmd_status(data_dir: Path) -> int:
    idx = build_index(data_dir)
    if not idx["regions"]:
        print("Databáze je zatím prázdná.")
        return 0
    icons = {"fresh": "🟢", "aging": "🟡", "stale": "🔴", "empty": "⚪"}
    for r in idx["regions"]:
        fr = freshness(r["last_updated"])
        age = "—" if fr["age_days"] is None else f"{fr['age_days']} dní"
        print(f"{icons[fr['status']]} {r['region_label']:<20} {r['active_count']:>5} aktivních "
              f"z {r['listing_count']:<5} stáří {age}")
    return 0


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m scraper.store")
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("merge", help="sloučit běh scraperu do databáze regionu")
    m.add_argument("run_file", help="např. results/latest.json")
    m.add_argument("--data-dir", default="data")
    m.add_argument("--sources", default=",".join(ALL_SOURCES),
                   help="čárkou oddělené zdroje, které tento běh pokrývá")
    m.add_argument("--prune-days", type=int, default=PRUNE_DAYS)
    m.add_argument("--dry-run", action="store_true", help="jen vypsat, co by se stalo")

    i = sub.add_parser("index", help="přegenerovat data/index.json")
    i.add_argument("--data-dir", default="data")

    s = sub.add_parser("status", help="vypsat čerstvost regionů")
    s.add_argument("--data-dir", default="data")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "merge":
            srcs = tuple(x.strip() for x in args.sources.split(",") if x.strip())
            unknown = [x for x in srcs if x not in ALL_SOURCES]
            if unknown:
                raise StoreError("Neznámý zdroj: " + ", ".join(unknown))
            rep = merge_file(Path(args.run_file), Path(args.data_dir), srcs,
                             args.prune_days, args.dry_run)
            print(rep.summary() + ("\n(dry-run, nic se nezapsalo)" if args.dry_run else ""))
            return 0
        if args.cmd == "index":
            idx = write_index(Path(args.data_dir))
            print(f"index.json: {len(idx['regions'])} regionů")
            return 0
        return _cmd_status(Path(args.data_dir))
    except StoreError as e:
        print(f"CHYBA: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
