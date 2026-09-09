#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V5.3 Google Drive OAuth 初始化工具。

用途：
1) 使用 Google Cloud 下載的 Desktop OAuth client JSON 登入「教材專用 Google 帳號」。
2) 取得可供 Render 長期使用的 refresh token。
3) 在該帳號 My Drive 建立 app 可存取的 smh-teaching-materials 資料夾。
4) 顯示 Render Environment 需要的 4 個值。

注意：不要把輸出的 Secret / Refresh Token 提交到 GitHub。
"""
import argparse
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPE = "https://www.googleapis.com/auth/drive.file"
FOLDER_MIME = "application/vnd.google-apps.folder"


def main():
    ap = argparse.ArgumentParser(description="建立 V5.3 Google Drive OAuth 與教材資料夾")
    ap.add_argument("client_secret_json", help="Google Cloud 下載的 OAuth Desktop client JSON")
    ap.add_argument("--folder-name", default="smh-teaching-materials", help="要建立的教材根資料夾名稱")
    ap.add_argument("--output", default="", help="可選：將 Render 環境變數寫入指定文字檔（請勿提交 GitHub）")
    args = ap.parse_args()

    secret_path = Path(args.client_secret_json).expanduser().resolve()
    if not secret_path.exists():
        raise SystemExit(f"找不到檔案：{secret_path}")

    raw = json.loads(secret_path.read_text(encoding="utf-8"))
    cfg = raw.get("installed") or raw.get("web") or {}
    client_id = cfg.get("client_id", "")
    client_secret = cfg.get("client_secret", "")
    if not client_id or not client_secret:
        raise SystemExit("OAuth JSON 缺少 client_id / client_secret。請建立 Desktop app OAuth client。")

    flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), scopes=[SCOPE])
    creds = flow.run_local_server(
        host="localhost",
        port=0,
        open_browser=True,
        access_type="offline",
        prompt="consent",
        success_message="Google Drive 授權完成，可以關閉此頁並回到命令視窗。",
    )
    if not creds.refresh_token:
        raise SystemExit(
            "沒有取得 refresh token。請到 Google 帳號撤銷此 App 的存取權後重跑，或確認使用 prompt=consent。"
        )

    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    folder = service.files().create(
        body={
            "name": args.folder_name,
            "mimeType": FOLDER_MIME,
            "appProperties": {"smh_kind": "materials_root", "smh_version": "5.3"},
        },
        fields="id,name",
    ).execute()

    lines = [
        "MATERIAL_STORAGE_BACKEND=gdrive",
        f"GDRIVE_CLIENT_ID={client_id}",
        f"GDRIVE_CLIENT_SECRET={client_secret}",
        f"GDRIVE_REFRESH_TOKEN={creds.refresh_token}",
        f"GDRIVE_FOLDER_ID={folder['id']}",
        "GDRIVE_TOKEN_URI=https://oauth2.googleapis.com/token",
        "GDRIVE_CHUNK_MB=8",
    ]
    text = "\n".join(lines) + "\n"

    print("\n=== V5.3 Render Environment ===")
    print(text)
    print(f"Google Drive 教材資料夾：{folder['name']}  (ID: {folder['id']})")
    print("\n重要：上面的 CLIENT_SECRET / REFRESH_TOKEN 是密鑰，不要貼到公開 GitHub。")
    print("若 Google OAuth App 還在 Testing 狀態，refresh token 通常 7 天後會失效；正式使用前請依 README_V5_3.md 處理發布狀態。")

    if args.output:
        out = Path(args.output).expanduser().resolve()
        out.write_text(text, encoding="utf-8")
        print(f"已寫入：{out}（請勿提交 GitHub）")


if __name__ == "__main__":
    main()
