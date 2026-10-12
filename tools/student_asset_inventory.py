"""List the scripts the /system page loads and which look teacher/admin-only.

Groundwork for loading fewer scripts for students (docs/STUDENT_LEAN_ASSETS_PLAN.md).
It changes nothing: it prints a Markdown table of size and cross-references so each
candidate can be checked by hand before any script is withheld from learners.

Usage: python tools/student_asset_inventory.py > report.md
"""
from __future__ import annotations

import gzip
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from teacher_app.frontend import assets  # noqa: E402

CANDIDATE = re.compile(
    r"^/(admin-|teacher-|course-wizard|worker-status|maintenance-|roles-signing|pgy-workflow|system-admin|review-links)"
)


def _flat(value):
    if isinstance(value, str):
        return [value]
    out: list[str] = []
    for item in value:
        out += _flat(item)
    return out


def system_scripts() -> list[str]:
    manifest = assets.ASSET_MANIFEST["system"]
    files: list[str] = []
    for key in ("ordered", "head", "body"):
        files += _flat(manifest.get(key, ()))
    html = (ROOT / "static" / "system.html").read_text(encoding="utf-8")
    files += ["/" + m for m in re.findall(r'src="/([^"?#]+\.js)', html)]
    return [f for f in dict.fromkeys(files) if f.endswith(".js") and (ROOT / "static" / f.lstrip("/")).exists()]


def main() -> int:
    files = system_scripts()
    text = {f: (ROOT / "static" / f.lstrip("/")).read_text(encoding="utf-8", errors="ignore") for f in files}
    gz = {f: len(gzip.compress(text[f].encode("utf-8"), 6)) for f in files}
    candidates = [f for f in files if CANDIDATE.match(f)]
    kept = [f for f in files if f not in candidates]
    kept_text = "\n".join(text[f] for f in kept)
    print("| 檔案 | 壓縮後 KB | 名稱像教師/管理 | 被其他（學員）程式引用的名稱 |")
    print("|---|---:|:---:|---|")
    for f in sorted(files, key=lambda x: -gz[x]):
        names = set(re.findall(r"(?:window|root|global|self)\.([A-Za-z_]\w{4,})\s*=", text[f]))
        used = sorted(n for n in names if f in candidates and re.search(rf"\b{re.escape(n)}\b", kept_text))
        print(f"| `{f}` | {gz[f] / 1024:.1f} | {'是' if f in candidates else ''} | {', '.join(used[:6])} |")
    total = sum(gz.values()) / 1024
    cand = sum(gz[f] for f in candidates) / 1024
    print(f"\n合計 {len(files)} 支、{total:.0f} KB；名稱像教師/管理的 {len(candidates)} 支、{cand:.0f} KB。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
