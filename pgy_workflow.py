"""PGY assignment, signature workflow and audit trail for Teacher 6.2.

This module is intentionally registered from ``pgy_app.py`` instead of making a
large invasive edit to the legacy ``app.py``. It reuses the application's
existing database connector and authentication helpers.
"""
from __future__ import annotations

import datetime as _dt
import json
import uuid
from typing import Any, Dict, Iterable, Optional

from flask import jsonify, request


ASSIGNMENT_STATUSES = {
    "assigned",
    "submitted",
    "teacher_signed",
    "group_countersigned",
    "finalized",
    "cancelled",
}

# One action has exactly one expected source state and target state. Reopen and
# cancel are administrative exceptions handled explicitly by the route.
WORKFLOW_TRANSITIONS = {
    "submit": ("assigned", "submitted", "student"),
    "teacher_sign": ("submitted", "teacher_signed", "clinical_teacher"),
    "group_countersign": ("teacher_signed", "group_countersigned", "group_leader"),
    "finalize": ("group_countersigned", "finalized", "education_admin"),
}


def utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def transition_allowed(status: str, action: str, role: str) -> bool:
    spec = WORKFLOW_TRANSITIONS.get(str(action or ""))
    if not spec:
        return False
    source, _target, required_role = spec
    return str(status or "") == source and str(role or "") == required_role


def _json_load(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return default


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _username(value: Any) -> str:
    return str(value or "").strip().lower()[:100]


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _ph(kind: str) -> str:
    return "%s" if kind == "postgres" else "?"


def _role(base, user: Optional[Dict[str, Any]]) -> str:
    return base.normalize_role((user or {}).get("role", "student"))


def _user_group(base, user: Dict[str, Any]) -> str:
    return base.normalize_group(user.get("preferredGroup") or user.get("preferred_group"))


def _auth(base, allowed: Optional[Iterable[str]] = None):
    user = base._current_user()
    if not user:
        return None, (jsonify({"error": "請先登入後再執行此操作。", "loginRequired": True}), 401)
    if allowed is not None:
        normalized = {base.normalize_role(r) for r in allowed}
        if _role(base, user) not in normalized:
            return None, (jsonify({"error": "權限不足。"}), 403)
    return user, None


def init_pgy_workflow_db(base) -> None:
    conn, kind = base._db_conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pgy_assignments (
                id TEXT PRIMARY KEY,
                learner_username TEXT NOT NULL,
                teacher_username TEXT NOT NULL,
                training_area TEXT NOT NULL DEFAULT 'pgy',
                group_key TEXT NOT NULL DEFAULT 'grpBio',
                course_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                instructions TEXT NOT NULL DEFAULT '',
                due_at TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'assigned',
                evidence TEXT NOT NULL DEFAULT '{}',
                reflection TEXT NOT NULL DEFAULT '',
                student_submitted_at TEXT NOT NULL DEFAULT '',
                teacher_signature TEXT NOT NULL DEFAULT '{}',
                group_signature TEXT NOT NULL DEFAULT '{}',
                final_confirmation TEXT NOT NULL DEFAULT '{}',
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pgy_assignments_learner ON pgy_assignments(learner_username, status, updated_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pgy_assignments_teacher ON pgy_assignments(teacher_username, status, updated_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pgy_assignments_group ON pgy_assignments(group_key, status, updated_at)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pgy_assignment_audit (
                id TEXT PRIMARY KEY,
                assignment_id TEXT NOT NULL,
                action TEXT NOT NULL,
                from_status TEXT NOT NULL DEFAULT '',
                to_status TEXT NOT NULL DEFAULT '',
                actor_username TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pgy_assignment_audit_assignment ON pgy_assignment_audit(assignment_id, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pgy_assignment_audit_actor ON pgy_assignment_audit(actor_username, created_at)")
    finally:
        conn.close()


def _lookup_account(conn, kind: str, username: str):
    ph = _ph(kind)
    row = conn.execute(f"SELECT * FROM user_accounts WHERE username={ph}", (username,)).fetchone()
    return dict(row) if row else None


def _course_row(conn, kind: str, course_id: str):
    if not course_id:
        return None
    ph = _ph(kind)
    try:
        row = conn.execute(f"SELECT * FROM courses WHERE id={ph}", (course_id,)).fetchone()
    except Exception:
        return None
    return dict(row) if row else None


def _assignment_query() -> str:
    return """
        SELECT a.*,
               l.display_name AS learner_name, l.emp_id AS learner_emp_id,
               t.display_name AS teacher_name, t.emp_id AS teacher_emp_id
        FROM pgy_assignments a
        LEFT JOIN user_accounts l ON l.username=a.learner_username
        LEFT JOIN user_accounts t ON t.username=a.teacher_username
    """


def _assignment_dict(row) -> Dict[str, Any]:
    d = dict(row)
    return {
        "id": str(d.get("id", "")),
        "learnerUsername": str(d.get("learner_username", "")),
        "learnerName": str(d.get("learner_name", "")),
        "learnerEmpId": str(d.get("learner_emp_id", "")),
        "teacherUsername": str(d.get("teacher_username", "")),
        "teacherName": str(d.get("teacher_name", "")),
        "teacherEmpId": str(d.get("teacher_emp_id", "")),
        "area": str(d.get("training_area", "pgy")),
        "group": str(d.get("group_key", "grpBio")),
        "courseId": str(d.get("course_id", "")),
        "title": str(d.get("title", "")),
        "instructions": str(d.get("instructions", "")),
        "dueAt": str(d.get("due_at", "")),
        "status": str(d.get("status", "assigned")),
        "evidence": _json_load(d.get("evidence"), {}),
        "reflection": str(d.get("reflection", "")),
        "studentSubmittedAt": str(d.get("student_submitted_at", "")),
        "teacherSignature": _json_load(d.get("teacher_signature"), {}),
        "groupSignature": _json_load(d.get("group_signature"), {}),
        "finalConfirmation": _json_load(d.get("final_confirmation"), {}),
        "createdBy": str(d.get("created_by", "")),
        "createdAt": str(d.get("created_at", "")),
        "updatedAt": str(d.get("updated_at", "")),
    }


def _get_assignment(conn, kind: str, assignment_id: str):
    ph = _ph(kind)
    return conn.execute(_assignment_query() + f" WHERE a.id={ph}", (assignment_id,)).fetchone()


def _can_view(base, user: Dict[str, Any], row) -> bool:
    d = dict(row)
    role = _role(base, user)
    username = _username(user.get("username"))
    if role == "education_admin":
        return True
    if role == "student":
        return d.get("learner_username") == username
    if role == "clinical_teacher":
        return d.get("teacher_username") == username
    if role == "group_leader":
        return d.get("group_key") == _user_group(base, user)
    return False


def _audit(conn, kind: str, base, assignment_id: str, user: Dict[str, Any], action: str,
           from_status: str = "", to_status: str = "", detail: Optional[Dict[str, Any]] = None) -> None:
    ph = _ph(kind)
    conn.execute(
        f"INSERT INTO pgy_assignment_audit (id,assignment_id,action,from_status,to_status,actor_username,actor_role,detail,created_at) VALUES ({','.join([ph] * 9)})",
        (
            uuid.uuid4().hex,
            assignment_id,
            action,
            from_status or "",
            to_status or "",
            _username(user.get("username")),
            _role(base, user),
            _json_dump(detail or {}),
            utcnow(),
        ),
    )


def register_pgy_workflow(base):
    """Register PGY workflow tables and routes on the legacy Flask app."""
    app = base.app
    if app.extensions.get("pgy_workflow_registered"):
        return app
    init_pgy_workflow_db(base)
    app.extensions["pgy_workflow_registered"] = True

    @app.get("/api/pgy/workflow/meta")
    def pgy_workflow_meta():
        user, denied = _auth(base)
        if denied:
            return denied
        role = _role(base, user)
        actions = [name for name, (_src, _dst, required) in WORKFLOW_TRANSITIONS.items() if required == role]
        if role == "education_admin":
            actions.extend(["create", "edit_assignment", "reopen", "cancel"])
        return jsonify({
            "statuses": sorted(ASSIGNMENT_STATUSES),
            "actions": actions,
            "role": role,
            "signatureOrder": ["student", "clinical_teacher", "group_leader", "education_admin"],
        })

    @app.get("/api/pgy/assignment-candidates")
    def pgy_assignment_candidates():
        user, denied = _auth(base, {"education_admin", "group_leader"})
        if denied:
            return denied
        requested_group = base.normalize_group(request.args.get("group") or _user_group(base, user))
        if _role(base, user) == "group_leader" and requested_group != _user_group(base, user):
            return jsonify({"error": "組長只能查看自己組別的指派候選人。"}), 403
        conn, _kind = base._db_conn()
        try:
            rows = conn.execute("SELECT username,display_name,emp_id,role,preferred_group,active FROM user_accounts ORDER BY display_name ASC").fetchall()
            students, teachers = [], []
            for row in rows:
                d = dict(row)
                if not bool(d.get("active", True)):
                    continue
                role = base.normalize_role(d.get("role"))
                group = base.normalize_group(d.get("preferred_group"))
                if group != requested_group:
                    continue
                item = {"username": d.get("username", ""), "name": d.get("display_name", ""), "empId": d.get("emp_id", ""), "group": group}
                if role == "student":
                    students.append(item)
                elif role == "clinical_teacher":
                    teachers.append(item)
            return jsonify({"group": requested_group, "students": students, "teachers": teachers})
        finally:
            conn.close()

    @app.get("/api/pgy/assignments")
    def pgy_assignments_list():
        user, denied = _auth(base, {"student", "clinical_teacher", "group_leader", "education_admin"})
        if denied:
            return denied
        conn, kind = base._db_conn()
        ph = _ph(kind)
        role = _role(base, user)
        where = ["a.training_area='pgy'"]
        params = []
        if role == "student":
            where.append(f"a.learner_username={ph}"); params.append(_username(user.get("username")))
        elif role == "clinical_teacher":
            where.append(f"a.teacher_username={ph}"); params.append(_username(user.get("username")))
        elif role == "group_leader":
            where.append(f"a.group_key={ph}"); params.append(_user_group(base, user))
        status = _text(request.args.get("status"), 40)
        if status:
            if status not in ASSIGNMENT_STATUSES:
                conn.close()
                return jsonify({"error": "狀態格式不正確。"}), 400
            where.append(f"a.status={ph}"); params.append(status)
        group = _text(request.args.get("group"), 40)
        if group and role == "education_admin":
            group = base.normalize_group(group)
            where.append(f"a.group_key={ph}"); params.append(group)
        try:
            rows = conn.execute(_assignment_query() + " WHERE " + " AND ".join(where) + " ORDER BY a.updated_at DESC", tuple(params)).fetchall()
            return jsonify([_assignment_dict(r) for r in rows])
        finally:
            conn.close()

    @app.get("/api/pgy/assignments/<assignment_id>")
    def pgy_assignment_get(assignment_id):
        user, denied = _auth(base, {"student", "clinical_teacher", "group_leader", "education_admin"})
        if denied:
            return denied
        conn, kind = base._db_conn()
        try:
            row = _get_assignment(conn, kind, assignment_id)
            if not row:
                return jsonify({"error": "找不到指派。"}), 404
            if not _can_view(base, user, row):
                return jsonify({"error": "無權查看此指派。"}), 403
            return jsonify(_assignment_dict(row))
        finally:
            conn.close()

    @app.post("/api/pgy/assignments")
    def pgy_assignment_create():
        user, denied = _auth(base, {"education_admin"})
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        learner_username = _username(data.get("learnerUsername"))
        teacher_username = _username(data.get("teacherUsername"))
        if not learner_username or not teacher_username:
            return jsonify({"error": "學員與臨床教師皆為必填。"}), 400
        area = _text(data.get("area") or "pgy", 20)
        if area != "pgy":
            return jsonify({"error": "PGY 指派只能建立在 PGY 訓練區。"}), 400
        conn, kind = base._db_conn(); ph = _ph(kind)
        try:
            learner = _lookup_account(conn, kind, learner_username)
            teacher = _lookup_account(conn, kind, teacher_username)
            if not learner or not bool(learner.get("active", True)) or base.normalize_role(learner.get("role")) != "student":
                return jsonify({"error": "指定的學員不存在、已停用或角色不是學員。"}), 400
            if not teacher or not bool(teacher.get("active", True)) or base.normalize_role(teacher.get("role")) != "clinical_teacher":
                return jsonify({"error": "指定的教師不存在、已停用或角色不是臨床教師。"}), 400
            group = base.normalize_group(data.get("group") or learner.get("preferred_group"))
            course_id = _text(data.get("courseId"), 120)
            course = _course_row(conn, kind, course_id) if course_id else None
            if course_id and not course:
                return jsonify({"error": "找不到指定課程。"}), 400
            if course:
                course_area = base.normalize_area(course.get("training_area"))
                course_group = base.normalize_group(course.get("group_key"))
                if course_area != "pgy" or course_group != group:
                    return jsonify({"error": "課程的訓練區或組別與指派不一致。"}), 400
            if course_id:
                duplicate = conn.execute(
                    f"SELECT id FROM pgy_assignments WHERE learner_username={ph} AND course_id={ph} AND status NOT IN ('finalized','cancelled') LIMIT 1",
                    (learner_username, course_id),
                ).fetchone()
                if duplicate:
                    return jsonify({"error": "此學員在同一課程已有進行中的指派。"}), 409
            assignment_id = uuid.uuid4().hex
            now = utcnow()
            title = _text(data.get("title") or (course or {}).get("title") or "PGY訓練指派", 180)
            instructions = _text(data.get("instructions"), 10000)
            due_at = _text(data.get("dueAt"), 80)
            values = (
                assignment_id, learner_username, teacher_username, "pgy", group, course_id,
                title, instructions, due_at, "assigned", "{}", "", "", "{}", "{}", "{}",
                _username(user.get("username")), now, now,
            )
            conn.execute(
                f"INSERT INTO pgy_assignments (id,learner_username,teacher_username,training_area,group_key,course_id,title,instructions,due_at,status,evidence,reflection,student_submitted_at,teacher_signature,group_signature,final_confirmation,created_by,created_at,updated_at) VALUES ({','.join([ph] * 19)})",
                values,
            )
            _audit(conn, kind, base, assignment_id, user, "create", "", "assigned", {"learnerUsername": learner_username, "teacherUsername": teacher_username, "courseId": course_id, "group": group})
            row = _get_assignment(conn, kind, assignment_id)
            return jsonify({"ok": True, "assignment": _assignment_dict(row)}), 201
        finally:
            conn.close()

    @app.patch("/api/pgy/assignments/<assignment_id>")
    def pgy_assignment_update(assignment_id):
        user, denied = _auth(base, {"student", "education_admin"})
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        conn, kind = base._db_conn(); ph = _ph(kind)
        try:
            row = _get_assignment(conn, kind, assignment_id)
            if not row:
                return jsonify({"error": "找不到指派。"}), 404
            raw = dict(row); role = _role(base, user)
            if role == "student":
                if raw.get("learner_username") != _username(user.get("username")):
                    return jsonify({"error": "只能更新自己的指派。"}), 403
                if raw.get("status") != "assigned":
                    return jsonify({"error": "送出後即鎖定學員內容；如需修改請由教學管理者退回。"}), 409
                evidence = data.get("evidence", _json_load(raw.get("evidence"), {}))
                if not isinstance(evidence, (dict, list)):
                    return jsonify({"error": "evidence 必須是 JSON 物件或陣列。"}), 400
                evidence_text = _json_dump(evidence)
                if len(evidence_text) > 30000:
                    return jsonify({"error": "佐證內容過長，請改放教材/檔案連結。"}), 400
                reflection = _text(data.get("reflection", raw.get("reflection", "")), 12000)
                now = utcnow()
                conn.execute(f"UPDATE pgy_assignments SET evidence={ph}, reflection={ph}, updated_at={ph} WHERE id={ph}", (evidence_text, reflection, now, assignment_id))
                _audit(conn, kind, base, assignment_id, user, "student_edit", raw.get("status", ""), raw.get("status", ""), {"evidenceUpdated": "evidence" in data, "reflectionUpdated": "reflection" in data})
            else:
                if raw.get("status") != "assigned":
                    return jsonify({"error": "只有尚未送出的指派可以調整教師、課程或期限。"}), 409
                fields, values, detail = [], [], {}
                if "teacherUsername" in data:
                    teacher_username = _username(data.get("teacherUsername"))
                    teacher = _lookup_account(conn, kind, teacher_username)
                    if not teacher or not bool(teacher.get("active", True)) or base.normalize_role(teacher.get("role")) != "clinical_teacher":
                        return jsonify({"error": "新指派教師不存在、已停用或角色不是臨床教師。"}), 400
                    fields.append(f"teacher_username={ph}"); values.append(teacher_username); detail["teacherUsername"] = teacher_username
                for key, column, limit in (("title", "title", 180), ("instructions", "instructions", 10000), ("dueAt", "due_at", 80)):
                    if key in data:
                        value = _text(data.get(key), limit)
                        fields.append(f"{column}={ph}"); values.append(value); detail[key] = value
                if not fields:
                    return jsonify({"error": "沒有可更新的欄位。"}), 400
                now = utcnow(); fields.append(f"updated_at={ph}"); values.append(now); values.append(assignment_id)
                conn.execute(f"UPDATE pgy_assignments SET {','.join(fields)} WHERE id={ph}", tuple(values))
                _audit(conn, kind, base, assignment_id, user, "admin_edit", raw.get("status", ""), raw.get("status", ""), detail)
            updated = _get_assignment(conn, kind, assignment_id)
            return jsonify({"ok": True, "assignment": _assignment_dict(updated)})
        finally:
            conn.close()

    def _workflow_action(assignment_id: str, action: str):
        source, target, required_role = WORKFLOW_TRANSITIONS[action]
        user, denied = _auth(base, {required_role})
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        conn, kind = base._db_conn(); ph = _ph(kind)
        try:
            row = _get_assignment(conn, kind, assignment_id)
            if not row:
                return jsonify({"error": "找不到指派。"}), 404
            raw = dict(row); role = _role(base, user); username = _username(user.get("username"))
            if not transition_allowed(raw.get("status"), action, role):
                return jsonify({"error": f"目前狀態 {raw.get('status')} 無法執行 {action}。"}), 409
            if action == "submit":
                if raw.get("learner_username") != username:
                    return jsonify({"error": "只能送出自己的指派。"}), 403
                evidence = _json_load(raw.get("evidence"), {})
                reflection = str(raw.get("reflection", "")).strip()
                if not evidence and not reflection:
                    return jsonify({"error": "送出前至少需填寫反思或佐證內容。"}), 400
                now = utcnow()
                conn.execute(f"UPDATE pgy_assignments SET status={ph}, student_submitted_at={ph}, updated_at={ph} WHERE id={ph}", (target, now, now, assignment_id))
                detail = {"submittedAt": now}
            elif action == "teacher_sign":
                if raw.get("teacher_username") != username:
                    return jsonify({"error": "只有此指派指定的臨床教師可以簽核。"}), 403
                now = utcnow(); signature = {"username": username, "name": user.get("name", ""), "signedAt": now, "comment": _text(data.get("comment"), 4000)}
                conn.execute(f"UPDATE pgy_assignments SET status={ph}, teacher_signature={ph}, updated_at={ph} WHERE id={ph}", (target, _json_dump(signature), now, assignment_id))
                detail = {"comment": signature["comment"]}
            elif action == "group_countersign":
                if raw.get("group_key") != _user_group(base, user):
                    return jsonify({"error": "組長只能複核自己組別的指派。"}), 403
                now = utcnow(); signature = {"username": username, "name": user.get("name", ""), "signedAt": now, "comment": _text(data.get("comment"), 4000)}
                conn.execute(f"UPDATE pgy_assignments SET status={ph}, group_signature={ph}, updated_at={ph} WHERE id={ph}", (target, _json_dump(signature), now, assignment_id))
                detail = {"comment": signature["comment"]}
            else:
                now = utcnow(); confirmation = {"username": username, "name": user.get("name", ""), "confirmedAt": now, "comment": _text(data.get("comment"), 4000)}
                conn.execute(f"UPDATE pgy_assignments SET status={ph}, final_confirmation={ph}, updated_at={ph} WHERE id={ph}", (target, _json_dump(confirmation), now, assignment_id))
                detail = {"comment": confirmation["comment"]}
            _audit(conn, kind, base, assignment_id, user, action, source, target, detail)
            updated = _get_assignment(conn, kind, assignment_id)
            return jsonify({"ok": True, "assignment": _assignment_dict(updated)})
        finally:
            conn.close()

    @app.post("/api/pgy/assignments/<assignment_id>/submit")
    def pgy_assignment_submit(assignment_id):
        return _workflow_action(assignment_id, "submit")

    @app.post("/api/pgy/assignments/<assignment_id>/teacher-sign")
    def pgy_assignment_teacher_sign(assignment_id):
        return _workflow_action(assignment_id, "teacher_sign")

    @app.post("/api/pgy/assignments/<assignment_id>/countersign")
    def pgy_assignment_countersign(assignment_id):
        return _workflow_action(assignment_id, "group_countersign")

    @app.post("/api/pgy/assignments/<assignment_id>/finalize")
    def pgy_assignment_finalize(assignment_id):
        return _workflow_action(assignment_id, "finalize")

    @app.post("/api/pgy/assignments/<assignment_id>/reopen")
    def pgy_assignment_reopen(assignment_id):
        user, denied = _auth(base, {"education_admin"})
        if denied:
            return denied
        data = request.get_json(silent=True) or {}; reason = _text(data.get("reason"), 4000)
        if not reason:
            return jsonify({"error": "退回/重開必須填寫原因。"}), 400
        conn, kind = base._db_conn(); ph = _ph(kind)
        try:
            row = _get_assignment(conn, kind, assignment_id)
            if not row:
                return jsonify({"error": "找不到指派。"}), 404
            raw = dict(row); old = str(raw.get("status", ""))
            if old not in {"submitted", "teacher_signed", "group_countersigned", "finalized"}:
                return jsonify({"error": "目前狀態不需要退回。"}), 409
            now = utcnow()
            conn.execute(
                f"UPDATE pgy_assignments SET status={ph},student_submitted_at={ph},teacher_signature={ph},group_signature={ph},final_confirmation={ph},updated_at={ph} WHERE id={ph}",
                ("assigned", "", "{}", "{}", "{}", now, assignment_id),
            )
            _audit(conn, kind, base, assignment_id, user, "reopen", old, "assigned", {"reason": reason})
            updated = _get_assignment(conn, kind, assignment_id)
            return jsonify({"ok": True, "assignment": _assignment_dict(updated)})
        finally:
            conn.close()

    @app.post("/api/pgy/assignments/<assignment_id>/cancel")
    def pgy_assignment_cancel(assignment_id):
        user, denied = _auth(base, {"education_admin"})
        if denied:
            return denied
        data = request.get_json(silent=True) or {}; reason = _text(data.get("reason"), 4000)
        if not reason:
            return jsonify({"error": "取消指派必須填寫原因。"}), 400
        conn, kind = base._db_conn(); ph = _ph(kind)
        try:
            row = _get_assignment(conn, kind, assignment_id)
            if not row:
                return jsonify({"error": "找不到指派。"}), 404
            raw = dict(row); old = str(raw.get("status", ""))
            if old in {"cancelled", "finalized"}:
                return jsonify({"error": "已取消或已完成的指派不可直接取消。"}), 409
            now = utcnow(); conn.execute(f"UPDATE pgy_assignments SET status={ph},updated_at={ph} WHERE id={ph}", ("cancelled", now, assignment_id))
            _audit(conn, kind, base, assignment_id, user, "cancel", old, "cancelled", {"reason": reason})
            updated = _get_assignment(conn, kind, assignment_id)
            return jsonify({"ok": True, "assignment": _assignment_dict(updated)})
        finally:
            conn.close()

    @app.get("/api/pgy/audit")
    def pgy_audit_list():
        user, denied = _auth(base, {"auditor", "system_admin", "education_admin", "group_leader"})
        if denied:
            return denied
        assignment_id = _text(request.args.get("assignmentId"), 80)
        conn, kind = base._db_conn(); ph = _ph(kind)
        try:
            role = _role(base, user); where, params = [], []
            if assignment_id:
                where.append(f"x.assignment_id={ph}"); params.append(assignment_id)
            if role == "group_leader":
                where.append(f"a.group_key={ph}"); params.append(_user_group(base, user))
            sql = """
                SELECT x.*, a.group_key, a.learner_username, a.teacher_username, a.title
                FROM pgy_assignment_audit x
                LEFT JOIN pgy_assignments a ON a.id=x.assignment_id
            """
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY x.created_at DESC"
            rows = conn.execute(sql, tuple(params)).fetchall()
            result = []
            for row in rows:
                d = dict(row)
                result.append({
                    "id": d.get("id", ""), "assignmentId": d.get("assignment_id", ""), "title": d.get("title", ""),
                    "group": d.get("group_key", ""), "learnerUsername": d.get("learner_username", ""), "teacherUsername": d.get("teacher_username", ""),
                    "action": d.get("action", ""), "fromStatus": d.get("from_status", ""), "toStatus": d.get("to_status", ""),
                    "actorUsername": d.get("actor_username", ""), "actorRole": d.get("actor_role", ""),
                    "detail": _json_load(d.get("detail"), {}), "createdAt": d.get("created_at", ""),
                })
            return jsonify(result)
        finally:
            conn.close()

    return app
