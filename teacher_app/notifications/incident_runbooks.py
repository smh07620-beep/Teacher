"""Static, non-secret operational runbooks keyed by stable error code."""
from __future__ import annotations

from typing import Any


_RUNBOOKS = {
    "WORKER_OFFLINE": {
        "title": "Worker 離線處置",
        "steps": [
            "確認院內電腦是否開機、網路是否可用。",
            "確認 Windows Task Scheduler 的 Teacher Worker 工作正在執行。",
            "查看 Worker / Job 狀態的最後 heartbeat 與 Worker ID。",
            "必要時重新啟動排程；已在 R2 staging 的教材不要重新上傳。",
        ],
    },
    "WORKER_HEARTBEAT_STALLED": {
        "title": "Job stale／heartbeat 卡住",
        "steps": [
            "確認該 Worker process 是否仍存在，以及 heartbeat 是否恢復。",
            "確認 FFmpeg、LibreOffice 或 storage publish 是否仍在執行。",
            "不要手動建立重複 Job；等待既有 stale recovery 做安全續接。",
            "若 shared staging 已不存在，再依 Job 狀態決定是否需要重新上傳來源檔。",
        ],
    },
    "R2_STORAGE": {
        "title": "R2 儲存異常",
        "steps": [
            "確認 Cloudflare R2 bucket 與 endpoint 可連線。",
            "確認 Web/Worker 使用的 R2 access key、secret 與 bucket 權限仍有效。",
            "檢查 multipart/single PUT 的 staging object 是否仍存在。",
            "原始 staging 還在時優先重試既有 Job，不要重新上傳。",
        ],
    },
    "STORAGE_PROVIDER": {
        "title": "正式儲存 Provider 異常",
        "steps": [
            "確認目前啟用的正式儲存 Provider 與 Worker preflight 狀態。",
            "確認 provider 登入/session/寫入權限與院內網路。",
            "先恢復 provider，再對既有 Job 重試；避免建立重複教材。",
        ],
    },
    "GDRIVE_STORAGE": {
        "title": "Google Drive 儲存異常",
        "steps": [
            "確認 refresh token、client 設定與目標 folder 權限。",
            "確認 Worker 能列出並寫入既有目標資料夾。",
            "修復憑證或權限後重試既有 Job。",
        ],
    },
    "MEGA_STORAGE": {
        "title": "MEGA 儲存異常",
        "steps": [
            "確認 Task Scheduler 執行身分與 MEGAcmd 安裝使用者一致。",
            "執行 mega-whoami，確認 MEGAcmd Server/session 已啟動。",
            "確認目標教材根目錄可建立、上傳與刪除 probe。",
            "恢復 MEGA 後重試既有 Job；R2 staging 不需重傳。",
        ],
    },
    "OCI_STORAGE": {
        "title": "OCI Object Storage 異常",
        "steps": [
            "確認 bucket、namespace、endpoint 與認證設定。",
            "確認 Worker 到 OCI 的 HTTPS 連線與寫入權限。",
            "修復後重試既有 Job。",
        ],
    },
    "FFMPEG_CONVERSION": {
        "title": "FFmpeg 影音處理異常",
        "steps": [
            "確認 FFmpeg 與 FFprobe 在 Worker PATH 或設定路徑可執行。",
            "查看是否為硬體 encoder 失敗；確認 CPU fallback 是否成功啟動。",
            "檢查來源影音是否可由 ffprobe 正常解析。",
            "不要因單一硬體 encoder 失敗就重新上傳原始影音。",
        ],
    },
    "LIBREOFFICE_CONVERSION": {
        "title": "LibreOffice 文件轉檔異常",
        "steps": [
            "確認 soffice 可執行且 Worker 執行身分有權啟動 LibreOffice。",
            "確認 warm instance 是否存活；必要時讓 Worker 使用 one-shot fallback。",
            "確認來源 Office 檔未損毀或加密。",
            "來源檔正常時直接重試既有 Job。",
        ],
    },
    "DATABASE": {
        "title": "資料庫異常",
        "steps": [
            "確認 Render 到 Supabase/PostgreSQL 的連線與 pool 狀態。",
            "確認最新 schema migration 已套用。",
            "不要用重複上傳繞過資料庫錯誤。",
        ],
    },
    "DNS_RESOLUTION": {
        "title": "DNS 解析異常",
        "steps": [
            "從 Web 與院內 Worker 所在網路分別解析正式 Teacher hostname。",
            "確認 DNS、proxy/VPN 與院內防火牆設定。",
            "DNS 恢復後讓原 Job 自動或人工重試，不需重傳 staging。",
        ],
    },
    "NETWORK_TIMEOUT": {
        "title": "網路逾時",
        "steps": [
            "確認目標服務目前可連線且沒有長時間延遲。",
            "查看同時間是否有 DNS、R2、provider 或資料庫 incident。",
            "若來源已安全保留，優先等待 retry。",
        ],
    },
    "MATERIAL_FAILURE_RATE_HIGH": {
        "title": "教材失敗率升高",
        "steps": [
            "先看最近 error code 分布，找出是否集中在同一 provider/轉檔層。",
            "確認是否同時存在 Worker offline、R2 或 conversion incident。",
            "先處理共同根因，再逐筆重試失敗 Job。",
        ],
    },
}


def runbook_for(error_code: Any, incident_type: Any = "") -> dict[str, Any]:
    code = str(error_code or "").strip().upper()
    if code in _RUNBOOKS:
        item = _RUNBOOKS[code]
        return {"code": code, "title": item["title"], "steps": list(item["steps"])}
    if code.startswith("AI_"):
        return {
            "code": code,
            "title": "AI 背景工作連續失敗",
            "steps": [
                "確認 AI Worker 是否在線並可正常領取工作。",
                "確認主要 provider 額度、rate limit 與服務可用性。",
                "查看 fallback provider 是否已啟用且可用。",
                "恢復 provider/Worker 後重試原工作，不要建立重複內容。",
            ],
        }
    if str(incident_type or "") == "error_burst":
        return {
            "code": code,
            "title": "連續錯誤處置",
            "steps": [
                "先確認相同 error code 是否仍持續出現。",
                "依錯誤分類檢查 Worker、網路、儲存或轉檔依賴。",
                "修復共同根因後再處理既有失敗工作。",
            ],
        }
    return {
        "code": code,
        "title": "一般維運事件",
        "steps": [
            "確認 Incident 詳細資訊、最近工作與 Worker 狀態。",
            "依 error code 與 technical detail 找出共同根因。",
            "修復後確認 Incident 是否由系統自動轉為已恢復。",
        ],
    }


__all__ = ["runbook_for"]
