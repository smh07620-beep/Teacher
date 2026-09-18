"""Canonical live provider configuration and client/session construction.

This module is the production owner for storage credentials and SDK client
construction.  Higher-level material/template workflows stay in the legacy host
during the transition and call these helpers through thin compatibility wrappers.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

try:
    import boto3
    from botocore.config import Config as BotoConfig
except ImportError:
    boto3 = None
    BotoConfig = None

try:
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2.credentials import Credentials as GoogleCredentials
    from googleapiclient.discovery import build as google_build
    from googleapiclient.http import MediaFileUpload
except ImportError:
    AuthorizedSession = None
    GoogleCredentials = None
    google_build = None
    MediaFileUpload = None


GDRIVE_CLIENT_ID = os.environ.get("GDRIVE_CLIENT_ID", "").strip()
GDRIVE_CLIENT_SECRET = os.environ.get("GDRIVE_CLIENT_SECRET", "").strip()
GDRIVE_REFRESH_TOKEN = os.environ.get("GDRIVE_REFRESH_TOKEN", "").strip()
GDRIVE_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID", "").strip()
GDRIVE_TOKEN_URI = os.environ.get(
    "GDRIVE_TOKEN_URI",
    "https://oauth2.googleapis.com/token",
).strip()
GDRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
GDRIVE_CHUNK_MB = max(1, min(64, int(os.environ.get("GDRIVE_CHUNK_MB", "8"))))

R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "").strip()
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "").strip()
R2_PRESIGN_SECONDS = max(
    60,
    min(604800, int(os.environ.get("R2_PRESIGN_SECONDS", "3600"))),
)

OCI_NAMESPACE = os.environ.get("OCI_NAMESPACE", "").strip()
OCI_REGION = os.environ.get("OCI_REGION", "").strip()
OCI_ACCESS_KEY_ID = os.environ.get("OCI_ACCESS_KEY_ID", "").strip()
OCI_SECRET_ACCESS_KEY = os.environ.get("OCI_SECRET_ACCESS_KEY", "").strip()
OCI_BUCKET_NAME = os.environ.get("OCI_BUCKET_NAME", "smh-teaching-materials").strip()
OCI_PRESIGN_SECONDS = max(
    60,
    min(604800, int(os.environ.get("OCI_PRESIGN_SECONDS", "3600"))),
)
OCI_FREE_LIMIT_GB = max(
    1.0,
    min(20.0, float(os.environ.get("OCI_FREE_LIMIT_GB", "19.5"))),
)

MEGA_EMAIL = os.environ.get("MEGA_EMAIL", "").strip()
MEGA_PASSWORD = os.environ.get("MEGA_PASSWORD", "").strip()
MEGA_ROOT_FOLDER = (
    os.environ.get("MEGA_ROOT_FOLDER", "smh-teaching-materials").strip().strip("/")
    or "smh-teaching-materials"
)
MEGA_STORAGE_LIMIT_GB = max(
    1.0,
    min(100.0, float(os.environ.get("MEGA_STORAGE_LIMIT_GB", "18.0"))),
)
MEGA_SESSION_CACHE_SECONDS = max(
    60,
    min(86400, int(os.environ.get("MEGA_SESSION_CACHE_SECONDS", "1800"))),
)
_DEFAULT_MEGACMD_HOME = str(Path(tempfile.gettempdir()) / "megacmd-home")
MEGACMD_HOME = (
    os.environ.get("MEGACMD_HOME", _DEFAULT_MEGACMD_HOME).strip()
    or _DEFAULT_MEGACMD_HOME
)
MEGACMD_TIMEOUT_SECONDS = max(
    30,
    min(1800, int(os.environ.get("MEGACMD_TIMEOUT_SECONDS", "300"))),
)
MEGA_WEB_READ_TIMEOUT_SECONDS = max(
    20,
    min(150, int(os.environ.get("MEGA_WEB_READ_TIMEOUT_SECONDS", "120"))),
)
Path(MEGACMD_HOME).mkdir(parents=True, exist_ok=True)


def r2_is_configured(
    *,
    account_id: str = R2_ACCOUNT_ID,
    access_key_id: str = R2_ACCESS_KEY_ID,
    secret_access_key: str = R2_SECRET_ACCESS_KEY,
    bucket_name: str = R2_BUCKET_NAME,
) -> bool:
    return bool(
        account_id
        and access_key_id
        and secret_access_key
        and bucket_name
        and boto3 is not None
    )


def r2_client(
    *,
    account_id: str = R2_ACCOUNT_ID,
    access_key_id: str = R2_ACCESS_KEY_ID,
    secret_access_key: str = R2_SECRET_ACCESS_KEY,
    bucket_name: str = R2_BUCKET_NAME,
):
    if not r2_is_configured(
        account_id=account_id,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        bucket_name=bucket_name,
    ):
        raise RuntimeError("Cloudflare R2 尚未完成設定。")
    return boto3.client(
        service_name="s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="auto",
        config=BotoConfig(signature_version="s3v4") if BotoConfig else None,
    )


def r2_delete_object(key: str, **client_overrides) -> None:
    if not key:
        return
    bucket_name = client_overrides.get("bucket_name", R2_BUCKET_NAME)
    r2_client(**client_overrides).delete_object(Bucket=bucket_name, Key=str(key))


def oci_is_configured(
    *,
    namespace: str = OCI_NAMESPACE,
    region: str = OCI_REGION,
    access_key_id: str = OCI_ACCESS_KEY_ID,
    secret_access_key: str = OCI_SECRET_ACCESS_KEY,
    bucket_name: str = OCI_BUCKET_NAME,
) -> bool:
    return bool(
        namespace
        and region
        and access_key_id
        and secret_access_key
        and bucket_name
        and boto3 is not None
    )


def oci_client(
    *,
    namespace: str = OCI_NAMESPACE,
    region: str = OCI_REGION,
    access_key_id: str = OCI_ACCESS_KEY_ID,
    secret_access_key: str = OCI_SECRET_ACCESS_KEY,
    bucket_name: str = OCI_BUCKET_NAME,
):
    if not oci_is_configured(
        namespace=namespace,
        region=region,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        bucket_name=bucket_name,
    ):
        raise RuntimeError("Oracle Object Storage 尚未完成設定。")
    endpoint = (
        f"https://{namespace}.compat.objectstorage.{region}.oci.customer-oci.com"
    )
    return boto3.client(
        service_name="s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name=region,
        config=(
            BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"})
            if BotoConfig
            else None
        ),
    )


def oci_delete_object(key: str, **client_overrides) -> None:
    if not key:
        return
    bucket_name = client_overrides.get("bucket_name", OCI_BUCKET_NAME)
    oci_client(**client_overrides).delete_object(Bucket=bucket_name, Key=str(key))


def gdrive_is_configured(
    *,
    client_id: str = GDRIVE_CLIENT_ID,
    client_secret: str = GDRIVE_CLIENT_SECRET,
    refresh_token: str = GDRIVE_REFRESH_TOKEN,
    folder_id: str = GDRIVE_FOLDER_ID,
) -> bool:
    return bool(
        client_id
        and client_secret
        and refresh_token
        and folder_id
        and GoogleCredentials is not None
        and AuthorizedSession is not None
        and google_build is not None
        and MediaFileUpload is not None
    )


def gdrive_credentials(
    *,
    client_id: str = GDRIVE_CLIENT_ID,
    client_secret: str = GDRIVE_CLIENT_SECRET,
    refresh_token: str = GDRIVE_REFRESH_TOKEN,
    folder_id: str = GDRIVE_FOLDER_ID,
    token_uri: str = GDRIVE_TOKEN_URI,
    scope: str = GDRIVE_SCOPE,
):
    if not gdrive_is_configured(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
        folder_id=folder_id,
    ):
        raise RuntimeError("Google Drive 尚未完成 OAuth 設定。")
    return GoogleCredentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=token_uri,
        client_id=client_id,
        client_secret=client_secret,
        scopes=[scope],
    )


def gdrive_service(**credential_overrides):
    return google_build(
        "drive",
        "v3",
        credentials=gdrive_credentials(**credential_overrides),
        cache_discovery=False,
    )


def gdrive_delete_file(file_id: str, **credential_overrides) -> None:
    if file_id:
        gdrive_service(**credential_overrides).files().delete(fileId=str(file_id)).execute()


def gdrive_authorized_session(**credential_overrides):
    return AuthorizedSession(gdrive_credentials(**credential_overrides))


def gdrive_media_file_upload(
    local_path,
    *,
    mimetype: str,
    chunk_mb: int = GDRIVE_CHUNK_MB,
):
    if MediaFileUpload is None:
        raise RuntimeError("Google Drive API 套件尚未安裝。")
    return MediaFileUpload(
        str(local_path),
        mimetype=mimetype,
        chunksize=max(1, min(64, int(chunk_mb))) * 1024 * 1024,
        resumable=True,
    )


def mega_credentials_present(
    *,
    email: str = MEGA_EMAIL,
    password: str = MEGA_PASSWORD,
) -> bool:
    return bool(email or password)


def mega_is_configured(
    find_command: Callable[[str], Any],
    *,
    email: str = MEGA_EMAIL,
    password: str = MEGA_PASSWORD,
) -> bool:
    return bool(
        email
        and password
        and find_command("mega-whoami")
        and find_command("mega-put")
    )


def mega_timeout_for_deadline(deadline, default_seconds):
    if deadline is None:
        return default_seconds
    remaining = float(deadline) - time.monotonic()
    if remaining <= 0:
        raise RuntimeError("MEGA 讀取逾時，請稍後重試。")
    return max(1, min(int(default_seconds), int(max(1, remaining))))


_MEGA_AUTH_CACHE = {"ok": False, "at": 0.0}
_MEGA_LOCK = threading.RLock()


def invalidate_mega_auth_cache() -> None:
    with _MEGA_LOCK:
        _MEGA_AUTH_CACHE.update({"ok": False, "at": 0.0})


def mega_login_if_needed(
    *,
    is_configured: Callable[[], bool],
    run: Callable[..., Any],
    email: str = MEGA_EMAIL,
    password: str = MEGA_PASSWORD,
    session_cache_seconds: int = MEGA_SESSION_CACHE_SECONDS,
    force: bool = False,
    deadline=None,
) -> None:
    """Own the single process-local MEGAcmd authentication cache/session policy."""

    if not is_configured():
        raise RuntimeError(
            "MEGA 尚未完成設定。請設定 MEGA_EMAIL、MEGA_PASSWORD，並確認官方 MEGAcmd 已安裝。"
        )
    now = time.time()
    with _MEGA_LOCK:
        if (
            not force
            and _MEGA_AUTH_CACHE.get("ok")
            and now - float(_MEGA_AUTH_CACHE.get("at", 0) or 0)
            < int(session_cache_seconds)
        ):
            return
        probe = run(
            ["mega-whoami"],
            check=False,
            timeout=mega_timeout_for_deadline(deadline, 30),
        )
        if probe.returncode != 0:
            run(
                ["mega-logout"],
                check=False,
                timeout=mega_timeout_for_deadline(deadline, 30),
            )
            login = run(
                ["mega-login", email, password],
                check=False,
                timeout=mega_timeout_for_deadline(deadline, 120),
            )
            if login.returncode != 0:
                detail = (login.stderr or login.stdout or "login failed").strip()
                raise RuntimeError(f"MEGA 登入失敗：{detail[-600:]}")
        verify = run(
            ["mega-whoami"],
            check=False,
            timeout=mega_timeout_for_deadline(deadline, 30),
        )
        if verify.returncode != 0:
            raise RuntimeError("MEGA 登入後仍無法驗證帳號 session。")
        _MEGA_AUTH_CACHE.update({"ok": True, "at": now})


def mega_delete_object(
    file_id: str,
    *,
    is_configured: Callable[[], bool],
    run: Callable[..., Any],
    email: str = MEGA_EMAIL,
    password: str = MEGA_PASSWORD,
    session_cache_seconds: int = MEGA_SESSION_CACHE_SECONDS,
) -> None:
    """Strictly delete one MEGA path using the canonical auth/session owner."""

    if not file_id:
        return
    mega_login_if_needed(
        is_configured=is_configured,
        run=run,
        email=email,
        password=password,
        session_cache_seconds=session_cache_seconds,
    )
    run(["mega-rm", "-r", "-f", str(file_id)], check=True, timeout=120)
