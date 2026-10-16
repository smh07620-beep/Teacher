"""Count front-end 'patch layering' debt so it can only go down.

Usage: python tools/ui_debt_report.py [--json]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
PATCH_NAME = re.compile(r"(fix|convergence|cleanup|resilience|refine|focus)", re.I)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def measure() -> dict[str, int]:
    js = sorted(STATIC.glob("*.js"))
    css = sorted(STATIC.glob("*.css"))
    html = sorted(STATIC.glob("*.html"))
    return {
        "patchFiles": sum(1 for p in js if PATCH_NAME.search(p.stem)),
        "mutationObserverFiles": sum(1 for p in js if "MutationObserver" in read(p)),
        "importantDeclarations": sum(read(p).count("!important") for p in css),
        "tinyTextClasses": sum(
            len(re.findall(r"text-\[(?:[0-9]|1[01])px\]", read(p))) for p in js + html
        ),
    }


if __name__ == "__main__":
    data = measure()
    print(json.dumps(data, indent=2) if "--json" in sys.argv else "\n".join(f"{k}: {v}" for k, v in data.items()))
