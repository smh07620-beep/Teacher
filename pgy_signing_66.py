"""Teacher 6.6 single/dual PGY signing compatibility adapter.

Public URLs remain unchanged.
Legacy assignments continue using the 6.5 workflow.
"""

from __future__ import annotations

from flask import (
    jsonify,
    request,
)

import pgy_workflow as wf
from teacher_app.common.auth import (
    has_role,
    user_roles,
)
from teacher_app.common.errors import (
    ApiError,
)
from teacher_app.pgy import (
    signing,
)


def _error(exc: ApiError):
    body = {
        "error": exc.message
    }

    if exc.extra.get(
        "loginRequired"
    ):
        body[
            "loginRequired"
        ] = True

    return jsonify(
        body
    ), exc.status


def _current_user(base):
    user = base._current_user()

    if not user:
        raise ApiError(
            "LOGIN_REQUIRED",
            "請先登入後再執行此操作。",
            status=401,
            extra={
                "loginRequired": True
            },
        )

    return user


def _row_has_role(
    row,
    role: str,
) -> bool:
    data = dict(row)

    probe = {
        "role":
            data.get(
                "role",
                "student",
            ),
        "roles_json":
            data.get(
                "roles_json",
                "[]",
            ),
    }

    return role in user_roles(
        probe
    )


def _user_group(
    base,
    user,
) -> str:
    return base.normalize_group(
        user.get(
            "preferredGroup"
        )
        or user.get(
            "preferred_group"
        )
    )


def _assignment_mode(
    base,
    assignment_id,
):
    return signing.get_sign_mode(
        base,
        assignment_id,
    )


def register_pgy_signing_66(
    base,
):
    app = base.app

    if app.extensions.get(
        "teacher_pgy_signing_66_registered"
    ):
        return app

    signing.ensure_schema(
        base
    )

    # --------------------------------------------------------
    # Extend existing assignment JSON contract additively.
    # --------------------------------------------------------

    original_assignment_dict = (
        wf._assignment_dict
    )

    def assignment_dict_66(row):
        data = original_assignment_dict(
            row
        )

        data.update(
            signing.assignment_extension(
                row
            )
        )

        return data

    wf._assignment_dict = (
        assignment_dict_66
    )

    # --------------------------------------------------------
    # Preserve existing handlers for legacy rows.
    # --------------------------------------------------------

    legacy_teacher_sign = (
        app.view_functions[
            "pgy_assignment_teacher_sign"
        ]
    )

    legacy_countersign = (
        app.view_functions[
            "pgy_assignment_countersign"
        ]
    )

    legacy_reopen = (
        app.view_functions[
            "pgy_assignment_reopen"
        ]
    )

    legacy_update = (
        app.view_functions[
            "pgy_assignment_update"
        ]
    )

    # --------------------------------------------------------
    # Meta: additive roles/signingModes.
    # --------------------------------------------------------

    def workflow_meta():
        try:
            user = _current_user(
                base
            )
        except ApiError as exc:
            return _error(exc)

        roles = user_roles(
            user
        )

        actions = []

        if "student" in roles:
            actions.append(
                "submit"
            )

        if (
            "clinical_teacher"
            in roles
            or "group_leader"
            in roles
        ):
            actions.extend(
                [
                    "sign",
                    "countersign",
                ]
            )

        if (
            "education_admin"
            in roles
        ):
            actions.extend(
                [
                    "create",
                    "edit_assignment",
                    "reopen",
                    "cancel",
                ]
            )

        return jsonify(
            {
                "statuses":
                    sorted(
                        wf.ASSIGNMENT_STATUSES
                    ),
                "actions":
                    actions,
                # Keep old primary-role field.
                "role":
                    base.normalize_role(
                        user.get(
                            "role"
                        )
                    ),
                "roles":
                    roles,
                "signatureOrder":
                    [
                        "student",
                        "clinical_teacher",
                        "group_leader",
                        "education_admin",
                    ],
                "signingModes":
                    [
                        "single",
                        "dual",
                    ],
            }
        )

    app.view_functions[
        "pgy_workflow_meta"
    ] = workflow_meta

    # --------------------------------------------------------
    # Multi-role aware candidate list.
    # --------------------------------------------------------

    def candidates():
        try:
            user = _current_user(
                base
            )
        except ApiError as exc:
            return _error(exc)

        roles = user_roles(
            user
        )

        if not (
            "education_admin"
            in roles
            or "group_leader"
            in roles
        ):
            return jsonify(
                {
                    "error":
                        "權限不足。"
                }
            ), 403

        requested_group = (
            base.normalize_group(
                request.args.get(
                    "group"
                )
                or _user_group(
                    base,
                    user,
                )
            )
        )

        if (
            "education_admin"
            not in roles
            and "group_leader"
            in roles
            and requested_group
            != _user_group(
                base,
                user,
            )
        ):
            return jsonify(
                {
                    "error":
                        "組長只能查看自己組別的指派候選人。"
                }
            ), 403

        conn, _kind = (
            base._db_conn()
        )

        try:
            rows = conn.execute(
                """
                SELECT
                    username,
                    display_name,
                    emp_id,
                    role,
                    roles_json,
                    preferred_group,
                    active
                FROM user_accounts
                ORDER BY display_name ASC
                """
            ).fetchall()

            students = []
            teachers = []

            for row in rows:
                data = dict(row)

                if not bool(
                    data.get(
                        "active",
                        True,
                    )
                ):
                    continue

                group = (
                    base.normalize_group(
                        data.get(
                            "preferred_group"
                        )
                    )
                )

                if (
                    group
                    != requested_group
                ):
                    continue

                item = {
                    "username":
                        data.get(
                            "username",
                            "",
                        ),
                    "name":
                        data.get(
                            "display_name",
                            "",
                        ),
                    "empId":
                        data.get(
                            "emp_id",
                            "",
                        ),
                    "group":
                        group,
                    "roles":
                        user_roles(
                            {
                                "role":
                                    data.get(
                                        "role"
                                    ),
                                "roles_json":
                                    data.get(
                                        "roles_json"
                                    ),
                            }
                        ),
                }

                if _row_has_role(
                    data,
                    "student",
                ):
                    students.append(
                        item
                    )

                if _row_has_role(
                    data,
                    "clinical_teacher",
                ):
                    teachers.append(
                        item
                    )

            return jsonify(
                {
                    "group":
                        requested_group,
                    "students":
                        students,
                    "teachers":
                        teachers,
                }
            )

        finally:
            conn.close()

    app.view_functions[
        "pgy_assignment_candidates"
    ] = candidates

    # --------------------------------------------------------
    # Multi-role aware list/get.
    # --------------------------------------------------------

    def list_assignments():
        try:
            user = _current_user(
                base
            )
        except ApiError as exc:
            return _error(exc)

        roles = set(
            user_roles(user)
        )

        permitted = {
            "student",
            "clinical_teacher",
            "group_leader",
            "education_admin",
        }

        if not (
            roles
            & permitted
        ):
            return jsonify(
                {
                    "error":
                        "權限不足。"
                }
            ), 403

        conn, kind = (
            base._db_conn()
        )

        ph = wf._ph(
            kind
        )

        try:
            where = [
                "a.training_area='pgy'"
            ]

            params = []

            username = wf._username(
                user.get("username")
            )

            if (
                "education_admin"
                not in roles
            ):
                scopes = []

                if (
                    "student"
                    in roles
                ):
                    scopes.append(
                        f"a.learner_username={ph}"
                    )
                    params.append(
                        username
                    )

                if (
                    "clinical_teacher"
                    in roles
                ):
                    scopes.append(
                        f"a.teacher_username={ph}"
                    )
                    params.append(
                        username
                    )

                if (
                    "group_leader"
                    in roles
                ):
                    scopes.append(
                        f"a.group_key={ph}"
                    )
                    params.append(
                        _user_group(
                            base,
                            user,
                        )
                    )

                if not scopes:
                    return jsonify(
                        {
                            "error":
                                "權限不足。"
                        }
                    ), 403

                where.append(
                    "("
                    + " OR ".join(
                        scopes
                    )
                    + ")"
                )

            status = wf._text(
                request.args.get(
                    "status"
                ),
                40,
            )

            if status:
                if (
                    status
                    not in wf.ASSIGNMENT_STATUSES
                ):
                    return jsonify(
                        {
                            "error":
                                "狀態格式不正確。"
                        }
                    ), 400

                where.append(
                    f"a.status={ph}"
                )

                params.append(
                    status
                )

            group = wf._text(
                request.args.get(
                    "group"
                ),
                40,
            )

            if (
                group
                and "education_admin"
                in roles
            ):
                where.append(
                    f"a.group_key={ph}"
                )

                params.append(
                    base.normalize_group(
                        group
                    )
                )

            rows = conn.execute(
                wf._assignment_query()
                + " WHERE "
                + " AND ".join(
                    where
                )
                + " ORDER BY a.updated_at DESC",
                tuple(params),
            ).fetchall()

            return jsonify(
                [
                    wf._assignment_dict(
                        row
                    )
                    for row in rows
                ]
            )

        finally:
            conn.close()

    app.view_functions[
        "pgy_assignments_list"
    ] = list_assignments

    def assignment_get(
        assignment_id,
    ):
        try:
            user = _current_user(
                base
            )
        except ApiError as exc:
            return _error(exc)

        roles = set(
            user_roles(user)
        )

        conn, kind = (
            base._db_conn()
        )

        try:
            row = wf._get_assignment(
                conn,
                kind,
                assignment_id,
            )

            if not row:
                return jsonify(
                    {
                        "error":
                            "找不到指派。"
                    }
                ), 404

            data = dict(row)

            username = (
                wf._username(
                    user.get(
                        "username"
                    )
                )
            )

            allowed = False

            if (
                "education_admin"
                in roles
            ):
                allowed = True

            if (
                "student"
                in roles
                and data.get(
                    "learner_username"
                )
                == username
            ):
                allowed = True

            if (
                "clinical_teacher"
                in roles
                and data.get(
                    "teacher_username"
                )
                == username
            ):
                allowed = True

            if (
                "group_leader"
                in roles
                and base.normalize_group(
                    data.get(
                        "group_key"
                    )
                )
                == _user_group(
                    base,
                    user,
                )
            ):
                allowed = True

            if not allowed:
                return jsonify(
                    {
                        "error":
                            "無權查看此指派。"
                    }
                ), 403

            return jsonify(
                wf._assignment_dict(
                    row
                )
            )

        finally:
            conn.close()

    app.view_functions[
        "pgy_assignment_get"
    ] = assignment_get

    # --------------------------------------------------------
    # New PGY assignments default to single signing.
    # --------------------------------------------------------

    def create_assignment():
        try:
            user = _current_user(
                base
            )
        except ApiError as exc:
            return _error(exc)

        if not has_role(
            user,
            "education_admin",
        ):
            return jsonify(
                {
                    "error":
                        "權限不足。"
                }
            ), 403

        data = (
            request.get_json(
                silent=True
            )
            or {}
        )

        learner_username = (
            wf._username(
                data.get(
                    "learnerUsername"
                )
            )
        )

        teacher_username = (
            wf._username(
                data.get(
                    "teacherUsername"
                )
            )
        )

        if (
            not learner_username
            or not teacher_username
        ):
            return jsonify(
                {
                    "error":
                        "學員與臨床教師皆為必填。"
                }
            ), 400

        area = wf._text(
            data.get(
                "area"
            )
            or "pgy",
            20,
        )

        if area != "pgy":
            return jsonify(
                {
                    "error":
                        "PGY 指派只能建立在 PGY 訓練區。"
                }
            ), 400

        try:
            sign_mode = (
                signing.validate_new_sign_mode(
                    data.get(
                        "signMode",
                        "single",
                    )
                )
            )
        except ApiError as exc:
            return _error(exc)

        conn, kind = (
            base._db_conn()
        )

        ph = wf._ph(
            kind
        )

        try:
            learner = (
                wf._lookup_account(
                    conn,
                    kind,
                    learner_username,
                )
            )

            teacher = (
                wf._lookup_account(
                    conn,
                    kind,
                    teacher_username,
                )
            )

            if (
                not learner
                or not bool(
                    learner.get(
                        "active",
                        True,
                    )
                )
                or not _row_has_role(
                    learner,
                    "student",
                )
            ):
                return jsonify(
                    {
                        "error":
                            "指定的學員不存在、已停用或角色不是學員。"
                    }
                ), 400

            if (
                not teacher
                or not bool(
                    teacher.get(
                        "active",
                        True,
                    )
                )
                or not _row_has_role(
                    teacher,
                    "clinical_teacher",
                )
            ):
                return jsonify(
                    {
                        "error":
                            "指定的教師不存在、已停用或未具臨床教師身分。"
                    }
                ), 400

            group = (
                base.normalize_group(
                    data.get(
                        "group"
                    )
                    or learner.get(
                        "preferred_group"
                    )
                )
            )

            course_id = wf._text(
                data.get(
                    "courseId"
                ),
                120,
            )

            course = (
                wf._course_row(
                    conn,
                    kind,
                    course_id,
                )
                if course_id
                else None
            )

            if (
                course_id
                and not course
            ):
                return jsonify(
                    {
                        "error":
                            "找不到指定課程。"
                    }
                ), 400

            if course:
                course_area = (
                    base.normalize_area(
                        course.get(
                            "training_area"
                        )
                    )
                )

                course_group = (
                    base.normalize_group(
                        course.get(
                            "group_key"
                        )
                    )
                )

                if (
                    course_area
                    != "pgy"
                    or course_group
                    != group
                ):
                    return jsonify(
                        {
                            "error":
                                "課程的訓練區或組別與指派不一致。"
                        }
                    ), 400

            if course_id:
                duplicate = (
                    conn.execute(
                        f"""
                        SELECT id
                        FROM pgy_assignments
                        WHERE learner_username={ph}
                          AND course_id={ph}
                          AND status
                              NOT IN (
                                  'finalized',
                                  'cancelled'
                              )
                        LIMIT 1
                        """,
                        (
                            learner_username,
                            course_id,
                        ),
                    ).fetchone()
                )

                if duplicate:
                    return jsonify(
                        {
                            "error":
                                "此學員在同一課程已有進行中的指派。"
                        }
                    ), 409

            import uuid

            assignment_id = (
                uuid.uuid4().hex
            )

            now = wf.utcnow()

            title = wf._text(
                data.get(
                    "title"
                )
                or (
                    course or {}
                ).get(
                    "title"
                )
                or "PGY訓練指派",
                180,
            )

            instructions = (
                wf._text(
                    data.get(
                        "instructions"
                    ),
                    10000,
                )
            )

            due_at = wf._text(
                data.get(
                    "dueAt"
                ),
                80,
            )

            values = (
                assignment_id,
                learner_username,
                teacher_username,
                "pgy",
                group,
                course_id,
                title,
                instructions,
                due_at,
                "assigned",
                "{}",
                "",
                "",
                "{}",
                "{}",
                "{}",
                wf._username(
                    user.get(
                        "username"
                    )
                ),
                now,
                now,
                sign_mode,
                "{}",
                "{}",
            )

            conn.execute(
                f"""
                INSERT INTO
                pgy_assignments
                (
                    id,
                    learner_username,
                    teacher_username,
                    training_area,
                    group_key,
                    course_id,
                    title,
                    instructions,
                    due_at,
                    status,
                    evidence,
                    reflection,
                    student_submitted_at,
                    teacher_signature,
                    group_signature,
                    final_confirmation,
                    created_by,
                    created_at,
                    updated_at,
                    sign_mode,
                    first_signature,
                    second_signature
                )
                VALUES (
                    {','.join([ph] * 22)}
                )
                """,
                values,
            )

            wf._audit(
                conn,
                kind,
                base,
                assignment_id,
                user,
                "create",
                "",
                "assigned",
                {
                    "learnerUsername":
                        learner_username,
                    "teacherUsername":
                        teacher_username,
                    "courseId":
                        course_id,
                    "group":
                        group,
                    "signMode":
                        sign_mode,
                },
            )

            row = wf._get_assignment(
                conn,
                kind,
                assignment_id,
            )

            return jsonify(
                {
                    "ok": True,
                    "assignment":
                        wf._assignment_dict(
                            row
                        ),
                }
            ), 201

        finally:
            conn.close()

    app.view_functions[
        "pgy_assignment_create"
    ] = create_assignment

    # --------------------------------------------------------
    # PATCH signMode while assignment is still assigned.
    # Other legacy editable fields still use original handler.
    # --------------------------------------------------------

    def update_assignment(
        assignment_id,
    ):
        data = (
            request.get_json(
                silent=True
            )
            or {}
        )

        if "signMode" not in data:
            return legacy_update(
                assignment_id
            )

        try:
            user = _current_user(
                base
            )
        except ApiError as exc:
            return _error(exc)

        if not has_role(
            user,
            "education_admin",
        ):
            return jsonify(
                {
                    "error":
                        "權限不足。"
                }
            ), 403

        try:
            sign_mode = (
                signing.validate_new_sign_mode(
                    data.get(
                        "signMode"
                    )
                )
            )
        except ApiError as exc:
            return _error(exc)

        conn, kind = (
            base._db_conn()
        )

        ph = wf._ph(
            kind
        )

        try:
            row = wf._get_assignment(
                conn,
                kind,
                assignment_id,
            )

            if not row:
                return jsonify(
                    {
                        "error":
                            "找不到指派。"
                    }
                ), 404

            raw = dict(row)

            if (
                raw.get("status")
                != "assigned"
            ):
                return jsonify(
                    {
                        "error":
                            "只有尚未送出的指派可以修改簽核模式。"
                    }
                ), 409

            # If other existing fields are supplied, let the
            # retained 6.5 handler update them first.
            legacy_fields = {
                "teacherUsername",
                "title",
                "instructions",
                "dueAt",
            }

            if (
                legacy_fields
                & set(data)
            ):
                result = legacy_update(
                    assignment_id
                )

                response = (
                    result[0]
                    if isinstance(
                        result,
                        tuple,
                    )
                    else result
                )

                status_code = (
                    result[1]
                    if isinstance(
                        result,
                        tuple,
                    )
                    else getattr(
                        response,
                        "status_code",
                        200,
                    )
                )

                if (
                    status_code
                    >= 400
                ):
                    return result

            now = wf.utcnow()

            conn.execute(
                f"""
                UPDATE pgy_assignments
                SET sign_mode={ph},
                    updated_at={ph}
                WHERE id={ph}
                  AND status='assigned'
                """,
                (
                    sign_mode,
                    now,
                    assignment_id,
                ),
            )

            wf._audit(
                conn,
                kind,
                base,
                assignment_id,
                user,
                "admin_edit",
                "assigned",
                "assigned",
                {
                    "signMode":
                        sign_mode
                },
            )

            updated = (
                wf._get_assignment(
                    conn,
                    kind,
                    assignment_id,
                )
            )

            return jsonify(
                {
                    "ok": True,
                    "assignment":
                        wf._assignment_dict(
                            updated
                        ),
                }
            )

        finally:
            conn.close()

    app.view_functions[
        "pgy_assignment_update"
    ] = update_assignment

    # --------------------------------------------------------
    # New sign/countersign behavior; legacy rows delegate.
    # --------------------------------------------------------

    def teacher_sign(
        assignment_id,
    ):
        try:
            mode = _assignment_mode(
                base,
                assignment_id,
            )
        except ApiError as exc:
            return _error(exc)

        if mode == "legacy":
            return legacy_teacher_sign(
                assignment_id
            )

        try:
            assignment = (
                signing.sign_assignment(
                    _current_user(base),
                    assignment_id,
                    request.get_json(
                        silent=True
                    )
                    or {},
                )
            )

            return jsonify(
                {
                    "ok": True,
                    "assignment":
                        assignment,
                }
            )

        except ApiError as exc:
            return _error(exc)

    app.view_functions[
        "pgy_assignment_teacher_sign"
    ] = teacher_sign

    def countersign(
        assignment_id,
    ):
        try:
            mode = _assignment_mode(
                base,
                assignment_id,
            )
        except ApiError as exc:
            return _error(exc)

        if mode == "legacy":
            return legacy_countersign(
                assignment_id
            )

        try:
            assignment = (
                signing.countersign_assignment(
                    _current_user(base),
                    assignment_id,
                    request.get_json(
                        silent=True
                    )
                    or {},
                )
            )

            return jsonify(
                {
                    "ok": True,
                    "assignment":
                        assignment,
                }
            )

        except ApiError as exc:
            return _error(exc)

    app.view_functions[
        "pgy_assignment_countersign"
    ] = countersign

    def reopen(
        assignment_id,
    ):
        try:
            mode = _assignment_mode(
                base,
                assignment_id,
            )
        except ApiError as exc:
            return _error(exc)

        if mode == "legacy":
            return legacy_reopen(
                assignment_id
            )

        try:
            assignment = (
                signing.reopen_assignment(
                    _current_user(base),
                    assignment_id,
                    request.get_json(
                        silent=True
                    )
                    or {},
                )
            )

            return jsonify(
                {
                    "ok": True,
                    "assignment":
                        assignment,
                }
            )

        except ApiError as exc:
            return _error(exc)

    app.view_functions[
        "pgy_assignment_reopen"
    ] = reopen

    app.extensions[
        "teacher_pgy_signing_66_registered"
    ] = True

    return app
