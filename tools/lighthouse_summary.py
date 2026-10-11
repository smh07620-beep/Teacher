#!/usr/bin/env python3
"""Summarize Lighthouse CI reports as a short Chinese Markdown table.

Reads ``<reports-dir>/manifest.json`` written by ``lhci autorun`` (filesystem
upload target) and prints one table row per audited URL.  Used by
``.github/workflows/lighthouse.yml`` to fill the GitHub Actions job summary.

Standard library only.  It never fails the build: missing or empty reports only
produce an explanatory message, because the thresholds themselves are warnings.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Same thresholds as tests/lighthouse/lighthouserc.js.
SCORE_THRESHOLDS = {"performance": 60, "accessibility": 90, "best-practices": 90}
LCP_LIMIT_MS = 4000
CLS_LIMIT = 0.1
TBT_LIMIT_MS = 600

CATEGORY_LABELS = (
    ("performance", "速度"),
    ("accessibility", "無障礙"),
    ("best-practices", "最佳實務"),
)


def _score(report: dict[str, Any], category: str) -> int | None:
    value = (report.get("categories", {}).get(category) or {}).get("score")
    return None if value is None else round(float(value) * 100)


def _numeric(report: dict[str, Any], audit: str) -> float | None:
    value = (report.get("audits", {}).get(audit) or {}).get("numericValue")
    return None if value is None else float(value)


def _mark(ok: bool | None) -> str:
    if ok is None:
        return "—"
    return "🟢" if ok else "🟠"


def summarize_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return the values shown for one audited page."""
    scores = {key: _score(report, key) for key, _label in CATEGORY_LABELS}
    return {
        "url": str(report.get("finalUrl") or report.get("requestedUrl") or ""),
        "formFactor": str((report.get("configSettings") or {}).get("formFactor") or ""),
        "scores": scores,
        "lcp_ms": _numeric(report, "largest-contentful-paint"),
        "cls": _numeric(report, "cumulative-layout-shift"),
        "tbt_ms": _numeric(report, "total-blocking-time"),
    }


def _fmt_seconds(ms: float | None) -> str:
    return "—" if ms is None else f"{ms / 1000:.1f} 秒"


def _row(item: dict[str, Any], base_url: str) -> str:
    path = item["url"]
    if base_url and path.startswith(base_url):
        path = path[len(base_url):] or "/"
    cells = [f"`{path}`"]
    for key, _label in CATEGORY_LABELS:
        score = item["scores"][key]
        cells.append("—" if score is None else f"{_mark(score >= SCORE_THRESHOLDS[key])} {score}")
    lcp, cls, tbt = item["lcp_ms"], item["cls"], item["tbt_ms"]
    cells.append(f"{_mark(None if lcp is None else lcp <= LCP_LIMIT_MS)} {_fmt_seconds(lcp)}")
    cells.append(f"{_mark(None if cls is None else cls <= CLS_LIMIT)} {'—' if cls is None else f'{cls:.3f}'}")
    cells.append(f"{_mark(None if tbt is None else tbt <= TBT_LIMIT_MS)} {'—' if tbt is None else f'{tbt:.0f} ms'}")
    return "| " + " | ".join(cells) + " |"


def build_summary(reports_dir: Path, *, title: str = "", base_url: str = "") -> str:
    manifest_path = reports_dir / "manifest.json"
    lines: list[str] = []
    if title:
        lines.append(f"### {title}")
        lines.append("")
    if not manifest_path.is_file():
        lines.append("沒有找到 Lighthouse 報告（可能是網站無法連線，或檢測過程失敗）。請查看上方的執行紀錄。")
        return "\n".join(lines) + "\n"

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError:
        manifest = []
    items: list[dict[str, Any]] = []
    for entry in manifest if isinstance(manifest, list) else []:
        if not entry.get("isRepresentativeRun", True):
            continue  # 同一頁面跑多次，只顯示中位數那一次
        json_path = Path(str(entry.get("jsonPath") or ""))
        if not json_path.is_absolute():
            json_path = reports_dir / json_path.name
        elif not json_path.is_file():
            json_path = reports_dir / json_path.name
        try:
            report = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        items.append(summarize_report(report))

    if not items:
        lines.append("報告是空的，沒有可顯示的結果。")
        return "\n".join(lines) + "\n"

    form_factor = items[0]["formFactor"]
    if form_factor:
        lines.append(f"檢測裝置：{'電腦版' if form_factor == 'desktop' else '手機版（模擬較慢網路）'}")
        lines.append("")
    lines.append("| 頁面 | 速度 | 無障礙 | 最佳實務 | 最大內容顯示 | 版面位移 | 操作卡頓 |")
    lines.append("|---|---|---|---|---|---|---|")
    for item in items:
        lines.append(_row(item, base_url.rstrip("/")))
    lines.append("")
    lines.append("🟢 達標　🟠 未達標（僅提醒，不影響上線）。分數滿分 100；時間越短越好。")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", default=".lighthouseci/reports")
    parser.add_argument("--title", default="")
    parser.add_argument("--base-url", default="")
    args = parser.parse_args(argv)
    sys.stdout.write(build_summary(Path(args.reports_dir), title=args.title, base_url=args.base_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
