"""Execute the real legacy auth adapters against a disposable database only."""
import ast
import datetime
import re
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path

from flask import Flask, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from teacher_app.auth import routes as auth_routes, service as auth_service
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
            auth_routes=auth_routes, auth_service=auth_service,
            check_password_hash=check_password_hash, generate_password_hash=generate_password_hash,
            CANONICAL_ROLES=CANONICAL_ROLES, LEGACY_ROLE_ALIASES=LEGACY_ROLE_ALIASES,
            ROLE_PERMISSIONS=ROLE_PERMISSIONS, normalize_role=normalize_role,
            DEFAULT_TRAINING_AREA='internal', DEFAULT_GROUP='grpBio',
            normalize_area=lambda x: x if x in {'internal', 'pgy'} else 'internal',
            normalize_group=lambda x: x if x in {'grpBio', 'grpHema'} else 'grpBio',
            require_admin=lambda: None,
        )
        names = {'init_user_accounts_db', '_normalize_username', '_user_public', '_current_user',
                 'require_roles', 'api_auth_me', 'api_auth_login', 'api_auth_logout', 'api_user_update'}
        names |= {'_legacy_' + n.lstrip('_') for n in names}
        tree = ast.parse(Path(__file__).parents[1].joinpath('app.py').read_text(encoding='utf-8'))
        selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        exec(compile(ast.Module(body=selected, type_ignores=[]), 'app.py', 'exec'), self.base.__dict__)
        self.base.init_user_accounts_db()
        self.password = 'valid-password'
        self.sql('INSERT INTO user_accounts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                 ('teacher1', generate_password_hash(self.password, method='pbkdf2:sha256:1000'),
                  'Teacher One', 'E001', 'teacher', 'pgy', 'grpHema', 1, 1, 'created', 'updated', ''))
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
