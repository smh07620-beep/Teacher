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
        cls.scope = ROOT.joinpath("teacher_app/common/scope.py").read_text(encoding="utf-8")
        cls.catalog = ROOT.joinpath("teacher_app/materials/catalog.py").read_text(encoding="utf-8")
        cls.materials = ROOT.joinpath("teacher_app/materials/service.py").read_text(encoding="utf-8")
        cls.course_repo = ROOT.joinpath("teacher_app/courses/repository.py").read_text(encoding="utf-8")
        cls.assessment_repo = ROOT.joinpath("teacher_app/assessments/repository.py").read_text(encoding="utf-8")
        cls.courses = ROOT.joinpath("teacher_app/courses/service.py").read_text(encoding="utf-8")
        cls.assessments = ROOT.joinpath("teacher_app/assessments/service.py").read_text(encoding="utf-8")
        cls.external = ROOT.joinpath("external_media_68.py").read_text(encoding="utf-8")
        cls.hardening = ROOT.joinpath("production_hardening.py").read_text(encoding="utf-8")

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
            for sql in ("SELECT ", "UPDATE ", "INSERT ", "DELETE "):
                self.assertNotIn(sql, source)

    def test_repository_uses_only_shared_read_connection_scope(self):
        self.assertIn("from teacher_app.common import db as common_db", self.repo)
        self.assertIn("with common_db.read_connection()", self.repo)
        self.assertNotIn("psycopg.connect", self.repo)
        self.assertNotIn("sqlite3.connect", self.repo)
        self.assertIn("def read_connection()", self.db)
        self.assertIn("conn, kind = get_connection()", self.db)
        self.assertIn("conn.close()", self.db)

    def test_material_repository_does_not_consult_legacy_host(self):
        self.assertNotIn(".normalize_group(", self.repo)
        self.assertNotIn(".normalize_area(", self.repo)
        self.assertNotIn("DEFAULT_GROUP", self.repo.replace("scope.DEFAULT_GROUP", ""))
        self.assertIn("scope.normalize_group", self.repo)
        self.assertIn("scope.normalize_area", self.repo)
        self.assertIn("legacy_base is accepted but never consulted", self.repo)

    def test_material_catalog_and_update_validation_use_canonical_domains(self):
        for forbidden in (
            "base.normalize_group",
            "base.normalize_area",
            "base.category_label_map",
            "base.load_meta",
            "base.get_course",
            "base.get_quiz_category",
        ):
            self.assertNotIn(forbidden, self.materials)
        self.assertIn("catalog.load_builtin_meta()", self.materials)
        self.assertIn("scope.normalize_group", self.materials)
        self.assertIn("scope.normalize_area", self.materials)
        self.assertIn("course_repository.get_course", self.materials)
        self.assertIn("assessment_repository.get_category", self.materials)
        self.assertIn("assessment_repository.category_labels", self.materials)
        self.assertIn("with common_db.read_connection()", self.course_repo)
        self.assertIn("with common_db.read_connection()", self.assessment_repo)

    def test_material_delete_is_the_only_remaining_legacy_provider_seam(self):
        delete_start = self.materials.index("def delete_material(")
        before_delete = self.materials[:delete_start]
        self.assertNotIn("base.", before_delete)
        delete_source = self.materials[delete_start:]
        self.assertIn("base.mega_destroy", delete_source)
        self.assertIn("base.gdrive_delete_material", delete_source)
        self.assertIn("base.r2_delete_prefix", delete_source)

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
        for forbidden in ("UPDATE materials", "SELECT id FROM materials"):
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
            r"(SELECT\s+.*FROM\s+materials|INSERT\s+.*INTO\s+materials|UPDATE\s+materials|DELETE\s+FROM\s+materials)",
            re.I,
        )
        for source in (self.app, self.materials, self.courses, self.assessments, self.external):
            self.assertIsNone(material_dml.search(source))
        self.assertIsNotNone(material_dml.search(self.repo))
        self.assertIn("material_repository.insert_material_on_connection(", self.external)
        self.assertIn("with common_db.transaction()", self.external)

    def test_material_and_course_hot_paths_emit_latency_metrics(self):
        self.assertIn('{"api_list_slides", "api_courses"}', self.hardening)
        self.assertIn("time.perf_counter()", self.hardening)
        self.assertIn("teacher_stage2 endpoint=%s status=%s duration_ms=%.1f", self.hardening)

    def test_repository_has_no_provider_credentials_or_storage_clients(self):
        for forbidden in (
            "R2_SECRET_ACCESS_KEY", "OCI_SECRET_ACCESS_KEY", "MEGA_PASSWORD",
            "GDRIVE_CLIENT_SECRET", "boto3", "googleapiclient",
        ):
            self.assertNotIn(forbidden, self.repo)


if __name__ == "__main__":
    unittest.main()
