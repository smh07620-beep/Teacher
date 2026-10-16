"""Canonical static page-shell routes."""
from __future__ import annotations

from flask import redirect, request, send_from_directory


def register_page_routes(app, *, static_dir, current_user):
    if app.extensions.get("teacher_page_routes_registered"):
        return app

    def index():
        return send_from_directory(static_dir, "index.html")

    def internal_area():
        return send_from_directory(static_dir, "area-internal.html")

    def pgy_area():
        return send_from_directory(static_dir, "area-pgy.html")

    def login_page():
        if current_user():
            target = str(request.args.get("next", "/") or "/")
            if not target.startswith("/") or target.startswith("//"):
                target = "/"
            return redirect(target)
        return send_from_directory(static_dir, "login.html")

    def account_page():
        if not current_user():
            return redirect("/login?next=%2Faccount")
        return send_from_directory(static_dir, "account.html")

    def reset_password_page():
        return send_from_directory(static_dir, "reset-password.html")

    def training_system():
        # RBAC registration replaces this endpoint with the canonical protected
        # workspace guard later in composition.  Keeping the route here gives
        # that guard a base-free page-shell owner.
        return send_from_directory(static_dir, "system.html")

    def _workspace_entry(next_path, workspace, persona, extra=None):
        from teacher_app.common.workspace_routes import workspace_url

        if not current_user():
            return redirect(f"/login?next={next_path.replace('/', '%2F')}")
        return redirect(workspace_url(workspace, persona=persona, params=extra or {}))

    def teach_entry():
        """Short, bookmarkable address for the teacher workspace (RBAC still decides what loads)."""
        return _workspace_entry("/teach", "course-materials", "teacher")

    def admin_entry():
        """Short, bookmarkable address for the system area, opening on the health overview."""
        return _workspace_entry("/admin", "system", "system")

    for rule, endpoint, view in (
        ("/", "index", index),
        ("/internal", "internal_area", internal_area),
        ("/pgy", "pgy_area", pgy_area),
        ("/login", "login_page", login_page),
        ("/account", "account_page", account_page),
        ("/reset-password", "reset_password_page", reset_password_page),
        ("/system", "training_system", training_system),
        ("/teach", "teach_entry", teach_entry),
        ("/admin", "admin_entry", admin_entry),
    ):
        app.add_url_rule(rule, endpoint=endpoint, view_func=view, methods=["GET"])

    app.extensions["teacher_page_routes_registered"] = True
    return app


__all__ = ["register_page_routes"]
