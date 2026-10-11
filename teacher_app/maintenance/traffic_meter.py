"""Outbound traffic meter with an e-mail early warning.

Why: the hosting plan has a monthly outbound-bandwidth allowance and suspends the
service when it runs out.  This module counts the response bytes the web service
sends, per day and per feature bucket, and e-mails the administrator when the
month's total crosses configurable thresholds.

What it records: the day, a coarse feature bucket (for example ``api/slides`` or
``media/uploaded-slides``), a byte count and a request count.  It never stores
user names, full URLs, query strings, headers or bodies.

What it does NOT see: traffic the service itself initiates (uploads to R2/MEGA,
AI provider calls) and HTTP headers.  The hosting dashboard remains the
authoritative number; this is an early-warning estimate, so thresholds should be
set below the real allowance.

Failures here must never affect a request: every database or mail problem is
logged and swallowed.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import threading
import time
from typing import Callable

from flask import g, jsonify, request

from teacher_app.common import db as common_db
from teacher_app.common.auth import has_permission

LOGGER = logging.getLogger(__name__)

_GB = 1024**3
FLUSH_SECONDS = 60
MAIL_RETRY_SECONDS = 15 * 60
MAX_BUCKETS = 120
_MEDIA_PREFIXES = (
    "/uploaded-slides/",
    "/material-preview/",
    "/view/",
    "/download/",
    "/question-images/",
)
_STATIC_SUFFIXES = (
    ".js", ".css", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico", ".woff", ".woff2", ".map",
)


def enabled() -> bool:
    return os.environ.get("TRAFFIC_METER", "true").strip().lower() not in {"0", "false", "no", "off"}


def thresholds_gb(environ=None) -> list[float]:
    raw = str((environ or os.environ).get("TRAFFIC_ALERT_GB", "2.5,3.5") or "")
    values: list[float] = []
    for part in raw.split(","):
        try:
            value = float(part.strip())
        except ValueError:
            continue
        if 0 < value <= 100000:
            values.append(value)
    return sorted(set(values))


def bucket_for(path: str) -> str:
    """Map a request path to a small, bounded feature bucket (no ids, no names)."""
    p = (path or "/").lower()
    if p.startswith("/api/"):
        parts = p.split("/")
        return "api/" + (parts[2] if len(parts) > 2 and parts[2] else "root")[:40]
    for prefix in _MEDIA_PREFIXES:
        if p.startswith(prefix):
            return "media/" + prefix.strip("/")
    if p.startswith("/static/") or p.endswith(_STATIC_SUFFIXES):
        return "static"
    return "page"


def response_bytes(response) -> int:
    """Body size of a response without consuming a stream."""
    try:
        if response.direct_passthrough or response.is_streamed:
            return max(0, int(response.content_length or 0))
        return len(response.get_data())
    except Exception:
        return max(0, int(response.content_length or 0))


def _day(now: dt.datetime) -> str:
    return now.strftime("%Y-%m-%d")


def _month(now: dt.datetime) -> str:
    return now.strftime("%Y-%m")


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _send_mail(to: str, subject: str, body: str) -> bool:
    from teacher_app.auth.self_service import _send

    return bool(_send(to, subject, body))


class TrafficMeter:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.time,
        utcnow: Callable[[], dt.datetime] = _utcnow,
        mailer: Callable[[str, str, str], bool] = _send_mail,
    ) -> None:
        self._clock = clock
        self._utcnow = utcnow
        self._mailer = mailer
        self._lock = threading.Lock()
        self._pending: dict[tuple[str, str], list[int]] = {}
        self._last_flush = clock()
        self._last_mail_attempt: dict[str, float] = {}

    # -- recording -----------------------------------------------------
    def record(self, bucket: str, nbytes: int) -> None:
        day = _day(self._utcnow())
        with self._lock:
            key = (day, bucket)
            if key not in self._pending and len({b for _, b in self._pending}) >= MAX_BUCKETS:
                key = (day, "other")
            cell = self._pending.setdefault(key, [0, 0])
            cell[0] += max(0, int(nbytes))
            cell[1] += 1
            due = self._clock() - self._last_flush >= FLUSH_SECONDS
        if due:
            self.flush()

    def flush(self) -> None:
        with self._lock:
            pending, self._pending = self._pending, {}
            self._last_flush = self._clock()
        if not pending:
            return
        try:
            with common_db.transaction() as (conn, kind):
                ph = common_db.placeholder(kind)
                for (day, bucket), (nbytes, count) in pending.items():
                    conn.execute(
                        f"INSERT INTO traffic_usage (day,bucket,bytes,requests) VALUES ({ph},{ph},{ph},{ph}) "
                        "ON CONFLICT(day,bucket) DO UPDATE SET "
                        "bytes=traffic_usage.bytes+EXCLUDED.bytes, "
                        "requests=traffic_usage.requests+EXCLUDED.requests",
                        (day, bucket, nbytes, count),
                    )
        except Exception as exc:
            LOGGER.warning("traffic_meter_flush_failed error_type=%s", type(exc).__name__)
            return
        try:
            self.check_alerts()
        except Exception as exc:
            LOGGER.warning("traffic_meter_alert_failed error_type=%s", type(exc).__name__)

    # -- reading -------------------------------------------------------
    def month_summary(self, month: str | None = None) -> dict:
        month = month or _month(self._utcnow())
        with common_db.read_connection() as (conn, kind):
            ph = common_db.placeholder(kind)
            rows = conn.execute(
                f"SELECT bucket, SUM(bytes) AS b, SUM(requests) AS r FROM traffic_usage "
                f"WHERE day LIKE {ph} GROUP BY bucket ORDER BY b DESC",
                (month + "-%",),
            ).fetchall()
            alerts = conn.execute(
                f"SELECT threshold_gb, sent_at FROM traffic_alerts WHERE month={ph}", (month,)
            ).fetchall()
        buckets = [
            {"bucket": r["bucket"], "bytes": int(r["b"] or 0), "requests": int(r["r"] or 0)}
            for r in map(dict, rows)
        ]
        total = sum(item["bytes"] for item in buckets)
        return {
            "month": month,
            "totalBytes": total,
            "totalGb": round(total / _GB, 3),
            "buckets": buckets[:15],
            "thresholdsGb": thresholds_gb(),
            "alertsSent": {str(dict(a)["threshold_gb"]): str(dict(a)["sent_at"]) for a in alerts},
            "emailConfigured": bool(os.environ.get("TRAFFIC_ALERT_EMAIL", "").strip()),
            "note": "僅統計網站送出的回應內容，不含網站自己對外上傳／呼叫 AI 的流量；實際用量以 Render 後台為準。",
        }

    # -- alerting ------------------------------------------------------
    def check_alerts(self) -> list[str]:
        summary = self.month_summary()
        total = summary["totalBytes"]
        recipient = os.environ.get("TRAFFIC_ALERT_EMAIL", "").strip()
        if not recipient:
            return []
        sent: list[str] = []
        for threshold in summary["thresholdsGb"]:
            label = f"{threshold:g}"
            if total < threshold * _GB or label in summary["alertsSent"]:
                continue
            last = self._last_mail_attempt.get(label, 0.0)
            if self._clock() - last < MAIL_RETRY_SECONDS:
                continue
            self._last_mail_attempt[label] = self._clock()
            top = "\n".join(
                f"  - {item['bucket']}：{item['bytes'] / (1024**2):.0f} MB（{item['requests']} 次）"
                for item in summary["buckets"][:5]
            )
            body = (
                f"教學網站本月（{summary['month']}）送出的資料量已達 {summary['totalGb']} GB，"
                f"超過你設定的提醒門檻 {label} GB。\n\n"
                f"用量最多的功能：\n{top}\n\n"
                "這是網站自己的估計值，只含網站回應內容。實際用量請到 Render 後台 → "
                "Billing / Usage 查看；Hobby 工作區內含 5 GB，超過後依用量計費。\n"
            )
            try:
                ok = self._mailer(recipient, f"【教學網站】本月流量已達 {label} GB 提醒", body)
            except Exception as exc:
                LOGGER.warning("traffic_alert_mail_failed error_type=%s", type(exc).__name__)
                ok = False
            if not ok:
                continue
            with common_db.transaction() as (conn, kind):
                ph = common_db.placeholder(kind)
                conn.execute(
                    f"INSERT INTO traffic_alerts (month,threshold_gb,sent_at,total_bytes) "
                    f"VALUES ({ph},{ph},{ph},{ph}) ON CONFLICT(month,threshold_gb) DO NOTHING",
                    (summary["month"], label, self._utcnow().isoformat(), total),
                )
            sent.append(label)
        return sent


def register_traffic_meter(app, *, meter: TrafficMeter | None = None):
    if app.extensions.get("teacher_traffic_meter_registered"):
        return app
    meter = meter or TrafficMeter()
    app.extensions["teacher_traffic_meter"] = meter

    @app.after_request
    def count_outbound_bytes(response):
        if not enabled():
            return response
        try:
            meter.record(bucket_for(request.path), response_bytes(response))
        except Exception as exc:  # metering must never break a response
            LOGGER.warning("traffic_meter_record_failed error_type=%s", type(exc).__name__)
        return response

    def traffic_usage():
        user = getattr(g, "teacher_user", None)
        if not user:
            resolver = getattr(app, "_current_user", None)
            user = resolver() if callable(resolver) else None
        if not user:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401
        if not has_permission(user, "storage.manage"):
            return jsonify({"error": "權限不足：此功能限系統管理者使用。"}), 403
        meter.flush()
        try:
            return jsonify(meter.month_summary())
        except Exception as exc:
            LOGGER.warning("traffic_meter_summary_failed error_type=%s", type(exc).__name__)
            return jsonify({"error": "流量統計暫時無法讀取。"}), 503

    app.add_url_rule(
        "/api/admin/traffic-usage",
        endpoint="api_admin_traffic_usage",
        view_func=traffic_usage,
        methods=["GET"],
    )
    app.extensions["teacher_traffic_meter_registered"] = True
    return app


__all__ = ["TrafficMeter", "bucket_for", "register_traffic_meter", "thresholds_gb"]
