"""Opt-in short cache for the full material list (Supabase egress, 2026-10-12)."""
import contextlib
import unittest
from pathlib import Path
from unittest import mock

from teacher_app.materials import repository

ROOT = Path(__file__).resolve().parents[1]


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class _Conn:
    def __init__(self, owner):
        self.owner = owner

    def execute(self, sql, params=()):
        self.owner.queries.append(sql)
        return _Cursor(self.owner.rows)


class _FakeDb:
    def __init__(self):
        self.rows = [{"id": "m1", "title": "A", "active": True}]
        self.queries = []

    @contextlib.contextmanager
    def read_connection(self):
        yield _Conn(self), "postgres"


class MaterialListCacheTests(unittest.TestCase):
    def setUp(self):
        repository.invalidate_materials_cache()
        self.addCleanup(repository.invalidate_materials_cache)
        self.db = _FakeDb()
        for patcher in (
            mock.patch.object(repository.common_db, "read_connection", self.db.read_connection),
            mock.patch.object(repository.common_db, "database_url", lambda: "postgresql://example.invalid/db"),
            mock.patch.object(repository, "material_row_to_dict", lambda row: dict(row)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_disabled_by_default_every_call_reads_the_database(self):
        with mock.patch.dict("os.environ", {"MATERIAL_LIST_CACHE_SECONDS": ""}):
            repository.list_uploaded_materials()
            repository.list_uploaded_materials()
        self.assertEqual(len(self.db.queries), 2)

    def test_enabled_serves_repeat_reads_from_memory(self):
        with mock.patch.dict("os.environ", {"MATERIAL_LIST_CACHE_SECONDS": "10"}):
            first = repository.list_uploaded_materials()
            second = repository.list_uploaded_materials()
            repository.list_uploaded_materials(include_inactive=True)
        self.assertEqual(first, second)
        # one read per include_inactive variant
        self.assertEqual(len(self.db.queries), 2)

    def test_callers_cannot_corrupt_the_cached_copy(self):
        with mock.patch.dict("os.environ", {"MATERIAL_LIST_CACHE_SECONDS": "10"}):
            repository.list_uploaded_materials()[0]["title"] = "mutated"
            self.assertEqual(repository.list_uploaded_materials()[0]["title"], "A")

    def test_ttl_expiry_rereads(self):
        clock = [1000.0]
        with mock.patch.dict("os.environ", {"MATERIAL_LIST_CACHE_SECONDS": "10"}), mock.patch.object(
            repository.time, "monotonic", lambda: clock[0]
        ):
            repository.list_uploaded_materials()
            clock[0] += 9
            repository.list_uploaded_materials()
            self.assertEqual(len(self.db.queries), 1)
            clock[0] += 2
            repository.list_uploaded_materials()
        self.assertEqual(len(self.db.queries), 2)

    def test_every_writer_clears_the_cache(self):
        with mock.patch.dict("os.environ", {"MATERIAL_LIST_CACHE_SECONDS": "10"}):
            repository.list_uploaded_materials()
            self.assertEqual(len(self.db.queries), 1)

            @repository._clears_list_cache
            def writer():
                return "done"

            self.assertEqual(writer(), "done")
            repository.list_uploaded_materials()
            self.assertEqual(len(self.db.queries), 2)

            @repository._clears_list_cache
            def failing_writer():
                raise RuntimeError("db write failed")

            with self.assertRaises(RuntimeError):
                failing_writer()
            repository.list_uploaded_materials()
            self.assertEqual(len(self.db.queries), 3)

    def test_all_material_writers_are_decorated(self):
        source = (ROOT / "teacher_app" / "materials" / "repository.py").read_text(encoding="utf-8")
        for name in (
            "ensure_material_version_baseline_on_connection",
            "insert_material_on_connection",
            "insert_material",
            "update_material_storage",
            "update_material_metadata",
            "publish_material_version",
            "delete_material_record",
            "clear_course_assignment",
            "replace_category_assignments",
            "clear_category_assignment",
            "replace_material_content_and_publish",
            "restore_material_version",
        ):
            self.assertIn(f"@_clears_list_cache\ndef {name}(", source, name)

    def test_render_blueprint_enables_the_cache(self):
        render = (ROOT / "render.yaml").read_text(encoding="utf-8")
        self.assertIn("key: MATERIAL_LIST_CACHE_SECONDS", render)


if __name__ == "__main__":
    unittest.main()


class FreshReadTests(MaterialListCacheTests):
    def test_fresh_read_sees_a_row_a_worker_just_inserted(self):
        with mock.patch.dict("os.environ", {"MATERIAL_LIST_CACHE_SECONDS": "10"}):
            repository.list_uploaded_materials(include_inactive=True)
            self.db.rows = self.db.rows + [{"id": "upload-new", "title": "B", "active": False}]
            stale = repository.list_uploaded_materials(include_inactive=True)
            fresh = repository.list_uploaded_materials(include_inactive=True, fresh=True)
        self.assertEqual([r["id"] for r in stale], ["m1"])
        self.assertEqual([r["id"] for r in fresh], ["m1", "upload-new"])
