import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, g

import release_contract
from teacher_app.assessments import question_bank_routes
from teacher_app.assessments import routes as assessment_routes
from teacher_app.assessments import schema as assessment_schema
from teacher_app.auth import account_routes
from teacher_app.common import audit
from teacher_app.common.audit_routes import register_general_audit_routes
from teacher_app.maintenance import migrations


ROOT = Path(__file__).resolve().parents[1]


class GeneralAudit77Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "audit.sqlite"

        def connect():
            conn = sqlite3.connect(self.path)
            conn.row_factory = sqlite3.Row
            conn.isolation_level = None
            return conn, "sqlite"

        self.connect = connect
        conn, kind = self.connect()
        try:
            migrations._baseline(conn, kind)
            migrations._additive_rbac_pgy_signing_66(conn, kind)
            migrations._user_profile_titles_69(conn, kind)
            migrations._pgy_learner_audience_71(conn, kind)
            migrations._general_audit_events_77(conn, kind)
        finally:
            conn.close()
        self.db_patch = patch("teacher_app.common.db.get_connection", side_effect=self.connect)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)

    def test_migration_and_release_contract_create_append_only_general_store(self):
        self.assertIn("0077-general-audit-events", release_contract.REQUIRED_MIGRATIONS)
        self.assertLess(
            release_contract.REQUIRED_MIGRATIONS.index("0077-general-audit-events"),
            release_contract.REQUIRED_MIGRATIONS.index("0078-item-analytics-metrics"),
        )
        self.assertIn(
            "0077-general-audit-events",
            [version for version, _fn in migrations.MIGRATIONS],
        )
        conn, _ = self.connect()
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(audit_events)").fetchall()}
            indexes = {row[1] for row in conn.execute("PRAGMA index_list(audit_events)").fetchall()}
        finally:
            conn.close()
        self.assertTrue({
            "id", "created_at", "actor_username", "actor_role", "action",
            "target_type", "target_id", "group_key", "scope_json",
            "before_json", "after_json", "detail_json", "request_id",
        }.issubset(columns))
        self.assertIn("idx_audit_events_target", indexes)
        self.assertIn("idx_audit_events_actor", indexes)

    def test_store_binds_actor_and_redacts_secret_like_metadata(self):
        created = audit.record_event(
            actor={"username": "root", "role": "system_admin"},
            action="account.update",
            target_type="account",
            target_id="teacher1",
            group="grpBio",
            before={"role": "student", "passwordHash": "must-not-log"},
            after={"role": "clinical_teacher", "active": True},
            detail={"token": "must-not-log", "changedFields": ["role"]},
        )
        self.assertEqual(created["actorUsername"], "root")
        self.assertEqual(created["actorRole"], "system_admin")
        self.assertEqual(created["group"], "grpBio")
        rows = audit.list_events(target_type="account", target_id="teacher1")
        self.assertEqual(len(rows), 1)
        self.assertNotIn("passwordHash", rows[0]["before"])
        self.assertNotIn("token", rows[0]["detail"])
        self.assertEqual(rows[0]["detail"]["changedFields"], ["role"])

    def test_audit_api_requires_audit_read_and_exposes_get_only(self):
        audit.record_event(
            actor={"username": "root", "role": "system_admin"},
            action="backup.export",
            target_type="backup",
            target_id="b1",
        )
        app = Flask(__name__)
        app.config.update(TESTING=True, SECRET_KEY="audit-test")
        actor = {"username": "audit1", "role": "auditor"}

        @app.before_request
        def bind_actor():
            g.teacher_user = actor

        register_general_audit_routes(app)
        client = app.test_client()
        response = client.get("/api/audit/events")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["items"][0]["action"], "backup.export")
        rule = next(rule for rule in app.url_map.iter_rules() if rule.rule == "/api/audit/events")
        self.assertEqual(set(rule.methods) - {"HEAD", "OPTIONS"}, {"GET"})

        actor.clear()
        actor.update({"username": "learner", "role": "student"})
        denied = client.get("/api/audit/events")
        self.assertEqual(denied.status_code, 403)

    def test_account_and_role_mutations_emit_safe_events(self):
        app = Flask(__name__ + "-accounts")
        app.config.update(TESTING=True, SECRET_KEY="audit-account-test")

        @app.before_request
        def bind_actor():
            g.teacher_user = {"username": "root", "role": "system_admin"}

        account_routes.register_multi_role_66(app)
        client = app.test_client()
        created = client.post(
            "/api/users",
            json={
                "username": "teacher1",
                "password": "secret-pass",
                "name": "Teacher One",
                "empId": "T001",
                "role": "clinical_teacher",
                "preferredGroup": "grpBio",
            },
        )
        self.assertEqual(created.status_code, 200, created.get_data(as_text=True))
        updated = client.patch(
            "/api/users/teacher1",
            json={"role": "group_leader", "password": "new-secret"},
        )
        self.assertEqual(updated.status_code, 200, updated.get_data(as_text=True))
        rows = audit.list_events(target_type="account", target_id="teacher1")
        actions = [row["action"] for row in rows]
        self.assertIn("account.create", actions)
        self.assertIn("account.update", actions)
        self.assertIn("role.update", actions)
        update = next(row for row in rows if row["action"] == "account.update")
        self.assertNotIn("password", update["detail"].get("changedFields", []))
        self.assertTrue(update["detail"]["credentialChanged"])
        self.assertNotIn("password_hash", update["after"])

    def test_assessment_review_publish_delete_emit_general_audit(self):
        conn, kind = self.connect()
        try:
            assessment_schema.init_schema(conn, kind)
            conn.execute("CREATE TABLE materials (id TEXT PRIMARY KEY, category TEXT NOT NULL DEFAULT '')")
            conn.execute(
                "INSERT INTO quiz_categories(id,group_key,training_area,title,date_added,active,review_status) "
                "VALUES(?,?,?,?,?,?,?)",
                ("cat-audit", "grpBio", "internal", "Audit Exam", "now", 0, "draft"),
            )
            conn.execute(
                "INSERT INTO quiz_questions(id,quiz_category_id,tag,question,question_type,options,correct,answer_config,explanation,sort_order,active) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                ("q-audit", "cat-audit", "general", "Question", "choice", '["A","B"]', 0, "{}", "why", 0, 1),
            )
        finally:
            conn.close()

        app = Flask(__name__ + "-assessment")
        app.config.update(TESTING=True, SECRET_KEY="audit-assessment-test")

        @app.before_request
        def bind_actor():
            g.teacher_user = {
                "username": "root",
                "name": "System Admin",
                "role": "system_admin",
                "preferredGroup": "grpBio",
            }

        assessment_routes.register_assessment_routes(app)
        client = app.test_client()
        reviewed = client.post("/api/quiz-categories/cat-audit/review")
        self.assertEqual(reviewed.status_code, 200, reviewed.get_data(as_text=True))
        published = client.post("/api/quiz-categories/cat-audit/publish")
        self.assertEqual(published.status_code, 200, published.get_data(as_text=True))
        deleted = client.delete("/api/quiz-categories/cat-audit")
        self.assertEqual(deleted.status_code, 200, deleted.get_data(as_text=True))
        rows = audit.list_events(target_type="assessment", target_id="cat-audit")
        actions = [row["action"] for row in rows]
        self.assertIn("assessment.review", actions)
        self.assertIn("assessment.publish", actions)
        self.assertIn("assessment.delete", actions)
        self.assertTrue(all(row["actorUsername"] == "root" for row in rows))
        self.assertTrue(all(row["group"] == "grpBio" for row in rows))

    def test_question_review_publish_snapshot_and_delete_emit_general_audit(self):
        conn, kind = self.connect()
        try:
            assessment_schema.init_schema(conn, kind)
            migrations._external_interactive_media_68(conn, kind)
            conn.execute(
                "INSERT INTO quiz_categories(id,group_key,training_area,title,date_added,active,review_status) "
                "VALUES(?,?,?,?,?,?,?)",
                ("cat-bank", "grpBio", "internal", "Bank Exam", "now", 0, "draft"),
            )
            conn.execute(
                "INSERT INTO quiz_questions("
                "id,quiz_category_id,tag,question,question_type,options,correct,answer_config,explanation,"
                "sort_order,active,difficulty,status,origin,updated_at,normalized_hash"
                ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "q-bank", "cat-bank", "general", "Reviewed question", "choice", '["A","B"]', 0,
                    "{}", "why", 0, 1, "standard", "draft", "manual", "now", "hash-q-bank",
                ),
            )
        finally:
            conn.close()

        app = Flask(__name__ + "-question-bank")
        app.config.update(TESTING=True, SECRET_KEY="audit-question-bank-test")

        @app.before_request
        def bind_actor():
            g.teacher_user = {
                "username": "root",
                "name": "System Admin",
                "role": "system_admin",
                "preferredGroup": "grpBio",
            }

        question_bank_routes.register_question_bank(app, runtime_question_runtime=object())
        client = app.test_client()
        reviewed = client.post(
            "/api/question-bank/q-bank/review",
            json={"decision": "accept"},
        )
        self.assertEqual(reviewed.status_code, 200, reviewed.get_data(as_text=True))
        blueprint = client.post(
            "/api/exam-blueprints",
            json={"quizCategoryId": "cat-bank", "questionCount": 1, "quotas": {}},
        )
        self.assertEqual(blueprint.status_code, 201, blueprint.get_data(as_text=True))
        published = client.post(
            f"/api/exam-blueprints/{blueprint.get_json()['id']}/publish"
        )
        self.assertEqual(published.status_code, 201, published.get_data(as_text=True))
        deleted = client.delete("/api/question-bank/q-bank")
        self.assertEqual(deleted.status_code, 200, deleted.get_data(as_text=True))

        actions = [row["action"] for row in audit.list_events(group="grpBio")]
        self.assertIn("question.review", actions)
        self.assertIn("question.publish", actions)
        self.assertIn("question.delete", actions)

    def test_required_canonical_mutation_hooks_are_covered(self):
        sources = {
            "questions": (ROOT / "teacher_app/assessments/runtime_question_routes.py").read_text(encoding="utf-8"),
            "bank": (ROOT / "teacher_app/assessments/question_bank_routes.py").read_text(encoding="utf-8"),
            "materials": (ROOT / "teacher_app/materials/routes.py").read_text(encoding="utf-8"),
            "backup": (ROOT / "teacher_app/maintenance/backup_routes.py").read_text(encoding="utf-8"),
        }
        for marker in (
            'action="question.delete"',
            'action="question.batch_delete"',
            'action="ai.generation.submit"',
            'action="ai.candidates.import"',
        ):
            self.assertIn(marker, sources["questions"])
        self.assertIn('action="question.review"', sources["bank"])
        self.assertIn('action="question.publish"', sources["bank"])
        for marker in ('action="material.publish"', 'action="material.delete"'):
            self.assertIn(marker, sources["materials"])
        for marker in ('action="backup.export"', 'action="backup.restore"'):
            self.assertIn(marker, sources["backup"])


if __name__ == "__main__":
    unittest.main()
