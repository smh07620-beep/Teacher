"""Authenticated account self-service and password recovery."""
from __future__ import annotations
import datetime as dt, hashlib, os, re, secrets, smtplib
from email.message import EmailMessage
from flask import g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash
from teacher_app.auth import repository, service
from teacher_app.common import audit, db as common_db

EMAIL_RE=re.compile(r"^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$")

def _now(): return dt.datetime.now(dt.timezone.utc)
def _iso(v): return v.isoformat()
def _hash(token): return hashlib.sha256(token.encode()).hexdigest()
def _email(v):
    value=str(v or "").strip().lower()[:254]
    if value and not EMAIL_RE.match(value): raise ValueError("Email 格式不正確。")
    return value

def _send(to, subject, body):
    host=str(os.getenv("SMTP_HOST","")).strip()
    sender=str(os.getenv("SMTP_FROM","")).strip()
    if not host or not sender: return False
    msg=EmailMessage(); msg["To"]=to; msg["From"]=sender; msg["Subject"]=subject; msg.set_content(body)
    port=int(os.getenv("SMTP_PORT","587") or 587)
    user=os.getenv("SMTP_USERNAME",""); password=os.getenv("SMTP_PASSWORD","")
    with smtplib.SMTP(host,port,timeout=15) as smtp:
        if str(os.getenv("SMTP_STARTTLS","true")).lower() in {"1","true","yes","on"}: smtp.starttls()
        if user: smtp.login(user,password)
        smtp.send_message(msg)
    return True

def _actor():
    return getattr(g,"teacher_user",None) or service.current_user(session,include_roles=True)

def register_account_self_service(app):
    if app.extensions.get("teacher_account_self_service_registered"): return app

    @app.get("/api/account/profile")
    def account_profile():
        user=_actor()
        if not user: return jsonify({"error":"請先登入。","loginRequired":True}),401
        row=repository.find_user(user["username"]) or {}
        data=service.public_user(row,include_roles=True)
        data["email"]=str(row.get("email") or "")
        data["emailNotifications"]=bool(row.get("email_notifications",True))
        return jsonify({"user":data})

    @app.patch("/api/account/profile")
    def account_profile_update():
        user=_actor()
        if not user: return jsonify({"error":"請先登入。","loginRequired":True}),401
        data=request.get_json(silent=True) or {}; updates={}
        if "name" in data:
            name=str(data.get("name") or "").strip()[:100]
            if not name: return jsonify({"error":"姓名不可空白。"}),400
            updates["display_name"]=name
        if "professionalTitle" in data: updates["professional_title"]=str(data.get("professionalTitle") or "").strip()[:100]
        if "email" in data:
            try: updates["email"]=_email(data.get("email"))
            except ValueError as exc: return jsonify({"error":str(exc)}),400
        if "emailNotifications" in data:
            if type(data["emailNotifications"]) is not bool: return jsonify({"error":"通知設定格式不正確。"}),400
            updates["email_notifications"]=data["emailNotifications"]
        if not updates: return jsonify({"error":"沒有可更新的個人資料。"}),400
        updates["updated_at"]=_iso(_now())
        row=repository.update_user(user["username"],updates)
        audit.record_event(actor=user,action="account.profile.update",target_type="account",target_id=user["username"],detail={"changedFields":sorted(updates)})
        return jsonify({"ok":True,"user":service.public_user(row,include_roles=True)})

    @app.post("/api/account/change-password")
    def change_password():
        user=_actor()
        if not user: return jsonify({"error":"請先登入。","loginRequired":True}),401
        data=request.get_json(silent=True) or {}; current=str(data.get("currentPassword") or ""); new=str(data.get("newPassword") or "")
        row=repository.find_user(user["username"]) or {}
        if not check_password_hash(str(row.get("password_hash") or ""),current): return jsonify({"error":"目前密碼不正確。"}),400
        if len(new)<8: return jsonify({"error":"新密碼至少 8 碼。"}),400
        repository.update_user(user["username"],{"password_hash":generate_password_hash(new),"updated_at":_iso(_now())},invalidate_session=True)
        audit.record_event(actor=user,action="account.password.change",target_type="account",target_id=user["username"])
        session.clear()
        return jsonify({"ok":True,"loginRequired":True})

    @app.post("/api/auth/forgot-password")
    def forgot_password():
        data=request.get_json(silent=True) or {}; identity=str(data.get("identity") or "").strip().lower()
        row=repository.find_user(service.normalize_username(identity))
        if not row and "@" in identity:
            with common_db.read_connection() as (conn,kind):
                ph=common_db.placeholder(kind); found=conn.execute(f"SELECT * FROM user_accounts WHERE LOWER(email)={ph}",(identity,)).fetchone()
                row=dict(found) if found else None
        if row and row.get("active") and str(row.get("email") or ""):
            token=secrets.token_urlsafe(32); now=_now(); expires=now+dt.timedelta(minutes=30)
            with common_db.transaction() as (conn,kind):
                ph=common_db.placeholder(kind)
                conn.execute(f"INSERT INTO password_reset_tokens(token_hash,username,created_at,expires_at,used_at) VALUES ({','.join([ph]*5)})",(_hash(token),row["username"],_iso(now),_iso(expires),""))
            base=str(os.getenv("PUBLIC_BASE_URL","")).rstrip("/")
            link=f"{base}/reset-password?token={token}" if base else ""
            if link:
                try:_send(str(row["email"]),"醫學檢驗教學平台｜重設密碼",f"請在 30 分鐘內使用以下連結重設密碼：\n\n{link}\n\n若非本人操作，請忽略此信。")
                except Exception: pass
        return jsonify({"ok":True,"message":"若帳號與 Email 資料相符，系統將寄出重設密碼信件。"})

    @app.post("/api/auth/reset-password")
    def reset_password():
        data=request.get_json(silent=True) or {}; token=str(data.get("token") or ""); new=str(data.get("newPassword") or "")
        if len(new)<8 or len(token)<20: return jsonify({"error":"重設連結無效或新密碼不足 8 碼。"}),400
        now=_now()
        with common_db.transaction() as (conn,kind):
            ph=common_db.placeholder(kind)
            row=conn.execute(f"SELECT * FROM password_reset_tokens WHERE token_hash={ph}",(_hash(token),)).fetchone()
            item=dict(row) if row else None
            if not item or item.get("used_at") or dt.datetime.fromisoformat(str(item["expires_at"]).replace("Z","+00:00"))<now:
                return jsonify({"error":"重設連結已失效，請重新申請。"}),400
            conn.execute(f"UPDATE user_accounts SET password_hash={ph},session_version=session_version+1,updated_at={ph} WHERE username={ph}",(generate_password_hash(new),_iso(now),item["username"]))
            conn.execute(f"UPDATE password_reset_tokens SET used_at={ph} WHERE token_hash={ph}",(_iso(now),_hash(token)))
        return jsonify({"ok":True})

    app.extensions["teacher_account_self_service_registered"]=True
    return app

__all__=["register_account_self_service"]
