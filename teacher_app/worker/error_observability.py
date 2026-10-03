"""Safe, deterministic error taxonomy for material Worker observability."""
from __future__ import annotations

import re
from typing import Any


_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key|access[_-]?key)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)(https?://[^/@:\s]+:)[^/@\s]+@"),
)

_RULES = (
    (
        "LIBREOFFICE_CONVERSION",
        "conversion",
        ("libreoffice", "soffice", "office/pdf preview", "office to pdf"),
        "LibreOffice 文件轉檔失敗",
        "確認院內 Worker 的 LibreOffice 可執行；原始檔仍保留時可直接重新處理。",
    ),
    (
        "FFMPEG_CONVERSION",
        "conversion",
        ("ffmpeg", "ffprobe", "libx264", "nvenc", "qsv", "amf", "codec", "encoder"),
        "FFmpeg 影音處理失敗",
        "確認 FFmpeg/FFprobe 與編碼器可用；硬體編碼失敗時可由 CPU fallback 或重新處理。",
    ),
    (
        "R2_STORAGE",
        "storage",
        (
            "cloudflare r2",
            "r2 ",
            "r2:",
            "s3",
            "bucket",
            "multipart",
            "nosuchkey",
            "accessdenied",
            "invalidaccesskeyid",
            "signaturedoesnotmatch",
        ),
        "R2 儲存或上傳失敗",
        "確認 R2 bucket、憑證與網路；已安全接收的 staging 檔不要重複上傳。",
    ),
    (
        "GDRIVE_STORAGE",
        "storage",
        ("google drive", "gdrive"),
        "Google Drive 儲存失敗",
        "確認 Google Drive 憑證/權限與共享目錄，再重新處理既有工作。",
    ),
    (
        "MEGA_STORAGE",
        "storage",
        ("mega", "megacmd"),
        "MEGA 儲存失敗",
        "確認 MEGAcmd 登入與寫入權限，再重新處理既有工作。",
    ),
    (
        "OCI_STORAGE",
        "storage",
        ("oracle cloud", "oci ", "object storage"),
        "OCI Object Storage 儲存失敗",
        "確認 OCI bucket、namespace、憑證與網路，再重新處理既有工作。",
    ),
    (
        "STORAGE_PROVIDER",
        "storage",
        ("storage provider", "provider unavailable", "storage unavailable", "儲存未就緒"),
        "教材儲存 Provider 暫時不可用",
        "確認目前啟用的儲存 Provider 與網路；原始檔仍保留時等待或重新處理即可。",
    ),
    (
        "DATABASE",
        "database",
        ("postgres", "psycopg", "sqlite", "database", "db failed", "sqlstate"),
        "資料庫操作失敗",
        "檢查資料庫連線與 migration 狀態；不要用重複上傳來繞過資料庫錯誤。",
    ),
    (
        "SOURCE_INTEGRITY",
        "validation",
        (
            "sha256",
            "檔案大小不符",
            "空白檔案",
            "內容與副檔名不符",
            "不安全的檔名",
            "完整性驗證",
            "magic",
            "zip",
        ),
        "教材檔案完整性或格式驗證失敗",
        "確認原始檔未損毀、格式與副檔名一致；這類問題通常需要修正來源檔再上傳。",
    ),
    (
        "DNS_RESOLUTION",
        "network",
        ("getaddrinfo", "name resolution", "temporary failure in name resolution", "nodename nor servname", "dns"),
        "網路 DNS 解析失敗",
        "確認院內網路/DNS 與正式網址可解析；不需要重新上傳已安全接收的教材。",
    ),
    (
        "TLS_CONNECTION",
        "network",
        ("ssl", "tls", "certificate verify", "certificate_verify_failed"),
        "安全連線驗證失敗",
        "檢查系統時間、TLS 憑證與代理伺服器設定，再讓 Worker 重試。",
    ),
    (
        "NETWORK_TIMEOUT",
        "network",
        ("timed out", "timeout", "readtimeout", "connecttimeout"),
        "外部連線逾時",
        "先確認網路與服務狀態；若原始檔仍保留，讓系統自動重試即可。",
    ),
    (
        "WORKER_API",
        "worker",
        ("worker api ", "ownership 不符", "worker ownership"),
        "Worker 與 Web 協議/工作狀態不同步",
        "先查看 Worker 版本、heartbeat 與工作 ownership；不要直接建立重複工作。",
    ),
)


def sanitize_technical_detail(value: Any, limit: int = 1200) -> str:
    detail = str(value or "").replace("\x00", "").strip()
    for pattern in _SECRET_PATTERNS:
        if pattern.pattern.lower().startswith("(?i)(https"):
            detail = pattern.sub(r"\1***@", detail)
        elif "authorization" in pattern.pattern.lower():
            detail = pattern.sub(r"\1***", detail)
        else:
            detail = pattern.sub(lambda match: f"{match.group(1)}=***", detail)
    return detail[: max(0, int(limit))]


def classify_material_error(
    error: Any,
    *,
    stage: Any = "",
    status: Any = "",
    observability_state: Any = "",
) -> dict[str, Any]:
    raw = sanitize_technical_detail(error)
    stage_text = str(stage or "")
    status_text = str(status or "")
    live_state = str(observability_state or "")

    if live_state == "stalled":
        return {
            "errorCode": "WORKER_HEARTBEAT_STALLED",
            "errorCategory": "worker",
            "errorMessage": "Worker heartbeat 已超過 stale 門檻",
            "errorAction": "確認院內 Worker 是否仍在執行；系統會依既有 stale recovery 安全續接，請勿重複上傳。",
            "technicalDetail": raw,
            "requiresSourceReplacement": False,
        }
    if live_state == "heartbeat_delayed":
        return {
            "errorCode": "WORKER_HEARTBEAT_DELAYED",
            "errorCategory": "worker",
            "errorMessage": "Worker heartbeat 回報延遲",
            "errorAction": "先觀察 Worker 是否恢復回報；尚未達 stale 門檻時不要手動建立重複工作。",
            "technicalDetail": raw,
            "requiresSourceReplacement": False,
        }

    haystack = f"{stage_text}\n{raw}".lower()
    for code, category, markers, message, action in _RULES:
        if any(marker.lower() in haystack for marker in markers):
            return {
                "errorCode": code,
                "errorCategory": category,
                "errorMessage": message,
                "errorAction": action,
                "technicalDetail": raw,
                "requiresSourceReplacement": code == "SOURCE_INTEGRITY",
            }

    if status_text == "failed" or raw:
        return {
            "errorCode": "WORKER_PROCESSING_FAILED",
            "errorCategory": "worker",
            "errorMessage": "教材背景處理失敗",
            "errorAction": "查看技術細節與 Worker 狀態；原始檔仍保留時優先重新處理，不要重複上傳。",
            "technicalDetail": raw,
            "requiresSourceReplacement": False,
        }

    return {
        "errorCode": "",
        "errorCategory": "",
        "errorMessage": "",
        "errorAction": "",
        "technicalDetail": "",
        "requiresSourceReplacement": False,
    }


__all__ = ["classify_material_error", "sanitize_technical_detail"]
