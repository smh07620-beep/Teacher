"""Teacher 6.6 M1A multi-role compatibility adapter.

The legacy `role` column remains the primary role.
`roles_json` stores additional roles without breaking old clients.
"""
from __future__ import annotations

import datetime
import json

from flask import jsonify, request
from werkzeug.security import generate_password_hash

from teacher_app.auth.service import public_user
from teacher_app.common.auth import (
    CANONICAL_ROLES,
    LEGACY_ROLE_ALIASES,
    normalize_role,
    normalize_roles,
)


def _json_roles(roles):
    return json.dumps(
        list(roles),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _ensure_schema(base):
    conn, kind = base._db_conn()

    try:
        if kind == "postgres":
            conn.execute(
                """
                ALTER TABLE user_accounts
                ADD COLUMN IF NOT EXISTS
                roles_json TEXT NOT NULL DEFAULT '[]'
                """
            )
        else:
            columns = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(user_accounts)"
                ).fetchall()
            }

            if "roles_json" not in columns:
                conn.execute(
                    """
                    ALTER TABLE user_accounts
                    ADD COLUMN roles_json
                    TEXT NOT NULL DEFAULT '[]'
                    """
                )
    finally:
        conn.close()


def _validate_raw_roles(value):
    if value is None:
        return

    if isinstance(value, str):
        raw = [
            item.strip()
            for item in value.split(",")
            if item.strip()
        ]
    elif isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        raise ValueError(
            "roles 必須為角色陣列。"
        )

    for item in raw:
        code = str(item or "").strip().lower()

        if (
            code not in CANONICAL_ROLES
            and code not in LEGACY_ROLE_ALIASES
        ):
            raise ValueError(
                f"角色格式不正確：{code}"
            )


def _roles_for_create(data):
    requested_role = str(
        data.get("role", "student")
    ).strip().lower()

    if (
        requested_role not in CANONICAL_ROLES
        and requested_role not in LEGACY_ROLE_ALIASES
    ):
        raise ValueError(
            "角色格式不正確。"
        )

    _validate_raw_roles(
        data.get("roles")
    )

    primary = normalize_role(
        requested_role
    )

    roles = normalize_roles(
        data.get("roles"),
        primary=primary,
    )

    return primary, roles


def _roles_for_update(data, current):
    current_primary = normalize_role(
        current.get("role", "student")
    )

    current_roles = normalize_roles(
        current.get("roles_json"),
        primary=current_primary,
    )

    if (
        "role" not in data
        and "roles" not in data
    ):
        return (
            current_primary,
            current_roles,
            False,
        )

    if "role" in data:
        requested = str(
            data.get("role", "")
        ).strip().lower()

        if (
            requested not in CANONICAL_ROLES
            and requested not in LEGACY_ROLE_ALIASES
        ):
            raise ValueError(
                "角色格式不正確。"
            )

        primary = normalize_role(
            requested
        )
    else:
        primary = current_primary

    if "roles" in data:
        _validate_raw_roles(
            data.get("roles")
        )

        roles = normalize_roles(
            data.get("roles"),
            primary=primary,
        )
    elif "role" in data:
        # A legacy client changing only `role`
        # keeps legacy single-role semantics.
        roles = [primary]
    else:
        roles = current_roles

    if primary not in roles:
        roles.insert(
            0,
            primary,
        )

    changed = (
        primary != current_primary
        or roles != current_roles
    )

    return primary, roles, changed


def register_multi_role_66(base):
    app = base.app

    if app.extensions.get(
        "teacher_multi_role_66_registered"
    ):
        return app

    _ensure_schema(base)

    def users_admin():
        denied = base.require_admin()

        if denied:
            return denied

        conn, _kind = base._db_conn()

        try:
            rows = conn.execute(
                """
                SELECT *
                FROM user_accounts
                ORDER BY active DESC,
                         display_name ASC,
                         username ASC
                """
            ).fetchall()

            return jsonify(
                [
                    public_user(
                        base,
                        row,
                        include_roles=True,
                    )
                    for row in rows
                ]
            )
        finally:
            conn.close()

    def user_create():
        denied = base.require_admin()

        if denied:
            return denied

        data = (
            request.get_json(
                silent=True
            )
            or {}
        )

        username = base._normalize_username(
            data.get("username")
        )

        password = str(
            data.get("password", "")
        )

        name = str(
            data.get("name", "")
        ).strip()[:100]

        emp_id = str(
            data.get("empId", "")
        ).strip()[:100]

        if (
            len(username) < 3
            or len(password) < 4
            or not name
            or not emp_id
        ):
            return jsonify(
                {
                    "error":
                    "帳號至少 3 碼、密碼至少 4 碼，姓名與工號皆為必填。"
                }
            ), 400

        try:
            role, roles = (
                _roles_for_create(
                    data
                )
            )
        except ValueError as exc:
            return jsonify(
                {"error": str(exc)}
            ), 400

        area = base.normalize_area(
            data.get(
                "preferredArea",
                base.DEFAULT_TRAINING_AREA,
            )
        )

        group = base.normalize_group(
            data.get(
                "preferredGroup",
                base.DEFAULT_GROUP,
            )
        )

        now = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()

        conn, kind = base._db_conn()

        ph = (
            "%s"
            if kind == "postgres"
            else "?"
        )

        try:
            conn.execute(
                f"""
                INSERT INTO user_accounts
                (
                    username,
                    password_hash,
                    display_name,
                    emp_id,
                    role,
                    roles_json,
                    preferred_area,
                    preferred_group,
                    active,
                    session_version,
                    created_at,
                    updated_at,
                    last_login_at
                )
                VALUES (
                    {','.join([ph] * 13)}
                )
                """,
                (
                    username,
                    generate_password_hash(
                        password
                    ),
                    name,
                    emp_id,
                    role,
                    _json_roles(roles),
                    area,
                    group,
                    (
                        True
                        if kind == "postgres"
                        else 1
                    ),
                    1,
                    now,
                    now,
                    "",
                ),
            )

            created = conn.execute(
                f"""
                SELECT *
                FROM user_accounts
                WHERE username={ph}
                """,
                (username,),
            ).fetchone()

        except Exception as exc:
            return jsonify(
                {
                    "error":
                    "帳號或工號已存在。",
                    "detail":
                    str(exc)[:180],
                }
            ), 409

        finally:
            conn.close()

        return jsonify(
            {
                "ok": True,
                "user": public_user(
                    base,
                    created,
                    include_roles=True,
                ),
            }
        )

    def user_update(username):
        denied = base.require_admin()

        if denied:
            return denied

        username = base._normalize_username(
            username
        )

        data = (
            request.get_json(
                silent=True
            )
            or {}
        )

        conn, kind = base._db_conn()

        ph = (
            "%s"
            if kind == "postgres"
            else "?"
        )

        try:
            row = conn.execute(
                f"""
                SELECT *
                FROM user_accounts
                WHERE username={ph}
                """,
                (username,),
            ).fetchone()

            if not row:
                return jsonify(
                    {
                        "error":
                        "找不到帳號。"
                    }
                ), 404

            current = dict(row)

            fields = []
            values = []

            mapping = {
                "name": "display_name",
                "empId": "emp_id",
                "preferredArea":
                    "preferred_area",
                "preferredGroup":
                    "preferred_group",
            }

            for key, column in (
                mapping.items()
            ):
                if key not in data:
                    continue

                value = str(
                    data.get(key, "")
                ).strip()[:100]

                if key == "preferredArea":
                    value = (
                        base.normalize_area(
                            value
                        )
                    )

                if key == "preferredGroup":
                    value = (
                        base.normalize_group(
                            value
                        )
                    )

                if (
                    key in {
                        "name",
                        "empId",
                    }
                    and not value
                ):
                    return jsonify(
                        {
                            "error":
                            "姓名與工號不可空白。"
                        }
                    ), 400

                fields.append(
                    f"{column}={ph}"
                )
                values.append(
                    value
                )

            try:
                (
                    role,
                    roles,
                    roles_changed,
                ) = _roles_for_update(
                    data,
                    current,
                )
            except ValueError as exc:
                return jsonify(
                    {"error": str(exc)}
                ), 400

            if roles_changed:
                fields.extend(
                    [
                        f"role={ph}",
                        f"roles_json={ph}",
                        (
                            "session_version="
                            "session_version+1"
                        ),
                    ]
                )

                values.extend(
                    [
                        role,
                        _json_roles(
                            roles
                        ),
                    ]
                )

            if "active" in data:
                active = data.get(
                    "active"
                )

                if type(active) is not bool:
                    return jsonify(
                        {
                            "error":
                            "帳號狀態格式不正確。"
                        }
                    ), 400

                fields.append(
                    f"active={ph}"
                )

                values.append(
                    (
                        active
                        if kind == "postgres"
                        else int(active)
                    )
                )

                if not active:
                    fields.append(
                        "session_version="
                        "session_version+1"
                    )

            password = str(
                data.get(
                    "password",
                    "",
                )
            )

            if password:
                if len(password) < 4:
                    return jsonify(
                        {
                            "error":
                            "新密碼至少 4 碼。"
                        }
                    ), 400

                fields.extend(
                    [
                        f"password_hash={ph}",
                        (
                            "session_version="
                            "session_version+1"
                        ),
                    ]
                )

                values.append(
                    generate_password_hash(
                        password
                    )
                )

            if not fields:
                return jsonify(
                    {
                        "error":
                        "沒有可更新的欄位。"
                    }
                ), 400

            fields.append(
                f"updated_at={ph}"
            )

            values.append(
                datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat()
            )

            values.append(
                username
            )

            conn.execute(
                f"""
                UPDATE user_accounts
                SET {','.join(fields)}
                WHERE username={ph}
                """,
                values,
            )

            updated = conn.execute(
                f"""
                SELECT *
                FROM user_accounts
                WHERE username={ph}
                """,
                (username,),
            ).fetchone()

            return jsonify(
                {
                    "ok": True,
                    "user": public_user(
                        base,
                        updated,
                        include_roles=True,
                    ),
                }
            )

        except Exception as exc:
            return jsonify(
                {
                    "error":
                    "更新失敗，請確認工號未被其他帳號使用。",
                    "detail":
                    str(exc)[:180],
                }
            ), 409

        finally:
            conn.close()

    # Replace existing Flask view functions by URL,
    # without changing public API paths.
    for rule in list(
        app.url_map.iter_rules()
    ):
        if (
            rule.rule == "/api/users"
            and "GET" in rule.methods
        ):
            app.view_functions[
                rule.endpoint
            ] = users_admin

        elif (
            rule.rule == "/api/users"
            and "POST" in rule.methods
        ):
            app.view_functions[
                rule.endpoint
            ] = user_create

        elif (
            rule.rule ==
            "/api/users/<username>"
            and "PATCH" in rule.methods
        ):
            app.view_functions[
                rule.endpoint
            ] = user_update

    app.extensions[
        "teacher_multi_role_66_registered"
    ] = True

    return app
