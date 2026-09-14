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


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _user(base):
    user = base._current_user()
    if not user:
        return None, (jsonify({"error": "請先登入。", "loginRequired": True}), 401)
    return user, None


def _row(row):
    return dict(row) if row else {}


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
        if not data: return jsonify({"materialId": material_id, "position": {}, "progress": 0, "completed": False})
        try: data["position"] = json.loads(data.get("position", "{}"))
        except Exception: data["position"] = {}
        data["materialId"] = data.pop("material_id"); data.pop("username", None)
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
        completed = bool(body.get("completed", False)); now = _now()
        conn, kind = base._db_conn(); ph = "%s" if kind == "postgres" else "?"
        values = (material_id, user["username"], json.dumps(position, ensure_ascii=False), progress, completed if kind == "postgres" else int(completed), now, now if completed else "")
        try:
            if kind == "postgres":
                conn.execute("INSERT INTO learning_progress(material_id,username,position,progress,completed,last_viewed_at,completed_at) VALUES(%s,%s,%s::jsonb,%s,%s,%s,%s) ON CONFLICT(material_id,username) DO UPDATE SET position=EXCLUDED.position,progress=EXCLUDED.progress,completed=learning_progress.completed OR EXCLUDED.completed,last_viewed_at=EXCLUDED.last_viewed_at,completed_at=CASE WHEN EXCLUDED.completed THEN EXCLUDED.last_viewed_at ELSE learning_progress.completed_at END", values)
            else:
                conn.execute("INSERT INTO learning_progress(material_id,username,position,progress,completed,last_viewed_at,completed_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(material_id,username) DO UPDATE SET position=excluded.position,progress=excluded.progress,completed=MAX(learning_progress.completed,excluded.completed),last_viewed_at=excluded.last_viewed_at,completed_at=CASE WHEN excluded.completed=1 THEN excluded.last_viewed_at ELSE learning_progress.completed_at END", values)
        finally: conn.close()
        # Preserve 6.6 sequential unlock: only a real completion writes its old marker.
        if completed:
            client = app.test_client()  # no request/session forwarding; legacy marker remains UI-owned
        return jsonify({"ok": True, "materialId": material_id, "position": position, "progress": progress, "completed": completed, "lastViewedAt": now})

    @app.get("/api/material-search")
    def material_search():
        user, denied = _user(base)
        if denied: return denied
        query = str(request.args.get("q", "")).strip()[:200]
        material_id = str(request.args.get("materialId", "")).strip()[:100]
        if not query or not material_id: return jsonify([])
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
        if material.get("storageBackend")!="local" or not path.is_file(): return jsonify({"error":"此教材目前無可安全索引的本機原始檔"}),409
        rows=extract_slide_text(path); conn,kind=base._db_conn(); ph="%s" if kind=="postgres" else "?"
        try:
            conn.execute(f"DELETE FROM material_text_index WHERE material_id={ph}",(material_id,))
            for page_no,text,title in rows: conn.execute(f"INSERT INTO material_text_index(material_id,page_no,title,text,indexed_at) VALUES({ph},{ph},{ph},{ph},{ph})",(material_id,page_no,title,text,_now()))
        finally:conn.close()
        return jsonify({"ok":True,"pages":len(rows),"searchable":bool(rows)})

    @app.get("/api/learning-analytics")
    def learning_analytics():
        denied = base.require_admin()
        if denied: return denied
        conn, kind = base._db_conn()
        try:
            rows = conn.execute("SELECT material_id,COUNT(*) learners,SUM(CASE WHEN completed THEN 1 ELSE 0 END) completed,AVG(progress) average_progress,MAX(last_viewed_at) last_viewed_at FROM learning_progress GROUP BY material_id").fetchall()
        finally: conn.close()
        return jsonify([{"materialId": _row(r).get("material_id"), "learners": int(_row(r).get("learners") or 0), "completed": int(_row(r).get("completed") or 0), "averageProgress": round(float(_row(r).get("average_progress") or 0), 1), "lastViewedAt": _row(r).get("last_viewed_at") or ""} for r in rows])

    app.extensions["teacher_smart_learning_67_registered"] = True
    return app
