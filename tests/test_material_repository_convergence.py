import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class MaterialRepositoryConvergenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = ROOT.joinpath("app.py").read_text(encoding="utf-8")
        cls.repo = ROOT.joinpath("teacher_app/materials/repository.py").read_text(encoding="utf-8")
        cls.db = ROOT.joinpath("teacher_app/common/db.py").read_text(encoding="utf-8")
        cls.materials = ROOT.joinpath("teacher_app/materials/service.py").read_text(encoding="utf-8")
        cls.courses = ROOT.joinpath("teacher_app/courses/service.py").read_text(encoding="utf-8")
        cls.assessments = ROOT.joinpath("teacher_app/assessments/service.py").read_text(encoding="utf-8")
        cls.external = ROOT.joinpath("external_media_68.py").read_text(encoding="utf-8")

    def test_material_read_sql_is_owned_by_repository(self):
        self.assertIn("SELECT * FROM materials", self.repo)
        self.assertNotRegex(self.app, re.compile(r"SELECT\s+\*\s+FROM\s+materials", re.I))

    def test_legacy_material_read_functions_are_thin_delegates(self):
        for name, target in (
            ("material_row_to_dict", "material_repository.material_row_to_dict"),
            ("list_uploaded_materials", "material_repository.list_uploaded_materials"),
            ("get_material", "material_repository.get_material"),
        ):
            start = self.app.index(f"def {name}(")
            next_def = self.app.find("\ndef ", start + 5)
            end = next_def if next_def >= 0 else len(self.app)
            source = self.app[start:end]
            self.assertIn(target, source)
            self.assertNotIn("SELECT ", source)
            self.assertNotIn("UPDATE ", source)
            self.assertNotIn("INSERT ", source)
            self.assertNotIn("DELETE ", source)

    def test_repository_uses_only_shared_read_connection_scope(self):
        self.assertIn("from teacher_app.common import db as common_db", self.repo)
        self.assertIn("with common_db.read_connection()", self.repo)
        self.assertNotIn("psycopg.connect", self.repo)
        self.assertNotIn("sqlite3.connect", self.repo)
        self.assertIn("def read_connection()", self.db)
        self.assertIn("conn, kind = get_connection()", self.db)
        self.assertIn("conn.close()", self.db)

    def test_canonical_services_do_not_bounce_material_reads_through_legacy_host(self):
        self.assertIn("repository.list_uploaded_materials(base", self.materials)
        self.assertIn("repository.get_material(base", self.materials)
        self.assertNotIn("base.list_uploaded_materials(", self.materials)
        self.assertNotIn("base.get_material(", self.materials)
        self.assertIn("materials_repository.list_uploaded_materials(base", self.courses)
        self.assertIn("materials_repository.list_uploaded_materials(base", self.assessments)

    def test_material_inserts_use_repository_transaction_boundary(self):
        self.assertIn("def insert_material(", self.repo)
        self.assertIn("with common_db.transaction()", self.repo)
        self.assertNotIn("INSERT INTO materials", self.app)
        self.assertIn("material_repository.insert_material(entry, ignore_conflict=True)", self.app)
        self.assertIn("material_repository.insert_material(entry)", self.app)
    def test_storage_pointer_updates_are_transactional_repository_writes(self):
        self.assertIn("def update_material_storage(", self.repo)
        self.assertIn("UPDATE materials SET storage_backend=", self.repo)
        self.assertNotIn("UPDATE materials SET storage_backend=", self.app)
        self.assertIn("material_repository.update_material_storage(", self.app)
    def test_material_metadata_update_and_delete_are_repository_writes(self):
        self.assertIn("def update_material_metadata(", self.repo)
        self.assertIn("def delete_material_record(", self.repo)
        self.assertNotIn("UPDATE materials SET title=", self.materials)
        self.assertNotIn("DELETE FROM materials", self.materials)
        self.assertIn("repository.update_material_metadata(", self.materials)
        self.assertIn("repository.delete_material_record(", self.materials)
    def test_course_and_assessment_material_relations_use_repository(self):
        for forbidden in (
            "UPDATE materials",
            "SELECT id FROM materials",
        ):
            self.assertNotIn(forbidden, self.courses)
        self.assertNotIn("UPDATE materials", self.assessments)
        self.assertIn("materials_repository.clear_course_assignment(", self.courses)
        self.assertIn("materials_repository.material_ids_for_course(", self.courses)
        self.assertIn("materials_repository.replace_category_assignments(", self.assessments)
        self.assertIn("materials_repository.clear_category_assignment(", self.assessments)
        self.assertIn("with common_db.transaction()", self.courses)
        self.assertIn("with common_db.transaction()", self.assessments)
    def test_runtime_material_dml_exists_only_in_repository(self):
        material_dml = re.compile(
            r"(SELECT\s+.*FROM\s+materials|INSERT\s+.*INTO\s+materials|"
            r"UPDATE\s+materials|DELETE\s+FROM\s+materials)",
            re.I,
        )
        for source in (self.app, self.materials, self.courses, self.assessments, self.external):
            self.assertIsNone(material_dml.search(source))
        self.assertIsNotNone(material_dml.search(self.repo))
        self.assertIn("material_repository.insert_material_on_connection(", self.external)
        self.assertIn("with common_db.transaction()", self.external)
    def test_repository_has_no_provider_credentials_or_storage_clients(self):
        for forbidden in (
            "R2_SECRET_ACCESS_KEY",
            "OCI_SECRET_ACCESS_KEY",
            "MEGA_PASSWORD",
            "GDRIVE_CLIENT_SECRET",
            "boto3",
            "googleapiclient",
        ):
            self.assertNotIn(forbidden, self.repo)


if __name__ == "__main__":
    unittest.main()
