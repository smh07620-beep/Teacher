import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from teacher_app.common.errors import ApiError
from teacher_app.courses import repository, schema, service
from teacher_app.learning import assignment_service
from teacher_app.maintenance.course_lifecycle_migration import course_lifecycle_113


ROOT = Path(__file__).parents[1]


class F2CourseLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=str(Path(self.tmp.name)/"f2-course.sqlite")

        def connect():
            conn=sqlite3.connect(self.db)
            conn.row_factory=sqlite3.Row
            conn.isolation_level=None
            return conn,"sqlite"

        self.connect=connect
        conn,kind=connect()
        schema.init_schema(conn,kind)
        conn.close()
        self.patch=patch("teacher_app.common.db.get_connection",side_effect=connect)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_migration_backfills_legacy_status(self):
        conn,kind=self.connect()
        conn.execute("INSERT INTO courses(id,title,date_added,active,lifecycle_status) VALUES('a','A','',1,'')")
        conn.execute("INSERT INTO courses(id,title,date_added,active,lifecycle_status) VALUES('b','B','',0,'')")
        course_lifecycle_113(conn,kind)
        rows={row["id"]:row["lifecycle_status"] for row in conn.execute("SELECT id,lifecycle_status FROM courses")}
        conn.close()
        self.assertEqual(rows,{"a":"published","b":"draft"})

    def test_new_service_course_is_hidden_draft(self):
        course=service.create_course(None,{"area":"internal","group":"grpBio","title":"Draft"})
        self.assertEqual(course["lifecycleStatus"],"draft")
        self.assertFalse(course["active"])
        self.assertEqual(repository.list_courses("internal","grpBio",False),[])
        self.assertEqual(len(repository.list_courses("internal","grpBio",True)),1)

    def test_readiness_requires_material_and_published_exam(self):
        repository.create_course(
            course_id="c1",area="internal",group="grpBio",title="C",
            description="",date_added="",active=False,lifecycle_status="draft"
        )
        with patch.object(service.materials_repository,"list_uploaded_materials",return_value=[]), \
             patch.object(service.assessments_repository,"list_categories",return_value=[]):
            first=service.publication_readiness("c1")
        self.assertFalse(first["ready"])
        self.assertEqual(first["blockers"][0]["code"],"COURSE_MATERIAL_REQUIRED")

        with patch.object(service.materials_repository,"list_uploaded_materials",return_value=[{"id":"m1","courseId":"c1","active":True}]), \
             patch.object(service.assessments_repository,"list_categories",return_value=[{"id":"e1","courseId":"c1","active":False}]):
            second=service.publication_readiness("c1")
        self.assertFalse(second["ready"])
        self.assertIn("COURSE_EXAM_UNPUBLISHED",[item["code"] for item in second["blockers"]])

    def test_assignment_rejects_draft_course(self):
        actor={"username":"admin","role":"education_admin","roles":["education_admin"]}
        draft={"id":"c1","area":"internal","group":"grpBio","active":False,"lifecycleStatus":"draft"}
        with patch.object(assignment_service.course_repository,"get_course",return_value=draft):
            with self.assertRaises(ApiError) as caught:
                assignment_service.build_assignment(actor,{"courseId":"c1","assigneeType":"group","assigneeKey":"grpBio"})
        self.assertEqual(caught.exception.code,"COURSE_NOT_PUBLISHED")

    def test_teacher_ui_exposes_explicit_lifecycle_actions(self):
        source=ROOT.joinpath("static","course-lifecycle-f2.js").read_text(encoding="utf-8")
        for marker in ("發布檢查","正式發布","結束課程","封存","重新開啟草稿"):
            self.assertIn(marker,source)
        self.assertIn("/readiness",source)
        self.assertIn("/lifecycle",source)


if __name__=="__main__":
    unittest.main()
