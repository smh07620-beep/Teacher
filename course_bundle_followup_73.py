"""Retry-safe Course Wizard follow-up stages.

Course/exam creation is owned by course_bundle_72.  This adapter makes the two
remaining follow-up mutations safe to repeat with the same wizard workflow:
linking an existing material and enqueueing a new material upload.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json

from flask import jsonify, request

from course_bundle_72 import WORKFLOW_RE
from schema_migrations import MIGRATIONS, migration

MIGRATION_ID = "0073-course-bundle-followups"
MAX_FOLLOWUP_INDEX = 499


def _course_bundle_followups_73(conn, kind: str) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS course_bundle_followups ("
        "username TEXT NOT NULL,workflow_id TEXT NOT NULL,item_key TEXT NOT NULL,"
        "kind TEXT NOT NULL,request_hash TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'processing',"
        "response_status INTEGER NOT NULL DEFAULT 0,response_json TEXT NOT NULL DEFAULT '{}',"
        "created_at TEXT NOT NULL,updated_at TEXT NOT NULL,"
        "PRIMARY KEY(username,workflow_id,item_key))"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_course_bundle_followups_status "
        "ON course_bundle_followups(status,updated_at)"
    )


if not any(version == MIGRATION_ID for version, _fn in MIGRATIONS):
    migration(MIGRATION_ID)(_course_bundle_followups_73)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _username(user) -> str:
    return str(
        (user or {}).get("username")
        or (user or {}).get("empId")
        or (user or {}).get("emp_id")
        or ""
    ).strip()


def _row(row):
    return dict(row) if row is not None else {}


def _ph(kind: str) -> str:
    return "%s" if kind == "postgres" else "?"


def _hash_payload(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _load_bundle(base, username: str, workflow_id: str):
    conn = None
    try:
        conn, kind = base._db_conn()
        ph = _ph(kind)
        row = conn.execute(
            f"SELECT status,course_id,quiz_category_id,training_area,group_key "
            f"FROM course_bundle_requests WHERE username={ph} AND workflow_id={ph}",
            (username, workflow_id),
        ).fetchone()
        return _row(row)
    finally:
        if conn is not None:
            conn.close()


def _validate_bundle_target(base, bundle: dict, *, course_id: str, group: str, area: str, category: str):
    if not bundle or str(bundle.get("status") or "") != "completed":
        return "找不到已完成的課程建立流程，請先完成課程建立。", "BUNDLE_NOT_READY"
    if str(bundle.get("course_id") or "") != str(course_id or ""):
        return "教材操作的課程與原建立流程不一致。", "FOLLOWUP_BUNDLE_MISMATCH"
    normalized_group = base.normalize_group(str(group or getattr(base, "DEFAULT_GROUP", "")))
    normalized_area = base.normalize_area(str(area or getattr(base, "DEFAULT_TRAINING_AREA", "")))
    if str(bundle.get("group_key") or "") != normalized_group or str(bundle.get("training_area") or "") != normalized_area:
        return "教材操作的組別或訓練區與原建立流程不一致。", "FOLLOWUP_SCOPE_MISMATCH"
    expected_category = str(bundle.get("quiz_category_id") or "")
    if expected_category and str(category or "") != expected_category:
        return "教材操作的考卷關聯與原建立流程不一致。", "FOLLOWUP_EXAM_MISMATCH"
    return "", ""


def _claim(base, *, username: str, workflow_id: str, item_key: str, kind_name: str, request_hash: str):
    conn = None
    try:
        conn, kind = base._db_conn()
        now = _now()
        params = (username, workflow_id, item_key, kind_name, request_hash, "processing", 0, "{}", now, now)
        if kind == "postgres":
            cur = conn.execute(
                "INSERT INTO course_bundle_followups "
                "(username,workflow_id,item_key,kind,request_hash,status,response_status,response_json,created_at,updated_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (username,workflow_id,item_key) DO NOTHING",
                params,
            )
        else:
            cur = conn.execute(
                "INSERT OR IGNORE INTO course_bundle_followups "
                "(username,workflow_id,item_key,kind,request_hash,status,response_status,response_json,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                params,
            )
        ph = _ph(kind)
        row = conn.execute(
            f"SELECT * FROM course_bundle_followups WHERE username={ph} AND workflow_id={ph} AND item_key={ph}",
            (username, workflow_id, item_key),
        ).fetchone()
        return cur.rowcount == 1, _row(row)
    finally:
        if conn is not None:
            conn.close()


def _release(base, *, username: str, workflow_id: str, item_key: str, request_hash: str) -> None:
    conn = None
    try:
        conn, kind = base._db_conn()
        ph = _ph(kind)
        conn.execute(
            f"DELETE FROM course_bundle_followups WHERE username={ph} AND workflow_id={ph} "
            f"AND item_key={ph} AND request_hash={ph} AND status={ph}",
            (username, workflow_id, item_key, request_hash, "processing"),
        )
    finally:
        if conn is not None:
            conn.close()


def _complete(base, *, username: str, workflow_id: str, item_key: str, request_hash: str, status_code: int, payload: dict) -> None:
    conn = None
    try:
        conn, kind = base._db_conn()
        ph = _ph(kind)
        conn.execute(
            f"UPDATE course_bundle_followups SET status={ph},response_status={ph},response_json={ph},updated_at={ph} "
            f"WHERE username={ph} AND workflow_id={ph} AND item_key={ph} AND request_hash={ph}",
            (
                "completed",
                int(status_code),
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                _now(),
                username,
                workflow_id,
                item_key,
                request_hash,
            ),
        )
    finally:
        if conn is not None:
            conn.close()


def _reuse_or_error(inserted: bool, row: dict, request_hash: str):
    if inserted:
        return None
    if str(row.get("request_hash") or "") != request_hash:
        return jsonify({
            "error": "此教材步驟識別碼已用於不同內容，請重新開始建立流程。",
            "code": "FOLLOWUP_KEY_REUSED",
        }), 409
    if str(row.get("status") or "") == "completed":
        try:
            payload = json.loads(row.get("response_json") or "{}")
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload["reused"] = True
        return jsonify(payload), 200
    return jsonify({
        "error": "此教材步驟仍在處理中，請稍後使用相同建立流程重試。",
        "code": "FOLLOWUP_IN_PROGRESS",
    }), 409


def _workflow_context(base, workflow_id: str):
    if not WORKFLOW_RE.fullmatch(str(workflow_id or "")):
        return None, None, (jsonify({"error": "建立流程識別碼格式不正確。"}), 400)
    user = base._current_user()
    username = _username(user)
    if not username:
        return None, None, (jsonify({"error": "請先登入。", "loginRequired": True}), 401)
    bundle = _load_bundle(base, username, workflow_id)
    return username, bundle, None


def register_course_bundle_followup_73(base):
    app = base.app
    if app.extensions.get("teacher_course_bundle_followup_73_registered"):
        return app

    original_upload = app.view_functions.get("api_enqueue_material_job")
    original_link = app.view_functions.get("api_update_slide")
    if original_upload is None or original_link is None:
        return app

    def retry_safe_upload():
        workflow_id = str(request.form.get("bundleWorkflowId") or "").strip()
        index_raw = str(request.form.get("bundleFileIndex") or "").strip()
        if not workflow_id and not index_raw:
            return original_upload()

        denied = base.require_admin()
        if denied:
            return denied
        try:
            index = int(index_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "教材步驟序號格式不正確。"}), 400
        if index < 0 or index > MAX_FOLLOWUP_INDEX:
            return jsonify({"error": "教材步驟序號超出允許範圍。"}), 400

        username, bundle, error = _workflow_context(base, workflow_id)
        if error:
            return error
        course_id = str(request.form.get("courseId") or "").strip()
        group = str(request.form.get("group") or "").strip()
        area = str(request.form.get("area") or "").strip()
        category = str(request.form.get("category") or "").strip()
        message, code = _validate_bundle_target(
            base, bundle, course_id=course_id, group=group, area=area, category=category
        )
        if message:
            return jsonify({"error": message, "code": code}), 409

        upload = request.files.get("file")
        original_name = str(getattr(upload, "filename", "") or "")
        request_hash = _hash_payload({
            "workflowId": workflow_id,
            "index": index,
            "courseId": course_id,
            "category": category,
            "group": base.normalize_group(group),
            "area": base.normalize_area(area),
            "title": str(request.form.get("title") or "").strip(),
            "materialType": str(request.form.get("materialType") or "auto").strip(),
            "originalName": original_name,
            "fileSize": str(request.form.get("bundleFileSize") or "").strip(),
            "lastModified": str(request.form.get("bundleFileLastModified") or "").strip(),
        })
        item_key = f"upload:{index}"
        inserted, claim = _claim(
            base,
            username=username,
            workflow_id=workflow_id,
            item_key=item_key,
            kind_name="upload",
            request_hash=request_hash,
        )
        reused = _reuse_or_error(inserted, claim, request_hash)
        if reused is not None:
            return reused

        try:
            response = app.make_response(original_upload())
        except Exception:
            _release(base, username=username, workflow_id=workflow_id, item_key=item_key, request_hash=request_hash)
            raise
        if response.status_code < 200 or response.status_code >= 300:
            _release(base, username=username, workflow_id=workflow_id, item_key=item_key, request_hash=request_hash)
            return response
        payload = response.get_json(silent=True)
        if not isinstance(payload, dict):
            _release(base, username=username, workflow_id=workflow_id, item_key=item_key, request_hash=request_hash)
            return response
        payload = dict(payload)
        payload.update({"reused": False, "bundleWorkflowId": workflow_id, "bundleFileIndex": index})
        # If persistence of the completion marker fails after the queue accepted
        # the upload, keep the processing claim instead of releasing it.  This
        # fails closed against duplicate queue insertion.
        _complete(
            base,
            username=username,
            workflow_id=workflow_id,
            item_key=item_key,
            request_hash=request_hash,
            status_code=response.status_code,
            payload=payload,
        )
        return jsonify(payload), response.status_code

    def retry_safe_link(slide_id):
        data = request.get_json(silent=True) or {}
        workflow_id = str(data.get("bundleWorkflowId") or "").strip() if isinstance(data, dict) else ""
        link_key = str(data.get("bundleLinkKey") or "").strip() if isinstance(data, dict) else ""
        if not workflow_id and not link_key:
            return original_link(slide_id)

        denied = base.require_admin()
        if denied:
            return denied
        if link_key != str(slide_id):
            return jsonify({"error": "教材關聯識別碼與目標教材不一致。"}), 400

        username, bundle, error = _workflow_context(base, workflow_id)
        if error:
            return error
        course_id = str(data.get("courseId") or "").strip()
        group = str(data.get("group") or "").strip()
        area = str(data.get("area") or "").strip()
        category = str(data.get("category") or "").strip()
        message, code = _validate_bundle_target(
            base, bundle, course_id=course_id, group=group, area=area, category=category
        )
        if message:
            return jsonify({"error": message, "code": code}), 409

        request_hash = _hash_payload({
            "workflowId": workflow_id,
            "materialId": str(slide_id),
            "courseId": course_id,
            "category": category,
            "group": base.normalize_group(group),
            "area": base.normalize_area(area),
        })
        item_key = f"link:{slide_id}"
        inserted, claim = _claim(
            base,
            username=username,
            workflow_id=workflow_id,
            item_key=item_key,
            kind_name="link",
            request_hash=request_hash,
        )
        reused = _reuse_or_error(inserted, claim, request_hash)
        if reused is not None:
            return reused

        try:
            response = app.make_response(original_link(slide_id))
        except Exception:
            _release(base, username=username, workflow_id=workflow_id, item_key=item_key, request_hash=request_hash)
            raise
        if response.status_code < 200 or response.status_code >= 300:
            _release(base, username=username, workflow_id=workflow_id, item_key=item_key, request_hash=request_hash)
            return response
        payload = response.get_json(silent=True)
        if not isinstance(payload, dict):
            _release(base, username=username, workflow_id=workflow_id, item_key=item_key, request_hash=request_hash)
            return response
        payload = dict(payload)
        payload.update({"reused": False, "bundleWorkflowId": workflow_id, "bundleLinkKey": str(slide_id)})
        _complete(
            base,
            username=username,
            workflow_id=workflow_id,
            item_key=item_key,
            request_hash=request_hash,
            status_code=response.status_code,
            payload=payload,
        )
        return jsonify(payload), response.status_code

    app.view_functions["api_enqueue_material_job"] = retry_safe_upload
    app.view_functions["api_update_slide"] = retry_safe_link
    app.extensions["teacher_course_bundle_followup_73_registered"] = True
    return app
