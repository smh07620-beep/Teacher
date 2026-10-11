#!/usr/bin/env python3
"""Send one harmless test event to Sentry to confirm error notifications work.

Uses the same privacy settings as the web service (teacher_app/maintenance/
error_reporting.py): no cookies, headers, request bodies, users or breadcrumbs.

    SENTRY_DSN="https://...@....ingest.sentry.io/..." python tools/sentry_test_event.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def send_test_event(environ=None, *, transport=None) -> bool:
    from teacher_app.maintenance.error_reporting import init_error_reporting

    env = os.environ if environ is None else environ
    if not init_error_reporting(env, transport=transport):
        print("未啟用：請確認已設定 SENTRY_DSN，且已安裝 sentry-sdk（pip install -r requirements.txt）。")
        return False
    import sentry_sdk

    sentry_sdk.capture_message("Teacher 錯誤通知測試（這是測試訊息，不是真的錯誤）", level="info")
    sentry_sdk.flush(timeout=10)
    print("已送出測試訊息。請到 Sentry 專案的 Issues 頁面查看（可能需要幾十秒）。")
    return True


def main() -> int:
    return 0 if send_test_event() else 1


if __name__ == "__main__":
    raise SystemExit(main())
