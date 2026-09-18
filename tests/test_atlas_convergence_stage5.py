"""Ownership guards for Stage 5 Atlas convergence."""
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class AtlasConvergenceStage5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = ROOT.joinpath("atlas_70.py").read_text(encoding="utf-8")
        cls.service = ROOT.joinpath("teacher_app", "atlas", "service.py").read_text(encoding="utf-8")
        cls.repository = ROOT.joinpath("teacher_app", "atlas", "repository.py").read_text(encoding="utf-8")
        cls.search = ROOT.joinpath("teacher_app", "atlas", "search.py").read_text(encoding="utf-8")
        cls.image_store = ROOT.joinpath("teacher_app", "atlas", "image_store.py").read_text(encoding="utf-8")
        cls.learning_repository = ROOT.joinpath("teacher_app", "learning", "repository.py").read_text(encoding="utf-8")

    def test_root_adapter_has_no_atlas_table_sql(self):
        for sql in (
            "SELECT * FROM atlas_items",
            "SELECT group_key,published FROM atlas_items",
            "INSERT INTO atlas_items",
            "UPDATE atlas_items SET",
            "DELETE FROM atlas_items",
        ):
            self.assertNotIn(sql, self.adapter)
            self.assertIn("atlas_items", self.repository)

    def test_repository_owns_projection_and_crud_boundaries(self):
        for marker in (
            "def row_to_item(",
            "def list_items(",
            "def get_item(",
            "def insert_item(",
            "def update_item(",
            "def delete_item(",
            "common_db.read_connection()",
            "common_db.transaction()",
        ):
            self.assertIn(marker, self.repository)

    def test_service_owns_scope_visibility_and_validation(self):
        for marker in (
            "def readable_groups(",
            "def can_read(",
            "def can_manage(",
            "def list_items(",
            "def create_item(",
            "def update_item(",
            "def delete_item(",
        ):
            self.assertIn(marker, self.service)
        self.assertNotIn("from flask", self.service)
        self.assertNotIn("base.", self.service)

    def test_search_aggregation_is_canonical_and_reuses_learning_index_owner(self):
        self.assertIn("def search_resources(", self.search)
        self.assertIn("material_repository.list_uploaded_materials", self.search)
        self.assertIn("learning_repository.get_material_text_rows", self.search)
        self.assertIn("atlas_repository.list_items", self.search)
        self.assertIn("def get_material_text_rows(", self.learning_repository)
        self.assertIn("material_text_index", self.learning_repository)
        self.assertNotIn("material_text_index", self.adapter)
        self.assertIn("atlas_search.search_resources", self.adapter)

    def test_local_image_storage_and_thumbnail_generation_are_canonical(self):
        for marker in (
            "def image_directory(",
            "def store_image_bytes(",
            "def requested_image(",
            "Image.open(",
            "thumb.thumbnail(",
            '"atlas_images"',
        ):
            self.assertIn(marker, self.image_store)
        self.assertIn("atlas_image_store.store_image_bytes", self.adapter)
        self.assertIn("atlas_image_store.requested_image", self.adapter)
        self.assertNotIn("Image.open(", self.adapter)
        self.assertNotIn("BytesIO", self.adapter)
        self.assertNotIn('mkdir(parents=True, exist_ok=True)', self.adapter)
        self.assertNotIn("thumb.thumbnail(", self.adapter)

    def test_remaining_transport_debt_is_docx_only(self):
        self.assertIn("send_from_directory", self.adapter)
        self.assertIn("zipfile.ZipFile", self.adapter)
        self.assertIn("preview_docx_atlas", self.adapter)
        self.assertNotIn("material_text_index", self.adapter)
        self.assertNotIn("MATERIAL_STORAGE", self.service)
        self.assertNotIn("UPLOADED_SLIDES_DIR", self.service)
        self.assertNotIn("send_from_directory", self.search)
        self.assertNotIn("zipfile", self.search)
        self.assertNotIn("zipfile", self.image_store)


if __name__ == "__main__":
    unittest.main()
