"""Canonical HTTP compatibility routes for runtime quiz and AI question APIs."""
from __future__ import annotations

import csv
import io
import ipaddress
import json
from pathlib import Path
import random
import re
import socket
import urllib.parse
import urllib.request
import uuid

from flask import g, jsonify, request

from teacher_app.assessments import ai_job_repository, ai_jobs
from teacher_app.assessments import repository
from teacher_app.assessments.question_runtime import (
    QuestionImageMegaUploadError,
    QuestionRuntime,
    runtime_from_owner,
)
from teacher_app.assessments import runtime_questions
from teacher_app.common import audit, scope_filter
from teacher_app.common.auth import has_permission
from teacher_app.materials import repository as material_repository


def _app(owner):
    return getattr(owner, "app", owner)


def _current_user(owner=None):
    if hasattr(g, "teacher_user"):
        return g.teacher_user
    resolver = getattr(owner, "_current_user", None)
    return resolver() if callable(resolver) else None


def _login_required(owner):
    if _current_user(owner):
        return None
    return jsonify({"error": "請先登入後再使用教材。", "loginRequired": True}), 401


def _strict_admin(owner):
    user = _current_user(owner)
    if not user:
        return jsonify({
            "error": "請先以管理者帳號登入。",
            "loginRequired": True,
        }), 401
    if not has_permission(user, "system.manage"):
        return jsonify({"error": "權限不足：此功能限教學管理者使用。"}), 403
    return None


def _question_guard(owner, *, scoped: bool):
    if scoped:
        return scope_filter.scoped_groups(
            owner,
            "question.manage",
            scope_filter.request_groups(owner),
        )[1]
    return scope_filter.denied(owner, "question.manage")[1]


def _bind_or_add(app, rule: str, endpoint: str, view, methods: list[str]) -> None:
    """Replace a copied legacy endpoint, or add the canonical rule standalone."""
    if endpoint in app.view_functions:
        app.view_functions[endpoint] = view
        return
    app.add_url_rule(rule, endpoint=endpoint, view_func=view, methods=methods)


def _parse_import_correct(raw_value, *, qtype: str, option_count: int) -> int:
    """Parse a URL-import answer without silently changing malformed values."""
    if qtype in {"essay", "fill", "multi"}:
        return 0
    if raw_value in (None, ""):
        return 0
    if qtype == "true_false":
        text = str(raw_value).strip()
        if text in {"是", "對", "true", "True", "TRUE"}:
            return 0
        if text in {"否", "錯", "false", "False", "FALSE"}:
            return 1
    if isinstance(raw_value, str) and raw_value.strip().upper() in "ABCDEF":
        correct = "ABCDEF".index(raw_value.strip().upper())
    else:
        try:
            correct = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("正確答案格式錯誤") from exc
    if correct < 0 or correct >= option_count:
        raise ValueError("正確答案超出選項範圍")
    return correct


def register_runtime_question_routes(owner, *, runtime: QuestionRuntime | None = None):
    app = _app(owner)
    if app.extensions.get("teacher_runtime_question_routes_registered"):
        return app
    runtime = runtime or runtime_from_owner(owner)

    def audit_actor():
        return _current_user(owner) or {}

    def category_for_question(question):
        category_id = str((question or {}).get("quizCategoryId") or "")
        return repository.get_category_full(category_id) if category_id else None

    def question_snapshot(question):
        question = question or {}
        return {
            "id": str(question.get("id") or ""),
            "quizCategoryId": str(question.get("quizCategoryId") or ""),
            "questionType": str(question.get("questionType") or ""),
            "difficulty": str(question.get("difficulty") or ""),
            "tag": str(question.get("tag") or ""),
            "active": bool(question.get("active", True)),
            "status": str(question.get("status") or ""),
            "origin": str(question.get("origin") or ""),
        }

    def api_upload_question_image():
        denied = _question_guard(owner, scoped=False)
        if denied:
            return denied
        if "file" not in request.files:
            return jsonify({"error": "缺少圖片檔案"}), 400
        upload = request.files["file"]
        ext = Path(upload.filename or "").suffix.lower()
        if ext not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
            return jsonify({"error": "僅接受 PNG/JPG/GIF/WEBP"}), 400
        name = f"{uuid.uuid4().hex}{ext}"
        try:
            url = runtime.save_question_image(upload, name)
        except QuestionImageMegaUploadError as exc:
            return jsonify({"error": f"題目影像上傳 MEGA 失敗：{exc.cause}"}), 502
        return jsonify({"url": url})

    def api_random_quiz_questions():
        denied = _login_required(owner)
        if denied:
            return denied
        category_id = request.args.get("category", "")
        if not category_id:
            return jsonify([])
        category = repository.get_category_full(category_id)
        if not category or not category.get("active", True):
            return jsonify([])
        questions = repository.list_questions(category_id, include_inactive=False)
        count = int(category.get("drawCount", 0) or 0)
        raw_override = request.args.get("count")
        if raw_override not in (None, ""):
            try:
                override = int(raw_override)
                if override > 0:
                    count = override
            except (TypeError, ValueError):
                pass
        draw_rules = category.get("drawRules", {}) if isinstance(category.get("drawRules", {}), dict) else {}
        if draw_rules.get("mode") == "type_quota":
            quotas = draw_rules.get("quotas", {}) if isinstance(draw_rules.get("quotas", {}), dict) else {}
            types = ("choice", "multi", "true_false", "fill", "essay", "image", "video")
            target_total = sum(max(0, int(quotas.get(qtype, 0) or 0)) for qtype in types)
            selected = []
            selected_ids = set()
            for qtype in types:
                pool = [q for q in questions if q.get("questionType", "choice") == qtype]
                random.shuffle(pool)
                want = max(0, int(quotas.get(qtype, 0) or 0))
                for question in pool[: min(want, len(pool))]:
                    selected.append(question)
                    selected_ids.add(question.get("id"))
            if len(selected) < target_total:
                remaining = [question for question in questions if question.get("id") not in selected_ids]
                random.shuffle(remaining)
                selected.extend(remaining[: max(0, target_total - len(selected))])
            random.shuffle(selected)
            return jsonify(selected)
        random.shuffle(questions)
        return jsonify(questions if count <= 0 else questions[: min(count, len(questions))])

    def api_list_quiz_questions():
        denied = _login_required(owner)
        if denied:
            return denied
        category_id = request.args.get("category", "")
        if not category_id:
            return jsonify({"error": "缺少 category 參數"}), 400
        return jsonify(repository.list_questions(category_id, include_inactive=False))

    def api_admin_list_quiz_questions():
        denied = _question_guard(owner, scoped=True)
        if denied:
            return denied
        category_id = request.args.get("category", "")
        if not category_id:
            return jsonify({"error": "缺少 category 參數"}), 400
        return jsonify(repository.list_questions(category_id, include_inactive=True))

    def api_create_quiz_question():
        denied = _question_guard(owner, scoped=True)
        if denied:
            return denied
        try:
            return jsonify(runtime_questions.create_question(
                request.get_json(silent=True) or {},
                allow_hosts=app.config.get("DIRECT_MEDIA_ALLOWLIST", []),
            ))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    def api_update_quiz_question(question_id):
        denied = _question_guard(owner, scoped=True)
        if denied:
            return denied
        try:
            return jsonify(runtime_questions.update_question(
                question_id,
                request.get_json(silent=True) or {},
                allow_hosts=app.config.get("DIRECT_MEDIA_ALLOWLIST", []),
            ))
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    def api_batch_update_quiz_questions():
        denied = _question_guard(owner, scoped=True)
        if denied:
            return denied
        try:
            payload = runtime_questions.batch_update(
                (request.get_json(silent=True) or {}).get("items") or [],
                allow_hosts=app.config.get("DIRECT_MEDIA_ALLOWLIST", []),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        missing = payload.get("missing") if isinstance(payload, dict) else None
        if missing:
            return jsonify({"error": f"找不到 {len(missing)} 題", "missing": missing}), 404
        return jsonify(payload)

    def api_batch_delete_quiz_questions():
        # This endpoint was never in the legacy endpoint-policy map, so retain
        # its historical teaching-admin boundary instead of widening it to all
        # question managers during the base-free cutover.
        denied = _strict_admin(owner)
        if denied:
            return denied
        denied = scope_filter.scoped_groups(
            owner,
            "question.manage",
            scope_filter.request_groups(owner),
        )[1]
        if denied:
            return denied
        body = request.get_json(silent=True) or {}
        requested_ids = body.get("ids") or []
        touched_groups = sorted(scope_filter.request_groups(owner))
        try:
            payload = runtime_questions.batch_delete(requested_ids)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        missing = payload.get("missing") if isinstance(payload, dict) else None
        if missing:
            return jsonify({"error": f"找不到 {len(missing)} 題", "missing": missing}), 404
        audit.record_event(
            actor=audit_actor(),
            action="question.batch_delete",
            target_type="question_batch",
            target_id=str((payload.get("deleted") or [""])[0]),
            group=touched_groups[0] if len(touched_groups) == 1 else "",
            scope={"groups": touched_groups},
            detail={
                "questionIds": payload.get("deleted") or [],
                "count": payload.get("count", 0),
            },
        )
        return jsonify(payload)

    def api_import_quiz_questions_url():
        denied = _question_guard(owner, scoped=True)
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        category_id = str(data.get("quizCategoryId", "")).strip()
        url = str(data.get("url", "")).strip()
        if not repository.get_category_full(category_id):
            return jsonify({"error": "找不到考題頁籤"}), 400
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return jsonify({"error": "僅接受公開 HTTP/HTTPS 連結"}), 400
        try:
            for info in socket.getaddrinfo(
                parsed.hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            ):
                ip = ipaddress.ip_address(info[4][0])
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                    return jsonify({"error": "基於安全性，不允許讀取內網或本機網址"}), 400
        except Exception:
            return jsonify({"error": "無法解析該網址"}), 400
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "HospitalTrainingImporter/1.0"})
            with urllib.request.urlopen(req, timeout=12) as response:
                raw = response.read(5 * 1024 * 1024 + 1)
                content_type = (response.headers.get("Content-Type") or "").lower()
            if len(raw) > 5 * 1024 * 1024:
                return jsonify({"error": "題庫檔案超過 5MB"}), 400
            text = raw.decode("utf-8-sig")
            if "json" in content_type or url.lower().split("?")[0].endswith(".json"):
                items = json.loads(text)
                items = items.get("questions", []) if isinstance(items, dict) else items
            else:
                items = list(csv.DictReader(io.StringIO(text)))
        except Exception as exc:
            return jsonify({"error": f"讀取或解析連結失敗：{exc}"}), 400
        if not isinstance(items, list):
            return jsonify({"error": "JSON 格式需為題目陣列，或使用 questions 陣列"}), 400

        imported = 0
        errors = []
        aliases = {
            "問答題": "essay", "申論題": "essay", "text": "essay", "essay": "essay",
            "多選題": "multi", "複選題": "multi", "multi": "multi", "multiple": "multi",
            "填空題": "fill", "fill": "fill", "blank": "fill",
            "是非題": "true_false", "判斷題": "true_false", "true_false": "true_false", "truefalse": "true_false",
            "圖片題": "image", "圖片判讀題": "image", "image": "image",
            "影片題": "video", "video": "video",
            "選擇題": "choice", "單選題": "choice", "choice": "choice", "single": "choice",
        }
        for index, item in enumerate(items[:500], 1):
            if not isinstance(item, dict):
                continue
            question = str(item.get("question") or item.get("題目") or "").strip()
            qtype = str(item.get("questionType") or item.get("type") or item.get("題型") or "choice").strip().lower()
            qtype = aliases.get(qtype, "choice")
            options = item.get("options")
            if isinstance(options, str):
                try:
                    options = json.loads(options)
                except Exception:
                    options = [value.strip() for value in options.split("|") if value.strip()]
            if not isinstance(options, list):
                options = [
                    str(item.get(key, "")).strip()
                    for key in ("optionA", "optionB", "optionC", "optionD", "optionE", "optionF")
                    if str(item.get(key, "")).strip()
                ]
            raw_correct = item.get("correct", item.get("answer", 0))
            answer_config = item.get("answerConfig", {})
            if isinstance(answer_config, str):
                try:
                    answer_config = json.loads(answer_config)
                except Exception:
                    answer_config = {}
            if not isinstance(answer_config, dict):
                answer_config = {}
            if qtype == "multi" and not answer_config.get("correctIndices"):
                raw_multi = item.get("correctIndices", item.get("正確選項", ""))
                if isinstance(raw_multi, str):
                    answer_config["correctIndices"] = [
                        "ABCDEF".index(value) for value in re.findall(r"[A-F]", raw_multi.upper())
                    ]
                elif isinstance(raw_multi, list):
                    answer_config["correctIndices"] = raw_multi
            if qtype == "fill" and not answer_config.get("acceptedAnswers"):
                raw_fill = item.get("acceptedAnswers", item.get("可接受答案", item.get("標準答案", "")))
                if isinstance(raw_fill, str):
                    answer_config["acceptedAnswers"] = [value.strip() for value in raw_fill.split("|") if value.strip()]
                elif isinstance(raw_fill, list):
                    answer_config["acceptedAnswers"] = raw_fill
            if qtype == "true_false":
                options = ["是", "否"]
            if qtype == "video":
                answer_config.setdefault("mediaUrl", str(item.get("mediaUrl", item.get("影片網址", ""))).strip())
                try:
                    answer_config.setdefault("pauseAt", float(item.get("pauseAt", item.get("時間點", 0)) or 0))
                except Exception:
                    answer_config.setdefault("pauseAt", 0)
            needs_options = qtype in {"choice", "multi", "image", "video", "true_false"}
            if not question or (needs_options and len(options) < 2):
                errors.append(f"第{index}題格式不足")
                continue
            if qtype == "multi" and not answer_config.get("correctIndices"):
                errors.append(f"第{index}題缺少多選正確答案")
                continue
            if qtype == "fill" and not answer_config.get("acceptedAnswers"):
                errors.append(f"第{index}題缺少填空可接受答案")
                continue
            try:
                correct = _parse_import_correct(
                    raw_correct,
                    qtype=qtype,
                    option_count=len(options),
                )
            except ValueError as exc:
                errors.append(f"第{index}題：{exc}")
                continue
            payload = {
                "quizCategoryId": category_id,
                "question": question,
                "questionType": qtype,
                "difficulty": item.get("difficulty", item.get("難度", "standard")),
                "options": options,
                "correct": correct,
                "answerConfig": answer_config,
                "tag": item.get("tag", item.get("分類", "一般")),
                "explanation": item.get("explanation", item.get("詳解", "")),
                "imageUrl": item.get("imageUrl", ""),
            }
            try:
                runtime_questions.insert_payload(
                    category_id,
                    payload,
                    allow_hosts=app.config.get("DIRECT_MEDIA_ALLOWLIST", []),
                )
                imported += 1
            except ValueError as exc:
                errors.append(f"第{index}題：{exc}")
        if imported:
            runtime_questions.mark_category_draft(category_id)
        return jsonify({"ok": True, "imported": imported, "errors": errors[:20], "reviewInvalidated": bool(imported)})

    def api_delete_quiz_question(question_id):
        denied = _question_guard(owner, scoped=True)
        if denied:
            return denied
        before = repository.get_question(question_id)
        category = category_for_question(before)
        try:
            payload = runtime_questions.delete_question(question_id)
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404
        audit.record_event(
            actor=audit_actor(),
            action="question.delete",
            target_type="question",
            target_id=question_id,
            group=str((category or {}).get("group") or ""),
            before=question_snapshot(before),
            detail={"source": "runtime_question"},
        )
        return jsonify(payload)

    def api_ai_question_status():
        denied = _question_guard(owner, scoped=False)
        if denied:
            return denied
        provider = runtime.active_ai_provider()
        return jsonify({
            "configured": runtime.ai_question_is_configured(),
            "provider": provider,
            "model": runtime.ai_model_name(),
            "maxQuestions": runtime.max_questions,
            "sourceMaxChars": runtime.source_max_chars,
            "mediaSupported": provider in {"gemini", "groq"},
            "maxMaterials": runtime.max_materials,
            "multisourceSupported": provider in {"gemini", "groq"},
            "freeOnlyMode": runtime.free_only_mode,
        })

    def api_ai_generate_questions():
        denied = _question_guard(owner, scoped=True)
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        try:
            job = ai_jobs.enqueue(data, runtime, _current_user(owner))
        except ai_jobs.AiJobLimitError as exc:
            return jsonify({"error": str(exc)}), 429
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        audit.record_event(
            actor=audit_actor(),
            action="ai.generation.submit",
            target_type="ai_question_job",
            target_id=str(job.get("id") or ""),
            group=str(job.get("group") or job.get("group_key") or ""),
            scope={
                "area": str(job.get("area") or job.get("training_area") or ""),
                "quizCategoryId": str(job.get("quizCategoryId") or job.get("quiz_category_id") or data.get("quizCategoryId") or ""),
            },
            detail={
                "materialIds": list((job.get("request") or {}).get("materialIds") or data.get("materialIds") or []),
                "count": (job.get("request") or {}).get("count", data.get("count", 5)),
                "questionType": (job.get("request") or {}).get("questionType", data.get("questionType", "mixed")),
                "difficulty": (job.get("request") or {}).get("difficulty", data.get("difficulty", "standard")),
                "strategy": (job.get("request") or {}).get("strategy", data.get("strategy", "auto")),
            },
        )
        return jsonify({"ok": True, "jobId": job.get("id"), "status": "queued"}), 202

    def api_ai_question_job(job_id):
        job = ai_job_repository.get_job(str(job_id or ""))
        if not job:
            return jsonify({"error": "找不到 AI 出題工作"}), 404
        denied = scope_filter.scoped_groups(
            owner,
            "question.manage",
            {str(job.get("group") or "")},
        )[1]
        if denied:
            return denied
        return jsonify(ai_jobs.public_job(job))

    def api_ai_import_questions():
        denied = _question_guard(owner, scoped=True)
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        category_id = str(data.get("quizCategoryId", "")).strip()
        if not repository.get_category_full(category_id):
            return jsonify({"error": "找不到考題頁籤"}), 404
        items = data.get("questions") or []
        if not isinstance(items, list) or not items:
            return jsonify({"error": "請至少勾選一題"}), 400
        valid = []
        errors = []
        for index, question in enumerate(items[:50], 1):
            if isinstance(question, dict):
                valid.append(question)
            else:
                errors.append(f"第{index}題：題目格式錯誤")
        try:
            inserted = runtime_questions.insert_payloads_bulk(
                category_id,
                valid,
                allow_hosts=app.config.get("DIRECT_MEDIA_ALLOWLIST", []),
            )
        except Exception as exc:
            return jsonify({"error": f"批次匯入失敗：{exc}"}), 400
        category = repository.get_category_full(category_id)
        audit.record_event(
            actor=audit_actor(),
            action="ai.candidates.import",
            target_type="assessment",
            target_id=category_id,
            group=str((category or {}).get("group") or ""),
            scope={"area": str((category or {}).get("area") or "")},
            detail={
                "imported": len(inserted),
                "questionIds": [str(item.get("id") or "") for item in inserted if isinstance(item, dict)],
                "rejected": len(errors),
            },
        )
        return jsonify({"ok": True, "imported": len(inserted), "errors": errors[:20], "questions": inserted})

    rules = (
        ("/api/quiz-question-images", "api_upload_question_image", api_upload_question_image, ["POST"]),
        ("/api/quiz-questions/random", "api_random_quiz_questions", api_random_quiz_questions, ["GET"]),
        ("/api/quiz-questions", "api_list_quiz_questions", api_list_quiz_questions, ["GET"]),
        ("/api/quiz-questions/admin", "api_admin_list_quiz_questions", api_admin_list_quiz_questions, ["GET"]),
        ("/api/quiz-questions", "api_create_quiz_question", api_create_quiz_question, ["POST"]),
        ("/api/quiz-questions/<question_id>", "api_update_quiz_question", api_update_quiz_question, ["PATCH"]),
        ("/api/quiz-questions/batch", "api_batch_update_quiz_questions", api_batch_update_quiz_questions, ["PATCH"]),
        ("/api/quiz-questions/batch-delete", "api_batch_delete_quiz_questions", api_batch_delete_quiz_questions, ["POST"]),
        ("/api/quiz-questions/import-url", "api_import_quiz_questions_url", api_import_quiz_questions_url, ["POST"]),
        ("/api/quiz-questions/<question_id>", "api_delete_quiz_question", api_delete_quiz_question, ["DELETE"]),
        ("/api/ai-questions/status", "api_ai_question_status", api_ai_question_status, ["GET"]),
        ("/api/ai-questions/generate", "api_ai_generate_questions", api_ai_generate_questions, ["POST"]),
        ("/api/ai-questions/jobs/<job_id>", "api_ai_question_job", api_ai_question_job, ["GET"]),
        ("/api/ai-questions/import", "api_ai_import_questions", api_ai_import_questions, ["POST"]),
    )
    for rule, endpoint, view, methods in rules:
        _bind_or_add(app, rule, endpoint, view, methods)

    app.extensions["teacher_runtime_question_routes_registered"] = True
    return app


__all__ = ["register_runtime_question_routes"]
