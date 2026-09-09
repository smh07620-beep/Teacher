"""Atomic PGY status transitions for Teacher 6.3.

Overrides only the six state-changing Phase 3 endpoints after the legacy
``pgy_workflow`` routes are registered. The rest of the PGY API stays unchanged.
"""
from __future__ import annotations

from contextlib import contextmanager

from flask import jsonify, request

import pgy_workflow as wf


@contextmanager
def _transaction(conn, kind: str):
    if kind == "postgres":
        with conn.transaction():
            yield
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()


def _expect_one(cursor) -> None:
    if getattr(cursor, "rowcount", 1) != 1:
        raise RuntimeError("此指派狀態已由其他請求更新，請重新整理後再操作。")


def register_pgy_atomic_workflow(base):
    app = base.app
    if app.extensions.get("pgy_atomic_registered"):
        return app
    app.extensions["pgy_atomic_registered"] = True

    def workflow_action(assignment_id: str, action: str):
        source, target, required_role = wf.WORKFLOW_TRANSITIONS[action]
        user, denied = wf._auth(base, {required_role})
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        conn, kind = base._db_conn(); ph = wf._ph(kind)
        try:
            with _transaction(conn, kind):
                row = wf._get_assignment(conn, kind, assignment_id)
                if not row:
                    return jsonify({"error": "找不到指派。"}), 404
                raw = dict(row); role = wf._role(base, user); username = wf._username(user.get("username"))
                if not wf.transition_allowed(raw.get("status"), action, role):
                    return jsonify({"error": f"目前狀態 {raw.get('status')} 無法執行 {action}。"}), 409
                if action == "submit":
                    if raw.get("learner_username") != username:
                        return jsonify({"error": "只能送出自己的指派。"}), 403
                    evidence = wf._json_load(raw.get("evidence"), {})
                    reflection = str(raw.get("reflection", "")).strip()
                    if not evidence and not reflection:
                        return jsonify({"error": "送出前至少需填寫反思或佐證內容。"}), 400
                    now = wf.utcnow()
                    cur = conn.execute(
                        f"UPDATE pgy_assignments SET status={ph}, student_submitted_at={ph}, updated_at={ph} WHERE id={ph} AND status={ph}",
                        (target, now, now, assignment_id, source),
                    )
                    detail = {"submittedAt": now}
                elif action == "teacher_sign":
                    if raw.get("teacher_username") != username:
                        return jsonify({"error": "只有此指派指定的臨床教師可以簽核。"}), 403
                    now = wf.utcnow(); signature = {"username": username, "name": user.get("name", ""), "signedAt": now, "comment": wf._text(data.get("comment"), 4000)}
                    cur = conn.execute(
                        f"UPDATE pgy_assignments SET status={ph}, teacher_signature={ph}, updated_at={ph} WHERE id={ph} AND status={ph}",
                        (target, wf._json_dump(signature), now, assignment_id, source),
                    )
                    detail = {"comment": signature["comment"]}
                elif action == "group_countersign":
                    if raw.get("group_key") != wf._user_group(base, user):
                        return jsonify({"error": "組長只能複核自己組別的指派。"}), 403
                    now = wf.utcnow(); signature = {"username": username, "name": user.get("name", ""), "signedAt": now, "comment": wf._text(data.get("comment"), 4000)}
                    cur = conn.execute(
                        f"UPDATE pgy_assignments SET status={ph}, group_signature={ph}, updated_at={ph} WHERE id={ph} AND status={ph}",
                        (target, wf._json_dump(signature), now, assignment_id, source),
                    )
                    detail = {"comment": signature["comment"]}
                else:
                    now = wf.utcnow(); confirmation = {"username": username, "name": user.get("name", ""), "confirmedAt": now, "comment": wf._text(data.get("comment"), 4000)}
                    cur = conn.execute(
                        f"UPDATE pgy_assignments SET status={ph}, final_confirmation={ph}, updated_at={ph} WHERE id={ph} AND status={ph}",
                        (target, wf._json_dump(confirmation), now, assignment_id, source),
                    )
                    detail = {"comment": confirmation["comment"]}
                _expect_one(cur)
                wf._audit(conn, kind, base, assignment_id, user, action, source, target, detail)
                updated = wf._get_assignment(conn, kind, assignment_id)
            return jsonify({"ok": True, "assignment": wf._assignment_dict(updated)})
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 409
        finally:
            conn.close()

    def submit(assignment_id):
        return workflow_action(assignment_id, "submit")

    def teacher_sign(assignment_id):
        return workflow_action(assignment_id, "teacher_sign")

    def countersign(assignment_id):
        return workflow_action(assignment_id, "group_countersign")

    def finalize(assignment_id):
        return workflow_action(assignment_id, "finalize")

    def reopen(assignment_id):
        user, denied = wf._auth(base, {"education_admin"})
        if denied:
            return denied
        data = request.get_json(silent=True) or {}; reason = wf._text(data.get("reason"), 4000)
        if not reason:
            return jsonify({"error": "退回/重開必須填寫原因。"}), 400
        conn, kind = base._db_conn(); ph = wf._ph(kind)
        try:
            with _transaction(conn, kind):
                row = wf._get_assignment(conn, kind, assignment_id)
                if not row:
                    return jsonify({"error": "找不到指派。"}), 404
                raw = dict(row); old = str(raw.get("status", ""))
                if old not in {"submitted", "teacher_signed", "group_countersigned", "finalized"}:
                    return jsonify({"error": "目前狀態不需要退回。"}), 409
                now = wf.utcnow()
                cur = conn.execute(
                    f"UPDATE pgy_assignments SET status={ph},student_submitted_at={ph},teacher_signature={ph},group_signature={ph},final_confirmation={ph},updated_at={ph} WHERE id={ph} AND status={ph}",
                    ("assigned", "", "{}", "{}", "{}", now, assignment_id, old),
                )
                _expect_one(cur)
                wf._audit(conn, kind, base, assignment_id, user, "reopen", old, "assigned", {"reason": reason})
                updated = wf._get_assignment(conn, kind, assignment_id)
            return jsonify({"ok": True, "assignment": wf._assignment_dict(updated)})
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 409
        finally:
            conn.close()

    def cancel(assignment_id):
        user, denied = wf._auth(base, {"education_admin"})
        if denied:
            return denied
        data = request.get_json(silent=True) or {}; reason = wf._text(data.get("reason"), 4000)
        if not reason:
            return jsonify({"error": "取消指派必須填寫原因。"}), 400
        conn, kind = base._db_conn(); ph = wf._ph(kind)
        try:
            with _transaction(conn, kind):
                row = wf._get_assignment(conn, kind, assignment_id)
                if not row:
                    return jsonify({"error": "找不到指派。"}), 404
                raw = dict(row); old = str(raw.get("status", ""))
                if old in {"cancelled", "finalized"}:
                    return jsonify({"error": "已取消或已完成的指派不可直接取消。"}), 409
                now = wf.utcnow()
                cur = conn.execute(
                    f"UPDATE pgy_assignments SET status={ph},updated_at={ph} WHERE id={ph} AND status={ph}",
                    ("cancelled", now, assignment_id, old),
                )
                _expect_one(cur)
                wf._audit(conn, kind, base, assignment_id, user, "cancel", old, "cancelled", {"reason": reason})
                updated = wf._get_assignment(conn, kind, assignment_id)
            return jsonify({"ok": True, "assignment": wf._assignment_dict(updated)})
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 409
        finally:
            conn.close()

    app.view_functions["pgy_assignment_submit"] = submit
    app.view_functions["pgy_assignment_teacher_sign"] = teacher_sign
    app.view_functions["pgy_assignment_countersign"] = countersign
    app.view_functions["pgy_assignment_finalize"] = finalize
    app.view_functions["pgy_assignment_reopen"] = reopen
    app.view_functions["pgy_assignment_cancel"] = cancel
    return app
