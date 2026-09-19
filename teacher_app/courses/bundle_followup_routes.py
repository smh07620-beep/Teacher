"""Canonical retry-safe Course Wizard follow-up HTTP adapter.

The established upload/link handlers remain the mutation owners. Workflow
lookup, scope validation, request hashes and idempotency persistence live in
``teacher_app.courses.bundle_followup``. Schema registration lives in
``schema_migrations``.
"""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.maintenance.migrations import _course_bundle_followups_73
from teacher_app.common import scope, scope_filter
from teacher_app.common.errors import ApiError
from teacher_app.courses import bundle_followup as followup_service


MIGRATION_ID = followup_service.MIGRATION_ID
MAX_FOLLOWUP_INDEX = followup_service.MAX_FOLLOWUP_INDEX


def _error(exc: ApiError):
    body = {"error": exc.message}
    if exc.code in {
        "BUNDLE_NOT_READY",
        "FOLLOWUP_BUNDLE_MISMATCH",
        "FOLLOWUP_SCOPE_MISMATCH",
        "FOLLOWUP_EXAM_MISMATCH",
        "FOLLOWUP_KEY_REUSED",
        "FOLLOWUP_IN_PROGRESS",
    }:
        body["code"] = exc.code
    if exc.extra.get("loginRequired"):
        body["loginRequired"] = True
    return jsonify(body), exc.status


def _app(owner):
    return getattr(owner, "app", owner)


def _current_user():
    return getattr(g, "teacher_user", None)


def _material_manage_guard(app):
    return scope_filter.scoped_groups(
        app,
        "material.manage",
        scope_filter.request_groups(app),
    )[1]


def register_course_bundle_followup_73(owner):
    app = _app(owner)
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

        group = str(
            request.form.get("group")
            or scope.DEFAULT_GROUP
            or ""
        ).strip()
        denied = _material_manage_guard(app)
        if denied:
            return denied

        try:
            index = followup_service.validate_index(index_raw)
            course_id = str(request.form.get("courseId") or "").strip()
            area = str(
                request.form.get("area")
                or scope.DEFAULT_TRAINING_AREA
                or ""
            ).strip()
            category = str(request.form.get("category") or "").strip()
            username, bundle = followup_service.workflow_context(
                _current_user(),
                workflow_id,
            )
            followup_service.validate_bundle_target(
                bundle,
                course_id=course_id,
                group=group,
                area=area,
                category=category,
            )

            upload = request.files.get("file")
            original_name = str(getattr(upload, "filename", "") or "")
            item_key, request_hash = followup_service.upload_claim(
                workflow_id=workflow_id,
                index=index,
                course_id=course_id,
                category=category,
                group=group,
                area=area,
                title=str(request.form.get("title") or "").strip(),
                material_type=str(request.form.get("materialType") or "auto").strip(),
                original_name=original_name,
                file_size=str(request.form.get("bundleFileSize") or "").strip(),
                last_modified=str(request.form.get("bundleFileLastModified") or "").strip(),
            )
            inserted, claim = followup_service.claim(
                username=username,
                workflow_id=workflow_id,
                item_key=item_key,
                kind_name="upload",
                request_hash=request_hash,
            )
            reused = followup_service.reuse_payload(
                inserted,
                claim,
                request_hash,
            )
        except ApiError as exc:
            return _error(exc)

        if reused is not None:
            payload, status_code = reused
            return jsonify(payload), status_code

        try:
            response = app.make_response(original_upload())
        except Exception:
            followup_service.release(
                username=username,
                workflow_id=workflow_id,
                item_key=item_key,
                request_hash=request_hash,
            )
            raise

        if response.status_code < 200 or response.status_code >= 300:
            followup_service.release(
                username=username,
                workflow_id=workflow_id,
                item_key=item_key,
                request_hash=request_hash,
            )
            return response

        payload = response.get_json(silent=True)
        if not isinstance(payload, dict):
            followup_service.release(
                username=username,
                workflow_id=workflow_id,
                item_key=item_key,
                request_hash=request_hash,
            )
            return response

        payload = dict(payload)
        payload.update({
            "reused": False,
            "bundleWorkflowId": workflow_id,
            "bundleFileIndex": index,
        })
        # If completion persistence fails after queue acceptance, keep the
        # processing claim. This fails closed against a duplicate queue insert.
        followup_service.complete(
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
        workflow_id = (
            str(data.get("bundleWorkflowId") or "").strip()
            if isinstance(data, dict)
            else ""
        )
        link_key = (
            str(data.get("bundleLinkKey") or "").strip()
            if isinstance(data, dict)
            else ""
        )
        if not workflow_id and not link_key:
            return original_link(slide_id)

        group = str(
            (data.get("group") if isinstance(data, dict) else "")
            or scope.DEFAULT_GROUP
            or ""
        ).strip()
        denied = _material_manage_guard(app)
        if denied:
            return denied
        if link_key != str(slide_id):
            return jsonify({"error": "教材關聯識別碼與目標教材不一致。"}), 400

        try:
            course_id = str(data.get("courseId") or "").strip()
            area = str(
                data.get("area")
                or scope.DEFAULT_TRAINING_AREA
                or ""
            ).strip()
            category = str(data.get("category") or "").strip()
            username, bundle = followup_service.workflow_context(
                _current_user(),
                workflow_id,
            )
            followup_service.validate_bundle_target(
                bundle,
                course_id=course_id,
                group=group,
                area=area,
                category=category,
            )
            item_key, request_hash = followup_service.link_claim(
                workflow_id=workflow_id,
                material_id=str(slide_id),
                course_id=course_id,
                category=category,
                group=group,
                area=area,
            )
            inserted, claim = followup_service.claim(
                username=username,
                workflow_id=workflow_id,
                item_key=item_key,
                kind_name="link",
                request_hash=request_hash,
            )
            reused = followup_service.reuse_payload(
                inserted,
                claim,
                request_hash,
            )
        except ApiError as exc:
            return _error(exc)

        if reused is not None:
            payload, status_code = reused
            return jsonify(payload), status_code

        try:
            response = app.make_response(original_link(slide_id))
        except Exception:
            followup_service.release(
                username=username,
                workflow_id=workflow_id,
                item_key=item_key,
                request_hash=request_hash,
            )
            raise

        if response.status_code < 200 or response.status_code >= 300:
            followup_service.release(
                username=username,
                workflow_id=workflow_id,
                item_key=item_key,
                request_hash=request_hash,
            )
            return response

        payload = response.get_json(silent=True)
        if not isinstance(payload, dict):
            followup_service.release(
                username=username,
                workflow_id=workflow_id,
                item_key=item_key,
                request_hash=request_hash,
            )
            return response

        payload = dict(payload)
        payload.update({
            "reused": False,
            "bundleWorkflowId": workflow_id,
            "bundleLinkKey": str(slide_id),
        })
        followup_service.complete(
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
