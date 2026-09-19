"""Canonical external-media validation and persistence.

External references are metadata only. This module never fetches, proxies, or
stages a remote video through object storage or the material worker.
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import json
import re
import uuid
from collections.abc import Callable
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse, urlunparse

from teacher_app.assessments import repository as assessment_repository
from teacher_app.common import db as common_db
from teacher_app.common import scope
from teacher_app.common.errors import ApiError
from teacher_app.courses import repository as course_repository
from teacher_app.materials import repository as material_repository


PROVIDER_REGISTRY = {
    "youtube": {
        "input_hosts": frozenset({
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "youtu.be",
            "youtube-nocookie.com",
            "www.youtube-nocookie.com",
        }),
        "verification_hosts": frozenset({"youtube.com", "www.youtube.com"}),
        "oembed_endpoint": "https://www.youtube.com/oembed",
        "privacy_playback_origin": "https://www.youtube-nocookie.com",
    },
    "vimeo": {
        "input_hosts": frozenset({"vimeo.com", "www.vimeo.com", "player.vimeo.com"}),
        "verification_hosts": frozenset({"vimeo.com", "www.vimeo.com"}),
        "oembed_endpoint": "https://vimeo.com/api/oembed.json",
        "playback_origin": "https://player.vimeo.com",
    },
}

# Historical import compatibility only.  There is deliberately no built-in
# direct-video host: hospital CDN access must be explicitly configured.
DIRECT_HOSTS = frozenset()
VIDEO_TYPES = frozenset({".mp4", ".webm"})
AVAILABILITY_STATUSES = frozenset({"unverified", "available", "unavailable", "error"})


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize_hospital_cdn_hosts(allow_hosts=()) -> frozenset[str]:
    hosts: set[str] = set()
    for item in allow_hosts or ():
        host = str(item or "").strip().lower().rstrip(".")
        if host.startswith("[") and host.endswith("]"):
            host = host[1:-1]
        if not host or "://" in host or "/" in host or "*" in host:
            continue
        # host:port is configuration ambiguity; IPv6 literals contain more
        # than one colon and remain valid exact host identities.
        if host.count(":") == 1:
            continue
        hosts.add(host)
    return frozenset(hosts)


def _is_local_or_private_host(host: str) -> bool:
    if host in {"localhost", "metadata.google.internal"} or host.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_unspecified
        or address.is_reserved
    )


def _playback_url(provider: str, canonical_url: str, video_id: str) -> str:
    if provider == "youtube" and video_id:
        origin = PROVIDER_REGISTRY["youtube"]["privacy_playback_origin"]
        return f"{origin}/embed/{video_id}?rel=0&enablejsapi=1"
    if provider == "vimeo" and video_id:
        origin = PROVIDER_REGISTRY["vimeo"]["playback_origin"]
        return f"{origin}/video/{video_id}?autoplay=0&dnt=1"
    return canonical_url


def _provider_metadata_for_validated(data: Mapping[str, Any]) -> dict:
    metadata = dict(data.get("providerMetadata") or {}) if isinstance(data.get("providerMetadata"), Mapping) else {}
    playback = str(data.get("playbackUrl") or "").strip()
    if playback:
        metadata["playbackUrl"] = playback[:2048]
    return metadata


def validate_external_url(value: str, allow_hosts=()) -> dict:
    """Return canonical provider data without making a network request."""
    raw = str(value or "").strip()
    if len(raw) > 2048:
        raise ValueError("媒體網址過長")

    parsed = urlparse(raw)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("只允許 HTTPS 外部媒體網址")
    if parsed.username or parsed.password:
        raise ValueError("外部媒體網址不可包含帳號資訊")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("外部媒體網址連接埠無效") from exc
    if port not in (None, 443):
        raise ValueError("外部媒體僅允許標準 HTTPS 連接埠")

    host = parsed.hostname.lower().rstrip(".")
    configured = normalize_hospital_cdn_hosts(allow_hosts)
    if _is_local_or_private_host(host) and host not in configured:
        raise ValueError("不允許內部網路位址")

    if host in PROVIDER_REGISTRY["youtube"]["input_hosts"]:
        parts = [part for part in parsed.path.split("/") if part]
        video_id = ""
        if host == "youtu.be" and parts:
            video_id = parts[0]
        elif parts and parts[0] in {"shorts", "embed"} and len(parts) >= 2:
            video_id = parts[1]
        elif parsed.path.rstrip("/") == "/watch":
            video_id = (parse_qs(parsed.query).get("v") or [""])[0]
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id or ""):
            raise ValueError("YouTube video id 無效")
        canonical = f"https://www.youtube.com/watch?v={video_id}"
        return {
            "provider": "youtube",
            "canonicalUrl": canonical,
            "videoId": video_id,
            "playbackUrl": _playback_url("youtube", canonical, video_id),
            "providerMetadata": {"providerKind": "youtube"},
        }

    if host in PROVIDER_REGISTRY["vimeo"]["input_hosts"]:
        parts = [part for part in parsed.path.split("/") if part]
        video_id = ""
        if host == "player.vimeo.com" and len(parts) >= 2 and parts[0] == "video":
            video_id = parts[1]
        elif parts:
            video_id = parts[0]
        if not re.fullmatch(r"[0-9]{6,12}", video_id or ""):
            raise ValueError("Vimeo video id 無效")
        canonical = f"https://vimeo.com/{video_id}"
        return {
            "provider": "vimeo",
            "canonicalUrl": canonical,
            "videoId": video_id,
            "playbackUrl": _playback_url("vimeo", canonical, video_id),
            "providerMetadata": {"providerKind": "vimeo"},
        }

    if host not in configured or not any(parsed.path.lower().endswith(ext) for ext in VIDEO_TYPES):
        raise ValueError("此 direct video 網域或格式未被允許")

    canonical = urlunparse(("https", parsed.netloc, parsed.path, parsed.params, parsed.query, ""))
    return {
        "provider": "direct",
        "canonicalUrl": canonical,
        "videoId": "",
        "playbackUrl": canonical,
        "providerMetadata": {"providerKind": "hospital_cdn", "cdnHost": host},
    }


def _validated(value: Any, allow_hosts=()) -> dict:
    try:
        return validate_external_url(value, allow_hosts)
    except ValueError as exc:
        raise ApiError("EXTERNAL_MEDIA_INVALID", str(exc), status=400) from exc


def _media_values(material_id: str, data: Mapping[str, Any], stamp: str) -> tuple:
    return (
        material_id,
        material_id,
        data["provider"],
        data["canonicalUrl"],
        data["videoId"],
        stamp,
        stamp,
    )


def _table_columns(conn, kind: str) -> set[str]:
    if kind == "postgres":
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name=%s",
            ("external_media",),
        ).fetchall()
        return {str(dict(row).get("column_name") or "").lower() for row in rows}
    return {str(row[1]).lower() for row in conn.execute("PRAGMA table_info(external_media)").fetchall()}


def _json_object(value: Any) -> dict:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return dict(parsed) if isinstance(parsed, Mapping) else {}
        except Exception:
            return {}
    return {}


def _write_validation_metadata(conn, kind: str, material_id: str, data: Mapping[str, Any]) -> None:
    columns = _table_columns(conn, kind)
    if not {"availability_status", "provider_metadata"}.issubset(columns):
        return
    ph = common_db.placeholder(kind)
    payload = json.dumps(
        _provider_metadata_for_validated(data),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    conn.execute(
        "UPDATE external_media SET availability_status=" + ph + ",last_verified_at=" + ph
        + ",last_error=" + ph + ",provider_metadata=" + ph + " WHERE material_id=" + ph,
        ("unverified", "", "", payload, material_id),
    )


def _insert_media_on_connection(conn, kind: str, material_id: str, data: Mapping[str, Any], stamp: str) -> None:
    ph = common_db.placeholder(kind)
    conn.execute(
        "INSERT INTO external_media"
        "(id,material_id,provider,canonical_url,video_id,created_at,updated_at) "
        f"VALUES({','.join([ph] * 7)})",
        _media_values(material_id, data, stamp),
    )
    _write_validation_metadata(conn, kind, material_id, data)


def _upsert_media_on_connection(conn, kind: str, material_id: str, data: Mapping[str, Any], stamp: str) -> None:
    values = _media_values(material_id, data, stamp)
    if kind == "postgres":
        conn.execute(
            "INSERT INTO external_media"
            "(id,material_id,provider,canonical_url,video_id,created_at,updated_at) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT(material_id) DO UPDATE SET "
            "provider=EXCLUDED.provider,canonical_url=EXCLUDED.canonical_url,"
            "video_id=EXCLUDED.video_id,updated_at=EXCLUDED.updated_at",
            values,
        )
    else:
        conn.execute(
            "INSERT INTO external_media"
            "(id,material_id,provider,canonical_url,video_id,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(material_id) DO UPDATE SET "
            "provider=excluded.provider,canonical_url=excluded.canonical_url,"
            "video_id=excluded.video_id,updated_at=excluded.updated_at",
            values,
        )
    _write_validation_metadata(conn, kind, material_id, data)


def set_external_media(material_id: str, value: Any, allow_hosts=()) -> dict:
    """Attach or replace external-media metadata for an existing material."""
    if not material_repository.get_material(material_id):
        raise ApiError("MATERIAL_NOT_FOUND", "找不到教材", status=404)

    data = _validated(value, allow_hosts)
    stamp = now()
    with common_db.transaction() as (conn, kind):
        _upsert_media_on_connection(conn, kind, material_id, data, stamp)
    return data


def create_external_material(
    body: Mapping[str, Any],
    allow_hosts=(),
    *,
    material_loader: Callable[[str], dict | None] | None = None,
) -> dict:
    """Create external video metadata without object storage or worker work.

    ``material_loader`` preserves the caller's historical response projection;
    persistence and validation remain canonical here.
    """
    data = _validated(body.get("url"), allow_hosts)

    title = str(body.get("title") or "").strip()[:255]
    if not title:
        raise ApiError("MATERIAL_TITLE_REQUIRED", "請輸入教材名稱", status=400)

    group = scope.normalize_group(body.get("group") or scope.DEFAULT_GROUP)
    area = scope.normalize_area(body.get("area") or scope.DEFAULT_TRAINING_AREA)
    course_id = str(body.get("courseId") or "").strip()
    category = str(body.get("category") or "").strip()

    if course_id:
        course = course_repository.get_course(course_id)
        if not course or course.get("group") != group or course.get("area") != area:
            raise ApiError("COURSE_SCOPE_MISMATCH", "所屬課程不在相同訓練區／組別", status=400)

    if category:
        quiz = assessment_repository.get_category(category)
        if not quiz or quiz.get("group") != group or quiz.get("area") != area:
            raise ApiError("ASSESSMENT_SCOPE_MISMATCH", "關聯考卷不在相同訓練區／組別", status=400)

    material_id = f"external-{uuid.uuid4().hex[:16]}"
    stamp = now()
    extension = (
        ".webm"
        if data["provider"] == "direct"
        and data["canonicalUrl"].lower().split("?")[0].endswith(".webm")
        else ".mp4"
    )
    filename = f"external{extension}"
    storage_meta = json.dumps(
        {
            "external": True,
            "provider": data["provider"],
            "canonicalUrl": data["canonicalUrl"],
        },
        ensure_ascii=False,
    )
    entry = {
        "id": material_id,
        "filename": filename,
        "title": title,
        "description": str(body.get("description") or "")[:1000],
        "category": category,
        "group_key": group,
        "training_area": area,
        "course_id": course_id,
        "folder": material_id,
        "page_count": 0,
        "date_added": stamp,
        "storage_filename": filename,
        "storage_backend": "external",
        "storage_key": "",
        "slides_prefix": "",
        "storage_meta": storage_meta,
        "material_type": "video",
        "atlas_meta": "{}",
        "active": True,
    }

    with common_db.transaction() as (conn, kind):
        material_repository.insert_material_on_connection(conn, kind, entry)
        _insert_media_on_connection(conn, kind, material_id, data, stamp)

    loader = material_loader or material_repository.get_material
    return {
        "material": loader(material_id),
        "externalMedia": data,
    }


def get_external_media(material_id: str) -> dict | None:
    with common_db.read_connection() as (conn, kind):
        ph = common_db.placeholder(kind)
        columns = _table_columns(conn, kind)
        selected = ["provider", "canonical_url", "video_id"]
        for column in ("last_verified_at", "availability_status", "last_error", "provider_metadata"):
            if column in columns:
                selected.append(column)
        row = conn.execute(
            f"SELECT {','.join(selected)} FROM external_media WHERE material_id={ph}",
            (material_id,),
        ).fetchone()
    if not row:
        return None
    data = dict(row)
    provider = str(data["provider"] or "")
    canonical = str(data["canonical_url"] or "")
    video_id = str(data["video_id"] or "")
    provider_metadata = _json_object(data.get("provider_metadata"))
    return {
        "provider": provider,
        "canonicalUrl": canonical,
        "videoId": video_id,
        "playbackUrl": _playback_url(provider, canonical, video_id),
        "lastVerifiedAt": str(data.get("last_verified_at") or ""),
        "availabilityStatus": str(data.get("availability_status") or "unverified"),
        "lastError": str(data.get("last_error") or ""),
        "providerMetadata": provider_metadata,
    }


def list_external_media_report(*, status: str = "", limit: int = 200) -> list[dict]:
    wanted_status = str(status or "").strip().lower()
    if wanted_status and wanted_status not in AVAILABILITY_STATUSES:
        raise ApiError("EXTERNAL_MEDIA_STATUS_INVALID", "外部影音狀態篩選無效", status=400)
    bounded_limit = max(1, min(500, int(limit or 200)))
    with common_db.read_connection() as (conn, kind):
        columns = _table_columns(conn, kind)
        selected = [
            "e.material_id AS material_id",
            "e.provider AS provider",
            "e.canonical_url AS canonical_url",
            "e.video_id AS video_id",
            "e.updated_at AS updated_at",
            "m.title AS title",
            "m.group_key AS group_key",
            "m.training_area AS training_area",
            "m.active AS active",
        ]
        for column in ("last_verified_at", "availability_status", "last_error", "provider_metadata"):
            if column in columns:
                selected.append(f"e.{column} AS {column}")
        ph = common_db.placeholder(kind)
        params: list[Any] = []
        where = ""
        if wanted_status and "availability_status" in columns:
            where = f" WHERE e.availability_status={ph}"
            params.append(wanted_status)
        params.append(bounded_limit)
        rows = conn.execute(
            f"SELECT {','.join(selected)} FROM external_media e "
            "LEFT JOIN materials m ON m.id=e.material_id"
            + where
            + f" ORDER BY e.updated_at DESC LIMIT {ph}",
            tuple(params),
        ).fetchall()
    items: list[dict] = []
    for row in rows:
        data = dict(row)
        availability = str(data.get("availability_status") or "unverified")
        if wanted_status and availability != wanted_status:
            continue
        provider = str(data.get("provider") or "")
        canonical = str(data.get("canonical_url") or "")
        video_id = str(data.get("video_id") or "")
        items.append({
            "materialId": str(data.get("material_id") or ""),
            "title": str(data.get("title") or ""),
            "group": str(data.get("group_key") or ""),
            "area": str(data.get("training_area") or ""),
            "active": bool(data.get("active")),
            "provider": provider,
            "canonicalUrl": canonical,
            "videoId": video_id,
            "playbackUrl": _playback_url(provider, canonical, video_id),
            "availabilityStatus": availability,
            "lastVerifiedAt": str(data.get("last_verified_at") or ""),
            "lastError": str(data.get("last_error") or ""),
            "providerMetadata": _json_object(data.get("provider_metadata")),
        })
    return items


def _persist_verification(material_id: str, result: Mapping[str, Any]) -> None:
    status = str(result.get("availabilityStatus") or "error").strip().lower()
    if status not in AVAILABILITY_STATUSES - {"unverified"}:
        status = "error"
    verified_at = str(result.get("lastVerifiedAt") or now())[:64]
    last_error = str(result.get("lastError") or "")[:1000]
    provider_metadata = _json_object(result.get("providerMetadata"))
    with common_db.transaction() as (conn, kind):
        columns = _table_columns(conn, kind)
        required = {"last_verified_at", "availability_status", "last_error", "provider_metadata"}
        if not required.issubset(columns):
            raise ApiError(
                "EXTERNAL_MEDIA_SCHEMA_REQUIRED",
                "外部影音驗證欄位尚未完成資料庫 migration。",
                status=503,
            )
        ph = common_db.placeholder(kind)
        payload = json.dumps(
            provider_metadata,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        conn.execute(
            "UPDATE external_media SET last_verified_at=" + ph + ",availability_status=" + ph
            + ",last_error=" + ph + ",provider_metadata=" + ph + ",updated_at=" + ph
            + " WHERE material_id=" + ph,
            (verified_at, status, last_error, payload, now(), material_id),
        )


def verify_external_media(
    material_id: str,
    *,
    allow_hosts=(),
    http_request=None,
    timeout_seconds: float = 5.0,
) -> dict:
    media = get_external_media(material_id)
    if not media:
        raise ApiError("EXTERNAL_MEDIA_NOT_FOUND", "找不到外部影音設定", status=404)
    from teacher_app.materials.external_media_verification import verify_media

    result = verify_media(
        media,
        hospital_hosts=normalize_hospital_cdn_hosts(allow_hosts),
        http_request=http_request,
        timeout_seconds=timeout_seconds,
    )
    merged_metadata = dict(media.get("providerMetadata") or {})
    merged_metadata.update(_json_object(result.get("providerMetadata")))
    result = {**result, "providerMetadata": merged_metadata}
    _persist_verification(material_id, result)
    return get_external_media(material_id) or media


def verify_due_external_media(
    *,
    allow_hosts=(),
    older_than_minutes: int = 360,
    limit: int = 100,
    http_request=None,
) -> dict:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
        minutes=max(1, min(7 * 24 * 60, int(older_than_minutes or 360)))
    )
    candidates = list_external_media_report(limit=max(1, min(500, int(limit or 100))))
    due: list[dict] = []
    for item in candidates:
        stamp = str(item.get("lastVerifiedAt") or "").strip()
        if not stamp:
            due.append(item)
            continue
        try:
            parsed = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            if parsed <= cutoff:
                due.append(item)
        except ValueError:
            due.append(item)
    results: list[dict] = []
    for item in due[: max(1, min(500, int(limit or 100)))]:
        material_id = str(item.get("materialId") or "")
        try:
            verified = verify_external_media(
                material_id,
                allow_hosts=allow_hosts,
                http_request=http_request,
            )
            results.append({
                "materialId": material_id,
                "availabilityStatus": verified.get("availabilityStatus", "error"),
                "lastVerifiedAt": verified.get("lastVerifiedAt", ""),
            })
        except Exception as exc:
            results.append({
                "materialId": material_id,
                "availabilityStatus": "error",
                "lastError": str(exc)[:500],
            })
    counts = {status: 0 for status in ("available", "unavailable", "error")}
    for item in results:
        status = str(item.get("availabilityStatus") or "error")
        counts[status if status in counts else "error"] += 1
    return {"checked": len(results), "counts": counts, "items": results}
