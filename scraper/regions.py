"""Seznam všech oblastí (z docs/data/mapa-cr.json), oddělený středníkem.

Použití ve workflow: prázdné pole Lokalita = projdi všechny oblasti.
"""
import json
from pathlib import Path


def all_regions() -> list[str]:
    m = json.loads((Path(__file__).parent.parent / "docs" / "data" / "mapa-cr.json").read_text(encoding="utf-8"))
    return [o["name"] for o in m["oblasti"]]


if __name__ == "__main__":
    print("; ".join(all_regions()))
