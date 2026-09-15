"""Safe external-media adapters for Teacher 6.8.

External references are metadata only: this module never fetches, proxies, or
stages a remote video through R2, a worker, MEGA, or Google Drive.
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import re
from urllib.parse import parse_qs, urlparse

from flask import jsonify, request

DIRECT_HOSTS = {"media.example.edu"}  # deployment may add comma-separated hosts
VIDEO_TYPES = {".mp4", ".webm"}

def now(): return dt.datetime.now(dt.timezone.utc).isoformat()

def validate_external_url(value: str, allow_hosts=()) -> dict:
    """Return canonical provider data without making a network request."""
    raw = str(value or "").strip()
    if len(raw) > 2048: raise ValueError("媒體網址過長")
    p = urlparse(raw)
    if p.scheme != "https" or not p.hostname: raise ValueError("只允許 HTTPS 外部媒體網址")
    host = p.hostname.lower().rstrip(".")
    try:
        if ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback or ipaddress.ip_address(host).is_link_local:
            raise ValueError("不允許內部網路位址")
    except ValueError as exc:
        if str(exc) == "不允許內部網路位址": raise
    if host in {"localhost", "metadata.google.internal"} or host.endswith(".local"):
        raise ValueError("不允許內部網路位址")
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        vid = (parse_qs(p.query).get("v") or [p.path.strip("/")])[0]
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", vid or ""): raise ValueError("YouTube video id 無效")
        return {"provider":"youtube", "canonicalUrl":f"https://www.youtube.com/watch?v={vid}", "videoId":vid}
    if host in {"vimeo.com", "www.vimeo.com", "player.vimeo.com"}:
        vid = next((x for x in p.path.split("/") if x.isdigit()), "")
        if not vid: raise ValueError("Vimeo video id 無效")
        return {"provider":"vimeo", "canonicalUrl":f"https://vimeo.com/{vid}", "videoId":vid}
    configured = {x.strip().lower() for x in allow_hosts if x.strip()} | DIRECT_HOSTS
    if host not in configured or not any(p.path.lower().endswith(ext) for ext in VIDEO_TYPES):
        raise ValueError("此 direct video 網域或格式未被允許")
    return {"provider":"direct", "canonicalUrl":raw, "videoId":""}

def register_external_media(base):
    app=base.app
    if app.extensions.get("teacher_external_media_68_registered"): return app
    @app.put("/api/materials/<material_id>/external-media")
    def put_external_media(material_id):
        denied=base.require_admin()
        if denied: return denied
        if not base.get_material(material_id): return jsonify({"error":"找不到教材"}),404
        try: data=validate_external_url((request.get_json(silent=True) or {}).get("url"), app.config.get("DIRECT_MEDIA_ALLOWLIST", []))
        except ValueError as exc: return jsonify({"error":str(exc)}),400
        conn,kind=base._db_conn(); ph="%s" if kind=="postgres" else "?"; stamp=now()
        try:
            if kind=="postgres": conn.execute("INSERT INTO external_media(id,material_id,provider,canonical_url,video_id,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(material_id) DO UPDATE SET provider=EXCLUDED.provider,canonical_url=EXCLUDED.canonical_url,video_id=EXCLUDED.video_id,updated_at=EXCLUDED.updated_at", (material_id,material_id,data["provider"],data["canonicalUrl"],data["videoId"],stamp,stamp))
            else: conn.execute("INSERT INTO external_media(id,material_id,provider,canonical_url,video_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(material_id) DO UPDATE SET provider=excluded.provider,canonical_url=excluded.canonical_url,video_id=excluded.video_id,updated_at=excluded.updated_at", (material_id,material_id,data["provider"],data["canonicalUrl"],data["videoId"],stamp,stamp))
        finally: conn.close()
        return jsonify({"ok":True,"materialId":material_id,**data})
    @app.get("/api/materials/<material_id>/external-media")
    def get_external_media(material_id):
        if not base._current_user(): return jsonify({"error":"請先登入。","loginRequired":True}),401
        conn,kind=base._db_conn(); ph="%s" if kind=="postgres" else "?"
        try: row=conn.execute(f"SELECT provider,canonical_url,video_id FROM external_media WHERE material_id={ph}",(material_id,)).fetchone()
        finally: conn.close()
        if not row:return jsonify({"externalMedia":None})
        d=dict(row);return jsonify({"externalMedia":{"provider":d["provider"],"canonicalUrl":d["canonical_url"],"videoId":d["video_id"]}})
    app.extensions["teacher_external_media_68_registered"]=True
    return app
