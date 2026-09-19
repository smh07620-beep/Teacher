"""Canonical uploaded-material text extraction and classification.

This module owns the synchronous upload classifier's local text extraction,
keyword heuristics, and optional Groq Free classification call.  It reads only
its own environment-backed settings and does not depend on the legacy Flask
host or the AI question-generation workflow.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import requests

from teacher_app.materials import repository as material_repository

try:
    import pymupdf
except ImportError:  # pragma: no cover - optional deployment dependency
    pymupdf = None


MATERIAL_TYPE_VALUES = frozenset(material_repository.MATERIAL_TYPES)
OFFICE_EXT = frozenset({".pptx", ".ppt", ".doc", ".docx", ".xls", ".xlsx", ".odp", ".odt", ".ods"})
IMAGE_EXT = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})
VIDEO_EXT = frozenset({".mp4", ".webm", ".mov", ".m4v"})
AUDIO_EXT = frozenset({".mp3", ".wav", ".m4a", ".ogg"})
SUBTITLE_EXT = frozenset({".srt", ".vtt"})

_MATERIAL_CLASSIFY_KEYWORDS = {
    "sop": ["sop", "標準作業", "標準操作", "作業程序", "作業標準", "工作指引", "操作指引", "規範", "作業指引"],
    "troubleshooting": ["troubleshooting", "故障", "異常", "排除", "error", "alarm", "溶血", "檢體量不足", "量不足", "qc違反", "qc 異常", "westgard", "問題處理"],
    "case": ["案例", "case", "輸血反應", "discrepancy", "個案分析", "案例分析"],
    "infographic": ["資訊圖表", "infographic", "流程圖", "管制圖", "決策樹", "algorithm", "流程"],
    "atlas": ["atlas", "圖譜", "顯微鏡", "血球型態", "細胞型態", "尿液沉渣", "結晶", "寄生蟲", "蟲卵", "原蟲", "細菌形態", "真菌形態", "morphology", "microscopy"],
}

_CONVERSION_LOCK = threading.Lock()


def groq_api_key() -> str:
    return os.environ.get("GROQ_API_KEY", "").strip()


def groq_model() -> str:
    return os.environ.get("GROQ_MODEL", "qwen/qwen3.6-27b").strip() or "qwen/qwen3.6-27b"


def classify_timeout_seconds() -> int:
    try:
        value = int(os.environ.get("AI_CLASSIFY_TIMEOUT_SECONDS", "12"))
    except (TypeError, ValueError):
        value = 12
    return max(3, min(30, value))


def soffice_bin() -> str:
    return os.environ.get("SOFFICE_PATH", "soffice") or "soffice"


def clean_extracted_text(text) -> str:
    text = (text or "").replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf_text(path: Path) -> str:
    if pymupdf is None:
        raise RuntimeError("伺服器缺少 PyMuPDF，無法擷取 PDF 文字。")
    out = []
    with pymupdf.open(str(path)) as doc:
        for index, page in enumerate(doc, 1):
            text = clean_extracted_text(page.get_text("text"))
            if text:
                out.append(f"[第 {index} 頁]\n{text}")
    return "\n\n".join(out)


def extract_pptx_text(path: Path) -> str:
    out = []
    with zipfile.ZipFile(path) as archive:
        names = [
            name
            for name in archive.namelist()
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
        ]
        names.sort(key=lambda name: int(re.search(r"slide(\d+)\.xml", name).group(1)))
        namespace = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
        for index, name in enumerate(names, 1):
            root = ET.fromstring(archive.read(name))
            parts = [
                element.text.strip()
                for element in root.findall(".//a:t", namespace)
                if element.text and element.text.strip()
            ]
            if parts:
                out.append(f"[投影片 {index}]\n" + "\n".join(parts))
    return "\n\n".join(out)


def extract_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = []
    for paragraph in root.findall(".//w:p", namespace):
        parts = [text.text for text in paragraph.findall(".//w:t", namespace) if text.text]
        line = clean_extracted_text("".join(parts))
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)


def extract_plain_text(path: Path) -> str:
    raw = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def convert_office_to_pdf_for_text(source: Path, temp_root: Path) -> Path:
    temp_root = Path(temp_root)
    out_dir = temp_root / "pdf"
    out_dir.mkdir(parents=True, exist_ok=True)
    profile_dir = temp_root / "lo-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    command = [
        soffice_bin(),
        "--headless",
        "--norestore",
        f"-env:UserInstallation=file:///{profile_dir.as_posix()}",
        "--convert-to",
        "pdf",
        "--outdir",
        str(out_dir),
        str(source),
    ]
    with _CONVERSION_LOCK:
        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
            check=False,
        )
    pdfs = list(out_dir.glob("*.pdf"))
    if process.returncode != 0 or not pdfs:
        message = (process.stderr or process.stdout or b"").decode("utf-8", errors="ignore")[-800:]
        raise RuntimeError(
            f"LibreOffice 無法將教材轉成可讀文字的 PDF：{message or '轉檔失敗'}"
        )
    return pdfs[0]


def score_material_classification(text: str, weight: int = 1) -> dict[str, int]:
    normalized = (text or "").lower()
    scores = {kind: 0 for kind in _MATERIAL_CLASSIFY_KEYWORDS}
    for kind, words in _MATERIAL_CLASSIFY_KEYWORDS.items():
        for word in words:
            count = normalized.count(word.lower())
            if count:
                scores[kind] += min(4, count) * weight
    return scores


def merge_classification_scores(*score_sets) -> dict[str, int]:
    result = {kind: 0 for kind in _MATERIAL_CLASSIFY_KEYWORDS}
    for scores in score_sets:
        for kind, value in (scores or {}).items():
            if kind in result:
                result[kind] += int(value or 0)
    return result


def extract_local_text_for_classification(path: Path) -> str:
    """Best-effort short text extraction for one newly uploaded local file."""
    path = Path(path)
    extension = path.suffix.lower()
    temp_root = None
    try:
        if extension == ".pdf":
            text = extract_pdf_text(path)
        elif extension == ".pptx":
            text = extract_pptx_text(path)
        elif extension == ".docx":
            text = extract_docx_text(path)
        elif extension in {".txt", ".csv", ".srt", ".vtt"}:
            text = extract_plain_text(path)
        elif extension in OFFICE_EXT:
            temp_root = Path(tempfile.mkdtemp(prefix="material-classify-"))
            text = extract_pdf_text(convert_office_to_pdf_for_text(path, temp_root))
        else:
            return ""
        return clean_extracted_text(text)[:14000]
    except Exception:
        return ""
    finally:
        if temp_root:
            shutil.rmtree(temp_root, ignore_errors=True)


def groq_classify_material(text: str, filename: str, title: str, desc: str) -> tuple[str, str]:
    api_key = groq_api_key()
    if not api_key or not text or len(text) < 100:
        return "", ""
    prompt = f"""你是醫院檢驗科教學平台的教材管理助理。請只判斷這份教材最適合放在哪一個模組。
可選 materialType 僅能是：standard, atlas, infographic, troubleshooting, case, sop。
定義：
standard=一般核心課程教材；atlas=顯微鏡/細胞/細菌/結晶/寄生蟲辨識圖譜；infographic=流程圖/資訊圖表；troubleshooting=故障、異常、QC、檢體問題處理；case=案例分析/輸血反應案例；sop=正式 SOP/規範/作業指引。
若沒有足夠證據，選 standard。不得僅因內文出現「流程」二字就選 infographic。
只回傳 JSON：{{"materialType":"standard","reason":"20字內理由"}}

檔名：{filename}
教材名稱：{title}
說明：{desc}
內容節錄：
{text[:9000]}"""
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": groq_model(),
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "response_format": {"type": "json_object"},
                "max_completion_tokens": 250,
            },
            timeout=classify_timeout_seconds(),
        )
        if not response.ok:
            return "", ""
        payload = response.json()
        raw = (
            (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
            .strip()
        )
        parsed = json.loads(raw)
        kind = str(parsed.get("materialType") or "").strip().lower()
        reason = str(parsed.get("reason") or "").strip()[:120]
        if kind in MATERIAL_TYPE_VALUES - {"video"}:
            return kind, reason
    except Exception:
        pass
    return "", ""


def classify_uploaded_material(
    path: Path,
    original_name: str,
    title: str = "",
    desc: str = "",
    text_override: str | None = None,
) -> tuple[str, str, str]:
    """Return ``(resolved_type, method, reason)`` without paid AI fallback."""
    path = Path(path)
    extension = path.suffix.lower()
    media_extensions = VIDEO_EXT | AUDIO_EXT | SUBTITLE_EXT
    if extension in media_extensions:
        return "video", "副檔名判斷", "影音/字幕檔自動放入操作教學影片區"

    name_text = f"{original_name} {title}"
    if extension in IMAGE_EXT:
        name_scores = score_material_classification(name_text, 4)
        ranked = sorted(name_scores.items(), key=lambda item: item[1], reverse=True)
        if (
            ranked
            and ranked[0][1] >= 4
            and ranked[0][0] in {"atlas", "infographic", "troubleshooting", "case", "sop"}
        ):
            return ranked[0][0], "檔名判斷", f"檔名符合 {ranked[0][0]} 特徵"
        return "standard", "預設分類", "一般圖片未偵測到明確圖譜/流程圖標籤"

    title_scores = score_material_classification(f"{name_text} {desc}", 4)
    title_ranked = sorted(title_scores.items(), key=lambda item: item[1], reverse=True)
    if (
        title_ranked
        and title_ranked[0][1] >= 12
        and (len(title_ranked) < 2 or title_ranked[0][1] >= title_ranked[1][1] + 4)
    ):
        return title_ranked[0][0], "檔名判斷", f"檔名關鍵字分數 {title_ranked[0][1]}"

    text = (
        clean_extracted_text(text_override)[:14000]
        if text_override is not None
        else extract_local_text_for_classification(path)
    )
    content_scores = score_material_classification(text, 1)
    scores = merge_classification_scores(title_scores, content_scores)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top_kind, top_score = ranked[0] if ranked else ("standard", 0)
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    if top_score >= 8 and top_score >= second_score + 3:
        return top_kind, "內容規則判斷", f"關鍵字分數 {top_score}"

    ai_kind, ai_reason = groq_classify_material(text, original_name, title, desc)
    if ai_kind:
        return ai_kind, "Groq AI 內容判斷", ai_reason or "依教材內容判斷"

    if top_score >= 4 and top_score > second_score:
        return top_kind, "內容規則判斷", f"關鍵字分數 {top_score}"
    return "standard", "預設分類", "內容未呈現足夠明確的專用模組特徵"


# Compatibility aliases keep the extracted cluster easy to compare with the
# legacy implementation while production callers use the public names above.
_clean_extracted_text = clean_extracted_text
_extract_pdf_text = extract_pdf_text
_extract_pptx_text = extract_pptx_text
_extract_docx_text = extract_docx_text
_extract_plain_text = extract_plain_text
_convert_office_to_pdf_for_text = convert_office_to_pdf_for_text
_score_material_classification = score_material_classification
_merge_classification_scores = merge_classification_scores
_extract_local_text_for_classification = extract_local_text_for_classification
_groq_classify_material = groq_classify_material


__all__ = [
    "AUDIO_EXT",
    "IMAGE_EXT",
    "MATERIAL_TYPE_VALUES",
    "OFFICE_EXT",
    "SUBTITLE_EXT",
    "VIDEO_EXT",
    "classify_timeout_seconds",
    "classify_uploaded_material",
    "clean_extracted_text",
    "convert_office_to_pdf_for_text",
    "extract_docx_text",
    "extract_local_text_for_classification",
    "extract_pdf_text",
    "extract_plain_text",
    "extract_pptx_text",
    "groq_api_key",
    "groq_classify_material",
    "groq_model",
    "merge_classification_scores",
    "score_material_classification",
    "soffice_bin",
]
