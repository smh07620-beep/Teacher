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
from urllib.parse import parse_qs, urlparse

from teacher_app.assessments import repository as assessment_repository
from teacher_app.common import db as common_db
from teacher_app.common import scope
from teacher_app.common.errors import ApiError
from teacher_app.courses import repository as course_repository
from teacher_app.materials import repository as material_repository


DIRECT_HOSTS = {"media.example.edu"}
VIDEO_TYPES = {".mp4", ".webm"}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def validate_external_url(value: str, allow_hosts=()) -> dict:
    """Return canonical provider data without making a network request."""
    raw = str(value or "").strip()
    if len(raw) > 2048:
        raise ValueError("媒體網址過長")

    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("只允許 HTTPS 外部媒體網址")

    host = parsed.hostname.lower().rstrip(".")
    try:
        address = ipaddress.ip_address(host)
        if address.is_private or address.is_loopback or address.is_link_local:
            raise ValueError("不允許內部網路位址")
    except ValueError as exc:
        if str(exc) == "不允許內部網路位址":
            raise

    if host in {"localhost", "metadata.google.internal"} or host.endswith(".local"):
        raise ValueError("不允許內部網路位址")

    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        parts = [part for part in parsed.path.split("/") if part]
        video_id = (
            parse_qs(parsed.query).get("v")
            or ([parts[1]] if len(parts) >= 2 and parts[0] == "shorts" else [parsed.path.strip("/")])
        )[0]
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id or ""):
            raise ValueError("YouTube video id 無效")
        return {
            "provider": "youtube",
            "canonicalUrl": f"https://www.youtube.com/watch?v={video_id}",
            "videoId": video_id,
        }

    if host in {"vimeo.com", "www.vimeo.com", "player.vimeo.com"}:
        raise ValueError("目前僅支援 YouTube、YouTube Shorts 與核准的 HTTPS MP4/WebM。")

    configured = {str(item).strip().lower() for item in allow_hosts if str(item).strip()} | DIRECT_HOSTS
    if host not in configured or not any(parsed.path.lower().endswith(ext) for ext in VIDEO_TYPES):
        raise ValueError("此 direct video 網域或格式未被允許")

    return {"provider": "direct", "canonicalUrl": raw, "videoId": ""}


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


def _insert_media_on_connection(conn, kind: str, material_id: str, data: Mapping[str, Any], stamp: str) -> None:
    ph = common_db.placeholder(kind)
    conn.execute(
        "INSERT INTO external_media"
        "(id,material_id,provider,canonical_url,video_id,created_at,updated_at) "
        f"VALUES({','.join([ph] * 7)})",
        _media_values(material_id, data, stamp),
    )


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
        return

    conn.execute(
        "INSERT INTO external_media"
        "(id,material_id,provider,canonical_url,video_id,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?) "
        "ON CONFLICT(material_id) DO UPDATE SET "
        "provider=excluded.provider,canonical_url=excluded.canonical_url,"
        "video_id=excluded.video_id,updated_at=excluded.updated_at",
        values,
    )


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
        row = conn.execute(
            f"SELECT provider,canonical_url,video_id FROM external_media WHERE material_id={ph}",
            (material_id,),
        ).fetchone()
    if not row:
        return None
    data = dict(row)
    return {
        "provider": data["provider"],
        "canonicalUrl": data["canonical_url"],
        "videoId": data["video_id"],
    }
