"""One-screen health summary for administrators: five lights, details on demand.

Read-only and cheap: one migrations query, one heartbeat query, one traffic-alert
query and one R2 ledger sum.  Nothing here refreshes by itself; the admin page asks
when the admin presses the button.
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Any, Callable

GREEN, YELLOW, RED, GRAY = "green", "yellow", "red", "gray"
WORKER_FRESH_SECONDS = 10 * 60
WORKER_STALE_SECONDS = 60 * 60


def _light(key: str, label: str, state: str, detail: str) -> dict[str, str]:
    return {"key": key, "label": label, "state": state, "detail": detail}


def _parse(value: Any) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def database_light(health: dict[str, Any]) -> dict[str, str]:
    database = health.get("database") or {}
    migrations = health.get("migrations") or {}
    if not database.get("ok"):
        return _light("database", "資料庫", RED, "連不上資料庫。")
    if not migrations.get("ok", True):
        return _light("database", "資料庫", YELLOW, f"尚有 {len(migrations.get('missing') or [])} 個資料庫更新未套用。")
    return _light("database", "資料庫", GREEN, "連線正常，資料庫版本已是最新。")


def worker_lights(heartbeats: list[dict[str, Any]], now: dt.datetime | None = None) -> list[dict[str, str]]:
    now = now or dt.datetime.now(dt.timezone.utc)
    if not heartbeats:
        return [_light("worker", "教材 Worker", RED, "最近沒有任何 Worker 回報。教材轉檔會一直排隊。")]
    lights = []
    for index, item in enumerate(heartbeats[:2], start=1):
        seen = _parse(item.get("last_seen"))
        age = (now - seen).total_seconds() if seen else None
        name = str(item.get("worker_id") or f"Worker {index}")
        if age is None:
            state, detail = YELLOW, "回報時間無法判讀。"
        elif age <= WORKER_FRESH_SECONDS:
            state, detail = GREEN, f"{int(age // 60)} 分鐘前回報。"
        elif age <= WORKER_STALE_SECONDS:
            state, detail = YELLOW, f"已 {int(age // 60)} 分鐘沒有回報。"
        else:
            state, detail = RED, f"已超過 {int(age // 3600)} 小時沒有回報。"
        lights.append(_light(f"worker-{index}", f"Worker：{name}", state, detail))
    return lights


def storage_light(used_bytes: int | None, limit_bytes: int | None) -> dict[str, str]:
    if used_bytes is None:
        return _light("storage", "R2 儲存", GRAY, "目前讀不到用量。")
    gigabytes = used_bytes / 1024 ** 3
    if not limit_bytes:
        return _light("storage", "R2 儲存", GRAY, f"已用約 {gigabytes:.2f} GB（尚未設定用量上限）。")
    ratio = used_bytes / limit_bytes
    state = GREEN if ratio < 0.7 else YELLOW if ratio < 0.9 else RED
    return _light("storage", "R2 儲存", state, f"已用約 {gigabytes:.2f} GB（{ratio * 100:.0f}% of 上限）。")


def traffic_light(alerts_this_month: int | None) -> dict[str, str]:
    if alerts_this_month is None:
        return _light("traffic", "本月流量", GRAY, "目前讀不到流量警示。")
    if alerts_this_month <= 0:
        return _light("traffic", "本月流量", GREEN, "本月沒有流量警示。")
    return _light("traffic", "本月流量", YELLOW, f"本月已有 {alerts_this_month} 則流量警示，請查看流量設定。")


def _scalar(sql: str, params: tuple = ()) -> Any:
    from teacher_app.common import db as common_db

    with common_db.read_connection() as (conn, _kind):
        row = conn.execute(sql, params).fetchone()
    return None if row is None else list(dict(row).values())[0]


def collect(*, health_state: Callable[[], dict[str, Any]], now: dt.datetime | None = None) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.timezone.utc)
    lights = [_light("web", "網站", GREEN, "網站本身運作中。")]
    state = health_state()
    lights.append(database_light(state[0] if isinstance(state, tuple) else state))
    try:
        from teacher_app.worker import repository as worker_repository

        lights += worker_lights(worker_repository.list_heartbeats(5), now)
    except Exception:
        lights.append(_light("worker", "教材 Worker", GRAY, "目前讀不到 Worker 狀態。"))
    try:
        used = int(_scalar("SELECT COALESCE(SUM(object_bytes),0) AS total FROM r2_usage_ledger WHERE deleted_at=''") or 0)
    except Exception:
        used = None
    try:
        limit = int(os.environ.get("R2_STORAGE_LIMIT_BYTES", "") or 0) or None
    except ValueError:
        limit = None
    lights.append(storage_light(used, limit))
    try:
        month = now.strftime("%Y-%m")
        count = int(_scalar("SELECT COUNT(*) AS n FROM traffic_alerts WHERE month=" + _placeholder(), (month,)) or 0)
    except Exception:
        count = None
    lights.append(traffic_light(count))
    order = {RED: 3, YELLOW: 2, GRAY: 1, GREEN: 0}
    overall = max((light["state"] for light in lights), key=lambda state: order[state])
    return {"overall": overall, "lights": lights, "checkedAt": now.isoformat()}


def _placeholder() -> str:
    from teacher_app.common import db as common_db

    _conn, kind = common_db.get_connection()
    try:
        return common_db.placeholder(kind)
    finally:
        _conn.close()
