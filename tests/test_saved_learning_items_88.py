import contextlib
import sqlite3
import unittest
from unittest.mock import patch

import release_contract
import schema_migrations
from teacher_app.common import db as common_db
from teacher_app.common.errors import ApiError
from teacher_app.courses import repository as course_repository
from teacher_app.learning import saved_service
from teacher_app.maintenance.saved_learning_items_migration import saved_learning_items_88
from teacher_app.materials import repository as material_repository


class SavedLearningItems88Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        saved_learning_items_88(self.conn, "sqlite")
        self.course = {"id": "course-1", "title": "輸血安全", "active": True, "area": "internal", "group": "grpBB"}
        self.material = {"id": "mat-1", "title": "抗體鑑定 SOP", "active": True, "area": "internal", "group": "grpBB", "courseId": "course-1", "materialType": "sop"}
        self.user = {"username": "student.a", "role": "student", "roles": ["student"], "preferredArea": "internal", "preferredGroup": "grpBB"}

    def tearDown(self): self.conn.close()

    @contextlib.contextmanager
    def _read(self): yield self.conn, "sqlite"

    @contextlib.contextmanager
    def _tx(self):
        try:
            yield self.conn, "sqlite"
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def _patches(self):
        return (
            patch.object(common_db, "read_connection", self._read),
            patch.object(common_db, "transaction", self._tx),
            patch.object(course_repository, "get_course", side_effect=lambda item_id: self.course if item_id == "course-1" else None),
            patch.object(material_repository, "get_material", side_effect=lambda item_id: self.material if item_id == "mat-1" else None),
        )

    def test_release_contract_registers_0088_after_0087(self):
        versions = [version for version, _fn in schema_migrations.MIGRATIONS]
        self.assertEqual(versions.count("0088-saved-learning-items"), 1)
        feedback_index = release_contract.REQUIRED_MIGRATIONS.index("0087-course-feedback")
        saved_index = release_contract.REQUIRED_MIGRATIONS.index("0088-saved-learning-items")
        self.assertEqual(saved_index, feedback_index + 1)

    def test_course_and_material_are_saved_per_account(self):
        p = self._patches()
        with p[0], p[1], p[2], p[3]:
            saved_service.set_saved_item(self.user, "course", "course-1", saved=True)
            saved_service.set_saved_item(self.user, "material", "mat-1", saved=True)
            items = saved_service.list_saved_items(self.user)
        self.assertEqual({(i["itemType"], i["itemId"]) for i in items}, {("course", "course-1"), ("material", "mat-1")})

    def test_unsave_removes_marker(self):
        p = self._patches()
        with p[0], p[1], p[2], p[3]:
            saved_service.set_saved_item(self.user, "material", "mat-1", saved=True)
            saved_service.set_saved_item(self.user, "material", "mat-1", saved=False)
            self.assertEqual(saved_service.list_saved_items(self.user), [])

    def test_cross_scope_save_fails_closed_and_stale_marker_is_hidden(self):
        p = self._patches(); other = {**self.user, "preferredGroup": "grpHema"}
        with p[0], p[1], p[2], p[3]:
            with self.assertRaises(ApiError) as caught: saved_service.set_saved_item(other, "material", "mat-1", saved=True)
            self.assertEqual(caught.exception.status, 404)
            saved_service.set_saved_item(self.user, "material", "mat-1", saved=True)
            self.assertEqual(saved_service.list_saved_items(other), [])

    def test_invalid_type_and_missing_auth_are_rejected(self):
        with self.assertRaises(ApiError) as item_type: saved_service.set_saved_item(self.user, "exam", "x", saved=True)
        self.assertEqual(item_type.exception.code, "INVALID_SAVED_ITEM_TYPE")
        with self.assertRaises(ApiError) as auth: saved_service.list_saved_items(None)
        self.assertEqual(auth.exception.status, 401)


if __name__ == "__main__": unittest.main()
