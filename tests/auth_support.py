"""Execute the live app.py auth adapters against a disposable database only."""
import datetime
import re
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import schema_migrations

from flask import Flask, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from teacher_app.auth import bp as auth_bp
from teacher_app.auth import account_routes, accounts as auth_accounts, routes as auth_routes, service as auth_service
from teacher_app.common.auth import CANONICAL_ROLES, LEGACY_ROLE_ALIASES, ROLE_PERMISSIONS, normalize_role


class AuthFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / 'accounts.db')
        self.base = types.ModuleType('_teacher_auth_test_' + str(id(self)))
        sys.modules[self.base.__name__] = self.base
        self.addCleanup(sys.modules.pop, self.base.__name__, None)
        self.app = Flask(self.base.__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='isolated-auth-test')
        self.base.__dict__.update(
            app=self.app, _db_conn=self.connect, sys=sys, re=re,
            datetime=datetime, jsonify=jsonify, request=request, session=session,
            auth_accounts=auth_accounts, auth_routes=auth_routes, auth_service=auth_service,
            schema_migrations=schema_migrations,
            check_password_hash=check_password_hash, generate_password_hash=generate_password_hash,
            CANONICAL_ROLES=CANONICAL_ROLES, LEGACY_ROLE_ALIASES=LEGACY_ROLE_ALIASES,
            ROLE_PERMISSIONS=ROLE_PERMISSIONS, normalize_role=normalize_role,
            DEFAULT_TRAINING_AREA='internal', DEFAULT_GROUP='grpBio',
            normalize_area=lambda x: x if x in {'internal', 'pgy'} else 'internal',
            normalize_group=lambda x: x if x in {'grpBio', 'grpHema'} else 'grpBio',
            require_admin=lambda: None,
        )
        common_db_patch = patch("teacher_app.common.db.get_connection", side_effect=self.connect)
        common_db_patch.start()
        self.addCleanup(common_db_patch.stop)
        self.base.init_user_accounts_db = lambda: schema_migrations.ensure_user_accounts_base(self.base)
        self.base._normalize_username = auth_service.normalize_username
        self.base._user_public = lambda row: auth_service.public_user(self.base, row)
        self.base._current_user = lambda: auth_service.current_user(
            self.base,
            session,
            include_roles=True,
        )
        self.base.require_roles = lambda *roles: auth_routes.require_roles(
            self.base._current_user(),
            *roles,
        )
        self.base.init_user_accounts_db()
        conn, kind = self.connect()
        try:
            schema_migrations._additive_rbac_pgy_signing_66(conn, kind)
        finally:
            conn.close()
        self.password = 'valid-password'
        self.sql('INSERT INTO user_accounts '
                 '(username,password_hash,display_name,emp_id,role,preferred_area,preferred_group,active,session_version,created_at,updated_at,last_login_at) '
                 'VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                 ('teacher1', generate_password_hash(self.password, method='pbkdf2:sha256:1000'),
                  'Teacher One', 'E001', 'teacher', 'pgy', 'grpHema', 1, 1, 'created', 'updated', ''))
        self.app.config['AUTH_BASE'] = self.base
        self.app.register_blueprint(auth_bp)
        account_routes.register_multi_role_66(self.base)
        self.client = self.app.test_client()

    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, 'sqlite'

    def sql(self, query, params=()):
        conn, _ = self.connect()
        try:
            return conn.execute(query, params).fetchall()
        finally:
            conn.close()

    def login(self, **data):
        return self.client.post('/api/auth/login', json={'username': 'teacher1', 'password': self.password, **data})
