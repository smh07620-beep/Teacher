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
from teacher_app.worker import repository as worker_repository


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
    original_direct_init = app.view_functions.get("material_upload_init")
    original_direct_complete = app.view_functions.get("material_upload_complete")
    original_direct_abort = app.view_functions.get("material_upload_abort")
    original_direct_resume = app.view_functions.get("material_upload_resume")
    original_worker_retry = app.view_functions.get("material_worker_retry")
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

    def _direct_claim_context(body):
        workflow_id = str(body.get("bundleWorkflowId") or "").strip()
        index_raw = str(body.get("bundleFileIndex") or "").strip()
        if not workflow_id and not index_raw:
            return None

        group = str(body.get("group") or scope.DEFAULT_GROUP or "").strip()
        index = followup_service.validate_index(index_raw)
        course_id = str(body.get("courseId") or "").strip()
        area = str(body.get("area") or scope.DEFAULT_TRAINING_AREA or "").strip()
        category = str(body.get("category") or "").strip()
        username, bundle = followup_service.workflow_context(_current_user(), workflow_id)
        followup_service.validate_bundle_target(
            bundle,
            course_id=course_id,
            group=group,
            area=area,
            category=category,
        )
        item_key, request_hash = followup_service.upload_claim(
            workflow_id=workflow_id,
            index=index,
            course_id=course_id,
            category=category,
            group=group,
            area=area,
            title=str(body.get("title") or "").strip(),
            material_type=str(body.get("materialType") or "auto").strip(),
            original_name=str(body.get("filename") or "").strip(),
            file_size=str(body.get("size") or body.get("bundleFileSize") or "").strip(),
            last_modified=str(body.get("lastModified") or body.get("bundleFileLastModified") or "").strip(),
            fingerprint=str(body.get("fingerprint") or "").strip(),
            fingerprint_strategy=str(body.get("fingerprintStrategy") or "").strip(),
            fingerprint_part_size=str(body.get("fingerprintPartSize") or "").strip(),
        )
        return {
            "username": username,
            "workflowId": workflow_id,
            "fileIndex": index,
            "itemKey": item_key,
            "requestHash": request_hash,
        }

    def _reset_direct_session_claim(session):
        payload = dict((session or {}).get("payload") or {})
        meta = dict(payload.get("bundleFollowupClaim") or {})
        if not meta:
            return
        username = str(meta.get("username") or "").strip()
        workflow_id = str(meta.get("workflowId") or "").strip()
        item_key = str(meta.get("itemKey") or "").strip()
        request_hash = str(meta.get("requestHash") or "").strip()
        if not all((username, workflow_id, item_key, request_hash)):
            return
        followup_service.reset_claim(
            username=username,
            workflow_id=workflow_id,
            item_key=item_key,
            request_hash=request_hash,
        )

    def _already_queued_payload(session, prior):
        job_id = str((session or {}).get("job_id") or prior.get("jobId") or "")
        material_id = str((session or {}).get("material_id") or prior.get("materialId") or "")
        upload_id = str((session or {}).get("id") or prior.get("uploadId") or "")
        job = worker_repository.get_material_job(job_id, include_payload=False) if job_id else None
        return jsonify({
            "error": "此教材已排入背景處理，不需要再次上傳。",
            "alreadyQueued": True,
            "existingJobId": job_id,
            "existingMaterialId": material_id,
            "existingUploadId": upload_id,
            "existingJobStatus": str((job or {}).get("status") or "queued"),
        }), 409

    def retry_safe_direct_init():
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict):
            return original_direct_init()
        workflow_id = str(body.get("bundleWorkflowId") or "").strip()
        index_raw = str(body.get("bundleFileIndex") or "").strip()
        if not workflow_id and not index_raw:
            return original_direct_init()

        denied = _material_manage_guard(app)
        if denied:
            return denied

        try:
            meta = _direct_claim_context(body)
            inserted, claim = followup_service.claim(
                username=meta["username"],
                workflow_id=meta["workflowId"],
                item_key=meta["itemKey"],
                kind_name="direct_upload_init",
                request_hash=meta["requestHash"],
            )
            reused = followup_service.reuse_payload(inserted, claim, meta["requestHash"])
            if reused is not None:
                prior, _stored_status = reused
                upload_id = str(prior.get("uploadId") or "").strip()
                session = worker_repository.get_upload_session(upload_id) if upload_id else None
                job_id = str((session or {}).get("job_id") or prior.get("jobId") or "").strip()
                existing_job = (
                    worker_repository.get_material_job(job_id, include_payload=False)
                    if job_id else None
                )
                status = str((session or {}).get("status") or "")
                if status == "completed" or existing_job:
                    return _already_queued_payload(session, prior)
                if status == "uploading":
                    upload_mode = str(
                        ((session or {}).get("payload") or {}).get("uploadMode")
                        or ("multipart" if (session or {}).get("r2_upload_id") else "single")
                    )
                    if upload_mode == "multipart" and original_direct_resume is not None:
                        response = app.make_response(original_direct_resume(upload_id))
                        resume_payload = response.get_json(silent=True)
                        if 200 <= response.status_code < 300 and isinstance(resume_payload, dict):
                            resume_payload = dict(resume_payload)
                            resume_payload["reused"] = True
                            return jsonify(resume_payload), response.status_code
                    return jsonify({
                        "error": "同一教材已有上傳工作進行中，請稍候目前工作完成。",
                        "uploadInProgress": True,
                        "existingUploadId": upload_id,
                        "existingJobId": job_id,
                    }), 409
                # A terminal upload session that never became a queue job may
                # be safely retired so the same bytes can be sent again.
                followup_service.reset_claim(
                    username=meta["username"],
                    workflow_id=meta["workflowId"],
                    item_key=meta["itemKey"],
                    request_hash=meta["requestHash"],
                )
                inserted, claim = followup_service.claim(
                    username=meta["username"],
                    workflow_id=meta["workflowId"],
                    item_key=meta["itemKey"],
                    kind_name="direct_upload_init",
                    request_hash=meta["requestHash"],
                )
                followup_service.reuse_payload(inserted, claim, meta["requestHash"])
        except ApiError as exc:
            return _error(exc)

        try:
            response = app.make_response(original_direct_init())
        except Exception:
            followup_service.release(
                username=meta["username"],
                workflow_id=meta["workflowId"],
                item_key=meta["itemKey"],
                request_hash=meta["requestHash"],
            )
            raise

        if response.status_code < 200 or response.status_code >= 300:
            followup_service.release(
                username=meta["username"],
                workflow_id=meta["workflowId"],
                item_key=meta["itemKey"],
                request_hash=meta["requestHash"],
            )
            return response

        payload = response.get_json(silent=True)
        if not isinstance(payload, dict):
            followup_service.release(
                username=meta["username"],
                workflow_id=meta["workflowId"],
                item_key=meta["itemKey"],
                request_hash=meta["requestHash"],
            )
            return response

        payload = dict(payload)
        upload_id = str(payload.get("uploadId") or "").strip()
        session = worker_repository.get_upload_session(upload_id) if upload_id else None
        if session:
            session_payload = dict(session.get("payload") or {})
            session_payload["bundleFollowupClaim"] = {
                "username": meta["username"],
                "workflowId": meta["workflowId"],
                "fileIndex": meta["fileIndex"],
                "itemKey": meta["itemKey"],
                "requestHash": meta["requestHash"],
            }
            worker_repository.update_upload_session(
                upload_id,
                fields={"payload": session_payload},
            )
        payload.update({
            "reused": False,
            "bundleWorkflowId": meta["workflowId"],
            "bundleFileIndex": meta["fileIndex"],
        })
        # Keep the claim after init succeeds. It is the cross-request mutex
        # that prevents one Course Wizard file from creating a second R2/job
        # identity while the first upload or Worker job is still alive.
        followup_service.complete(
            username=meta["username"],
            workflow_id=meta["workflowId"],
            item_key=meta["itemKey"],
            request_hash=meta["requestHash"],
            status_code=response.status_code,
            payload=payload,
        )
        return jsonify(payload), response.status_code

    def retry_safe_direct_complete(upload_id):
        session = worker_repository.get_upload_session(upload_id)
        response = app.make_response(original_direct_complete(upload_id))
        if response.status_code >= 400:
            current = worker_repository.get_upload_session(upload_id) or session
            if str((current or {}).get("status") or "") in {"failed", "aborted"}:
                _reset_direct_session_claim(current)
        return response

    def retry_safe_direct_abort(upload_id):
        session = worker_repository.get_upload_session(upload_id)
        response = app.make_response(original_direct_abort(upload_id))
        if 200 <= response.status_code < 300 and str((session or {}).get("status") or "") != "completed":
            _reset_direct_session_claim(session)
        return response

    def observable_worker_retry(job_id):
        body = request.get_json(silent=True) or {}
        response = app.make_response(original_worker_retry(job_id))
        payload = response.get_json(silent=True)
        if 200 <= response.status_code < 300 and isinstance(payload, dict) and payload.get("status") == "retry_wait":
            reason = str((body or {}).get("error") or "").strip()[:1200]
            if reason:
                delay = int(payload.get("retryAfterSeconds") or 0)
                suffix = f"；{delay} 秒後重試。" if delay else "。"
                worker_repository.update_material_job(
                    job_id,
                    fields={
                        "detail": f"本機 Worker 回報暫時失敗：{reason}{suffix}",
                        "error": reason,
                    },
                )
        return response

    app.view_functions["api_enqueue_material_job"] = retry_safe_upload
    app.view_functions["api_update_slide"] = retry_safe_link
    if original_direct_init is not None:
        app.view_functions["material_upload_init"] = retry_safe_direct_init
    if original_direct_complete is not None:
        app.view_functions["material_upload_complete"] = retry_safe_direct_complete
    if original_direct_abort is not None:
        app.view_functions["material_upload_abort"] = retry_safe_direct_abort
    if original_worker_retry is not None:
        app.view_functions["material_worker_retry"] = observable_worker_retry
    app.extensions["teacher_course_bundle_followup_73_registered"] = True
    return app
