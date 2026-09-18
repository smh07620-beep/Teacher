"""Narrow runtime seams for runtime-question HTTP APIs.

Question persistence, RBAC and material lookup are canonical concerns owned by
their repositories/routes.  AI provider/source/generation behavior is composed
from :mod:`teacher_app.assessments.ai_runtime`; progress files and
question-image storage use their existing canonical owners.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from teacher_app.assessments import ai_runtime
from teacher_app.config import storage_paths
from teacher_app.materials.upload_progress import UploadProgressStore
from teacher_app.storage.worker_runtime import WorkerMaterialStorageAdapter


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _env_true(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def _missing(name: str):
    def missing(*_args, **_kwargs):
        raise RuntimeError(f"QuestionRuntime callback is not configured: {name}")

    return missing


class QuestionImageMegaUploadError(RuntimeError):
    """MEGA-only question-image failure mapped to the historical HTTP 502."""

    def __init__(self, cause: Exception):
        self.cause = cause
        super().__init__(str(cause))


@dataclass
class QuestionRuntime:
    """Explicit boundary for AI generation and question web-runtime I/O."""

    ai_question_is_configured: Callable[[], bool]
    active_ai_provider: Callable[[], str]
    ai_model_name: Callable[[], str]
    generate_ai_questions_from_materials: Callable[..., tuple[list, str, list]]
    infer_ai_strategy: Callable[[list[dict]], str]
    paths_provider: Callable[[], Any] = storage_paths
    storage_adapter: Any | None = None
    clear_progress_callback: Callable[[str], Any] | None = None
    set_progress_callback: Callable[[str, float, str, str], Any] | None = None
    max_questions: int = 15
    source_max_chars: int = 50000
    max_materials: int = 4
    free_only_mode: bool = True

    def __post_init__(self) -> None:
        self.max_questions = max(1, min(30, int(self.max_questions or 15)))
        self.source_max_chars = max(5000, min(120000, int(self.source_max_chars or 50000)))
        self.max_materials = max(1, min(8, int(self.max_materials or 4)))
        if self.storage_adapter is None:
            self.storage_adapter = WorkerMaterialStorageAdapter()

    @classmethod
    def unconfigured(cls, *, paths_provider: Callable[[], Any] = storage_paths) -> "QuestionRuntime":
        """Build a credential-free runtime whose legacy-only AI callbacks fail closed."""

        return cls(
            ai_question_is_configured=lambda: False,
            active_ai_provider=_missing("active_ai_provider"),
            ai_model_name=_missing("ai_model_name"),
            generate_ai_questions_from_materials=_missing("generate_ai_questions_from_materials"),
            infer_ai_strategy=_missing("infer_ai_strategy"),
            paths_provider=paths_provider,
            max_questions=_int_env("AI_MAX_QUESTIONS", 15, 1, 30),
            source_max_chars=_int_env("AI_SOURCE_MAX_CHARS", 50000, 5000, 120000),
            max_materials=_int_env("AI_MAX_MATERIALS", 4, 1, 8),
            free_only_mode=_env_true("FREE_ONLY_MODE", True),
        )

    def _progress_store(self) -> UploadProgressStore:
        return UploadProgressStore(self.paths_provider())

    def clear_progress(self, progress_id: str) -> None:
        if self.clear_progress_callback is not None:
            self.clear_progress_callback(progress_id)
            return
        self._progress_store().clear(progress_id)

    def set_progress(self, progress_id: str, percent: float, stage: str, detail: str) -> None:
        if self.set_progress_callback is not None:
            self.set_progress_callback(progress_id, percent, stage, detail)
            return
        self._progress_store().set(progress_id, percent, stage, detail)

    def save_question_image(self, upload, name: str) -> str:
        """Persist one question image using the established local/MEGA behavior."""

        paths = self.paths_provider()
        directory = Path(paths.question_images_dir)
        directory.mkdir(parents=True, exist_ok=True)
        local = directory / str(name)
        upload.save(str(local))

        # Historical behavior keeps images local for every backend except MEGA.
        # MEGA removes the local copy only after the canonical adapter uploads it.
        if self.storage_adapter.active_backend() == "mega":
            try:
                self.storage_adapter._mega_free_guard(local.stat().st_size)
                remote_dir = self.storage_adapter._mega_remote_join(
                    self.storage_adapter._mega_root(),
                    "question-images",
                )
                self.storage_adapter._mega_upload_file(local, remote_dir, name)
                try:
                    local.unlink()
                except OSError:
                    pass
            except Exception as exc:
                try:
                    local.unlink()
                except OSError:
                    pass
                raise QuestionImageMegaUploadError(exc) from exc
        return f"/question-images/{name}"


def build_canonical_question_runtime(
    *,
    paths_provider: Callable[[], Any] = storage_paths,
    storage_adapter=None,
) -> QuestionRuntime:
    """Compose a production runtime without callbacks from a broad owner.

    AI provider configuration is captured from the current environment once for
    this runtime.  All provider/source functions remain public in ``ai_runtime``
    so privacy integration can wrap explicit extractor targets before this
    builder is invoked.
    """

    settings = ai_runtime.ai_settings()
    progress_store = UploadProgressStore(paths_provider())

    def generate(materials, **kwargs):
        return ai_runtime.generate_ai_questions_from_materials(
            materials,
            settings=settings,
            paths_provider=paths_provider,
            progress_callback=progress_store.set,
            **kwargs,
        )

    return QuestionRuntime(
        ai_question_is_configured=lambda: ai_runtime.ai_question_is_configured(settings),
        active_ai_provider=lambda: ai_runtime.active_ai_provider(settings),
        ai_model_name=lambda: ai_runtime.ai_model_name(settings),
        generate_ai_questions_from_materials=generate,
        infer_ai_strategy=ai_runtime.infer_ai_strategy,
        paths_provider=paths_provider,
        storage_adapter=storage_adapter,
        clear_progress_callback=progress_store.clear,
        set_progress_callback=progress_store.set,
        max_questions=settings.max_questions,
        source_max_chars=settings.source_max_chars,
        max_materials=settings.max_materials,
        free_only_mode=settings.free_only_mode,
    )


def runtime_from_owner(owner) -> QuestionRuntime:
    """Compatibility constructor for isolated Base-shaped callers.

    Direct Flask-app composition uses the canonical AI runtime.  A Base-shaped
    owner that still exposes the historical callbacks keeps an isolated-test /
    migration compatibility seam until factory wiring is fully cut over.
    """

    app = getattr(owner, "app", owner)
    configured_paths = getattr(getattr(app, "config", {}), "get", lambda *_: None)("STORAGE_PATHS")
    legacy_question_dir = getattr(owner, "QUESTION_IMAGES_DIR", None)
    if configured_paths is not None:
        paths_provider = lambda: configured_paths
    elif legacy_question_dir is not None:
        root = Path(legacy_question_dir)
        paths_provider = lambda: SimpleNamespace(
            question_images_dir=root,
            upload_progress_dir=root.parent / "upload_progress",
        )
    else:
        paths_provider = storage_paths

    if not callable(getattr(owner, "generate_ai_questions_from_materials", None)):
        return build_canonical_question_runtime(paths_provider=paths_provider)

    return QuestionRuntime(
        ai_question_is_configured=getattr(owner, "ai_question_is_configured", lambda: False),
        active_ai_provider=getattr(owner, "active_ai_provider", _missing("active_ai_provider")),
        ai_model_name=getattr(owner, "ai_model_name", _missing("ai_model_name")),
        generate_ai_questions_from_materials=getattr(
            owner,
            "generate_ai_questions_from_materials",
            _missing("generate_ai_questions_from_materials"),
        ),
        infer_ai_strategy=getattr(owner, "_infer_ai_strategy", _missing("infer_ai_strategy")),
        paths_provider=paths_provider,
        clear_progress_callback=getattr(owner, "clear_upload_progress", None),
        set_progress_callback=getattr(owner, "set_upload_progress", None),
        max_questions=getattr(owner, "AI_MAX_QUESTIONS", _int_env("AI_MAX_QUESTIONS", 15, 1, 30)),
        source_max_chars=getattr(
            owner,
            "AI_SOURCE_MAX_CHARS",
            _int_env("AI_SOURCE_MAX_CHARS", 50000, 5000, 120000),
        ),
        max_materials=getattr(owner, "AI_MAX_MATERIALS", _int_env("AI_MAX_MATERIALS", 4, 1, 8)),
        free_only_mode=bool(getattr(owner, "FREE_ONLY_MODE", _env_true("FREE_ONLY_MODE", True))),
    )


__all__ = [
    "QuestionImageMegaUploadError",
    "QuestionRuntime",
    "build_canonical_question_runtime",
    "runtime_from_owner",
]
