"""Server-authoritative exam availability windows."""
from __future__ import annotations
import datetime as dt
from flask import g, jsonify, request
from teacher_app.common import audit, db as common_db
from teacher_app.common.auth import has_permission
from teacher_app.common.errors import ApiError

def _parse(v):
    text=str(v or "").strip()
    if not text:return ""
    try:
        d=dt.datetime.fromisoformat(text[:-1]+"+00:00" if text.endswith("Z") else text)
    except ValueError as exc: raise ApiError("INVALID_EXAM_WINDOW","考核日期格式不正確。",400) from exc
    if d.tzinfo is None:d=d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc).isoformat()

def get_window(category_id):
    with common_db.read_connection() as (conn,kind):
        ph=common_db.placeholder(kind); row=conn.execute(f"SELECT * FROM exam_windows WHERE quiz_category_id={ph}",(category_id,)).fetchone()
    return dict(row) if row else None

def _window_time(raw):
    text=str(raw or "").strip()
    if not text:return None
    value=dt.datetime.fromisoformat(text.replace("Z","+00:00"))
    if value.tzinfo is None:value=value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc)

def assert_exam_open(category_id):
    item=get_window(category_id)
    if not item:return
    now=dt.datetime.now(dt.timezone.utc)
    for field,code,msg,cmp in (("opens_at","EXAM_NOT_OPEN","此考核尚未開放。","before"),("closes_at","EXAM_CLOSED","此考核已超過最後考核日期。","after")):
        value=_window_time(item.get(field))
        if value and ((cmp=="before" and now<value) or (cmp=="after" and now>value)): raise ApiError(code,msg,403,{"examWindow":True})

def assert_exam_not_closed(category_id):
    item=get_window(category_id)
    if not item:return
    closes=_window_time(item.get("closes_at"))
    if closes and dt.datetime.now(dt.timezone.utc)>closes:
        raise ApiError("EXAM_CLOSED","此考核已超過最後考核日期，不能繼續作答或提交。",403,{"examWindow":True,"closed":True})

def register_exam_window_routes(app):
    if app.extensions.get("teacher_exam_windows_registered"):return app
    @app.get("/api/exam-windows/<category_id>")
    def exam_window_get(category_id):
        user=getattr(g,"teacher_user",None)
        if not user:return jsonify({"error":"請先登入。","loginRequired":True}),401
        return jsonify({"window":get_window(category_id)})
    @app.put("/api/exam-windows/<category_id>")
    def exam_window_put(category_id):
        user=getattr(g,"teacher_user",None)
        if not user:return jsonify({"error":"請先登入。","loginRequired":True}),401
        if not has_permission(user,"exam.manage"):return jsonify({"error":"權限不足。"}),403
        data=request.get_json(silent=True) or {}
        try:opens=_parse(data.get("opensAt")); closes=_parse(data.get("closesAt"))
        except ApiError as exc:return jsonify({"error":exc.message,"code":exc.code}),exc.status
        if opens and closes and opens>=closes:return jsonify({"error":"最後考核日期必須晚於開放日期。"}),400
        now=dt.datetime.now(dt.timezone.utc).isoformat(); enabled=bool(data.get("reminderEnabled",True))
        with common_db.transaction() as (conn,kind):
            ph=common_db.placeholder(kind); stored=enabled if kind=="postgres" else int(enabled)
            conn.execute(f"""INSERT INTO exam_windows(quiz_category_id,opens_at,closes_at,reminder_enabled,updated_at,updated_by)
            VALUES ({','.join([ph]*6)}) ON CONFLICT(quiz_category_id) DO UPDATE SET opens_at=excluded.opens_at,closes_at=excluded.closes_at,reminder_enabled=excluded.reminder_enabled,updated_at=excluded.updated_at,updated_by=excluded.updated_by""",(category_id,opens,closes,stored,now,user["username"]))
        audit.record_event(actor=user,action="exam.window.update",target_type="quiz_category",target_id=category_id,after={"opensAt":opens,"closesAt":closes,"reminderEnabled":enabled})
        return jsonify({"ok":True,"window":get_window(category_id)})
    app.extensions["teacher_exam_windows_registered"]=True
    return app
__all__=["assert_exam_not_closed","assert_exam_open","get_window","register_exam_window_routes"]
