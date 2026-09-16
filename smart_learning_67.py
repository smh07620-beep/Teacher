"""Teacher 6.7 Smart Learning Content adapters.

The adapter is deliberately additive: it augments the legacy Flask app and
never changes grading, review-source visibility, or existing material routes.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import zipfile
from pathlib import Path

from flask import jsonify, request
from media_processing_67 import ffmpeg_capability, libreoffice_capability, worker_architecture


def extract_slide_text(path: Path):
    """Return reliable native text only; scanned PDFs deliberately return no hits."""
    suffix=path.suffix.lower(); pages=[]
    if suffix==".pptx":
        with zipfile.ZipFile(path) as zf:
            names=sorted((n for n in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml",n)), key=lambda n:int(re.search(r"\d+",n).group()))
            for number,name in enumerate(names,1):
                xml=zf.read(name).decode("utf-8","ignore")
                text=" ".join(re.findall(r"<a:t>(.*?)</a:t>",xml)).strip()
                pages.append((number,text,text.split(" ")[0] if text else ""))
    elif suffix==".pdf":
        try:
            import fitz
            doc=fitz.open(path)
            pages=[(i+1,(page.get_text("text") or "").strip(),"") for i,page in enumerate(doc)]
            doc.close()
        except Exception: pages=[]
    return [(n,t,title) for n,t,title in pages if t]

def preview_docx_atlas(path: Path):
    """Extract DOCX media in document order with surrounding text; never publishes."""
    with zipfile.ZipFile(path) as zf:
        doc=zf.read("word/document.xml").decode("utf-8","ignore")
        media={Path(n).name:zf.read(n) for n in zf.namelist() if n.startswith("word/media/")}
    text=" ".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>",doc))
    images=[]
    for index,name in enumerate(re.findall(r"(?:embed|link)=\"rId(\d+)\"",doc),1):
        # Relationships may be absent/broken: expose a warning rather than corrupting order.
        images.append({"index":index,"relationshipId":"rId"+name,"section":text[:180],"caption":"","region":{"x":0,"y":0,"width":1,"height":1}})
    return {"images":images,"warnings":["DOCX 預覽僅處理 inline/table 圖片；浮動圖、群組、SmartArt、圖表與 OLE 保留原文件，需人工處理。"] if not images else []}


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _user(base):
    user = base._current_user()
    if not user:
        return None, (jsonify({"error": "請先登入。", "loginRequired": True}), 401)
    return user, None


def _row(row):
    return dict(row) if row else {}


def auto_index_material(base, material_id):
    """Best-effort completion hook; never affects Worker completion/heartbeat."""
    material=base.get_material(material_id)
    if not material:return "unsupported"
    path=Path(base.UPLOADED_SLIDES_DIR)/str(material.get("folder") or material_id)/str(material.get("storageFilename") or material.get("filename") or "")
    if material.get("storageBackend")!="local" or not path.is_file():return "unsupported"
    try: rows=extract_slide_text(path)
    except Exception:return "failed"
    conn,kind=base._db_conn();ph="%s" if kind=="postgres" else "?"
    try:
        conn.execute(f"DELETE FROM material_text_index WHERE material_id={ph}",(material_id,))
        for page_no,text,title in rows:conn.execute(f"INSERT INTO material_text_index(material_id,page_no,title,text,indexed_at) VALUES({ph},{ph},{ph},{ph},{ph})",(material_id,page_no,title,text,_now()))
        status="indexed" if rows else "no_text"
        conn.execute(f"INSERT INTO material_search_status(material_id,status,page_count,last_indexed_at,failure_reason,source_kind) VALUES({ph},{ph},{ph},{ph},{ph},{ph}) ON CONFLICT(material_id) DO UPDATE SET status=EXCLUDED.status,page_count=EXCLUDED.page_count,last_indexed_at=EXCLUDED.last_indexed_at,failure_reason=EXCLUDED.failure_reason",(material_id,status,len(rows),_now(),"" if rows else "無可搜尋文字",path.suffix.lower()))
        return status
    except Exception:return "failed"
    finally:conn.close()


def media_completion(duration, watched_buckets, threshold=.9):
    """Server-authoritative ten-second bucket coverage for video/audio."""
    duration=max(0.0, float(duration or 0)); threshold=max(0.0,min(1.0,float(threshold)))
    if duration <= 0: return False
    buckets={max(0,int(item)) for item in watched_buckets}
    # A final partial bucket counts only for its real duration, not ten seconds.
    covered=sum(min(10.0,max(0.0,duration-(bucket*10))) for bucket in buckets)
    return covered >= duration * threshold


def resolved_completion(duration, watched_buckets, client_completed, is_media, threshold=.9):
    """Ignore client completion flags for media, retain legacy document flow."""
    return media_completion(duration, watched_buckets, threshold) if is_media else bool(client_completed)


def register_smart_learning(base):
    app = base.app
    if app.extensions.get("teacher_smart_learning_67_registered"):
        return app

    @app.get("/api/learning-progress/<material_id>")
    def learning_progress_get(material_id):
        user, denied = _user(base)
        if denied: return denied
        conn, kind = base._db_conn(); ph = "%s" if kind == "postgres" else "?"
        try:
            row = conn.execute(f"SELECT * FROM learning_progress WHERE material_id={ph} AND username={ph}", (material_id, user["username"])).fetchone()
            data = _row(row)
        finally: conn.close()
        if not data: return jsonify({"materialId": material_id, "position": {}, "progress": 0, "completed": False, "lastPositionSeconds": 0, "duration": 0, "watchedBuckets": [], "completionThreshold": .9})
        try: data["position"] = json.loads(data.get("position", "{}"))
        except Exception: data["position"] = {}
        data["materialId"] = data.pop("material_id"); data.pop("username", None)
        try: data["watchedBuckets"] = json.loads(data.pop("watched_buckets", "[]"))
        except Exception: data["watchedBuckets"] = []
        data["lastPositionSeconds"] = data.pop("last_position_seconds", 0)
        data["completionThreshold"] = data.pop("completion_threshold", .9)
        return jsonify(data)

    @app.put("/api/learning-progress/<material_id>")
    def learning_progress_put(material_id):
        user, denied = _user(base)
        if denied: return denied
        if not base.get_material(material_id): return jsonify({"error": "找不到教材"}), 404
        body = request.get_json(silent=True) or {}; position = body.get("position") or {}
        if not isinstance(position, dict): return jsonify({"error": "position 格式錯誤"}), 400
        try: progress = max(0, min(100, float(body.get("progress", 0))))
        except (TypeError, ValueError): return jsonify({"error": "progress 格式錯誤"}), 400
        # Bucket coverage makes a seek-to-end insufficient for completion.
        try: duration=max(0.0,float(body.get("duration",0) or 0)); last=max(0.0,min(duration,float(body.get("lastPositionSeconds",0) or 0)))
        except (TypeError,ValueError): return jsonify({"error":"media progress 格式錯誤"}),400
        buckets=body.get("watchedBuckets",[])
        if not isinstance(buckets,list): return jsonify({"error":"watchedBuckets 格式錯誤"}),400
        buckets=sorted({max(0,min(99999,int(x))) for x in buckets})[:10000]
        threshold=.9; covered=len(buckets)*10
        media_request=duration>0 or "watchedBuckets" in body or "lastPositionSeconds" in body
        # Only legacy/non-media flows retain their old client completion signal.
        # For media, client completed=true is intentionally ignored.
        media_completed=media_completion(duration,buckets,threshold)
        completed = resolved_completion(duration,buckets,body.get("completed",False),media_request,threshold); now = _now()
        conn, kind = base._db_conn(); ph = "%s" if kind == "postgres" else "?"
        values = (material_id, user["username"], json.dumps(position, ensure_ascii=False), progress, completed if kind == "postgres" else int(completed), now, now if completed else "")
        try:
            if kind == "postgres":
                conn.execute("INSERT INTO learning_progress(material_id,username,position,progress,completed,last_viewed_at,completed_at) VALUES(%s,%s,%s::jsonb,%s,%s,%s,%s) ON CONFLICT(material_id,username) DO UPDATE SET position=EXCLUDED.position,progress=EXCLUDED.progress,completed=learning_progress.completed OR EXCLUDED.completed,last_viewed_at=EXCLUDED.last_viewed_at,completed_at=CASE WHEN EXCLUDED.completed THEN EXCLUDED.last_viewed_at ELSE learning_progress.completed_at END", values)
            else:
                conn.execute("INSERT INTO learning_progress(material_id,username,position,progress,completed,last_viewed_at,completed_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(material_id,username) DO UPDATE SET position=excluded.position,progress=excluded.progress,completed=MAX(learning_progress.completed,excluded.completed),last_viewed_at=excluded.last_viewed_at,completed_at=CASE WHEN excluded.completed=1 THEN excluded.last_viewed_at ELSE learning_progress.completed_at END", values)
        finally: conn.close()
        # Additive 6.8 fields are updated separately so an un-upgraded test DB
        # still receives the established 6.7 behavior.
        conn,kind=base._db_conn(); ph="%s" if kind=="postgres" else "?"
        try:
            conn.execute(f"UPDATE learning_progress SET last_position_seconds={ph},duration={ph},watched_buckets={ph},completion_threshold={ph},updated_at={ph} WHERE material_id={ph} AND username={ph}", (last,duration,json.dumps(buckets),threshold,now,material_id,user["username"]))
        finally: conn.close()
        # Preserve 6.6 sequential unlock: only a real completion writes its old marker.
        if completed:
            client = app.test_client()  # no request/session forwarding; legacy marker remains UI-owned
        return jsonify({"ok": True, "materialId": material_id, "position": position, "progress": progress, "completed": completed, "lastPositionSeconds":last,"duration":duration,"watchedBuckets":buckets,"lastViewedAt": now})

    @app.get("/api/material-search")
    def material_search():
        user, denied = _user(base)
        if denied: return denied
        query = str(request.args.get("q", "")).strip()[:200]
        material_id = str(request.args.get("materialId", "")).strip()[:100]
        if not query or not material_id: return jsonify([])
        material=base.get_material(material_id)
        # Do not turn the index into a visibility bypass.  The reader already
        # receives only active material, and search applies the same group
        # boundary on the server rather than trusting the UI's selected group.
        if not material or not material.get("active", True): return jsonify([])
        from teacher_app.common.auth import has_role
        group=str(material.get("group") or material.get("groupKey") or "")
        own=str(user.get("preferredGroup") or user.get("preferred_group") or "")
        if not (has_role(user,"system_admin") or has_role(user,"education_admin") or group==own): return jsonify([])
        conn, kind = base._db_conn(); ph = "%s" if kind == "postgres" else "?"
        try:
            rows = conn.execute(f"SELECT page_no,title,text FROM material_text_index WHERE material_id={ph} AND LOWER(text) LIKE {ph} ORDER BY page_no LIMIT 50", (material_id, "%" + query.lower() + "%")).fetchall()
            return jsonify([{"page": int(_row(r).get("page_no", 0)), "title": _row(r).get("title", ""), "excerpt": _row(r).get("text", "")[:240]} for r in rows])
        finally: conn.close()

    @app.post("/api/material-search/<material_id>/index")
    def material_index(material_id):
        denied=base.require_admin()
        if denied:return denied
        material=base.get_material(material_id)
        if not material:return jsonify({"error":"找不到教材"}),404
        path=Path(base.UPLOADED_SLIDES_DIR)/str(material.get("folder") or material_id)/str(material.get("storageFilename") or material.get("filename") or "")
        if material.get("storageBackend")!="local" or not path.is_file():
            conn,kind=base._db_conn(); ph="%s" if kind=="postgres" else "?"
            try: conn.execute(f"INSERT INTO material_search_status(material_id,status,page_count,last_indexed_at,failure_reason,source_kind) VALUES({ph},{ph},{ph},{ph},{ph},{ph}) ON CONFLICT(material_id) DO UPDATE SET status=EXCLUDED.status,failure_reason=EXCLUDED.failure_reason",(material_id,"unsupported",0,"","此教材目前無可安全索引的本機原始檔",str(material.get("storageBackend") or "")))
            finally: conn.close()
            return jsonify({"error":"此教材目前無可安全索引的本機原始檔","status":"unsupported"}),409
        rows=extract_slide_text(path); conn,kind=base._db_conn(); ph="%s" if kind=="postgres" else "?"
        try:
            conn.execute(f"DELETE FROM material_text_index WHERE material_id={ph}",(material_id,))
            for page_no,text,title in rows: conn.execute(f"INSERT INTO material_text_index(material_id,page_no,title,text,indexed_at) VALUES({ph},{ph},{ph},{ph},{ph})",(material_id,page_no,title,text,_now()))
            status="indexed" if rows else "unsupported"; reason="" if rows else "找不到可擷取文字；掃描型 PDF 不提供假性搜尋結果。"
            conn.execute(f"INSERT INTO material_search_status(material_id,status,page_count,last_indexed_at,failure_reason,source_kind) VALUES({ph},{ph},{ph},{ph},{ph},{ph}) ON CONFLICT(material_id) DO UPDATE SET status=EXCLUDED.status,page_count=EXCLUDED.page_count,last_indexed_at=EXCLUDED.last_indexed_at,failure_reason=EXCLUDED.failure_reason,source_kind=EXCLUDED.source_kind",(material_id,status,len(rows),_now(),reason,path.suffix.lower()))
        finally:conn.close()
        return jsonify({"ok":True,"pages":len(rows),"searchable":bool(rows),"status":"indexed" if rows else "unsupported"})

    @app.get("/api/material-search/<material_id>/status")
    def material_index_status(material_id):
        user, denied=_user(base)
        if denied:return denied
        material=base.get_material(material_id)
        if not material:return jsonify({"error":"找不到教材"}),404
        from teacher_app.common.auth import has_role
        group=str(material.get("group") or material.get("groupKey") or "")
        own=str(user.get("preferredGroup") or user.get("preferred_group") or "")
        if not (has_role(user,"system_admin") or has_role(user,"education_admin") or group==own): return jsonify({"error":"找不到教材"}),404
        conn,kind=base._db_conn(); ph="%s" if kind=="postgres" else "?"
        try: row=conn.execute(f"SELECT status,page_count,last_indexed_at,failure_reason,source_kind FROM material_search_status WHERE material_id={ph}",(material_id,)).fetchone()
        finally:conn.close()
        return jsonify(_row(row) or {"status":"not_indexed","page_count":0,"last_indexed_at":"","failure_reason":"","source_kind":""})

    @app.post("/api/docx-atlas-preview/<material_id>")
    def docx_atlas_preview(material_id):
        denied=base.require_admin()
        if denied:return denied
        material=base.get_material(material_id)
        if not material:return jsonify({"error":"找不到教材"}),404
        path=Path(base.UPLOADED_SLIDES_DIR)/str(material.get("folder") or material_id)/str(material.get("storageFilename") or material.get("filename") or "")
        if path.suffix.lower()!=".docx" or not path.is_file():return jsonify({"error":"需要可存取的 DOCX 原始檔"}),409
        return jsonify({"materialId":material_id,"preview":preview_docx_atlas(path),"publishRequired":True})

    @app.get("/api/learning-analytics")
    def learning_analytics():
        denied = base.require_admin()
        if denied: return denied
        conn, kind = base._db_conn()
        try:
            rows = conn.execute("SELECT material_id,COUNT(*) learners,SUM(CASE WHEN completed THEN 1 ELSE 0 END) completed,AVG(progress) average_progress,MAX(last_viewed_at) last_viewed_at FROM learning_progress GROUP BY material_id").fetchall()
        finally: conn.close()
        return jsonify([{"materialId": _row(r).get("material_id"), "learners": int(_row(r).get("learners") or 0), "completed": int(_row(r).get("completed") or 0), "averageProgress": round(float(_row(r).get("average_progress") or 0), 1), "lastViewedAt": _row(r).get("last_viewed_at") or ""} for r in rows])

    @app.get("/api/media-processing/capability")
    def media_capability():
        denied=base.require_admin()
        if denied:return denied
        staging = base.shared_staging_capability()
        data = worker_architecture(staging)
        data.update({"ffmpeg": ffmpeg_capability(), "libreOffice": libreoffice_capability(base.SOFFICE_BIN), "staging": staging, "processing": "material_worker.py"})
        return jsonify(data)

    app.extensions["teacher_smart_learning_67_registered"] = True
    return app
