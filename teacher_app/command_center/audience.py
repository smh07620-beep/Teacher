"""Teacher 7.1 audience/profile classification.

`pgy_learner` is an explicit admin-managed training audience flag. It is not
an RBAC role and never grants signing, administration, or clinical authority.
Professional title remains presentation-only metadata.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from flask import g, jsonify, request

from teacher_app.common import db as common_db
from teacher_app.common.auth import has_permission, normalize_role, user_roles
from teacher_app.common.errors import ApiError


def _username(value: Any) -> str:
    return str(value or "").strip().lower()[:100]


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


def _row_for_username(username: str) -> dict[str, Any]:
    if not username:
        return {}
    try:
        with common_db.read_connection() as (conn, kind):
            ph = common_db.placeholder(kind)
            try:
                row = conn.execute(
                    f"""
                    SELECT username,display_name,emp_id,role,roles_json,
                           preferred_group,professional_title,pgy_learner
                    FROM user_accounts
                    WHERE username={ph}
                    """,
                    (username,),
                ).fetchone()
            except Exception:
                # Pre-0071/isolated test databases fail closed to ordinary online
                # training rather than guessing a PGY identity.
                try:
                    row = conn.execute(
                        f"""
                        SELECT username,display_name,emp_id,role,roles_json,
                               preferred_group,professional_title
                        FROM user_accounts
                        WHERE username={ph}
                        """,
                        (username,),
                    ).fetchone()
                except Exception:
                    return {}
            return dict(row) if row else {}
    except Exception:
        return {}


def current_profile(user: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    if not user:
        raise ApiError(
            "LOGIN_REQUIRED",
            "請先登入後再讀取訓練身分。",
            status=401,
            extra={"loginRequired": True},
        )

    username = _username(user.get("username"))
    stored = _row_for_username(username)
    role = normalize_role(stored.get("role") or user.get("role") or "student")
    merged = dict(user)
    merged.update(stored)
    roles = list(user_roles(merged))

    # Explicit mapping values make isolated tests deterministic; production
    # normally reads the persisted column above.
    if "pgyLearner" in user:
        pgy_learner = _bool(user.get("pgyLearner"))
    else:
        pgy_learner = _bool(stored.get("pgy_learner", False))

    professional_title = str(
        stored.get("professional_title")
        or user.get("professionalTitle")
        or ""
    ).strip()[:100]

    return {
        "username": username,
        "name": str(stored.get("display_name") or user.get("name") or "").strip()[:100],
        "empId": str(stored.get("emp_id") or user.get("empId") or user.get("emp_id") or "").strip()[:100],
        "role": role,
        "roles": roles,
        "professionalTitle": professional_title,
        "pgyLearner": pgy_learner,
        "audience": "pgy" if pgy_learner else "online",
        "group": str(stored.get("preferred_group") or user.get("preferredGroup") or user.get("preferred_group") or ""),
    }


def annotate_learners(learners: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = [dict(item) for item in learners]
    usernames = [_username(item.get("username")) for item in output if _username(item.get("username"))]
    flags: dict[str, bool] = {}
    if usernames:
        try:
            with common_db.read_connection() as (conn, kind):
                ph = common_db.placeholder(kind)
                marks = ",".join(ph for _ in usernames)
                try:
                    rows = conn.execute(
                        f"SELECT username,pgy_learner FROM user_accounts WHERE username IN ({marks})",
                        tuple(usernames),
                    ).fetchall()
                    flags = {
                        _username(dict(row).get("username")): _bool(dict(row).get("pgy_learner"))
                        for row in rows
                    }
                except Exception:
                    flags = {}
        except Exception:
            flags = {}

    for item in output:
        username = _username(item.get("username"))
        direct = item.get("pgyLearner") if "pgyLearner" in item else None
        is_pgy = _bool(direct) if direct is not None else bool(flags.get(username, False))
        item["pgyLearner"] = is_pgy
        item["audience"] = "pgy" if is_pgy else "online"
    return output


def _app(owner):
    return getattr(owner, "app", owner)


def _current_user(owner=None):
    if hasattr(g, "teacher_user"):
        return g.teacher_user
    resolver = getattr(owner, "_current_user", None)
    return resolver() if callable(resolver) else None


def register_training_audience_71(owner):
    """Admin management API for the explicit PGY learner audience flag."""
    app = _app(owner)
    if app.extensions.get("teacher_training_audience_71_registered"):
        return app

    def authorized():
        actor = _current_user(owner)
        if not actor:
            return None, (jsonify({"error": "請先登入。", "loginRequired": True}), 401)
        if not has_permission(actor, "user.manage"):
            return None, (jsonify({"error": "權限不足。"}), 403)
        return actor, None

    def read_flag(username: str):
        key = _username(username)
        with common_db.read_connection() as (conn, kind):
            ph = common_db.placeholder(kind)
            row = conn.execute(
                f"SELECT username,pgy_learner FROM user_accounts WHERE username={ph}",
                (key,),
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        return {"username": key, "pgyLearner": _bool(data.get("pgy_learner"))}

    @app.get("/api/users/<username>/training-audience")
    def training_audience_get(username):
        _actor, denied = authorized()
        if denied:
            return denied
        result = read_flag(username)
        if not result:
            return jsonify({"error": "找不到帳號。"}), 404
        return jsonify(result)

    @app.patch("/api/users/<username>/training-audience")
    def training_audience_update(username):
        _actor, denied = authorized()
        if denied:
            return denied
        payload = request.get_json(silent=True) or {}
        value = payload.get("pgyLearner")
        if type(value) is not bool:
            return jsonify({"error": "PGY 學員狀態必須為布林值。"}), 400
        key = _username(username)
        with common_db.transaction() as (conn, kind):
            ph = common_db.placeholder(kind)
            row = conn.execute(f"SELECT username FROM user_accounts WHERE username={ph}", (key,)).fetchone()
            if not row:
                return jsonify({"error": "找不到帳號。"}), 404
            stored = value if kind == "postgres" else int(value)
            conn.execute(
                f"UPDATE user_accounts SET pgy_learner={ph} WHERE username={ph}",
                (stored, key),
            )
        return jsonify({"ok": True, "username": key, "pgyLearner": value})

    app.extensions["teacher_training_audience_71_registered"] = True
    return app
