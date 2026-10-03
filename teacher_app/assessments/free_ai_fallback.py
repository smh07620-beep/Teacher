"""Free-first AI fallback used only by the trusted Teacher AI Worker.

Fallback is deliberately narrow: only quota/rate-limit or transient provider
availability failures may switch provider. Validation, unsupported content and
malformed model output remain visible and never trigger provider hopping.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping

import requests

from teacher_app.assessments import ai_runtime
from teacher_app.assessments import repository as assessment_repository
from teacher_app.common import privacy as ai_privacy
from teacher_app.config import storage_paths


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class LocalFallbackSettings:
    enabled: bool
    ollama_enabled: bool
    ollama_base_url: str
    ollama_model: str
    ollama_timeout_seconds: int
    whisper_enabled: bool
    whisper_model: str
    whisper_device: str
    whisper_compute_type: str

    @classmethod
    def from_env(cls) -> "LocalFallbackSettings":
        return cls(
            enabled=_env_true("AI_FREE_FALLBACK_ENABLED", True),
            ollama_enabled=_env_true("OLLAMA_ENABLED", False),
            ollama_base_url=(os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/") or "http://127.0.0.1:11434"),
            ollama_model=(os.environ.get("OLLAMA_MODEL", "qwen3:4b").strip() or "qwen3:4b"),
            ollama_timeout_seconds=_int_env("OLLAMA_TIMEOUT_SECONDS", 240, 30, 900),
            whisper_enabled=_env_true("LOCAL_WHISPER_ENABLED", True),
            whisper_model=(os.environ.get("LOCAL_WHISPER_MODEL", "small").strip() or "small"),
            whisper_device=(os.environ.get("LOCAL_WHISPER_DEVICE", "cpu").strip() or "cpu"),
            whisper_compute_type=(os.environ.get("LOCAL_WHISPER_COMPUTE_TYPE", "int8").strip() or "int8"),
        )


def _env_true(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def local_ai_is_configured(local: LocalFallbackSettings | None = None) -> bool:
    local = local or LocalFallbackSettings.from_env()
    return bool(local.enabled and local.ollama_enabled and local.ollama_model)


def _cloud_provider_ready(provider: str, settings) -> bool:
    if not ai_privacy.external_enabled():
        return False
    if provider == "groq":
        return bool(getattr(settings, "groq_api_key", ""))
    if provider == "gemini":
        return bool(
            getattr(settings, "gemini_api_key", "")
            and ai_runtime.google_genai is not None
            and ai_runtime.google_genai_types is not None
        )
    if provider == "openai":
        return bool(getattr(settings, "openai_api_key", ""))
    return False


def provider_chain(primary: str, *, settings=None, local: LocalFallbackSettings | None = None) -> list[str]:
    settings = settings or ai_runtime.ai_settings()
    local = local or LocalFallbackSettings.from_env()
    primary = str(primary or "groq").strip().lower()
    if primary == "auto":
        primary = "groq"
    preferred = {
        "groq": ["groq", "gemini", "ollama"],
        "gemini": ["gemini", "groq", "ollama"],
        "ollama": ["ollama"],
        "openai": ["openai", "ollama"],
    }.get(primary, ["groq", "gemini", "ollama"])
    if not local.enabled:
        preferred = [primary]
    result: list[str] = []
    for provider in preferred:
        ready = local_ai_is_configured(local) if provider == "ollama" else _cloud_provider_ready(provider, settings)
        if ready and provider not in result:
            result.append(provider)
    return result


_RETRYABLE_MARKERS = (
    "429", "too many requests", "rate limit", "rate_limit", "resource_exhausted", "quota",
    "額度/速率已達上限", "額度已達上限", "速率已達上限",
    "temporarily unavailable", "service unavailable", "provider unavailable", "upstream unavailable",
    "服務暫時不可用", "服務暫時無法使用",
    "deadline exceeded", "timed out", "timeout", "connection reset", "connection aborted",
    "connection refused", "connection error", "502", "503", "504",
)


def is_retryable_provider_error(exc: BaseException) -> bool:
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    text = str(exc or "").strip().lower()
    return bool(text and any(marker in text for marker in _RETRYABLE_MARKERS))


def provider_model(provider: str, *, settings=None, local: LocalFallbackSettings | None = None) -> str:
    settings = settings or ai_runtime.ai_settings()
    local = local or LocalFallbackSettings.from_env()
    return {
        "groq": str(getattr(settings, "groq_model", "") or ""),
        "gemini": str(getattr(settings, "gemini_model", "") or ""),
        "openai": str(getattr(settings, "openai_model", "") or ""),
        "ollama": local.ollama_model,
    }.get(provider, "")


def _provider_label(provider: str) -> str:
    return {"groq": "Groq", "gemini": "Gemini", "ollama": "本機 AI", "openai": "OpenAI"}.get(provider, "AI")


def run_with_fallback(
    primary: str,
    *,
    cloud_callers: Mapping[str, Callable[[], Any]],
    local_caller: Callable[[], Any] | None = None,
    settings=None,
    local: LocalFallbackSettings | None = None,
    notify: Callable[[str, str], Any] | None = None,
) -> tuple[Any, dict[str, Any]]:
    settings = settings or ai_runtime.ai_settings()
    local = local or LocalFallbackSettings.from_env()
    chain = provider_chain(primary, settings=settings, local=local)
    if not chain:
        raise RuntimeError("免費 AI 尚未完成設定；請設定 Groq、Gemini 或本機 Ollama。")
    last_error: BaseException | None = None
    attempts: list[str] = []
    for index, provider in enumerate(chain):
        attempts.append(provider)
        caller = local_caller if provider == "ollama" else cloud_callers.get(provider)
        if caller is None:
            continue
        try:
            value = caller()
            return value, {
                "provider": provider,
                "model": provider_model(provider, settings=settings, local=local),
                "fallbackUsed": index > 0,
                "attemptedProviders": attempts[:],
            }
        except Exception as exc:
            last_error = exc
            retryable = is_retryable_provider_error(exc)
            next_provider = chain[index + 1] if retryable and index + 1 < len(chain) else ""
            LOGGER.warning(
                "AI provider attempt failed provider=%s next_provider=%s retryable=%s error_type=%s",
                provider,
                next_provider,
                str(bool(retryable)).lower(),
                type(exc).__name__,
            )
            if not retryable:
                raise
            if next_provider and notify is not None:
                notify(provider, next_provider)
    raise RuntimeError(
        "免費 AI 目前暫時無法使用：雲端額度/速率或服務可用性已達限制，"
        "且已設定的本機備援未能完成工作。請稍後再試。"
    ) from last_error


def ollama_chat(prompt: str, *, json_mode: bool, local: LocalFallbackSettings | None = None) -> str:
    local = local or LocalFallbackSettings.from_env()
    if not local_ai_is_configured(local):
        raise RuntimeError("本機 Ollama 尚未啟用。")
    payload: dict[str, Any] = {
        "model": local.ollama_model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.15},
    }
    if json_mode:
        payload["format"] = "json"
    try:
        response = requests.post(
            f"{local.ollama_base_url}/api/chat",
            json=payload,
            timeout=local.ollama_timeout_seconds,
        )
    except requests.RequestException as exc:
        raise RuntimeError("本機 Ollama connection unavailable。") from exc
    if response.status_code >= 500:
        raise RuntimeError(f"本機 Ollama provider unavailable HTTP {response.status_code}。")
    if response.status_code >= 400:
        raise RuntimeError(f"本機 Ollama 請求失敗 HTTP {response.status_code}。")
    text = str(((response.json().get("message") or {}).get("content") or "")).strip()
    if not text:
        raise RuntimeError("本機 AI 沒有回傳內容。")
    return text


_WHISPER_CACHE: dict[tuple[str, str, str], Any] = {}


def local_transcribe(path: Path, *, local: LocalFallbackSettings | None = None) -> str:
    local = local or LocalFallbackSettings.from_env()
    if not local.whisper_enabled:
        raise RuntimeError("本機 Whisper 備援尚未啟用。")
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("本機 faster-whisper 尚未安裝。") from exc
    key = (local.whisper_model, local.whisper_device, local.whisper_compute_type)
    model = _WHISPER_CACHE.get(key)
    if model is None:
        model = WhisperModel(local.whisper_model, device=local.whisper_device, compute_type=local.whisper_compute_type)
        _WHISPER_CACHE[key] = model
    segments, _info = model.transcribe(str(path), vad_filter=True)
    lines: list[str] = []
    for segment in segments:
        text = str(getattr(segment, "text", "") or "").strip()
        if text:
            start = float(getattr(segment, "start", 0.0) or 0.0)
            lines.append(f"[{int(start // 60):02d}:{int(start % 60):02d}] {text}")
    result = "\n".join(lines).strip()
    if not result:
        raise RuntimeError("本機 Whisper 沒有辨識到可用語音內容。")
    return result


def _local_context(entries, *, source_title: str, focus: str, strategy: str, settings, paths_provider, local):
    chunks: list[dict] = []
    temp_roots: list[Path] = []
    kinds = [ai_runtime.material_kind(entry) for entry in entries]
    try:
        for entry, kind in zip(entries, kinds):
            if kind in {"text", "subtitle"}:
                text, _total = ai_runtime.extract_material_text_for_ai(
                    entry,
                    settings=settings,
                    paths_provider=paths_provider,
                    retrieval_max_chars=_int_env("AI_RAG_SOURCE_MAX_CHARS", 250000, 5000, 2_000_000),
                )
                chunks.extend(ai_runtime.build_retrieval_chunks(entry, text))
                continue
            if kind == "video":
                derivative_root, derivatives = ai_runtime.material_derivatives_to_temp(entry, paths_provider=paths_provider)
                temp_roots.append(derivative_root)
                audio = derivatives.get("audio.m4a")
                if audio is None:
                    source_root, source = ai_runtime.material_source_to_temp(entry, paths_provider=paths_provider)
                    temp_roots.append(source_root)
                    audio, _frames = ai_runtime.extract_video_audio_and_frames(source, source_root, settings=settings)
                if audio:
                    chunks.extend(ai_runtime.build_retrieval_chunks(entry, local_transcribe(audio, local=local)))
                continue
            if kind == "audio":
                source_root, source = ai_runtime.material_source_to_temp(entry, paths_provider=paths_provider)
                temp_roots.append(source_root)
                chunks.extend(ai_runtime.build_retrieval_chunks(entry, local_transcribe(source, local=local)))
        selected = ai_runtime.select_retrieval_chunks(chunks, " ".join([source_title, focus, strategy]))
        if not selected:
            raise RuntimeError(
                "本機免費 AI 備援目前需要可擷取文字或語音的教材；純圖片教材請等雲端免費額度恢復。"
            )
        return ai_runtime.format_retrieval_context(selected), selected, kinds
    finally:
        for root in temp_roots:
            shutil.rmtree(root, ignore_errors=True)


def generate_local_questions(
    entries: list[dict], *, category_id: str, count: int, qtype: str, difficulty: str,
    focus: str, strategy: str, settings=None, paths_provider=storage_paths,
    local: LocalFallbackSettings | None = None,
):
    settings = settings or ai_runtime.ai_settings()
    local = local or LocalFallbackSettings.from_env()
    title = " + ".join(entry.get("title") or entry.get("filename") or "教材" for entry in entries)
    context, chunks, kinds = _local_context(
        entries, source_title=title, focus=focus, strategy=strategy,
        settings=settings, paths_provider=paths_provider, local=local,
    )
    count2, system_prompt, prompt = ai_runtime.question_prompt_parts(
        count=count, qtype=qtype, difficulty=difficulty, focus=focus,
        source_title=title, source_text=context, settings=settings,
    )
    existing = [
        str(item.get("question") or "").strip()
        for item in assessment_repository.list_questions(str(category_id), include_inactive=True)
        if str(item.get("question") or "").strip()
    ][:50]
    if existing:
        prompt += "\n\n【現有正式題庫】\n" + "\n".join(f"- {value[:220]}" for value in existing) + "\n避免重複題。"
    prompt += "\n" + ai_runtime.ai_strategy_rule(strategy, entries)
    raw = ollama_chat(system_prompt + "\n\n" + prompt, json_mode=True, local=local)
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.S).strip()
    try:
        parsed = json.loads(cleaned)
    except Exception as exc:
        raise RuntimeError(f"本機 AI 題目 JSON 解析失敗：{exc}") from exc
    video = next((entry for entry in entries if ai_runtime.material_kind(entry) == "video"), None)
    questions = ai_runtime.normalize_ai_questions(
        parsed, count2,
        video_media_url=f"/view/{video.get('id')}" if video else "",
        provenance_chunks=chunks,
    )
    return questions, title, kinds


def install_question_runtime_fallback(runtime):
    """Wrap one dedicated Worker runtime and preserve actual provider provenance."""
    if getattr(runtime, "_free_fallback_installed", False):
        return runtime
    original_generate = runtime.generate_ai_questions_from_materials
    original_provider = runtime.active_ai_provider
    original_model = runtime.ai_model_name
    state = {"provider": "", "model": ""}

    def generate(entries, **kwargs):
        settings = ai_runtime.ai_settings()
        local = LocalFallbackSettings.from_env()
        primary = str(original_provider() or settings.provider or "groq").lower()
        progress_callback = kwargs.get("progress_callback")
        progress_id = str(kwargs.get("progress_id") or "")

        def notify(failed: str, next_provider: str) -> None:
            if progress_callback is not None and progress_id:
                progress_callback(
                    progress_id, 58, "切換免費 AI 備援",
                    f"{_provider_label(failed)} 額度/速率或服務暫時不可用，改用 {_provider_label(next_provider)}。",
                )

        def canonical(provider: str):
            if provider == primary:
                return original_generate(entries, **kwargs)
            provider_settings = replace(settings, provider=provider)
            return ai_runtime.generate_ai_questions_from_materials(
                entries,
                category_id=kwargs.get("category_id", ""),
                count=kwargs.get("count", 5),
                qtype=kwargs.get("qtype", "mixed"),
                difficulty=kwargs.get("difficulty", "standard"),
                focus=kwargs.get("focus", ""),
                strategy=kwargs.get("strategy", "balanced"),
                progress_id=progress_id,
                progress_callback=progress_callback,
                settings=provider_settings,
                paths_provider=getattr(runtime, "paths_provider", storage_paths),
            )

        callers = {"groq": lambda: canonical("groq"), "gemini": lambda: canonical("gemini")}
        if primary == "openai" and not bool(getattr(settings, "free_only_mode", True)):
            callers["openai"] = lambda: canonical("openai")
        result, meta = run_with_fallback(
            primary,
            cloud_callers=callers,
            local_caller=lambda: generate_local_questions(
                entries,
                category_id=str(kwargs.get("category_id") or ""),
                count=int(kwargs.get("count", 5) or 5),
                qtype=str(kwargs.get("qtype") or "mixed"),
                difficulty=str(kwargs.get("difficulty") or "standard"),
                focus=str(kwargs.get("focus") or ""),
                strategy=str(kwargs.get("strategy") or "balanced"),
                settings=settings,
                paths_provider=getattr(runtime, "paths_provider", storage_paths),
                local=local,
            ),
            settings=settings, local=local, notify=notify,
        )
        state["provider"] = str(meta.get("provider") or "")
        state["model"] = str(meta.get("model") or "")
        return result

    runtime.generate_ai_questions_from_materials = generate
    runtime.active_ai_provider = lambda: state["provider"] or original_provider()
    runtime.ai_model_name = lambda: state["model"] or original_model()
    runtime._free_fallback_installed = True
    return runtime


def generate_text_with_fallback(prompt: str, *, settings, primary: str, cloud_callers, notify=None):
    local = LocalFallbackSettings.from_env()
    return run_with_fallback(
        primary,
        cloud_callers=cloud_callers,
        local_caller=lambda: ollama_chat(prompt, json_mode=False, local=local),
        settings=settings,
        local=local,
        notify=notify,
    )


__all__ = [
    "LocalFallbackSettings", "generate_local_questions", "generate_text_with_fallback",
    "install_question_runtime_fallback", "is_retryable_provider_error", "local_ai_is_configured",
    "local_transcribe", "ollama_chat", "provider_chain", "provider_model", "run_with_fallback",
]
