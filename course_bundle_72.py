"""Session-scoped, retry-safe Course Wizard bundle creation.

The Course Wizard owns UI state.  This adapter owns only the atomic creation of
one course plus an optional draft exam.  Material linking and background
uploads remain separate, idempotent follow-up stages.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import uuid

from flask import jsonify, request

from schema_migrations import MIGRATIONS, migration

MIGRATION_ID = "0072-course-bundle-idempotency"
WORKFLOW_RE = re.compile(r"^[A-Za-z0-9._:-]{12,120}$")
EXAM_MODES = {"later", "bank", "ai", "blueprint"}


def _course_bundle_idempotency_72(conn, kind: str) -> None:
    """Persist idempotency state without changing existing course/exam rows."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS course_bundle_requests ("
        "username TEXT NOT NULL,workflow_id TEXT NOT NULL,request_hash TEXT NOT NULL,"
        "training_area TEXT NOT NULL,group_key TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'creating',"
        "course_id TEXT NOT NULL DEFAULT '',quiz_category_id TEXT NOT NULL DEFAULT '',"
        "result_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,"
        "PRIMARY KEY(username,workflow_id))"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_course_bundle_requests_status "
        "ON course_bundle_requests(status,updated_at)"
    )


# Register the additive migration before pgy_app calls register_schema_migrations.
if not any(version == MIGRATION_ID for version, _fn in MIGRATIONS):
    migration(MIGRATION_ID)(_course_bundle_idempotency_72)


def _row_dict(row):
    return dict(row) if row is not None else {}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _display_time() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def _username(user) -> str:
    return str(
        (user or {}).get("username")
        or (user or {}).get("empId")
        or (user or {}).get("emp_id")
        or ""
    ).strip()


def _request_core(base, data):
    workflow_id = str(data.get("workflowId") or "").strip()
    if not WORKFLOW_RE.fullmatch(workflow_id):
        raise ValueError("建立流程識別碼格式不正確，請重新開始建立流程。")
    area = base.normalize_area(str(data.get("area") or getattr(base, "DEFAULT_TRAINING_AREA", "internal")))
    group = base.normalize_group(str(data.get("group") or getattr(base, "DEFAULT_GROUP", "grpBio")))
    title = str(data.get("title") or "").strip()[:255]
    desc = str(data.get("desc") or "").strip()[:2000]
    exam_mode = str(data.get("examMode") or "later").strip().lower()
    exam_title = str(data.get("examTitle") or "").strip()[:255]
    if not title:
        raise ValueError("請輸入課程名稱")
    if exam_mode not in EXAM_MODES:
        raise ValueError("不支援的考卷建立模式")
    if exam_mode != "later" and not exam_title:
        raise ValueError("請輸入考卷名稱，或改選「稍後建立」。")
    core = {
        "area": area,
        "group": group,
        "title": title,
        "desc": desc,
        "examMode": exam_mode,
        "examTitle": exam_title if exam_mode != "later" else "",
    }
    digest = hashlib.sha256(
        json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return workflow_id, core, digest


def _begin(conn, kind: str) -> None:
    conn.execute("BEGIN" if kind == "postgres" else "BEGIN IMMEDIATE")


def _commit(conn) -> None:
    conn.execute("COMMIT")


def _rollback(conn) -> None:
    try:
        conn.execute("ROLLBACK")
    except Exception:
        pass


def _insert_claim(conn, kind, *, username, workflow_id, request_hash, area, group, now):
    params = (username, workflow_id, request_hash, area, group, "creating", "", "", "{}", now, now)
    if kind == "postgres":
        cur = conn.execute(
            "INSERT INTO course_bundle_requests "
            "(username,workflow_id,request_hash,training_area,group_key,status,course_id,quiz_category_id,result_json,created_at,updated_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (username,workflow_id) DO NOTHING",
            params,
        )
    else:
        cur = conn.execute(
            "INSERT OR IGNORE INTO course_bundle_requests "
            "(username,workflow_id,request_hash,training_area,group_key,status,course_id,quiz_category_id,result_json,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            params,
        )
    return cur.rowcount == 1


def _load_claim(conn, kind, username, workflow_id):
    ph = "%s" if kind == "postgres" else "?"
    return _row_dict(
        conn.execute(
            f"SELECT * FROM course_bundle_requests WHERE username={ph} AND workflow_id={ph}",
            (username, workflow_id),
        ).fetchone()
    )


def _next_order(conn, kind, table: str, where_sql: str, params):
    row = conn.execute(
        f"SELECT COALESCE(MAX(sort_order),-1) AS m FROM {table} WHERE {where_sql}", params
    ).fetchone()
    value = _row_dict(row).get("m") if row is not None else -1
    if value is None and row is not None:
        try:
            value = row[0]
        except Exception:
            value = -1
    return int(value or 0) + 1


def _create_course(conn, kind, core):
    course_id = f"course-{uuid.uuid4().hex[:12]}"
    ph = "%s" if kind == "postgres" else "?"
    order = _next_order(
        conn,
        kind,
        "courses",
        f"training_area={ph} AND group_key={ph}",
        (core["area"], core["group"]),
    )
    added = _display_time()
    values = (course_id, core["area"], core["group"], core["title"], core["desc"], order, added, True if kind == "postgres" else 1)
    if kind == "postgres":
        conn.execute(
            "INSERT INTO courses (id,training_area,group_key,title,description,sort_order,date_added,active) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            values,
        )
    else:
        conn.execute(
            "INSERT INTO courses (id,training_area,group_key,title,description,sort_order,date_added,active) "
            "VALUES (?,?,?,?,?,?,?,?)",
            values,
        )
    return course_id


def _create_exam(conn, kind, core, course_id):
    if core["examMode"] == "later":
        return ""
    category_id = f"cat-{uuid.uuid4().hex[:12]}"
    ph = "%s" if kind == "postgres" else "?"
    order = _next_order(
        conn,
        kind,
        "quiz_categories",
        f"group_key={ph} AND training_area={ph}",
        (core["group"], core["area"]),
    )
    added = _display_time()
    desc = f"{core['title']} 課後評量"
    draw_rules = json.dumps({}, ensure_ascii=False)
    values = (
        category_id,
        core["group"],
        core["area"],
        course_id,
        core["examTitle"],
        desc,
        order,
        added,
        False if kind == "postgres" else 0,
        0,
        80,
        "",
        draw_rules,
        "draft",
        "",
        "",
        "",
    )
    if kind == "postgres":
        conn.execute(
            "INSERT INTO quiz_categories "
            "(id,group_key,training_area,course_id,title,description,sort_order,date_added,active,draw_count,passing_score,audience,draw_rules,review_status,reviewer_name,reviewed_at,published_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)",
            values,
        )
    else:
        conn.execute(
            "INSERT INTO quiz_categories "
            "(id,group_key,training_area,course_id,title,description,sort_order,date_added,active,draw_count,passing_score,audience,draw_rules,review_status,reviewer_name,reviewed_at,published_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            values,
        )
    return category_id


def _stored_result(workflow_id, core, course_id, category_id, material_count, upload_count):
    return {
        "ok": True,
        "workflowId": workflow_id,
        "status": "completed",
        "reused": False,
        "course": {
            "id": course_id,
            "area": core["area"],
            "group": core["group"],
            "title": core["title"],
            "desc": core["desc"],
            "active": True,
        },
        "quizCategory": (
            {
                "id": category_id,
                "group": core["group"],
                "area": core["area"],
                "courseId": course_id,
                "title": core["examTitle"],
                "desc": f"{core['title']} 課後評量",
                "active": False,
                "reviewStatus": "draft",
            }
            if category_id
            else None
        ),
        "stages": {
            "course": "created",
            "exam": "created" if category_id else "skipped",
            "materials": "pending-client" if material_count else "skipped",
            "uploads": "pending-background" if upload_count else "skipped",
        },
    }


def _hydrate(base, result, reused):
    result = dict(result or {})
    course = result.get("course") or {}
    category = result.get("quizCategory") or None
    try:
        current = base.get_course(str(course.get("id") or "")) if course else None
        if current:
            result["course"] = current
    except Exception:
        pass
    if category:
        try:
            current = base.get_quiz_category(str(category.get("id") or ""))
            if current:
                result["quizCategory"] = current
        except Exception:
            pass
    result["reused"] = bool(reused)
    if reused:
        stages = dict(result.get("stages") or {})
        stages["course"] = "reused"
        if result.get("quizCategory"):
            stages["exam"] = "reused"
        result["stages"] = stages
    return result


def register_course_bundle_72(base):
    app = base.app
    if app.extensions.get("teacher_course_bundle_72_registered"):
        return app

    def create_course_bundle():
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"error": "請提供有效的建立資料。"}), 400

        # Canonical session RBAC.  No AdminKey/elevation path is accepted here.
        denied = base.require_permission("course.manage")
        if denied:
            return denied
        exam_mode = str(data.get("examMode") or "later").strip().lower()
        if exam_mode != "later":
            denied = base.require_permission("question.manage")
            if denied:
                return denied

        user = base._current_user()
        username = _username(user)
        if not username:
            return jsonify({"error": "請先登入。", "loginRequired": True}), 401

        try:
            workflow_id, core, request_hash = _request_core(base, data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        material_count = max(0, min(500, int(data.get("existingMaterialCount") or 0)))
        upload_count = max(0, min(500, int(data.get("uploadCount") or 0)))
        now = _now()
        conn = None
        try:
            conn, kind = base._db_conn()
            _begin(conn, kind)
            inserted = _insert_claim(
                conn,
                kind,
                username=username,
                workflow_id=workflow_id,
                request_hash=request_hash,
                area=core["area"],
                group=core["group"],
                now=now,
            )
            claim = _load_claim(conn, kind, username, workflow_id)
            if not claim:
                raise RuntimeError("無法建立流程紀錄")
            if claim.get("request_hash") != request_hash:
                _rollback(conn)
                return jsonify({
                    "error": "此建立流程識別碼已用於不同內容，請重新開始建立流程。",
                    "code": "IDEMPOTENCY_KEY_REUSED",
                }), 409
            if not inserted:
                if claim.get("status") == "completed":
                    stored = json.loads(claim.get("result_json") or "{}")
                    _commit(conn)
                    return jsonify(_hydrate(base, stored, True)), 200
                _rollback(conn)
                return jsonify({
                    "error": "此建立流程仍在處理中，請稍後使用相同流程識別碼重試。",
                    "code": "WORKFLOW_IN_PROGRESS",
                }), 409

            course_id = _create_course(conn, kind, core)
            category_id = _create_exam(conn, kind, core, course_id)
            result = _stored_result(
                workflow_id,
                core,
                course_id,
                category_id,
                material_count,
                upload_count,
            )
            ph = "%s" if kind == "postgres" else "?"
            conn.execute(
                f"UPDATE course_bundle_requests SET status={ph},course_id={ph},quiz_category_id={ph},result_json={ph},updated_at={ph} "
                f"WHERE username={ph} AND workflow_id={ph}",
                (
                    "completed",
                    course_id,
                    category_id,
                    json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                    _now(),
                    username,
                    workflow_id,
                ),
            )
            _commit(conn)
            return jsonify(_hydrate(base, result, False)), 201
        except (TypeError, ValueError):
            if conn is not None:
                _rollback(conn)
            return jsonify({"error": "教材數量格式不正確。"}), 400
        except Exception:
            if conn is not None:
                _rollback(conn)
            return jsonify({"error": "建立課程流程失敗，未完成的資料已回復；可使用相同流程識別碼重試。"}), 500
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    app.add_url_rule(
        "/api/course-bundles",
        endpoint="course_bundle_create_72",
        view_func=create_course_bundle,
        methods=["POST"],
    )
    app.extensions["teacher_course_bundle_72_registered"] = True
    return app
