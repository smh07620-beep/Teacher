"""AI-assisted teacher draft generation from existing teaching materials.

The runtime reuses canonical AI extraction/privacy helpers and the dedicated AI
Worker.  It supports several teacher-authoring draft types while preserving the
original lecture-script contract.  Every result is a draft and must be reviewed
by a teacher before approval or publication.
"""
from __future__ import annotations

from typing import Any

import requests

from teacher_app.assessments import ai_runtime, free_ai_fallback
from teacher_app.common import privacy as ai_privacy


MAX_SCRIPT_SOURCE_CHARS = 22000
MAX_SCRIPT_CHUNKS = 14
OUTPUT_TYPES = {
    "handout": "教學講義",
    "summary": "重點摘要",
    "slides": "投影片大綱",
    "script": "教學講稿",
    "quiz": "測驗題草稿",
    "objectives": "課程學習目標",
}


def normalize_output_type(value: Any) -> str:
    output_type = str(value or "script").strip().lower()
    if output_type not in OUTPUT_TYPES:
        raise ValueError("不支援的 AI 教材產出類型。")
    return output_type


def output_type_label(value: Any) -> str:
    return OUTPUT_TYPES.get(str(value or "").strip().lower(), "AI 教材草稿")


def _bounded_source_chunks(entry: dict, text: str, focus: str) -> list[dict]:
    chunks = ai_runtime.build_retrieval_chunks(entry, text)
    if not chunks:
        return []
    if str(focus or "").strip():
        return ai_runtime.select_retrieval_chunks(
            chunks,
            focus,
            max_chunks=MAX_SCRIPT_CHUNKS,
            max_chars=MAX_SCRIPT_SOURCE_CHARS,
        )
    selected: list[dict] = []
    used = 0
    for chunk in chunks:
        body = str(chunk.get("text") or "")
        if selected and used + len(body) > MAX_SCRIPT_SOURCE_CHARS:
            break
        selected.append(chunk)
        used += len(body)
        if len(selected) >= MAX_SCRIPT_CHUNKS:
            break
    return selected


def _draft_instruction(output_type: str, *, target_minutes: int) -> str:
    target_chars = max(700, min(9000, int(target_minutes) * 280))
    return {
        "handout": (
            "整理成可供學員閱讀的教學講義草稿。使用清楚標題、重點條列、必要步驟與警示；"
            "不可補造來源沒有的內容。"
        ),
        "summary": (
            "整理成精簡重點摘要。先列 5–10 個核心重點，再整理必要流程、數值、警示與易錯點；"
            "不要為了篇幅加入來源沒有的資訊。"
        ),
        "slides": (
            "整理成投影片大綱。請用「第 1 張、第 2 張……」方式規劃每張標題與 3–6 個重點；"
            "只做大綱，不虛構圖片、病例或數據。"
        ),
        "quiz": (
            "整理成教師可再審核的測驗題草稿。產生 5 題，混合單選、是非或簡答；"
            "每題附答案與簡短依據，題目只能取材自提供來源。不要直接發布到正式題庫。"
        ),
        "objectives": (
            "整理成課程學習目標草稿。列出 3–8 項可觀察、可評量的學習目標，必要時分為知識、技能、"
            "態度；不得加入來源未涵蓋的能力要求。"
        ),
        "script": (
            f"整理成老師可再編修、可自然朗讀的繁體中文口語講稿草稿。目標約 {target_minutes} 分鐘，"
            f"約 {target_chars} 個中文字上下；可依教材資訊量縮短，不可為湊長度而新增內容。"
        ),
    }[output_type]


def _prompt(*, source_title: str, context: str, focus: str, tone: str, target_minutes: int,
            output_type: str = "script") -> str:
    output_type = normalize_output_type(output_type)
    focus_line = ai_privacy.deidentify_external_text(focus).strip()
    tone = str(tone or "clinical").strip().lower()
    tone_rule = {
        "clinical": "專業、清楚、像臨床教師實際授課，不使用浮誇語氣。",
        "friendly": "口語自然但維持醫療專業，不使用過度娛樂化或誇大語氣。",
        "brief": "精簡直接，只保留核心概念、步驟、警示與結論。",
    }.get(tone, "專業、清楚、像臨床教師實際授課。")
    draft_rule = _draft_instruction(output_type, target_minutes=target_minutes)
    final_note = (
        "※ 本講稿需由授課教師確認後方可用於正式教學影音。"
        if output_type == "script"
        else "※ 本內容為 AI 草稿，需由教師確認後方可發布。"
    )
    return f"""你是醫學檢驗教師的教材編輯助手。請只根據下方【教材來源】產生「{output_type_label(output_type)}」草稿。

必要規則：
1. 不得加入教材來源沒有支持的醫療事實、數值、步驟、法規、診斷或治療建議。
2. 教材中的數字、單位、警示、條件與流程不得自行改寫成不同意思。
3. 如果教材資訊不足，直接寫「【需教師補充】」，不要猜測。
4. 病人或人員可識別資訊不得出現在輸出；來源已經過系統去識別化，仍請避免重新推測身份。
5. 這只是草稿，結尾加入「{final_note}」
6. 不要輸出 JSON，不要使用 markdown code fence。
7. 可使用短標題、條列與自然段落，讓老師容易直接修改。

產出要求：{draft_rule}
教材名稱：{source_title}
文字風格：{tone_rule}
特別聚焦：{focus_line or '依教材順序完整整理'}

【教材來源】
{context}
"""


def _groq(settings, prompt: str) -> str:
    if not settings.groq_api_key:
        raise RuntimeError("Groq AI 尚未設定。")
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}", "Content-Type": "application/json"},
            json={
                "model": settings.groq_model,
                "messages": [
                    {"role": "system", "content": "只根據提供的教材整理醫學檢驗教學內容，不得補造醫療內容。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 5000,
            },
            timeout=180,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Groq provider unavailable：{exc}") from exc
    if response.status_code == 429:
        raise RuntimeError("Groq 免費 AI quota/rate limit 已達上限。")
    if response.status_code in {502, 503, 504}:
        raise RuntimeError(f"Groq provider unavailable HTTP {response.status_code}。")
    response.raise_for_status()
    data = response.json()
    text = str((((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")).strip()
    if not text:
        raise RuntimeError("AI 沒有回傳教材草稿內容。")
    return text


def _openai(settings, prompt: str) -> str:
    if not settings.openai_api_key:
        raise RuntimeError("OpenAI API 尚未設定。")
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
        json={
            "model": settings.openai_model,
            "input": prompt,
            "temperature": 0.2,
            "max_output_tokens": 5000,
        },
        timeout=180,
    )
    response.raise_for_status()
    text = ai_runtime._response_output_text(response.json()).strip()
    if not text:
        raise RuntimeError("AI 沒有回傳教材草稿內容。")
    return text


def _gemini(settings, prompt: str) -> str:
    if not settings.gemini_api_key or ai_runtime.google_genai is None:
        raise RuntimeError("Gemini AI 尚未設定。")
    client = ai_runtime.google_genai.Client(api_key=settings.gemini_api_key)
    config = None
    if ai_runtime.google_genai_types is not None:
        config = ai_runtime.google_genai_types.GenerateContentConfig(temperature=0.2)
    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=config,
        )
    except Exception as exc:
        if free_ai_fallback.is_retryable_provider_error(exc):
            raise RuntimeError(f"Gemini provider unavailable/rate limit：{exc}") from exc
        raise
    text = str(getattr(response, "text", None) or "").strip()
    if not text:
        raise RuntimeError("AI 沒有回傳教材草稿內容。")
    return text


def _generate_body_with_fallback(settings, provider: str, prompt: str, progress_callback=None) -> tuple[str, dict[str, Any]]:
    local = free_ai_fallback.LocalFallbackSettings.from_env()
    chain = [provider]
    if local.enabled:
        for candidate in free_ai_fallback.provider_chain(provider, settings=settings, local=local):
            if candidate not in chain:
                chain.append(candidate)

    last_error: Exception | None = None
    for index, candidate in enumerate(chain):
        try:
            if candidate == "groq":
                body = _groq(settings, prompt)
            elif candidate == "gemini":
                body = _gemini(settings, prompt)
            elif candidate == "openai":
                body = _openai(settings, prompt)
            elif candidate == "ollama":
                body = free_ai_fallback.generate_text_with_fallback(
                    prompt,
                    settings=settings,
                    primary="ollama",
                    cloud_callers={},
                )[0]
            else:
                raise RuntimeError("未支援的 AI provider。")
            model = (
                ai_runtime.ai_model_name(settings)
                if candidate == provider
                else free_ai_fallback.provider_model(candidate, settings=settings, local=local)
            )
            return body, {
                "provider": candidate,
                "model": model,
                "fallbackUsed": index > 0,
                "attemptedProviders": chain[: index + 1],
            }
        except Exception as exc:
            last_error = exc
            if not free_ai_fallback.is_retryable_provider_error(exc):
                raise
            if index + 1 < len(chain) and progress_callback:
                progress_callback(
                    60,
                    "切換免費 AI 備援",
                    "主要免費 AI 額度/速率或服務暫時不可用，正在改用下一個免費備援。",
                )
    raise RuntimeError(
        "免費 AI 目前暫時無法使用：雲端額度/速率已達限制，且本機 AI 備援尚未完成工作。"
    ) from last_error


def generate_script(entry: dict, *, reference_entries: list[dict] | None = None, focus: str = "", tone: str = "clinical", target_minutes: int = 5,
                    output_type: str = "script", progress_callback=None) -> dict[str, Any]:
    output_type = normalize_output_type(output_type)
    label = output_type_label(output_type)
    settings = ai_runtime.ai_settings()
    local_ready = free_ai_fallback.local_ai_is_configured()
    if not ai_privacy.external_enabled() and not local_ready:
        raise RuntimeError("院方目前已停用外部 AI 處理，且本機 AI 備援尚未啟用。")
    provider = ai_runtime.active_ai_provider(settings) if ai_privacy.external_enabled() else "ollama"

    if progress_callback:
        progress_callback(15, "統整原始資料", "正在讀取 Worker 文字索引並建立多來源檢索內容")
    entries = [entry, *(reference_entries or [])]
    source_chars = 0
    chunks = []
    source_warnings = []
    readable_sources = []
    focus = ai_privacy.deidentify_external_text(focus).strip()[:500]
    for source in entries:
        try:
            text, chars = ai_runtime.extract_material_text_for_ai(source, settings=settings)
            selected = _bounded_source_chunks(source, text, focus)[:12]
            if not selected:
                raise RuntimeError("可擷取文字不足")
            source_chars += int(chars or len(text))
            chunks.extend(selected)
            readable_sources.append(source)
        except Exception as exc:
            source_warnings.append({
                "materialId": str(source.get("id") or ""),
                "title": str(source.get("title") or source.get("filename") or source.get("id") or "教材")[:240],
                "storageBackend": str(source.get("storageBackend") or ""),
                "reason": str(exc)[:300],
            })
    chunks = chunks[:36]
    if not chunks:
        detail = "；".join(
            f"{item['title']}：{item['reason']}" for item in source_warnings[:3]
        )
        raise RuntimeError(
            f"所選教材都沒有可用的文字來源，無法產生{label}。"
            + (f" {detail}" if detail else "")
        )
    context = ai_runtime.format_retrieval_context(chunks)
    title_source = readable_sources[0] if readable_sources else entry
    title = ai_privacy.deidentify_external_text(
        title_source.get("title") or title_source.get("filename") or "教材"
    ).strip()[:300]
    prompt = _prompt(
        source_title=title,
        context=context,
        focus=focus,
        tone=tone,
        target_minutes=target_minutes,
        output_type=output_type,
    )

    if progress_callback:
        progress_callback(55, f"AI 產生{label}", f"使用免費 AI 產生{label}草稿")
    body, provider_meta = _generate_body_with_fallback(
        settings,
        provider,
        prompt,
        progress_callback=progress_callback,
    )

    body = ai_privacy.deidentify_external_text(body).strip()
    if len(body) < 60:
        raise RuntimeError(f"AI 回傳的{label}內容過短，請調整教材或聚焦內容後再試。")
    if progress_callback:
        progress_callback(90, "整理來源", "正在附上教材來源與教師確認標記")

    source_chunks = [
        {
            "materialId": str(chunk.get("materialId") or ""),
            "chunkId": str(chunk.get("chunkId") or ""),
            "section": str(chunk.get("section") or ""),
        }
        for chunk in chunks
    ]
    return {
        "title": f"{title}｜{label}",
        "body": body[:40000],
        "outputType": output_type,
        "outputLabel": label,
        "sourceMaterialId": str(title_source.get("id") or entry.get("id") or ""),
        "sourceTitle": title,
        "sourceChars": int(source_chars),
        "sourceChunks": source_chunks,
        "sourceWarnings": source_warnings,
        "sourceMaterialCount": len(readable_sources),
        "provider": provider_meta["provider"],
        "model": provider_meta["model"],
        "fallbackUsed": bool(provider_meta.get("fallbackUsed")),
        "targetMinutes": int(target_minutes),
        "tone": tone,
        "requiresTeacherReview": True,
    }


__all__ = [
    "OUTPUT_TYPES", "generate_script", "normalize_output_type", "output_type_label",
]
