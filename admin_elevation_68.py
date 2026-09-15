"""Server-side short lived elevation.  Secrets never leave the request."""
from __future__ import annotations
import datetime as dt
import hmac
import os
from flask import jsonify, request, session
from teacher_app.common.auth import has_permission

TTL_SECONDS = 15 * 60
def now(): return dt.datetime.now(dt.timezone.utc)
def register_admin_elevation(base):
    app=base.app
    if app.extensions.get("teacher_admin_elevation_68_registered"): return app
    def clear(): session.pop("admin_elevation_marker",None)
    def elevated(user):
        if not user:return False
        conn,kind=base._db_conn();ph="%s" if kind=="postgres" else "?"
        try:row=conn.execute(f"SELECT expires_at,session_version FROM admin_elevations WHERE username={ph}",(user["username"],)).fetchone()
        finally:conn.close()
        return bool(row and str(dict(row)["expires_at"])>now().isoformat() and int(dict(row)["session_version"] or 0)==int(session.get("session_version",0) or 0))
    @app.post("/api/admin/elevation")
    def elevate():
        user=base._current_user()
        if not user: return jsonify({"error":"請先登入。","loginRequired":True}),401
        if not (has_permission(user,"user.manage") or has_permission(user,"system.manage")): return jsonify({"error":"權限不足。"}),403
        supplied=str((request.get_json(silent=True) or {}).get("password") or "")
        key=os.environ.get("ADMIN_KEY", "").strip()
        if not key or not supplied or not hmac.compare_digest(supplied,key): return jsonify({"error":"驗證失敗。"}),401
        stamp=now(); expires=stamp+dt.timedelta(seconds=TTL_SECONDS); username=user["username"]
        conn,kind=base._db_conn();ph="%s" if kind=="postgres" else "?"
        try:
            vals=(username,stamp.isoformat(),expires.isoformat(),int(session.get("session_version",0) or 0))
            if kind=="postgres": conn.execute("INSERT INTO admin_elevations(username,elevated_at,expires_at,session_version) VALUES(%s,%s,%s,%s) ON CONFLICT(username) DO UPDATE SET elevated_at=EXCLUDED.elevated_at,expires_at=EXCLUDED.expires_at,session_version=EXCLUDED.session_version",vals)
            else: conn.execute("INSERT INTO admin_elevations(username,elevated_at,expires_at,session_version) VALUES(?,?,?,?) ON CONFLICT(username) DO UPDATE SET elevated_at=excluded.elevated_at,expires_at=excluded.expires_at,session_version=excluded.session_version",vals)
        finally: conn.close()
        session["admin_elevation_marker"]=expires.isoformat()
        return jsonify({"ok":True,"expiresAt":expires.isoformat()})
    @app.get("/api/admin/elevation")
    def elevation_status():
        user=base._current_user()
        if not user:return jsonify({"elevated":False})
        ok=elevated(user)
        conn,kind=base._db_conn();ph="%s" if kind=="postgres" else "?"
        try: row=conn.execute(f"SELECT expires_at FROM admin_elevations WHERE username={ph}",(user["username"],)).fetchone()
        finally:conn.close()
        return jsonify({"elevated":ok,"expiresAt":dict(row)["expires_at"] if ok else ""})
    @app.after_request
    def elevation_logout_clear(response):
        if request.path=="/api/auth/logout": clear()
        return response
    # Legacy routes resolve this global helper at request time.  Preserve the
    # emergency header-key bootstrap path, but require a short-lived elevation
    # for every authenticated management action.
    original_require_admin=base.require_admin
    def elevated_require_admin():
        denied=original_require_admin()
        if denied:return denied
        user=base._current_user()
        if user and (has_permission(user,"user.manage") or has_permission(user,"system.manage")) and not elevated(user):
            return jsonify({"error":"需要管理權限驗證。","elevationRequired":True}),403
        return None
    base.require_admin=elevated_require_admin
    app.extensions["teacher_admin_elevation_68_registered"]=True
    return app
