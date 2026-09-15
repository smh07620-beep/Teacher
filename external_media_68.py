"""Safe external-media adapters for Teacher 6.8.

External references are metadata only: this module never fetches, proxies, or
stages a remote video through R2, a worker, MEGA, or Google Drive.
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import json
import re
import uuid
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
        parts=[part for part in p.path.split("/") if part]
        vid = (parse_qs(p.query).get("v") or ([parts[1]] if len(parts)>=2 and parts[0]=="shorts" else [p.path.strip("/")]))[0]
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", vid or ""): raise ValueError("YouTube video id 無效")
        return {"provider":"youtube", "canonicalUrl":f"https://www.youtube.com/watch?v={vid}", "videoId":vid}
    if host in {"vimeo.com", "www.vimeo.com", "player.vimeo.com"}:
        raise ValueError("目前僅支援 YouTube、YouTube Shorts 與核准的 HTTPS MP4/WebM。")
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
    @app.post("/api/materials/external")
    def create_external_material():
        """Create an external video record without fetching or storing it.

        The URL is validated before a material exists.  The resulting record
        deliberately has no object-store key, upload job, or worker request.
        """
        denied=base.require_admin()
        if denied:return denied
        body=request.get_json(silent=True) or {}
        try:data=validate_external_url(body.get("url"),app.config.get("DIRECT_MEDIA_ALLOWLIST",[]))
        except ValueError as exc:return jsonify({"error":str(exc)}),400
        title=str(body.get("title") or "").strip()[:255]
        if not title:return jsonify({"error":"請輸入教材名稱"}),400
        group=base.normalize_group(str(body.get("group") or base.DEFAULT_GROUP))
        area=base.normalize_area(str(body.get("area") or base.DEFAULT_TRAINING_AREA))
        course_id=str(body.get("courseId") or "").strip()
        category=str(body.get("category") or "").strip()
        if course_id:
            course=base.get_course(course_id)
            if not course or course.get("group")!=group or course.get("area")!=area:return jsonify({"error":"所屬課程不在相同訓練區／組別"}),400
        if category:
            quiz=base.get_quiz_category(category)
            if not quiz or quiz.get("group")!=group or quiz.get("area")!=area:return jsonify({"error":"關聯考卷不在相同訓練區／組別"}),400
        material_id=f"external-{uuid.uuid4().hex[:16]}"; stamp=now()
        extension=".webm" if data["provider"]=="direct" and data["canonicalUrl"].lower().split("?")[0].endswith(".webm") else ".mp4"
        filename=f"external{extension}"
        meta=json.dumps({"external":True,"provider":data["provider"],"canonicalUrl":data["canonicalUrl"]},ensure_ascii=False)
        conn,kind=base._db_conn();ph="%s" if kind=="postgres" else "?"
        try:
            values=(material_id,filename,title,str(body.get("description") or "")[:1000],category,group,area,material_id,0,stamp,filename,"external","","",meta,"video","{}",True if kind=="postgres" else 1,course_id)
            conn.execute(f"INSERT INTO materials(id,filename,title,description,category,group_key,training_area,folder,page_count,date_added,storage_filename,storage_backend,storage_key,slides_prefix,storage_meta,material_type,atlas_meta,active,course_id) VALUES({','.join([ph]*19)})",values)
            media_values=(material_id,material_id,data["provider"],data["canonicalUrl"],data["videoId"],stamp,stamp)
            conn.execute(f"INSERT INTO external_media(id,material_id,provider,canonical_url,video_id,created_at,updated_at) VALUES({','.join([ph]*7)})",media_values)
        finally:conn.close()
        item=base.get_material(material_id)
        return jsonify({"ok":True,"material":item,"externalMedia":data}),201
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
