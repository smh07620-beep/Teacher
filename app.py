# -*- coding: utf-8 -*-
"""
羅東聖母醫院 檢驗科生化組 - 2026生化教育訓練考核系統
後端服務 (Flask)

功能：
1. 提供靜態網頁 (static/index.html) 與已轉檔的簡報圖片。
2. 提供 /api/slides 給前端讀取目前所有簡報清單（內建 + 使用者上傳）。
3. 提供 /api/slides/upload：接收使用者上傳的 Office/PDF 教材。
   V5.7.0 延續單一 preview.pdf，並新增資料庫背景工作佇列、失敗續接、Fast Web View、
   預覽快取暖機與考卷發布快照；舊 WebP/PNG 教材仍相容。
4. 提供 /api/slides/<id> (DELETE)：刪除管理者上傳的教材。

部署需求：
- Python 3.9+
- pip install -r requirements.txt
- 主機需安裝 LibreOffice（可執行 soffice 指令）。
  Windows 預設路徑通常在 "C:\\Program Files\\LibreOffice\\program\\soffice.exe"，
  若不在 PATH 中，請設定環境變數 SOFFICE_PATH 指向該執行檔完整路徑。

啟動方式：
    python app.py
    預設監聽 0.0.0.0:5000，可用瀏覽器開啟 http://<伺服器IP>:5000/
    正式環境建議搭配 gunicorn / waitress 等 WSGI 伺服器，並在前面加 Nginx/IIS 反向代理。
"""

import os
import json
import uuid
import shutil
import subprocess
import threading
import datetime
import sqlite3
import time
import mimetypes
import re
import zipfile
import xml.etree.ElementTree as ET
import base64
import io
import tempfile
import hashlib
import socket
from functools import wraps
from urllib.parse import quote
from pathlib import Path

import requests

from flask import Flask, request, jsonify, send_from_directory, send_file, abort, redirect, Response, stream_with_context, session
from werkzeug.security import generate_password_hash, check_password_hash

try:
    import boto3
    from botocore.config import Config as BotoConfig
except ImportError:
    boto3 = None
    BotoConfig = None

try:
    from google.oauth2.credentials import Credentials as GoogleCredentials
    from google.auth.transport.requests import AuthorizedSession
    from googleapiclient.discovery import build as google_build
    from googleapiclient.http import MediaFileUpload
except ImportError:
    GoogleCredentials = None
    AuthorizedSession = None
    google_build = None
    MediaFileUpload = None

try:
    from google import genai as google_genai
    from google.genai import types as google_genai_types
except ImportError:
    google_genai = None
    google_genai_types = None

try:
    import pymupdf  # PyMuPDF，用於 PDF -> 教材頁面，跨平台不需額外安裝 poppler
except ImportError:
    pymupdf = None

try:
    from PIL import Image
except ImportError:
    Image = None


# ---------------------------------------------------------------------------
# 路徑與基本設定
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
SLIDES_DIR = STATIC_DIR / "slides"
MATERIAL_STORAGE = Path(os.environ.get("MATERIAL_STORAGE", "/var/data/materials"))
# Render Persistent Disk 建議掛載 /var/data；本機若無此路徑權限則改用專案 uploads。
try:
    MATERIAL_STORAGE.mkdir(parents=True, exist_ok=True)
except OSError:
    MATERIAL_STORAGE = BASE_DIR / "uploads"
UPLOAD_DIR = MATERIAL_STORAGE / "ppt"
QUESTION_IMAGES_DIR = MATERIAL_STORAGE / "question_images"
UPLOADED_SLIDES_DIR = MATERIAL_STORAGE / "slides"
DOC_TEMPLATES_DIR = MATERIAL_STORAGE / "doc_templates"
PGY_ASSESSMENT_TEMPLATES_DIR = MATERIAL_STORAGE / "pgy_assessment_templates"
MATERIAL_JOB_DIR = MATERIAL_STORAGE / "job_staging"
DATA_DIR = BASE_DIR / "data"
META_FILE = DATA_DIR / "slides_meta.json"
TMP_DIR = BASE_DIR / "tmp_convert"

for d in (SLIDES_DIR, UPLOAD_DIR, UPLOADED_SLIDES_DIR, DOC_TEMPLATES_DIR, PGY_ASSESSMENT_TEMPLATES_DIR, MATERIAL_JOB_DIR, QUESTION_IMAGES_DIR, DATA_DIR, TMP_DIR):
    d.mkdir(parents=True, exist_ok=True)

UPLOAD_PROGRESS_DIR = TMP_DIR / "upload_progress"
PREVIEW_CACHE_DIR = TMP_DIR / "preview_cache"
UPLOAD_PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
PREVIEW_CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _upload_progress_path(progress_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "", str(progress_id or ""))[:80]
    return UPLOAD_PROGRESS_DIR / f"{safe}.json" if safe else Path()

def set_upload_progress(progress_id: str, percent: float, stage: str, detail: str = "", *, current=0, total=0):
    path = _upload_progress_path(progress_id)
    if not progress_id or not str(path):
        return
    data = {
        "percent": max(0, min(100, round(float(percent or 0), 1))),
        "stage": str(stage or "處理中"),
        "detail": str(detail or ""),
        "current": int(current or 0),
        "total": int(total or 0),
        "updatedAt": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    tmp = path.with_suffix('.tmp')
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        tmp.replace(path)
    except Exception:
        pass

def clear_upload_progress(progress_id: str):
    path = _upload_progress_path(progress_id)
    try:
        if path and path.exists(): path.unlink()
    except Exception:
        pass

# 如果 soffice 不在系統 PATH 中，可用環境變數指定完整路徑，例如：
#   set SOFFICE_PATH=C:\Program Files\LibreOffice\program\soffice.exe   (Windows)
#   export SOFFICE_PATH=/usr/bin/soffice                                 (Linux)
SOFFICE_BIN = os.environ.get("SOFFICE_PATH", "soffice")

ALLOWED_EXT = {".pptx", ".ppt", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".odp", ".odt", ".ods", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".webm", ".mov", ".m4v", ".mp3", ".wav", ".m4a", ".ogg", ".txt", ".csv", ".srt", ".vtt", ".zip"}
OFFICE_EXT = {".pptx", ".ppt", ".doc", ".docx", ".xls", ".xlsx", ".odp", ".odt", ".ods"}
DIRECT_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
AI_IMAGE_EXT = DIRECT_IMAGE_EXT
AI_VIDEO_EXT = {".mp4", ".webm", ".mov", ".m4v"}
AI_AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg"}
AI_SUBTITLE_EXT = {".srt", ".vtt"}
# V5.3：上傳仍先由 Flask/Render 接收並處理，再送到 Google Drive 或 R2。
# MAX_UPLOAD_MB 是網站單次上傳限制，不是 Google Drive/R2 的總容量。大型影音仍可能受 Render/HTTP 連線限制。
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "250"))
# V5.6.1：教材頁面預設改用 WebP，降低 MEGA / Object Storage 佔用；缺少 Pillow 時自動回退 PNG。
MATERIAL_SLIDE_FORMAT = os.environ.get("MATERIAL_SLIDE_FORMAT", "webp").strip().lower()
if MATERIAL_SLIDE_FORMAT not in {"webp", "png"}:
    MATERIAL_SLIDE_FORMAT = "webp"
MATERIAL_WEBP_QUALITY = max(70, min(96, int(os.environ.get("MATERIAL_WEBP_QUALITY", "88"))))
# V5.6.2：MEGA 新教材優先改為「單一預覽 PDF」，避免每頁一張圖片造成大量上傳/讀取請求。
MATERIAL_SINGLE_PREVIEW = os.environ.get("MATERIAL_SINGLE_PREVIEW", "true").strip().lower() not in {"0","false","no","off"}
MATERIAL_PREVIEW_OPTIMIZE = os.environ.get("MATERIAL_PREVIEW_OPTIMIZE", "true").strip().lower() not in {"0","false","no","off"}
MATERIAL_PREVIEW_CACHE_MB = max(64, min(2048, int(os.environ.get("MATERIAL_PREVIEW_CACHE_MB", "512"))))
MATERIAL_PREVIEW_CACHE_TTL_SECONDS = max(300, min(86400, int(os.environ.get("MATERIAL_PREVIEW_CACHE_TTL_SECONDS", "21600"))))
# V5.7.0：大型教材先完成 HTTP 接收，再交由資料庫佇列背景轉檔／上雲。
MATERIAL_BACKGROUND_JOBS = os.environ.get("MATERIAL_BACKGROUND_JOBS", "true").strip().lower() not in {"0","false","no","off"}
MATERIAL_JOB_MAX_ATTEMPTS = max(1, min(8, int(os.environ.get("MATERIAL_JOB_MAX_ATTEMPTS", "3"))))
MATERIAL_JOB_STALE_SECONDS = max(300, min(21600, int(os.environ.get("MATERIAL_JOB_STALE_SECONDS", "1800"))))
MATERIAL_JOB_RETENTION_HOURS = max(6, min(720, int(os.environ.get("MATERIAL_JOB_RETENTION_HOURS", "72"))))
MATERIAL_JOB_POLL_SECONDS = max(1, min(30, int(os.environ.get("MATERIAL_JOB_POLL_SECONDS", "2"))))
MATERIAL_PDF_LINEARIZE = os.environ.get("MATERIAL_PDF_LINEARIZE", "true").strip().lower() not in {"0","false","no","off"}
TEACHING_USAGE_NOTICE = "教學專用・不得轉發、轉載、販售"
MAX_PGY_TEMPLATE_MB = max(1, min(50, int(os.environ.get("MAX_PGY_TEMPLATE_MB", "20"))))
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

# V5.3.16 教材雲端儲存：官方 MEGAcmd 為主；Google Drive / OCI / R2 僅保留舊資料相容。
# MATERIAL_STORAGE_BACKEND 可設：mega / gdrive / oci / r2 / local / auto。
# auto 優先 MEGA；正式 Render 建議明確設為 mega。
MATERIAL_STORAGE_BACKEND = os.environ.get("MATERIAL_STORAGE_BACKEND", "auto").strip().lower() or "auto"
# V5.3.21：可選的容量滿載備援。預設關閉；若啟用 gdrive，必須使用另一個正常可登入的 Google OAuth 帳號。
STORAGE_FALLBACK_BACKEND = os.environ.get("STORAGE_FALLBACK_BACKEND", "").strip().lower()
STORAGE_FAILOVER_ON_FULL = os.environ.get("STORAGE_FAILOVER_ON_FULL", "false").strip().lower() in {"1","true","yes","on"}

# Google Drive：使用「使用者 OAuth refresh token」而不是 Service Account，
# 這樣檔案會計入該 Google 帳號的 My Drive 空間（適合使用個人帳號免費容量）。
GDRIVE_CLIENT_ID = os.environ.get("GDRIVE_CLIENT_ID", "").strip()
GDRIVE_CLIENT_SECRET = os.environ.get("GDRIVE_CLIENT_SECRET", "").strip()
GDRIVE_REFRESH_TOKEN = os.environ.get("GDRIVE_REFRESH_TOKEN", "").strip()
GDRIVE_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID", "").strip()
GDRIVE_TOKEN_URI = os.environ.get("GDRIVE_TOKEN_URI", "https://oauth2.googleapis.com/token").strip()
GDRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
GDRIVE_CHUNK_MB = max(1, min(64, int(os.environ.get("GDRIVE_CHUNK_MB", "8"))))

# Cloudflare R2 保留為可選備援/舊資料相容。
R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "").strip()
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "").strip()
R2_PRESIGN_SECONDS = max(60, min(604800, int(os.environ.get("R2_PRESIGN_SECONDS", "3600"))))

# V5.3.14：Oracle Cloud Object Storage Always Free（S3 相容 API）。
# FREE_ONLY_MODE=true 時，網站會在接近免費容量上限前拒絕新上傳，避免意外超額。
OCI_NAMESPACE = os.environ.get("OCI_NAMESPACE", "").strip()
OCI_REGION = os.environ.get("OCI_REGION", "").strip()
OCI_ACCESS_KEY_ID = os.environ.get("OCI_ACCESS_KEY_ID", "").strip()
OCI_SECRET_ACCESS_KEY = os.environ.get("OCI_SECRET_ACCESS_KEY", "").strip()
OCI_BUCKET_NAME = os.environ.get("OCI_BUCKET_NAME", "smh-teaching-materials").strip()
OCI_PRESIGN_SECONDS = max(60, min(604800, int(os.environ.get("OCI_PRESIGN_SECONDS", "3600"))))
OCI_FREE_LIMIT_GB = max(1.0, min(20.0, float(os.environ.get("OCI_FREE_LIMIT_GB", "19.5"))))
FREE_ONLY_MODE = os.environ.get("FREE_ONLY_MODE", "true").strip().lower() not in {"0","false","no","off"}

# V5.3.16：官方 MEGAcmd 優先教材儲存。
# Render 只保存登入環境變數，MEGAcmd 的本地 session/cache 放在暫存 HOME。
MEGA_EMAIL = os.environ.get("MEGA_EMAIL", "").strip()
MEGA_PASSWORD = os.environ.get("MEGA_PASSWORD", "").strip()
MEGA_ROOT_FOLDER = os.environ.get("MEGA_ROOT_FOLDER", "smh-teaching-materials").strip().strip("/") or "smh-teaching-materials"
MEGA_STORAGE_LIMIT_GB = max(1.0, min(100.0, float(os.environ.get("MEGA_STORAGE_LIMIT_GB", "18.0"))))
MEGA_SESSION_CACHE_SECONDS = max(60, min(86400, int(os.environ.get("MEGA_SESSION_CACHE_SECONDS", "1800"))))
# Use the operating system's temporary directory by default.  The former
# hard-coded /tmp path resolves to C:\\tmp on Windows and prevented the
# application from starting during local development.
_DEFAULT_MEGACMD_HOME = str(Path(tempfile.gettempdir()) / "megacmd-home")
MEGACMD_HOME = os.environ.get("MEGACMD_HOME", _DEFAULT_MEGACMD_HOME).strip() or _DEFAULT_MEGACMD_HOME
MEGACMD_TIMEOUT_SECONDS = max(30, min(1800, int(os.environ.get("MEGACMD_TIMEOUT_SECONDS", "300"))))
Path(MEGACMD_HOME).mkdir(parents=True, exist_ok=True)
_MEGA_AUTH_CACHE = {"ok": False, "at": 0.0}
_MEGA_LOCK = threading.RLock()
# V5.3.19：後台儲存狀態短暫快取，避免每次開啟後台都同步執行 mega-whoami / mega-df。
STORAGE_STATUS_CACHE_SECONDS = max(5, min(300, int(os.environ.get("STORAGE_STATUS_CACHE_SECONDS", "30"))))
_STORAGE_STATUS_CACHE = {"at": 0.0, "data": None}
_STORAGE_STATUS_LOCK = threading.RLock()

# 預設管理者金鑰。正式站建議改由 Render Dashboard 環境變數 ADMIN_KEY 覆蓋，
# 不要把正式使用的金鑰提交到公開的 GitHub Repository。
ADMIN_KEY = os.environ.get("ADMIN_KEY", "").strip()

# V5.3.16 AI 智慧出題：Groq Free 優先；Gemini/OpenAI 僅保留相容性。
# FREE_ONLY_MODE=true 時不會自動切換到任何付費 provider；免費額度用完即回傳明確提示。
AI_PROVIDER = os.environ.get("AI_PROVIDER", "groq").strip().lower() or "groq"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "qwen/qwen3.6-27b").strip() or "qwen/qwen3.6-27b"
GROQ_TRANSCRIBE_MODEL = os.environ.get("GROQ_TRANSCRIBE_MODEL", "whisper-large-v3-turbo").strip() or "whisper-large-v3-turbo"
AI_CLASSIFY_TIMEOUT_SECONDS = max(3, min(30, int(os.environ.get("AI_CLASSIFY_TIMEOUT_SECONDS", "12"))))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6-luna").strip() or "gpt-5.6-luna"
AI_SOURCE_MAX_CHARS = max(5000, min(120000, int(os.environ.get("AI_SOURCE_MAX_CHARS", "50000"))))
AI_MAX_QUESTIONS = max(1, min(30, int(os.environ.get("AI_MAX_QUESTIONS", "15"))))
AI_MEDIA_MAX_MB = max(10, min(2000, int(os.environ.get("AI_MEDIA_MAX_MB", "300"))))
AI_MAX_MATERIALS = max(1, min(8, int(os.environ.get("AI_MAX_MATERIALS", "4"))))
AI_VIDEO_FRAME_COUNT = max(1, min(5, int(os.environ.get("AI_VIDEO_FRAME_COUNT", "3"))))

SQLITE_DB = DATA_DIR / "exam_records.db"

# ---------------------------------------------------------------------------
# V5.3.16 雲端教材儲存層：官方 MEGAcmd 優先；Google Drive / OCI / R2 / 本機相容
# ---------------------------------------------------------------------------
def r2_is_configured():
    return bool(R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY and R2_BUCKET_NAME and boto3 is not None)


def gdrive_is_configured():
    return bool(
        GDRIVE_CLIENT_ID and GDRIVE_CLIENT_SECRET and GDRIVE_REFRESH_TOKEN and GDRIVE_FOLDER_ID
        and GoogleCredentials is not None and AuthorizedSession is not None
        and google_build is not None and MediaFileUpload is not None
    )


def active_material_backend():
    mode = MATERIAL_STORAGE_BACKEND
    if mode not in {"auto", "local", "r2", "gdrive", "oci", "mega"}:
        mode = "auto"
    if mode == "local": return "local"
    if mode == "mega":
        if not mega_is_configured():
            raise RuntimeError("MATERIAL_STORAGE_BACKEND=mega，但 MEGA_EMAIL / MEGA_PASSWORD 未設定，或容器內找不到官方 MEGAcmd。")
        return "mega"
    if mode == "oci":
        if not oci_is_configured():
            raise RuntimeError("MATERIAL_STORAGE_BACKEND=oci，但 Oracle Object Storage 環境變數不完整。")
        return "oci"
    if mode == "gdrive":
        if not gdrive_is_configured():
            raise RuntimeError("MATERIAL_STORAGE_BACKEND=gdrive，但 Google Drive OAuth 環境變數不完整，或缺少 Google API 套件。")
        return "gdrive"
    if mode == "r2":
        if not r2_is_configured():
            raise RuntimeError("MATERIAL_STORAGE_BACKEND=r2，但 R2 環境變數不完整，或缺少 boto3。")
        return "r2"
    # V5.3.16 auto：優先官方 MEGAcmd；其餘後端僅保留既有資料相容性。
    if mega_is_configured(): return "mega"
    if oci_is_configured(): return "oci"
    if gdrive_is_configured(): return "gdrive"
    if r2_is_configured(): return "r2"
    return "local"


def resolve_material_storage_backend():
    """Backward-compatible storage resolver for PGY/template features.

    V5.3.24 introduced PGY assessment templates that referenced this helper,
    while the storage layer had already standardized on active_material_backend().
    Keep one canonical decision path so MEGA primary / Google Drive failover
    settings are interpreted consistently across the app.
    """
    return active_material_backend()


def r2_client():
    if not r2_is_configured():
        raise RuntimeError("Cloudflare R2 尚未完成設定。")
    return boto3.client(
        service_name="s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=BotoConfig(signature_version="s3v4") if BotoConfig else None,
    )


def _content_type_for(path_or_name):
    return mimetypes.guess_type(str(path_or_name))[0] or "application/octet-stream"


def r2_put_file(local_path: Path, key: str, content_type=None):
    extra = {"ContentType": content_type or _content_type_for(local_path)}
    r2_client().upload_file(str(local_path), R2_BUCKET_NAME, key, ExtraArgs=extra)


def r2_presigned_get(key: str, *, download_name=None, inline=True):
    params = {"Bucket": R2_BUCKET_NAME, "Key": key}
    # 盡量讓瀏覽器依用途以 inline / attachment 呈現；R2 支援 S3 相容的 GetObject。
    if download_name:
        safe = str(download_name).replace('"', "'").replace("\r", "").replace("\n", "")
        disposition = "inline" if inline else "attachment"
        params["ResponseContentDisposition"] = f'{disposition}; filename="{safe}"'
    return r2_client().generate_presigned_url("get_object", Params=params, ExpiresIn=R2_PRESIGN_SECONDS)


def r2_delete_prefix(prefix: str):
    if not prefix:
        return
    client = r2_client()
    token = None
    while True:
        kwargs = {"Bucket": R2_BUCKET_NAME, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        res = client.list_objects_v2(**kwargs)
        objects = [{"Key": x["Key"]} for x in res.get("Contents", [])]
        if objects:
            client.delete_objects(Bucket=R2_BUCKET_NAME, Delete={"Objects": objects, "Quiet": True})
        if not res.get("IsTruncated"):
            break
        token = res.get("NextContinuationToken")


def upload_material_tree_to_r2(material_id: str, source_path: Path, slides_dir: Path, page_count: int):
    source_key = f"materials/{material_id}/source{source_path.suffix.lower()}"
    slides_prefix = f"materials/{material_id}/slides"
    r2_put_file(source_path, source_key)
    for i in range(1, int(page_count or 0) + 1):
        img = _slide_local_path(slides_dir, i); fn = img.name
        if img.exists():
            r2_put_file(img, f"{slides_prefix}/{fn}", _slide_content_type(img))
    return source_key, slides_prefix


# ----------------------------- MEGA storage (official MEGAcmd) -----------------------------
def _megacmd_env():
    env = os.environ.copy()
    env["HOME"] = MEGACMD_HOME
    return env


def _mega_run(args, *, check=True, timeout=None):
    """執行官方 mega-* 指令。不得使用 shell，避免路徑/密碼被 shell 重新解讀。"""
    cmd = [str(x) for x in args]
    try:
        cp = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=_megacmd_env(),
            timeout=timeout or MEGACMD_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("找不到官方 MEGAcmd 指令。請確認 Dockerfile 已安裝 megacmd。") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"MEGAcmd 執行逾時：{' '.join(cmd[:1])}") from exc
    if check and cp.returncode != 0:
        detail = (cp.stderr or cp.stdout or "MEGAcmd command failed").strip()
        if len(detail) > 600:
            detail = detail[-600:]
        raise RuntimeError(f"MEGAcmd 執行失敗 ({Path(cmd[0]).name})：{detail}")
    return cp


def _mega_ensure_dir(remote_path: str):
    """Ensure a MEGA folder exists without treating "already exists" as an error.

    Some MEGAcmd builds return a non-zero status for ``mega-mkdir -p`` when the
    target folder already exists.  Folder creation is therefore made idempotent:
    an existing directory is a successful result, while genuine MEGA errors are
    still raised.
    """
    _mega_login_if_needed()
    remote_path = str(remote_path or '').strip()
    if not remote_path:
        raise RuntimeError("MEGA 資料夾路徑不可為空。")
    cp = _mega_run(["mega-mkdir", "-p", remote_path], check=False, timeout=60)
    if cp.returncode == 0:
        return remote_path
    detail = ((cp.stderr or '') + '\n' + (cp.stdout or '')).strip()
    normalized = detail.lower().replace(' ', '')
    tolerated = (
        'folderalreadyexists' in normalized
        or 'alreadyexists' in normalized
        or 'eexist' in normalized
    )
    if tolerated:
        return remote_path
    if len(detail) > 600:
        detail = detail[-600:]
    raise RuntimeError(f"MEGA 建立資料夾失敗：{detail or 'unknown error'}")


def mega_is_configured():
    return bool(MEGA_EMAIL and MEGA_PASSWORD and shutil.which("mega-whoami") and shutil.which("mega-put"))


def _mega_login_if_needed(force=False):
    if not mega_is_configured():
        raise RuntimeError("MEGA 尚未完成設定。請設定 MEGA_EMAIL、MEGA_PASSWORD，並確認官方 MEGAcmd 已安裝。")
    now = time.time()
    with _MEGA_LOCK:
        if (not force) and _MEGA_AUTH_CACHE.get("ok") and now - float(_MEGA_AUTH_CACHE.get("at", 0) or 0) < MEGA_SESSION_CACHE_SECONDS:
            probe = _mega_run(["mega-whoami"], check=False, timeout=30)
            if probe.returncode == 0:
                return
        probe = _mega_run(["mega-whoami"], check=False, timeout=30)
        if probe.returncode != 0:
            # 殘留 session 可能屬於舊帳號，先安全登出再登入。
            _mega_run(["mega-logout"], check=False, timeout=30)
            login = _mega_run(["mega-login", MEGA_EMAIL, MEGA_PASSWORD], check=False, timeout=120)
            if login.returncode != 0:
                detail = (login.stderr or login.stdout or "login failed").strip()
                raise RuntimeError(f"MEGA 登入失敗：{detail[-600:]}")
        verify = _mega_run(["mega-whoami"], check=False, timeout=30)
        if verify.returncode != 0:
            raise RuntimeError("MEGA 登入後仍無法驗證帳號 session。")
        _MEGA_AUTH_CACHE.update({"ok": True, "at": now})


def _mega_remote_join(*parts):
    cleaned = []
    for part in parts:
        text = str(part or "").replace("\\", "/").strip("/")
        if text:
            cleaned.append(text)
    return "/" + "/".join(cleaned)


def _mega_root_id():
    # 保留舊函式名稱，實際回傳遠端路徑，讓既有呼叫不必大改。
    _mega_login_if_needed()
    root = _mega_remote_join(MEGA_ROOT_FOLDER)
    _mega_ensure_dir(root)
    return root


def mega_storage_space():
    _mega_login_if_needed()
    cp = _mega_run(["mega-df"], timeout=60)
    # mega-df 不加 -h 時，USED STORAGE 行以 bytes 輸出。
    m = re.search(r"USED STORAGE:\s*([0-9]+)\s+[^\n]*?of\s+([0-9]+)", cp.stdout or "", re.I)
    if not m:
        # 部分版本會加千分位，做較寬鬆的 fallback。
        line = next((ln for ln in (cp.stdout or "").splitlines() if "USED STORAGE:" in ln.upper()), "")
        nums = [int(x.replace(",", "")) for x in re.findall(r"[0-9][0-9,]*", line)]
        if len(nums) >= 2:
            return {"used": nums[0], "total": nums[-1]}
        raise RuntimeError("無法解析 MEGAcmd mega-df 的容量資訊。")
    return {"used": int(m.group(1)), "total": int(m.group(2))}


def _mega_free_guard(extra_bytes=0):
    if not FREE_ONLY_MODE:
        return
    info = mega_storage_space(); used = info["used"]; total = info["total"]
    configured = int(MEGA_STORAGE_LIMIT_GB * 1024**3)
    account_cap = int(total * 0.98) if total else configured
    limit = min(configured, account_cap)
    if used + int(extra_bytes or 0) > limit:
        raise RuntimeError(
            f"免費模式已鎖定：MEGA 已使用約 {used/1024**3:.2f}GB；"
            f"加入此檔會超過網站硬上限 {limit/1024**3:.2f}GB。請先刪除舊教材。"
        )


def _mega_upload_file(local_path: Path, folder_id: str, remote_name: str):
    _mega_login_if_needed()
    folder = str(folder_id)
    _mega_ensure_dir(folder)
    # 為避免同名版本累積，先刪除同一路徑舊檔，再上傳。
    remote_path = _mega_remote_join(folder, remote_name)
    _mega_run(["mega-rm", "-f", remote_path], check=False, timeout=60)
    _mega_run(["mega-put", "-c", str(local_path), folder], timeout=max(MEGACMD_TIMEOUT_SECONDS, 600))
    # mega-put 會保留本機檔名；若 remote_name 不同則重新命名。
    uploaded = _mega_remote_join(folder, local_path.name)
    if local_path.name != remote_name:
        _mega_run(["mega-mv", uploaded, remote_path], timeout=60)
    return remote_path


def mega_download_file(file_id: str, target: Path):
    _mega_login_if_needed()
    target.parent.mkdir(parents=True, exist_ok=True)
    # mega-get 的 localpath 使用目錄時會保留遠端檔名，因此先下載到暫存目錄再改名。
    tempdir = target.parent / f".mega-get-{uuid.uuid4().hex[:8]}"
    tempdir.mkdir(parents=True, exist_ok=True)
    try:
        _mega_run(["mega-get", str(file_id), str(tempdir)], timeout=max(MEGACMD_TIMEOUT_SECONDS, 600))
        files = [x for x in tempdir.iterdir() if x.is_file()]
        if not files:
            raise RuntimeError(f"MEGA 下載完成但找不到檔案：{file_id}")
        shutil.move(str(files[0]), str(target))
    finally:
        shutil.rmtree(tempdir, ignore_errors=True)
    return target


def mega_destroy(file_id: str):
    if not file_id:
        return
    try:
        _mega_login_if_needed()
        _mega_run(["mega-rm", "-r", "-f", str(file_id)], check=False, timeout=120)
    except Exception:
        pass


def upload_material_tree_to_mega(material_id: str, source_path: Path, slides_dir: Path, page_count: int, progress_id: str = ""):
    total = source_path.stat().st_size + sum(x.stat().st_size for x in slides_dir.glob("slide-*.*"))
    _mega_free_guard(total)
    root = _mega_root_id()
    folder_path = _mega_remote_join(root, material_id)
    _mega_ensure_dir(folder_path)
    slide_files = {}
    total_items = 1 + int(page_count or 0)
    try:
        if progress_id:
            set_upload_progress(progress_id, 54, "上傳雲端教材", "正在上傳原始教材到 MEGA", current=0, total=total_items)
        source_remote = _mega_upload_file(source_path, folder_path, f"source{source_path.suffix.lower()}")
        if progress_id:
            set_upload_progress(progress_id, 60, "原始教材已上傳", f"開始上傳教材頁面，共 {int(page_count or 0)} 張", current=1, total=total_items)
        for i in range(1, int(page_count or 0) + 1):
            fp = _slide_local_path(slides_dir, i); fn = fp.name
            if fp.exists():
                slide_files[fn] = _mega_upload_file(fp, folder_path, fn)
            if progress_id:
                pct = 60 + (i / max(1, int(page_count or 0))) * 30
                set_upload_progress(progress_id, pct, "上傳教材頁面", f"MEGA：第 {i} / {int(page_count or 0)} 張", current=i+1, total=total_items)
        meta = {"folderId": folder_path, "sourceFileId": source_remote, "slideFiles": slide_files, "adapter": "megacmd", "slideFormat": _slide_format(slides_dir, page_count)}
        return source_remote, folder_path, meta
    except Exception:
        mega_destroy(folder_path)
        raise


def upload_material_preview_to_mega(material_id: str, source_path: Path, preview_path: Path, page_count: int, progress_id: str = ""):
    """V5.6.2：只上傳原始檔 + 單一 preview.pdf，避免逐頁 mega-put。"""
    total = source_path.stat().st_size + (preview_path.stat().st_size if preview_path.exists() else 0)
    _mega_free_guard(total)
    root = _mega_root_id()
    folder_path = _mega_remote_join(root, material_id)
    _mega_ensure_dir(folder_path)
    source_name = f"source{source_path.suffix.lower()}"
    preview_name = "preview.pdf"
    try:
        if progress_id:
            set_upload_progress(progress_id, 54, "上傳雲端教材", "MEGA：一次傳送原始檔與單一預覽檔，避免逐頁上傳", current=0, total=2)
        # 同一路徑採取覆寫語意，避免舊版本累積。
        for remote_name in (source_name, preview_name):
            _mega_run(["mega-rm", "-f", _mega_remote_join(folder_path, remote_name)], check=False, timeout=60)
        # source_path 本身已命名 source.ext；preview_path 命名 preview.pdf，可一次 mega-put。
        _mega_run(["mega-put", "-c", str(source_path), str(preview_path), folder_path], timeout=max(MEGACMD_TIMEOUT_SECONDS, 900))
        source_remote = _mega_remote_join(folder_path, source_path.name)
        preview_remote = _mega_remote_join(folder_path, preview_path.name)
        if source_path.name != source_name:
            _mega_run(["mega-mv", source_remote, _mega_remote_join(folder_path, source_name)], timeout=60)
            source_remote = _mega_remote_join(folder_path, source_name)
        if preview_path.name != preview_name:
            _mega_run(["mega-mv", preview_remote, _mega_remote_join(folder_path, preview_name)], timeout=60)
            preview_remote = _mega_remote_join(folder_path, preview_name)
        if progress_id:
            set_upload_progress(progress_id, 90, "MEGA 上傳完成", "原始教材 + preview.pdf 已完成；不需要逐頁上傳圖片", current=2, total=2)
        meta = {
            "folderId": folder_path,
            "sourceFileId": source_remote,
            "previewFileId": preview_remote,
            "previewFilename": preview_name,
            "previewMode": "single_pdf",
            "previewBytes": preview_path.stat().st_size if preview_path.exists() else 0,
            "pageCount": int(page_count or 0),
            "adapter": "megacmd",
            "slideFormat": "pdf",
            "cloudObjectCount": 2,
            "uploadStrategy": "single_preview",
        }
        return source_remote, folder_path, meta
    except Exception:
        mega_destroy(folder_path)
        raise


def _preview_cache_cleanup(protect: Path = None):
    """限制 Render 暫存預覽總量；只清除過期或最舊快取，不碰 MEGA 正式檔。"""
    try:
        now = time.time()
        files = [p for p in PREVIEW_CACHE_DIR.glob("*.pdf") if p.is_file()]
        protect_resolved = protect.resolve() if protect else None
        for p in list(files):
            if protect_resolved and p.resolve() == protect_resolved:
                continue
            if now - p.stat().st_mtime > MATERIAL_PREVIEW_CACHE_TTL_SECONDS:
                try: p.unlink()
                except OSError: pass
        files = [p for p in PREVIEW_CACHE_DIR.glob("*.pdf") if p.is_file()]
        limit = MATERIAL_PREVIEW_CACHE_MB * 1024 * 1024
        total = sum(p.stat().st_size for p in files)
        if total <= limit:
            return
        for p in sorted(files, key=lambda x: x.stat().st_mtime):
            if total <= limit: break
            if protect_resolved and p.resolve() == protect_resolved:
                continue
            try:
                size = p.stat().st_size; p.unlink(); total -= size
            except OSError:
                pass
    except Exception:
        pass


_PREVIEW_CACHE_LOCKS = {}
_PREVIEW_CACHE_LOCKS_GUARD = threading.Lock()

def _preview_cache_lock(cache_name: str):
    with _PREVIEW_CACHE_LOCKS_GUARD:
        lock = _PREVIEW_CACHE_LOCKS.get(cache_name)
        if lock is None:
            lock = threading.RLock()
            _PREVIEW_CACHE_LOCKS[cache_name] = lock
        return lock

def _mega_cached_preview(entry):
    meta = entry.get("storageMeta") or {}
    preview_id = meta.get("previewFileId", "")
    if not preview_id:
        raise RuntimeError("MEGA 教材缺少單一預覽檔路徑。")
    cache_name = re.sub(r"[^A-Za-z0-9_-]", "_", str(entry.get("id") or "material")) + ".pdf"
    target = PREVIEW_CACHE_DIR / cache_name
    # V5.7：不同教材可同時暖快取；只有同一份 preview.pdf 互斥，避免全站被單一大檔拖住。
    with _preview_cache_lock(cache_name):
        valid = target.exists() and target.stat().st_size > 0 and (time.time() - target.stat().st_mtime) < MATERIAL_PREVIEW_CACHE_TTL_SECONDS
        if not valid:
            tmp = target.with_suffix(".part")
            try:
                if tmp.exists(): tmp.unlink()
                mega_download_file(preview_id, tmp)
                os.replace(tmp, target)
            finally:
                if tmp.exists():
                    try: tmp.unlink()
                    except OSError: pass
        try: os.utime(target, None)
        except OSError: pass
        _preview_cache_cleanup(protect=target)
    return target


def _mega_send_file(file_id: str, filename: str, inline=True):
    temp_root = TMP_DIR / f"mega-read-{uuid.uuid4().hex[:10]}"; temp_root.mkdir(parents=True, exist_ok=True)
    target = temp_root / (Path(filename).name or "file.bin")
    try:
        mega_download_file(file_id, target)
    except Exception:
        shutil.rmtree(temp_root, ignore_errors=True); raise
    resp = send_file(target, as_attachment=not inline, download_name=filename, conditional=True)
    resp.call_on_close(lambda: shutil.rmtree(temp_root, ignore_errors=True))
    return resp


def _download_material_from_mega(entry, source: Path, slides: Path):
    meta = entry.get("storageMeta") or {}
    source_id = entry.get("storageKey") or meta.get("sourceFileId", "")
    if not source_id:
        raise RuntimeError("MEGA 教材缺少原始檔路徑。")
    mega_download_file(source_id, source)
    slide_map = meta.get("slideFiles") or {}
    slide_fmt=str(entry.get("slideFormat") or meta.get("slideFormat") or "png").lower()
    for i in range(1, int(entry.get("pageCount", 0) or 0) + 1):
        fn = f"slide-{i:02d}.{slide_fmt}"; fid = slide_map.get(fn, "")
        if fid:
            mega_download_file(fid, slides / fn)

# ----------------------------- Oracle OCI ------------------------------
def oci_is_configured():
    return bool(OCI_NAMESPACE and OCI_REGION and OCI_ACCESS_KEY_ID and OCI_SECRET_ACCESS_KEY and OCI_BUCKET_NAME and boto3 is not None)

def oci_client():
    if not oci_is_configured():
        raise RuntimeError("Oracle Object Storage 尚未完成設定。")
    endpoint = f"https://{OCI_NAMESPACE}.compat.objectstorage.{OCI_REGION}.oci.customer-oci.com"
    return boto3.client(
        service_name="s3", endpoint_url=endpoint,
        aws_access_key_id=OCI_ACCESS_KEY_ID, aws_secret_access_key=OCI_SECRET_ACCESS_KEY,
        region_name=OCI_REGION,
        config=BotoConfig(signature_version="s3v4", s3={"addressing_style":"path"}) if BotoConfig else None,
    )

def oci_bucket_usage_bytes():
    client = oci_client(); total = 0; token = None
    while True:
        kw = {"Bucket": OCI_BUCKET_NAME}
        if token: kw["ContinuationToken"] = token
        res = client.list_objects_v2(**kw)
        total += sum(int(x.get("Size",0) or 0) for x in res.get("Contents", []))
        if not res.get("IsTruncated"): break
        token = res.get("NextContinuationToken")
    return total

def _oci_free_guard(extra_bytes=0):
    if not FREE_ONLY_MODE: return
    limit = int(OCI_FREE_LIMIT_GB * 1024**3)
    used = oci_bucket_usage_bytes()
    if used + int(extra_bytes or 0) > limit:
        raise RuntimeError(f"免費模式已鎖定：Oracle 教材空間約 {used/1024**3:.2f}GB，新增此檔會超過網站設定的 {OCI_FREE_LIMIT_GB:.1f}GB 上限。請先刪除舊教材。")

def oci_put_file(local_path: Path, key: str, content_type=None):
    _oci_free_guard(Path(local_path).stat().st_size)
    extra = {"ContentType": content_type or _content_type_for(local_path)}
    oci_client().upload_file(str(local_path), OCI_BUCKET_NAME, key, ExtraArgs=extra)

def oci_presigned_get(key: str, *, download_name=None, inline=True):
    params = {"Bucket": OCI_BUCKET_NAME, "Key": key}
    if download_name:
        safe = str(download_name).replace('"', "'").replace("\r","").replace("\n","")
        params["ResponseContentDisposition"] = f'{"inline" if inline else "attachment"}; filename="{safe}"'
    return oci_client().generate_presigned_url("get_object", Params=params, ExpiresIn=OCI_PRESIGN_SECONDS)

def oci_delete_prefix(prefix: str):
    if not prefix: return
    client = oci_client(); token = None
    while True:
        kw={"Bucket":OCI_BUCKET_NAME,"Prefix":prefix}
        if token: kw["ContinuationToken"]=token
        res=client.list_objects_v2(**kw)
        objs=[{"Key":x["Key"]} for x in res.get("Contents",[])]
        if objs: client.delete_objects(Bucket=OCI_BUCKET_NAME, Delete={"Objects":objs,"Quiet":True})
        if not res.get("IsTruncated"): break
        token=res.get("NextContinuationToken")

def upload_material_tree_to_oci(material_id: str, source_path: Path, slides_dir: Path, page_count: int):
    # 一次估算原始檔＋已轉出的頁面大小，先做免費硬上限檢查。
    total = source_path.stat().st_size + sum(_slide_local_path(slides_dir,i).stat().st_size for i in range(1,int(page_count or 0)+1) if _slide_local_path(slides_dir,i).exists())
    _oci_free_guard(total)
    source_key=f"materials/{material_id}/source{source_path.suffix.lower()}"; slides_prefix=f"materials/{material_id}/slides"
    extra={"ContentType":_content_type_for(source_path)}
    oci_client().upload_file(str(source_path), OCI_BUCKET_NAME, source_key, ExtraArgs=extra)
    for i in range(1,int(page_count or 0)+1):
        img=_slide_local_path(slides_dir,i); fn=img.name
        if img.exists(): oci_client().upload_file(str(img), OCI_BUCKET_NAME, f"{slides_prefix}/{fn}", ExtraArgs={"ContentType":_slide_content_type(img)})
    return source_key, slides_prefix


# ----------------------------- Google Drive ------------------------------
def gdrive_credentials():
    if not gdrive_is_configured():
        raise RuntimeError("Google Drive 尚未完成 OAuth 設定。")
    return GoogleCredentials(
        token=None,
        refresh_token=GDRIVE_REFRESH_TOKEN,
        token_uri=GDRIVE_TOKEN_URI,
        client_id=GDRIVE_CLIENT_ID,
        client_secret=GDRIVE_CLIENT_SECRET,
        scopes=[GDRIVE_SCOPE],
    )


def gdrive_service():
    return google_build("drive", "v3", credentials=gdrive_credentials(), cache_discovery=False)


def gdrive_check():
    info = gdrive_service().files().get(
        fileId=GDRIVE_FOLDER_ID, fields="id,name,mimeType,trashed"
    ).execute()
    if info.get("trashed"):
        raise RuntimeError("Google Drive 教材根資料夾目前在垃圾桶中。")
    if info.get("mimeType") != "application/vnd.google-apps.folder":
        raise RuntimeError("GDRIVE_FOLDER_ID 不是 Google Drive 資料夾。")
    return info


def gdrive_create_folder(name: str, parent_id: str, app_properties=None):
    body = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    if app_properties:
        body["appProperties"] = app_properties
    return gdrive_service().files().create(body=body, fields="id,name").execute()["id"]


def gdrive_upload_file(local_path: Path, name: str, parent_id: str, app_properties=None):
    body = {"name": name, "parents": [parent_id]}
    if app_properties:
        body["appProperties"] = app_properties
    media = MediaFileUpload(
        str(local_path),
        mimetype=_content_type_for(local_path),
        chunksize=GDRIVE_CHUNK_MB * 1024 * 1024,
        resumable=True,
    )
    return gdrive_service().files().create(
        body=body, media_body=media, fields="id,name,size,mimeType"
    ).execute()


def gdrive_delete_file(file_id: str):
    if file_id:
        gdrive_service().files().delete(fileId=file_id).execute()


def upload_material_tree_to_gdrive(material_id: str, source_path: Path, slides_dir: Path, page_count: int, original_name=None):
    material_folder_id = ""
    try:
        material_folder_id = gdrive_create_folder(
            material_id, GDRIVE_FOLDER_ID, {"smh_kind": "material", "smh_material_id": material_id}
        )
        source_name = Path(original_name or source_path.name).name
        src = gdrive_upload_file(
            source_path, source_name, material_folder_id,
            {"smh_kind": "source", "smh_material_id": material_id}
        )
        slides_folder_id = ""
        slide_files = {}
        if int(page_count or 0) > 0:
            slides_folder_id = gdrive_create_folder(
                "slides", material_folder_id, {"smh_kind": "slides", "smh_material_id": material_id}
            )
            for i in range(1, int(page_count or 0) + 1):
                img = _slide_local_path(slides_dir, i)
                fn = img.name
                if img.exists():
                    uploaded = gdrive_upload_file(
                        img, fn, slides_folder_id,
                        {"smh_kind": "slide", "smh_material_id": material_id, "smh_page": str(i)}
                    )
                    slide_files[fn] = uploaded["id"]
        meta = {
            "materialFolderId": material_folder_id,
            "sourceFileId": src["id"],
            "slidesFolderId": slides_folder_id,
            "slideFiles": slide_files,
            "slideFormat": _slide_format(slides_dir, page_count),
        }
        return src["id"], slides_folder_id, meta
    except Exception:
        if material_folder_id:
            try:
                gdrive_delete_file(material_folder_id)
            except Exception:
                pass
        raise


def gdrive_find_file_in_folder(folder_id: str, filename: str):
    if not folder_id:
        return ""
    safe_name = str(filename).replace("\\", "\\\\").replace("'", "\\'")
    safe_parent = str(folder_id).replace("\\", "\\\\").replace("'", "\\'")
    q = f"'{safe_parent}' in parents and name = '{safe_name}' and trashed = false"
    res = gdrive_service().files().list(q=q, fields="files(id,name)", pageSize=2).execute()
    files = res.get("files", [])
    return files[0]["id"] if files else ""


def gdrive_proxy_file(file_id: str, filename: str, inline=True):
    if not file_id:
        abort(404)
    creds = gdrive_credentials()
    session = AuthorizedSession(creds)
    headers = {}
    range_header = request.headers.get("Range")
    if range_header:
        headers["Range"] = range_header
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    upstream = session.get(url, headers=headers, stream=True, timeout=90)
    if upstream.status_code not in (200, 206):
        msg = upstream.text[:500]
        upstream.close(); session.close()
        return jsonify({"error": f"Google Drive 讀取失敗（HTTP {upstream.status_code}）：{msg}"}), 502
    out_headers = {}
    for h in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges", "ETag", "Last-Modified"):
        if upstream.headers.get(h):
            out_headers[h] = upstream.headers[h]
    disposition = "inline" if inline else "attachment"
    safe = Path(filename or "download").name.replace('"', "'").replace("\r", "").replace("\n", "")
    ascii_name = safe.encode("ascii", "ignore").decode("ascii").strip() or "download"
    out_headers["Content-Disposition"] = f'{disposition}; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(safe)}'
    out_headers["Cache-Control"] = "private, max-age=300"
    resp = Response(
        stream_with_context(upstream.iter_content(chunk_size=512 * 1024)),
        status=upstream.status_code,
        headers=out_headers,
        direct_passthrough=True,
    )
    resp.call_on_close(upstream.close)
    resp.call_on_close(session.close)
    return resp


def gdrive_download_to_path(file_id: str, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    session = AuthorizedSession(gdrive_credentials())
    try:
        with session.get(
            f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media",
            stream=True, timeout=120
        ) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
    finally:
        session.close()


def gdrive_delete_material(entry):
    meta = entry.get("storageMeta") or {}
    folder_id = meta.get("materialFolderId", "")
    if folder_id:
        gdrive_delete_file(folder_id)
        return
    ids = [entry.get("storageKey", "")] + list((meta.get("slideFiles") or {}).values())
    for fid in dict.fromkeys(x for x in ids if x):
        try:
            gdrive_delete_file(fid)
        except Exception:
            pass

# ---------------------------------------------------------------------------
# 六大組別（頁面最上層分組）
# ---------------------------------------------------------------------------
GROUPS = {
    "grpBio": "1 生化組",
    "grpMicro": "2 鏡檢組",
    "grpSero": "3 血清組",
    "grpBB": "4 血庫組",
    "grpBact": "5 細菌組",
    "grpHema": "6 血液組",
    # V5.3.19：PGY 共通資源入口。沿用 group_key 欄位，讓教材、課程、考卷、進度
    # 都可以直接使用既有資料模型，不需要另開第二套資料表。
    "grpNew": "新進醫檢師專區",
    "grpPgyDocs": "PGY專用資料放置區",
}
PGY_ONLY_GROUPS = {"grpNew", "grpPgyDocs"}
DEFAULT_GROUP = "grpBio"
TRAINING_AREAS = {"internal": "內部教育訓練區", "pgy": "PGY訓練區"}
# Milestone 4: one live RBAC policy for legacy and modular code.
from teacher_app.common.auth import CANONICAL_ROLES, LEGACY_ROLE_ALIASES, ROLE_PERMISSIONS
from teacher_app.auth import service as auth_service, routes as auth_routes
import sys

# Retained pre-extraction implementation for compatibility verification.
def _legacy_normalize_role(value):
    role = str(value or "student").strip().lower()
    role = LEGACY_ROLE_ALIASES.get(role, role)
    return role if role in CANONICAL_ROLES else "student"


def normalize_role(value):
    from teacher_app.common.auth import normalize_role as canonical_normalize_role
    return canonical_normalize_role(value)

# Retained pre-extraction implementation for compatibility verification.
def _legacy_has_permission(user, permission):
    return bool(user) and permission in ROLE_PERMISSIONS.get(normalize_role(user.get("role")), set())


def has_permission(user, permission):
    from teacher_app.common.auth import has_permission as canonical_has_permission
    return canonical_has_permission(user, permission)
DEFAULT_TRAINING_AREA = "internal"

# 舊版生化四份考卷保留原 category 代碼，方便既有教材連結與成績紀錄相容；考卷本身已改為動態資料庫管理。
CATEGORY_LABELS = {
    "subA1": "1-1 一致性與法定傳染病通報",
    "subA2": "1-2 c503一般作業流程與異常訊號故障排除",
    "subA3": "1-3 Cobas b 211異常訊號故障排除與QC設定",
    "zoneB": "2 COVER C1人員考區（Sebia）",
    "": "未分類 / 一般補充教材",
}

# LibreOffice headless 同一時間只能處理一份轉檔工作，避免多人同時上傳互相衝突
conversion_lock = threading.Lock()

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "").strip() or ADMIN_KEY or "local-development-only-change-me"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
app.config["PERMANENT_SESSION_LIFETIME"] = datetime.timedelta(days=30)


@app.after_request
def set_browser_cache_policy(response):
    """Keep repeat navigation fast without caching learner or admin data."""
    path = request.path.lower()
    if path.startswith("/api/") or path in {"/", "/internal", "/pgy", "/login", "/system"}:
        response.headers["Cache-Control"] = "no-store"
    elif path.endswith((".css", ".js", ".png", ".jpg", ".jpeg", ".webp", ".svg")):
        response.headers["Cache-Control"] = "public, max-age=86400, stale-while-revalidate=604800"
    return response


# ---------------------------------------------------------------------------
# 考核成績資料庫
# ---------------------------------------------------------------------------
def _db_conn():
    """有 DATABASE_URL 時強制使用 PostgreSQL；本機未設定時才使用 SQLite。

    這樣 Render 若 PostgreSQL 暫時連線失敗，會直接顯示錯誤，避免悄悄寫進
    Render 的暫存 SQLite，造成「看起來有存檔、實際成績沒有進中央資料庫」的問題。
    """
    if DATABASE_URL:
        import psycopg
        from psycopg.rows import dict_row
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10)
        conn.autocommit = True
        return conn, "postgres"
    conn = sqlite3.connect(str(SQLITE_DB), timeout=30)
    conn.row_factory = sqlite3.Row
    # 與 Postgres 分支的 conn.autocommit = True 對齊：SQLite 預設每個
    # INSERT/UPDATE/DELETE 需要顯式 commit() 才會真正寫入，若忘記 commit
    # 又直接 close()，寫入會被靜默 rollback。isolation_level=None 讓每個
    # SQL 陳述式即時自動提交，行為與 Postgres 分支一致。
    conn.isolation_level = None
    return conn, "sqlite"



# ---------------------------------------------------------------------------
# V5.7.0 大型教材背景工作佇列（資料庫保存狀態；原始檔暫存在 MATERIAL_STORAGE）
# ---------------------------------------------------------------------------
def _utc_now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _material_job_priority(source_bytes: int) -> int:
    """小檔優先，避免一份 250MB 教材長時間堵住後面的小型教材。"""
    mb = max(0, int(source_bytes or 0)) / 1024 / 1024
    if mb <= 25:
        return 100
    if mb <= 100:
        return 70
    return 40


def init_material_jobs_db():
    conn, kind = _db_conn()
    try:
        if kind == "postgres":
            conn.execute("""
                CREATE TABLE IF NOT EXISTS material_jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'queued',
                    priority INTEGER NOT NULL DEFAULT 50,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    available_at TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT '',
                    finished_at TEXT NOT NULL DEFAULT '',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    stage TEXT NOT NULL DEFAULT '等待處理',
                    detail TEXT NOT NULL DEFAULT '',
                    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    staging_path TEXT NOT NULL,
                    material_id TEXT NOT NULL DEFAULT '',
                    source_sha256 TEXT NOT NULL DEFAULT '',
                    source_bytes BIGINT NOT NULL DEFAULT 0,
                    error TEXT NOT NULL DEFAULT '',
                    result JSONB NOT NULL DEFAULT '{}'::jsonb,
                    worker_id TEXT NOT NULL DEFAULT '',
                    cancel_requested BOOLEAN NOT NULL DEFAULT FALSE
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_material_jobs_queue ON material_jobs(status, priority DESC, created_at)")
        else:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS material_jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'queued',
                    priority INTEGER NOT NULL DEFAULT 50,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    available_at TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT '',
                    finished_at TEXT NOT NULL DEFAULT '',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    stage TEXT NOT NULL DEFAULT '等待處理',
                    detail TEXT NOT NULL DEFAULT '',
                    payload TEXT NOT NULL DEFAULT '{}',
                    staging_path TEXT NOT NULL,
                    material_id TEXT NOT NULL DEFAULT '',
                    source_sha256 TEXT NOT NULL DEFAULT '',
                    source_bytes INTEGER NOT NULL DEFAULT 0,
                    error TEXT NOT NULL DEFAULT '',
                    result TEXT NOT NULL DEFAULT '{}',
                    worker_id TEXT NOT NULL DEFAULT '',
                    cancel_requested INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_material_jobs_queue ON material_jobs(status, priority, created_at)")
    finally:
        conn.close()


def _material_job_row_to_dict(row, include_payload=False):
    if not row:
        return None
    r = dict(row)
    for key in ("payload", "result"):
        raw = r.get(key, {}) or {}
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = {}
        r[key] = raw if isinstance(raw, dict) else {}
    r["cancelRequested"] = bool(r.pop("cancel_requested", False))
    r["createdAt"] = r.pop("created_at", "")
    r["updatedAt"] = r.pop("updated_at", "")
    r["availableAt"] = r.pop("available_at", "")
    r["startedAt"] = r.pop("started_at", "")
    r["finishedAt"] = r.pop("finished_at", "")
    r["maxAttempts"] = int(r.pop("max_attempts", MATERIAL_JOB_MAX_ATTEMPTS) or MATERIAL_JOB_MAX_ATTEMPTS)
    r["materialId"] = r.pop("material_id", "") or ""
    r["sourceSha256"] = r.pop("source_sha256", "") or ""
    r["sourceBytes"] = int(r.pop("source_bytes", 0) or 0)
    r["workerId"] = r.pop("worker_id", "") or ""
    r["originalName"] = str((r.get("payload") or {}).get("originalName", "") or "")
    r["title"] = str((r.get("payload") or {}).get("title", "") or "")
    r["progress"] = 0.0
    progress_id = str(r.get("id") or "")
    pp = _upload_progress_path(progress_id)
    if pp and pp.exists():
        try:
            pd = json.loads(pp.read_text(encoding="utf-8"))
            if isinstance(pd, dict):
                r["progress"] = float(pd.get("percent", 0) or 0)
                if pd.get("stage"):
                    r["stage"] = pd.get("stage")
                if pd.get("detail"):
                    r["detail"] = pd.get("detail")
                r["progressUpdatedAt"] = pd.get("updatedAt", "")
        except Exception:
            pass
    if r.get("status") == "completed":
        r["progress"] = 100.0
    if not include_payload:
        r.pop("payload", None)
        r.pop("staging_path", None)
    else:
        r["stagingPath"] = r.pop("staging_path", "")
    return r


def create_material_job(*, job_id: str, payload: dict, staging_path: Path, source_sha256: str, source_bytes: int, material_id: str):
    now = _utc_now_iso()
    priority = _material_job_priority(source_bytes)
    conn, kind = _db_conn()
    try:
        values = (job_id, "queued", priority, now, now, now, MATERIAL_JOB_MAX_ATTEMPTS, "等待背景處理", "教材已安全接收，可離開此頁；背景工作會繼續。", json.dumps(payload, ensure_ascii=False), str(staging_path), material_id, source_sha256, int(source_bytes or 0))
        if kind == "postgres":
            conn.execute("""INSERT INTO material_jobs
                (id,status,priority,created_at,updated_at,available_at,max_attempts,stage,detail,payload,staging_path,material_id,source_sha256,source_bytes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)""", values)
        else:
            conn.execute("""INSERT INTO material_jobs
                (id,status,priority,created_at,updated_at,available_at,max_attempts,stage,detail,payload,staging_path,material_id,source_sha256,source_bytes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", values)
    finally:
        conn.close()


def get_material_job(job_id: str, include_payload=False):
    conn, kind = _db_conn(); ph = "%s" if kind == "postgres" else "?"
    try:
        row = conn.execute(f"SELECT * FROM material_jobs WHERE id={ph}", (job_id,)).fetchone()
        return _material_job_row_to_dict(row, include_payload=include_payload)
    finally:
        conn.close()


def list_material_jobs(limit=30):
    limit = max(1, min(100, int(limit or 30)))
    conn, _ = _db_conn()
    try:
        rows = conn.execute(f"SELECT * FROM material_jobs ORDER BY created_at DESC LIMIT {limit}").fetchall()
        return [_material_job_row_to_dict(r, include_payload=False) for r in rows]
    finally:
        conn.close()


def _update_material_job(job_id: str, **fields):
    allowed = {"status","updated_at","available_at","started_at","finished_at","attempts","stage","detail","material_id","error","result","worker_id","cancel_requested"}
    clean = {k:v for k,v in fields.items() if k in allowed}
    if not clean:
        return
    clean.setdefault("updated_at", _utc_now_iso())
    conn, kind = _db_conn(); ph = "%s" if kind == "postgres" else "?"
    try:
        sets=[]; vals=[]
        for key, value in clean.items():
            if key == "result":
                value = json.dumps(value or {}, ensure_ascii=False)
                sets.append(f"{key}={ph}" + ("::jsonb" if kind == "postgres" else ""))
            else:
                if key == "cancel_requested" and kind != "postgres":
                    value = int(bool(value))
                sets.append(f"{key}={ph}")
            vals.append(value)
        vals.append(job_id)
        conn.execute(f"UPDATE material_jobs SET {', '.join(sets)} WHERE id={ph}", tuple(vals))
    finally:
        conn.close()


def claim_next_material_job(worker_id: str):
    now = _utc_now_iso()
    conn, kind = _db_conn()
    try:
        if kind == "postgres":
            with conn.transaction():
                row = conn.execute("""
                    SELECT * FROM material_jobs
                    WHERE status IN ('queued','retry_wait') AND cancel_requested=FALSE AND available_at <= %s
                    ORDER BY priority DESC, created_at ASC
                    FOR UPDATE SKIP LOCKED LIMIT 1
                """, (now,)).fetchone()
                if not row:
                    return None
                attempts = int(row.get("attempts", 0) or 0) + 1
                conn.execute("UPDATE material_jobs SET status='processing', attempts=%s, started_at=%s, updated_at=%s, stage='背景處理中', detail='Worker 已取得工作', worker_id=%s WHERE id=%s", (attempts, now, now, worker_id, row["id"]))
                row = conn.execute("SELECT * FROM material_jobs WHERE id=%s", (row["id"],)).fetchone()
                return _material_job_row_to_dict(row, include_payload=True)
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("""
            SELECT * FROM material_jobs
            WHERE status IN ('queued','retry_wait') AND cancel_requested=0 AND available_at <= ?
            ORDER BY priority DESC, created_at ASC LIMIT 1
        """, (now,)).fetchone()
        if not row:
            conn.execute("COMMIT")
            return None
        attempts = int(dict(row).get("attempts", 0) or 0) + 1
        conn.execute("UPDATE material_jobs SET status='processing', attempts=?, started_at=?, updated_at=?, stage='背景處理中', detail='Worker 已取得工作', worker_id=? WHERE id=?", (attempts, now, now, worker_id, dict(row)["id"]))
        conn.execute("COMMIT")
        row = conn.execute("SELECT * FROM material_jobs WHERE id=?", (dict(row)["id"],)).fetchone()
        return _material_job_row_to_dict(row, include_payload=True)
    except Exception:
        if kind != "postgres":
            try: conn.execute("ROLLBACK")
            except Exception: pass
        raise
    finally:
        conn.close()


def recover_stale_material_jobs():
    """Worker / Render 重啟後，把超時 processing 工作放回佇列；原始檔仍在 staging 就不必重新上傳。"""
    threshold = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=MATERIAL_JOB_STALE_SECONDS)).isoformat()
    now = _utc_now_iso()
    conn, kind = _db_conn(); ph = "%s" if kind == "postgres" else "?"
    try:
        rows = conn.execute(f"SELECT id,staging_path FROM material_jobs WHERE status='processing' AND updated_at < {ph}", (threshold,)).fetchall()
        recovered = 0
        for row in rows:
            rr = dict(row)
            if Path(rr.get("staging_path") or "").exists():
                conn.execute(f"UPDATE material_jobs SET status='queued', available_at={ph}, updated_at={ph}, stage='重新排隊', detail='偵測到前次 Worker 中斷，已自動續接', worker_id='' WHERE id={ph}", (now, now, rr["id"]))
                recovered += 1
            else:
                conn.execute(f"UPDATE material_jobs SET status='failed', updated_at={ph}, finished_at={ph}, error='背景工作中斷且暫存原始檔已不存在，請重新上傳' WHERE id={ph}", (now, now, rr["id"]))
        return recovered
    finally:
        conn.close()


def cleanup_material_job_staging():
    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=MATERIAL_JOB_RETENTION_HOURS)).isoformat()
    conn, kind = _db_conn(); ph = "%s" if kind == "postgres" else "?"
    try:
        rows = conn.execute(f"SELECT id,staging_path,status FROM material_jobs WHERE updated_at < {ph} AND status IN ('completed','cancelled','failed')", (cutoff,)).fetchall()
        for row in rows:
            rr = dict(row); path = Path(rr.get("staging_path") or "")
            root = path.parent if path.name else path
            if root.exists() and MATERIAL_JOB_DIR in root.parents:
                shutil.rmtree(root, ignore_errors=True)
    finally:
        conn.close()


def init_exam_db():
    conn, kind = _db_conn()
    try:
        if kind == "postgres":
            conn.execute("""
                CREATE TABLE IF NOT EXISTS exam_records (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    name TEXT NOT NULL,
                    emp_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    evaluator_name TEXT,
                    evaluator_title TEXT,
                    quiz_title TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    correct_count INTEGER NOT NULL DEFAULT 0,
                    wrong_count INTEGER NOT NULL DEFAULT 0,
                    answers_detail JSONB NOT NULL,
                    group_key TEXT NOT NULL DEFAULT 'grpBio',
                    training_area TEXT NOT NULL DEFAULT 'internal'
                )
            """)
            try:
                conn.execute("ALTER TABLE exam_records ADD COLUMN IF NOT EXISTS group_key TEXT NOT NULL DEFAULT 'grpBio'")
                conn.execute("ALTER TABLE exam_records ADD COLUMN IF NOT EXISTS training_area TEXT NOT NULL DEFAULT 'internal'")
                conn.execute("ALTER TABLE exam_records ADD COLUMN IF NOT EXISTS publication_id TEXT NOT NULL DEFAULT ''")
                conn.execute("ALTER TABLE exam_records ADD COLUMN IF NOT EXISTS publication_hash TEXT NOT NULL DEFAULT ''")
            except Exception:
                pass
        else:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS exam_records (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    name TEXT NOT NULL,
                    emp_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    evaluator_name TEXT,
                    evaluator_title TEXT,
                    quiz_title TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    correct_count INTEGER NOT NULL DEFAULT 0,
                    wrong_count INTEGER NOT NULL DEFAULT 0,
                    answers_detail TEXT NOT NULL,
                    group_key TEXT NOT NULL DEFAULT 'grpBio',
                    training_area TEXT NOT NULL DEFAULT 'internal'
                )
            """)
            existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(exam_records)").fetchall()}
            if "group_key" not in existing_cols:
                conn.execute("ALTER TABLE exam_records ADD COLUMN group_key TEXT NOT NULL DEFAULT 'grpBio'")
            if "training_area" not in existing_cols:
                conn.execute("ALTER TABLE exam_records ADD COLUMN training_area TEXT NOT NULL DEFAULT 'internal'")
            if "publication_id" not in existing_cols:
                conn.execute("ALTER TABLE exam_records ADD COLUMN publication_id TEXT NOT NULL DEFAULT ''")
            if "publication_hash" not in existing_cols:
                conn.execute("ALTER TABLE exam_records ADD COLUMN publication_hash TEXT NOT NULL DEFAULT ''")
    finally:
        conn.close()


def _record_to_dict(row):
    r = dict(row)
    raw = r.pop("answers_detail", "[]")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = []
    r["answersDetail"] = raw
    r["timestamp"] = r.pop("created_at", "")
    r["empId"] = r.pop("emp_id", "")
    r["evaluatorName"] = r.pop("evaluator_name", "")
    r["evaluatorTitle"] = r.pop("evaluator_title", "")
    group = r.pop("group_key", "grpBio") or "grpBio"
    r["groupKey"] = group
    r["groupLabel"] = GROUPS.get(group, GROUPS["grpBio"])
    area = normalize_area(r.pop("training_area", DEFAULT_TRAINING_AREA))
    r["trainingArea"] = area
    r["trainingAreaLabel"] = TRAINING_AREAS[area]
    r["courseId"] = r.pop("course_id", "") or ""
    r["reviewStatus"] = r.pop("review_status", "completed") or "completed"
    r["reviewedAt"] = r.pop("reviewed_at", "") or ""
    r["reviewerName"] = r.pop("reviewer_name", "") or ""
    r["reviewComment"] = r.pop("review_comment", "") or ""
    r["quizCategoryId"] = r.pop("quiz_category_id", "") or ""
    r["publicationId"] = r.pop("publication_id", "") or ""
    r["publicationHash"] = r.pop("publication_hash", "") or ""
    try:
        r["passingScore"] = max(1, min(100, int(r.pop("passing_score", 80) or 80)))
    except Exception:
        r["passingScore"] = 80
    return r


def require_admin():
    supplied = request.headers.get("X-Admin-Key", "")
    if ADMIN_KEY and supplied == ADMIN_KEY:
        return None
    user = _current_user()
    if not user:
        return jsonify({"error": "請先以管理者帳號登入，或提供正確的 ADMIN_KEY。", "loginRequired": True}), 401
    if not (has_permission(user, "user.manage") or has_permission(user, "system.manage")):
        return jsonify({"error": "權限不足：此功能限教學管理者使用。"}), 403
    return None


def normalize_group(value):
    """把不合法或空白的組別代碼收斂為預設的生化組，避免髒資料。"""
    return value if value in GROUPS else DEFAULT_GROUP

def normalize_area(value):
    return value if value in TRAINING_AREAS else DEFAULT_TRAINING_AREA


init_exam_db()


def init_materials_db():
    conn, kind = _db_conn()
    try:
        if kind == "postgres":
            conn.execute("""
                CREATE TABLE IF NOT EXISTS materials (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT '',
                    group_key TEXT NOT NULL DEFAULT 'grpBio',
                    training_area TEXT NOT NULL DEFAULT 'internal',
                    folder TEXT NOT NULL,
                    page_count INTEGER NOT NULL DEFAULT 0,
                    date_added TEXT NOT NULL,
                    storage_filename TEXT NOT NULL,
                    storage_backend TEXT NOT NULL DEFAULT 'local',
                    storage_key TEXT NOT NULL DEFAULT '',
                    slides_prefix TEXT NOT NULL DEFAULT '',
                    storage_meta TEXT NOT NULL DEFAULT '{}',
                    material_type TEXT NOT NULL DEFAULT 'standard',
                    atlas_meta TEXT NOT NULL DEFAULT '{}',
                    active BOOLEAN NOT NULL DEFAULT TRUE
                )
            """)
            try:
                conn.execute("ALTER TABLE materials ADD COLUMN IF NOT EXISTS group_key TEXT NOT NULL DEFAULT 'grpBio'")
                conn.execute("ALTER TABLE materials ADD COLUMN IF NOT EXISTS training_area TEXT NOT NULL DEFAULT 'internal'")
                conn.execute("ALTER TABLE materials ADD COLUMN IF NOT EXISTS storage_backend TEXT NOT NULL DEFAULT 'local'")
                conn.execute("ALTER TABLE materials ADD COLUMN IF NOT EXISTS storage_key TEXT NOT NULL DEFAULT ''")
                conn.execute("ALTER TABLE materials ADD COLUMN IF NOT EXISTS slides_prefix TEXT NOT NULL DEFAULT ''")
                conn.execute("ALTER TABLE materials ADD COLUMN IF NOT EXISTS storage_meta TEXT NOT NULL DEFAULT '{}'")
                conn.execute("ALTER TABLE materials ADD COLUMN IF NOT EXISTS material_type TEXT NOT NULL DEFAULT 'standard'")
                conn.execute("ALTER TABLE materials ADD COLUMN IF NOT EXISTS atlas_meta TEXT NOT NULL DEFAULT '{}'")
            except Exception:
                pass
        else:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS materials (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT '',
                    group_key TEXT NOT NULL DEFAULT 'grpBio',
                    training_area TEXT NOT NULL DEFAULT 'internal',
                    folder TEXT NOT NULL,
                    page_count INTEGER NOT NULL DEFAULT 0,
                    date_added TEXT NOT NULL,
                    storage_filename TEXT NOT NULL,
                    storage_backend TEXT NOT NULL DEFAULT 'local',
                    storage_key TEXT NOT NULL DEFAULT '',
                    slides_prefix TEXT NOT NULL DEFAULT '',
                    storage_meta TEXT NOT NULL DEFAULT '{}',
                    material_type TEXT NOT NULL DEFAULT 'standard',
                    atlas_meta TEXT NOT NULL DEFAULT '{}',
                    active INTEGER NOT NULL DEFAULT 1
                )
            """)
            existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(materials)").fetchall()}
            if "group_key" not in existing_cols:
                conn.execute("ALTER TABLE materials ADD COLUMN group_key TEXT NOT NULL DEFAULT 'grpBio'")
            if "training_area" not in existing_cols:
                conn.execute("ALTER TABLE materials ADD COLUMN training_area TEXT NOT NULL DEFAULT 'internal'")
            if "storage_backend" not in existing_cols:
                conn.execute("ALTER TABLE materials ADD COLUMN storage_backend TEXT NOT NULL DEFAULT 'local'")
            if "storage_key" not in existing_cols:
                conn.execute("ALTER TABLE materials ADD COLUMN storage_key TEXT NOT NULL DEFAULT ''")
            if "slides_prefix" not in existing_cols:
                conn.execute("ALTER TABLE materials ADD COLUMN slides_prefix TEXT NOT NULL DEFAULT ''")
            if "storage_meta" not in existing_cols:
                conn.execute("ALTER TABLE materials ADD COLUMN storage_meta TEXT NOT NULL DEFAULT '{}'")
            if "material_type" not in existing_cols:
                conn.execute("ALTER TABLE materials ADD COLUMN material_type TEXT NOT NULL DEFAULT 'standard'")
            if "atlas_meta" not in existing_cols:
                conn.execute("ALTER TABLE materials ADD COLUMN atlas_meta TEXT NOT NULL DEFAULT '{}'")
    finally:
        conn.close()


def init_quiz_db():
    """所有組別的考題頁籤與題目皆使用資料庫動態管理。"""
    conn, kind = _db_conn()
    try:
        if kind == "postgres":
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quiz_categories (
                    id TEXT PRIMARY KEY,
                    group_key TEXT NOT NULL DEFAULT 'grpBio',
                    training_area TEXT NOT NULL DEFAULT 'internal',
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    date_added TEXT NOT NULL,
                    active BOOLEAN NOT NULL DEFAULT TRUE
                )
            """)
            conn.execute("ALTER TABLE quiz_categories ADD COLUMN IF NOT EXISTS training_area TEXT NOT NULL DEFAULT 'internal'")
            conn.execute("ALTER TABLE quiz_categories ADD COLUMN IF NOT EXISTS blind_mode BOOLEAN NOT NULL DEFAULT FALSE")
            # V5.4.0：考卷層級設定。draw_count=0 代表使用全部啟用題目。
            conn.execute("ALTER TABLE quiz_categories ADD COLUMN IF NOT EXISTS draw_count INTEGER NOT NULL DEFAULT 0")
            conn.execute("ALTER TABLE quiz_categories ADD COLUMN IF NOT EXISTS passing_score INTEGER NOT NULL DEFAULT 80")
            conn.execute("ALTER TABLE quiz_categories ADD COLUMN IF NOT EXISTS audience TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE quiz_categories ADD COLUMN IF NOT EXISTS draw_rules JSONB NOT NULL DEFAULT '{}'::jsonb")
            # V5.6.1：出題流程必須經過審核後才能發布；既有考卷視為已審核以維持相容。
            conn.execute("ALTER TABLE quiz_categories ADD COLUMN IF NOT EXISTS review_status TEXT NOT NULL DEFAULT 'approved'")
            conn.execute("ALTER TABLE quiz_categories ADD COLUMN IF NOT EXISTS reviewer_name TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE quiz_categories ADD COLUMN IF NOT EXISTS reviewed_at TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE quiz_categories ADD COLUMN IF NOT EXISTS published_at TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE quiz_categories ADD COLUMN IF NOT EXISTS publication_id TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE quiz_categories ADD COLUMN IF NOT EXISTS publication_hash TEXT NOT NULL DEFAULT ''")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quiz_publications (
                    id TEXT PRIMARY KEY,
                    quiz_category_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    reviewer_name TEXT NOT NULL DEFAULT '',
                    snapshot_hash TEXT NOT NULL,
                    snapshot JSONB NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_quiz_publications_category ON quiz_publications(quiz_category_id, created_at DESC)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quiz_questions (
                    id TEXT PRIMARY KEY,
                    quiz_category_id TEXT NOT NULL,
                    tag TEXT NOT NULL DEFAULT '',
                    question TEXT NOT NULL,
                    question_type TEXT NOT NULL DEFAULT 'choice',
                    image_url TEXT NOT NULL DEFAULT '',
                    options JSONB NOT NULL,
                    correct INTEGER NOT NULL DEFAULT 0,
                    answer_config JSONB NOT NULL DEFAULT '{}'::jsonb,
                    explanation TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    active BOOLEAN NOT NULL DEFAULT TRUE
                )
            """)
            conn.execute("ALTER TABLE quiz_questions ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE")
            conn.execute("ALTER TABLE quiz_questions ADD COLUMN IF NOT EXISTS answer_config JSONB NOT NULL DEFAULT '{}'::jsonb")
            conn.execute("ALTER TABLE quiz_questions ADD COLUMN IF NOT EXISTS difficulty TEXT NOT NULL DEFAULT 'standard'")
        else:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quiz_categories (
                    id TEXT PRIMARY KEY,
                    group_key TEXT NOT NULL DEFAULT 'grpBio',
                    training_area TEXT NOT NULL DEFAULT 'internal',
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    date_added TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                )
            """)
            existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(quiz_categories)").fetchall()}
            if "training_area" not in existing_cols:
                conn.execute("ALTER TABLE quiz_categories ADD COLUMN training_area TEXT NOT NULL DEFAULT 'internal'")
            if "blind_mode" not in existing_cols:
                conn.execute("ALTER TABLE quiz_categories ADD COLUMN blind_mode INTEGER NOT NULL DEFAULT 0")
            if "draw_count" not in existing_cols:
                conn.execute("ALTER TABLE quiz_categories ADD COLUMN draw_count INTEGER NOT NULL DEFAULT 0")
            if "passing_score" not in existing_cols:
                conn.execute("ALTER TABLE quiz_categories ADD COLUMN passing_score INTEGER NOT NULL DEFAULT 80")
            if "audience" not in existing_cols:
                conn.execute("ALTER TABLE quiz_categories ADD COLUMN audience TEXT NOT NULL DEFAULT ''")
            if "draw_rules" not in existing_cols:
                conn.execute("ALTER TABLE quiz_categories ADD COLUMN draw_rules TEXT NOT NULL DEFAULT '{}'")
            if "review_status" not in existing_cols:
                conn.execute("ALTER TABLE quiz_categories ADD COLUMN review_status TEXT NOT NULL DEFAULT 'approved'")
            if "reviewer_name" not in existing_cols:
                conn.execute("ALTER TABLE quiz_categories ADD COLUMN reviewer_name TEXT NOT NULL DEFAULT ''")
            if "reviewed_at" not in existing_cols:
                conn.execute("ALTER TABLE quiz_categories ADD COLUMN reviewed_at TEXT NOT NULL DEFAULT ''")
            if "published_at" not in existing_cols:
                conn.execute("ALTER TABLE quiz_categories ADD COLUMN published_at TEXT NOT NULL DEFAULT ''")
            if "publication_id" not in existing_cols:
                conn.execute("ALTER TABLE quiz_categories ADD COLUMN publication_id TEXT NOT NULL DEFAULT ''")
            if "publication_hash" not in existing_cols:
                conn.execute("ALTER TABLE quiz_categories ADD COLUMN publication_hash TEXT NOT NULL DEFAULT ''")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quiz_publications (
                    id TEXT PRIMARY KEY,
                    quiz_category_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    reviewer_name TEXT NOT NULL DEFAULT '',
                    snapshot_hash TEXT NOT NULL,
                    snapshot TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_quiz_publications_category ON quiz_publications(quiz_category_id, created_at DESC)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quiz_questions (
                    id TEXT PRIMARY KEY,
                    quiz_category_id TEXT NOT NULL,
                    tag TEXT NOT NULL DEFAULT '',
                    question TEXT NOT NULL,
                    question_type TEXT NOT NULL DEFAULT 'choice',
                    image_url TEXT NOT NULL DEFAULT '',
                    options TEXT NOT NULL,
                    correct INTEGER NOT NULL DEFAULT 0,
                    answer_config TEXT NOT NULL DEFAULT '{}',
                    explanation TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 1
                )
            """)
            q_existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(quiz_questions)").fetchall()}
            if "active" not in q_existing_cols:
                conn.execute("ALTER TABLE quiz_questions ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
            if "answer_config" not in q_existing_cols:
                conn.execute("ALTER TABLE quiz_questions ADD COLUMN answer_config TEXT NOT NULL DEFAULT '{}'")
            if "difficulty" not in q_existing_cols:
                conn.execute("ALTER TABLE quiz_questions ADD COLUMN difficulty TEXT NOT NULL DEFAULT 'standard'")
    finally:
        conn.close()


def material_row_to_dict(row):
    r = dict(row)
    r["isBuiltin"] = False
    r["is_builtin"] = False
    r["desc"] = r.pop("description", "")
    r["dateAdded"] = r.pop("date_added", "")
    r["pageCount"] = int(r.pop("page_count", 0) or 0)
    r["storageFilename"] = r.pop("storage_filename", "")
    r["storageBackend"] = (r.pop("storage_backend", "local") or "local").lower()
    r["storageKey"] = r.pop("storage_key", "") or ""
    r["slidesPrefix"] = r.pop("slides_prefix", "") or ""
    raw_storage_meta = r.pop("storage_meta", "{}") or "{}"
    try:
        r["storageMeta"] = json.loads(raw_storage_meta) if isinstance(raw_storage_meta, str) else (raw_storage_meta or {})
    except Exception:
        r["storageMeta"] = {}
    r["slideFormat"] = str((r["storageMeta"] or {}).get("slideFormat", "png") or "png").lower()
    material_type = str(r.pop("material_type", "standard") or "standard").lower()
    r["materialType"] = material_type if material_type in {"standard", "atlas", "infographic", "video", "troubleshooting", "sop", "case"} else "standard"
    raw_atlas_meta = r.pop("atlas_meta", "{}") or "{}"
    try:
        r["atlasMeta"] = json.loads(raw_atlas_meta) if isinstance(raw_atlas_meta, str) else (raw_atlas_meta or {})
    except Exception:
        r["atlasMeta"] = {}
    r["active"] = bool(r.get("active", True))
    r["blindMode"] = bool(r.pop("blind_mode", False))
    r["group"] = normalize_group(r.pop("group_key", DEFAULT_GROUP))
    r["area"] = normalize_area(r.pop("training_area", DEFAULT_TRAINING_AREA))
    r["courseId"] = r.pop("course_id", "") or ""
    ext = Path(r.get("filename", "")).suffix.lower()
    if ext in {".mp4", ".webm", ".mov", ".m4v"}: r["viewerMode"] = "video"
    elif ext in {".mp3", ".wav", ".m4a", ".ogg"}: r["viewerMode"] = "audio"
    elif ext in {".png", ".jpg", ".jpeg", ".gif", ".webp"}: r["viewerMode"] = "image"
    elif (r.get("storageMeta") or {}).get("previewMode") == "single_pdf": r["viewerMode"] = "preview_pdf"
    elif r["pageCount"] > 0: r["viewerMode"] = "slides"
    else: r["viewerMode"] = "download"
    r["previewUrl"] = f"/material-preview/{r.get('id','')}" if r["viewerMode"] == "preview_pdf" else ""
    return r


def list_uploaded_materials(include_inactive=False):
    conn, _ = _db_conn()
    try:
        sql = "SELECT * FROM materials"
        if not include_inactive:
            sql += " WHERE active = " + ("TRUE" if DATABASE_URL else "1")
        sql += " ORDER BY date_added DESC"
        return [material_row_to_dict(r) for r in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def get_material(material_id):
    conn, _ = _db_conn()
    try:
        row = conn.execute("SELECT * FROM materials WHERE id = %s" % ("%s" if DATABASE_URL else "?"), (material_id,)).fetchone()
        return material_row_to_dict(row) if row else None
    finally:
        conn.close()


init_materials_db()
init_quiz_db()
init_material_jobs_db()


def init_learning_db():
    """V5：課程、教材完成紀錄、PGY進度與問答題人工審閱欄位。"""
    conn, kind = _db_conn()
    try:
        if kind == "postgres":
            conn.execute("""
                CREATE TABLE IF NOT EXISTS courses (
                    id TEXT PRIMARY KEY,
                    training_area TEXT NOT NULL DEFAULT 'pgy',
                    group_key TEXT NOT NULL DEFAULT 'grpBio',
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    date_added TEXT NOT NULL,
                    active BOOLEAN NOT NULL DEFAULT TRUE
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS material_progress (
                    emp_id TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    material_id TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    PRIMARY KEY (emp_id, material_id)
                )
            """)
            conn.execute("ALTER TABLE materials ADD COLUMN IF NOT EXISTS course_id TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE quiz_categories ADD COLUMN IF NOT EXISTS course_id TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE exam_records ADD COLUMN IF NOT EXISTS course_id TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE exam_records ADD COLUMN IF NOT EXISTS review_status TEXT NOT NULL DEFAULT 'completed'")
            conn.execute("ALTER TABLE exam_records ADD COLUMN IF NOT EXISTS reviewed_at TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE exam_records ADD COLUMN IF NOT EXISTS reviewer_name TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE exam_records ADD COLUMN IF NOT EXISTS review_comment TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE exam_records ADD COLUMN IF NOT EXISTS quiz_category_id TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE exam_records ADD COLUMN IF NOT EXISTS passing_score INTEGER NOT NULL DEFAULT 80")
        else:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS courses (
                    id TEXT PRIMARY KEY,
                    training_area TEXT NOT NULL DEFAULT 'pgy',
                    group_key TEXT NOT NULL DEFAULT 'grpBio',
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    date_added TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS material_progress (
                    emp_id TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    material_id TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    PRIMARY KEY (emp_id, material_id)
                )
            """)
            def add_col(table, name, ddl):
                cols={r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
                if name not in cols:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
            add_col('materials','course_id',"course_id TEXT NOT NULL DEFAULT ''")
            add_col('quiz_categories','course_id',"course_id TEXT NOT NULL DEFAULT ''")
            add_col('exam_records','course_id',"course_id TEXT NOT NULL DEFAULT ''")
            add_col('exam_records','review_status',"review_status TEXT NOT NULL DEFAULT 'completed'")
            add_col('exam_records','reviewed_at',"reviewed_at TEXT NOT NULL DEFAULT ''")
            add_col('exam_records','reviewer_name',"reviewer_name TEXT NOT NULL DEFAULT ''")
            add_col('exam_records','review_comment',"review_comment TEXT NOT NULL DEFAULT ''")
            add_col('exam_records','quiz_category_id',"quiz_category_id TEXT NOT NULL DEFAULT ''")
            add_col('exam_records','passing_score',"passing_score INTEGER NOT NULL DEFAULT 80")
    finally:
        conn.close()


def course_row_to_dict(row):
    r=dict(row)
    r['area']=normalize_area(r.pop('training_area', DEFAULT_TRAINING_AREA))
    r['group']=normalize_group(r.pop('group_key', DEFAULT_GROUP))
    r['desc']=r.pop('description','')
    r['sortOrder']=int(r.pop('sort_order',0) or 0)
    r['dateAdded']=r.pop('date_added','')
    r['active']=bool(r.get('active', True))
    r['learningObjectives']=r.pop('learning_objectives','')
    r['estimatedMinutes']=int(r.pop('estimated_minutes',0) or 0)
    r['startDate']=r.pop('start_date','')
    r['endDate']=r.pop('end_date','')
    try:
        r['materialOrder']=json.loads(r.pop('material_order','[]') or '[]')
    except (ValueError, TypeError):
        r['materialOrder']=[]
    return r

def get_course(course_id):
    if not course_id: return None
    conn,kind=_db_conn(); ph='%s' if kind=='postgres' else '?'
    try:
        row=conn.execute(f"SELECT * FROM courses WHERE id={ph}",(course_id,)).fetchone()
        return course_row_to_dict(row) if row else None
    finally: conn.close()

def list_courses(area=None, group=None, include_inactive=False):
    conn,kind=_db_conn(); ph='%s' if kind=='postgres' else '?'
    try:
        clauses=[]; params=[]
        if area: clauses.append(f"training_area={ph}"); params.append(normalize_area(area))
        if group: clauses.append(f"group_key={ph}"); params.append(normalize_group(group))
        if not include_inactive: clauses.append("active=" + ("TRUE" if kind=='postgres' else "1"))
        sql='SELECT * FROM courses' + ((' WHERE '+' AND '.join(clauses)) if clauses else '') + ' ORDER BY sort_order ASC, date_added ASC'
        return [course_row_to_dict(r) for r in conn.execute(sql,params).fetchall()]
    finally: conn.close()

init_learning_db()


# ---------------------------------------------------------------------------
# V5.8.0 使用者帳號、個人檔案與登入工作階段
# ---------------------------------------------------------------------------
def init_user_accounts_db():
    conn, kind = _db_conn()
    try:
        active_type = "BOOLEAN" if kind == "postgres" else "INTEGER"
        active_default = "TRUE" if kind == "postgres" else "1"
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS user_accounts (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL,
                emp_id TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL DEFAULT 'learner',
                preferred_area TEXT NOT NULL DEFAULT 'internal',
                preferred_group TEXT NOT NULL DEFAULT 'grpBio',
                active {active_type} NOT NULL DEFAULT {active_default},
                session_version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_login_at TEXT NOT NULL DEFAULT ''
            )
        """)
    finally:
        conn.close()


# Retained pre-extraction implementation for compatibility verification.
def _legacy_normalize_username(value):
    return re.sub(r"[^a-z0-9._-]", "", str(value or "").strip().lower())[:64]


def _normalize_username(value):
    return auth_service.normalize_username(value)


# Retained pre-extraction implementation for compatibility verification.
def _legacy_user_public(row):
    d = dict(row)
    return {
        "username": str(d.get("username", "")),
        "name": str(d.get("display_name", "")),
        "empId": str(d.get("emp_id", "")),
        "role": normalize_role(d.get("role", "student")),
        "legacyRole": str(d.get("role", "")) if str(d.get("role", "")) in LEGACY_ROLE_ALIASES else "",
        "preferredArea": normalize_area(d.get("preferred_area", DEFAULT_TRAINING_AREA)),
        "preferredGroup": normalize_group(d.get("preferred_group", DEFAULT_GROUP)),
        "active": bool(d.get("active", True)),
        "createdAt": str(d.get("created_at", "")),
        "updatedAt": str(d.get("updated_at", "")),
        "lastLoginAt": str(d.get("last_login_at", "")),
    }


def _user_public(row):
    return auth_service.public_user(sys.modules[__name__], row)


# Retained pre-extraction implementation for compatibility verification.
def _legacy_current_user():
    username = _normalize_username(session.get("username", ""))
    if not username:
        return None
    conn, kind = _db_conn(); ph = "%s" if kind == "postgres" else "?"
    try:
        row = conn.execute(f"SELECT * FROM user_accounts WHERE username={ph}", (username,)).fetchone()
    finally:
        conn.close()
    if not row or not bool(dict(row).get("active", True)):
        session.clear()
        return None
    if int(dict(row).get("session_version", 1) or 1) != int(session.get("session_version", 0) or 0):
        session.clear()
        return None
    return _user_public(row)


def _current_user():
    return auth_service.current_user(sys.modules[__name__], session)


def login_required(api=True):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            user = _current_user()
            if not user:
                if api:
                    return jsonify({"error": "請先登入後再使用教材。", "loginRequired": True}), 401
                target = request.full_path if request.query_string else request.path
                return redirect("/login?next=" + quote(target, safe=""))
            return fn(*args, **kwargs)
        return wrapped
    return decorator


# Retained pre-extraction implementation for compatibility verification.
def _legacy_require_roles(*allowed_roles):
    """Return the authenticated user or an error response for RBAC checks."""
    user = _current_user()
    if not user:
        return None, (jsonify({"error": "請先登入後再執行此操作。", "loginRequired": True}), 401)
    normalized_allowed = {normalize_role(role) for role in allowed_roles}
    if normalize_role(user.get("role")) not in normalized_allowed:
        labels = {"student": "學員", "clinical_teacher": "臨床教師", "group_leader": "組長", "education_admin": "教學管理者", "system_admin": "系統管理者", "auditor": "稽核／唯讀"}
        expected = "、".join(labels.get(role, role) for role in normalized_allowed)
        return None, (jsonify({"error": f"權限不足：此操作限{expected}使用。"}), 403)
    return user, None


def require_roles(*allowed_roles):
    return auth_routes.require_roles(_current_user(), *allowed_roles)


init_user_accounts_db()


# Retained pre-extraction implementation for compatibility verification.
def _legacy_api_auth_me():
    user = _current_user()
    return jsonify({"authenticated": bool(user), "user": user})


@app.get("/api/auth/me")
def api_auth_me():
    return auth_routes.me(sys.modules[__name__])


# Retained pre-extraction implementation for compatibility verification.
def _legacy_api_auth_login():
    data = request.get_json(silent=True) or {}
    username = _normalize_username(data.get("username"))
    password = str(data.get("password", ""))
    conn, kind = _db_conn(); ph = "%s" if kind == "postgres" else "?"
    try:
        row = conn.execute(f"SELECT * FROM user_accounts WHERE username={ph}", (username,)).fetchone()
        raw = dict(row) if row else None
        if not raw or not bool(raw.get("active", True)) or not check_password_hash(str(raw.get("password_hash", "")), password):
            return jsonify({"error": "帳號或密碼不正確，請洽管理者。"}), 401
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn.execute(f"UPDATE user_accounts SET last_login_at={ph} WHERE username={ph}", (now, username))
        raw["last_login_at"] = now
    finally:
        conn.close()
    session.clear()
    session.permanent = True
    session["username"] = username
    session["session_version"] = int(raw.get("session_version", 1) or 1)
    return jsonify({"ok": True, "user": _user_public(raw)})


@app.post("/api/auth/login")
def api_auth_login():
    return auth_routes.login(sys.modules[__name__])


# Retained pre-extraction implementation for compatibility verification.
def _legacy_api_auth_logout():
    session.clear()
    return jsonify({"ok": True})


@app.post("/api/auth/logout")
def api_auth_logout():
    return auth_routes.logout()


@app.get("/api/users")
def api_users_admin():
    denied = require_admin()
    if denied: return denied
    conn, _ = _db_conn()
    try:
        rows = conn.execute("SELECT * FROM user_accounts ORDER BY active DESC, display_name ASC, username ASC").fetchall()
        return jsonify([_user_public(row) for row in rows])
    finally:
        conn.close()


@app.post("/api/users")
def api_user_create():
    denied = require_admin()
    if denied: return denied
    data = request.get_json(silent=True) or {}
    username = _normalize_username(data.get("username"))
    password = str(data.get("password", ""))
    name = str(data.get("name", "")).strip()[:100]
    emp_id = str(data.get("empId", "")).strip()[:100]
    requested_role = str(data.get("role", "student")).strip().lower()
    if len(username) < 3 or len(password) < 4 or not name or not emp_id:
        return jsonify({"error": "帳號至少 3 碼、密碼至少 4 碼，姓名與工號皆為必填。"}), 400
    if requested_role not in CANONICAL_ROLES and requested_role not in LEGACY_ROLE_ALIASES:
        return jsonify({"error": "角色格式不正確。"}), 400
    role = normalize_role(requested_role)
    area = normalize_area(data.get("preferredArea", DEFAULT_TRAINING_AREA))
    group = normalize_group(data.get("preferredGroup", DEFAULT_GROUP))
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn, kind = _db_conn(); ph = "%s" if kind == "postgres" else "?"
    try:
        conn.execute(
            f"INSERT INTO user_accounts (username,password_hash,display_name,emp_id,role,preferred_area,preferred_group,active,session_version,created_at,updated_at,last_login_at) VALUES ({','.join([ph]*12)})",
            (username, generate_password_hash(password), name, emp_id, role, area, group, True if kind == "postgres" else 1, 1, now, now, ""),
        )
    except Exception as exc:
        return jsonify({"error": "帳號或工號已存在。", "detail": str(exc)[:180]}), 409
    finally:
        conn.close()
    return jsonify({"ok": True, "user": {"username": username, "name": name, "empId": emp_id, "role": role, "preferredArea": area, "preferredGroup": group, "active": True}})


@app.patch("/api/users/<username>")
def api_user_update(username):
    denied = require_admin()
    if denied: return denied
    username = _normalize_username(username)
    data = request.get_json(silent=True) or {}
    conn, kind = _db_conn(); ph = "%s" if kind == "postgres" else "?"
    try:
        row = conn.execute(f"SELECT * FROM user_accounts WHERE username={ph}", (username,)).fetchone()
        if not row: return jsonify({"error": "找不到帳號。"}), 404
        raw = dict(row); fields = []; values = []
        mapping = {"name": "display_name", "empId": "emp_id", "role": "role", "preferredArea": "preferred_area", "preferredGroup": "preferred_group"}
        for key, column in mapping.items():
            if key not in data: continue
            value = str(data.get(key, "")).strip()[:100]
            if key == "role":
                if value not in CANONICAL_ROLES and value not in LEGACY_ROLE_ALIASES: return jsonify({"error": "角色格式不正確。"}), 400
                value = normalize_role(value)
            if key == "preferredArea": value = normalize_area(value)
            if key == "preferredGroup": value = normalize_group(value)
            if key in {"name", "empId"} and not value: return jsonify({"error": "姓名與工號不可空白。"}), 400
            fields.append(f"{column}={ph}"); values.append(value)
        if "active" in data:
            active = data.get("active")
            if type(active) is not bool: return jsonify({"error": "帳號狀態格式不正確。"}), 400
            fields.append(f"active={ph}"); values.append(active if kind == "postgres" else int(active))
            if not active: fields.append("session_version=session_version+1")
        password = str(data.get("password", ""))
        if password:
            if len(password) < 4: return jsonify({"error": "新密碼至少 4 碼。"}), 400
            fields.extend([f"password_hash={ph}", "session_version=session_version+1"]); values.append(generate_password_hash(password))
        if not fields: return jsonify({"error": "沒有可更新的欄位。"}), 400
        fields.append(f"updated_at={ph}"); values.append(datetime.datetime.now(datetime.timezone.utc).isoformat()); values.append(username)
        conn.execute(f"UPDATE user_accounts SET {','.join(fields)} WHERE username={ph}", values)
        updated = conn.execute(f"SELECT * FROM user_accounts WHERE username={ph}", (username,)).fetchone()
        return jsonify({"ok": True, "user": _user_public(updated)})
    except Exception as exc:
        return jsonify({"error": "更新失敗，請確認工號未被其他帳號使用。", "detail": str(exc)[:180]}), 409
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# V5.7.1 平台公告
# ---------------------------------------------------------------------------
def init_announcements_db():
    conn, kind = _db_conn()
    try:
        if kind == "postgres":
            conn.execute("""
                CREATE TABLE IF NOT EXISTS announcements (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL DEFAULT '',
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TEXT NOT NULL,
                    published_at TEXT NOT NULL DEFAULT ''
                )
            """)
        else:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS announcements (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    published_at TEXT NOT NULL DEFAULT ''
                )
            """)
    finally:
        conn.close()


init_announcements_db()


def init_teaching_plan_db():
    """Additive migration: existing courses and completion records remain intact."""
    conn, kind = _db_conn()
    columns = {
        'learning_objectives': "TEXT NOT NULL DEFAULT ''",
        'estimated_minutes': 'INTEGER NOT NULL DEFAULT 0',
        'start_date': "TEXT NOT NULL DEFAULT ''",
        'end_date': "TEXT NOT NULL DEFAULT ''",
        'material_order': "TEXT NOT NULL DEFAULT '[]'",
    }
    try:
        existing = set() if kind == 'postgres' else {r[1] for r in conn.execute('PRAGMA table_info(courses)').fetchall()}
        for name, ddl in columns.items():
            if kind == 'postgres':
                conn.execute(f'ALTER TABLE courses ADD COLUMN IF NOT EXISTS {name} {ddl}')
            elif name not in existing:
                conn.execute(f'ALTER TABLE courses ADD COLUMN {name} {ddl}')
    finally:
        conn.close()


init_teaching_plan_db()


def seed_builtin_bio_quizzes():
    """V5.3.7 一次性 migration：把舊版前端寫死的 4 份生化考卷搬進資料庫。

    migration 完成後以 app_meta 記錄，因此管理者日後刪除或修改考卷時，
    重新啟動服務不會把舊題庫重新塞回來。
    """
    seed_path = BASE_DIR / "data" / "builtin_quiz_seed.json"
    if not seed_path.exists():
        return
    try:
        payload = json.loads(seed_path.read_text(encoding="utf-8"))
    except Exception as exc:
        app.logger.warning("builtin quiz seed load failed: %s", exc)
        return
    conn, kind = _db_conn()
    ph = "%s" if kind == "postgres" else "?"
    migration_key = "v5.3.7-bio-quiz-migrated"
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS app_meta (meta_key TEXT PRIMARY KEY, meta_value TEXT NOT NULL DEFAULT '')")
        done = conn.execute(f"SELECT meta_value FROM app_meta WHERE meta_key={ph}", (migration_key,)).fetchone()
        if done:
            return
        for cat in payload.get("categories", []):
            cid = str(cat.get("id", "")).strip()
            if not cid:
                continue
            exists = conn.execute(f"SELECT id FROM quiz_categories WHERE id={ph}", (cid,)).fetchone()
            if not exists:
                title = str(cat.get("title", cid))[:255]
                desc = str(cat.get("desc", ""))[:1000]
                order = int(cat.get("sortOrder", 0) or 0)
                date_added = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                if kind == "postgres":
                    conn.execute("INSERT INTO quiz_categories (id,group_key,training_area,course_id,title,description,sort_order,date_added,active) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                                 (cid, "grpBio", "internal", "", title, desc, order, date_added, True))
                else:
                    conn.execute("INSERT INTO quiz_categories (id,group_key,training_area,course_id,title,description,sort_order,date_added,active) VALUES (?,?,?,?,?,?,?,?,?)",
                                 (cid, "grpBio", "internal", "", title, desc, order, date_added, 1))
                for q in cat.get("questions", []):
                    vals=(str(q.get("id") or f"q-{uuid.uuid4().hex[:12]}"), cid, str(q.get("tag","一般"))[:100], str(q.get("question","")).strip(), str(q.get("questionType","choice")), str(q.get("imageUrl",""))[:1000], json.dumps(q.get("options",[]),ensure_ascii=False), int(q.get("correct",0) or 0), str(q.get("explanation","")), int(q.get("sortOrder",0) or 0))
                    if kind == "postgres":
                        conn.execute("INSERT INTO quiz_questions (id,quiz_category_id,tag,question,question_type,image_url,options,correct,explanation,sort_order,active) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)", vals)
                    else:
                        conn.execute("INSERT INTO quiz_questions (id,quiz_category_id,tag,question,question_type,image_url,options,correct,explanation,sort_order,active) VALUES (?,?,?,?,?,?,?,?,?,?,1)", vals)
        now = datetime.datetime.now().isoformat()
        if kind == "postgres":
            conn.execute("INSERT INTO app_meta (meta_key,meta_value) VALUES (%s,%s) ON CONFLICT (meta_key) DO UPDATE SET meta_value=EXCLUDED.meta_value", (migration_key, now))
        else:
            conn.execute("INSERT OR REPLACE INTO app_meta (meta_key,meta_value) VALUES (?,?)", (migration_key, now))
    except Exception as exc:
        app.logger.exception("builtin quiz seed failed: %s", exc)
    finally:
        conn.close()


seed_builtin_bio_quizzes()


def migrate_v540_exam_settings():
    """V5.4.0 一次性相容升級。

    V5.3.x 前台預設每份考卷抽 10 題。第一次啟動 V5.4.0 時，
    把當下已存在且未設定抽題數的考卷保留為 10 題；之後新建考卷
    仍使用資料表預設 draw_count=0（全部啟用題目）。
    """
    conn, kind = _db_conn()
    ph = "%s" if kind == "postgres" else "?"
    key = "v5.4.0-exam-settings-migrated"
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS app_meta (meta_key TEXT PRIMARY KEY, meta_value TEXT NOT NULL DEFAULT '')")
        done = conn.execute(f"SELECT meta_value FROM app_meta WHERE meta_key={ph}", (key,)).fetchone()
        if done:
            return
        conn.execute("UPDATE quiz_categories SET draw_count=10 WHERE COALESCE(draw_count,0)=0")
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if kind == "postgres":
            conn.execute("INSERT INTO app_meta (meta_key,meta_value) VALUES (%s,%s) ON CONFLICT (meta_key) DO UPDATE SET meta_value=EXCLUDED.meta_value", (key, now))
        else:
            conn.execute("INSERT OR REPLACE INTO app_meta (meta_key,meta_value) VALUES (?,?)", (key, now))
    finally:
        conn.close()


migrate_v540_exam_settings()


# ---------------------------------------------------------------------------
# 考題頁籤 (quiz_categories) 與題目 (quiz_questions) 存取輔助函式
# ---------------------------------------------------------------------------
def quiz_category_row_to_dict(row):
    r = dict(row)
    r["desc"] = r.pop("description", "")
    r["dateAdded"] = r.pop("date_added", "")
    r["active"] = bool(r.get("active", True))
    r["blindMode"] = bool(r.pop("blind_mode", False))
    r["group"] = normalize_group(r.pop("group_key", DEFAULT_GROUP))
    r["area"] = normalize_area(r.pop("training_area", DEFAULT_TRAINING_AREA))
    r["courseId"] = r.pop("course_id", "") or ""
    r["sortOrder"] = int(r.pop("sort_order", 0) or 0)
    try:
        r["drawCount"] = max(0, int(r.pop("draw_count", 0) or 0))
    except Exception:
        r["drawCount"] = 0
    try:
        r["passingScore"] = max(1, min(100, int(r.pop("passing_score", 80) or 80)))
    except Exception:
        r["passingScore"] = 80
    r["audience"] = str(r.pop("audience", "") or "")
    raw_draw_rules = r.pop("draw_rules", {}) or {}
    if isinstance(raw_draw_rules, str):
        try:
            raw_draw_rules = json.loads(raw_draw_rules)
        except Exception:
            raw_draw_rules = {}
    r["drawRules"] = raw_draw_rules if isinstance(raw_draw_rules, dict) else {}
    review_status = str(r.pop("review_status", "approved") or "approved").lower()
    r["reviewStatus"] = review_status if review_status in {"draft", "approved"} else "draft"
    r["reviewerName"] = str(r.pop("reviewer_name", "") or "")
    r["reviewedAt"] = str(r.pop("reviewed_at", "") or "")
    r["publishedAt"] = str(r.pop("published_at", "") or "")
    r["publicationId"] = str(r.pop("publication_id", "") or "")
    r["publicationHash"] = str(r.pop("publication_hash", "") or "")
    if r.get("active"):
        r["workflowStage"] = "published"
    elif r["reviewStatus"] == "approved":
        r["workflowStage"] = "reviewed"
    else:
        r["workflowStage"] = "draft"
    return r


def quiz_question_row_to_dict(row):
    r = dict(row)
    raw_options = r.pop("options", "[]")
    if isinstance(raw_options, str):
        try:
            raw_options = json.loads(raw_options)
        except json.JSONDecodeError:
            raw_options = []
    r["options"] = raw_options
    raw_answer_config = r.pop("answer_config", {}) or {}
    if isinstance(raw_answer_config, str):
        try:
            raw_answer_config = json.loads(raw_answer_config)
        except Exception:
            raw_answer_config = {}
    r["answerConfig"] = raw_answer_config if isinstance(raw_answer_config, dict) else {}
    r["questionType"] = r.pop("question_type", "choice")
    diff = str(r.pop("difficulty", "standard") or "standard").lower()
    r["difficulty"] = diff if diff in {"basic", "standard", "advanced"} else "standard"
    r["imageUrl"] = r.pop("image_url", "")
    r["quizCategoryId"] = r.pop("quiz_category_id", "")
    r["sortOrder"] = int(r.pop("sort_order", 0) or 0)
    r["active"] = bool(r.get("active", True))
    return r


def list_quiz_categories(group_key=None, training_area=None, include_inactive=False):
    conn, kind = _db_conn()
    try:
        ph = "%s" if kind == "postgres" else "?"
        sql = "SELECT * FROM quiz_categories"
        params = []
        clauses = []
        if group_key:
            clauses.append(f"group_key = {ph}")
            params.append(group_key)
        if training_area:
            clauses.append(f"training_area = {ph}")
            params.append(normalize_area(training_area))
        if not include_inactive:
            clauses.append("active = " + ("TRUE" if kind == "postgres" else "1"))
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY sort_order ASC, date_added ASC"
        return [quiz_category_row_to_dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def list_quiz_categories_with_counts(group_key=None, training_area=None, include_inactive=True):
    """用同一個資料庫連線取得考卷與題數，減少 Render ↔ Supabase 往返。"""
    conn, kind = _db_conn()
    try:
        ph = "%s" if kind == "postgres" else "?"
        sql = "SELECT * FROM quiz_categories"
        params = []
        clauses = []
        if group_key:
            clauses.append(f"group_key = {ph}")
            params.append(group_key)
        if training_area:
            clauses.append(f"training_area = {ph}")
            params.append(normalize_area(training_area))
        if not include_inactive:
            clauses.append("active = " + ("TRUE" if kind == "postgres" else "1"))
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY sort_order ASC, date_added ASC"
        cats = [quiz_category_row_to_dict(r) for r in conn.execute(sql, params).fetchall()]
        ids = [str(c.get("id", "")) for c in cats if c.get("id")]
        counts = {}
        if ids:
            placeholders = ",".join([ph] * len(ids))
            qsql = f"SELECT quiz_category_id, COUNT(*) AS cnt FROM quiz_questions WHERE quiz_category_id IN ({placeholders})"
            qsql += " AND active = " + ("TRUE" if kind == "postgres" else "1")
            qsql += " GROUP BY quiz_category_id"
            for row in conn.execute(qsql, ids).fetchall():
                try:
                    d = dict(row)
                    counts[str(d.get("quiz_category_id", ""))] = int(d.get("cnt", 0) or 0)
                except Exception:
                    counts[str(row[0])] = int(row[1] or 0)
        for c in cats:
            c["questionCount"] = counts.get(str(c.get("id", "")), 0)
        return cats
    finally:
        conn.close()


def get_quiz_category(category_id):
    conn, kind = _db_conn()
    try:
        ph = "%s" if kind == "postgres" else "?"
        row = conn.execute(f"SELECT * FROM quiz_categories WHERE id = {ph}", (category_id,)).fetchone()
        return quiz_category_row_to_dict(row) if row else None
    finally:
        conn.close()


def list_quiz_questions(category_id, include_inactive=False):
    conn, kind = _db_conn()
    try:
        ph = "%s" if kind == "postgres" else "?"
        sql = f"SELECT * FROM quiz_questions WHERE quiz_category_id = {ph}"
        if not include_inactive:
            sql += " AND active = " + ("TRUE" if kind == "postgres" else "1")
        sql += " ORDER BY sort_order ASC"
        rows = conn.execute(sql, (category_id,)).fetchall()
        return [quiz_question_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_quiz_question(question_id):
    conn, kind = _db_conn()
    try:
        ph = "%s" if kind == "postgres" else "?"
        row = conn.execute(f"SELECT * FROM quiz_questions WHERE id = {ph}", (question_id,)).fetchone()
        return quiz_question_row_to_dict(row) if row else None
    finally:
        conn.close()


def resolve_category_label(category, group_key):
    """依 category 代碼組出前端顯示用頁籤名稱；優先採資料庫目前名稱。"""
    if not category:
        return CATEGORY_LABELS[""]
    cat = get_quiz_category(category)
    if cat:
        return cat["title"]
    return CATEGORY_LABELS.get(category, CATEGORY_LABELS[""])


def category_label_map():
    """一次讀取所有動態考卷名稱，避免教材清單逐筆連 Supabase 查名稱（N+1）。"""
    labels = dict(CATEGORY_LABELS)
    try:
        for cat in list_quiz_categories(include_inactive=True):
            labels[cat.get("id", "")] = cat.get("title", "") or labels.get(cat.get("id", ""), CATEGORY_LABELS[""])
    except Exception:
        # 教材 API 即使暫時讀不到題庫名稱也應可回傳清單。
        pass
    return labels


def quiz_question_counts(category_ids, include_inactive=False):
    """以單一 SQL 取得多張考卷題數，取代前端每張考卷各打一個 API。"""
    ids = [str(x) for x in category_ids if x]
    if not ids:
        return {}
    conn, kind = _db_conn()
    try:
        ph = "%s" if kind == "postgres" else "?"
        placeholders = ",".join([ph] * len(ids))
        sql = f"SELECT quiz_category_id, COUNT(*) AS cnt FROM quiz_questions WHERE quiz_category_id IN ({placeholders})"
        if not include_inactive:
            sql += " AND active = " + ("TRUE" if kind == "postgres" else "1")
        sql += " GROUP BY quiz_category_id"
        rows = conn.execute(sql, ids).fetchall()
        out = {}
        for row in rows:
            try:
                d = dict(row)
                out[str(d.get("quiz_category_id", ""))] = int(d.get("cnt", 0) or 0)
            except Exception:
                out[str(row[0])] = int(row[1] or 0)
        return out
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 附件1 Word 匯出範本 (doc_templates) —— 每個組別可各自上傳一份空白 .docx 範本，
# 前端匯出時改用該組別的範本自動填入，取代原本每次都要在瀏覽器手動選檔的方式。
# V5.3.7 起六組皆可由後台上傳 Word 匯出範本；生化組仍保留瀏覽器手動選檔作為備援。
# ---------------------------------------------------------------------------
def init_doc_templates_db():
    """Word 範本資料表。V5.3.7 起可跟教材一樣保存到 Google Drive / R2。"""
    conn, kind = _db_conn()
    try:
        if kind == "postgres":
            conn.execute("""
                CREATE TABLE IF NOT EXISTS doc_templates (
                    group_key TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    storage_filename TEXT NOT NULL,
                    uploaded_at TEXT NOT NULL,
                    storage_backend TEXT NOT NULL DEFAULT 'local',
                    storage_key TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute("ALTER TABLE doc_templates ADD COLUMN IF NOT EXISTS storage_backend TEXT NOT NULL DEFAULT 'local'")
            conn.execute("ALTER TABLE doc_templates ADD COLUMN IF NOT EXISTS storage_key TEXT NOT NULL DEFAULT ''")
        else:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS doc_templates (
                    group_key TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    storage_filename TEXT NOT NULL,
                    uploaded_at TEXT NOT NULL,
                    storage_backend TEXT NOT NULL DEFAULT 'local',
                    storage_key TEXT NOT NULL DEFAULT ''
                )
            """)
            cols = {row[1] for row in conn.execute("PRAGMA table_info(doc_templates)").fetchall()}
            if "storage_backend" not in cols:
                conn.execute("ALTER TABLE doc_templates ADD COLUMN storage_backend TEXT NOT NULL DEFAULT 'local'")
            if "storage_key" not in cols:
                conn.execute("ALTER TABLE doc_templates ADD COLUMN storage_key TEXT NOT NULL DEFAULT ''")
    finally:
        conn.close()


def list_doc_templates():
    conn, kind = _db_conn()
    try:
        rows = conn.execute("SELECT * FROM doc_templates").fetchall()
        return {row["group_key"]: dict(row) for row in rows}
    finally:
        conn.close()


def get_doc_template_row(group_key):
    conn, kind = _db_conn()
    try:
        ph = "%s" if kind == "postgres" else "?"
        row = conn.execute(f"SELECT * FROM doc_templates WHERE group_key = {ph}", (group_key,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def save_doc_template_row(group_key, filename, storage_filename, storage_backend="local", storage_key=""):
    conn, kind = _db_conn()
    try:
        uploaded_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        backend = (storage_backend or "local").lower()
        key = storage_key or ""
        if kind == "postgres":
            conn.execute("""
                INSERT INTO doc_templates (group_key, filename, storage_filename, uploaded_at, storage_backend, storage_key)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (group_key) DO UPDATE SET filename=EXCLUDED.filename,
                    storage_filename=EXCLUDED.storage_filename, uploaded_at=EXCLUDED.uploaded_at,
                    storage_backend=EXCLUDED.storage_backend, storage_key=EXCLUDED.storage_key
            """, (group_key, filename, storage_filename, uploaded_at, backend, key))
        else:
            conn.execute("""
                INSERT INTO doc_templates (group_key, filename, storage_filename, uploaded_at, storage_backend, storage_key)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(group_key) DO UPDATE SET filename=excluded.filename,
                    storage_filename=excluded.storage_filename, uploaded_at=excluded.uploaded_at,
                    storage_backend=excluded.storage_backend, storage_key=excluded.storage_key
            """, (group_key, filename, storage_filename, uploaded_at, backend, key))
    finally:
        conn.close()


def delete_doc_template_row(group_key):
    conn, kind = _db_conn()
    try:
        ph = "%s" if kind == "postgres" else "?"
        conn.execute(f"DELETE FROM doc_templates WHERE group_key = {ph}", (group_key,))
    finally:
        conn.close()


init_doc_templates_db()


# ----------------------------------------------------------------------------
# 簡報中繼資料 (slides_meta.json) 存取
# ---------------------------------------------------------------------------
def load_meta():
    if META_FILE.exists():
        return json.loads(META_FILE.read_text(encoding="utf-8"))
    return []


def save_meta(meta):
    META_FILE.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def init_builtin_meta():
    """V5.3.10 起不再內建舊投影片；教材請由管理後台重新上傳。"""
    if not META_FILE.exists():
        save_meta([])


init_builtin_meta()


# ---------------------------------------------------------------------------
# V5.6.1 教材頁面最佳化：WebP 優先，PNG 向下相容
# ---------------------------------------------------------------------------
def _render_slide_pixmap(pix, out_folder: Path, page_no: int, quality: int = None) -> Path:
    quality = max(70, min(96, int(quality or MATERIAL_WEBP_QUALITY)))
    use_webp = MATERIAL_SLIDE_FORMAT == "webp" and Image is not None
    if use_webp:
        out = out_folder / f"slide-{page_no:02d}.webp"
        try:
            with Image.open(io.BytesIO(pix.tobytes("png"))) as img:
                if img.mode not in {"RGB", "RGBA"}:
                    img = img.convert("RGB")
                img.save(out, format="WEBP", quality=quality, method=6)
            return out
        except Exception:
            # 若環境 WebP codec 不可用，回退 PNG，不中斷教材建立。
            pass
    out = out_folder / f"slide-{page_no:02d}.png"
    pix.save(str(out))
    return out

def _slide_local_path(slides_dir: Path, page_no: int) -> Path:
    for ext in ("webp", "png", "jpg", "jpeg"):
        p = slides_dir / f"slide-{page_no:02d}.{ext}"
        if p.exists():
            return p
    return slides_dir / f"slide-{page_no:02d}.png"

def _slide_format(slides_dir: Path, page_count: int) -> str:
    if int(page_count or 0) <= 0:
        return ""
    p=_slide_local_path(slides_dir,1)
    return p.suffix.lower().lstrip(".") if p.exists() else "png"

def _slide_content_type(path: Path) -> str:
    return {".webp":"image/webp",".jpg":"image/jpeg",".jpeg":"image/jpeg",".png":"image/png"}.get(path.suffix.lower(),"application/octet-stream")


def _linearize_pdf_in_place(path: Path) -> bool:
    """使用 qpdf 建立 Fast Web View；環境沒有 qpdf 時安全回退，不影響教材建立。"""
    if not MATERIAL_PDF_LINEARIZE:
        return False
    qpdf = shutil.which("qpdf")
    if not qpdf or not path.exists():
        return False
    temp = path.with_name(path.stem + ".linearized.tmp.pdf")
    try:
        cp = subprocess.run([qpdf, "--linearize", str(path), str(temp)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180, check=False)
        if cp.returncode == 0 and temp.exists() and temp.stat().st_size > 0:
            os.replace(temp, path)
            return True
    except Exception:
        pass
    finally:
        if temp.exists():
            try: temp.unlink()
            except OSError: pass
    return False


def _save_optimized_pdf(source_pdf: Path, output_pdf: Path) -> int:
    """建立單一 PDF 閱讀版；保留向量文字與原始醫學影像，不做破壞性重新取樣。"""
    if pymupdf is None:
        raise RuntimeError("伺服器缺少 PyMuPDF 套件")
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(str(source_pdf))
    page_count = 0
    try:
        page_count = int(doc.page_count or 0)
        if page_count <= 0:
            raise RuntimeError("教材頁數為 0，請確認檔案內容是否正確。")
        if MATERIAL_PREVIEW_OPTIMIZE:
            try:
                doc.save(str(output_pdf), garbage=4, clean=True, deflate=True, deflate_images=True, deflate_fonts=True)
            except TypeError:
                # 舊版 PyMuPDF 不支援 deflate_images / deflate_fonts 時仍保留結構壓縮。
                doc.save(str(output_pdf), garbage=4, clean=True, deflate=True)
        else:
            doc.save(str(output_pdf), garbage=3, deflate=True)
    finally:
        doc.close()
    # PyMuPDF 新版已移除 linearize 寫入能力，V5.7 改由 qpdf 進行 Fast Web View。
    _linearize_pdf_in_place(output_pdf)
    return page_count


def build_single_preview_pdf(source_path: Path, output_pdf: Path, progress_id: str = "") -> int:
    """Office / PDF -> 單一 preview.pdf。MEGA 模式避免逐頁產生與上傳數十張圖片。"""
    ext = source_path.suffix.lower()
    if ext == ".pdf":
        if progress_id:
            set_upload_progress(progress_id, 16, "建立單一預覽檔", "正在整理 PDF 結構與壓縮可安全壓縮的資料…")
        pages = _save_optimized_pdf(source_path, output_pdf)
        if progress_id:
            set_upload_progress(progress_id, 46, "單一預覽檔完成", f"已建立 {pages} 頁 preview.pdf，不再產生逐頁圖片", current=pages, total=pages)
        return pages
    if ext not in OFFICE_EXT:
        return 0
    with conversion_lock:
        profile_dir = TMP_DIR / f"profile-preview-{uuid.uuid4().hex}"
        pdf_tmp_dir = TMP_DIR / f"pdf-preview-{uuid.uuid4().hex}"
        profile_dir.mkdir(parents=True, exist_ok=True)
        pdf_tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            if progress_id:
                set_upload_progress(progress_id, 12, "建立單一預覽檔", "LibreOffice 正在將教材轉為單一 PDF 預覽檔…")
            cmd=[SOFFICE_BIN,"--headless","--norestore",f"-env:UserInstallation=file:///{profile_dir.as_posix()}","--convert-to","pdf","--outdir",str(pdf_tmp_dir),str(source_path)]
            result=subprocess.run(cmd,capture_output=True,timeout=240)
            if result.returncode != 0:
                raise RuntimeError(result.stderr.decode(errors="ignore")[:500] or "LibreOffice 轉檔失敗")
            pdfs=list(pdf_tmp_dir.glob("*.pdf"))
            if not pdfs:
                raise RuntimeError("LibreOffice 未產生 PDF 預覽檔")
            if progress_id:
                set_upload_progress(progress_id, 30, "壓縮單一預覽檔", "正在移除 PDF 冗餘物件並壓縮字型／影像資料；不降低醫療圖像解析度")
            pages = _save_optimized_pdf(pdfs[0], output_pdf)
            if progress_id:
                set_upload_progress(progress_id, 46, "單一預覽檔完成", f"已建立 {pages} 頁 preview.pdf，不再產生逐頁圖片", current=pages, total=pages)
            return pages
        finally:
            shutil.rmtree(profile_dir, ignore_errors=True)
            shutil.rmtree(pdf_tmp_dir, ignore_errors=True)

# ---------------------------------------------------------------------------
# 舊版相容：Office / PDF -> 逐頁教材圖片（非 MEGA 或既有流程可繼續使用）
# ---------------------------------------------------------------------------
def convert_pptx_to_images(pptx_path: Path, out_folder: Path) -> int:
    """
    將 pptx_path 轉換成一系列最佳化教材頁面（預設 WebP，必要時回退 PNG）。
    回傳頁數。若轉檔失敗會拋出例外。
    """
    if pymupdf is None:
        raise RuntimeError("伺服器缺少 PyMuPDF 套件，請先執行 pip install -r requirements.txt")

    out_folder.mkdir(parents=True, exist_ok=True)

    with conversion_lock:
        profile_dir = TMP_DIR / f"profile-{uuid.uuid4().hex}"
        pdf_tmp_dir = TMP_DIR / f"pdf-{uuid.uuid4().hex}"
        profile_dir.mkdir(parents=True, exist_ok=True)
        pdf_tmp_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 1) 用 LibreOffice 無頭模式將 pptx 轉成 pdf
            #    -env:UserInstallation 讓每次轉檔使用獨立設定檔，避免併發時互相鎖死
            cmd = [
                SOFFICE_BIN,
                "--headless",
                "--norestore",
                f"-env:UserInstallation=file:///{profile_dir.as_posix()}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(pdf_tmp_dir),
                str(pptx_path),
            ]
            result = subprocess.run(
                cmd, capture_output=True, timeout=180
            )
            if result.returncode != 0:
                stderr = result.stderr.decode(errors="ignore")
                raise RuntimeError(f"LibreOffice 轉檔失敗：{stderr[:500]}")

            pdf_files = list(pdf_tmp_dir.glob("*.pdf"))
            if not pdf_files:
                raise RuntimeError("找不到轉檔後產生的 PDF 檔案，請確認 LibreOffice 是否正確安裝。")
            pdf_path = pdf_files[0]

            # 2) 用 PyMuPDF 把 PDF 每一頁轉成閱讀版圖片（約 170 DPI；預設 WebP）
            doc = pymupdf.open(str(pdf_path))
            zoom = 170 / 72.0
            mat = pymupdf.Matrix(zoom, zoom)
            page_count = doc.page_count
            for i in range(page_count):
                page = doc.load_page(i)
                pix = page.get_pixmap(matrix=mat)
                _render_slide_pixmap(pix, out_folder, i + 1)
            doc.close()

            if page_count == 0:
                raise RuntimeError("簡報頁數為 0，請確認檔案內容是否正確。")

            return page_count
        finally:
            shutil.rmtree(profile_dir, ignore_errors=True)
            shutil.rmtree(pdf_tmp_dir, ignore_errors=True)



def convert_pdf_to_images(pdf_path: Path, out_folder: Path, progress_id: str = "") -> int:
    if pymupdf is None:
        raise RuntimeError("伺服器缺少 PyMuPDF 套件")
    out_folder.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(str(pdf_path)); zoom = 170 / 72.0; mat = pymupdf.Matrix(zoom, zoom)
    page_count = doc.page_count
    if progress_id:
        set_upload_progress(progress_id, 18, "解析文件頁面", f"偵測到 {page_count} 頁，準備產生高解析投影片圖片", current=0, total=page_count)
    for i in range(page_count):
        pix = doc.load_page(i).get_pixmap(matrix=mat)
        _render_slide_pixmap(pix, out_folder, i + 1)
        if progress_id:
            pct = 18 + ((i + 1) / max(1, page_count)) * 32
            set_upload_progress(progress_id, pct, "產生投影片圖片", f"正在產生第 {i+1} / {page_count} 張高解析圖片", current=i+1, total=page_count)
    doc.close()
    return page_count

def convert_office_to_images(source_path: Path, out_folder: Path, progress_id: str = "") -> int:
    with conversion_lock:
        profile_dir = TMP_DIR / f"profile-{uuid.uuid4().hex}"
        pdf_tmp_dir = TMP_DIR / f"pdf-{uuid.uuid4().hex}"
        profile_dir.mkdir(parents=True, exist_ok=True); pdf_tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            if progress_id:
                set_upload_progress(progress_id, 12, "轉換 Office 文件", "LibreOffice 正在轉換為 PDF…")
            cmd=[SOFFICE_BIN,"--headless","--norestore",f"-env:UserInstallation=file:///{profile_dir.as_posix()}","--convert-to","pdf","--outdir",str(pdf_tmp_dir),str(source_path)]
            result=subprocess.run(cmd,capture_output=True,timeout=180)
            if result.returncode != 0: raise RuntimeError(result.stderr.decode(errors="ignore")[:500] or "LibreOffice 轉檔失敗")
            pdfs=list(pdf_tmp_dir.glob("*.pdf"))
            if not pdfs: raise RuntimeError("LibreOffice 未產生 PDF")
            if progress_id:
                set_upload_progress(progress_id, 17, "Office 轉檔完成", "開始將 PDF 轉成高解析教材頁面")
            return convert_pdf_to_images(pdfs[0], out_folder, progress_id=progress_id)
        finally:
            shutil.rmtree(profile_dir, ignore_errors=True); shutil.rmtree(pdf_tmp_dir, ignore_errors=True)

# ---------------------------------------------------------------------------
# API 路由
# ---------------------------------------------------------------------------
@app.get("/api/slides")
@login_required()
def api_list_slides():
    requested_area = normalize_area(request.args.get("area", DEFAULT_TRAINING_AREA))
    labels = category_label_map()
    builtin = []
    for m in load_meta():
        if not m.get("isBuiltin"):
            continue
        group = normalize_group(m.get("group", DEFAULT_GROUP))
        area = normalize_area(m.get("area", DEFAULT_TRAINING_AREA))
        if area != requested_area: continue
        category = m.get("category", "")
        builtin.append({
            **m,
            "group": group,
            "area": area,
            "viewerMode": "slides",
            "categoryLabel": labels.get(category, CATEGORY_LABELS.get(category, CATEGORY_LABELS[""])),
            "imageFolder": f"slides/{m['folder']}",
            "viewUrl": "",
        })
    uploaded = []
    for m in list_uploaded_materials(False):
        if m.get("area") != requested_area: continue
        category = m.get("category", "")
        uploaded.append({
            **m,
            "categoryLabel": labels.get(category, CATEGORY_LABELS.get(category, CATEGORY_LABELS[""])),
            "imageFolder": f"uploaded-slides/{m['folder']}",
            "previewUrl": (f"/material-preview/{m['id']}" if m.get("viewerMode") == "preview_pdf" else m.get("previewUrl", "")),
            "viewUrl": (f"/view/{m['id']}" if m.get("viewerMode") not in {"slides", "preview_pdf"} else ""),
        })
    return jsonify(builtin + uploaded)


@app.get("/api/slides/admin")
def api_admin_slides():
    denied = require_admin()
    if denied:
        return denied
    labels = category_label_map()
    items = []
    for m in load_meta():
        if m.get("isBuiltin"):
            group = normalize_group(m.get("group", DEFAULT_GROUP))
            category = m.get("category", "")
            items.append({**m, "group": group, "categoryLabel": labels.get(category, CATEGORY_LABELS.get(category, CATEGORY_LABELS[""]))})
    for m in list_uploaded_materials(True):
        category = m.get("category", "")
        items.append({**m, "categoryLabel": labels.get(category, CATEGORY_LABELS.get(category, CATEGORY_LABELS[""]))})
    return jsonify(items)


@app.get("/api/groups")
def api_list_groups():
    return jsonify([{"key": k, "label": v} for k, v in GROUPS.items()])

@app.get("/api/training-areas")
def api_training_areas():
    return jsonify([{"key": k, "label": v} for k, v in TRAINING_AREAS.items()])


@app.get("/uploaded-slides/<folder>/<path:filename>")
@login_required()
def uploaded_slide_image(folder, filename):
    # 僅允許以資料庫登記的 folder 存取，避免路徑穿越。
    if Path(folder).name != folder or Path(filename).name != filename:
        abort(404)
    entry = get_material(folder)
    if not entry or not entry.get("active"):
        abort(404)
    if entry.get("storageBackend") == "mega":
        meta=entry.get("storageMeta") or {}
        file_id=(meta.get("slideFiles") or {}).get(filename,"")
        if not file_id: abort(404)
        try: return _mega_send_file(file_id,filename,inline=True)
        except Exception as e: return jsonify({"error":f"MEGA 讀取失敗：{e}"}),502
    if entry.get("storageBackend") == "gdrive":
        meta = entry.get("storageMeta") or {}
        file_id = (meta.get("slideFiles") or {}).get(filename, "")
        if not file_id:
            file_id = gdrive_find_file_in_folder(entry.get("slidesPrefix", ""), filename)
        try:
            return gdrive_proxy_file(file_id, filename, inline=True)
        except Exception as e:
            return jsonify({"error": f"Google Drive 讀取失敗：{e}"}), 502
    if entry.get("storageBackend") == "oci":
        prefix = entry.get("slidesPrefix") or f"materials/{entry['id']}/slides"
        key = f"{prefix}/{filename}"
        try:
            return redirect(oci_presigned_get(key, download_name=filename, inline=True), code=302)
        except Exception as e:
            return jsonify({"error": f"Oracle Object Storage 讀取失敗：{e}"}), 502
    if entry.get("storageBackend") == "r2":
        prefix = entry.get("slidesPrefix") or f"materials/{entry['id']}/slides"
        key = f"{prefix}/{filename}"
        try:
            return redirect(r2_presigned_get(key, download_name=filename, inline=True), code=302)
        except Exception as e:
            return jsonify({"error": f"R2 讀取失敗：{e}"}), 502
    return send_from_directory(UPLOADED_SLIDES_DIR / folder, filename)


@app.get("/download/<slide_id>")
@login_required()
def download_slide(slide_id):
    # V5.3.8：學員端不再提供教材原始檔下載；僅管理者 API 權限可存取來源檔。
    denied = require_admin()
    if denied:
        return denied
    meta = load_meta()
    entry = next((m for m in meta if m["id"] == slide_id), None)
    if entry and entry.get("isBuiltin"):
        return send_from_directory(STATIC_DIR, entry["filename"], as_attachment=True, download_name=entry["filename"])
    entry = get_material(slide_id)
    if not entry:
        abort(404)
    if entry.get("storageBackend") == "mega":
        try: return _mega_send_file(entry.get("storageKey", ""),entry["filename"],inline=False)
        except Exception as e: return jsonify({"error":f"MEGA 下載失敗：{e}"}),502
    if entry.get("storageBackend") == "gdrive":
        try:
            return gdrive_proxy_file(entry.get("storageKey", ""), entry["filename"], inline=False)
        except Exception as e:
            return jsonify({"error": f"Google Drive 下載失敗：{e}"}), 502
    if entry.get("storageBackend") == "oci":
        key = entry.get("storageKey") or f"materials/{entry['id']}/{entry.get('storageFilename','source')}"
        try:
            return redirect(oci_presigned_get(key, download_name=entry["filename"], inline=False), code=302)
        except Exception as e:
            return jsonify({"error": f"Oracle Object Storage 下載連結產生失敗：{e}"}), 502
    if entry.get("storageBackend") == "r2":
        key = entry.get("storageKey") or f"materials/{entry['id']}/{entry.get('storageFilename','source')}"
        try:
            return redirect(r2_presigned_get(key, download_name=entry["filename"], inline=False), code=302)
        except Exception as e:
            return jsonify({"error": f"R2 下載連結產生失敗：{e}"}), 502
    path = UPLOAD_DIR / entry["id"] / entry["storageFilename"]
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=True, download_name=entry["filename"])


@app.get("/material-preview/<material_id>")
@login_required()
def material_preview(material_id):
    """V5.6.2 單一教材預覽檔。MEGA 首次讀取後短暫快取於 Render，後續直接 Range/conditional 回應。"""
    entry = get_material(material_id)
    if not entry or not entry.get("active"):
        abort(404)
    meta = entry.get("storageMeta") or {}
    if meta.get("previewMode") != "single_pdf":
        abort(404)
    if entry.get("storageBackend") != "mega":
        return jsonify({"error": "此教材的單一預覽目前僅支援 MEGA 儲存模式。"}), 409
    try:
        path = _mega_cached_preview(entry)
        resp = send_file(path, mimetype="application/pdf", as_attachment=False, download_name="teaching-preview.pdf", conditional=True, max_age=300)
        resp.headers["Content-Disposition"] = 'inline; filename="teaching-preview.pdf"'
        resp.headers["Cache-Control"] = "private, max-age=300"
        resp.headers["Accept-Ranges"] = "bytes"
        resp.headers["X-Preview-Mode"] = "single-pdf-range"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        resp.headers["X-Teaching-Use-Notice"] = quote(TEACHING_USAGE_NOTICE, safe="")
        return resp
    except Exception as e:
        return jsonify({"error": f"教材預覽讀取失敗：{e}"}), 502


@app.get("/view/<material_id>")
@login_required()
def view_material(material_id):
    entry = get_material(material_id)
    if not entry or not entry.get("active"):
        abort(404)
    # 已轉成逐頁影像的簡報/PDF/Office 教材只允許透過內建檢視器閱讀，
    # 不把原始來源檔暴露給學員端。
    if entry.get("viewerMode") == "slides" or int(entry.get("pageCount", 0) or 0) > 0:
        abort(403)
    if entry.get("storageBackend") == "mega":
        try: return _mega_send_file(entry.get("storageKey", ""),entry["filename"],inline=True)
        except Exception as e: return jsonify({"error":f"MEGA 檢視失敗：{e}"}),502
    if entry.get("storageBackend") == "gdrive":
        try:
            return gdrive_proxy_file(entry.get("storageKey", ""), entry["filename"], inline=True)
        except Exception as e:
            return jsonify({"error": f"Google Drive 檢視失敗：{e}"}), 502
    if entry.get("storageBackend") == "oci":
        key = entry.get("storageKey") or f"materials/{entry['id']}/{entry.get('storageFilename','source')}"
        try:
            return redirect(oci_presigned_get(key, download_name=entry["filename"], inline=True), code=302)
        except Exception as e:
            return jsonify({"error": f"Oracle Object Storage 檢視連結產生失敗：{e}"}), 502
    if entry.get("storageBackend") == "r2":
        key = entry.get("storageKey") or f"materials/{entry['id']}/{entry.get('storageFilename','source')}"
        try:
            return redirect(r2_presigned_get(key, download_name=entry["filename"], inline=True), code=302)
        except Exception as e:
            return jsonify({"error": f"R2 檢視連結產生失敗：{e}"}), 502
    path = UPLOAD_DIR / entry["id"] / entry["storageFilename"]
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=False, download_name=entry["filename"])


def _is_storage_full_error(exc):
    msg = str(exc or "").lower()
    return any(x in msg for x in ("免費模式已鎖定", "超過網站硬上限", "storage full", "quota exceeded", "insufficient storage"))


def _fallback_backend_ready():
    if not STORAGE_FAILOVER_ON_FULL:
        return ""
    fb = STORAGE_FALLBACK_BACKEND
    if fb == "gdrive" and gdrive_is_configured():
        return "gdrive"
    if fb == "r2" and r2_is_configured():
        return "r2"
    if fb == "oci" and oci_is_configured():
        return "oci"
    return ""



# ---------------------------------------------------------------------------
# V5.3.32：教材模組智慧分類（快速建立 / 單獨上傳共用）
# ---------------------------------------------------------------------------
MATERIAL_TYPE_VALUES = {"standard", "atlas", "infographic", "video", "troubleshooting", "sop", "case"}
_MATERIAL_CLASSIFY_KEYWORDS = {
    "sop": ["sop", "標準作業", "標準操作", "作業程序", "作業標準", "工作指引", "操作指引", "規範", "作業指引"],
    "troubleshooting": ["troubleshooting", "故障", "異常", "排除", "error", "alarm", "溶血", "檢體量不足", "量不足", "qc違反", "qc 異常", "westgard", "問題處理"],
    "case": ["案例", "case", "輸血反應", "discrepancy", "個案分析", "案例分析"],
    "infographic": ["資訊圖表", "infographic", "流程圖", "管制圖", "決策樹", "algorithm", "流程"],
    "atlas": ["atlas", "圖譜", "顯微鏡", "血球型態", "細胞型態", "尿液沉渣", "結晶", "寄生蟲", "蟲卵", "原蟲", "細菌形態", "真菌形態", "morphology", "microscopy"],
}

def _score_material_classification(text: str, weight: int = 1):
    t = (text or "").lower()
    scores = {k: 0 for k in _MATERIAL_CLASSIFY_KEYWORDS}
    for kind, words in _MATERIAL_CLASSIFY_KEYWORDS.items():
        for word in words:
            count = t.count(word.lower())
            if count:
                scores[kind] += min(4, count) * weight
    return scores

def _merge_classification_scores(*score_sets):
    out = {k: 0 for k in _MATERIAL_CLASSIFY_KEYWORDS}
    for scores in score_sets:
        for k, v in (scores or {}).items():
            if k in out:
                out[k] += int(v or 0)
    return out

def _extract_local_text_for_classification(path: Path):
    """Best-effort short text extraction for a newly uploaded local file."""
    ext = path.suffix.lower()
    tmp = None
    try:
        if ext == ".pdf":
            text = _extract_pdf_text(path)
        elif ext == ".pptx":
            text = _extract_pptx_text(path)
        elif ext == ".docx":
            text = _extract_docx_text(path)
        elif ext in {".txt", ".csv", ".srt", ".vtt"}:
            text = _extract_plain_text(path)
        elif ext in OFFICE_EXT:
            tmp = Path(tempfile.mkdtemp(prefix="material-classify-"))
            text = _extract_pdf_text(_convert_office_to_pdf_for_text(path, tmp))
        else:
            return ""
        return _clean_extracted_text(text)[:14000]
    except Exception:
        return ""
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

def _groq_classify_material(text: str, filename: str, title: str, desc: str):
    if not GROQ_API_KEY or not text or len(text) < 100:
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
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": GROQ_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.0, "response_format": {"type": "json_object"}, "max_completion_tokens": 250},
            timeout=AI_CLASSIFY_TIMEOUT_SECONDS,
        )
        if not resp.ok:
            return "", ""
        data = resp.json()
        raw = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        parsed = json.loads(raw)
        kind = str(parsed.get("materialType") or "").strip().lower()
        reason = str(parsed.get("reason") or "").strip()[:120]
        if kind in MATERIAL_TYPE_VALUES - {"video"}:
            return kind, reason
    except Exception:
        pass
    return "", ""

def classify_uploaded_material(path: Path, original_name: str, title: str = "", desc: str = "", text_override: str = None):
    """Return (resolved_type, method, reason). No paid fallback is ever invoked."""
    ext = path.suffix.lower()
    media_ext = AI_VIDEO_EXT | AI_AUDIO_EXT | AI_SUBTITLE_EXT
    if ext in media_ext:
        return "video", "副檔名判斷", "影音/字幕檔自動放入操作教學影片區"

    name_text = f"{original_name} {title}"
    # 圖片優先靠檔名語意判斷；無明確 Atlas/資訊圖表線索時仍作一般教材。
    if ext in AI_IMAGE_EXT:
        name_scores = _score_material_classification(name_text, 4)
        ranked = sorted(name_scores.items(), key=lambda kv: kv[1], reverse=True)
        if ranked and ranked[0][1] >= 4 and ranked[0][0] in {"atlas", "infographic", "troubleshooting", "case", "sop"}:
            return ranked[0][0], "檔名判斷", f"檔名符合 {ranked[0][0]} 特徵"
        return "standard", "預設分類", "一般圖片未偵測到明確圖譜/流程圖標籤"

    title_scores = _score_material_classification(f"{name_text} {desc}", 4)
    title_ranked = sorted(title_scores.items(), key=lambda kv: kv[1], reverse=True)
    # 檔名/名稱已非常明確時直接採用，避免 Office/PDF 為了分類而多轉檔一次。
    if title_ranked and title_ranked[0][1] >= 12 and (len(title_ranked) < 2 or title_ranked[0][1] >= title_ranked[1][1] + 4):
        return title_ranked[0][0], "檔名判斷", f"檔名關鍵字分數 {title_ranked[0][1]}"
    text = _clean_extracted_text(text_override)[:14000] if text_override is not None else _extract_local_text_for_classification(path)
    content_scores = _score_material_classification(text, 1)
    scores = _merge_classification_scores(title_scores, content_scores)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_kind, top_score = ranked[0] if ranked else ("standard", 0)
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    # 強而明確的關鍵字直接採用，避免浪費免費 AI 額度。
    if top_score >= 8 and top_score >= second_score + 3:
        return top_kind, "內容規則判斷", f"關鍵字分數 {top_score}"

    ai_kind, ai_reason = _groq_classify_material(text, original_name, title, desc)
    if ai_kind:
        return ai_kind, "Groq AI 內容判斷", ai_reason or "依教材內容判斷"

    if top_score >= 4 and top_score > second_score:
        return top_kind, "內容規則判斷", f"關鍵字分數 {top_score}"
    return "standard", "預設分類", "內容未呈現足夠明確的專用模組特徵"

@app.get("/api/slides/upload-progress/<progress_id>")
def api_upload_progress(progress_id):
    denied = require_admin()
    if denied: return denied
    path = _upload_progress_path(progress_id)
    if not path or not path.exists():
        return jsonify({"percent": 0, "stage": "等待上傳開始", "detail": ""})
    try:
        return jsonify(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return jsonify({"percent": 0, "stage": "讀取進度中", "detail": ""})


@app.get("/api/material-jobs")
def api_list_material_jobs():
    denied = require_admin()
    if denied:
        return denied
    try:
        limit = int(request.args.get("limit", 30) or 30)
    except Exception:
        limit = 30
    return jsonify({"jobs": list_material_jobs(limit), "backgroundEnabled": MATERIAL_BACKGROUND_JOBS})


@app.get("/api/material-jobs/<job_id>")
def api_get_material_job(job_id):
    denied = require_admin()
    if denied:
        return denied
    job = get_material_job(job_id, include_payload=False)
    if not job:
        return jsonify({"error": "找不到此背景教材工作"}), 404
    return jsonify(job)


@app.post("/api/material-jobs/upload")
def api_enqueue_material_job():
    """V5.7.0：只負責安全接收大型教材並排隊；轉檔與 MEGA 上傳交由 material_worker.py。"""
    denied = require_admin()
    if denied:
        return denied
    if not MATERIAL_BACKGROUND_JOBS:
        return jsonify({"error": "背景教材佇列未啟用，請改用同步上傳端點。"}), 409
    if "file" not in request.files:
        return jsonify({"error": "未收到檔案"}), 400
    file = request.files["file"]
    original_name = Path(file.filename or "untitled").name
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXT:
        return jsonify({"error": "不支援此檔案格式。可上傳簡報、PDF、Office 文件、圖片、影音、文字與 ZIP。"}), 400

    job_id = f"matjob-{uuid.uuid4().hex[:16]}"
    material_id = "upload-" + hashlib.sha256(job_id.encode("utf-8")).hexdigest()[:12]
    job_dir = MATERIAL_JOB_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    staged = job_dir / f"source{ext}"
    try:
        file.save(str(staged))
        source_bytes = staged.stat().st_size
        if source_bytes <= 0:
            raise ValueError("教材檔案為空白檔案")
        source_sha256 = _sha256_file(staged)
        payload = {
            "originalName": original_name,
            "title": request.form.get("title", "").strip()[:255],
            "desc": request.form.get("desc", "").strip()[:1000],
            "category": request.form.get("category", "").strip()[:100],
            "group": normalize_group(request.form.get("group", DEFAULT_GROUP)),
            "area": normalize_area(request.form.get("area", DEFAULT_TRAINING_AREA)),
            "courseId": request.form.get("courseId", "").strip()[:100],
            "materialType": request.form.get("materialType", "standard").strip().lower(),
            "atlasCategory": request.form.get("atlasCategory", "").strip()[:120],
            "atlasMagnification": request.form.get("atlasMagnification", "").strip()[:80],
            "atlasInterpretation": request.form.get("atlasInterpretation", "").strip()[:1000],
            "atlasClinical": request.form.get("atlasClinical", "").strip()[:1000],
            "atlasDifferential": request.form.get("atlasDifferential", "").strip()[:1000],
            "atlasNormality": request.form.get("atlasNormality", "").strip()[:40],
            "atlasTags": request.form.get("atlasTags", "").strip()[:300],
            "materialId": material_id,
            "sourceSha256": source_sha256,
        }
        create_material_job(job_id=job_id, payload=payload, staging_path=staged, source_sha256=source_sha256, source_bytes=source_bytes, material_id=material_id)
        clear_upload_progress(job_id)
        set_upload_progress(job_id, 9, "已加入背景佇列", "教材已安全接收，可離開此頁；背景 Worker 將自動轉檔、最佳化並送往雲端。")
        return jsonify({
            "accepted": True,
            "jobId": job_id,
            "materialId": material_id,
            "status": "queued",
            "sourceBytes": source_bytes,
            "sourceSha256": source_sha256,
            "statusUrl": f"/api/material-jobs/{job_id}",
            "message": "教材已安全接收並加入背景佇列，可離開此頁。",
        }), 202
    except Exception as e:
        shutil.rmtree(job_dir, ignore_errors=True)
        return jsonify({"error": f"教材排隊失敗：{e}"}), 400


@app.post("/api/material-jobs/<job_id>/retry")
def api_retry_material_job(job_id):
    denied = require_admin()
    if denied:
        return denied
    job = get_material_job(job_id, include_payload=True)
    if not job:
        return jsonify({"error": "找不到此背景教材工作"}), 404
    if job.get("status") not in {"failed", "cancelled"}:
        return jsonify({"error": "只有失敗或已取消的工作可以重新處理"}), 409
    staging = Path(job.get("stagingPath") or "")
    if not staging.exists():
        return jsonify({"error": "暫存原始檔已過期或不存在，請重新上傳教材。"}), 410
    now = _utc_now_iso()
    clear_upload_progress(job_id)
    _update_material_job(job_id, status="queued", available_at=now, finished_at="", attempts=0, error="", stage="重新排隊", detail="使用既有原始檔重新處理，不需要重新上傳；自動重試次數已重新計算", cancel_requested=False, worker_id="")
    set_upload_progress(job_id, 9, "重新排隊", "保留既有原始檔，等待背景 Worker 重新處理。")
    return jsonify({"ok": True, "job": get_material_job(job_id)})


@app.post("/api/material-jobs/<job_id>/cancel")
def api_cancel_material_job(job_id):
    denied = require_admin()
    if denied:
        return denied
    job = get_material_job(job_id, include_payload=True)
    if not job:
        return jsonify({"error": "找不到此背景教材工作"}), 404
    if job.get("status") == "processing":
        return jsonify({"error": "此工作已進入 LibreOffice／雲端處理階段，為避免留下半成品，請等待本次工作完成或失敗後再處理。"}), 409
    if job.get("status") in {"completed", "cancelled"}:
        return jsonify({"ok": True, "job": get_material_job(job_id)})
    now = _utc_now_iso()
    _update_material_job(job_id, status="cancelled", finished_at=now, cancel_requested=True, stage="已取消", detail="工作在開始轉檔前由管理者取消", worker_id="")
    set_upload_progress(job_id, 0, "已取消", "教材背景工作已取消；暫存原始檔會依保留期限自動清理。")
    return jsonify({"ok": True, "job": get_material_job(job_id)})


@app.post("/api/slides/upload")
def api_upload_slide():
    denied = require_admin()
    if denied:
        return denied
    if "file" not in request.files:
        return jsonify({"error": "未收到檔案"}), 400

    file = request.files["file"]
    progress_id = request.form.get("progressId", "").strip()[:80]
    if progress_id:
        clear_upload_progress(progress_id)
        set_upload_progress(progress_id, 2, "接收教材", f"正在接收 {Path(file.filename or '教材').name}")
    group = normalize_group(request.form.get("group", DEFAULT_GROUP))
    area = normalize_area(request.form.get("area", DEFAULT_TRAINING_AREA))
    category = request.form.get("category", "")
    course_id = request.form.get("courseId", "").strip()
    course = get_course(course_id) if course_id else None
    if not course or course.get("group") != group or course.get("area") != area:
        course_id = ""
    cat = get_quiz_category(category) if category else None
    if category and (not cat or cat["group"] != group or cat.get("area") != area):
        category = ""
    title = request.form.get("title", "").strip()
    desc = request.form.get("desc", "").strip()
    requested_material_type = request.form.get("materialType", "standard").strip().lower()
    if requested_material_type not in MATERIAL_TYPE_VALUES | {"auto"}:
        requested_material_type = "standard"
    material_type = requested_material_type
    raw_atlas_meta = {
        "category": request.form.get("atlasCategory", "").strip()[:120],
        "magnification": request.form.get("atlasMagnification", "").strip()[:80],
        "interpretation": request.form.get("atlasInterpretation", "").strip()[:1000],
        "clinical": request.form.get("atlasClinical", "").strip()[:1000],
        "differential": request.form.get("atlasDifferential", "").strip()[:1000],
        "normality": request.form.get("atlasNormality", "").strip()[:40],
        "tags": request.form.get("atlasTags", "").strip()[:300],
    }
    atlas_meta = {}
    classification_method = "人工指定"
    classification_reason = ""

    original_name = Path(file.filename or "untitled").name
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXT:
        return jsonify({"error": "不支援此檔案格式。可上傳簡報、PDF、Office 文件、圖片、影音、文字與 ZIP。"}), 400

    try:
        backend = active_material_backend()
    except Exception as e:
        return jsonify({"error": str(e)}), 503

    requested_material_id = request.form.get("materialId", "").strip().lower()
    slide_id = requested_material_id if re.fullmatch(r"upload-[a-f0-9]{12}", requested_material_id) else f"upload-{uuid.uuid4().hex[:12]}"
    existing_material = get_material(slide_id)
    if existing_material:
        # 背景 Worker 可能在資料庫寫入完成後、尚未更新 job 狀態前重啟；重試時直接視為完成，避免重複上雲。
        return jsonify(existing_material)
    material_dir = UPLOAD_DIR / slide_id
    out_folder = UPLOADED_SLIDES_DIR / slide_id
    material_dir.mkdir(parents=True, exist_ok=True)
    out_folder.mkdir(parents=True, exist_ok=True)
    saved_path = material_dir / f"source{ext}"
    file.save(str(saved_path))
    if progress_id:
        set_upload_progress(progress_id, 8, "教材已接收", f"{original_name} 已上傳至伺服器，開始處理")

    storage_meta = {}
    preview_path = material_dir / "preview.pdf"
    try:
        single_preview = bool(backend == "mega" and MATERIAL_SINGLE_PREVIEW and (ext == ".pdf" or ext in OFFICE_EXT))
        preview_ready = False
        page_count = 0
        classification_text = None
        # 自動分類 + 單一預覽時先建立 preview.pdf，分類直接讀同一份 PDF，避免舊 Office 檔被 LibreOffice 轉兩次。
        if requested_material_type == "auto" and single_preview:
            page_count = build_single_preview_pdf(saved_path, preview_path, progress_id=progress_id)
            preview_ready = True
            try:
                classification_text = _extract_pdf_text(preview_path)
            except Exception:
                classification_text = None
        if requested_material_type == "auto":
            if progress_id:
                set_upload_progress(progress_id, 47 if preview_ready else 9, "智慧分類教材", "正在依檔名、教材內容與可用的免費 AI 判斷教材模組")
            material_type, classification_method, classification_reason = classify_uploaded_material(saved_path, original_name, title, desc, text_override=classification_text)
        else:
            material_type = requested_material_type
        if material_type not in MATERIAL_TYPE_VALUES:
            material_type = "standard"
        atlas_meta = raw_atlas_meta if material_type == "atlas" else {}
        if progress_id and requested_material_type == "auto":
            set_upload_progress(progress_id, 48 if preview_ready else 11, "教材分類完成", f"{classification_method}：{material_type}{(' · '+classification_reason) if classification_reason else ''}")

        if single_preview:
            if not preview_ready:
                page_count = build_single_preview_pdf(saved_path, preview_path, progress_id=progress_id)
            slide_format = "pdf"
        elif ext == ".pdf":
            page_count = convert_pdf_to_images(saved_path, out_folder, progress_id=progress_id)
            slide_format = _slide_format(out_folder, page_count)
        elif ext in OFFICE_EXT:
            page_count = convert_office_to_images(saved_path, out_folder, progress_id=progress_id)
            slide_format = _slide_format(out_folder, page_count)
        else:
            page_count = 0
            slide_format = ""
            if progress_id:
                set_upload_progress(progress_id, 50, "無需轉換", "此教材將直接上傳雲端儲存")

        source_bytes = saved_path.stat().st_size if saved_path.exists() else 0
        supplied_hash = request.form.get("sourceSha256", "").strip().lower()
        source_sha256 = supplied_hash if re.fullmatch(r"[a-f0-9]{64}", supplied_hash) else _sha256_file(saved_path)
        slide_bytes = (preview_path.stat().st_size if single_preview and preview_path.exists() else sum(x.stat().st_size for x in out_folder.glob("slide-*.*"))) if page_count else 0
        storage_key = ""
        slides_prefix = ""
        storage_meta = {"slideFormat": slide_format, "sourceBytes": source_bytes, "slideBytes": slide_bytes, "sourceSha256": source_sha256}
        if single_preview:
            storage_meta.update({"previewMode": "single_pdf", "previewFilename": "preview.pdf", "previewBytes": slide_bytes})
        original_backend = backend
        try:
            if backend == "mega":
                if single_preview:
                    storage_key, slides_prefix, remote_meta = upload_material_preview_to_mega(slide_id, saved_path, preview_path, page_count, progress_id=progress_id)
                else:
                    storage_key, slides_prefix, remote_meta = upload_material_tree_to_mega(slide_id,saved_path,out_folder,page_count,progress_id=progress_id)
                storage_meta.update(remote_meta or {})
            elif backend == "oci":
                storage_key, slides_prefix = upload_material_tree_to_oci(slide_id, saved_path, out_folder, page_count)
            elif backend == "gdrive":
                storage_key, slides_prefix, remote_meta = upload_material_tree_to_gdrive(
                    slide_id, saved_path, out_folder, page_count, original_name=original_name
                )
                storage_meta.update(remote_meta or {})
            elif backend == "r2":
                storage_key, slides_prefix = upload_material_tree_to_r2(slide_id, saved_path, out_folder, page_count)
        except Exception as primary_error:
            fallback = _fallback_backend_ready() if backend == "mega" and _is_storage_full_error(primary_error) else ""
            if not fallback:
                raise
            # 備援後端仍沿用舊逐頁介面；只有真的 failover 才額外產生頁面，正常 MEGA 路徑不付出這筆成本。
            if single_preview and page_count > 0:
                if progress_id:
                    set_upload_progress(progress_id, 50, "啟用雲端備援", f"MEGA 容量不足，正在為 {fallback} 建立相容閱讀頁面")
                shutil.rmtree(out_folder, ignore_errors=True); out_folder.mkdir(parents=True, exist_ok=True)
                convert_pdf_to_images(preview_path, out_folder, progress_id=progress_id)
                slide_format = _slide_format(out_folder, page_count)
                slide_bytes = sum(x.stat().st_size for x in out_folder.glob("slide-*.*"))
                for k in ("previewMode","previewFilename","previewBytes","previewFileId","pageCount"):
                    storage_meta.pop(k, None)
                storage_meta.update({"slideFormat": slide_format, "slideBytes": slide_bytes})
                single_preview = False
            backend = fallback
            storage_key = ""; slides_prefix = ""; storage_meta.update({"failoverFrom": original_backend, "failoverReason": "primary_storage_full"})
            if backend == "gdrive":
                storage_key, slides_prefix, gdmeta = upload_material_tree_to_gdrive(slide_id, saved_path, out_folder, page_count, original_name=original_name)
                storage_meta.update(gdmeta or {})
            elif backend == "r2":
                storage_key, slides_prefix = upload_material_tree_to_r2(slide_id, saved_path, out_folder, page_count)
            elif backend == "oci":
                storage_key, slides_prefix = upload_material_tree_to_oci(slide_id, saved_path, out_folder, page_count)
            else:
                raise primary_error

        if progress_id:
            set_upload_progress(progress_id, 94, "寫入教材資料", "雲端檔案已完成，正在同步 Supabase/資料庫")
        entry = {
            "id": slide_id,
            "filename": original_name,
            "title": title or original_name,
            "description": desc or "管理者上傳之教育訓練補充教材",
            "category": category,
            "group_key": group,
            "training_area": area,
            "course_id": course_id,
            "folder": slide_id,
            "page_count": page_count,
            "date_added": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "storage_filename": saved_path.name,
            "storage_backend": backend,
            "storage_key": storage_key,
            "slides_prefix": slides_prefix,
            "storage_meta": json.dumps(storage_meta, ensure_ascii=False),
            "material_type": material_type,
            "atlas_meta": json.dumps(atlas_meta, ensure_ascii=False),
            "active": True,
        }
        conn, kind = _db_conn()
        try:
            vals = (entry["id"], entry["filename"], entry["title"], entry["description"], entry["category"], entry["group_key"], entry["training_area"], entry["course_id"], entry["folder"], entry["page_count"], entry["date_added"], entry["storage_filename"], entry["storage_backend"], entry["storage_key"], entry["slides_prefix"], entry["storage_meta"], entry["material_type"], entry["atlas_meta"], entry["active"])
            if kind == "postgres":
                conn.execute("""INSERT INTO materials (id,filename,title,description,category,group_key,training_area,course_id,folder,page_count,date_added,storage_filename,storage_backend,storage_key,slides_prefix,storage_meta,material_type,atlas_meta,active) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", vals)
            else:
                conn.execute("""INSERT INTO materials (id,filename,title,description,category,group_key,training_area,course_id,folder,page_count,date_added,storage_filename,storage_backend,storage_key,slides_prefix,storage_meta,material_type,atlas_meta,active) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", vals)
        finally:
            conn.close()

        # V5.7：MEGA 單一預覽在剛上傳完成時直接暖入 Render cache，第一次學員開啟不必再從 MEGA 整份抓一次。
        if backend == "mega" and single_preview and preview_path.exists():
            try:
                cache_target = PREVIEW_CACHE_DIR / (re.sub(r"[^A-Za-z0-9_-]", "_", str(slide_id)) + ".pdf")
                shutil.copy2(preview_path, cache_target)
                _preview_cache_cleanup(protect=cache_target)
            except Exception:
                pass
        # 雲端已成功保存後，Render 本機只扮演暫存/轉檔空間，立即清掉避免佔用磁碟。
        if backend in {"r2", "gdrive", "oci", "mega"}:
            shutil.rmtree(material_dir, ignore_errors=True)
            shutil.rmtree(out_folder, ignore_errors=True)

        if progress_id:
            set_upload_progress(progress_id, 100, "教材建立完成", "教材、單一預覽檔／閱讀頁與資料庫皆已完成同步")
        return jsonify({
            "id": slide_id, "filename": original_name, "title": entry["title"], "desc": entry["description"],
            "category": category, "group": group, "area": area, "courseId": course_id, "folder": slide_id, "pageCount": page_count, "isBuiltin": False,
            "dateAdded": entry["date_added"], "active": True, "storageBackend": backend, "storageMeta": storage_meta, "slideFormat": slide_format, "materialType": material_type, "atlasMeta": atlas_meta,
            "classificationMethod": classification_method, "classificationReason": classification_reason,
            "categoryLabel": resolve_category_label(category, group),
            "imageFolder": f"uploaded-slides/{slide_id}",
            "previewUrl": (f"/material-preview/{slide_id}" if (storage_meta or {}).get("previewMode") == "single_pdf" else ""),
            "viewerMode": ("preview_pdf" if (storage_meta or {}).get("previewMode") == "single_pdf" else ("slides" if page_count > 0 else "download")),
            "viewUrl": ("" if page_count > 0 else f"/view/{slide_id}")
        })
    except Exception as e:
        if progress_id:
            set_upload_progress(progress_id, 0, "教材建立失敗", str(e)[:500])
        # 遠端上傳失敗時盡量回滾；Google Drive 上傳函式本身也會清理其教材資料夾。
        if backend == "mega":
            try:
                mega_destroy((storage_meta or {}).get("folderId", ""))
            except Exception:
                pass
        if backend == "r2":
            try:
                r2_delete_prefix(f"materials/{slide_id}/")
            except Exception:
                pass
        shutil.rmtree(material_dir, ignore_errors=True)
        shutil.rmtree(out_folder, ignore_errors=True)
        return jsonify({"error": f"教材處理/儲存失敗：{e}", "stage": "教材建立失敗", "detail": str(e)[:500], "retryable": True}), 500


@app.patch("/api/slides/<slide_id>")
def api_update_slide(slide_id):
    denied = require_admin()
    if denied:
        return denied
    entry = get_material(slide_id)
    if not entry:
        return jsonify({"error": "找不到可編輯的上傳教材"}), 404
    data = request.get_json(silent=True) or {}
    title = str(data.get("title", entry["title"])).strip()[:255]
    desc = str(data.get("desc", entry.get("desc", ""))).strip()[:1000]
    material_type = str(data.get("materialType", entry.get("materialType", "standard"))).strip().lower()
    if material_type not in {"standard", "atlas", "infographic", "video", "troubleshooting", "sop", "case"}: material_type = "standard"
    atlas_meta = data.get("atlasMeta", entry.get("atlasMeta", {}))
    if not isinstance(atlas_meta, dict): atlas_meta = {}
    atlas_meta = {k: str(atlas_meta.get(k, "")).strip()[:1000] for k in ("category","magnification","interpretation","clinical","differential","normality","tags")} if material_type == "atlas" else {}
    group = normalize_group(str(data.get("group", entry.get("group", DEFAULT_GROUP))))
    area = normalize_area(str(data.get("area", entry.get("area", DEFAULT_TRAINING_AREA))))
    category = str(data.get("category", entry.get("category", "")))
    course_id = str(data.get("courseId", entry.get("courseId", ""))).strip()
    course = get_course(course_id) if course_id else None
    if not course or course.get("group") != group or course.get("area") != area:
        course_id = ""
    active = bool(data.get("active", entry.get("active", True)))
    cat = get_quiz_category(category) if category else None
    if category and (not cat or cat["group"] != group or cat.get("area") != area):
        category = ""
    conn, kind = _db_conn()
    try:
        if kind == "postgres":
            conn.execute("UPDATE materials SET title=%s, description=%s, category=%s, group_key=%s, training_area=%s, course_id=%s, material_type=%s, atlas_meta=%s, active=%s WHERE id=%s", (title, desc, category, group, area, course_id, material_type, json.dumps(atlas_meta, ensure_ascii=False), active, slide_id))
        else:
            conn.execute("UPDATE materials SET title=?, description=?, category=?, group_key=?, training_area=?, course_id=?, material_type=?, atlas_meta=?, active=? WHERE id=?", (title, desc, category, group, area, course_id, material_type, json.dumps(atlas_meta, ensure_ascii=False), int(active), slide_id))
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.delete("/api/slides/<slide_id>")
def api_delete_slide(slide_id):
    denied = require_admin()
    if denied:
        return denied
    entry = get_material(slide_id)
    if not entry:
        return jsonify({"error": "內建教材不能從後台刪除，或找不到此教材"}), 404
    if entry.get("storageBackend") == "gdrive":
        try:
            gdrive_delete_material(entry)
        except Exception as e:
            return jsonify({"error": f"Google Drive 教材刪除失敗：{e}"}), 502
    elif entry.get("storageBackend") == "mega":
        mega_destroy((entry.get("storageMeta") or {}).get("folderId", ""))
    elif entry.get("storageBackend") == "oci":
        try:
            oci_delete_prefix(f"materials/{entry['id']}/")
        except Exception as e:
            return jsonify({"error": f"Oracle Object Storage 教材刪除失敗：{e}"}), 502
    elif entry.get("storageBackend") == "r2":
        try:
            r2_delete_prefix(f"materials/{entry['id']}/")
        except Exception as e:
            return jsonify({"error": f"R2 教材刪除失敗：{e}"}), 502
    else:
        shutil.rmtree(UPLOAD_DIR / entry["id"], ignore_errors=True)
        shutil.rmtree(UPLOADED_SLIDES_DIR / entry["folder"], ignore_errors=True)
    # 同步清除 Render 單一預覽快取；只刪暫存，不影響其他教材。
    try:
        cache_file = PREVIEW_CACHE_DIR / (re.sub(r"[^A-Za-z0-9_-]", "_", str(slide_id)) + ".pdf")
        if cache_file.exists(): cache_file.unlink()
    except OSError:
        pass
    conn, kind = _db_conn()
    try:
        if kind == "postgres":
            conn.execute("DELETE FROM materials WHERE id=%s", (slide_id,))
        else:
            conn.execute("DELETE FROM materials WHERE id=?", (slide_id,))
    finally:
        conn.close()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# V5.3 儲存狀態 / Google Drive 搬移
# ---------------------------------------------------------------------------
@app.get("/api/storage-status")
def api_storage_status():
    denied = require_admin()
    if denied:
        return denied
    force = request.args.get("refresh", "").strip().lower() in {"1", "true", "yes"}
    now = time.time()
    with _STORAGE_STATUS_LOCK:
        cached = _STORAGE_STATUS_CACHE.get("data")
        cached_at = float(_STORAGE_STATUS_CACHE.get("at", 0) or 0)
        if not force and cached is not None and (now - cached_at) < STORAGE_STATUS_CACHE_SECONDS:
            return jsonify(cached)

    try:
        backend = active_material_backend()
        error = ""
    except Exception as e:
        backend = "error"
        error = str(e)

    # 只檢查目前真正使用中的雲端。舊 Google / OCI 環境變數即使仍存在，也不拖慢 MEGA 後台。
    drive_info = None
    drive_error = ""
    if backend == "gdrive" and gdrive_is_configured():
        try:
            drive_info = gdrive_check()
        except Exception as e:
            drive_error = str(e)
            if not error:
                error = drive_error

    mats = list_uploaded_materials(True)
    mega_space_info = None
    mega_status_error = ""
    if backend == "mega" and mega_is_configured():
        try:
            _sp = mega_storage_space()
            mega_space_info = {"usedGb": round(_sp["used"]/1024**3,3), "totalGb": round(_sp["total"]/1024**3,3)}
        except Exception as e:
            mega_status_error = str(e)
            if not error:
                error = mega_status_error

    oci_used = None
    if backend == "oci" and oci_is_configured():
        try:
            oci_used = round(oci_bucket_usage_bytes()/1024**3, 3)
        except Exception as e:
            if not error:
                error = str(e)

    data = {
        "configuredMode": MATERIAL_STORAGE_BACKEND,
        "activeBackend": backend,
        "fallbackBackend": STORAGE_FALLBACK_BACKEND,
        "failoverOnFull": STORAGE_FAILOVER_ON_FULL,
        "fallbackReady": bool(_fallback_backend_ready()),
        "gdriveConfigured": gdrive_is_configured(),
        "gdriveConnected": bool(drive_info),
        "gdriveFolderName": (drive_info or {}).get("name", ""),
        "megaConfigured": mega_is_configured(),
        "megaFreeOnly": FREE_ONLY_MODE,
        "megaFreeLimitGb": MEGA_STORAGE_LIMIT_GB,
        "megaSpace": mega_space_info,
        "megaError": mega_status_error,
        "ociConfigured": oci_is_configured(),
        "ociFreeOnly": FREE_ONLY_MODE,
        "ociFreeLimitGb": OCI_FREE_LIMIT_GB,
        "ociUsedGb": oci_used,
        "r2Configured": r2_is_configured(),
        "presignSeconds": OCI_PRESIGN_SECONDS if backend == "oci" else R2_PRESIGN_SECONDS,
        "materials": {
            "mega": sum(1 for m in mats if m.get("storageBackend") == "mega"),
            "oci": sum(1 for m in mats if m.get("storageBackend") == "oci"),
            "gdrive": sum(1 for m in mats if m.get("storageBackend") == "gdrive"),
            "r2": sum(1 for m in mats if m.get("storageBackend") == "r2"),
            "local": sum(1 for m in mats if m.get("storageBackend") not in {"mega", "oci", "gdrive", "r2"}),
        },
        "error": error,
        "cachedSeconds": STORAGE_STATUS_CACHE_SECONDS,
    }
    with _STORAGE_STATUS_LOCK:
        _STORAGE_STATUS_CACHE.update({"at": time.time(), "data": data})
    return jsonify(data)


@app.post("/api/storage/migrate-to-gdrive")
def api_migrate_materials_to_gdrive():
    denied = require_admin()
    if denied:
        return denied
    if not gdrive_is_configured():
        return jsonify({"error": "Google Drive 尚未設定完成，無法搬移。請先設定 OAuth refresh token 與 GDRIVE_FOLDER_ID。"}), 400
    try:
        gdrive_check()
    except Exception as e:
        return jsonify({"error": f"Google Drive 連線/資料夾檢查失敗：{e}"}), 400

    migrated, skipped, failed = 0, [], []
    for entry in list_uploaded_materials(True):
        old_backend = entry.get("storageBackend", "local")
        if old_backend == "gdrive":
            continue
        temp_root = None
        source = None
        slides = None
        try:
            if old_backend == "r2":
                if not r2_is_configured():
                    raise RuntimeError("此教材在 R2，但目前 Render 未設定 R2 金鑰，無法讀出後搬移。")
                temp_root = TMP_DIR / f"migrate-{entry['id']}-{uuid.uuid4().hex[:6]}"
                source_dir = temp_root / "source"
                slides = temp_root / "slides"
                source_dir.mkdir(parents=True, exist_ok=True); slides.mkdir(parents=True, exist_ok=True)
                ext = Path(entry.get("storageFilename") or entry.get("filename") or "source.bin").suffix or ".bin"
                source = source_dir / f"source{ext}"
                _download_material_from_r2(entry, source, slides)
            else:
                source = UPLOAD_DIR / entry["id"] / entry.get("storageFilename", "")
                slides = UPLOADED_SLIDES_DIR / entry.get("folder", entry["id"])
                if not source.exists():
                    skipped.append({"id": entry["id"], "title": entry.get("title", ""), "reason": "本機原始檔不存在"})
                    continue

            key, prefix, meta = upload_material_tree_to_gdrive(
                entry["id"], source, slides, entry.get("pageCount", 0), original_name=entry.get("filename")
            )
            conn, kind = _db_conn()
            try:
                meta_json = json.dumps(meta, ensure_ascii=False)
                if kind == "postgres":
                    conn.execute("UPDATE materials SET storage_backend=%s, storage_key=%s, slides_prefix=%s, storage_meta=%s WHERE id=%s", ("gdrive", key, prefix, meta_json, entry["id"]))
                else:
                    conn.execute("UPDATE materials SET storage_backend=?, storage_key=?, slides_prefix=?, storage_meta=? WHERE id=?", ("gdrive", key, prefix, meta_json, entry["id"]))
            finally:
                conn.close()

            if old_backend == "r2":
                r2_delete_prefix(f"materials/{entry['id']}/")
            else:
                shutil.rmtree(UPLOAD_DIR / entry["id"], ignore_errors=True)
                shutil.rmtree(UPLOADED_SLIDES_DIR / entry.get("folder", entry["id"]), ignore_errors=True)
            migrated += 1
        except Exception as e:
            failed.append({"id": entry["id"], "title": entry.get("title", ""), "reason": str(e)[:500]})
        finally:
            if temp_root:
                shutil.rmtree(temp_root, ignore_errors=True)
    return jsonify({"ok": len(failed) == 0, "migrated": migrated, "skipped": skipped, "failed": failed})


@app.post("/api/storage/migrate-to-r2")
def api_migrate_materials_to_r2():
    denied = require_admin()
    if denied:
        return denied
    if not r2_is_configured():
        return jsonify({"error": "R2 尚未設定完成，無法搬移。"}), 400
    migrated, skipped, failed = 0, [], []
    for entry in list_uploaded_materials(True):
        if entry.get("storageBackend") == "r2":
            continue
        if entry.get("storageBackend") == "gdrive":
            skipped.append({"id": entry["id"], "title": entry.get("title", ""), "reason": "目前已在 Google Drive；R2 搬移工具僅處理本機教材"})
            continue
        source = UPLOAD_DIR / entry["id"] / entry.get("storageFilename", "")
        slides = UPLOADED_SLIDES_DIR / entry.get("folder", entry["id"])
        if not source.exists():
            skipped.append({"id": entry["id"], "title": entry.get("title", ""), "reason": "本機原始檔不存在"})
            continue
        try:
            key, prefix = upload_material_tree_to_r2(entry["id"], source, slides, entry.get("pageCount", 0))
            conn, kind = _db_conn()
            try:
                if kind == "postgres":
                    conn.execute("UPDATE materials SET storage_backend=%s, storage_key=%s, slides_prefix=%s WHERE id=%s", ("r2", key, prefix, entry["id"]))
                else:
                    conn.execute("UPDATE materials SET storage_backend=?, storage_key=?, slides_prefix=? WHERE id=?", ("r2", key, prefix, entry["id"]))
            finally:
                conn.close()
            shutil.rmtree(UPLOAD_DIR / entry["id"], ignore_errors=True)
            shutil.rmtree(slides, ignore_errors=True)
            migrated += 1
        except Exception as e:
            try:
                r2_delete_prefix(f"materials/{entry['id']}/")
            except Exception:
                pass
            failed.append({"id": entry["id"], "title": entry.get("title", ""), "reason": str(e)[:300]})
    return jsonify({"ok": len(failed) == 0, "migrated": migrated, "skipped": skipped, "failed": failed})



# ---------------------------------------------------------------------------
# V5.3.7 AI 智慧出題：從已上傳教材擷取文字 → 產生候選題 → 管理者審核後匯入
# ---------------------------------------------------------------------------
def active_ai_provider():
    provider = AI_PROVIDER if AI_PROVIDER in {"groq", "gemini", "openai", "auto"} else "groq"
    if FREE_ONLY_MODE:
        # 免費鎖定：不自動切到 OpenAI 等可能計費 provider。
        return "groq" if provider in {"auto","groq"} else provider
    if provider == "auto":
        if GROQ_API_KEY: return "groq"
        if GEMINI_API_KEY and google_genai is not None: return "gemini"
        if OPENAI_API_KEY: return "openai"
        return "groq"
    return provider

def ai_question_is_configured():
    provider = active_ai_provider()
    if provider == "groq": return bool(GROQ_API_KEY)
    if provider == "gemini": return bool(GEMINI_API_KEY and google_genai is not None)
    return bool(OPENAI_API_KEY)

def ai_model_name():
    provider=active_ai_provider()
    if provider=="groq": return GROQ_MODEL
    return GEMINI_MODEL if provider=="gemini" else OPENAI_MODEL


def _material_source_to_temp(entry):
    """把教材原始檔取回暫存目錄。回傳 (temp_root, source_path)。"""
    ext = Path(entry.get("filename") or entry.get("storageFilename") or "source.bin").suffix.lower() or ".bin"
    temp_root = TMP_DIR / f"aiq-{entry['id']}-{uuid.uuid4().hex[:8]}"
    temp_root.mkdir(parents=True, exist_ok=True)
    source = temp_root / f"source{ext}"
    backend = (entry.get("storageBackend") or "local").lower()
    if backend == "mega":
        file_id=entry.get("storageKey") or (entry.get("storageMeta") or {}).get("sourceFileId","")
        if not file_id: raise RuntimeError("此教材缺少 MEGA 原始檔 ID。")
        mega_download_file(file_id,source)
    elif backend == "gdrive":
        file_id = entry.get("storageKey") or (entry.get("storageMeta") or {}).get("sourceFileId", "")
        if not file_id:
            raise RuntimeError("此教材缺少 Google Drive 原始檔 ID。")
        gdrive_download_to_path(file_id, source)
    elif backend == "oci":
        if not oci_is_configured():
            raise RuntimeError("此教材位於 Oracle Object Storage，但目前伺服器未設定 OCI 金鑰。")
        key = entry.get("storageKey") or f"materials/{entry['id']}/source{ext}"
        oci_client().download_file(OCI_BUCKET_NAME, key, str(source))
    elif backend == "r2":
        if not r2_is_configured():
            raise RuntimeError("此教材位於 R2，但目前伺服器未設定 R2 金鑰。")
        key = entry.get("storageKey") or f"materials/{entry['id']}/source{ext}"
        r2_client().download_file(R2_BUCKET_NAME, key, str(source))
    else:
        local = UPLOAD_DIR / entry["id"] / entry.get("storageFilename", f"source{ext}")
        if not local.exists():
            # 舊資料有時 storageFilename 不一致，嘗試目錄內第一個 source.*
            matches = list((UPLOAD_DIR / entry["id"]).glob("source.*")) if (UPLOAD_DIR / entry["id"]).exists() else []
            local = matches[0] if matches else local
        if not local.exists():
            raise RuntimeError("Render 本機找不到此教材原始檔，請重新上傳教材。")
        shutil.copy2(local, source)
    return temp_root, source


def _clean_extracted_text(text):
    text = (text or "").replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_pdf_text(path: Path):
    if pymupdf is None:
        raise RuntimeError("伺服器缺少 PyMuPDF，無法擷取 PDF 文字。")
    out = []
    with pymupdf.open(str(path)) as doc:
        for i, page in enumerate(doc, 1):
            txt = _clean_extracted_text(page.get_text("text"))
            if txt:
                out.append(f"[第 {i} 頁]\n{txt}")
    return "\n\n".join(out)


def _extract_pptx_text(path: Path):
    out = []
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
        names.sort(key=lambda n: int(re.search(r"slide(\d+)\.xml", n).group(1)))
        ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
        for idx, name in enumerate(names, 1):
            root_xml = ET.fromstring(z.read(name))
            parts = [el.text.strip() for el in root_xml.findall('.//a:t', ns) if el.text and el.text.strip()]
            if parts:
                out.append(f"[投影片 {idx}]\n" + "\n".join(parts))
    return "\n\n".join(out)


def _extract_docx_text(path: Path):
    with zipfile.ZipFile(path) as z:
        xml = ET.fromstring(z.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paras = []
    for p in xml.findall('.//w:p', ns):
        parts = [t.text for t in p.findall('.//w:t', ns) if t.text]
        line = _clean_extracted_text("".join(parts))
        if line:
            paras.append(line)
    return "\n".join(paras)


def _extract_plain_text(path: Path):
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _convert_office_to_pdf_for_text(source: Path, temp_root: Path):
    out_dir = temp_root / "pdf"
    out_dir.mkdir(parents=True, exist_ok=True)
    profile_dir = temp_root / "lo-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    cmd = [SOFFICE_BIN, "--headless", "--norestore", f"-env:UserInstallation=file:///{profile_dir.as_posix()}", "--convert-to", "pdf", "--outdir", str(out_dir), str(source)]
    with conversion_lock:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180, check=False)
    pdfs = list(out_dir.glob("*.pdf"))
    if proc.returncode != 0 or not pdfs:
        msg = (proc.stderr or proc.stdout or b"").decode("utf-8", errors="ignore")[-800:]
        raise RuntimeError(f"LibreOffice 無法將教材轉成可讀文字的 PDF：{msg or '轉檔失敗'}")
    return pdfs[0]


def extract_material_text_for_ai(entry):
    if entry.get("isBuiltin"):
        raise RuntimeError("內建舊教材沒有保留原始 PPT/PDF 檔，請先從後台重新上傳該教材後再使用 AI 出題。")
    temp_root, source = _material_source_to_temp(entry)
    try:
        ext = source.suffix.lower()
        if ext == ".pdf":
            text = _extract_pdf_text(source)
        elif ext == ".pptx":
            text = _extract_pptx_text(source)
        elif ext == ".docx":
            text = _extract_docx_text(source)
        elif ext in {".txt", ".csv", ".srt", ".vtt"}:
            text = _extract_plain_text(source)
        elif ext in OFFICE_EXT:
            text = _extract_pdf_text(_convert_office_to_pdf_for_text(source, temp_root))
        else:
            raise RuntimeError("目前文字擷取支援 PPT/PPTX、PDF、Word、Excel、ODP/ODT/ODS、TXT、CSV、SRT、VTT。若使用 Gemini，圖片、影音可直接交由多模態模型理解。")
        text = _clean_extracted_text(text)
        if len(text) < 80:
            raise RuntimeError("教材可擷取的文字太少，可能主要是圖片/掃描頁。請改用含文字的 PPT/PDF，或另外上傳文字版教材。")
        return text[:AI_SOURCE_MAX_CHARS], len(text)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def _response_output_text(data):
    chunks = []
    for item in data.get("output", []) if isinstance(data, dict) else []:
        if not isinstance(item, dict):
            continue
        for c in item.get("content", []) or []:
            if isinstance(c, dict) and c.get("type") in {"output_text", "text"} and isinstance(c.get("text"), str):
                chunks.append(c["text"])
    if chunks:
        return "".join(chunks)
    # 向前/向後相容：遞迴尋找 output_text/text
    def walk(x):
        if isinstance(x, dict):
            if x.get("type") == "output_text" and isinstance(x.get("text"), str):
                chunks.append(x["text"])
            for v in x.values(): walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(data)
    return "".join(chunks)


def generate_openai_question_candidates(source_text, *, count, qtype, difficulty, focus, source_title):
    if not ai_question_is_configured():
        raise RuntimeError("OpenAI 智慧出題尚未設定。請在 Render Environment 新增 OPENAI_API_KEY。")
    count = max(1, min(AI_MAX_QUESTIONS, int(count or 5)))
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
                        "sourceHint": {"type": "string"}
                    },
                    "required": ["questionType", "question", "options", "correct", "tag", "explanation", "sourceHint"],
                    "additionalProperties": False
                }
            }
        },
        "required": ["questions"],
        "additionalProperties": False
    }
    type_rule = {
        "choice": "全部產生選擇題。每題必須有 4 個不同且合理的選項，且只有 1 個正確答案。",
        "essay": "全部產生問答題。options 必須是空陣列，correct 固定為 0；explanation 請提供評分參考重點。",
        "mixed": "混合產生選擇題與問答題；若題數允許，至少各有 1 題。選擇題 4 選 1；問答題 options 為空陣列。"
    }[qtype]
    diff_rule = {
        "basic": "難度：基礎。以關鍵規範、名詞、步驟辨識為主。",
        "standard": "難度：標準。以流程順序、操作判斷、異常處置、QC/通報重點與應用為主。",
        "advanced": "難度：進階。以情境判斷、步驟錯誤辨識、故障排除與跨段落整合為主，但答案仍必須能由教材直接支持。"
    }[difficulty]
    focus_rule = f"額外出題重點：{focus}" if focus else "請平均涵蓋教材中的重要段落，避免所有題目集中在同一小節。"
    system_prompt = (
        "你是醫院檢驗科教育訓練的考題草擬助手。只能依照使用者提供的教材文字出題，不得使用教材外的醫學常識補充答案，"
        "不得自行更正教材、推測未寫明的數值或流程。若教材沒有明確支持某個答案，就不要出那一題。"
        "題目要適合院內教育訓練與能力考核，避免模稜兩可、雙重否定、只有語意陷阱的題目。"
        "詳解要指出教材中支持答案的重點；sourceHint 請填最接近的頁碼/投影片標記或教材段落線索。"
    )
    user_prompt = f"""教材名稱：{source_title}\n需要題數：{count}\n{type_rule}\n{diff_rule}\n{focus_rule}\n\n【教材文字開始】\n{source_text}\n【教材文字結束】"""
    payload = {
        "model": OPENAI_MODEL,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "reasoning": {"effort": "low"},
        "text": {"format": {"type": "json_schema", "name": "question_candidates", "strict": True, "schema": schema}},
        "max_output_tokens": 12000
    }
    try:
        resp = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"AI 服務連線失敗：{e}")
    if resp.status_code >= 400:
        try:
            err = resp.json().get("error", {}).get("message", "")
        except Exception:
            err = resp.text[:600]
        raise RuntimeError(f"AI 服務回傳 HTTP {resp.status_code}：{err or '請檢查 API Key / 額度 / 模型設定'}")
    data = resp.json()
    raw = _response_output_text(data)
    if not raw:
        raise RuntimeError("AI 沒有回傳可解析的題目內容。")
    try:
        parsed = json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"AI 題目 JSON 解析失敗：{e}")
    result = []
    for q in _coerce_ai_question_list(parsed)[:count]:
        qt = q.get("questionType") if q.get("questionType") in {"choice", "essay"} else "choice"
        question = str(q.get("question", "")).strip()
        if not question:
            continue
        options = [str(x).strip() for x in (q.get("options") or []) if str(x).strip()][:4]
        if qt == "choice":
            if len(options) != 4:
                continue
            correct = max(0, min(3, int(q.get("correct", 0) or 0)))
        else:
            options = []
            correct = 0
        result.append({
            "questionType": qt,
            "question": question[:2000],
            "options": options,
            "correct": correct,
            "tag": str(q.get("tag", "AI教材題"))[:100],
            "explanation": str(q.get("explanation", ""))[:4000],
            "sourceHint": str(q.get("sourceHint", ""))[:300],
            "sourceEvidence": str(q.get("sourceEvidence", ""))[:600],
        })
    if not result:
        raise RuntimeError("AI 回傳的題目未通過格式檢查，請重新產生。")
    return result


def _coerce_ai_question_list(parsed):
    """Accept common model JSON shapes and return a list of question dicts.

    Models may return {"questions": [...]}, a bare [...], or occasionally
    wrappers such as {"items": [...]} / {"data": {"questions": [...]}}.
    Invalid entries are ignored instead of crashing the whole AI workflow.
    """
    if isinstance(parsed, list):
        return [q for q in parsed if isinstance(q, dict)]
    if not isinstance(parsed, dict):
        return []
    for key in ("questions", "items", "results"):
        value = parsed.get(key)
        if isinstance(value, list):
            return [q for q in value if isinstance(q, dict)]
    data = parsed.get("data")
    if isinstance(data, list):
        return [q for q in data if isinstance(q, dict)]
    if isinstance(data, dict):
        for key in ("questions", "items", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return [q for q in value if isinstance(q, dict)]
    # A single question object is also accepted.
    if parsed.get("question"):
        return [parsed]
    return []


def _question_prompt_parts(*, count, qtype, difficulty, focus, source_title, source_text=""):
    count = max(1, min(AI_MAX_QUESTIONS, int(count or 5)))
    allowed = {"choice","multi","fill","essay","mixed","mixed_choice_multi","mixed_all","video_choice","video_multi","video_fill","video_essay","video_mixed"}
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

def _normalize_ai_questions(parsed, count, video_media_url=""):
    result = []
    for q in _coerce_ai_question_list(parsed)[:count]:
        qt = str(q.get("questionType") or "choice").lower()
        if qt not in {"choice","multi","fill","essay"}: qt = "choice"
        question = str(q.get("question", "")).strip()
        if not question: continue
        cfg = q.get("answerConfig") if isinstance(q.get("answerConfig"), dict) else {}
        options = [str(x).strip() for x in (q.get("options") or []) if str(x).strip()][:4]
        correct = 0
        if qt in {"choice","multi"}:
            if len(options) != 4: continue
            try: correct = max(0, min(3, int(q.get("correct", 0) or 0)))
            except Exception: correct = 0
        else:
            options = []
        if qt == "multi":
            indices=[]
            for x in cfg.get("correctIndices", q.get("correctIndices", [])) or []:
                try:
                    i=int(x)
                    if 0<=i<4: indices.append(i)
                except Exception: pass
            indices=sorted(set(indices))
            if not indices:
                indices=[correct]
            cfg["correctIndices"]=indices
            correct=indices[0]
        if qt == "fill":
            answers=[str(x).strip() for x in (cfg.get("acceptedAnswers", q.get("acceptedAnswers", [])) or []) if str(x).strip()][:10]
            if not answers:
                fallback=str(q.get("correctAnswer", "")).strip()
                if fallback: answers=[fallback]
            if not answers: continue
            cfg["acceptedAnswers"]=answers; cfg["caseSensitive"]=False
        pause=cfg.get("pauseAt", q.get("pauseAt", 0))
        try: pause=max(0, float(pause or 0))
        except Exception: pause=0
        if video_media_url:
            if pause<=0:
                hint=str(q.get("sourceHint", ""))
                m=re.search(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)", hint)
                if m: pause=int(m.group(1))*60+int(m.group(2))
            cfg["mediaUrl"]=video_media_url; cfg["pauseAt"]=pause
        result.append({
            "questionType": qt, "question": question[:2000], "options": options, "correct": correct,
            "answerConfig": cfg, "tag": str(q.get("tag", "AI教材題"))[:100],
            "explanation": str(q.get("explanation", ""))[:4000], "sourceHint": str(q.get("sourceHint", ""))[:300],
            "sourceEvidence": str(q.get("sourceEvidence", ""))[:600],
        })
    if not result: raise RuntimeError("AI 回傳的題目未通過格式檢查，請重新產生。")
    return result

def _groq_error(resp):
    try:
        d=resp.json(); return (d.get("error") or {}).get("message") or str(d)[:500]
    except Exception: return resp.text[:500]

def _groq_transcribe(path: Path):
    if not GROQ_API_KEY: raise RuntimeError("Groq 尚未設定 GROQ_API_KEY。")
    with open(path,"rb") as f:
        resp=requests.post("https://api.groq.com/openai/v1/audio/transcriptions", headers={"Authorization":f"Bearer {GROQ_API_KEY}"}, files={"file":(path.name,f,_content_type_for(path))}, data={"model":GROQ_TRANSCRIBE_MODEL,"response_format":"verbose_json"}, timeout=180)
    if resp.status_code==429: raise RuntimeError("Groq 免費 AI 額度/速率已達上限，請稍後或明日再試；系統不會自動切換付費服務。")
    if resp.status_code>=400: raise RuntimeError(f"Groq 語音轉文字失敗 HTTP {resp.status_code}：{_groq_error(resp)}")
    d=resp.json(); text=d.get("text","")
    segs=d.get("segments") or []
    if segs:
        lines=[]
        for seg in segs:
            st=float(seg.get("start",0) or 0); mm=int(st//60); ss=int(st%60); lines.append(f"[{mm:02d}:{ss:02d}] {seg.get('text','').strip()}")
        text="\n".join(lines)
    return text

def _extract_video_audio_and_frames(video: Path, temp_root: Path):
    audio=temp_root/"audio.mp3"
    subprocess.run(["ffmpeg","-y","-i",str(video),"-vn","-ac","1","-ar","16000","-b:a","64k",str(audio)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180, check=False)
    # 取得影片長度，平均擷取數張代表畫面。
    dur=0.0
    try:
        pr=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(video)],capture_output=True,text=True,timeout=30)
        dur=float((pr.stdout or "0").strip() or 0)
    except Exception: pass
    frames=[]
    for i in range(AI_VIDEO_FRAME_COUNT):
        t=(dur*(i+1)/(AI_VIDEO_FRAME_COUNT+1)) if dur>0 else i*10
        fp=temp_root/f"frame-{i+1}.jpg"
        subprocess.run(["ffmpeg","-y","-ss",str(t),"-i",str(video),"-frames:v","1","-vf","scale='min(1280,iw)':-2",str(fp)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=False)
        if fp.exists(): frames.append((fp,t))
    return (audio if audio.exists() else None), frames

def _extract_document_preview_frames(source: Path, temp_root: Path, max_frames=2):
    """Render a few representative document pages for multimodal AI review.

    This complements extracted text so image-heavy PPT/PDF pages, diagrams and
    screenshots can also influence candidate questions.
    """
    if pymupdf is None or max_frames <= 0:
        return []
    ext = source.suffix.lower()
    pdf = source if ext == ".pdf" else None
    try:
        if pdf is None and (ext in OFFICE_EXT or ext in {".ppt", ".pptx", ".doc", ".docx", ".xls", ".xlsx", ".odp", ".odt", ".ods"}):
            pdf = _convert_office_to_pdf_for_text(source, temp_root)
        if pdf is None or not Path(pdf).exists():
            return []
        out=[]
        with pymupdf.open(str(pdf)) as doc:
            n=len(doc)
            if n<=0: return []
            if max_frames==1: indices=[max(0,n//2)]
            else:
                candidates=[0, max(0,n//2), max(0,n-1)]
                indices=[]
                for i in candidates:
                    if i not in indices: indices.append(i)
                    if len(indices)>=max_frames: break
            for seq,i in enumerate(indices,1):
                fp=temp_root/f"doc-preview-{seq}.png"
                pix=doc[i].get_pixmap(matrix=pymupdf.Matrix(1.35,1.35), alpha=False)
                pix.save(str(fp))
                if fp.exists(): out.append((fp,i+1))
        return out
    except Exception:
        return []


def _data_url(path: Path):
    mime=_content_type_for(path); return f"data:{mime};base64,"+base64.b64encode(path.read_bytes()).decode("ascii")

def generate_groq_multisource_candidates(entries, *, count, qtype, difficulty, focus, source_title, strategy="balanced", existing_questions=None, progress_id=""):
    if not GROQ_API_KEY: raise RuntimeError("Groq Free AI 尚未設定。請在 Render Environment 新增 GROQ_API_KEY。")
    if not entries: raise RuntimeError("請至少選擇一份教材。")
    if len(entries)>AI_MAX_MATERIALS: raise RuntimeError(f"一次最多可選 {AI_MAX_MATERIALS} 份教材。")
    count, system_prompt, base_prompt=_question_prompt_parts(count=count,qtype=qtype,difficulty=difficulty,focus=focus,source_title=source_title,source_text="")
    existing=[str(x).strip() for x in (existing_questions or []) if str(x).strip()][:80]
    prompt=base_prompt+"\n"+_ai_strategy_rule(strategy, entries)+"\n每題請提供 sourceHint 與 sourceEvidence，指出答案依據；不可使用教材外知識。"
    if existing: prompt+="\n【現有正式題庫】\n"+"\n".join("- "+x[:220] for x in existing)+"\n避免重複題。"
    content=[{"type":"text","text":system_prompt+"\n\n"+prompt}]
    temp_roots=[]; text_sections=[]; image_count=0
    if progress_id:
        set_upload_progress(progress_id, 12, "準備 AI 教材", f"已選 {len(entries)} 份教材，開始解析內容", current=0, total=len(entries))
    try:
        for idx,e in enumerate(entries,1):
            title=e.get("title") or e.get("filename") or f"教材{idx}"; kind=_ai_material_kind(e)
            if progress_id:
                base_pct = 14 + ((idx-1) / max(1, len(entries))) * 38
                stage = {"text":"解析文件內容","subtitle":"解析字幕","image":"分析圖片 / Atlas","audio":"轉錄音訊","video":"擷取影片畫面與語音"}.get(kind,"解析教材")
                set_upload_progress(progress_id, base_pct, stage, f"{idx}/{len(entries)}：{title}", current=idx-1, total=len(entries))
            if kind in {"text","subtitle"}:
                txt=""
                try:
                    txt,_=extract_material_text_for_ai(e)
                except Exception as ex:
                    # 圖片型 / 掃描型文件可改由代表頁面視覺理解，不因文字太少整批失敗。
                    text_sections.append(f"【來源 {idx}：{title}】文字擷取有限，改以文件代表頁面視覺分析。")
                if txt:
                    text_sections.append(f"【來源 {idx}：{title}】\n{txt}")
                if kind=="text" and image_count<5:
                    try:
                        temp,src=_material_source_to_temp(e); temp_roots.append(temp)
                        previews=_extract_document_preview_frames(src,temp,max_frames=min(2,5-image_count))
                        for fp,page_no in previews:
                            content.append({"type":"image_url","image_url":{"url":_data_url(fp)}}); image_count+=1
                            text_sections.append(f"【{title} 代表頁面：第 {page_no} 頁】已附圖，請一併判讀圖表、流程、截圖或影像內容。")
                    except Exception:
                        pass
                if not txt and image_count==0:
                    raise RuntimeError(f"教材「{title}」無法擷取文字或可分析畫面，請改用 PDF/PPTX/圖片或影音教材。")
                continue
            temp,src=_material_source_to_temp(e); temp_roots.append(temp)
            if kind=="image":
                if image_count<5 and src.stat().st_size<=20*1024*1024:
                    content.append({"type":"image_url","image_url":{"url":_data_url(src)}}); image_count+=1
                text_sections.append(f"【來源 {idx}：{title}】此來源為圖片，請連同附圖判讀。")
            elif kind=="audio":
                if progress_id: set_upload_progress(progress_id, 28 + (idx/max(1,len(entries)))*18, "音訊轉文字", f"Groq Whisper 正在轉錄：{title}", current=idx, total=len(entries))
                text_sections.append(f"【來源 {idx}：{title} 音訊逐字稿】\n"+_groq_transcribe(src))
            elif kind=="video":
                if progress_id: set_upload_progress(progress_id, 24 + (idx/max(1,len(entries)))*14, "擷取影片代表畫面", f"正在抽取畫面與音訊：{title}", current=idx, total=len(entries))
                audio,frames=_extract_video_audio_and_frames(src,temp)
                if audio:
                    if progress_id: set_upload_progress(progress_id, 36 + (idx/max(1,len(entries)))*14, "影片語音轉文字", f"正在轉錄影片語音：{title}", current=idx, total=len(entries))
                    text_sections.append(f"【來源 {idx}：{title} 影片語音逐字稿】\n"+_groq_transcribe(audio))
                for fp,t in frames:
                    if image_count>=5: break
                    content.append({"type":"image_url","image_url":{"url":_data_url(fp)}}); image_count+=1
                    text_sections.append(f"【{title} 代表畫面約 {int(t//60):02d}:{int(t%60):02d}】已附圖。")
        if text_sections:
            combined="\n\n".join(text_sections)
            if len(combined)>AI_SOURCE_MAX_CHARS: combined=combined[:AI_SOURCE_MAX_CHARS]+"\n[內容已截斷]"
            content[0]["text"] += "\n\n"+combined
        payload={"model":GROQ_MODEL,"messages":[{"role":"user","content":content}],"temperature":0.15,"response_format":{"type":"json_object"},"max_completion_tokens":8000}
        if progress_id: set_upload_progress(progress_id, 62, "AI 正在產生候選題", f"{GROQ_MODEL} 正在整合教材、比對既有題庫並產生題目")
        resp=requests.post("https://api.groq.com/openai/v1/chat/completions",headers={"Authorization":f"Bearer {GROQ_API_KEY}","Content-Type":"application/json"},json=payload,timeout=180)
        if resp.status_code==429: raise RuntimeError("Groq 免費 AI 額度/速率已達上限，請稍後或明日再試；FREE_ONLY_MODE 不會自動切換任何付費 API。")
        if resp.status_code>=400: raise RuntimeError(f"Groq AI 出題失敗 HTTP {resp.status_code}：{_groq_error(resp)}")
        raw=resp.json().get("choices",[{}])[0].get("message",{}).get("content","")
        cleaned=re.sub(r"^```(?:json)?\s*|\s*```$","",raw,flags=re.I|re.S).strip()
        try: parsed=json.loads(cleaned)
        except Exception as ex: raise RuntimeError(f"Groq 題目 JSON 解析失敗：{ex}")
        if progress_id: set_upload_progress(progress_id, 86, "檢查 AI 題目格式", "正在驗證題型、答案、來源提示與多媒體時間點")
        video_entry = next((e for e in entries if _ai_material_kind(e)=="video"), None)
        video_url = f"/view/{video_entry.get('id')}" if video_entry else ""
        normalized = _normalize_ai_questions(parsed,count,video_media_url=video_url)
        if progress_id: set_upload_progress(progress_id, 94, "整理候選題", f"已完成 {len(normalized)} 題格式檢查，準備回傳後台")
        return normalized
    finally:
        for t in temp_roots: shutil.rmtree(t,ignore_errors=True)

def generate_gemini_question_candidates(*, source_text="", source_path=None, count, qtype, difficulty, focus, source_title):
    if not GEMINI_API_KEY:
        raise RuntimeError("Google Gemini 尚未設定。請在 Render Environment 新增 GEMINI_API_KEY。")
    if google_genai is None or google_genai_types is None:
        raise RuntimeError("伺服器缺少 google-genai 套件，請使用 V5.3.9 的 requirements.txt 重新部署。")
    count, system_prompt, user_prompt = _question_prompt_parts(
        count=count, qtype=qtype, difficulty=difficulty, focus=focus, source_title=source_title, source_text=source_text
    )
    client = google_genai.Client(api_key=GEMINI_API_KEY)
    uploaded = None
    try:
        contents = [system_prompt + "\n\n" + user_prompt]
        if source_path is not None:
            source_path = Path(source_path)
            if source_path.stat().st_size > AI_MEDIA_MAX_MB * 1024 * 1024:
                raise RuntimeError(f"此多媒體教材超過 AI_MEDIA_MAX_MB={AI_MEDIA_MAX_MB}MB，請壓縮後再出題。")
            uploaded = client.files.upload(file=str(source_path))
            # 影片/音訊可能需要後台處理；最多等 5 分鐘。
            deadline = time.time() + 300
            while getattr(getattr(uploaded, "state", None), "name", "") in {"PROCESSING", "STATE_UNSPECIFIED"}:
                if time.time() > deadline:
                    raise RuntimeError("Gemini 處理影音檔超時，請稍後重試或縮短影片。")
                time.sleep(3)
                uploaded = client.files.get(name=uploaded.name)
            if getattr(getattr(uploaded, "state", None), "name", "") == "FAILED":
                raise RuntimeError("Gemini 無法處理此影音/圖片教材。")
            contents = [uploaded, system_prompt + "\n\n" + user_prompt]
        config = google_genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2,
        )
        response = client.models.generate_content(model=GEMINI_MODEL, contents=contents, config=config)
        raw = (getattr(response, "text", None) or "").strip()
        if not raw:
            raise RuntimeError("Gemini 沒有回傳可解析的題目內容。")
        try:
            parsed = json.loads(raw)
        except Exception as e:
            # 偶爾模型仍會包 ```json ... ```，做保守清理。
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.S).strip()
            try:
                parsed = json.loads(cleaned)
            except Exception:
                raise RuntimeError(f"Gemini 題目 JSON 解析失敗：{e}")
        return _normalize_ai_questions(parsed, count)
    except Exception as e:
        if isinstance(e, RuntimeError):
            raise
        raise RuntimeError(f"Gemini AI 出題失敗：{e}")
    finally:
        if uploaded is not None:
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                pass



def _ai_material_kind(entry):
    ext = Path(entry.get("filename") or entry.get("storageFilename") or "").suffix.lower()
    if ext in AI_VIDEO_EXT:
        return "video"
    if ext in AI_AUDIO_EXT:
        return "audio"
    if ext in AI_IMAGE_EXT:
        return "image"
    if ext in AI_SUBTITLE_EXT:
        return "subtitle"
    return "text"


def _infer_ai_strategy(entries):
    joined = " ".join(str((e.get("title") or "")) + " " + str((e.get("description") or "")) + " " + str((e.get("materialType") or e.get("material_type") or "")) for e in (entries or [])).lower()
    kinds = {_ai_material_kind(e) for e in (entries or [])}
    if "atlas" in joined or any(x in joined for x in ["圖譜","辨識","型態","結晶","寄生蟲","血球","細菌","真菌"]):
        return "recognition"
    if "sop" in joined or any(x in joined for x in ["法規","指引","規範","標準作業"]):
        return "regulation"
    if any(x in joined for x in ["故障","異常","troubleshooting","案例","輸血反應","discrepancy"]):
        return "scenario"
    if any(x in joined for x in ["qc","品質","westgard","安全","通報","critical value"]):
        return "safety"
    if "video" in kinds or any(x in joined for x in ["操作","步驟","保養","流程","儀器"]):
        return "workflow"
    return "balanced"

def _ai_strategy_rule(strategy, entries=None):
    chosen = _infer_ai_strategy(entries) if strategy == "auto" else strategy
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


def generate_gemini_multisource_candidates(entries, *, count, qtype, difficulty, focus, source_title, strategy="balanced", existing_questions=None):
    """V5.3.11：Gemini 多來源智慧出題，可同時讀文字、字幕、圖片、音訊與一支影片。"""
    if not GEMINI_API_KEY:
        raise RuntimeError("Google Gemini 尚未設定。請在 Render Environment 新增 GEMINI_API_KEY。")
    if google_genai is None or google_genai_types is None:
        raise RuntimeError("伺服器缺少 google-genai 套件，請重新部署 requirements.txt。")
    if not entries:
        raise RuntimeError("請至少選擇一份教材。")
    if len(entries) > AI_MAX_MATERIALS:
        raise RuntimeError(f"一次最多可選 {AI_MAX_MATERIALS} 份教材，避免請求過大。")
    kinds = [_ai_material_kind(e) for e in entries]
    if kinds.count("video") > 1:
        raise RuntimeError("為提高影片理解穩定性，一次最多選 1 支影片；可再搭配字幕、圖片或文字教材。")

    count, system_prompt, base_prompt = _question_prompt_parts(
        count=count, qtype=qtype, difficulty=difficulty, focus=focus, source_title=source_title, source_text=""
    )
    strategy_rule = _ai_strategy_rule(strategy, entries)
    existing = [str(x).strip() for x in (existing_questions or []) if str(x).strip()][:80]
    duplicate_rule = ""
    if existing:
        duplicate_rule = "\n\n【現有正式題庫題幹】\n" + "\n".join(f"- {x[:240]}" for x in existing) + "\n請避免產生語意重複或只是換句話說的題目。"
    evidence_rule = (
        "\n每一題除了 sourceHint 外，必須提供 sourceEvidence：用一句話簡短說明答案依據來自哪份教材的哪個內容。"
        "不要大段逐字引用教材。若是影片請盡量填 MM:SS 時間戳；圖片請描述畫面線索；字幕請標示字幕時間。"
    )
    prompt = base_prompt + "\n" + strategy_rule + evidence_rule + duplicate_rule

    client = google_genai.Client(api_key=GEMINI_API_KEY)
    temp_roots, uploads, content_parts, text_sections = [], [], [], []
    try:
        for idx, entry in enumerate(entries, 1):
            title = entry.get("title") or entry.get("filename") or f"教材{idx}"
            kind = _ai_material_kind(entry)
            if kind in {"text", "subtitle"}:
                text, total = extract_material_text_for_ai(entry)
                text_sections.append(f"【來源 {idx}：{title}】\n{text}")
                continue
            if entry.get("isBuiltin"):
                raise RuntimeError(f"{title} 沒有保留原始多媒體檔，請重新上傳後再使用 AI 出題。")
            temp_root, source = _material_source_to_temp(entry)
            temp_roots.append(temp_root)
            if source.stat().st_size > AI_MEDIA_MAX_MB * 1024 * 1024:
                raise RuntimeError(f"{title} 超過 AI_MEDIA_MAX_MB={AI_MEDIA_MAX_MB}MB，請壓縮後再出題。")
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
            if len(combined) > AI_SOURCE_MAX_CHARS:
                combined = combined[:AI_SOURCE_MAX_CHARS] + "\n[文字來源已依 AI_SOURCE_MAX_CHARS 截斷]"
            prompt += "\n\n" + combined
        contents = content_parts + [system_prompt + "\n\n" + prompt]
        config = google_genai_types.GenerateContentConfig(response_mime_type="application/json", temperature=0.15)
        response = client.models.generate_content(model=GEMINI_MODEL, contents=contents, config=config)
        raw = (getattr(response, "text", None) or "").strip()
        if not raw:
            raise RuntimeError("Gemini 沒有回傳可解析的題目內容。")
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.S).strip()
        try:
            parsed = json.loads(cleaned)
        except Exception as e:
            raise RuntimeError(f"Gemini 題目 JSON 解析失敗：{e}")
        video_entry = next((e for e in entries if _ai_material_kind(e)=="video"), None)
        video_url = f"/view/{video_entry.get('id')}" if video_entry else ""
        result = _normalize_ai_questions(parsed, count, video_media_url=video_url)
        # 若模型漏掉 sourceEvidence，不阻斷，但候選題畫面會標示未提供。
        return result
    except Exception as e:
        if isinstance(e, RuntimeError):
            raise
        raise RuntimeError(f"Gemini 多媒體 AI 出題失敗：{e}")
    finally:
        for uploaded in uploads:
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                pass
        for temp_root in temp_roots:
            shutil.rmtree(temp_root, ignore_errors=True)


def generate_ai_questions_from_materials(entries, *, category_id, count, qtype, difficulty, focus, strategy="balanced", progress_id=""):
    if not entries:
        raise RuntimeError("請至少選擇一份教材。")
    provider = active_ai_provider()
    if progress_id: set_upload_progress(progress_id, 6, "讀取正式題庫", "正在載入既有題目，避免 AI 產生重複內容")
    existing = [q.get("question", "") for q in list_quiz_questions(category_id, include_inactive=True)]
    title = " + ".join((e.get("title") or e.get("filename") or "教材") for e in entries)
    has_media = any(_ai_material_kind(e) in {"image", "video", "audio"} for e in entries)
    if str(qtype).startswith("video_") and not any(_ai_material_kind(e)=="video" for e in entries):
        raise RuntimeError("影片互動題需要至少選擇 1 支影片教材。")
    if provider == "groq":
        questions = generate_groq_multisource_candidates(
            entries, count=count, qtype=qtype, difficulty=difficulty, focus=focus, source_title=title,
            strategy=strategy, existing_questions=existing, progress_id=progress_id
        )
        return questions, title, [_ai_material_kind(e) for e in entries]
    if provider == "gemini":
        if progress_id: set_upload_progress(progress_id, 18, "準備 Gemini 多媒體分析", "正在上傳 / 解析教材來源")
        questions = generate_gemini_multisource_candidates(
            entries, count=count, qtype=qtype, difficulty=difficulty, focus=focus, source_title=title,
            strategy=strategy, existing_questions=existing
        )
        return questions, title, [_ai_material_kind(e) for e in entries]
    if has_media or len(entries)>1:
        raise RuntimeError("OpenAI 備援模式在此版本僅處理單一文字來源；免費多媒體模式請使用 AI_PROVIDER=groq。")
    # OpenAI 備援：單一文字來源
    text, total = extract_material_text_for_ai(entries[0])
    questions = generate_openai_question_candidates(text, count=count, qtype=qtype, difficulty=difficulty, focus=focus, source_title=title)
    return questions, title, ["text"]

def generate_ai_question_candidates(source_text, *, count, qtype, difficulty, focus, source_title):
    """文字型教材：依 AI_PROVIDER 選 Gemini 或 OpenAI。"""
    provider = active_ai_provider()
    if provider == "groq":
        pseudo={"id":"inline","title":source_title,"filename":"inline.txt"}
        # 文字直送 Groq，不需建立實體教材檔。
        count2, system_prompt, base_prompt=_question_prompt_parts(count=count,qtype=qtype,difficulty=difficulty,focus=focus,source_title=source_title,source_text=source_text)
        payload={"model":GROQ_MODEL,"messages":[{"role":"user","content":system_prompt+"\n\n"+base_prompt}],"temperature":0.15,"response_format":{"type":"json_object"},"max_completion_tokens":8000}
        resp=requests.post("https://api.groq.com/openai/v1/chat/completions",headers={"Authorization":f"Bearer {GROQ_API_KEY}","Content-Type":"application/json"},json=payload,timeout=120)
        if resp.status_code==429: raise RuntimeError("Groq 免費 AI 額度已達上限，請稍後再試。")
        if resp.status_code>=400: raise RuntimeError(f"Groq AI 出題失敗：{_groq_error(resp)}")
        raw=resp.json().get("choices",[{}])[0].get("message",{}).get("content","")
        return _normalize_ai_questions(json.loads(re.sub(r"^```(?:json)?\s*|\s*```$","",raw,flags=re.I|re.S).strip()),count2)
    if provider == "gemini":
        return generate_gemini_question_candidates(
            source_text=source_text, count=count, qtype=qtype, difficulty=difficulty, focus=focus, source_title=source_title
        )
    return generate_openai_question_candidates(
        source_text, count=count, qtype=qtype, difficulty=difficulty, focus=focus, source_title=source_title
    )


def generate_ai_questions_from_material(entry, *, count, qtype, difficulty, focus):
    """V5.3.9：Gemini 可直接理解圖片/影音；字幕檔直接當文字。"""
    provider = active_ai_provider()
    title = entry.get("title") or entry.get("filename") or "教材"
    ext = Path(entry.get("filename") or entry.get("storageFilename") or "").suffix.lower()
    if provider == "groq" and ext in (AI_IMAGE_EXT | AI_VIDEO_EXT | AI_AUDIO_EXT):
        qs=generate_groq_multisource_candidates([entry],count=count,qtype=qtype,difficulty=difficulty,focus=focus,source_title=title)
        return qs,0,0,"media"
    if provider == "gemini" and ext in (AI_IMAGE_EXT | AI_VIDEO_EXT | AI_AUDIO_EXT):
        if entry.get("isBuiltin"):
            raise RuntimeError("內建舊教材沒有原始多媒體檔，請重新上傳後再使用 AI 出題。")
        temp_root, source = _material_source_to_temp(entry)
        try:
            return generate_gemini_question_candidates(
                source_path=source, count=count, qtype=qtype, difficulty=difficulty, focus=focus, source_title=title
            ), 0, 0, "media"
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)
    source_text, total_chars = extract_material_text_for_ai(entry)
    return generate_ai_question_candidates(
        source_text, count=count, qtype=qtype, difficulty=difficulty, focus=focus, source_title=title
    ), len(source_text), total_chars, "text"


def _insert_quiz_question_payload(category_id, payload):
    qtext = str(payload.get("question", "")).strip()
    qtype = str(payload.get("questionType", "choice")).lower()
    if qtype not in {"choice","multi","fill","essay","image","video","true_false"}: qtype = "choice"
    cfg = payload.get("answerConfig") if isinstance(payload.get("answerConfig"), dict) else {}
    options = [str(x).strip() for x in (payload.get("options") or []) if str(x).strip()][:6]
    if qtype in {"essay","fill"}: options=[]
    if qtype == "true_false": options=["是","否"]
    needs_options=qtype in {"choice","multi","image","video","true_false"}
    if not qtext or (needs_options and len(options)<2): raise ValueError("題目內容或選項不足")
    try: correct=int(payload.get("correct",0) or 0)
    except Exception: correct=0
    if options: correct=max(0,min(len(options)-1,correct))
    else: correct=0
    if qtype=="multi":
        ids=[]
        for x in cfg.get("correctIndices",[]) or []:
            try:
                i=int(x)
                if 0<=i<len(options): ids.append(i)
            except Exception: pass
        ids=sorted(set(ids))
        if not ids: raise ValueError("多選題至少要設定一個正確選項")
        cfg["correctIndices"]=ids; correct=ids[0]
    if qtype=="fill":
        ans=[str(x).strip() for x in cfg.get("acceptedAnswers",[]) if str(x).strip()][:20]
        if not ans: raise ValueError("填空題至少要設定一個可接受答案")
        cfg["acceptedAnswers"]=ans; cfg["caseSensitive"]=bool(cfg.get("caseSensitive",False))
    if cfg.get("mediaUrl"):
        cfg["mediaUrl"]=str(cfg.get("mediaUrl"))[:1500]
        try: cfg["pauseAt"]=max(0,float(cfg.get("pauseAt",0) or 0))
        except Exception: cfg["pauseAt"]=0
    difficulty=str(payload.get("difficulty","standard") or "standard").lower()
    if difficulty not in {"basic","standard","advanced"}: difficulty="standard"
    q_id=f"q-{uuid.uuid4().hex[:12]}"
    conn,kind=_db_conn()
    try:
        ph="%s" if kind=="postgres" else "?"
        row=conn.execute(f"SELECT COALESCE(MAX(sort_order), -1) AS m FROM quiz_questions WHERE quiz_category_id={ph}",(category_id,)).fetchone()
        order=(row["m"] if isinstance(row,dict) else row[0])+1
        vals=(q_id,category_id,str(payload.get("tag",""))[:100],qtext[:2000],qtype,difficulty,str(payload.get("imageUrl",""))[:1000],json.dumps(options,ensure_ascii=False),correct,json.dumps(cfg,ensure_ascii=False),str(payload.get("explanation",""))[:4000],order)
        if kind=="postgres":
            conn.execute("INSERT INTO quiz_questions (id,quiz_category_id,tag,question,question_type,difficulty,image_url,options,correct,answer_config,explanation,sort_order,active) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)",vals)
        else:
            conn.execute("INSERT INTO quiz_questions (id,quiz_category_id,tag,question,question_type,difficulty,image_url,options,correct,answer_config,explanation,sort_order,active) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)",vals)
    finally: conn.close()
    return q_id


def _insert_quiz_question_payloads_bulk(category_id, items):
    """Insert multiple AI-reviewed questions with one DB connection.

    Returns the inserted question dictionaries so the admin UI can render them
    immediately without reloading the whole dynamic question bank.
    """
    prepared=[]
    for payload in items:
        if not isinstance(payload, dict):
            raise ValueError("題目格式錯誤")
        qtext=str(payload.get("question","")).strip()
        qtype=str(payload.get("questionType","choice")).lower()
        if qtype not in {"choice","multi","fill","essay","image","video","true_false"}: qtype="choice"
        cfg=payload.get("answerConfig") if isinstance(payload.get("answerConfig"),dict) else {}
        options=[str(x).strip() for x in (payload.get("options") or []) if str(x).strip()][:6]
        if qtype in {"essay","fill"}: options=[]
        if not qtext or (qtype in {"choice","multi","image","video"} and len(options)<2):
            raise ValueError("題目內容或選項不足")
        try: correct=int(payload.get("correct",0) or 0)
        except Exception: correct=0
        if options: correct=max(0,min(len(options)-1,correct))
        else: correct=0
        if qtype=="multi":
            ids=[]
            for x in cfg.get("correctIndices",[]) or []:
                try:
                    i=int(x)
                    if 0<=i<len(options): ids.append(i)
                except Exception: pass
            ids=sorted(set(ids))
            if not ids: raise ValueError("多選題至少要設定一個正確選項")
            cfg["correctIndices"]=ids; correct=ids[0]
        if qtype=="fill":
            ans=[str(x).strip() for x in cfg.get("acceptedAnswers",[]) if str(x).strip()][:20]
            if not ans: raise ValueError("填空題至少要設定一個可接受答案")
            cfg["acceptedAnswers"]=ans; cfg["caseSensitive"]=bool(cfg.get("caseSensitive",False))
        if cfg.get("mediaUrl"):
            cfg["mediaUrl"]=str(cfg.get("mediaUrl"))[:1500]
            try: cfg["pauseAt"]=max(0,float(cfg.get("pauseAt",0) or 0))
            except Exception: cfg["pauseAt"]=0
        prepared.append({
            "id":f"q-{uuid.uuid4().hex[:12]}", "quizCategoryId":category_id,
            "tag":str(payload.get("tag",""))[:100], "question":qtext[:2000],
            "questionType":qtype, "difficulty":(str(payload.get("difficulty","standard") or "standard").lower() if str(payload.get("difficulty","standard") or "standard").lower() in {"basic","standard","advanced"} else "standard"), "imageUrl":str(payload.get("imageUrl",""))[:1000],
            "options":options, "correct":correct, "answerConfig":cfg,
            "explanation":str(payload.get("explanation",""))[:4000], "active":True,
        })
    if not prepared: return []
    conn,kind=_db_conn()
    try:
        ph="%s" if kind=="postgres" else "?"
        row=conn.execute(f"SELECT COALESCE(MAX(sort_order), -1) AS m FROM quiz_questions WHERE quiz_category_id={ph}",(category_id,)).fetchone()
        order=(row["m"] if isinstance(row,dict) else row[0])+1
        for idx,q in enumerate(prepared):
            q["sortOrder"]=order+idx
            vals=(q["id"],category_id,q["tag"],q["question"],q["questionType"],q["difficulty"],q["imageUrl"],json.dumps(q["options"],ensure_ascii=False),q["correct"],json.dumps(q["answerConfig"],ensure_ascii=False),q["explanation"],q["sortOrder"])
            if kind=="postgres":
                conn.execute("INSERT INTO quiz_questions (id,quiz_category_id,tag,question,question_type,difficulty,image_url,options,correct,answer_config,explanation,sort_order,active) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)",vals)
            else:
                conn.execute("INSERT INTO quiz_questions (id,quiz_category_id,tag,question,question_type,difficulty,image_url,options,correct,answer_config,explanation,sort_order,active) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)",vals)
    finally:
        conn.close()
    return prepared


@app.get("/api/ai-questions/status")
def api_ai_question_status():
    denied = require_admin()
    if denied: return denied
    return jsonify({"configured": ai_question_is_configured(), "provider": active_ai_provider(), "model": ai_model_name(), "maxQuestions": AI_MAX_QUESTIONS, "sourceMaxChars": AI_SOURCE_MAX_CHARS, "mediaSupported": active_ai_provider() in {"gemini","groq"}, "maxMaterials": AI_MAX_MATERIALS, "multisourceSupported": active_ai_provider() in {"gemini","groq"}, "freeOnlyMode": FREE_ONLY_MODE})


@app.post("/api/ai-questions/generate")
def api_ai_generate_questions():
    denied = require_admin()
    if denied: return denied
    data = request.get_json(silent=True) or {}
    progress_id = re.sub(r"[^A-Za-z0-9_-]", "", str(data.get("progressId", "") or ""))[:80]
    if progress_id:
        clear_upload_progress(progress_id)
        set_upload_progress(progress_id, 2, "準備 AI 出題", "正在驗證考卷與教材設定")
    category_id = str(data.get("quizCategoryId", "")).strip()
    cat = get_quiz_category(category_id)
    if not cat:
        return jsonify({"error": "找不到考題頁籤。請重新整理後台後再試。"}), 404
    raw_ids = data.get("materialIds")
    if not isinstance(raw_ids, list):
        one = str(data.get("materialId", "")).strip()
        raw_ids = [one] if one else []
    material_ids = []
    for x in raw_ids:
        mid = str(x).strip()
        if mid and mid not in material_ids:
            material_ids.append(mid)
    if not material_ids:
        return jsonify({"error": "請至少選擇一份教材"}), 400
    if len(material_ids) > AI_MAX_MATERIALS:
        return jsonify({"error": f"一次最多選 {AI_MAX_MATERIALS} 份教材"}), 400
    mats = []
    for mid in material_ids:
        mat = get_material(mid)
        if not mat or not mat.get("active", True):
            return jsonify({"error": f"找不到指定教材：{mid}"}), 404
        if mat.get("group") != cat.get("group") or mat.get("area") != cat.get("area"):
            return jsonify({"error": "所選教材與考卷不屬於同一訓練區/組別"}), 400
        mats.append(mat)
    try:
        requested_strategy = str(data.get("strategy", "auto")).strip()[:30] or "auto"
        questions, source_title, source_kinds = generate_ai_questions_from_materials(
            mats, category_id=category_id, count=data.get("count", 5),
            qtype=str(data.get("questionType", "mixed")),
            difficulty=str(data.get("difficulty", "standard")),
            focus=str(data.get("focus", "")).strip()[:500],
            strategy=requested_strategy, progress_id=progress_id,
        )
        if progress_id: set_upload_progress(progress_id, 100, "AI 候選題完成", f"已產生 {len(questions)} 題，請在後台人工審核後再匯入")
        applied_strategy = _infer_ai_strategy(mats) if requested_strategy == "auto" else requested_strategy
        return jsonify({
            "ok": True, "questions": questions, "sourceTitle": source_title,
            "sourceCount": len(mats), "sourceKinds": source_kinds,
            "sourceMode": "multimedia" if any(k in {"image","video","audio"} for k in source_kinds) else "text",
            "provider": active_ai_provider(), "model": ai_model_name(),
            "strategyRequested": requested_strategy, "strategyApplied": applied_strategy
        })
    except Exception as e:
        if progress_id: set_upload_progress(progress_id, 0, "AI 出題失敗", str(e)[:500])
        return jsonify({"error": str(e)}), 400


@app.post("/api/ai-questions/import")
def api_ai_import_questions():
    denied = require_admin()
    if denied: return denied
    data = request.get_json(silent=True) or {}
    category_id = str(data.get("quizCategoryId", "")).strip()
    if not get_quiz_category(category_id): return jsonify({"error": "找不到考題頁籤"}), 404
    items = data.get("questions") or []
    if not isinstance(items, list) or not items: return jsonify({"error": "請至少勾選一題"}), 400
    valid, errors = [], []
    for i,q in enumerate(items[:50],1):
        if isinstance(q,dict): valid.append(q)
        else: errors.append(f"第{i}題：題目格式錯誤")
    try:
        inserted=_insert_quiz_question_payloads_bulk(category_id, valid)
    except Exception as e:
        return jsonify({"error": f"批次匯入失敗：{e}"}), 400
    return jsonify({"ok": True, "imported": len(inserted), "errors": errors[:20], "questions": inserted})


# ---------------------------------------------------------------------------
# 考題頁籤 (quiz_categories) API —— 六組皆由後台動態管理
# ---------------------------------------------------------------------------
@app.get("/api/quiz-categories")
@login_required()
def api_list_quiz_categories():
    group = request.args.get("group", "")
    group = group if group in GROUPS else None
    area = normalize_area(request.args.get("area", DEFAULT_TRAINING_AREA))
    return jsonify(list_quiz_categories_with_counts(group_key=group, training_area=area, include_inactive=False))


@app.get("/api/quiz-categories/admin")
def api_admin_list_quiz_categories():
    denied = require_admin()
    if denied:
        return denied
    group = request.args.get("group", "")
    group = group if group in GROUPS else None
    area = normalize_area(request.args.get("area", DEFAULT_TRAINING_AREA))
    return jsonify(list_quiz_categories_with_counts(group_key=group, training_area=area, include_inactive=True))


@app.post("/api/quiz-categories")
def api_create_quiz_category():
    denied = require_admin()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    group = normalize_group(str(data.get("group", DEFAULT_GROUP)))
    area = normalize_area(str(data.get("area", DEFAULT_TRAINING_AREA)))
    title = str(data.get("title", "")).strip()[:255]
    desc = str(data.get("desc", "")).strip()[:1000]
    audience = str(data.get("audience", "")).strip()[:200]
    try:
        draw_count = max(0, int(data.get("drawCount", 0) or 0))
    except (TypeError, ValueError):
        draw_count = 0
    try:
        passing_score = max(1, min(100, int(data.get("passingScore", 80) or 80)))
    except (TypeError, ValueError):
        passing_score = 80
    draw_rules = data.get("drawRules", {}) if isinstance(data.get("drawRules", {}), dict) else {}
    if draw_rules.get("mode") != "type_quota":
        draw_rules = {}
    else:
        raw_q = draw_rules.get("quotas", {}) if isinstance(draw_rules.get("quotas", {}), dict) else {}
        draw_rules = {"mode":"type_quota","quotas":{k:max(0,min(200,int(raw_q.get(k,0) or 0))) for k in ("choice","multi","true_false","fill","essay","image","video")}}
        if sum(draw_rules["quotas"].values()) <= 0:
            draw_rules = {}
    course_id = str(data.get("courseId", "")).strip()
    course = get_course(course_id) if course_id else None
    if not course or course.get("group") != group or course.get("area") != area:
        course_id = ""
    if not title:
        return jsonify({"error": "請輸入頁籤名稱"}), 400
    cat_id = f"cat-{uuid.uuid4().hex[:12]}"
    conn, kind = _db_conn()
    try:
        existing = conn.execute(
            f"SELECT COALESCE(MAX(sort_order), -1) AS m FROM quiz_categories WHERE group_key = {'%s' if kind == 'postgres' else '?'}",
            (group,),
        ).fetchone()
        next_order = (existing["m"] if isinstance(existing, dict) else existing[0]) + 1
        date_added = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        if kind == "postgres":
            conn.execute(
                "INSERT INTO quiz_categories (id,group_key,training_area,course_id,title,description,sort_order,date_added,active,draw_count,passing_score,audience,draw_rules,review_status,reviewer_name,reviewed_at,published_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)",
                (cat_id, group, area, course_id, title, desc, next_order, date_added, False, draw_count, passing_score, audience, json.dumps(draw_rules, ensure_ascii=False), "draft", "", "", ""),
            )
        else:
            conn.execute(
                "INSERT INTO quiz_categories (id,group_key,training_area,course_id,title,description,sort_order,date_added,active,draw_count,passing_score,audience,draw_rules,review_status,reviewer_name,reviewed_at,published_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cat_id, group, area, course_id, title, desc, next_order, date_added, 0, draw_count, passing_score, audience, json.dumps(draw_rules, ensure_ascii=False), "draft", "", "", ""),
            )
    finally:
        conn.close()
    return jsonify(get_quiz_category(cat_id))


@app.patch("/api/quiz-categories/<category_id>")
def api_update_quiz_category(category_id):
    denied = require_admin()
    if denied:
        return denied
    entry = get_quiz_category(category_id)
    if not entry:
        return jsonify({"error": "找不到此考題頁籤"}), 404
    data = request.get_json(silent=True) or {}
    title = str(data.get("title", entry["title"])).strip()[:255]
    desc = str(data.get("desc", entry.get("desc", ""))).strip()[:1000]
    active = bool(data.get("active", entry.get("active", True)))
    review_status = str(data.get("reviewStatus", entry.get("reviewStatus", "approved")) or "draft").lower()
    if review_status not in {"draft", "approved"}:
        review_status = entry.get("reviewStatus", "draft")
    reviewer_name = str(data.get("reviewerName", entry.get("reviewerName", "")) or "").strip()[:100]
    reviewed_at = str(data.get("reviewedAt", entry.get("reviewedAt", "")) or "")[:80]
    published_at = str(data.get("publishedAt", entry.get("publishedAt", "")) or "")[:80]
    blind_mode = bool(data.get("blindMode", entry.get("blindMode", False)))
    audience = str(data.get("audience", entry.get("audience", ""))).strip()[:200]
    course_id = str(data.get("courseId", entry.get("courseId", ""))).strip()[:100]
    course = get_course(course_id) if course_id else None
    if not course or course.get("group") != entry.get("group") or course.get("area") != entry.get("area"):
        course_id = ""
    try:
        draw_count = max(0, int(data.get("drawCount", entry.get("drawCount", 0)) or 0))
    except (TypeError, ValueError):
        draw_count = max(0, int(entry.get("drawCount", 0) or 0))
    try:
        passing_score = max(1, min(100, int(data.get("passingScore", entry.get("passingScore", 80)) or 80)))
    except (TypeError, ValueError):
        passing_score = max(1, min(100, int(entry.get("passingScore", 80) or 80)))
    draw_rules = data.get("drawRules", entry.get("drawRules", {}))
    draw_rules = draw_rules if isinstance(draw_rules, dict) else {}
    if draw_rules.get("mode") != "type_quota":
        draw_rules = {}
    else:
        raw_q = draw_rules.get("quotas", {}) if isinstance(draw_rules.get("quotas", {}), dict) else {}
        draw_rules = {"mode":"type_quota","quotas":{k:max(0,min(200,int(raw_q.get(k,0) or 0))) for k in ("choice","multi","true_false","fill","essay","image","video")}}
        if sum(draw_rules["quotas"].values()) <= 0:
            draw_rules = {}

    # 任何會改變考生實際作答內容／規則的設定變更，都必須重新審核。
    config_changed = any([
        title != entry.get("title", ""), desc != entry.get("desc", ""), blind_mode != bool(entry.get("blindMode", False)),
        draw_count != int(entry.get("drawCount", 0) or 0), passing_score != int(entry.get("passingScore", 80) or 80),
        audience != str(entry.get("audience", "") or ""), course_id != str(entry.get("courseId", "") or ""),
        draw_rules != (entry.get("drawRules", {}) or {}),
    ])
    if config_changed:
        review_status, reviewer_name, reviewed_at, published_at, active = "draft", "", "", "", False
    elif active and review_status != "approved":
        return jsonify({"error": "此考卷尚未完成審核，請先執行『審核』再發布。"}), 409

    conn, kind = _db_conn()
    try:
        if kind == "postgres":
            conn.execute("UPDATE quiz_categories SET title=%s, description=%s, active=%s, blind_mode=%s, draw_count=%s, passing_score=%s, audience=%s, course_id=%s, draw_rules=%s::jsonb, review_status=%s, reviewer_name=%s, reviewed_at=%s, published_at=%s WHERE id=%s", (title, desc, active, blind_mode, draw_count, passing_score, audience, course_id, json.dumps(draw_rules, ensure_ascii=False), review_status, reviewer_name, reviewed_at, published_at, category_id))
        else:
            conn.execute("UPDATE quiz_categories SET title=?, description=?, active=?, blind_mode=?, draw_count=?, passing_score=?, audience=?, course_id=?, draw_rules=?, review_status=?, reviewer_name=?, reviewed_at=?, published_at=? WHERE id=?", (title, desc, int(active), int(blind_mode), draw_count, passing_score, audience, course_id, json.dumps(draw_rules, ensure_ascii=False), review_status, reviewer_name, reviewed_at, published_at, category_id))
        if config_changed:
            ph = "%s" if kind == "postgres" else "?"
            conn.execute(f"UPDATE quiz_categories SET publication_id='', publication_hash='' WHERE id={ph}", (category_id,))
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.post("/api/quiz-categories/<category_id>/review")
def api_review_quiz_category(category_id):
    """V5.6.1 出題流程第 4 步：審核。至少需有一題啟用題，並留下審核者。"""
    denied = require_admin()
    if denied:
        return denied
    entry = get_quiz_category(category_id)
    if not entry:
        return jsonify({"error": "找不到此考卷"}), 404
    data = request.get_json(silent=True) or {}
    reviewer = str(data.get("reviewerName", "")).strip()[:100]
    if not reviewer:
        return jsonify({"error": "審核前請填寫審核者姓名"}), 400
    questions = list_quiz_questions(category_id, include_inactive=False)
    if not questions:
        return jsonify({"error": "此考卷沒有啟用中的題目，無法完成審核"}), 409
    invalid = []
    for i, q in enumerate(questions, start=1):
        if not str(q.get("question", "")).strip():
            invalid.append(f"第 {i} 題題幹空白")
        if q.get("questionType") in {"choice", "multi", "image", "video", "true_false"} and len(q.get("options") or []) < 2:
            invalid.append(f"第 {i} 題選項不足")
        if q.get("questionType") == "essay" and not str(q.get("explanation", "")).strip():
            invalid.append(f"第 {i} 題問答題缺少評分參考")
    if invalid:
        return jsonify({"error": "題目審核未通過", "issues": invalid[:20]}), 409
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn, kind = _db_conn(); ph = "%s" if kind == "postgres" else "?"
    try:
        conn.execute(f"UPDATE quiz_categories SET review_status={ph}, reviewer_name={ph}, reviewed_at={ph}, active={ph} WHERE id={ph}", ("approved", reviewer, now, False if kind == "postgres" else 0, category_id))
    finally:
        conn.close()
    return jsonify({"ok": True, "reviewStatus": "approved", "reviewerName": reviewer, "reviewedAt": now, "questionCount": len(questions)})



def _quiz_publication_snapshot(category_id: str):
    """建立不可漂移的發布快照；歷史成績可追溯當時實際考卷內容。"""
    category = get_quiz_category(category_id)
    if not category:
        raise ValueError("找不到此考卷")
    questions = list_quiz_questions(category_id, include_inactive=False)
    snapshot = {
        "schemaVersion": 1,
        "category": {
            "id": category.get("id"),
            "title": category.get("title"),
            "desc": category.get("desc", ""),
            "group": category.get("group"),
            "area": category.get("area"),
            "courseId": category.get("courseId", ""),
            "blindMode": bool(category.get("blindMode", False)),
            "drawCount": int(category.get("drawCount", 0) or 0),
            "passingScore": int(category.get("passingScore", 80) or 80),
            "audience": category.get("audience", ""),
            "drawRules": category.get("drawRules", {}) or {},
            "reviewerName": category.get("reviewerName", ""),
            "reviewedAt": category.get("reviewedAt", ""),
        },
        "questions": [{
            "id": q.get("id"),
            "tag": q.get("tag", ""),
            "question": q.get("question", ""),
            "questionType": q.get("questionType", "choice"),
            "imageUrl": q.get("imageUrl", ""),
            "options": q.get("options", []) or [],
            "correct": q.get("correct", 0),
            "answerConfig": q.get("answerConfig", {}) or {},
            "explanation": q.get("explanation", ""),
            "difficulty": q.get("difficulty", "standard"),
            "sortOrder": int(q.get("sortOrder", 0) or 0),
        } for q in questions],
    }
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    publication_id = f"pub-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')}-{digest[:10]}"
    return snapshot, digest, publication_id


@app.get("/api/quiz-categories/<category_id>/publications")
def api_quiz_publications(category_id):
    denied = require_admin()
    if denied:
        return denied
    if not get_quiz_category(category_id):
        return jsonify({"error": "找不到此考卷"}), 404
    conn, kind = _db_conn(); ph = "%s" if kind == "postgres" else "?"
    try:
        rows = conn.execute(f"SELECT id,created_at,reviewer_name,snapshot_hash FROM quiz_publications WHERE quiz_category_id={ph} ORDER BY created_at DESC LIMIT 30", (category_id,)).fetchall()
        return jsonify([{"id":dict(r).get("id",""),"createdAt":dict(r).get("created_at",""),"reviewerName":dict(r).get("reviewer_name",""),"snapshotHash":dict(r).get("snapshot_hash","")} for r in rows])
    finally:
        conn.close()


@app.post("/api/quiz-categories/<category_id>/publish")
def api_publish_quiz_category(category_id):
    """V5.6.1 出題流程第 5 步：只有已審核考卷可以發布。"""
    denied = require_admin()
    if denied:
        return denied
    entry = get_quiz_category(category_id)
    if not entry:
        return jsonify({"error": "找不到此考卷"}), 404
    if entry.get("reviewStatus") != "approved":
        return jsonify({"error": "此考卷尚未完成審核，不能發布"}), 409
    if not list_quiz_questions(category_id, include_inactive=False):
        return jsonify({"error": "此考卷沒有啟用中的題目，不能發布"}), 409
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    snapshot, snapshot_hash, publication_id = _quiz_publication_snapshot(category_id)
    conn, kind = _db_conn(); ph = "%s" if kind == "postgres" else "?"
    try:
        if kind == "postgres":
            with conn.transaction():
                conn.execute("INSERT INTO quiz_publications (id,quiz_category_id,created_at,reviewer_name,snapshot_hash,snapshot) VALUES (%s,%s,%s,%s,%s,%s::jsonb)", (publication_id, category_id, now, entry.get("reviewerName", ""), snapshot_hash, json.dumps(snapshot, ensure_ascii=False)))
                conn.execute("UPDATE quiz_categories SET active=TRUE, published_at=%s, publication_id=%s, publication_hash=%s WHERE id=%s", (now, publication_id, snapshot_hash, category_id))
        else:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO quiz_publications (id,quiz_category_id,created_at,reviewer_name,snapshot_hash,snapshot) VALUES (?,?,?,?,?,?)", (publication_id, category_id, now, entry.get("reviewerName", ""), snapshot_hash, json.dumps(snapshot, ensure_ascii=False)))
            conn.execute("UPDATE quiz_categories SET active=1, published_at=?, publication_id=?, publication_hash=? WHERE id=?", (now, publication_id, snapshot_hash, category_id))
            conn.execute("COMMIT")
    except Exception:
        if kind != "postgres":
            try: conn.execute("ROLLBACK")
            except Exception: pass
        raise
    finally:
        conn.close()
    return jsonify({"ok": True, "active": True, "publishedAt": now, "publicationId": publication_id, "publicationHash": snapshot_hash, "snapshotQuestionCount": len(snapshot.get("questions") or [])})


@app.get("/api/quiz-categories/<category_id>/materials")
def api_quiz_category_materials(category_id):
    denied=require_admin()
    if denied: return denied
    cat=get_quiz_category(category_id)
    if not cat: return jsonify({"error":"找不到此考卷"}),404
    items=[]
    for m in list_uploaded_materials(include_inactive=True):
        if m.get("group")==cat.get("group") and m.get("area")==cat.get("area"):
            items.append({
                "id":m.get("id"),"title":m.get("title") or m.get("filename"),"filename":m.get("filename",""),
                "materialType":m.get("materialType","standard"),"courseId":m.get("courseId",""),
                "category":m.get("category",""),"linked":m.get("category")==category_id,"active":m.get("active",True)
            })
    items.sort(key=lambda x:(not x["linked"], str(x.get("title","")).lower()))
    return jsonify({"categoryId":category_id,"items":items})


@app.put("/api/quiz-categories/<category_id>/materials")
def api_update_quiz_category_materials(category_id):
    denied=require_admin()
    if denied: return denied
    cat=get_quiz_category(category_id)
    if not cat: return jsonify({"error":"找不到此考卷"}),404
    data=request.get_json(silent=True) or {}
    raw=data.get("materialIds") or []
    if not isinstance(raw,list): return jsonify({"error":"materialIds 必須是陣列"}),400
    allowed={m.get("id") for m in list_uploaded_materials(include_inactive=True) if m.get("group")==cat.get("group") and m.get("area")==cat.get("area")}
    selected=[]
    for x in raw:
        mid=str(x).strip()
        if mid in allowed and mid not in selected: selected.append(mid)
    conn,kind=_db_conn()
    try:
        if kind=="postgres":
            conn.execute("UPDATE materials SET category='' WHERE category=%s",(category_id,))
            if selected:
                placeholders=','.join(['%s']*len(selected))
                conn.execute(f"UPDATE materials SET category=%s WHERE id IN ({placeholders}) AND group_key=%s AND training_area=%s",tuple([category_id]+selected+[cat.get('group'),cat.get('area')]))
        else:
            conn.execute("UPDATE materials SET category='' WHERE category=?",(category_id,))
            if selected:
                placeholders=','.join(['?']*len(selected))
                conn.execute(f"UPDATE materials SET category=? WHERE id IN ({placeholders}) AND group_key=? AND training_area=?",tuple([category_id]+selected+[cat.get('group'),cat.get('area')]))
    finally:
        conn.close()
    return jsonify({"ok":True,"linkedIds":selected,"linked":len(selected)})


@app.delete("/api/quiz-categories/<category_id>")
def api_delete_quiz_category(category_id):
    denied = require_admin()
    if denied:
        return denied
    entry = get_quiz_category(category_id)
    if not entry:
        return jsonify({"error": "找不到此考題頁籤"}), 404
    conn, kind = _db_conn()
    try:
        if kind == "postgres":
            conn.execute("DELETE FROM quiz_questions WHERE quiz_category_id=%s", (category_id,))
            conn.execute("DELETE FROM quiz_categories WHERE id=%s", (category_id,))
            conn.execute("UPDATE materials SET category='' WHERE category=%s", (category_id,))
        else:
            conn.execute("DELETE FROM quiz_questions WHERE quiz_category_id=?", (category_id,))
            conn.execute("DELETE FROM quiz_categories WHERE id=?", (category_id,))
            conn.execute("UPDATE materials SET category='' WHERE category=?", (category_id,))
    finally:
        conn.close()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# 考題 (quiz_questions) API —— 每一題屬於某一個 quiz_category
# ---------------------------------------------------------------------------
@app.post("/api/quiz-question-images")
def api_upload_question_image():
    denied = require_admin()
    if denied: return denied
    if "file" not in request.files: return jsonify({"error":"缺少圖片檔案"}), 400
    f=request.files["file"]; ext=Path(f.filename or "").suffix.lower()
    if ext not in {".png",".jpg",".jpeg",".gif",".webp"}: return jsonify({"error":"僅接受 PNG/JPG/GIF/WEBP"}),400
    name=f"{uuid.uuid4().hex}{ext}"; local=QUESTION_IMAGES_DIR/name; f.save(str(local))
    # Render 本機磁碟可能會在重新部署後消失。使用 MEGA 時把題目影像同步存進專用資料夾，
    # URL 維持固定 /question-images/<name>，既有題庫不需知道雲端細節。
    if active_material_backend() == "mega":
        try:
            _mega_free_guard(local.stat().st_size)
            remote_dir=_mega_remote_join(_mega_root_id(), "question-images")
            _mega_upload_file(local, remote_dir, name)
            try: local.unlink()
            except OSError: pass
        except Exception as exc:
            try: local.unlink()
            except OSError: pass
            return jsonify({"error":f"題目影像上傳 MEGA 失敗：{exc}"}),502
    return jsonify({"url":f"/question-images/{name}"})

@app.get("/question-images/<path:name>")
@login_required()
def question_image(name):
    safe=Path(name).name
    local=QUESTION_IMAGES_DIR/safe
    if local.exists(): return send_from_directory(str(QUESTION_IMAGES_DIR), safe)
    if active_material_backend() == "mega" and mega_is_configured():
        try:
            remote=_mega_remote_join(_mega_root_id(), "question-images", safe)
            return _mega_send_file(remote, safe, inline=True)
        except Exception:
            return jsonify({"error":"找不到題目影像"}),404
    return jsonify({"error":"找不到題目影像"}),404

@app.get("/api/quiz-questions/random")
@login_required()
def api_random_quiz_questions():
    import random
    category_id = request.args.get("category", "")
    if not category_id:
        return jsonify([])
    cat = get_quiz_category(category_id)
    if not cat or not cat.get("active", True):
        return jsonify([])
    qs = list_quiz_questions(category_id)
    # V5.4.0：前台不再輸入抽題數；0 / NULL = 全部啟用題目。
    count = int(cat.get("drawCount", 0) or 0)
    raw_override = request.args.get("count")
    if raw_override not in (None, ""):
        try:
            override = int(raw_override)
            if override > 0:
                count = override
        except (TypeError, ValueError):
            pass
    draw_rules = cat.get("drawRules", {}) if isinstance(cat.get("drawRules", {}), dict) else {}
    if draw_rules.get("mode") == "type_quota":
        quotas = draw_rules.get("quotas", {}) if isinstance(draw_rules.get("quotas", {}), dict) else {}
        target_total = sum(max(0, int(quotas.get(t, 0) or 0)) for t in ("choice","multi","true_false","fill","essay","image","video"))
        selected = []
        selected_ids = set()
        for qtype in ("choice","multi","true_false","fill","essay","image","video"):
            pool = [q for q in qs if q.get("questionType", "choice") == qtype]
            random.shuffle(pool)
            want = max(0, int(quotas.get(qtype, 0) or 0))
            for q in pool[:min(want, len(pool))]:
                selected.append(q); selected_ids.add(q.get("id"))
        if len(selected) < target_total:
            remaining = [q for q in qs if q.get("id") not in selected_ids]
            random.shuffle(remaining)
            selected.extend(remaining[:max(0, target_total-len(selected))])
        random.shuffle(selected)
        return jsonify(selected)
    random.shuffle(qs)
    return jsonify(qs if count <= 0 else qs[:min(count, len(qs))])


@app.get("/api/quiz-questions")
@login_required()
def api_list_quiz_questions():
    category_id = request.args.get("category", "")
    if not category_id:
        return jsonify({"error": "缺少 category 參數"}), 400
    return jsonify(list_quiz_questions(category_id, include_inactive=False))

@app.get("/api/quiz-questions/admin")
def api_admin_list_quiz_questions():
    denied = require_admin()
    if denied:
        return denied
    category_id = request.args.get("category", "")
    if not category_id:
        return jsonify({"error": "缺少 category 參數"}), 400
    return jsonify(list_quiz_questions(category_id, include_inactive=True))


def _mark_quiz_category_draft(category_id, conn=None, kind=None):
    """Any question-bank mutation invalidates the previous review and unpublishes the exam."""
    category_id = str(category_id or '').strip()
    if not category_id:
        return
    own_conn = conn is None
    if own_conn:
        conn, kind = _db_conn()
    ph = "%s" if kind == "postgres" else "?"
    try:
        conn.execute(
            f"UPDATE quiz_categories SET review_status={ph}, reviewer_name={ph}, reviewed_at={ph}, published_at={ph}, publication_id={ph}, publication_hash={ph}, active={ph} WHERE id={ph}",
            ("draft", "", "", "", "", "", False if kind == "postgres" else 0, category_id),
        )
    finally:
        if own_conn:
            conn.close()


@app.post("/api/quiz-questions")
def api_create_quiz_question():
    denied = require_admin()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    category_id = str(data.get("quizCategoryId", "")).strip()
    cat = get_quiz_category(category_id)
    if not cat:
        return jsonify({"error": "找不到對應的考題頁籤，請先建立頁籤"}), 400
    question = str(data.get("question", "")).strip()
    question_type = str(data.get("questionType", "choice")).lower()
    if question_type not in ("choice", "essay", "multi", "fill", "image", "video", "true_false"):
        question_type = "choice"
    image_url = str(data.get("imageUrl", "")).strip()[:1000]
    options = data.get("options", [])
    answer_config = data.get("answerConfig", {}) if isinstance(data.get("answerConfig", {}), dict) else {}
    if question_type in {"essay", "fill"}:
        options = []
    if question_type == "true_false":
        options = ["是", "否"]
    if question_type == "multi":
        indices=[]
        for x in answer_config.get("correctIndices", []):
            try: indices.append(int(x))
            except Exception: pass
        answer_config["correctIndices"] = sorted(set(indices))
    if question_type == "fill":
        answer_config["acceptedAnswers"] = [str(x).strip() for x in answer_config.get("acceptedAnswers", []) if str(x).strip()][:20]
        answer_config["caseSensitive"] = bool(answer_config.get("caseSensitive", False))
    if question_type == "video":
        answer_config["mediaUrl"] = str(answer_config.get("mediaUrl", "")).strip()[:1500]
        try: answer_config["pauseAt"] = max(0, float(answer_config.get("pauseAt", 0) or 0))
        except Exception: answer_config["pauseAt"] = 0
    tag = str(data.get("tag", "")).strip()[:100] or "一般"
    difficulty = str(data.get("difficulty", "standard") or "standard").lower()
    if difficulty not in {"basic","standard","advanced"}: difficulty = "standard"
    explanation = str(data.get("explanation", "")).strip()
    try:
        correct = int(data.get("correct", 0))
    except (TypeError, ValueError):
        correct = 0
    needs_options = question_type in {"choice", "multi", "image", "video", "true_false"}
    if not question or (needs_options and (not isinstance(options, list) or len(options) < 2)):
        return jsonify({"error": "請輸入題目；選擇／多選／圖片／影片題至少需要 2 個選項"}), 400
    options = [str(o).strip() for o in options][:6]
    if options: correct = max(0, min(len(options) - 1, correct))
    else: correct = 0
    if question_type == "multi" and not answer_config.get("correctIndices"):
        return jsonify({"error": "多選題至少要設定一個正確選項"}), 400
    if question_type == "fill" and not answer_config.get("acceptedAnswers"):
        return jsonify({"error": "填空題至少要設定一個可接受答案"}), 400
    q_id = f"q-{uuid.uuid4().hex[:12]}"
    conn, kind = _db_conn()
    try:
        existing = conn.execute(
            f"SELECT COALESCE(MAX(sort_order), -1) AS m FROM quiz_questions WHERE quiz_category_id = {'%s' if kind == 'postgres' else '?'}",
            (category_id,),
        ).fetchone()
        next_order = (existing["m"] if isinstance(existing, dict) else existing[0]) + 1
        if kind == "postgres":
            conn.execute(
                "INSERT INTO quiz_questions (id,quiz_category_id,tag,question,question_type,difficulty,image_url,options,correct,answer_config,explanation,sort_order,active) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)",
                (q_id, category_id, tag, question, question_type, difficulty, image_url, json.dumps(options, ensure_ascii=False), correct, json.dumps(answer_config, ensure_ascii=False), explanation, next_order),
            )
        else:
            conn.execute(
                "INSERT INTO quiz_questions (id,quiz_category_id,tag,question,question_type,difficulty,image_url,options,correct,answer_config,explanation,sort_order,active) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)",
                (q_id, category_id, tag, question, question_type, difficulty, image_url, json.dumps(options, ensure_ascii=False), correct, json.dumps(answer_config, ensure_ascii=False), explanation, next_order),
            )
        _mark_quiz_category_draft(category_id, conn, kind)
    finally:
        conn.close()
    return jsonify(get_quiz_question(q_id))


def _prepare_quiz_question_update(entry, data):
    """Normalize and validate a quiz-question patch without opening a DB connection."""
    data = data if isinstance(data, dict) else {}
    question = str(data.get("question", entry["question"])).strip()
    question_type = str(data.get("questionType", entry.get("questionType", "choice"))).lower()
    if question_type not in ("choice", "essay", "multi", "fill", "image", "video", "true_false"):
        question_type = "choice"
    image_url = str(data.get("imageUrl", entry.get("imageUrl", ""))).strip()[:1000]
    options = data.get("options", entry.get("options", []))
    answer_config = data.get("answerConfig", entry.get("answerConfig", {}))
    answer_config = answer_config if isinstance(answer_config, dict) else {}
    if question_type in {"essay", "fill"}:
        options = []
    if question_type == "true_false":
        options = ["是", "否"]
    if question_type in {"choice", "multi", "image", "video", "true_false"} and (not isinstance(options, list) or len(options) < 2):
        raise ValueError("此題型至少需要 2 個選項")
    options = [str(o).strip() for o in options][:6]
    if question_type == "multi":
        answer_config["correctIndices"] = sorted(set(int(x) for x in answer_config.get("correctIndices", []) if str(x).lstrip('-').isdigit()))
        if not answer_config["correctIndices"]:
            raise ValueError("多選題至少要設定一個正確選項")
    if question_type == "fill":
        answer_config["acceptedAnswers"] = [str(x).strip() for x in answer_config.get("acceptedAnswers", []) if str(x).strip()][:20]
        answer_config["caseSensitive"] = bool(answer_config.get("caseSensitive", False))
        if not answer_config["acceptedAnswers"]:
            raise ValueError("填空題至少要設定一個可接受答案")
    if question_type == "video":
        answer_config["mediaUrl"] = str(answer_config.get("mediaUrl", "")).strip()[:1500]
        try:
            answer_config["pauseAt"] = max(0, float(answer_config.get("pauseAt", 0) or 0))
        except Exception:
            answer_config["pauseAt"] = 0
    tag = str(data.get("tag", entry.get("tag", ""))).strip()[:100] or "一般"
    difficulty = str(data.get("difficulty", entry.get("difficulty", "standard")) or "standard").lower()
    if difficulty not in {"basic","standard","advanced"}: difficulty = "standard"
    explanation = str(data.get("explanation", entry.get("explanation", ""))).strip()
    active = bool(data.get("active", entry.get("active", True)))
    try:
        correct = int(data.get("correct", entry.get("correct", 0)))
    except (TypeError, ValueError):
        correct = entry.get("correct", 0)
    correct = max(0, min(len(options) - 1, correct)) if options else 0
    if not question:
        raise ValueError("題目內容不能空白")
    return {
        "question": question,
        "questionType": question_type,
        "imageUrl": image_url,
        "options": options,
        "correct": correct,
        "answerConfig": answer_config,
        "tag": tag,
        "difficulty": difficulty,
        "explanation": explanation,
        "active": active,
    }


def _execute_quiz_question_update(conn, kind, question_id, normalized):
    values = (
        normalized["tag"], normalized["question"], normalized["questionType"], normalized["difficulty"], normalized["imageUrl"],
        json.dumps(normalized["options"], ensure_ascii=False), normalized["correct"],
        json.dumps(normalized["answerConfig"], ensure_ascii=False), normalized["explanation"],
        normalized["active"], question_id,
    )
    if kind == "postgres":
        conn.execute(
            "UPDATE quiz_questions SET tag=%s, question=%s, question_type=%s, difficulty=%s, image_url=%s, options=%s, correct=%s, answer_config=%s, explanation=%s, active=%s WHERE id=%s",
            values,
        )
    else:
        values = values[:-2] + (int(bool(normalized["active"])), question_id)
        conn.execute(
            "UPDATE quiz_questions SET tag=?, question=?, question_type=?, difficulty=?, image_url=?, options=?, correct=?, answer_config=?, explanation=?, active=? WHERE id=?",
            values,
        )


@app.patch("/api/quiz-questions/<question_id>")
def api_update_quiz_question(question_id):
    denied = require_admin()
    if denied:
        return denied
    entry = get_quiz_question(question_id)
    if not entry:
        return jsonify({"error": "找不到此題目"}), 404
    data = request.get_json(silent=True) or {}
    try:
        normalized = _prepare_quiz_question_update(entry, data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    conn, kind = _db_conn()
    try:
        _execute_quiz_question_update(conn, kind, question_id, normalized)
        _mark_quiz_category_draft(entry.get("quizCategoryId"), conn, kind)
    finally:
        conn.close()
    return jsonify({"ok": True, "question": {"id": question_id, **normalized}})


@app.patch("/api/quiz-questions/batch")
def api_batch_update_quiz_questions():
    """Update many questions in one HTTP request and one DB connection."""
    denied = require_admin()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    items = data.get("items") or []
    if not isinstance(items, list) or not items:
        return jsonify({"error": "items 必須是非空陣列"}), 400
    if len(items) > 200:
        return jsonify({"error": "一次最多更新 200 題"}), 400
    requested = []
    patches = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        qid = str(item.get("id", "")).strip()
        if not qid or qid in patches:
            continue
        requested.append(qid)
        patches[qid] = item.get("data") if isinstance(item.get("data"), dict) else {k:v for k,v in item.items() if k != "id"}
    if not requested:
        return jsonify({"error": "沒有有效題目"}), 400
    conn, kind = _db_conn()
    try:
        ph = "%s" if kind == "postgres" else "?"
        placeholders = ",".join([ph] * len(requested))
        rows = conn.execute(f"SELECT * FROM quiz_questions WHERE id IN ({placeholders})", tuple(requested)).fetchall()
        existing = {str(quiz_question_row_to_dict(r).get("id")): quiz_question_row_to_dict(r) for r in rows}
        missing = [qid for qid in requested if qid not in existing]
        if missing:
            return jsonify({"error": f"找不到 {len(missing)} 題", "missing": missing}), 404
        normalized_items = []
        for qid in requested:
            try:
                normalized = _prepare_quiz_question_update(existing[qid], patches[qid])
            except ValueError as exc:
                return jsonify({"error": f"題目 {qid}：{exc}"}), 400
            normalized_items.append((qid, normalized))
        for qid, normalized in normalized_items:
            _execute_quiz_question_update(conn, kind, qid, normalized)
        for category_id in {str(existing[qid].get("quizCategoryId", "")) for qid in requested}:
            _mark_quiz_category_draft(category_id, conn, kind)
        return jsonify({"ok": True, "updated": [{"id": qid, **normalized} for qid, normalized in normalized_items], "count": len(normalized_items), "reviewInvalidated": True})
    finally:
        conn.close()


@app.post("/api/quiz-questions/batch-delete")
def api_batch_delete_quiz_questions():
    denied = require_admin()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    ids = data.get("ids") or []
    ids = list(dict.fromkeys(str(x).strip() for x in ids if str(x).strip())) if isinstance(ids, list) else []
    if not ids:
        return jsonify({"error": "ids 必須是非空陣列"}), 400
    if len(ids) > 200:
        return jsonify({"error": "一次最多刪除 200 題"}), 400
    conn, kind = _db_conn()
    try:
        ph = "%s" if kind == "postgres" else "?"
        placeholders = ",".join([ph] * len(ids))
        category_rows = conn.execute(f"SELECT DISTINCT quiz_category_id FROM quiz_questions WHERE id IN ({placeholders})", tuple(ids)).fetchall()
        category_ids = {str(dict(r).get("quiz_category_id", "")) for r in category_rows}
        conn.execute(f"DELETE FROM quiz_questions WHERE id IN ({placeholders})", tuple(ids))
        for category_id in category_ids:
            _mark_quiz_category_draft(category_id, conn, kind)
        return jsonify({"ok": True, "deleted": ids, "count": len(ids), "reviewInvalidated": True})
    finally:
        conn.close()


@app.post("/api/quiz-questions/import-url")
def api_import_quiz_questions_url():
    """從公開 HTTPS/HTTP JSON 或 CSV 連結批次匯入題庫。避免 SSRF：拒絕本機與私有 IP。"""
    denied = require_admin()
    if denied: return denied
    import csv, io, ipaddress, socket, urllib.parse, urllib.request
    data = request.get_json(silent=True) or {}
    category_id = str(data.get("quizCategoryId", "")).strip()
    url = str(data.get("url", "")).strip()
    if not get_quiz_category(category_id): return jsonify({"error":"找不到考題頁籤"}),400
    p=urllib.parse.urlparse(url)
    if p.scheme not in ("http","https") or not p.hostname: return jsonify({"error":"僅接受公開 HTTP/HTTPS 連結"}),400
    try:
        for info in socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme=="https" else 80), type=socket.SOCK_STREAM):
            ip=ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return jsonify({"error":"基於安全性，不允許讀取內網或本機網址"}),400
    except Exception: return jsonify({"error":"無法解析該網址"}),400
    try:
        req=urllib.request.Request(url, headers={"User-Agent":"HospitalTrainingImporter/1.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw=resp.read(5*1024*1024+1)
            ctype=(resp.headers.get("Content-Type") or "").lower()
        if len(raw)>5*1024*1024: return jsonify({"error":"題庫檔案超過 5MB"}),400
        text=raw.decode("utf-8-sig")
        if "json" in ctype or url.lower().split("?")[0].endswith(".json"):
            items=json.loads(text); items=items.get("questions",[]) if isinstance(items,dict) else items
        else:
            items=list(csv.DictReader(io.StringIO(text)))
    except Exception as e: return jsonify({"error":f"讀取或解析連結失敗：{e}"}),400
    if not isinstance(items,list): return jsonify({"error":"JSON 格式需為題目陣列，或使用 questions 陣列"}),400
    imported=0; errors=[]
    for idx,item in enumerate(items[:500],1):
        if not isinstance(item,dict): continue
        qtext=str(item.get("question") or item.get("題目") or "").strip()
        qtype=str(item.get("questionType") or item.get("type") or item.get("題型") or "choice").strip().lower()
        qtype_alias = {
            "問答題":"essay", "申論題":"essay", "text":"essay", "essay":"essay",
            "多選題":"multi", "複選題":"multi", "multi":"multi", "multiple":"multi",
            "填空題":"fill", "fill":"fill", "blank":"fill",
            "圖片題":"image", "圖片判讀題":"image", "image":"image",
            "影片題":"video", "video":"video",
            "選擇題":"choice", "單選題":"choice", "choice":"choice", "single":"choice",
        }
        qtype = qtype_alias.get(qtype, "choice")
        options=item.get("options")
        if isinstance(options,str):
            try: options=json.loads(options)
            except Exception: options=[x.strip() for x in options.split("|") if x.strip()]
        if not isinstance(options,list): options=[str(item.get(k,"" )).strip() for k in ("optionA","optionB","optionC","optionD","optionE","optionF") if str(item.get(k,"" )).strip()]
        corr=item.get("correct", item.get("answer", 0))
        if isinstance(corr,str) and corr.upper() in "ABCDEF": corr="ABCDEF".index(corr.upper())
        try: corr=int(corr)
        except Exception: corr=0
        answer_config=item.get("answerConfig", {})
        if isinstance(answer_config,str):
            try: answer_config=json.loads(answer_config)
            except Exception: answer_config={}
        if not isinstance(answer_config,dict): answer_config={}
        if qtype=="multi" and not answer_config.get("correctIndices"):
            raw_multi=item.get("correctIndices", item.get("正確選項", ""))
            if isinstance(raw_multi,str):
                answer_config["correctIndices"]=["ABCDEF".index(x) for x in re.findall(r"[A-F]", raw_multi.upper())]
            elif isinstance(raw_multi,list): answer_config["correctIndices"]=raw_multi
        if qtype=="fill" and not answer_config.get("acceptedAnswers"):
            raw_fill=item.get("acceptedAnswers", item.get("可接受答案", item.get("標準答案", "")))
            if isinstance(raw_fill,str): answer_config["acceptedAnswers"]=[x.strip() for x in raw_fill.split("|") if x.strip()]
            elif isinstance(raw_fill,list): answer_config["acceptedAnswers"]=raw_fill
        if qtype=="true_false":
            options=["是","否"]
        if qtype=="video":
            answer_config.setdefault("mediaUrl", str(item.get("mediaUrl", item.get("影片網址", ""))).strip())
            try: answer_config.setdefault("pauseAt", float(item.get("pauseAt", item.get("時間點", 0)) or 0))
            except Exception: answer_config.setdefault("pauseAt", 0)
        needs_options=qtype in {"choice","multi","image","video","true_false"}
        if not qtext or (needs_options and len(options)<2): errors.append(f"第{idx}題格式不足"); continue
        if qtype=="multi" and not answer_config.get("correctIndices"): errors.append(f"第{idx}題缺少多選正確答案"); continue
        if qtype=="fill" and not answer_config.get("acceptedAnswers"): errors.append(f"第{idx}題缺少填空可接受答案"); continue
        payload={"quizCategoryId":category_id,"question":qtext,"questionType":qtype,"difficulty":item.get("difficulty",item.get("難度","standard")),"options":options,"correct":corr,"answerConfig":answer_config,"tag":item.get("tag",item.get("分類","一般")),"explanation":item.get("explanation",item.get("詳解","")),"imageUrl":item.get("imageUrl","")}
        # directly insert using same validation core
        q_id=f"q-{uuid.uuid4().hex[:12]}"; conn,kind=_db_conn()
        try:
            ex=conn.execute(f"SELECT COALESCE(MAX(sort_order), -1) AS m FROM quiz_questions WHERE quiz_category_id = {'%s' if kind=='postgres' else '?'}",(category_id,)).fetchone(); order=(ex["m"] if isinstance(ex,dict) else ex[0])+1
            opts=[str(o).strip() for o in options][:6]; corr=max(0,min(len(opts)-1,corr)) if opts else 0
            difficulty=str(payload.get('difficulty','standard') or 'standard').lower(); difficulty=difficulty if difficulty in {'basic','standard','advanced'} else 'standard'
            vals=(q_id,category_id,str(payload['tag'])[:100],qtext,qtype,difficulty,str(payload['imageUrl'])[:1000],json.dumps(opts,ensure_ascii=False),corr,json.dumps(payload.get('answerConfig',{}),ensure_ascii=False),str(payload['explanation']),order)
            if kind=='postgres': conn.execute("INSERT INTO quiz_questions (id,quiz_category_id,tag,question,question_type,difficulty,image_url,options,correct,answer_config,explanation,sort_order,active) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)",vals)
            else: conn.execute("INSERT INTO quiz_questions (id,quiz_category_id,tag,question,question_type,difficulty,image_url,options,correct,answer_config,explanation,sort_order,active) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)",vals)
            imported+=1
        finally: conn.close()
    if imported:
        _mark_quiz_category_draft(category_id)
    return jsonify({"ok":True,"imported":imported,"errors":errors[:20],"reviewInvalidated":bool(imported)})

@app.delete("/api/quiz-questions/<question_id>")
def api_delete_quiz_question(question_id):
    denied = require_admin()
    if denied:
        return denied
    entry = get_quiz_question(question_id)
    if not entry:
        return jsonify({"error": "找不到此題目"}), 404
    conn, kind = _db_conn()
    try:
        if kind == "postgres":
            conn.execute("DELETE FROM quiz_questions WHERE id=%s", (question_id,))
        else:
            conn.execute("DELETE FROM quiz_questions WHERE id=?", (question_id,))
        _mark_quiz_category_draft(entry.get("quizCategoryId"), conn, kind)
    finally:
        conn.close()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# 附件1 Word 匯出範本 (doc_templates) API
# ---------------------------------------------------------------------------
DOC_TEMPLATE_ALLOWED_EXT = {".docx"}
MAX_DOC_TEMPLATE_MB = max(1, min(50, int(os.environ.get("MAX_DOC_TEMPLATE_MB", "20"))))

def _validate_template_file(path: Path, ext: str, max_mb: int):
    """驗證副檔名之外的實際內容；拒絕只改副檔名、空檔與損壞的 DOCX/PDF。"""
    if not path.exists():
        raise ValueError("檔案不存在")
    size = path.stat().st_size
    if size <= 0:
        raise ValueError("檔案是空的")
    if size > int(max_mb) * 1024 * 1024:
        raise ValueError(f"檔案過大，上限 {int(max_mb)}MB")
    if ext == ".docx":
        if size < 800:
            raise ValueError("DOCX 檔案內容過小，可能已損壞或只是改副檔名")
        try:
            with zipfile.ZipFile(path, "r") as zf:
                names=set(zf.namelist())
                required={"[Content_Types].xml","word/document.xml"}
                if not required.issubset(names):
                    raise ValueError("檔案不是有效的 Word DOCX 結構")
                bad=zf.testzip()
                if bad:
                    raise ValueError(f"DOCX 壓縮結構損壞：{bad}")
                xml=zf.read("word/document.xml")
                ET.fromstring(xml)
        except ValueError:
            raise
        except (zipfile.BadZipFile, ET.ParseError, OSError) as exc:
            raise ValueError(f"DOCX 檔案損壞或格式不正確：{exc}")
        return {"kind":"docx","sizeBytes":size}
    if ext == ".pdf":
        head=path.read_bytes()[:8]
        if not head.startswith(b"%PDF-"):
            raise ValueError("檔案內容不是有效 PDF，請勿只修改副檔名")
        try:
            if pymupdf is not None:
                doc=pymupdf.open(str(path))
                pages=doc.page_count
                doc.close()
                if pages < 1:
                    raise ValueError("PDF 沒有可讀頁面")
            else:
                tail=path.read_bytes()[-2048:]
                if b"%%EOF" not in tail:
                    raise ValueError("PDF 結構不完整或已損壞")
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"PDF 無法解析：{exc}")
        return {"kind":"pdf","sizeBytes":size}
    raise ValueError("不支援的範本格式")


@app.get("/api/doc-templates")
def api_list_doc_templates():
    """公開：各組別是否已設定範本（前端匯出前用來判斷要不要先提示管理者上傳）。"""
    rows = list_doc_templates()
    return jsonify([
        {
            "group": g,
            "label": label,
            "exists": g in rows,
            "filename": rows.get(g, {}).get("filename", ""),
            "uploadedAt": rows.get(g, {}).get("uploaded_at", ""),
            "storageBackend": rows.get(g, {}).get("storage_backend", "local") or "local",
        }
        for g, label in GROUPS.items()
    ])


@app.post("/api/doc-templates/<group_key>")
def api_upload_doc_template(group_key):
    denied = require_admin()
    if denied:
        return denied
    if group_key not in GROUPS:
        return jsonify({"error": "無效的組別代碼"}), 400
    if "file" not in request.files:
        return jsonify({"error": "缺少檔案"}), 400
    file = request.files["file"]
    original_name = file.filename or "附件1.docx"
    ext = Path(original_name).suffix.lower()
    if ext not in DOC_TEMPLATE_ALLOWED_EXT:
        return jsonify({"error": "僅接受 .docx 檔案"}), 400
    old = get_doc_template_row(group_key)
    storage_filename = f"{group_key}.docx"
    tmp_path = TMP_DIR / f"doc-template-{group_key}-{uuid.uuid4().hex[:8]}.docx"
    backend = "local"
    storage_key = ""
    try:
        file.save(str(tmp_path))
        validation=_validate_template_file(tmp_path, ext, MAX_DOC_TEMPLATE_MB)
        # Word 範本跟教材採相同儲存後端；Google Drive 設定完成時不再依賴 Render 暫存磁碟。
        backend = active_material_backend()
        if backend == "mega":
            _mega_free_guard(tmp_path.stat().st_size)
            root=_mega_root_id(); folder_id=_mega_remote_join(root, "doc-templates"); _mega_ensure_dir(folder_id)
            storage_key=_mega_upload_file(tmp_path,folder_id,f"word-template-{group_key}-{uuid.uuid4().hex[:8]}.docx")
        elif backend == "oci":
            storage_key = f"doc_templates/{group_key}/{uuid.uuid4().hex}.docx"
            oci_put_file(tmp_path, storage_key, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        elif backend == "gdrive":
            uploaded = gdrive_upload_file(
                tmp_path,
                f"word-template-{group_key}.docx",
                GDRIVE_FOLDER_ID,
                {"smh_kind": "doc_template", "smh_group": group_key},
            )
            storage_key = uploaded["id"]
        elif backend == "r2":
            storage_key = f"doc_templates/{group_key}/{uuid.uuid4().hex}.docx"
            r2_put_file(tmp_path, storage_key, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        else:
            backend = "local"
            local_path = DOC_TEMPLATES_DIR / storage_filename
            shutil.copy2(tmp_path, local_path)

        # 新檔成功後才刪除舊的遠端檔，避免上傳失敗造成範本遺失。
        if old:
            old_backend = (old.get("storage_backend") or "local").lower()
            old_key = old.get("storage_key") or ""
            try:
                if old_backend == "mega" and old_key and old_key != storage_key and mega_is_configured():
                    mega_destroy(old_key)
                elif old_backend == "oci" and old_key and old_key != storage_key and oci_is_configured():
                    oci_client().delete_object(Bucket=OCI_BUCKET_NAME, Key=old_key)
                elif old_backend == "gdrive" and old_key and old_key != storage_key:
                    gdrive_delete_file(old_key)
                elif old_backend == "r2" and old_key and old_key != storage_key and r2_is_configured():
                    r2_client().delete_object(Bucket=R2_BUCKET_NAME, Key=old_key)
                elif old_backend == "local":
                    old_path = DOC_TEMPLATES_DIR / (old.get("storage_filename") or storage_filename)
                    if backend != "local" and old_path.exists():
                        old_path.unlink()
            except Exception as cleanup_exc:
                app.logger.warning("old doc template cleanup failed: %s", cleanup_exc)

        save_doc_template_row(group_key, original_name, storage_filename, backend, storage_key)
        return jsonify({"ok": True, "group": group_key, "filename": original_name, "storageBackend": backend, "validation": validation})
    except ValueError as exc:
        return jsonify({"error": f"Word 範本檢查失敗：{exc}", "stage": "範本內容驗證"}), 400
    except Exception as exc:
        app.logger.exception("doc template upload failed")
        # 若遠端新檔已建立但 DB 尚未完成，盡量清掉孤兒檔。
        try:
            if backend == "mega" and storage_key and mega_is_configured():
                mega_destroy(storage_key)
            elif backend == "oci" and storage_key and oci_is_configured():
                oci_client().delete_object(Bucket=OCI_BUCKET_NAME, Key=storage_key)
            elif backend == "gdrive" and storage_key:
                gdrive_delete_file(storage_key)
            elif backend == "r2" and storage_key and r2_is_configured():
                r2_client().delete_object(Bucket=R2_BUCKET_NAME, Key=storage_key)
        except Exception:
            pass
        return jsonify({"error": f"Word 範本上傳失敗：{exc}"}), 500
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


@app.get("/api/doc-templates/<group_key>/download")
def api_download_doc_template(group_key):
    """提供前端 docxtemplater 讀取範本；支援 Google Drive / R2 / 本機。"""
    row = get_doc_template_row(group_key)
    if not row:
        return jsonify({"error": "此組別尚未上傳 Word 匯出範本"}), 404
    backend = (row.get("storage_backend") or "local").lower()
    key = row.get("storage_key") or ""
    if backend == "mega":
        if not mega_is_configured(): return jsonify({"error":"MEGA 尚未設定完成，無法讀取 Word 範本"}),503
        try: return _mega_send_file(key,row["filename"],inline=True)
        except Exception as e: return jsonify({"error":f"MEGA 讀取 Word 範本失敗：{e}"}),502
    if backend == "oci":
        if not oci_is_configured():
            return jsonify({"error":"Oracle Object Storage 尚未設定完成，無法讀取 Word 範本"}), 503
        return redirect(oci_presigned_get(key, download_name=row["filename"], inline=True))
    if backend == "gdrive":
        if not gdrive_is_configured():
            return jsonify({"error": "Google Drive 尚未設定完成，無法讀取 Word 範本"}), 503
        return gdrive_proxy_file(key, row["filename"], inline=True)
    if backend == "r2":
        if not r2_is_configured():
            return jsonify({"error": "Cloudflare R2 尚未設定完成，無法讀取 Word 範本"}), 503
        return redirect(r2_presigned_get(key, download_name=row["filename"], inline=True))
    path = DOC_TEMPLATES_DIR / row["storage_filename"]
    if not path.exists():
        return jsonify({"error": "範本檔案遺失，請管理者重新上傳"}), 404
    return send_file(path, as_attachment=False, download_name=row["filename"])


@app.delete("/api/doc-templates/<group_key>")
def api_delete_doc_template(group_key):
    denied = require_admin()
    if denied:
        return denied
    row = get_doc_template_row(group_key)
    if row:
        backend = (row.get("storage_backend") or "local").lower()
        key = row.get("storage_key") or ""
        try:
            if backend == "mega" and key and mega_is_configured():
                mega_destroy(key)
            elif backend == "oci" and key and oci_is_configured():
                oci_client().delete_object(Bucket=OCI_BUCKET_NAME, Key=key)
            elif backend == "gdrive" and key and gdrive_is_configured():
                gdrive_delete_file(key)
            elif backend == "r2" and key and r2_is_configured():
                r2_client().delete_object(Bucket=R2_BUCKET_NAME, Key=key)
            else:
                path = DOC_TEMPLATES_DIR / row["storage_filename"]
                if path.exists():
                    path.unlink()
        finally:
            delete_doc_template_row(group_key)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# V5 課程 / PGY 學習進度 / 問答題人工審閱
# ---------------------------------------------------------------------------
@app.get("/api/courses")
@login_required()
def api_courses():
    area=normalize_area(request.args.get("area", DEFAULT_TRAINING_AREA))
    group=request.args.get("group", "")
    group=normalize_group(group) if group else None
    return jsonify(list_courses(area, group, False))

@app.get("/api/courses/admin")
def api_courses_admin():
    denied=require_admin()
    if denied: return denied
    area=request.args.get("area", "") or None
    group=request.args.get("group", "") or None
    return jsonify(list_courses(normalize_area(area) if area else None, normalize_group(group) if group else None, True))

@app.post("/api/courses")
def api_create_course():
    denied=require_admin()
    if denied: return denied
    data=request.get_json(silent=True) or {}
    area=normalize_area(str(data.get("area", "pgy")))
    group=normalize_group(str(data.get("group", DEFAULT_GROUP)))
    title=str(data.get("title","")).strip()[:255]
    desc=str(data.get("desc","")).strip()[:2000]
    if not title: return jsonify({"error":"請輸入課程名稱"}),400
    course_id=f"course-{uuid.uuid4().hex[:12]}"
    conn,kind=_db_conn(); ph='%s' if kind=='postgres' else '?'
    try:
        row=conn.execute(f"SELECT COALESCE(MAX(sort_order),-1) AS m FROM courses WHERE training_area={ph} AND group_key={ph}",(area,group)).fetchone()
        order=(row['m'] if isinstance(row,dict) else row[0])+1
        date_added=datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        if kind=='postgres': conn.execute("INSERT INTO courses (id,training_area,group_key,title,description,sort_order,date_added,active) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",(course_id,area,group,title,desc,order,date_added,True))
        else: conn.execute("INSERT INTO courses (id,training_area,group_key,title,description,sort_order,date_added,active) VALUES (?,?,?,?,?,?,?,?)",(course_id,area,group,title,desc,order,date_added,1))
    finally: conn.close()
    return jsonify(get_course(course_id))

@app.patch("/api/courses/<course_id>")
def api_update_course(course_id):
    denied=require_admin()
    if denied: return denied
    entry=get_course(course_id)
    if not entry: return jsonify({"error":"找不到課程"}),404
    data=request.get_json(silent=True) or {}
    title=str(data.get('title',entry['title'])).strip()[:255]
    desc=str(data.get('desc',entry.get('desc',''))).strip()[:2000]
    active=bool(data.get('active',entry.get('active',True)))
    conn,kind=_db_conn()
    try:
        if kind=='postgres': conn.execute("UPDATE courses SET title=%s,description=%s,active=%s WHERE id=%s",(title,desc,active,course_id))
        else: conn.execute("UPDATE courses SET title=?,description=?,active=? WHERE id=?",(title,desc,int(active),course_id))
    finally: conn.close()
    return jsonify({"ok":True})

@app.delete("/api/courses/<course_id>")
def api_delete_course(course_id):
    denied=require_admin()
    if denied: return denied
    if not get_course(course_id): return jsonify({"error":"找不到課程"}),404
    conn,kind=_db_conn(); ph='%s' if kind=='postgres' else '?'
    try:
        conn.execute(f"UPDATE materials SET course_id='' WHERE course_id={ph}",(course_id,))
        conn.execute(f"UPDATE quiz_categories SET course_id='' WHERE course_id={ph}",(course_id,))
        conn.execute(f"DELETE FROM courses WHERE id={ph}",(course_id,))
    finally: conn.close()
    return jsonify({"ok":True})

@app.get('/api/courses/<course_id>/plan')
def api_get_teaching_plan(course_id):
    denied = require_admin()
    if denied: return denied
    course = get_course(course_id)
    if not course: return jsonify({'error': '找不到課程'}), 404
    materials = [m for m in list_uploaded_materials(True) if m.get('courseId') == course_id]
    return jsonify({'course': course, 'materials': materials})


@app.put('/api/courses/<course_id>/plan')
def api_save_teaching_plan(course_id):
    denied = require_admin()
    if denied: return denied
    course = get_course(course_id)
    if not course: return jsonify({'error': '找不到課程'}), 404
    data = request.get_json(silent=True)
    if not isinstance(data, dict): return jsonify({'error': '課程資料格式不正確'}), 400
    try:
        title = data.get('title', course['title'])
        desc = data.get('desc', course['desc'])
        objectives = data.get('learningObjectives', course['learningObjectives'])
        if not isinstance(title, str) or not title.strip() or len(title) > 255:
            raise ValueError('請輸入 1–255 字的課程名稱')
        if not isinstance(desc, str) or len(desc) > 2000 or not isinstance(objectives, str) or len(objectives) > 4000:
            raise ValueError('課程說明限 2000 字，學習目標限 4000 字')
        minutes = data.get('estimatedMinutes', course['estimatedMinutes'])
        order = data.get('sortOrder', course['sortOrder'])
        if type(minutes) is not int or not 0 <= minutes <= 10000 or type(order) is not int or not 0 <= order <= 100000:
            raise ValueError('建議分鐘數與顯示順序須為有效非負整數')
        start = data.get('startDate', course['startDate'])
        end = data.get('endDate', course['endDate'])
        for date in (start, end):
            if not isinstance(date, str): raise ValueError('日期格式不正確')
            if date and (not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date) or not datetime.date.fromisoformat(date)):
                raise ValueError('日期格式不正確')
        if start and end and start > end: raise ValueError('結束日期不可早於開始日期')
        active = data.get('active', course['active'])
        if type(active) is not bool: raise ValueError('課程狀態格式不正確')
        material_order = data.get('materialOrder', course['materialOrder'])
        if not isinstance(material_order, list) or any(not isinstance(x, str) for x in material_order) or len(set(material_order)) != len(material_order):
            raise ValueError('教材順序格式不正確或含重複教材')
    except (ValueError, TypeError) as exc:
        return jsonify({'error': str(exc)}), 400
    conn, kind = _db_conn()
    ph = '%s' if kind == 'postgres' else '?'
    try:
        conn.execute('BEGIN')
        rows = conn.execute(f'SELECT id FROM materials WHERE course_id={ph}', (course_id,)).fetchall()
        valid = {dict(r)['id'] for r in rows}
        if set(material_order) != valid:
            conn.rollback()
            return jsonify({'error': '教材清單已變更，請關閉後重新開啟課程編排再儲存'}), 409
        values = (title.strip(), desc.strip(), objectives.strip(), minutes, start, end, json.dumps(material_order), order, active if kind == 'postgres' else int(active), course_id)
        fields = ['title', 'description', 'learning_objectives', 'estimated_minutes', 'start_date', 'end_date', 'material_order', 'sort_order', 'active']
        conn.execute(f"UPDATE courses SET {','.join(f'{field}={ph}' for field in fields)} WHERE id={ph}", values)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return jsonify(get_course(course_id))


@app.post("/api/material-progress")
@login_required()
def api_material_progress():
    data=request.get_json(silent=True) or {}
    user=_current_user()
    emp_id=user['empId']
    name=user['name']
    material_id=str(data.get('materialId','')).strip()[:100]
    if not emp_id or not name or not material_id: return jsonify({"error":"請先輸入姓名、工號，並指定教材"}),400
    if not get_material(material_id): return jsonify({"error":"找不到教材"}),404
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn,kind=_db_conn()
    try:
        if kind=='postgres': conn.execute("INSERT INTO material_progress (emp_id,name,material_id,completed_at) VALUES (%s,%s,%s,%s) ON CONFLICT (emp_id,material_id) DO UPDATE SET name=EXCLUDED.name, completed_at=EXCLUDED.completed_at",(emp_id,name,material_id,now))
        else: conn.execute("INSERT INTO material_progress (emp_id,name,material_id,completed_at) VALUES (?,?,?,?) ON CONFLICT(emp_id,material_id) DO UPDATE SET name=excluded.name, completed_at=excluded.completed_at",(emp_id,name,material_id,now))
    finally: conn.close()
    return jsonify({"ok":True,"completedAt":now})

@app.get("/api/my-progress")
@login_required()
def api_my_progress():
    user=_current_user()
    emp_id=user['empId']
    name=user['name']
    area=normalize_area(request.args.get('area','pgy'))
    group=normalize_group(request.args.get('group',DEFAULT_GROUP))
    if not emp_id or not name: return jsonify({"error":"請輸入姓名與工號"}),400
    conn,kind=_db_conn(); ph='%s' if kind=='postgres' else '?'
    try:
        progress_rows=conn.execute(f"SELECT material_id,completed_at FROM material_progress WHERE emp_id={ph}",(emp_id,)).fetchall()
        completed={dict(r)['material_id']:dict(r)['completed_at'] for r in progress_rows}
        record_rows=conn.execute(f"SELECT * FROM exam_records WHERE emp_id={ph} AND training_area={ph} AND group_key={ph} ORDER BY created_at DESC",(emp_id,area,group)).fetchall()
        records=[_record_to_dict(r) for r in record_rows]
    finally: conn.close()
    courses=list_courses(area,group,False)
    mats=[m for m in list_uploaded_materials(False) if m.get('area')==area and m.get('group')==group]
    cats=list_quiz_categories(group,area,False)
    result=[]
    for c in courses:
        cm=[m for m in mats if m.get('courseId')==c['id']]
        cq=[q for q in cats if q.get('courseId')==c['id']]
        done=sum(1 for m in cm if m['id'] in completed)
        course_records=[r for r in records if r.get('courseId')==c['id']]
        passed=any(r.get('reviewStatus')=='completed' and int(r.get('score',0))>=int(r.get('passingScore',80) or 80) for r in course_records)
        has_exam=len(cq)>0
        complete=(done==len(cm)) and (passed if has_exam else True) and (len(cm)>0 or has_exam)
        result.append({**c,'materialsTotal':len(cm),'materialsCompleted':done,'examRequired':has_exam,'examPassed':passed,'completed':complete})
    return jsonify({'courses':result,'materialsCompleted':completed,'records':records})


def _announcement_row_to_dict(row):
    d = dict(row)
    return {
        "id": str(d.get("id", "")),
        "title": str(d.get("title", "")),
        "body": str(d.get("body", "")),
        "active": bool(d.get("active", True)),
        "createdAt": str(d.get("created_at", "")),
        "publishedAt": str(d.get("published_at", "")),
    }


@app.get("/api/announcements")
def api_announcements_public():
    try:
        limit = max(1, min(50, int(request.args.get("limit", "8"))))
    except (TypeError, ValueError):
        limit = 8
    conn, kind = _db_conn(); ph = "%s" if kind == "postgres" else "?"
    try:
        rows = conn.execute(
            f"SELECT * FROM announcements WHERE active={ph} ORDER BY published_at DESC, created_at DESC LIMIT {limit}",
            (True if kind == "postgres" else 1,)
        ).fetchall()
        return jsonify([_announcement_row_to_dict(r) for r in rows])
    finally:
        conn.close()


@app.get("/api/announcements/admin")
def api_announcements_admin():
    denied = require_admin()
    if denied: return denied
    conn, _kind = _db_conn()
    try:
        rows = conn.execute("SELECT * FROM announcements ORDER BY created_at DESC").fetchall()
        return jsonify([_announcement_row_to_dict(r) for r in rows])
    finally:
        conn.close()


@app.post("/api/announcements")
def api_announcements_create():
    denied = require_admin()
    if denied: return denied
    data = request.get_json(silent=True) or {}
    title = str(data.get("title", "")).strip()[:200]
    body = str(data.get("body", "")).strip()[:4000]
    if not title:
        return jsonify({"error": "公告標題不能空白"}), 400
    aid = uuid.uuid4().hex
    now = _utc_now_iso()
    active = bool(data.get("active", True))
    conn, kind = _db_conn()
    try:
        if kind == "postgres":
            conn.execute("INSERT INTO announcements (id,title,body,active,created_at,published_at) VALUES (%s,%s,%s,%s,%s,%s)", (aid,title,body,active,now,now if active else ""))
        else:
            conn.execute("INSERT INTO announcements (id,title,body,active,created_at,published_at) VALUES (?,?,?,?,?,?)", (aid,title,body,1 if active else 0,now,now if active else ""))
        row = conn.execute("SELECT * FROM announcements WHERE id=" + ("%s" if kind == "postgres" else "?"), (aid,)).fetchone()
        return jsonify(_announcement_row_to_dict(row)), 201
    finally:
        conn.close()


@app.patch("/api/announcements/<announcement_id>")
def api_announcements_update(announcement_id):
    denied = require_admin()
    if denied: return denied
    data = request.get_json(silent=True) or {}
    conn, kind = _db_conn(); ph = "%s" if kind == "postgres" else "?"
    try:
        row = conn.execute(f"SELECT * FROM announcements WHERE id={ph}", (announcement_id,)).fetchone()
        if not row: return jsonify({"error": "找不到公告"}), 404
        old = _announcement_row_to_dict(row)
        title = str(data.get("title", old["title"])).strip()[:200]
        body = str(data.get("body", old["body"])).strip()[:4000]
        active = bool(data.get("active", old["active"]))
        if not title: return jsonify({"error": "公告標題不能空白"}), 400
        published = old["publishedAt"] or (_utc_now_iso() if active else "")
        if kind == "postgres":
            conn.execute("UPDATE announcements SET title=%s,body=%s,active=%s,published_at=%s WHERE id=%s", (title,body,active,published,announcement_id))
        else:
            conn.execute("UPDATE announcements SET title=?,body=?,active=?,published_at=? WHERE id=?", (title,body,1 if active else 0,published,announcement_id))
        row = conn.execute(f"SELECT * FROM announcements WHERE id={ph}", (announcement_id,)).fetchone()
        return jsonify(_announcement_row_to_dict(row))
    finally:
        conn.close()


@app.delete("/api/announcements/<announcement_id>")
def api_announcements_delete(announcement_id):
    denied = require_admin()
    if denied: return denied
    conn, kind = _db_conn(); ph = "%s" if kind == "postgres" else "?"
    try:
        row = conn.execute(f"SELECT id FROM announcements WHERE id={ph}", (announcement_id,)).fetchone()
        if not row: return jsonify({"error": "找不到公告"}), 404
        conn.execute(f"DELETE FROM announcements WHERE id={ph}", (announcement_id,))
        return jsonify({"ok": True})
    finally:
        conn.close()


@app.get("/api/dashboard/me")
@login_required()
def api_dashboard_me():
    """V5.6.1 個人化首頁摘要。

    empId 是唯一識別；name 只用於顯示與補足舊資料，不再作為查詢條件。
    首頁只讀既有教材完成、考試與 PGY 評核，不建立第二套學習紀錄。
    """
    user = _current_user()
    emp_id = user['empId']
    requested_name = user['name']

    conn, kind = _db_conn(); ph = '%s' if kind == 'postgres' else '?'
    try:
        progress_rows = conn.execute(
            f"SELECT material_id,name,completed_at FROM material_progress WHERE emp_id={ph} ORDER BY completed_at DESC",
            (emp_id,)
        ).fetchall()
        record_rows = conn.execute(
            f"SELECT * FROM exam_records WHERE emp_id={ph} ORDER BY created_at DESC",
            (emp_id,)
        ).fetchall()
        assessment_rows = conn.execute(
            f"SELECT * FROM pgy_assessments WHERE emp_id={ph} ORDER BY created_at DESC",
            (emp_id,)
        ).fetchall()
    finally:
        conn.close()

    records = [_record_to_dict(r) for r in record_rows]
    assessments = [_assessment_row_to_dict(r) for r in assessment_rows]
    completed_material_ids = {str(dict(r).get('material_id', '')) for r in progress_rows if dict(r).get('material_id')}

    # 以最近一筆真實紀錄補顯示名稱；核心身分仍以 empId 判定。
    display_name = requested_name
    if not display_name:
        for row in list(progress_rows) + list(record_rows) + list(assessment_rows):
            candidate = str(dict(row).get('name', '') or '').strip()
            if candidate:
                display_name = candidate[:100]
                break

    materials = [m for m in list_uploaded_materials(False) if m.get('active', True)]
    quizzes = [q for q in list_quiz_categories(None, None, False) if q.get('active', True)]
    courses = list_courses(None, None, False)
    active_material_ids = {str(m.get('id', '')) for m in materials if m.get('id')}
    material_done = len(active_material_ids & completed_material_ids)

    # 一份已發布考卷只要有完成且達該卷及格分數的紀錄，即視為已通過。
    passed_quiz_ids = set()
    pending_review_count = 0
    for rec in records:
        if rec.get('reviewStatus') == 'pending':
            pending_review_count += 1
            continue
        qid = str(rec.get('quizCategoryId', '') or '')
        if not qid:
            continue
        try:
            if float(rec.get('score', 0) or 0) >= float(rec.get('passingScore', 80) or 80):
                passed_quiz_ids.add(qid)
        except (TypeError, ValueError):
            pass
    active_quiz_ids = {str(q.get('id', '')) for q in quizzes if q.get('id')}
    quiz_done = len(active_quiz_ids & passed_quiz_ids)

    total_required = len(active_material_ids) + len(active_quiz_ids)
    total_done = material_done + quiz_done
    progress_percent = round(total_done / total_required * 100) if total_required else 0

    # 進行中課程使用課程日期欄位；未設定日期的課程視為目前可學習。
    today = datetime.date.today().isoformat()
    active_courses = []
    for c in courses:
        start = str(c.get('startDate', '') or '')[:10]
        end = str(c.get('endDate', '') or '')[:10]
        if (not start or start <= today) and (not end or end >= today):
            active_courses.append(c)

    pending_exams = []
    for q in quizzes:
        qid = str(q.get('id', '') or '')
        if not qid or qid in passed_quiz_ids:
            continue
        pending_exams.append({
            'id': qid,
            'title': str(q.get('title', '') or '未命名考核'),
            'area': str(q.get('area', 'internal') or 'internal'),
            'group': str(q.get('group', DEFAULT_GROUP) or DEFAULT_GROUP),
            'courseId': str(q.get('courseId', '') or ''),
            'passingScore': int(q.get('passingScore', 80) or 80),
            'publishedAt': str(q.get('publishedAt', '') or q.get('dateAdded', '') or ''),
        })
    pending_exams.sort(key=lambda x: x.get('publishedAt', ''), reverse=True)

    latest_record = records[0] if records else None
    latest_assessment = assessments[0] if assessments else None
    return jsonify({
        'empId': emp_id,
        'name': display_name,
        'activeCourses': len(active_courses),
        'materialsTotal': len(active_material_ids),
        'materialsCompleted': material_done,
        'materialsPending': max(0, len(active_material_ids) - material_done),
        'examsTotal': len(active_quiz_ids),
        'examsPassed': quiz_done,
        'examsPending': max(0, len(active_quiz_ids) - quiz_done),
        'pendingExams': pending_exams[:5],
        'essayReviewsPending': pending_review_count,
        'teacherAssessmentsCompleted': len(assessments),
        'progressPercent': progress_percent,
        'latestExam': latest_record,
        'latestAssessment': latest_assessment,
    })


@app.patch("/api/records/<record_id>/review")
def api_review_record(record_id):
    denied=require_admin()
    if denied: return denied
    data=request.get_json(silent=True) or {}
    scores=data.get('essayScores',{}) if isinstance(data.get('essayScores',{}), dict) else {}
    reviewer=str(data.get('reviewerName','')).strip()[:100]
    if not reviewer:
        return jsonify({'error':'問答題批改必須填寫批改者姓名'}),400
    comment=str(data.get('reviewComment','')).strip()[:2000]
    conn,kind=_db_conn(); ph='%s' if kind=='postgres' else '?'
    try:
        row=conn.execute(f"SELECT * FROM exam_records WHERE id={ph}",(record_id,)).fetchone()
        if not row: return jsonify({'error':'找不到考試紀錄'}),404
        rec=_record_to_dict(row); answers=rec.get('answersDetail',[])
        reviewed_at=datetime.datetime.now(datetime.timezone.utc).isoformat()
        points=0.0; total=len(answers)
        if total==0: return jsonify({'error':'此紀錄沒有題目明細'}),400
        for idx,a in enumerate(answers):
            if a.get('questionType')=='essay':
                if str(idx) not in scores and idx not in scores:
                    return jsonify({'error':f'第 {idx+1} 題問答題尚未逐題給分'}),400
                raw=scores.get(str(idx), scores.get(idx))
                if raw in (None, ''):
                    return jsonify({'error':f'第 {idx+1} 題問答題尚未逐題給分'}),400
                try: grade=max(0,min(100,float(raw)))
                except (TypeError,ValueError): return jsonify({'error':f'第 {idx+1} 題問答題分數格式錯誤'}),400
                a['reviewScore']=grade
                a['reviewComment']=str((data.get('essayComments') or {}).get(str(idx),''))[:1000]
                a['reviewerName']=reviewer
                a['reviewedAt']=reviewed_at if 'reviewed_at' in locals() else datetime.datetime.now(datetime.timezone.utc).isoformat()
                points += grade/100.0
            else:
                points += 1.0 if a.get('isCorrect') is True else 0.0
        final_score=round(points/total*100)
        passing_score=max(1,min(100,int(rec.get('passingScore',80) or 80)))
        status='合格' if final_score>=passing_score else '未達標'
        payload=json.dumps(answers,ensure_ascii=False)
        if kind=='postgres': conn.execute("UPDATE exam_records SET score=%s,status=%s,answers_detail=%s,review_status='completed',reviewed_at=%s,reviewer_name=%s,review_comment=%s WHERE id=%s",(final_score,status,payload,reviewed_at,reviewer,comment,record_id))
        else: conn.execute("UPDATE exam_records SET score=?,status=?,answers_detail=?,review_status='completed',reviewed_at=?,reviewer_name=?,review_comment=? WHERE id=?",(final_score,status,payload,reviewed_at,reviewer,comment,record_id))
        return jsonify({'ok':True,'score':final_score,'status':status})
    finally: conn.close()

@app.post("/api/records")
@login_required()
def api_create_record():
    data = request.get_json(silent=True) or {}
    user = _current_user()
    data["name"] = user["name"]
    data["empId"] = user["empId"]
    required = ["id", "name", "empId", "role", "quizTitle", "score", "status"]
    missing = [k for k in required if data.get(k) in (None, "")]
    if missing:
        return jsonify({"error": f"缺少欄位：{', '.join(missing)}"}), 400

    try:
        score = int(data.get("score", 0))
        correct_count = int(data.get("correctCount", 0))
        wrong_count = int(data.get("wrongCount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "分數或題數格式錯誤"}), 400
    score = max(0, min(100, score))
    record_id = str(data["id"])[:100]
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    answers = data.get("answersDetail", [])
    group_key = normalize_group(str(data.get("groupKey", DEFAULT_GROUP)))
    training_area = normalize_area(str(data.get("trainingArea", DEFAULT_TRAINING_AREA)))
    course_id = str(data.get("courseId", "")).strip()[:100]
    quiz_category_id = str(data.get("quizCategoryId", "")).strip()[:100]
    current_publication = get_quiz_category(quiz_category_id) if quiz_category_id else None
    publication_id = str((current_publication or {}).get("publicationId", "") or "")[:100]
    publication_hash = str((current_publication or {}).get("publicationHash", "") or "")[:64]
    try:
        passing_score = max(1, min(100, int(data.get("passingScore", 80) or 80)))
    except (TypeError, ValueError):
        passing_score = 80
    has_essay = any(isinstance(a, dict) and a.get("questionType") == "essay" for a in answers)
    review_status = "pending" if has_essay else "completed"
    if has_essay:
        # 問答題尚未人工批改前不得以自動分數直接判定不合格。
        data["status"] = "待人工批改"

    conn, kind = _db_conn()
    try:
        if kind == "postgres":
            conn.execute("""
                INSERT INTO exam_records
                (id, created_at, name, emp_id, role, evaluator_name, evaluator_title, quiz_title, score, status, correct_count, wrong_count, answers_detail, group_key, training_area, course_id, review_status, quiz_category_id, passing_score, publication_id, publication_hash)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO NOTHING
            """, (record_id, created_at, str(data["name"])[:100], str(data["empId"])[:100],
                  str(data["role"])[:100], str(data.get("evaluatorName", ""))[:100],
                  str(data.get("evaluatorTitle", ""))[:100], str(data["quizTitle"])[:255], score,
                  str(data["status"])[:30], correct_count, wrong_count, json.dumps(answers, ensure_ascii=False),
                  group_key, training_area, course_id, review_status, quiz_category_id, passing_score, publication_id, publication_hash))
        else:
            conn.execute("""
                INSERT OR IGNORE INTO exam_records
                (id, created_at, name, emp_id, role, evaluator_name, evaluator_title, quiz_title, score, status, correct_count, wrong_count, answers_detail, group_key, training_area, course_id, review_status, quiz_category_id, passing_score, publication_id, publication_hash)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (record_id, created_at, str(data["name"])[:100], str(data["empId"])[:100],
                  str(data["role"])[:100], str(data.get("evaluatorName", ""))[:100],
                  str(data.get("evaluatorTitle", ""))[:100], str(data["quizTitle"])[:255], score,
                  str(data["status"])[:30], correct_count, wrong_count, json.dumps(answers, ensure_ascii=False),
                  group_key, training_area, course_id, review_status, quiz_category_id, passing_score, publication_id, publication_hash))
        return jsonify({"ok": True, "id": record_id})
    finally:
        conn.close()


@app.get("/api/records")
def api_list_records():
    denied = require_admin()
    if denied:
        return denied
    conn, _ = _db_conn()
    try:
        rows = conn.execute("SELECT * FROM exam_records ORDER BY created_at DESC").fetchall()
        return jsonify([_record_to_dict(r) for r in rows])
    finally:
        conn.close()


@app.delete("/api/records")
def api_clear_records():
    denied = require_admin()
    if denied:
        return denied
    conn, _ = _db_conn()
    try:
        conn.execute("DELETE FROM exam_records")
        return jsonify({"ok": True})
    finally:
        conn.close()



# ---------------------------------------------------------------------------
# V6.0.0：第三階段 PGY 評量中心（依正式評核代碼分類）
# ---------------------------------------------------------------------------
PGY_ASSESSMENT_TYPES = {
    "dops": "DOPS 直接觀察操作技能評量",
    "mini_cex": "MINI-CEX 臨床能力評估",
    "cbd": "CBD 案例討論",
    "checklist": "CHECKLIST 技能查核表",
    "qc": "QC 品管案例",
    "feedback360": "360 度評量",
    "report": "REPORT 學習報告",
    "qi": "QI 品質改善專案",
    "reflection": "REFLECTION 反思紀錄",
    "attendance": "ATTENDANCE 課程完成",
    # 舊代碼保留讀取與既有紀錄相容性，不再顯示於新版建立介面。
    "core6": "六大核心能力檢核表（舊版）",
    "adhoc": "Ad-hoc 即時評量表（舊版）",
    "epa": "EPA 可信賴專業活動即時評估（舊版）",
    "learning": "PGY 學習評量表（舊版）",
}
TSLM_EPA_REFERENCE_URL = "https://www.labmed.org.tw/upfiles/file/20240119/20240119172950815081.pdf"

# V5.6.1：教師評核必須完成每一項評分。前後端各自檢查，避免繞過瀏覽器直接送入不完整紀錄。
PGY_ASSESSMENT_ITEMS = {
    "dops": ["操作前準備與身分確認", "技術步驟與熟練度", "安全與感染管制", "檢體／設備品質管理", "溝通與專業態度", "整體操作能力"],
    "mini_cex": ["臨床任務與準備", "專業知識與判斷", "溝通與說明", "病人安全與專業態度", "整體臨床能力"],
    "cbd": ["案例摘要與問題辨識", "檢驗數據判讀", "鑑別與臨床連結", "處置或追蹤建議", "討論與反思"],
    "checklist": ["操作前準備", "病人／檢體識別", "SOP 步驟執行", "品質與安全確認", "操作後處理與紀錄"],
    "qc": ["品管資料檢視", "管制規則判斷", "異常原因分析", "矯正措施", "後續監測與紀錄"],
    "feedback360": ["團隊合作", "跨專業溝通", "尊重與同理", "責任感與可靠度", "專業態度"],
    "report": ["主題與問題定義", "資料與文獻運用", "分析與論證", "結論與應用", "書面／口頭表達"],
    "qi": ["問題辨識", "根本原因分析", "改善方案設計", "執行與團隊協作", "成效衡量與維持"],
    "reflection": ["事件描述", "倫理與全人觀點", "自我覺察", "學習重點", "後續行動"],
    "attendance": ["課前準備", "出席與參與", "課程任務完成", "重點理解", "學習應用"],
    "core6": ["病人／檢驗照護", "醫學與檢驗專業知識", "從工作中學習及成長", "人際與溝通技巧", "專業素養", "制度下之臨床工作"],
    "adhoc": ["任務準備", "任務執行", "結果確認／後處置"],
    "epa": ["OPA / 任務一", "OPA / 任務二", "OPA / 任務三"],
    "learning": ["學習態度與主動性", "專業知識與技能", "工作品質與病人安全", "團隊合作與溝通", "時間管理與責任感", "反思與持續改善"],
}


def init_pgy_assessment_db():
    conn, kind = _db_conn()
    try:
        if kind == "postgres":
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pgy_assessments (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, assessment_type TEXT NOT NULL,
                    group_key TEXT NOT NULL DEFAULT 'grpBio', name TEXT NOT NULL, emp_id TEXT NOT NULL,
                    evaluator_name TEXT NOT NULL DEFAULT '', evaluator_title TEXT NOT NULL DEFAULT '',
                    assessment_date TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '',
                    details JSONB NOT NULL DEFAULT '{}'::jsonb, comments TEXT NOT NULL DEFAULT '',
                    overall_score REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'completed'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pgy_assessment_templates (
                    template_type TEXT PRIMARY KEY, filename TEXT NOT NULL, uploaded_at TEXT NOT NULL,
                    storage_backend TEXT NOT NULL DEFAULT 'local', storage_key TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT ''
                )
            """)
        else:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pgy_assessments (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, assessment_type TEXT NOT NULL,
                    group_key TEXT NOT NULL DEFAULT 'grpBio', name TEXT NOT NULL, emp_id TEXT NOT NULL,
                    evaluator_name TEXT NOT NULL DEFAULT '', evaluator_title TEXT NOT NULL DEFAULT '',
                    assessment_date TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '',
                    details TEXT NOT NULL DEFAULT '{}', comments TEXT NOT NULL DEFAULT '',
                    overall_score REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'completed'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pgy_assessment_templates (
                    template_type TEXT PRIMARY KEY, filename TEXT NOT NULL, uploaded_at TEXT NOT NULL,
                    storage_backend TEXT NOT NULL DEFAULT 'local', storage_key TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT ''
                )
            """)
    finally:
        conn.close()


def _assessment_row_to_dict(row):
    r=dict(row)
    raw=r.pop('details','{}') or '{}'
    if isinstance(raw,str):
        try: raw=json.loads(raw)
        except Exception: raw={}
    r['details']=raw if isinstance(raw,dict) else {}
    r['assessmentType']=r.pop('assessment_type','')
    r['group']=normalize_group(r.pop('group_key',DEFAULT_GROUP))
    r['empId']=r.pop('emp_id','')
    r['evaluatorName']=r.pop('evaluator_name','')
    r['evaluatorTitle']=r.pop('evaluator_title','')
    r['assessmentDate']=r.pop('assessment_date','')
    r['overallScore']=float(r.pop('overall_score',0) or 0)
    r['createdAt']=r.pop('created_at','')
    return r


def _assessment_template_to_dict(row):
    r=dict(row)
    return {
        'templateType':r.get('template_type',''), 'label':PGY_ASSESSMENT_TYPES.get(r.get('template_type',''), 'EPA 公版參考' if r.get('template_type')=='epa_reference' else r.get('template_type','')),
        'filename':r.get('filename',''), 'uploadedAt':r.get('uploaded_at',''), 'storageBackend':r.get('storage_backend','local'),
        'sourceUrl':r.get('source_url',''), 'exists':True
    }


def _save_pgy_template_row(template_type, filename, backend, key, source_url=''):
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn,kind=_db_conn()
    try:
        if kind=='postgres':
            conn.execute("""INSERT INTO pgy_assessment_templates(template_type,filename,uploaded_at,storage_backend,storage_key,source_url)
                VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(template_type) DO UPDATE SET filename=EXCLUDED.filename,uploaded_at=EXCLUDED.uploaded_at,storage_backend=EXCLUDED.storage_backend,storage_key=EXCLUDED.storage_key,source_url=EXCLUDED.source_url""",
                (template_type,filename,now,backend,key,source_url))
        else:
            conn.execute("""INSERT INTO pgy_assessment_templates(template_type,filename,uploaded_at,storage_backend,storage_key,source_url)
                VALUES(?,?,?,?,?,?) ON CONFLICT(template_type) DO UPDATE SET filename=excluded.filename,uploaded_at=excluded.uploaded_at,storage_backend=excluded.storage_backend,storage_key=excluded.storage_key,source_url=excluded.source_url""",
                (template_type,filename,now,backend,key,source_url))
    finally: conn.close()


def _get_pgy_template(template_type):
    conn,kind=_db_conn(); ph='%s' if kind=='postgres' else '?'
    try:
        return conn.execute(f"SELECT * FROM pgy_assessment_templates WHERE template_type={ph}",(template_type,)).fetchone()
    finally: conn.close()


def _delete_pgy_template_storage(row):
    """Best-effort removal of a superseded PGY assessment template file."""
    if not row:
        return
    try:
        backend=(row['storage_backend'] or 'local').lower()
        key=row['storage_key'] or ''
        if not key:
            return
        if backend=='mega' and mega_is_configured():
            mega_destroy(key)
        elif backend=='gdrive' and gdrive_is_configured():
            gdrive_delete_file(key)
        elif backend=='oci' and oci_is_configured():
            oci_client().delete_object(Bucket=OCI_BUCKET_NAME, Key=key)
        elif backend=='r2' and r2_is_configured():
            r2_client().delete_object(Bucket=R2_BUCKET_NAME, Key=key)
        elif backend=='local':
            Path(key).unlink(missing_ok=True)
    except Exception:
        # New template has already been stored; cleanup failure must not make
        # the administrator lose the successful replacement operation.
        pass


def _store_pgy_template(local_path: Path, template_type: str, filename: str):
    backend=active_material_backend()
    def do_store(b):
        if b=='mega':
            _mega_free_guard(local_path.stat().st_size)
            folder=_mega_remote_join(_mega_root_id(),'pgy-assessment-templates')
            _mega_ensure_dir(folder)
            return _mega_upload_file(local_path,folder,f'{template_type}-{uuid.uuid4().hex[:8]}{local_path.suffix.lower()}')
        if b=='gdrive':
            parent=gdrive_find_file_in_folder(GDRIVE_FOLDER_ID,'pgy-assessment-templates') or gdrive_create_folder('pgy-assessment-templates',GDRIVE_FOLDER_ID)
            return gdrive_upload_file(local_path,f'{template_type}-{uuid.uuid4().hex[:8]}{local_path.suffix.lower()}',parent)
        if b=='oci':
            key=f'pgy_assessment_templates/{template_type}/{uuid.uuid4().hex}{local_path.suffix.lower()}'; oci_put_file(local_path,key,mimetypes.guess_type(filename)[0]); return key
        if b=='r2':
            key=f'pgy_assessment_templates/{template_type}/{uuid.uuid4().hex}{local_path.suffix.lower()}'; r2_put_file(local_path,key,mimetypes.guess_type(filename)[0]); return key
        dest=PGY_ASSESSMENT_TEMPLATES_DIR/f'{template_type}-{uuid.uuid4().hex[:8]}{local_path.suffix.lower()}'; shutil.copy2(local_path,dest); return str(dest)
    try:
        return backend,do_store(backend)
    except Exception as exc:
        fb=_fallback_backend_ready() if _is_storage_full_error(exc) else ''
        if fb: return fb,do_store(fb)
        raise


def _send_pgy_template(row, inline=True):
    backend=(row['storage_backend'] or 'local').lower(); key=row['storage_key']; filename=row['filename']
    if backend=='mega': return _mega_send_file(key,filename,inline=inline)
    if backend=='gdrive': return gdrive_proxy_file(key,filename,inline=inline)
    if backend=='oci': return redirect(oci_presigned_get(key,download_name=filename,inline=inline),code=302)
    if backend=='r2': return redirect(r2_presigned_get(key,download_name=filename,inline=inline),code=302)
    p=Path(key); 
    if not p.exists(): abort(404)
    return send_file(p,as_attachment=not inline,download_name=filename)


init_pgy_assessment_db()

@app.get('/api/pgy-assessment-templates')
@login_required()
def api_pgy_assessment_templates():
    conn,_=_db_conn()
    try:
        rows=conn.execute('SELECT * FROM pgy_assessment_templates ORDER BY template_type').fetchall()
        return jsonify([_assessment_template_to_dict(r) for r in rows])
    finally: conn.close()

@app.post('/api/pgy-assessment-templates/<template_type>')
def api_upload_pgy_assessment_template(template_type):
    denied=require_admin()
    if denied:return denied
    if template_type not in PGY_ASSESSMENT_TYPES:return jsonify({'error':'不支援的評量範本類型'}),400
    f=request.files.get('file')
    if not f or not f.filename:return jsonify({'error':'請選擇檔案'}),400
    ext=Path(f.filename).suffix.lower()
    if ext not in {'.docx','.pdf'}:return jsonify({'error':'評量範本僅接受 .docx 或 .pdf'}),400
    tmp=TMP_DIR/f'pgy-template-{template_type}-{uuid.uuid4().hex}{ext}'
    f.save(tmp)
    try:
        validation=_validate_template_file(tmp,ext,MAX_PGY_TEMPLATE_MB)
        old_row=_get_pgy_template(template_type)
        backend,key=_store_pgy_template(tmp,template_type,f.filename)
        _save_pgy_template_row(template_type,f.filename,backend,key)
        if old_row and (old_row['storage_key'] or '') != key:
            _delete_pgy_template_storage(old_row)
        return jsonify({'ok':True,'templateType':template_type,'storageBackend':backend,'validation':validation})
    except ValueError as e:
        return jsonify({'error':f'範本檢查失敗：{e}'}),400
    except Exception as e:
        app.logger.exception('PGY template upload failed')
        return jsonify({'error':f'評量範本上傳失敗：{e}'}),500
    finally:
        try: tmp.unlink(missing_ok=True)
        except Exception: pass

@app.post('/api/pgy-assessment-templates/import-tslm-epa')
def api_import_tslm_epa_template():
    denied=require_admin()
    if denied:return denied
    tmp=TMP_DIR/f'tslm-epa-{uuid.uuid4().hex}.pdf'
    try:
        r=requests.get(TSLM_EPA_REFERENCE_URL,timeout=45,headers={'User-Agent':'SMH-Teaching-Portal/1.0'})
        r.raise_for_status(); tmp.write_bytes(r.content)
        validation=_validate_template_file(tmp,'.pdf',MAX_PGY_TEMPLATE_MB)
        old_row=_get_pgy_template('epa_reference')
        backend,key=_store_pgy_template(tmp,'epa_reference','台灣醫事檢驗學會_醫事檢驗職類_EPAs_第一版.pdf')
        _save_pgy_template_row('epa_reference','台灣醫事檢驗學會_醫事檢驗職類_EPAs_第一版.pdf',backend,key,TSLM_EPA_REFERENCE_URL)
        if old_row and (old_row['storage_key'] or '') != key:
            _delete_pgy_template_storage(old_row)
        return jsonify({'ok':True,'storageBackend':backend,'sourceUrl':TSLM_EPA_REFERENCE_URL,'validation':validation})
    except Exception as e:
        return jsonify({'error':f'匯入學會 EPA 公版失敗：{e}'}),502
    finally:
        try: tmp.unlink(missing_ok=True)
        except Exception: pass

@app.get('/api/pgy-assessment-templates/<template_type>/download')
@login_required()
def api_download_pgy_assessment_template(template_type):
    row=_get_pgy_template(template_type)
    if not row:return jsonify({'error':'尚未設定此評量範本'}),404
    return _send_pgy_template(row,inline=True)

@app.delete('/api/pgy-assessment-templates/<template_type>')
def api_delete_pgy_assessment_template(template_type):
    denied=require_admin()
    if denied:return denied
    row=_get_pgy_template(template_type)
    if not row:return jsonify({'ok':True})
    backend=(row['storage_backend'] or 'local').lower(); key=row['storage_key']
    try:
        if backend=='mega' and key: _mega_run(['mega-rm','-f',key],check=False,timeout=60)
        elif backend=='gdrive' and key and gdrive_is_configured(): gdrive_delete_file(key)
        elif backend=='r2' and key and r2_client(): r2_client().delete_object(Bucket=R2_BUCKET_NAME,Key=key)
        elif backend=='local' and key: Path(key).unlink(missing_ok=True)
    except Exception: pass
    conn,kind=_db_conn(); ph='%s' if kind=='postgres' else '?'
    try: conn.execute(f'DELETE FROM pgy_assessment_templates WHERE template_type={ph}',(template_type,))
    finally: conn.close()
    return jsonify({'ok':True})

@app.post('/api/pgy-assessments')
def api_create_pgy_assessment():
    user, denied = require_roles('clinical_teacher')
    if denied: return denied
    data=request.get_json(silent=True) or {}
    typ=str(data.get('assessmentType','')).strip()
    if typ not in PGY_ASSESSMENT_TYPES:return jsonify({'error':'評量類型不正確'}),400
    name=str(data.get('name','')).strip()[:100]; emp=str(data.get('empId','')).strip()[:100]
    # 評估者身分必須來自登入帳號，不接受前端自由冒用姓名或職稱。
    evaluator=str(user.get('name','')).strip()[:100]
    if not name or not emp or not evaluator:return jsonify({'error':'請填寫受評者姓名、工號與評估者'}),400
    group=normalize_group(data.get('group',DEFAULT_GROUP)); details=data.get('details') or {}
    if normalize_role(user.get('role')) == 'clinical_teacher' and group != normalize_group(user.get('preferredGroup')):
        return jsonify({'error':'權限不足：臨床教師只能評核自己負責組別的學員。'}),403
    if not isinstance(details, dict):
        return jsonify({'error':'評核明細格式錯誤'}),400
    ratings=details.get('ratings') or []
    expected=PGY_ASSESSMENT_ITEMS.get(typ,[])
    if not isinstance(ratings,list) or len(ratings) != len(expected):
        return jsonify({'error':f'教師評核必須完成全部 {len(expected)} 項評分'}),400
    normalized_ratings=[]
    for idx,item_name in enumerate(expected):
        row=ratings[idx] if idx < len(ratings) and isinstance(ratings[idx],dict) else {}
        try: rating=int(row.get('rating',0) or 0)
        except Exception: rating=0
        if rating not in {1,2,3,4,5}:
            return jsonify({'error':f'第 {idx+1} 項「{item_name}」尚未完成 1–5 分評核'}),400
        normalized_ratings.append({'item':item_name,'rating':rating,'note':str(row.get('note',''))[:1000]})
    details={'ratings':normalized_ratings}
    rec_id=uuid.uuid4().hex; now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    date=str(data.get('assessmentDate','')).strip()[:30] or now[:10]
    title=str(data.get('title',PGY_ASSESSMENT_TYPES[typ])).strip()[:255]
    comments=str(data.get('comments','')).strip()[:4000]
    score=sum(x['rating'] for x in details['ratings'])/len(details['ratings']) if details.get('ratings') else 0
    conn,kind=_db_conn()
    try:
        evaluator_title='臨床教師'
        vals=(rec_id,now,typ,group,name,emp,evaluator,evaluator_title,date,title,json.dumps(details,ensure_ascii=False),comments,score,'completed')
        if kind=='postgres': conn.execute('INSERT INTO pgy_assessments(id,created_at,assessment_type,group_key,name,emp_id,evaluator_name,evaluator_title,assessment_date,title,details,comments,overall_score,status) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)',vals)
        else: conn.execute('INSERT INTO pgy_assessments(id,created_at,assessment_type,group_key,name,emp_id,evaluator_name,evaluator_title,assessment_date,title,details,comments,overall_score,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',vals)
    finally: conn.close()
    return jsonify({'ok':True,'id':rec_id})

@app.get('/api/pgy-assessments')
def api_list_pgy_assessments():
    emp=str(request.args.get('emp_id','')).strip()
    admin=request.headers.get('X-Admin-Key','')==ADMIN_KEY and bool(ADMIN_KEY)
    user=_current_user()
    if not admin and not user:
        return jsonify({'error':'請先登入後查看評量紀錄','loginRequired':True}),401
    if not admin and normalize_role(user.get('role')) == 'student':
        emp=user['empId']
    elif not admin and normalize_role(user.get('role')) in {'clinical_teacher', 'group_leader'}:
        requested_group=normalize_group(request.args.get('group', user.get('preferredGroup')))
        if requested_group != normalize_group(user.get('preferredGroup')):
            return jsonify({'error':'權限不足：臨床教師只能查看自己負責組別的評量。'}),403
    conn,kind=_db_conn(); ph='%s' if kind=='postgres' else '?'
    try:
        if not admin and user and normalize_role(user.get('role')) in {'clinical_teacher', 'group_leader'}:
            rows=conn.execute(f'SELECT * FROM pgy_assessments WHERE group_key={ph} ORDER BY created_at DESC',(normalize_group(user.get('preferredGroup')),)).fetchall()
        elif emp: rows=conn.execute(f'SELECT * FROM pgy_assessments WHERE emp_id={ph} ORDER BY created_at DESC',(emp,)).fetchall()
        else: rows=conn.execute('SELECT * FROM pgy_assessments ORDER BY created_at DESC').fetchall()
        return jsonify([_assessment_row_to_dict(r) for r in rows])
    finally: conn.close()

@app.get("/health")
def health():
    db_ok = False
    db_kind = "unknown"
    try:
        conn, db_kind = _db_conn()
        try:
            conn.execute("SELECT 1").fetchone()
            db_ok = True
        finally:
            conn.close()
    except Exception:
        db_ok = False
    return jsonify({"ok": bool(db_ok), "service": "biochemical-training-exam", "database": db_kind, "databaseOk": bool(db_ok)}), (200 if db_ok else 503)


@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")

@app.get("/internal")
def internal_area():
    return send_from_directory(STATIC_DIR, "area-internal.html")

@app.get("/pgy")
def pgy_area():
    return send_from_directory(STATIC_DIR, "area-pgy.html")

@app.get("/login")
def login_page():
    if _current_user():
        target = str(request.args.get("next", "/") or "/")
        if not target.startswith("/") or target.startswith("//"): target = "/"
        return redirect(target)
    return send_from_directory(STATIC_DIR, "login.html")

@app.get("/system")
def training_system():
    # 管理者可先以 ADMIN_KEY 進入後台建立第一批帳號；一般教材區必須登入。
    if request.args.get("admin") != "1" and not _current_user():
        target = request.full_path if request.query_string else request.path
        return redirect("/login?next=" + quote(target, safe=""))
    return send_from_directory(STATIC_DIR, "system.html")


if __name__ == "__main__":
    # debug=False：正式上線請關閉 debug；如需開發除錯可暫時改 True
    app.run(host="0.0.0.0", port=5000, debug=False)
