import sqlite3
import unittest
from pathlib import Path

from teacher_app.maintenance import bootstrap

ROOT = Path(__file__).resolve().parents[1]


class AlignScopeTest(unittest.TestCase):
    def test_materials_follow_their_course_scope_and_unattached_untouched(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE courses (id TEXT, group_key TEXT, training_area TEXT)")
        conn.execute("CREATE TABLE materials (id TEXT, course_id TEXT, group_key TEXT, training_area TEXT)")
        conn.execute("INSERT INTO courses VALUES ('c1','grpMicro','internal')")
        conn.executemany("INSERT INTO materials VALUES (?,?,?,?)", [
            ("m1", "c1", "grpBio", "internal"),
            ("m2", "c1", "grpMicro", "internal"),
            ("m3", "", "grpBio", "internal"),
            ("m4", "gone", "grpBio", "pgy"),
        ])
        bootstrap.align_material_scope_to_courses(conn)
        rows = dict((r[0], r[1:]) for r in conn.execute("SELECT id,group_key,training_area FROM materials"))
        self.assertEqual(rows["m1"], ("grpMicro", "internal"))
        self.assertEqual(rows["m2"], ("grpMicro", "internal"))
        self.assertEqual(rows["m3"], ("grpBio", "internal"))
        self.assertEqual(rows["m4"], ("grpBio", "pgy"))

    def test_job_commit_uses_course_scope(self):
        src = (ROOT / "teacher_app/materials/job_commit.py").read_text(encoding="utf-8")
        self.assertIn("attached_course", src)
