import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from teacher_app.materials import derivative_repository
from teacher_app.maintenance.material_derivative_migration import material_derivative_publications_115


PPTX="application/vnd.openxmlformats-officedocument.presentationml.presentation"


class F5DerivativeLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=str(Path(self.tmp.name)/"derivatives.sqlite")

        def connect():
            conn=sqlite3.connect(self.path)
            conn.row_factory=sqlite3.Row
            conn.isolation_level=None
            return conn,"sqlite"

        self.connect=connect
        conn,kind=connect()
        conn.execute("CREATE TABLE materials(id TEXT PRIMARY KEY,current_version INTEGER NOT NULL DEFAULT 1)")
        conn.execute("INSERT INTO materials(id,current_version) VALUES('m1',4)")
        material_derivative_publications_115(conn,kind)
        conn.close()
        patcher=patch("teacher_app.common.db.get_connection",side_effect=connect)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_publication_attaches_to_current_material_version_without_bumping_it(self):
        first=derivative_repository.record_publication(
            material_id="m1",
            derivative_type="presentation",
            derivative_id="ppt-1",
            source_presentation_id="ppt-1",
            source_presentation_revision=3,
            artifact={
                "backend":"r2","key":"ai-presentations/a.pptx","sha256":"a"*64,
                "byteSize":1234,"mimeType":PPTX,
            },
            receipt_key="pptpub-1",
            provenance={"sourceMaterialVersion":4},
            published_by="teacher",
        )
        second=derivative_repository.record_publication(
            material_id="m1",
            derivative_type="presentation",
            derivative_id="ppt-1",
            source_presentation_id="ppt-1",
            source_presentation_revision=3,
            artifact={
                "backend":"r2","key":"ai-presentations/a.pptx","sha256":"a"*64,
                "byteSize":1234,"mimeType":PPTX,
            },
            receipt_key="pptpub-1",
            provenance={"sourceMaterialVersion":4},
            published_by="teacher",
        )
        self.assertEqual(first["id"],second["id"])
        self.assertEqual(first["materialVersion"],4)
        conn,_=self.connect()
        version=conn.execute("SELECT current_version FROM materials WHERE id='m1'").fetchone()[0]
        count=conn.execute("SELECT COUNT(*) FROM material_derivative_publications").fetchone()[0]
        conn.close()
        self.assertEqual(version,4)
        self.assertEqual(count,1)

    def test_video_and_presentation_can_share_same_material_version(self):
        for kind,mime,key in (
            ("presentation",PPTX,"a.pptx"),
            ("video","video/mp4","a.mp4"),
        ):
            derivative_repository.record_publication(
                material_id="m1",derivative_type=kind,derivative_id=kind+"-1",
                source_presentation_id="ppt-1",source_presentation_revision=2,
                artifact={"backend":"r2","key":key,"sha256":("b" if kind=="video" else "a")*64,"byteSize":1000,"mimeType":mime},
                receipt_key=kind+"-receipt",provenance={},published_by="teacher",
            )
        rows=derivative_repository.list_for_material_version("m1",4)
        self.assertEqual({row["type"] for row in rows},{"presentation","video"})


if __name__=="__main__":
    unittest.main()
