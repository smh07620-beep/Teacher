"""New materials are shared with every group by default; old rows stay as they were."""
import sqlite3
import unittest
from pathlib import Path

from teacher_app.materials import repository

ROOT = Path(__file__).parents[1]


def make_conn(with_audience=True):
    conn = sqlite3.connect(":memory:")
    cols = ",".join(f"{name} TEXT" for name in repository.MATERIAL_DB_COLUMNS if name != "id")
    conn.execute(f"CREATE TABLE materials(id TEXT PRIMARY KEY,{cols})")
    if with_audience:
        conn.execute("ALTER TABLE materials ADD COLUMN audience_scope TEXT NOT NULL DEFAULT 'group_only'")
        conn.execute("ALTER TABLE materials ADD COLUMN audience_groups TEXT NOT NULL DEFAULT '[]'")
    return conn


def entry(mid, **extra):
    base = {name: "" for name in repository.MATERIAL_DB_COLUMNS}
    base.update({"id": mid, "active": True, "group_key": "grpBio", "training_area": "internal"})
    base.update(extra)
    return base


def scope_of(conn, mid):
    return conn.execute("SELECT audience_scope FROM materials WHERE id=?", (mid,)).fetchone()[0]


class NewMaterialDefaultAudienceTests(unittest.TestCase):
    def test_new_material_is_shared_with_every_group(self):
        conn = make_conn()
        repository.insert_material_on_connection(conn, "sqlite", entry("m1"))
        self.assertEqual(scope_of(conn, "m1"), "all_staff")

    def test_an_explicit_choice_is_respected(self):
        conn = make_conn()
        repository.insert_material_on_connection(conn, "sqlite", entry("m1", audienceScope="group_only"))
        repository.insert_material_on_connection(conn, "sqlite", entry("m2", audience_scope="multi_group"))
        self.assertEqual(scope_of(conn, "m1"), "group_only")
        self.assertEqual(scope_of(conn, "m2"), "multi_group")

    def test_garbage_values_fall_back_to_the_default(self):
        conn = make_conn()
        repository.insert_material_on_connection(conn, "sqlite", entry("m1", audienceScope="everyone!!"))
        self.assertEqual(scope_of(conn, "m1"), "all_staff")

    def test_existing_rows_keep_their_restriction(self):
        conn = make_conn()
        conn.execute("INSERT INTO materials(id) VALUES('old')")
        repository.insert_material_on_connection(conn, "sqlite", entry("new"))
        self.assertEqual(scope_of(conn, "old"), "group_only")
        self.assertEqual(scope_of(conn, "new"), "all_staff")

    def test_re_inserting_an_existing_material_never_widens_it(self):
        conn = make_conn()
        repository.insert_material_on_connection(conn, "sqlite", entry("m1", audienceScope="group_only"))
        repository.insert_material_on_connection(conn, "sqlite", entry("m1"), ignore_conflict=True)
        self.assertEqual(scope_of(conn, "m1"), "group_only")

    def test_databases_without_the_audience_column_still_accept_inserts(self):
        conn = make_conn(with_audience=False)
        repository.insert_material_on_connection(conn, "sqlite", entry("m1"))
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0], 1)


class TeacherHintTests(unittest.TestCase):
    def test_restricted_materials_tell_teachers_how_to_open_them_up(self):
        source = ROOT.joinpath("static", "content-audience-1014.js").read_text(encoding="utf-8")
        self.assertIn("data-audience-hint", source.replace("dataset.audienceHint", "data-audience-hint"))
        self.assertIn("其他組別看不到；要開放請按「設定範圍」", source)
        self.assertIn("=== 'group_only'", source)


if __name__ == "__main__":
    unittest.main()
