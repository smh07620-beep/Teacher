"""Teacher 6.6 PGY single / dual signing service.

Existing pre-6.6 assignments keep ``sign_mode=legacy``.
New assignments default to ``single``.

single:
    submitted -> finalized

dual:
    submitted -> teacher_signed -> finalized

For dual mode the second signer must be a different account.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from teacher_app.common.auth import (
    has_role,
)
from teacher_app.common.db import (
    execute,
    fetch_one,
    placeholder,
    transaction,
)
from teacher_app.common.errors import ApiError
from teacher_app.pgy import repository as repo
from teacher_app.pgy.workflow import (
    normalize_group,
    utcnow,
)


SIGN_MODES = {
    "legacy",
    "single",
    "dual",
}


def _username(value: Any) -> str:
    return str(
        value or ""
    ).strip().lower()[:100]


def _text(value: Any, limit: int) -> str:
    return str(
        value or ""
    ).strip()[:limit]


def normalize_sign_mode(
    value: Any,
    default: str = "legacy",
) -> str:
    mode = str(
        value or ""
    ).strip().lower()

    if mode in SIGN_MODES:
        return mode

    return default


def validate_new_sign_mode(
    value: Any,
) -> str:
    mode = str(
        value or "single"
    ).strip().lower()

    if mode not in {
        "single",
        "dual",
    }:
        raise ApiError(
            "INVALID_SIGN_MODE",
            "簽核模式只能是單層或雙層。",
            status=400,
        )

    return mode


def ensure_schema_connection(
    conn,
    kind: str,
) -> None:
    columns = {
        "sign_mode":
            "sign_mode TEXT NOT NULL DEFAULT 'legacy'",
        "first_signature":
            "first_signature TEXT NOT NULL DEFAULT '{}'",
        "second_signature":
            "second_signature TEXT NOT NULL DEFAULT '{}'",
    }

    if kind == "postgres":
        for ddl in columns.values():
            execute(
                conn,
                f"""
                ALTER TABLE pgy_assignments
                ADD COLUMN IF NOT EXISTS {ddl}
                """,
            )
        return

    existing = {
        row[1]
        for row in conn.execute(
            "PRAGMA table_info(pgy_assignments)"
        ).fetchall()
    }

    for name, ddl in columns.items():
        if name not in existing:
            execute(
                conn,
                f"""
                ALTER TABLE pgy_assignments
                ADD COLUMN {ddl}
                """,
            )


def ensure_schema(base) -> None:
    conn, kind = base._db_conn()

    try:
        ensure_schema_connection(
            conn,
            kind,
        )
    finally:
        conn.close()


def assignment_extension(
    row,
) -> dict[str, Any]:
    data = dict(row)

    return {
        "signMode":
            normalize_sign_mode(
                data.get("sign_mode"),
                "legacy",
            ),
        "firstSignature":
            repo.json_load(
                data.get(
                    "first_signature"
                ),
                {},
            ),
        "secondSignature":
            repo.json_load(
                data.get(
                    "second_signature"
                ),
                {},
            ),
    }


def assignment_dict(
    row,
) -> dict[str, Any]:
    data = repo.assignment_dict(
        row
    )

    data.update(
        assignment_extension(
            row
        )
    )

    return data


def get_sign_mode(
    base,
    assignment_id: str,
) -> str:
    conn, kind = base._db_conn()
    ph = (
        "%s"
        if kind == "postgres"
        else "?"
    )

    try:
        row = conn.execute(
            f"""
            SELECT sign_mode
            FROM pgy_assignments
            WHERE id={ph}
            """,
            (assignment_id,),
        ).fetchone()

        if not row:
            raise ApiError(
                "ASSIGNMENT_NOT_FOUND",
                "找不到指派。",
                status=404,
            )

        return normalize_sign_mode(
            dict(row).get(
                "sign_mode"
            ),
            "legacy",
        )
    finally:
        conn.close()


def _actor_group(
    user: Mapping[str, Any],
) -> str:
    return normalize_group(
        user.get("preferredGroup")
        or user.get(
            "preferred_group"
        )
    )


def _signer_role(
    user: Mapping[str, Any],
    row: Mapping[str, Any],
) -> Optional[str]:
    username = _username(
        user.get("username")
    )

    # Assigned clinical teacher takes precedence when
    # one account also carries group-leader permission.
    if (
        has_role(
            user,
            "clinical_teacher",
        )
        and str(
            row.get(
                "teacher_username",
                "",
            )
        ) == username
    ):
        return "clinical_teacher"

    if (
        has_role(
            user,
            "group_leader",
        )
        and normalize_group(
            row.get("group_key")
        )
        == _actor_group(user)
    ):
        return "group_leader"

    return None


def _signature(
    user: Mapping[str, Any],
    signer_role: str,
    comment: str,
) -> dict[str, Any]:
    return {
        "username":
            _username(
                user.get("username")
            ),
        "name":
            str(
                user.get("name", "")
            ),
        "role":
            signer_role,
        "signedAt":
            utcnow(),
        "comment":
            _text(
                comment,
                4000,
            ),
    }


def _apply_role_signature(
    extra: dict[str, Any],
    signer_role: str,
    signature: Mapping[str, Any],
) -> None:
    encoded = repo.json_dump(
        dict(signature)
    )

    if (
        signer_role
        == "clinical_teacher"
    ):
        extra[
            "teacher_signature"
        ] = encoded
    elif (
        signer_role
        == "group_leader"
    ):
        extra[
            "group_signature"
        ] = encoded


def sign_assignment(
    user: Optional[Mapping[str, Any]],
    assignment_id: str,
    data: Optional[
        Mapping[str, Any]
    ] = None,
) -> dict[str, Any]:
    if not user:
        raise ApiError(
            "LOGIN_REQUIRED",
            "請先登入後再執行此操作。",
            status=401,
            extra={
                "loginRequired": True
            },
        )

    payload = data or {}

    with transaction() as (
        conn,
        kind,
    ):
        row = repo.get_assignment(
            conn,
            kind,
            assignment_id,
        )

        if not row:
            raise ApiError(
                "ASSIGNMENT_NOT_FOUND",
                "找不到指派。",
                status=404,
            )

        mode = normalize_sign_mode(
            row.get("sign_mode"),
            "legacy",
        )

        if mode == "legacy":
            raise ApiError(
                "LEGACY_WORKFLOW",
                "此指派仍使用舊版簽核流程。",
                status=409,
            )

        if (
            str(
                row.get("status")
            )
            != "submitted"
        ):
            raise ApiError(
                "TRANSITION_CONFLICT",
                "目前狀態無法進行第一層簽核。",
                status=409,
            )

        signer_role = _signer_role(
            user,
            row,
        )

        if not signer_role:
            raise ApiError(
                "FORBIDDEN",
                "只有指定臨床教師或該組組長可以簽核。",
                status=403,
            )

        signature = _signature(
            user,
            signer_role,
            payload.get(
                "comment",
                "",
            ),
        )

        target = (
            "finalized"
            if mode == "single"
            else "teacher_signed"
        )

        extra = {
            "first_signature":
                repo.json_dump(
                    signature
                ),
            "updated_at":
                signature["signedAt"],
        }

        _apply_role_signature(
            extra,
            signer_role,
            signature,
        )

        try:
            repo.transition_status(
                conn,
                kind,
                assignment_id,
                "submitted",
                target,
                extra,
            )
        except (
            repo.TransitionConflict
        ) as exc:
            raise ApiError(
                "TRANSITION_CONFLICT",
                str(exc),
                status=409,
            ) from exc

        repo.write_audit(
            conn,
            kind,
            assignment_id=
                assignment_id,
            action="sign",
            from_status=
                "submitted",
            to_status=target,
            actor_username=
                signature[
                    "username"
                ],
            actor_role=
                signer_role,
            detail={
                "signMode": mode,
                "stage": "primary",
                "comment":
                    signature[
                        "comment"
                    ],
            },
        )

        updated = repo.get_assignment(
            conn,
            kind,
            assignment_id,
        )

        return assignment_dict(
            updated
        )


def countersign_assignment(
    user: Optional[Mapping[str, Any]],
    assignment_id: str,
    data: Optional[
        Mapping[str, Any]
    ] = None,
) -> dict[str, Any]:
    if not user:
        raise ApiError(
            "LOGIN_REQUIRED",
            "請先登入後再執行此操作。",
            status=401,
            extra={
                "loginRequired": True
            },
        )

    payload = data or {}

    with transaction() as (
        conn,
        kind,
    ):
        row = repo.get_assignment(
            conn,
            kind,
            assignment_id,
        )

        if not row:
            raise ApiError(
                "ASSIGNMENT_NOT_FOUND",
                "找不到指派。",
                status=404,
            )

        mode = normalize_sign_mode(
            row.get("sign_mode"),
            "legacy",
        )

        if mode == "single":
            raise ApiError(
                "COUNTERSIGN_NOT_REQUIRED",
                "此項目為單層簽核，不需要第二人覆核。",
                status=409,
            )

        if mode != "dual":
            raise ApiError(
                "LEGACY_WORKFLOW",
                "此指派仍使用舊版簽核流程。",
                status=409,
            )

        if (
            str(
                row.get("status")
            )
            != "teacher_signed"
        ):
            raise ApiError(
                "TRANSITION_CONFLICT",
                "目前狀態無法進行第二人覆核。",
                status=409,
            )

        signer_role = _signer_role(
            user,
            row,
        )

        if not signer_role:
            raise ApiError(
                "FORBIDDEN",
                "只有指定臨床教師或該組組長可以覆核。",
                status=403,
            )

        first_signature = (
            repo.json_load(
                row.get(
                    "first_signature"
                ),
                {},
            )
        )

        username = _username(
            user.get("username")
        )

        if (
            first_signature.get(
                "username"
            )
            == username
        ):
            raise ApiError(
                "SAME_SIGNER",
                "雙層覆核必須由第二個不同帳號完成，不能自己簽核後再自己覆核。",
                status=403,
            )

        signature = _signature(
            user,
            signer_role,
            payload.get(
                "comment",
                "",
            ),
        )

        extra = {
            "second_signature":
                repo.json_dump(
                    signature
                ),
            "updated_at":
                signature["signedAt"],
        }

        _apply_role_signature(
            extra,
            signer_role,
            signature,
        )

        try:
            repo.transition_status(
                conn,
                kind,
                assignment_id,
                "teacher_signed",
                "finalized",
                extra,
            )
        except (
            repo.TransitionConflict
        ) as exc:
            raise ApiError(
                "TRANSITION_CONFLICT",
                str(exc),
                status=409,
            ) from exc

        repo.write_audit(
            conn,
            kind,
            assignment_id=
                assignment_id,
            action="countersign",
            from_status=
                "teacher_signed",
            to_status="finalized",
            actor_username=
                signature[
                    "username"
                ],
            actor_role=
                signer_role,
            detail={
                "signMode": "dual",
                "stage": "secondary",
                "comment":
                    signature[
                        "comment"
                    ],
                "firstSigner":
                    first_signature.get(
                        "username",
                        "",
                    ),
            },
        )

        updated = repo.get_assignment(
            conn,
            kind,
            assignment_id,
        )

        return assignment_dict(
            updated
        )


def reopen_assignment(
    user: Optional[Mapping[str, Any]],
    assignment_id: str,
    data: Optional[
        Mapping[str, Any]
    ] = None,
) -> dict[str, Any]:
    if not user:
        raise ApiError(
            "LOGIN_REQUIRED",
            "請先登入後再執行此操作。",
            status=401,
            extra={
                "loginRequired": True
            },
        )

    if not has_role(
        user,
        "education_admin",
    ):
        raise ApiError(
            "FORBIDDEN",
            "權限不足。",
            status=403,
        )

    payload = data or {}

    reason = _text(
        payload.get("reason"),
        4000,
    )

    if not reason:
        raise ApiError(
            "REASON_REQUIRED",
            "退回/重開必須填寫原因。",
            status=400,
        )

    with transaction() as (
        conn,
        kind,
    ):
        row = repo.get_assignment(
            conn,
            kind,
            assignment_id,
        )

        if not row:
            raise ApiError(
                "ASSIGNMENT_NOT_FOUND",
                "找不到指派。",
                status=404,
            )

        mode = normalize_sign_mode(
            row.get("sign_mode"),
            "legacy",
        )

        if mode == "legacy":
            raise ApiError(
                "LEGACY_WORKFLOW",
                "此指派仍使用舊版退回流程。",
                status=409,
            )

        old_status = str(
            row.get("status", "")
        )

        if old_status not in {
            "submitted",
            "teacher_signed",
            "finalized",
        }:
            raise ApiError(
                "CONFLICT",
                "目前狀態不需要退回。",
                status=409,
            )

        now = utcnow()

        try:
            repo.transition_status(
                conn,
                kind,
                assignment_id,
                old_status,
                "assigned",
                {
                    "student_submitted_at":
                        "",
                    "teacher_signature":
                        "{}",
                    "group_signature":
                        "{}",
                    "final_confirmation":
                        "{}",
                    "first_signature":
                        "{}",
                    "second_signature":
                        "{}",
                    "updated_at":
                        now,
                },
            )
        except (
            repo.TransitionConflict
        ) as exc:
            raise ApiError(
                "TRANSITION_CONFLICT",
                str(exc),
                status=409,
            ) from exc

        repo.write_audit(
            conn,
            kind,
            assignment_id=
                assignment_id,
            action="reopen",
            from_status=
                old_status,
            to_status="assigned",
            actor_username=
                _username(
                    user.get(
                        "username"
                    )
                ),
            actor_role=
                "education_admin",
            detail={
                "reason": reason,
                "signMode": mode,
            },
        )

        updated = repo.get_assignment(
            conn,
            kind,
            assignment_id,
        )

        return assignment_dict(
            updated
        )
