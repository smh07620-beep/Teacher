"""Regression coverage for the 6.8/6.8.1 material-navigation and RBAC fixes."""
import sqlite3
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

import app as legacy_app
import pgy_app
from smart_learning_67 import auto_index_material


ROOT = Path(__file__).parents[1]


class MaterialReadAccess68Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "teacher-navigation.sqlite"
        self.db_patch = patch.object(legacy_app, "_db_conn", self.connect)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        self.canonical_db_patch = patch(
            "teacher_app.common.db.get_connection",
            side_effect=self.connect,
        )
        self.canonical_db_patch.start()
        self.addCleanup(self.canonical_db_patch.stop)
        legacy_app.init_user_accounts_db()
        legacy_app.init_exam_db()
        legacy_app.init_materials_db()
        legacy_app.init_quiz_db()
        legacy_app.init_learning_db()
        conn, _ = self.connect()
        try:
            conn.execute(
                "CREATE TABLE admin_elevations ("
                "username TEXT PRIMARY KEY, elevated_at TEXT NOT NULL, "
                "expires_at TEXT NOT NULL, session_version INTEGER NOT NULL DEFAULT 0)"
            )
            conn.execute("CREATE TABLE atlas_items (id TEXT PRIMARY KEY,category TEXT NOT NULL,group_key TEXT NOT NULL,title TEXT NOT NULL,image_url TEXT NOT NULL DEFAULT '',description TEXT NOT NULL DEFAULT '',tags TEXT NOT NULL DEFAULT '[]',differential_points TEXT NOT NULL DEFAULT '',teaching_notes TEXT NOT NULL DEFAULT '',difficulty TEXT NOT NULL DEFAULT 'general',published INTEGER NOT NULL DEFAULT 0,source TEXT NOT NULL DEFAULT 'manual',source_material_id TEXT NOT NULL DEFAULT '',source_docx TEXT NOT NULL DEFAULT '',sort_order INTEGER NOT NULL DEFAULT 0,annotation_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,created_by TEXT NOT NULL DEFAULT '',updated_by TEXT NOT NULL DEFAULT '')")
            conn.execute("CREATE TABLE material_text_index (material_id TEXT NOT NULL,page_no INTEGER NOT NULL,title TEXT NOT NULL DEFAULT '',text TEXT NOT NULL DEFAULT '',indexed_at TEXT NOT NULL DEFAULT '',PRIMARY KEY(material_id,page_no))")
            conn.execute("CREATE TABLE material_search_status (material_id TEXT PRIMARY KEY,status TEXT NOT NULL,page_count INTEGER NOT NULL DEFAULT 0,last_indexed_at TEXT NOT NULL DEFAULT '',failure_reason TEXT NOT NULL DEFAULT '',source_kind TEXT NOT NULL DEFAULT '')")
            users = (
                ("education-admin", "Education Admin", "E001", "education_admin", "grpHema"),
                ("group-leader", "Group Leader", "G001", "group_leader", "grpHema"),
                ("clinical-teacher", "Clinical Teacher", "T001", "clinical_teacher", "grpHema"),
                ("student-user", "Student", "S001", "student", "grpHema"),
                ("auditor-user", "Auditor", "A001", "auditor", "grpHema"),
            )
            for username, display_name, emp_id, role, group in users:
                conn.execute(
                    "INSERT INTO user_accounts "
                    "(username,password_hash,display_name,emp_id,role,preferred_area,preferred_group,active,session_version,created_at,updated_at,last_login_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        username, generate_password_hash("test-password"), display_name,
                        emp_id, role, "internal", group, 1, 1,
                        "2026-01-01", "2026-01-01", "",
                    ),
                )
        finally:
            conn.close()
        self.client = pgy_app.app.test_client()

    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        return conn, "sqlite"

    def login(self, username="education-admin"):
        response = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": "test-password"},
            headers={"Origin": "http://localhost"},
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

    def test_education_admin_session_can_read_slides(self):
        self.login()
        response = self.client.get("/api/slides?area=internal")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

    def test_anonymous_slides_request_is_401(self):
        response = self.client.get("/api/slides?area=internal")
        self.assertEqual(response.status_code, 401)
        self.assertTrue(response.get_json()["loginRequired"])

    def test_education_admin_can_use_cross_group_material_management_without_elevation(self):
        self.login("education-admin")
        listing = self.client.get("/api/slides/admin")
        self.assertEqual(listing.status_code, 200, listing.get_data(as_text=True))
        upload = self.client.post(
            "/api/slides/upload",
            data={"group": "grpBio", "area": "internal"},
            headers={"Origin": "http://localhost"},
        )
        self.assertEqual(upload.status_code, 409, upload.get_data(as_text=True))
        self.assertTrue(upload.get_json().get("directUploadRequired"))
        self.assertFalse(upload.get_json().get("elevationRequired", False))

    def test_group_leader_can_upload_only_to_own_group(self):
        self.login("group-leader")
        own = self.client.post(
            "/api/slides/upload",
            data={"group": "grpHema", "area": "internal"},
            headers={"Origin": "http://localhost"},
        )
        self.assertEqual(own.status_code, 409, own.get_data(as_text=True))
        self.assertTrue(own.get_json().get("directUploadRequired"))

        other = self.client.post(
            "/api/slides/upload",
            data={"group": "grpBio", "area": "internal"},
            headers={"Origin": "http://localhost"},
        )
        self.assertEqual(other.status_code, 403, other.get_data(as_text=True))
        self.assertEqual(other.get_json().get("error"), "此資源不在你的授權範圍。")

    def test_clinical_teacher_can_upload_only_to_own_group(self):
        self.login("clinical-teacher")
        own = self.client.post(
            "/api/slides/upload",
            data={"group": "grpHema", "area": "internal"},
            headers={"Origin": "http://localhost"},
        )
        self.assertEqual(own.status_code, 409, own.get_data(as_text=True))
        self.assertTrue(own.get_json().get("directUploadRequired"))
        other = self.client.post(
            "/api/slides/upload",
            data={"group": "grpBio", "area": "internal"},
            headers={"Origin": "http://localhost"},
        )
        self.assertEqual(other.status_code, 403, other.get_data(as_text=True))

    def test_group_leader_question_management_is_group_scoped(self):
        self.login("group-leader")
        own = self.client.post(
            "/api/quiz-categories",
            json={"group": "grpHema", "area": "internal", "title": "Own group quiz"},
            headers={"Origin": "http://localhost"},
        )
        self.assertNotEqual(own.status_code, 403, own.get_data(as_text=True))

        other = self.client.post(
            "/api/quiz-categories",
            json={"group": "grpBio", "area": "internal", "title": "Other group quiz"},
            headers={"Origin": "http://localhost"},
        )
        self.assertEqual(other.status_code, 403, other.get_data(as_text=True))

    def test_student_and_auditor_cannot_mutate_materials(self):
        for username in ("student-user", "auditor-user"):
            self.login(username)
            response = self.client.post(
                "/api/slides/upload",
                data={"group": "grpHema", "area": "internal"},
                headers={"Origin": "http://localhost"},
            )
            self.assertEqual(response.status_code, 403, response.get_data(as_text=True))

    def test_atlas_publish_visibility_and_group_scope(self):
        self.login("education-admin")
        created = self.client.post("/api/atlas", json={
            "group": "grpHema", "category": "blood_cell", "title": "Myeloblast",
            "imageUrl": "/uploaded-slides/example/cell.png", "description": "blast cell",
            "tags": ["blast"], "published": True,
        }, headers={"Origin": "http://localhost"})
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True))
        published_id = created.get_json()["id"]
        draft = self.client.post("/api/atlas", json={
            "group": "grpHema", "category": "blood_cell", "title": "Draft cell",
            "published": False,
        }, headers={"Origin": "http://localhost"})
        self.assertEqual(draft.status_code, 201)
        self.login("student-user")
        listing = self.client.get("/api/atlas")
        self.assertEqual(listing.status_code, 200, listing.get_data(as_text=True))
        self.assertEqual([item["id"] for item in listing.get_json()["items"]], [published_id])
        self.assertEqual(self.client.post("/api/atlas", json={"group":"grpHema","category":"blood_cell","title":"Nope"}, headers={"Origin": "http://localhost"}).status_code, 403)
        self.login("auditor-user")
        self.assertEqual(self.client.patch(f"/api/atlas/{published_id}", json={"title":"Nope"}, headers={"Origin": "http://localhost"}).status_code, 403)

    def test_atlas_is_presented_as_formal_resource_ui(self):
        self.assertIn("/api/teaching-resource-search", ROOT.joinpath("teacher_app/atlas/routes.py").read_text(encoding="utf-8"))
        self.assertIn("搜尋本教材內容", ROOT.joinpath("static/system.html").read_text(encoding="utf-8"))
        self.assertIn("搜尋教學資源", ROOT.joinpath("static/system.html").read_text(encoding="utf-8"))

    def create_atlas(self, title, group="grpHema", published=False, tags=None):
        response = self.client.post("/api/atlas", json={"group": group, "category": "blood_cell", "title": title, "description": title + " description", "tags": tags or [], "published": published}, headers={"Origin": "http://localhost"})
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.get_json()["id"]

    def test_atlas_edit_and_filters_are_behavioral_and_group_scoped(self):
        self.login("education-admin")
        hema = self.create_atlas("Blast original", published=True, tags=["blast", "acute"])
        self.create_atlas("Urine draft", group="grpBio", published=False, tags=["sediment"])
        updated = self.client.patch(f"/api/atlas/{hema}", json={"title": "Edited blast", "tags": ["edited"], "difficulty": "advanced", "sortOrder": 7}, headers={"Origin": "http://localhost"})
        self.assertEqual(updated.status_code, 200, updated.get_data(as_text=True))
        found = self.client.get("/api/atlas?group=grpHema&tag=edited&status=published")
        self.assertEqual([x["title"] for x in found.get_json()["items"]], ["Edited blast"])
        self.assertEqual(found.get_json()["items"][0]["difficulty"], "advanced")
        self.login("student-user")
        student = self.client.get("/api/atlas?status=published&group=grpHema&tag=edited")
        self.assertEqual([x["title"] for x in student.get_json()["items"]], ["Edited blast"])
        self.assertEqual(self.client.patch(f"/api/atlas/{hema}", json={"title":"blocked"}, headers={"Origin":"http://localhost"}).status_code, 403)

    def test_unpublished_atlas_is_hidden_from_student_resource_search(self):
        self.login("education-admin")
        public_id = self.create_atlas("Public morphology", published=True, tags=["needle"])
        self.create_atlas("Secret morphology", published=False, tags=["needle"])
        self.login("student-user")
        items = self.client.get("/api/teaching-resource-search?q=needle").get_json()["items"]
        self.assertEqual([x.get("atlasItemId") for x in items if x["type"] == "atlas"], [public_id])

    def test_docx_confirm_merges_common_metadata_and_per_image_override(self):
        source = Path(self.temp.name) / "slides" / "docx-1"; source.mkdir(parents=True)
        docx = source / "atlas.docx"
        # A minimal valid PNG embedded twice is enough for the importer contract.
        from PIL import Image
        output = BytesIO(); Image.new("RGB", (1, 1), "white").save(output, format="PNG"); png = output.getvalue()
        with zipfile.ZipFile(docx, "w") as archive:
            archive.writestr("word/media/image1.png", png); archive.writestr("word/media/image2.png", png)
        material = {"id":"docx-1","group":"grpHema","folder":"docx-1","storageFilename":"atlas.docx","filename":"atlas.docx"}
        old_paths = pgy_app.app.config["STORAGE_PATHS"]
        test_paths = old_paths.with_runtime_overrides(
            uploaded_slides_dir=source.parent,
            material_storage=Path(self.temp.name) / "storage",
        )
        with patch(
            "teacher_app.materials.repository.get_material",
            return_value=material,
        ), patch.dict(pgy_app.app.config, {"STORAGE_PATHS": test_paths}):
            self.login("education-admin")
            result = self.client.post("/api/atlas/import-docx/docx-1/confirm", json={"metadata":{"title":"Shared title","group":"grpHema","category":"blood_cell","description":"Shared description","tags":["shared"],"differentialPoints":"Shared differential","teachingNotes":"Shared notes","difficulty":"basic","sortOrder":3},"items":[{"index":1},{"index":2,"title":"Override title","tags":["override"],"sortOrder":9}]}, headers={"Origin":"http://localhost"})
        self.assertEqual(result.status_code, 201, result.get_data(as_text=True))
        ids = result.get_json()["created"]
        records = [self.client.get(f"/api/atlas/{item_id}").get_json()["item"] for item_id in ids]
        self.assertEqual([x["title"] for x in records], ["Shared title", "Override title"])
        self.assertEqual(records[0]["tags"], ["shared"])
        self.assertEqual(records[1]["tags"], ["override"])
        self.assertTrue(all(not x["published"] and x["teachingNotes"] == "Shared notes" for x in records))

    def test_auto_index_records_no_text_and_unsupported_terminal_states(self):
        source = Path(self.temp.name) / "slides" / "empty"; source.mkdir(parents=True)
        pdf = source / "scan.pdf"; pdf.write_bytes(b"not a searchable pdf")
        material = {"id":"scan-1","group":"grpHema","folder":"empty","storageFilename":"scan.pdf","filename":"scan.pdf","storageBackend":"local"}
        with patch.object(legacy_app, "get_material", return_value=material), patch.object(legacy_app, "UPLOADED_SLIDES_DIR", source.parent), patch("smart_learning_67.extract_slide_text", return_value=[]):
            self.assertEqual(auto_index_material(legacy_app, "scan-1"), "no_text")
        conn, _ = self.connect()
        try: self.assertEqual(conn.execute("SELECT status FROM material_search_status WHERE material_id=?", ("scan-1",)).fetchone()[0], "no_text")
        finally: conn.close()

    def test_manual_rebuild_reports_no_text_not_unsupported_for_scanned_pdf(self):
        source = Path(self.temp.name) / "slides" / "manual"; source.mkdir(parents=True)
        (source / "scan.pdf").write_bytes(b"scan")
        material = {"id":"manual-scan","group":"grpHema","folder":"manual","storageFilename":"scan.pdf","filename":"scan.pdf","storageBackend":"local"}
        self.login("education-admin")
        old_paths = pgy_app.app.config["STORAGE_PATHS"]
        test_paths = old_paths.with_runtime_overrides(uploaded_slides_dir=source.parent)
        with patch(
            "teacher_app.materials.repository.get_material",
            return_value=material,
        ), patch.dict(pgy_app.app.config, {"STORAGE_PATHS": test_paths}), patch("smart_learning_67.extract_slide_text", return_value=[]):
            response = self.client.post("/api/material-search/manual-scan/index", headers={"Origin":"http://localhost"})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["status"], "no_text")
        unsupported = {**material, "id":"remote-1", "storageBackend":"r2"}
        with patch.object(legacy_app, "get_material", return_value=unsupported), patch.object(legacy_app, "UPLOADED_SLIDES_DIR", source.parent):
            self.assertEqual(auto_index_material(legacy_app, "remote-1"), "unsupported")
        conn, _ = self.connect()
        try: self.assertEqual(conn.execute("SELECT status FROM material_search_status WHERE material_id=?", ("remote-1",)).fetchone()[0], "unsupported")
        finally: conn.close()


class MaterialNavigationFrontend68Tests(unittest.TestCase):
    def source(self, relative_path):
        return ROOT.joinpath(relative_path).read_text(encoding="utf-8")

    def test_system_management_entry_opens_the_canonical_admin_workspace(self):
        html = self.source("static/system.html")
        core = self.source("static/system-core.js")
        self.assertIn('data-csp-click="openTeachingMaterials()"', html)
        self.assertIn("function openTeachingMaterials()", core)
        self.assertIn("window.openAdminWorkspace('course-materials')", core)
        self.assertNotIn('🔒 教材管理', html)
        self.assertNotIn('⚙️ 開啟管理後台', html)

    def test_portal_navigation_has_no_dead_public_management_handler(self):
        portal = self.source("static/portal-v56.js")
        self.assertNotIn("$$('.v575-manage-direct')", portal)
        self.assertNotIn("location.pathname==='/pgy'?'/pgy':'/internal'", portal)
        self.assertIn("['教材','/internal']", portal)

    def test_reader_error_contract_is_specific_and_login_is_safe(self):
        source = self.source("static/system-learner.js")
        for marker in (
            "error.status = res.status",
            "error.loginRequired",
            "登入已逾時，請",
            "重新登入",
            "沒有教材瀏覽權限",
            "教材服務暫時發生錯誤",
            "無法連線至伺服器",
            "encodeURIComponent(next)",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("Flask) 是否已啟動", source)

    def test_admin_secret_is_not_persisted_in_browser_storage(self):
        source = self.source("static/system-admin.js")
        self.assertNotIn("localStorage.setItem('admin_key'", source)
        self.assertNotIn("sessionStorage.setItem('admin_key'", source)


if __name__ == "__main__":
    unittest.main()
