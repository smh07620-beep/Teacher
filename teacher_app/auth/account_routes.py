"""Canonical account-administration HTTP compatibility routes.

Account validation and persistence live in ``teacher_app.auth.accounts``.
Schema ownership lives in ``schema_migrations.py`` and is applied before this
adapter during production composition.
"""
from __future__ import annotations

from flask import g, jsonify, request

from teacher_app.auth import accounts
from teacher_app.common.auth import has_permission


def _require_user_manage(owner=None):
    app = getattr(owner, "app", owner)
    if app is not None and not getattr(app, "extensions", {}).get("teacher_rbac_681_registered"):
        compat_guard = getattr(owner, "require_admin", None)
        if callable(compat_guard):
            return compat_guard()
    user = getattr(g, "teacher_user", None)
    if user is None:
        resolver = getattr(owner, "_current_user", None)
        if callable(resolver):
            user = resolver()
    if not user:
        return jsonify({"error": "請先登入。", "loginRequired": True}), 401
    if not has_permission(user, "user.manage"):
        return jsonify({"error": "權限不足。"}), 403
    return None


def register_multi_role_66(owner):
    app = getattr(owner, "app", owner)
    if app.extensions.get("teacher_multi_role_66_registered"):
        return app

    def users_admin():
        denied = _require_user_manage(owner)
        if denied:
            return denied
        return jsonify(accounts.list_accounts())

    def user_create():
        denied = _require_user_manage(owner)
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        try:
            user = accounts.create_account(data)
            return jsonify({"ok": True, "user": user})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({
                "error": "帳號或工號已存在。",
                "detail": str(exc)[:180],
            }), 409

    def user_update(username):
        denied = _require_user_manage(owner)
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        try:
            user = accounts.update_account(username, data)
            return jsonify({"ok": True, "user": user})
        except accounts.AccountNotFound as exc:
            return jsonify({"error": str(exc)}), 404
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({
                "error": "更新失敗，請確認工號未被其他帳號使用。",
                "detail": str(exc)[:180],
            }), 409

    bound = {"list": False, "create": False, "update": False}
    for rule in list(app.url_map.iter_rules()):
        if rule.rule == "/api/users" and "GET" in rule.methods:
            app.view_functions[rule.endpoint] = users_admin
            bound["list"] = True
        elif rule.rule == "/api/users" and "POST" in rule.methods:
            app.view_functions[rule.endpoint] = user_create
            bound["create"] = True
        elif rule.rule == "/api/users/<username>" and "PATCH" in rule.methods:
            app.view_functions[rule.endpoint] = user_update
            bound["update"] = True

    if not bound["list"]:
        app.add_url_rule("/api/users", endpoint="api_users", view_func=users_admin, methods=["GET"])
    if not bound["create"]:
        app.add_url_rule("/api/users", endpoint="api_user_create", view_func=user_create, methods=["POST"])
    if not bound["update"]:
        app.add_url_rule(
            "/api/users/<username>",
            endpoint="api_user_update",
            view_func=user_update,
            methods=["PATCH"],
        )

    app.extensions["teacher_multi_role_66_registered"] = True
    return app


__all__ = ["register_multi_role_66"]
