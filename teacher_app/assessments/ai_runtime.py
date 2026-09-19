"""Canonical AI question-generation runtime.

This module owns provider selection/configuration, material source retrieval,
text/media extraction and candidate generation for runtime AI questions.  HTTP
routes and question persistence stay in their existing canonical owners.

Storage credentials/clients remain owned by :mod:`teacher_app.storage.providers`.
Document text extraction reuses :mod:`teacher_app.materials.classification`.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import requests

from teacher_app.assessments import repository as assessment_repository
from teacher_app.common import privacy as ai_privacy
from teacher_app.config import storage_paths
from teacher_app.materials import classification
from teacher_app.storage import providers
from teacher_app.storage.web_runtime import WebStorageRuntime

try:  # optional deployment dependency
    from google import genai as google_genai
    from google.genai import types as google_genai_types
except ImportError:  # pragma: no cover - depends on deployment extras
    google_genai = None
    google_genai_types = None

try:  # optional deployment dependency used only for representative pages
    import pymupdf
except ImportError:  # pragma: no cover - depends on deployment extras
    pymupdf = None


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


@dataclass(frozen=True)
class AISettings:
    provider: str
    groq_api_key: str
    groq_model: str
    groq_transcribe_model: str
    gemini_api_key: str
    gemini_model: str
    openai_api_key: str
    openai_model: str
    source_max_chars: int
    max_questions: int
    media_max_mb: int
    max_materials: int
    video_frame_count: int
    free_only_mode: bool

    @classmethod
    def from_env(cls) -> "AISettings":
        return cls(
            provider=(os.environ.get("AI_PROVIDER", "groq").strip().lower() or "groq"),
            groq_api_key=classification.groq_api_key(),
            groq_model=classification.groq_model(),
            groq_transcribe_model=(
                os.environ.get("GROQ_TRANSCRIBE_MODEL", "whisper-large-v3-turbo").strip()
                or "whisper-large-v3-turbo"
            ),
            gemini_api_key=os.environ.get("GEMINI_API_KEY", "").strip(),
            gemini_model=(os.environ.get("GEMINI_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash"),
            openai_api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
            openai_model=(os.environ.get("OPENAI_MODEL", "gpt-5.6-luna").strip() or "gpt-5.6-luna"),
            source_max_chars=_int_env("AI_SOURCE_MAX_CHARS", 50000, 5000, 120000),
            max_questions=_int_env("AI_MAX_QUESTIONS", 15, 1, 30),
            media_max_mb=_int_env("AI_MEDIA_MAX_MB", 300, 10, 2000),
            max_materials=_int_env("AI_MAX_MATERIALS", 4, 1, 8),
            video_frame_count=_int_env("AI_VIDEO_FRAME_COUNT", 3, 1, 5),
            free_only_mode=_env_true("FREE_ONLY_MODE", True),
        )


def ai_settings() -> AISettings:
    return AISettings.from_env()


def active_ai_provider(settings: AISettings | None = None) -> str:
    settings = settings or ai_settings()
    provider = settings.provider if settings.provider in {"groq", "gemini", "openai", "auto"} else "groq"
    if settings.free_only_mode:
        return "groq" if provider in {"auto", "groq"} else provider
    if provider == "auto":
        if settings.groq_api_key:
            return "groq"
        if settings.gemini_api_key and google_genai is not None:
            return "gemini"
        if settings.openai_api_key:
            return "openai"
        return "groq"
    return provider


def ai_question_is_configured(settings: AISettings | None = None) -> bool:
    settings = settings or ai_settings()
    provider = active_ai_provider(settings)
    if provider == "groq":
        return bool(settings.groq_api_key)
    if provider == "gemini":
        return bool(settings.gemini_api_key and google_genai is not None)
    return bool(settings.openai_api_key)


def ai_model_name(settings: AISettings | None = None) -> str:
    settings = settings or ai_settings()
    provider = active_ai_provider(settings)
    if provider == "groq":
        return settings.groq_model
    if provider == "gemini":
        return settings.gemini_model
    return settings.openai_model


def material_kind(entry: dict) -> str:
    extension = Path(entry.get("filename") or entry.get("storageFilename") or "").suffix.lower()
    if extension in classification.VIDEO_EXT:
        return "video"
    if extension in classification.AUDIO_EXT:
        return "audio"
    if extension in classification.IMAGE_EXT:
        return "image"
    if extension in classification.SUBTITLE_EXT:
        return "subtitle"
    return "text"


def infer_ai_strategy(entries: list[dict]) -> str:
    joined = " ".join(
        str(entry.get("title") or "")
        + " "
        + str(entry.get("description") or "")
        + " "
        + str(entry.get("materialType") or entry.get("material_type") or "")
        for entry in (entries or [])
    ).lower()
    kinds = {material_kind(entry) for entry in (entries or [])}
    if "atlas" in joined or any(value in joined for value in ["圖譜", "辨識", "型態", "結晶", "寄生蟲", "血球", "細菌", "真菌"]):
        return "recognition"
    if "sop" in joined or any(value in joined for value in ["法規", "指引", "規範", "標準作業"]):
        return "regulation"
    if any(value in joined for value in ["故障", "異常", "troubleshooting", "案例", "輸血反應", "discrepancy"]):
        return "scenario"
    if any(value in joined for value in ["qc", "品質", "westgard", "安全", "通報", "critical value"]):
        return "safety"
    if "video" in kinds or any(value in joined for value in ["操作", "步驟", "保養", "流程", "儀器"]):
        return "workflow"
    return "balanced"


def ai_strategy_rule(strategy: str, entries: list[dict] | None = None) -> str:
    chosen = infer_ai_strategy(entries or []) if strategy == "auto" else strategy
    rule = {
        "balanced": "出題策略：均衡涵蓋教材重要內容，兼顧知識、流程與應用。",
        "workflow": "出題策略：優先考操作流程、先後順序、關鍵步驟與錯誤步驟辨識。",
        "scenario": "出題策略：優先產生臨床/值班情境題、異常處置、故障排除與判斷題。",
        "safety": "出題策略：優先考安全、品質、通報、風險控制與不可省略的關鍵步驟。",
        "recognition": "出題策略：優先考圖片/型態辨識、正異常比較、鑑別特徵與判讀線索。",
        "regulation": "出題策略：優先考 SOP、法規、指引、必要步驟、適用條件與不可省略的規範。",
    }.get(chosen, "出題策略：均衡涵蓋教材重要內容，兼顧知識、流程與應用。")
    if strategy == "auto":
        return (
            "出題策略：請先閱讀所有教材內容後，自行判斷最適合的考核方式，可混合知識、流程、辨識、情境、品質安全與法規。"
            f"系統依教材類型/標題初步判斷較適合「{chosen}」，僅作提示；若教材實際內容顯示其他策略更合理，請依內容調整。"
            + rule
        )
    return rule


def _content_type(path_or_name: object) -> str:
    return mimetypes.guess_type(str(path_or_name))[0] or "application/octet-stream"


def _gdrive_download_to_path(file_id: str, destination: Path) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    session = providers.gdrive_authorized_session()
    try:
        with session.get(
            f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media",
            stream=True,
            timeout=120,
        ) as response:
            response.raise_for_status()
            with destination.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
    finally:
        session.close()
    return destination


def material_source_to_temp(
    entry: dict,
    *,
    paths_provider: Callable[[], Any] = storage_paths,
    web_storage_factory: Callable[[Any], Any] = WebStorageRuntime,
) -> tuple[Path, Path]:
    """Fetch one material source into a temporary local file."""

    paths = paths_provider()
    extension = Path(entry.get("filename") or entry.get("storageFilename") or "source.bin").suffix.lower() or ".bin"
    temp_root = Path(paths.tmp_dir) / f"aiq-{entry['id']}-{uuid.uuid4().hex[:8]}"
    temp_root.mkdir(parents=True, exist_ok=True)
    source = temp_root / f"source{extension}"
    backend = str(entry.get("storageBackend") or "local").lower()
    try:
        if backend == "mega":
            file_id = entry.get("storageKey") or (entry.get("storageMeta") or {}).get("sourceFileId", "")
            if not file_id:
                raise RuntimeError("此教材缺少 MEGA 原始檔 ID。")
            web_storage_factory(paths).mega_download_file(str(file_id), source)
        elif backend == "gdrive":
            file_id = entry.get("storageKey") or (entry.get("storageMeta") or {}).get("sourceFileId", "")
            if not file_id:
                raise RuntimeError("此教材缺少 Google Drive 原始檔 ID。")
            _gdrive_download_to_path(str(file_id), source)
        elif backend == "oci":
            if not providers.oci_is_configured():
                raise RuntimeError("此教材位於 Oracle Object Storage，但目前伺服器未設定 OCI 金鑰。")
            key = entry.get("storageKey") or f"materials/{entry['id']}/source{extension}"
            providers.oci_client().download_file(providers.OCI_BUCKET_NAME, str(key), str(source))
        elif backend == "r2":
            if not providers.r2_is_configured():
                raise RuntimeError("此教材位於 R2，但目前伺服器未設定 R2 金鑰。")
            key = entry.get("storageKey") or f"materials/{entry['id']}/source{extension}"
            providers.r2_client().download_file(providers.R2_BUCKET_NAME, str(key), str(source))
        else:
            directory = Path(paths.upload_dir) / str(entry["id"])
            local = directory / str(entry.get("storageFilename") or f"source{extension}")
            if not local.exists():
                matches = list(directory.glob("source.*")) if directory.exists() else []
                local = matches[0] if matches else local
            if not local.exists():
                raise RuntimeError("Render 本機找不到此教材原始檔，請重新上傳教材。")
            shutil.copy2(local, source)
        return temp_root, source
    except Exception:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise


def extract_material_text_for_ai(
    entry: dict,
    *,
    settings: AISettings | None = None,
    paths_provider: Callable[[], Any] = storage_paths,
) -> tuple[str, int]:
    """Public privacy-wrap target for text sent to external AI providers."""

    settings = settings or ai_settings()
    if entry.get("isBuiltin"):
        raise RuntimeError("內建舊教材沒有保留原始 PPT/PDF 檔，請先從後台重新上傳該教材後再使用 AI 出題。")
    temp_root, source = material_source_to_temp(entry, paths_provider=paths_provider)
    try:
        extension = source.suffix.lower()
        if extension == ".pdf":
            text = classification.extract_pdf_text(source)
        elif extension == ".pptx":
            text = classification.extract_pptx_text(source)
        elif extension == ".docx":
            text = classification.extract_docx_text(source)
        elif extension in {".txt", ".csv", ".srt", ".vtt"}:
            text = classification.extract_plain_text(source)
        elif extension in classification.OFFICE_EXT:
            text = classification.extract_pdf_text(
                classification.convert_office_to_pdf_for_text(source, temp_root)
            )
        else:
            raise RuntimeError(
                "目前文字擷取支援 PPT/PPTX、PDF、Word、Excel、ODP/ODT/ODS、TXT、CSV、SRT、VTT。若使用 Gemini，圖片、影音可直接交由多模態模型理解。"
            )
        text = classification.clean_extracted_text(text)
        if len(text) < 80:
            raise RuntimeError("教材可擷取的文字太少，可能主要是圖片/掃描頁。請改用含文字的 PPT/PDF，或另外上傳文字版教材。")
        return text[: settings.source_max_chars], len(text)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


# Privacy integration must wrap named public targets explicitly.  Do not infer
# extractors by scanning this module's namespace.
EXTERNAL_AI_TEXT_EXTRACTOR_TARGETS = (
    "extract_material_text_for_ai",
    "groq_transcribe",
)


def _response_output_text(data: Any) -> str:
    chunks: list[str] = []
    for item in data.get("output", []) if isinstance(data, dict) else []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) or []:
            if isinstance(content, dict) and content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    if chunks:
        return "".join(chunks)

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("type") == "output_text" and isinstance(value.get("text"), str):
                chunks.append(value["text"])
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(data)
    return "".join(chunks)


def _coerce_ai_question_list(parsed: Any) -> list[dict]:
    if isinstance(parsed, list):
        return [question for question in parsed if isinstance(question, dict)]
    if not isinstance(parsed, dict):
        return []
    for key in ("questions", "items", "results"):
        value = parsed.get(key)
        if isinstance(value, list):
            return [question for question in value if isinstance(question, dict)]
    data = parsed.get("data")
    if isinstance(data, list):
        return [question for question in data if isinstance(question, dict)]
    if isinstance(data, dict):
        for key in ("questions", "items", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return [question for question in value if isinstance(question, dict)]
    return [parsed] if parsed.get("question") else []


def question_prompt_parts(
    *,
    count,
    qtype,
    difficulty,
    focus,
    source_title,
    source_text="",
    settings: AISettings | None = None,
) -> tuple[int, str, str]:
    settings = settings or ai_settings()
    focus = ai_privacy.deidentify_external_text(focus)
    source_title = ai_privacy.deidentify_external_text(source_title)
    source_text = ai_privacy.deidentify_external_text(source_text)
    count = max(1, min(settings.max_questions, int(count or 5)))
    allowed = {
        "choice", "multi", "fill", "essay", "mixed", "mixed_choice_multi", "mixed_all",
        "video_choice", "video_multi", "video_fill", "video_essay", "video_mixed",
    }
    qtype = qtype if qtype in allowed else "mixed_all"
    difficulty = difficulty if difficulty in {"basic", "standard", "advanced"} else "standard"
    video_mode = qtype.startswith("video_")
    base = qtype[6:] if video_mode else qtype
    type_rule = {
        "choice": "全部產生單選題。每題 4 個不同且合理的選項，只有 1 個正確答案。",
        "multi": "全部產生多選題。每題 4 個選項，至少 2 個正確答案；answerConfig.correctIndices 必須列出所有正確選項索引。",
        "fill": "全部產生填空題。options 必須是空陣列；answerConfig.acceptedAnswers 提供 1~5 個教材支持的可接受答案。",
        "essay": "全部產生問答題。options 必須是空陣列；explanation 提供人工批改用評分參考重點。",
        "mixed": "混合產生單選題與問答題；若題數允許至少各 1 題。",
        "mixed_choice_multi": "只混合產生單選題與多選題；若題數允許至少各 1 題，不要產生填空或問答題。",
        "mixed_all": "混合產生單選、多選、填空、問答四種題型；題數允許時盡量平均分配。",
    }.get(base, "混合產生單選、多選、填空、問答四種題型。")
    if video_mode:
        if base == "mixed":
            type_rule = "全部以影片互動題形式產生，混合單選、多選、填空、問答。"
        else:
            type_rule = "全部以影片互動題形式產生。" + type_rule
        type_rule += " 每題 answerConfig.pauseAt 必須填入建議暫停秒數，應對應逐字稿或畫面中可支持答案的時間點。"
    diff_rule = {
        "basic": "難度：基礎，以關鍵規範、名詞、步驟辨識為主。",
        "standard": "難度：標準，以流程順序、操作判斷、異常處置、QC/通報重點與應用為主。",
        "advanced": "難度：進階，以情境判斷、步驟錯誤辨識、故障排除與跨段落整合為主。",
    }[difficulty]
    focus_rule = f"額外出題重點：{focus}" if focus else "平均涵蓋教材重要內容，避免所有題目集中在同一小節。"
    system_prompt = (
        "你是醫院檢驗科教育訓練的考題草擬助手。只能根據提供的教材/圖片/影音內容出題，不得用教材外知識補答案。"
        "如果內容沒有明確支持答案就不要出題。題目需適合院內教育訓練與能力考核，避免模稜兩可、雙重否定與語意陷阱。"
        "圖片題要以畫面可辨識資訊為依據；影音題可引用字幕、語音或畫面內容。"
    )
    prompt = (
        f"教材名稱：{source_title}\n需要題數：{count}\n{type_rule}\n{diff_rule}\n{focus_rule}\n\n"
        "請只輸出 JSON，不要 Markdown。每題格式："
        '{"questionType":"choice|multi|fill|essay","question":"題幹","options":["A","B","C","D"],"correct":0,'
        '"answerConfig":{"correctIndices":[0,2],"acceptedAnswers":["答案"],"pauseAt":75},"tag":"分類",'
        '"explanation":"詳解或評分重點","sourceHint":"頁碼/投影片/MM:SS/畫面線索","sourceEvidence":"答案依據摘要"}。'
        "不適用的 answerConfig 欄位可留空陣列或 0。"
    )
    if source_text:
        prompt += f"\n\n【教材文字開始】\n{source_text}\n【教材文字結束】"
    return count, system_prompt, prompt


def normalize_ai_questions(parsed: Any, count: int, video_media_url: str = "") -> list[dict]:
    result: list[dict] = []
    for question in _coerce_ai_question_list(parsed)[:count]:
        qtype = str(question.get("questionType") or "choice").lower()
        if qtype not in {"choice", "multi", "fill", "essay"}:
            qtype = "choice"
        text = str(question.get("question", "")).strip()
        if not text:
            continue
        config = question.get("answerConfig") if isinstance(question.get("answerConfig"), dict) else {}
        options = [str(value).strip() for value in (question.get("options") or []) if str(value).strip()][:4]
        correct = 0
        if qtype in {"choice", "multi"}:
            if len(options) != 4:
                continue
            try:
                correct = max(0, min(3, int(question.get("correct", 0) or 0)))
            except Exception:
                correct = 0
        else:
            options = []
        if qtype == "multi":
            indices = []
            for value in config.get("correctIndices", question.get("correctIndices", [])) or []:
                try:
                    index = int(value)
                    if 0 <= index < 4:
                        indices.append(index)
                except Exception:
                    pass
            indices = sorted(set(indices)) or [correct]
            config["correctIndices"] = indices
            correct = indices[0]
        if qtype == "fill":
            answers = [
                str(value).strip()
                for value in (config.get("acceptedAnswers", question.get("acceptedAnswers", [])) or [])
                if str(value).strip()
            ][:10]
            if not answers:
                fallback = str(question.get("correctAnswer", "")).strip()
                if fallback:
                    answers = [fallback]
            if not answers:
                continue
            config["acceptedAnswers"] = answers
            config["caseSensitive"] = False
        pause = config.get("pauseAt", question.get("pauseAt", 0))
        try:
            pause = max(0, float(pause or 0))
        except Exception:
            pause = 0
        if video_media_url:
            if pause <= 0:
                hint = str(question.get("sourceHint", ""))
                match = re.search(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)", hint)
                if match:
                    pause = int(match.group(1)) * 60 + int(match.group(2))
            config["mediaUrl"] = video_media_url
            config["pauseAt"] = pause
        result.append({
            "questionType": qtype,
            "question": text[:2000],
            "options": options,
            "correct": correct,
            "answerConfig": config,
            "tag": str(question.get("tag", "AI教材題"))[:100],
            "explanation": str(question.get("explanation", ""))[:4000],
            "sourceHint": str(question.get("sourceHint", ""))[:300],
            "sourceEvidence": str(question.get("sourceEvidence", ""))[:600],
        })
    if not result:
        raise RuntimeError("AI 回傳的題目未通過格式檢查，請重新產生。")
    return result


def _groq_error(response) -> str:
    try:
        data = response.json()
        return (data.get("error") or {}).get("message") or str(data)[:500]
    except Exception:
        return response.text[:500]


def groq_transcribe(path: Path, *, settings: AISettings | None = None) -> str:
    settings = settings or ai_settings()
    if not settings.groq_api_key:
        raise RuntimeError("Groq 尚未設定 GROQ_API_KEY。")
    with Path(path).open("rb") as handle:
        response = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            files={"file": (Path(path).name, handle, _content_type(path))},
            data={"model": settings.groq_transcribe_model, "response_format": "verbose_json"},
            timeout=180,
        )
    if response.status_code == 429:
        raise RuntimeError("Groq 免費 AI 額度/速率已達上限，請稍後或明日再試；系統不會自動切換付費服務。")
    if response.status_code >= 400:
        raise RuntimeError(f"Groq 語音轉文字失敗 HTTP {response.status_code}：{_groq_error(response)}")
    data = response.json()
    text = data.get("text", "")
    segments = data.get("segments") or []
    if segments:
        lines = []
        for segment in segments:
            start = float(segment.get("start", 0) or 0)
            lines.append(f"[{int(start // 60):02d}:{int(start % 60):02d}] {segment.get('text', '').strip()}")
        text = "\n".join(lines)
    return text


def extract_video_audio_and_frames(
    video: Path,
    temp_root: Path,
    *,
    settings: AISettings | None = None,
) -> tuple[Path | None, list[tuple[Path, float]]]:
    settings = settings or ai_settings()
    temp_root = Path(temp_root)
    audio = temp_root / "audio.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", str(audio)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=180,
        check=False,
    )
    duration = 0.0
    try:
        process = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        duration = float((process.stdout or "0").strip() or 0)
    except Exception:
        pass
    frames: list[tuple[Path, float]] = []
    for index in range(settings.video_frame_count):
        timestamp = (
            duration * (index + 1) / (settings.video_frame_count + 1)
            if duration > 0
            else index * 10
        )
        frame = temp_root / f"frame-{index + 1}.jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(timestamp), "-i", str(video), "-frames:v", "1", "-vf", "scale='min(1280,iw)':-2", str(frame)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            check=False,
        )
        if frame.exists():
            frames.append((frame, timestamp))
    return (audio if audio.exists() else None), frames


def extract_document_preview_frames(source: Path, temp_root: Path, max_frames: int = 2) -> list[tuple[Path, int]]:
    if pymupdf is None or max_frames <= 0:
        return []
    extension = Path(source).suffix.lower()
    pdf = Path(source) if extension == ".pdf" else None
    try:
        if pdf is None and extension in classification.OFFICE_EXT:
            pdf = classification.convert_office_to_pdf_for_text(Path(source), Path(temp_root))
        if pdf is None or not Path(pdf).exists():
            return []
        result: list[tuple[Path, int]] = []
        with pymupdf.open(str(pdf)) as document:
            count = len(document)
            if count <= 0:
                return []
            if max_frames == 1:
                indices = [max(0, count // 2)]
            else:
                indices = []
                for index in [0, max(0, count // 2), max(0, count - 1)]:
                    if index not in indices:
                        indices.append(index)
                    if len(indices) >= max_frames:
                        break
            for sequence, index in enumerate(indices, 1):
                frame = Path(temp_root) / f"doc-preview-{sequence}.png"
                pixmap = document[index].get_pixmap(matrix=pymupdf.Matrix(1.35, 1.35), alpha=False)
                pixmap.save(str(frame))
                if frame.exists():
                    result.append((frame, index + 1))
        return result
    except Exception:
        return []


def _data_url(path: Path) -> str:
    return f"data:{_content_type(path)};base64," + base64.b64encode(Path(path).read_bytes()).decode("ascii")


def generate_openai_question_candidates(
    source_text: str,
    *,
    count,
    qtype,
    difficulty,
    focus,
    source_title,
    settings: AISettings | None = None,
) -> list[dict]:
    settings = settings or ai_settings()
    source_text = ai_privacy.deidentify_external_text(source_text)
    focus = ai_privacy.deidentify_external_text(focus)
    source_title = ai_privacy.deidentify_external_text(source_title)
    if not settings.openai_api_key:
        raise RuntimeError("OpenAI 智慧出題尚未設定。請在 Render Environment 新增 OPENAI_API_KEY。")
    count = max(1, min(settings.max_questions, int(count or 5)))
    qtype = qtype if qtype in {"choice", "essay", "mixed"} else "mixed"
    difficulty = difficulty if difficulty in {"basic", "standard", "advanced"} else "standard"
    schema = {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "minItems": count,
                "maxItems": count,
                "items": {
                    "type": "object",
                    "properties": {
                        "questionType": {"type": "string", "enum": ["choice", "essay"]},
                        "question": {"type": "string"},
                        "options": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
                        "correct": {"type": "integer", "minimum": 0, "maximum": 3},
                        "tag": {"type": "string"},
                        "explanation": {"type": "string"},
                        "sourceHint": {"type": "string"},
                    },
                    "required": ["questionType", "question", "options", "correct", "tag", "explanation", "sourceHint"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["questions"],
        "additionalProperties": False,
    }
    type_rule = {
        "choice": "全部產生選擇題。每題必須有 4 個不同且合理的選項，且只有 1 個正確答案。",
        "essay": "全部產生問答題。options 必須是空陣列，correct 固定為 0；explanation 請提供評分參考重點。",
        "mixed": "混合產生選擇題與問答題；若題數允許，至少各有 1 題。選擇題 4 選 1；問答題 options 為空陣列。",
    }[qtype]
    diff_rule = {
        "basic": "難度：基礎。以關鍵規範、名詞、步驟辨識為主。",
        "standard": "難度：標準。以流程順序、操作判斷、異常處置、QC/通報重點與應用為主。",
        "advanced": "難度：進階。以情境判斷、步驟錯誤辨識、故障排除與跨段落整合為主，但答案仍必須能由教材直接支持。",
    }[difficulty]
    focus_rule = f"額外出題重點：{focus}" if focus else "請平均涵蓋教材中的重要段落，避免所有題目集中在同一小節。"
    system_prompt = (
        "你是醫院檢驗科教育訓練的考題草擬助手。只能依照使用者提供的教材文字出題，不得使用教材外的醫學常識補充答案，"
        "不得自行更正教材、推測未寫明的數值或流程。若教材沒有明確支持某個答案，就不要出那一題。"
        "題目要適合院內教育訓練與能力考核，避免模稜兩可、雙重否定、只有語意陷阱的題目。"
        "詳解要指出教材中支持答案的重點；sourceHint 請填最接近的頁碼/投影片標記或教材段落線索。"
    )
    user_prompt = f"教材名稱：{source_title}\n需要題數：{count}\n{type_rule}\n{diff_rule}\n{focus_rule}\n\n【教材文字開始】\n{source_text}\n【教材文字結束】"
    payload = {
        "model": settings.openai_model,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "reasoning": {"effort": "low"},
        "text": {"format": {"type": "json_schema", "name": "question_candidates", "strict": True, "schema": schema}},
        "max_output_tokens": 12000,
    }
    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"AI 服務連線失敗：{exc}") from exc
    if response.status_code >= 400:
        try:
            error = response.json().get("error", {}).get("message", "")
        except Exception:
            error = response.text[:600]
        raise RuntimeError(f"AI 服務回傳 HTTP {response.status_code}：{error or '請檢查 API Key / 額度 / 模型設定'}")
    raw = _response_output_text(response.json())
    if not raw:
        raise RuntimeError("AI 沒有回傳可解析的題目內容。")
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        raise RuntimeError(f"AI 題目 JSON 解析失敗：{exc}") from exc
    result = []
    for question in _coerce_ai_question_list(parsed)[:count]:
        question_type = question.get("questionType") if question.get("questionType") in {"choice", "essay"} else "choice"
        text = str(question.get("question", "")).strip()
        if not text:
            continue
        options = [str(value).strip() for value in (question.get("options") or []) if str(value).strip()][:4]
        if question_type == "choice":
            if len(options) != 4:
                continue
            correct = max(0, min(3, int(question.get("correct", 0) or 0)))
        else:
            options = []
            correct = 0
        result.append({
            "questionType": question_type,
            "question": text[:2000],
            "options": options,
            "correct": correct,
            "tag": str(question.get("tag", "AI教材題"))[:100],
            "explanation": str(question.get("explanation", ""))[:4000],
            "sourceHint": str(question.get("sourceHint", ""))[:300],
            "sourceEvidence": str(question.get("sourceEvidence", ""))[:600],
        })
    if not result:
        raise RuntimeError("AI 回傳的題目未通過格式檢查，請重新產生。")
    return result


def generate_gemini_question_candidates(
    *,
    source_text="",
    source_path=None,
    count,
    qtype,
    difficulty,
    focus,
    source_title,
    settings: AISettings | None = None,
) -> list[dict]:
    settings = settings or ai_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("Google Gemini 尚未設定。請在 Render Environment 新增 GEMINI_API_KEY。")
    if google_genai is None or google_genai_types is None:
        raise RuntimeError("伺服器缺少 google-genai 套件，請使用 V5.3.9 的 requirements.txt 重新部署。")
    count, system_prompt, user_prompt = question_prompt_parts(
        count=count,
        qtype=qtype,
        difficulty=difficulty,
        focus=focus,
        source_title=source_title,
        source_text=source_text,
        settings=settings,
    )
    client = google_genai.Client(api_key=settings.gemini_api_key)
    uploaded = None
    try:
        contents: list[Any] = [system_prompt + "\n\n" + user_prompt]
        if source_path is not None:
            source_path = Path(source_path)
            if source_path.stat().st_size > settings.media_max_mb * 1024 * 1024:
                raise RuntimeError(f"此多媒體教材超過 AI_MEDIA_MAX_MB={settings.media_max_mb}MB，請壓縮後再出題。")
            uploaded = client.files.upload(file=str(source_path))
            deadline = time.time() + 300
            while getattr(getattr(uploaded, "state", None), "name", "") in {"PROCESSING", "STATE_UNSPECIFIED"}:
                if time.time() > deadline:
                    raise RuntimeError("Gemini 處理影音檔超時，請稍後重試或縮短影片。")
                time.sleep(3)
                uploaded = client.files.get(name=uploaded.name)
            if getattr(getattr(uploaded, "state", None), "name", "") == "FAILED":
                raise RuntimeError("Gemini 無法處理此影音/圖片教材。")
            contents = [uploaded, system_prompt + "\n\n" + user_prompt]
        config = google_genai_types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2)
        response = client.models.generate_content(model=settings.gemini_model, contents=contents, config=config)
        raw = (getattr(response, "text", None) or "").strip()
        if not raw:
            raise RuntimeError("Gemini 沒有回傳可解析的題目內容。")
        try:
            parsed = json.loads(raw)
        except Exception as original:
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.S).strip()
            try:
                parsed = json.loads(cleaned)
            except Exception:
                raise RuntimeError(f"Gemini 題目 JSON 解析失敗：{original}") from original
        return normalize_ai_questions(parsed, count)
    except Exception as exc:
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(f"Gemini AI 出題失敗：{exc}") from exc
    finally:
        if uploaded is not None:
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                pass


def generate_gemini_multisource_candidates(
    entries: list[dict],
    *,
    count,
    qtype,
    difficulty,
    focus,
    source_title,
    strategy="balanced",
    existing_questions=None,
    settings: AISettings | None = None,
    paths_provider: Callable[[], Any] = storage_paths,
) -> list[dict]:
    settings = settings or ai_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("Google Gemini 尚未設定。請在 Render Environment 新增 GEMINI_API_KEY。")
    if google_genai is None or google_genai_types is None:
        raise RuntimeError("伺服器缺少 google-genai 套件，請重新部署 requirements.txt。")
    if not entries:
        raise RuntimeError("請至少選擇一份教材。")
    if len(entries) > settings.max_materials:
        raise RuntimeError(f"一次最多可選 {settings.max_materials} 份教材，避免請求過大。")
    kinds = [material_kind(entry) for entry in entries]
    if kinds.count("video") > 1:
        raise RuntimeError("為提高影片理解穩定性，一次最多選 1 支影片；可再搭配字幕、圖片或文字教材。")
    count, system_prompt, base_prompt = question_prompt_parts(
        count=count,
        qtype=qtype,
        difficulty=difficulty,
        focus=focus,
        source_title=source_title,
        source_text="",
        settings=settings,
    )
    existing = [
        ai_privacy.deidentify_external_text(value).strip()
        for value in (existing_questions or [])
        if str(value).strip()
    ][:80]
    duplicate_rule = ""
    if existing:
        duplicate_rule = "\n\n【現有正式題庫題幹】\n" + "\n".join(f"- {value[:240]}" for value in existing) + "\n請避免產生語意重複或只是換句話說的題目。"
    evidence_rule = (
        "\n每一題除了 sourceHint 外，必須提供 sourceEvidence：用一句話簡短說明答案依據來自哪份教材的哪個內容。"
        "不要大段逐字引用教材。若是影片請盡量填 MM:SS 時間戳；圖片請描述畫面線索；字幕請標示字幕時間。"
    )
    prompt = base_prompt + "\n" + ai_strategy_rule(strategy, entries) + evidence_rule + duplicate_rule
    client = google_genai.Client(api_key=settings.gemini_api_key)
    temp_roots: list[Path] = []
    uploads: list[Any] = []
    content_parts: list[Any] = []
    text_sections: list[str] = []
    try:
        for index, entry in enumerate(entries, 1):
            title = ai_privacy.deidentify_external_text(
                entry.get("title") or entry.get("filename") or f"教材{index}"
            )
            kind = material_kind(entry)
            if kind in {"text", "subtitle"}:
                text, _total = extract_material_text_for_ai(entry, settings=settings, paths_provider=paths_provider)
                text_sections.append(f"【來源 {index}：{title}】\n{text}")
                continue
            if entry.get("isBuiltin"):
                raise RuntimeError(f"{title} 沒有保留原始多媒體檔，請重新上傳後再使用 AI 出題。")
            temp_root, source = material_source_to_temp(entry, paths_provider=paths_provider)
            temp_roots.append(temp_root)
            if source.stat().st_size > settings.media_max_mb * 1024 * 1024:
                raise RuntimeError(f"{title} 超過 AI_MEDIA_MAX_MB={settings.media_max_mb}MB，請壓縮後再出題。")
            uploaded = client.files.upload(file=str(source))
            uploads.append(uploaded)
            deadline = time.time() + 420
            while getattr(getattr(uploaded, "state", None), "name", "") in {"PROCESSING", "STATE_UNSPECIFIED"}:
                if time.time() > deadline:
                    raise RuntimeError(f"Gemini 處理 {title} 超時，請稍後重試或縮短影音檔。")
                time.sleep(3)
                uploaded = client.files.get(name=uploaded.name)
                uploads[-1] = uploaded
            if getattr(getattr(uploaded, "state", None), "name", "") == "FAILED":
                raise RuntimeError(f"Gemini 無法處理教材：{title}")
            content_parts.append(uploaded)
        if text_sections:
            combined = "\n\n".join(text_sections)
            if len(combined) > settings.source_max_chars:
                combined = combined[: settings.source_max_chars] + "\n[文字來源已依 AI_SOURCE_MAX_CHARS 截斷]"
            prompt += "\n\n" + combined
        contents = content_parts + [system_prompt + "\n\n" + prompt]
        config = google_genai_types.GenerateContentConfig(response_mime_type="application/json", temperature=0.15)
        response = client.models.generate_content(model=settings.gemini_model, contents=contents, config=config)
        raw = (getattr(response, "text", None) or "").strip()
        if not raw:
            raise RuntimeError("Gemini 沒有回傳可解析的題目內容。")
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.S).strip()
        try:
            parsed = json.loads(cleaned)
        except Exception as exc:
            raise RuntimeError(f"Gemini 題目 JSON 解析失敗：{exc}") from exc
        video_entry = next((entry for entry in entries if material_kind(entry) == "video"), None)
        video_url = f"/view/{video_entry.get('id')}" if video_entry else ""
        return normalize_ai_questions(parsed, count, video_media_url=video_url)
    except Exception as exc:
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(f"Gemini 多媒體 AI 出題失敗：{exc}") from exc
    finally:
        for uploaded in uploads:
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                pass
        for temp_root in temp_roots:
            shutil.rmtree(temp_root, ignore_errors=True)


def generate_groq_multisource_candidates(
    entries: list[dict],
    *,
    count,
    qtype,
    difficulty,
    focus,
    source_title,
    strategy="balanced",
    existing_questions=None,
    progress_id="",
    progress_callback: Callable[..., Any] | None = None,
    settings: AISettings | None = None,
    paths_provider: Callable[[], Any] = storage_paths,
) -> list[dict]:
    settings = settings or ai_settings()
    if not settings.groq_api_key:
        raise RuntimeError("Groq Free AI 尚未設定。請在 Render Environment 新增 GROQ_API_KEY。")
    if not entries:
        raise RuntimeError("請至少選擇一份教材。")
    if len(entries) > settings.max_materials:
        raise RuntimeError(f"一次最多可選 {settings.max_materials} 份教材。")
    count, system_prompt, base_prompt = question_prompt_parts(
        count=count,
        qtype=qtype,
        difficulty=difficulty,
        focus=focus,
        source_title=source_title,
        source_text="",
        settings=settings,
    )
    existing = [
        ai_privacy.deidentify_external_text(value).strip()
        for value in (existing_questions or [])
        if str(value).strip()
    ][:80]
    prompt = base_prompt + "\n" + ai_strategy_rule(strategy, entries) + "\n每題請提供 sourceHint 與 sourceEvidence，指出答案依據；不可使用教材外知識。"
    if existing:
        prompt += "\n【現有正式題庫】\n" + "\n".join("- " + value[:220] for value in existing) + "\n避免重複題。"
    content = [{"type": "text", "text": system_prompt + "\n\n" + prompt}]
    temp_roots: list[Path] = []
    text_sections: list[str] = []
    image_count = 0

    def progress(percent, stage, detail, *, current=0, total=0):
        if progress_id and progress_callback is not None:
            progress_callback(progress_id, percent, stage, detail, current=current, total=total)

    progress(12, "準備 AI 教材", f"已選 {len(entries)} 份教材，開始解析內容", current=0, total=len(entries))
    try:
        for index, entry in enumerate(entries, 1):
            title = ai_privacy.deidentify_external_text(
                entry.get("title") or entry.get("filename") or f"教材{index}"
            )
            kind = material_kind(entry)
            base_percent = 14 + ((index - 1) / max(1, len(entries))) * 38
            stage = {
                "text": "解析文件內容",
                "subtitle": "解析字幕",
                "image": "分析圖片 / Atlas",
                "audio": "轉錄音訊",
                "video": "擷取影片畫面與語音",
            }.get(kind, "解析教材")
            progress(base_percent, stage, f"{index}/{len(entries)}：{title}", current=index - 1, total=len(entries))
            if kind in {"text", "subtitle"}:
                text = ""
                try:
                    text, _total = extract_material_text_for_ai(entry, settings=settings, paths_provider=paths_provider)
                except Exception:
                    text_sections.append(f"【來源 {index}：{title}】文字擷取有限，改以文件代表頁面視覺分析。")
                if text:
                    text_sections.append(f"【來源 {index}：{title}】\n{text}")
                if kind == "text" and image_count < 5 and ai_privacy.external_media_allowed():
                    try:
                        temp_root, source = material_source_to_temp(entry, paths_provider=paths_provider)
                        temp_roots.append(temp_root)
                        previews = extract_document_preview_frames(source, temp_root, max_frames=min(2, 5 - image_count))
                        for frame, page_number in previews:
                            content.append({"type": "image_url", "image_url": {"url": _data_url(frame)}})
                            image_count += 1
                            text_sections.append(f"【{title} 代表頁面：第 {page_number} 頁】已附圖，請一併判讀圖表、流程、截圖或影像內容。")
                    except Exception:
                        pass
                if not text and image_count == 0:
                    raise RuntimeError(f"教材「{title}」無法擷取文字或可分析畫面，請改用 PDF/PPTX/圖片或影音教材。")
                continue

            temp_root, source = material_source_to_temp(entry, paths_provider=paths_provider)
            temp_roots.append(temp_root)
            if kind == "image":
                if image_count < 5 and source.stat().st_size <= 20 * 1024 * 1024:
                    content.append({"type": "image_url", "image_url": {"url": _data_url(source)}})
                    image_count += 1
                text_sections.append(f"【來源 {index}：{title}】此來源為圖片，請連同附圖判讀。")
            elif kind == "audio":
                progress(28 + (index / max(1, len(entries))) * 18, "音訊轉文字", f"Groq Whisper 正在轉錄：{title}", current=index, total=len(entries))
                text_sections.append(f"【來源 {index}：{title} 音訊逐字稿】\n" + groq_transcribe(source, settings=settings))
            elif kind == "video":
                progress(24 + (index / max(1, len(entries))) * 14, "擷取影片代表畫面", f"正在抽取畫面與音訊：{title}", current=index, total=len(entries))
                audio, frames = extract_video_audio_and_frames(source, temp_root, settings=settings)
                if audio:
                    progress(36 + (index / max(1, len(entries))) * 14, "影片語音轉文字", f"正在轉錄影片語音：{title}", current=index, total=len(entries))
                    text_sections.append(f"【來源 {index}：{title} 影片語音逐字稿】\n" + groq_transcribe(audio, settings=settings))
                for frame, timestamp in frames:
                    if image_count >= 5:
                        break
                    content.append({"type": "image_url", "image_url": {"url": _data_url(frame)}})
                    image_count += 1
                    text_sections.append(f"【{title} 代表畫面約 {int(timestamp // 60):02d}:{int(timestamp % 60):02d}】已附圖。")
        if text_sections:
            combined = "\n\n".join(text_sections)
            if len(combined) > settings.source_max_chars:
                combined = combined[: settings.source_max_chars] + "\n[內容已截斷]"
            content[0]["text"] += "\n\n" + combined
        payload = {
            "model": settings.groq_model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.15,
            "response_format": {"type": "json_object"},
            "max_completion_tokens": 8000,
        }
        progress(62, "AI 正在產生候選題", f"{settings.groq_model} 正在整合教材、比對既有題庫並產生題目")
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=180,
        )
        if response.status_code == 429:
            raise RuntimeError("Groq 免費 AI 額度/速率已達上限，請稍後或明日再試；FREE_ONLY_MODE 不會自動切換任何付費 API。")
        if response.status_code >= 400:
            raise RuntimeError(f"Groq AI 出題失敗 HTTP {response.status_code}：{_groq_error(response)}")
        raw = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.S).strip()
        try:
            parsed = json.loads(cleaned)
        except Exception as exc:
            raise RuntimeError(f"Groq 題目 JSON 解析失敗：{exc}") from exc
        progress(86, "檢查 AI 題目格式", "正在驗證題型、答案、來源提示與多媒體時間點")
        video_entry = next((entry for entry in entries if material_kind(entry) == "video"), None)
        video_url = f"/view/{video_entry.get('id')}" if video_entry else ""
        normalized = normalize_ai_questions(parsed, count, video_media_url=video_url)
        progress(94, "整理候選題", f"已完成 {len(normalized)} 題格式檢查，準備回傳後台")
        return normalized
    finally:
        for temp_root in temp_roots:
            shutil.rmtree(temp_root, ignore_errors=True)


def generate_ai_question_candidates(
    source_text: str,
    *,
    count,
    qtype,
    difficulty,
    focus,
    source_title,
    settings: AISettings | None = None,
) -> list[dict]:
    settings = settings or ai_settings()
    provider = active_ai_provider(settings)
    if provider == "groq":
        count2, system_prompt, base_prompt = question_prompt_parts(
            count=count,
            qtype=qtype,
            difficulty=difficulty,
            focus=focus,
            source_title=source_title,
            source_text=source_text,
            settings=settings,
        )
        payload = {
            "model": settings.groq_model,
            "messages": [{"role": "user", "content": system_prompt + "\n\n" + base_prompt}],
            "temperature": 0.15,
            "response_format": {"type": "json_object"},
            "max_completion_tokens": 8000,
        }
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
        if response.status_code == 429:
            raise RuntimeError("Groq 免費 AI 額度已達上限，請稍後再試。")
        if response.status_code >= 400:
            raise RuntimeError(f"Groq AI 出題失敗：{_groq_error(response)}")
        raw = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.S).strip())
        return normalize_ai_questions(parsed, count2)
    if provider == "gemini":
        return generate_gemini_question_candidates(
            source_text=source_text,
            count=count,
            qtype=qtype,
            difficulty=difficulty,
            focus=focus,
            source_title=source_title,
            settings=settings,
        )
    return generate_openai_question_candidates(
        source_text,
        count=count,
        qtype=qtype,
        difficulty=difficulty,
        focus=focus,
        source_title=source_title,
        settings=settings,
    )


def generate_ai_questions_from_material(
    entry: dict,
    *,
    count,
    qtype,
    difficulty,
    focus,
    settings: AISettings | None = None,
    paths_provider: Callable[[], Any] = storage_paths,
) -> tuple[list[dict], int, int, str]:
    settings = settings or ai_settings()
    provider = active_ai_provider(settings)
    title = entry.get("title") or entry.get("filename") or "教材"
    extension = Path(entry.get("filename") or entry.get("storageFilename") or "").suffix.lower()
    media_extensions = classification.IMAGE_EXT | classification.VIDEO_EXT | classification.AUDIO_EXT
    if provider == "groq" and extension in media_extensions:
        questions = generate_groq_multisource_candidates(
            [entry], count=count, qtype=qtype, difficulty=difficulty, focus=focus,
            source_title=title, settings=settings, paths_provider=paths_provider,
        )
        return questions, 0, 0, "media"
    if provider == "gemini" and extension in media_extensions:
        if entry.get("isBuiltin"):
            raise RuntimeError("內建舊教材沒有原始多媒體檔，請重新上傳後再使用 AI 出題。")
        temp_root, source = material_source_to_temp(entry, paths_provider=paths_provider)
        try:
            questions = generate_gemini_question_candidates(
                source_path=source,
                count=count,
                qtype=qtype,
                difficulty=difficulty,
                focus=focus,
                source_title=title,
                settings=settings,
            )
            return questions, 0, 0, "media"
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)
    source_text, total_chars = extract_material_text_for_ai(entry, settings=settings, paths_provider=paths_provider)
    questions = generate_ai_question_candidates(
        source_text,
        count=count,
        qtype=qtype,
        difficulty=difficulty,
        focus=focus,
        source_title=title,
        settings=settings,
    )
    return questions, len(source_text), total_chars, "text"


def generate_ai_questions_from_materials(
    entries: list[dict],
    *,
    category_id,
    count,
    qtype,
    difficulty,
    focus,
    strategy="balanced",
    progress_id="",
    progress_callback: Callable[..., Any] | None = None,
    settings: AISettings | None = None,
    paths_provider: Callable[[], Any] = storage_paths,
) -> tuple[list[dict], str, list[str]]:
    settings = settings or ai_settings()
    if not entries:
        raise RuntimeError("請至少選擇一份教材。")
    provider = active_ai_provider(settings)
    if progress_id and progress_callback is not None:
        progress_callback(progress_id, 6, "讀取正式題庫", "正在載入既有題目，避免 AI 產生重複內容")
    existing = [
        question.get("question", "")
        for question in assessment_repository.list_questions(str(category_id), include_inactive=True)
    ]
    title = " + ".join(entry.get("title") or entry.get("filename") or "教材" for entry in entries)
    kinds = [material_kind(entry) for entry in entries]
    has_media = any(kind in {"image", "video", "audio"} for kind in kinds)
    if str(qtype).startswith("video_") and "video" not in kinds:
        raise RuntimeError("影片互動題需要至少選擇 1 支影片教材。")
    if provider == "groq":
        questions = generate_groq_multisource_candidates(
            entries,
            count=count,
            qtype=qtype,
            difficulty=difficulty,
            focus=focus,
            source_title=title,
            strategy=strategy,
            existing_questions=existing,
            progress_id=progress_id,
            progress_callback=progress_callback,
            settings=settings,
            paths_provider=paths_provider,
        )
        return questions, title, kinds
    if provider == "gemini":
        if progress_id and progress_callback is not None:
            progress_callback(progress_id, 18, "準備 Gemini 多媒體分析", "正在上傳 / 解析教材來源")
        questions = generate_gemini_multisource_candidates(
            entries,
            count=count,
            qtype=qtype,
            difficulty=difficulty,
            focus=focus,
            source_title=title,
            strategy=strategy,
            existing_questions=existing,
            settings=settings,
            paths_provider=paths_provider,
        )
        return questions, title, kinds
    if has_media or len(entries) > 1:
        raise RuntimeError("OpenAI 備援模式在此版本僅處理單一文字來源；免費多媒體模式請使用 AI_PROVIDER=groq。")
    source_text, _total = extract_material_text_for_ai(entries[0], settings=settings, paths_provider=paths_provider)
    questions = generate_openai_question_candidates(
        source_text,
        count=count,
        qtype=qtype,
        difficulty=difficulty,
        focus=focus,
        source_title=title,
        settings=settings,
    )
    return questions, title, ["text"]


__all__ = [
    "AISettings",
    "EXTERNAL_AI_TEXT_EXTRACTOR_TARGETS",
    "active_ai_provider",
    "ai_model_name",
    "ai_question_is_configured",
    "ai_settings",
    "ai_strategy_rule",
    "extract_document_preview_frames",
    "extract_material_text_for_ai",
    "extract_video_audio_and_frames",
    "generate_ai_question_candidates",
    "generate_ai_questions_from_material",
    "generate_ai_questions_from_materials",
    "generate_gemini_multisource_candidates",
    "generate_gemini_question_candidates",
    "generate_groq_multisource_candidates",
    "generate_openai_question_candidates",
    "groq_transcribe",
    "infer_ai_strategy",
    "material_kind",
    "material_source_to_temp",
    "normalize_ai_questions",
    "question_prompt_parts",
]
