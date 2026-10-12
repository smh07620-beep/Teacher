import unittest
from pathlib import Path

from teacher_app.atlas import service

ROOT = Path(__file__).resolve().parents[1]


def item(i, created, published=False, title="A", desc="d", material="m1", source="docx", group="grpMicro"):
    return {"id": i, "createdAt": created, "published": published, "title": title,
            "description": desc, "sourceMaterialId": material, "source": source, "group": group}


class FindDuplicatesTest(unittest.TestCase):
    def test_keeps_oldest_draft_and_removes_rest(self):
        items = [item("1", "2026-01-01"), item("2", "2026-01-02"), item("3", "2026-01-03")]
        self.assertEqual(sorted(service.find_duplicate_ids(items)), ["2", "3"])

    def test_never_removes_published_and_prefers_keeping_it(self):
        items = [item("1", "2026-01-01"), item("2", "2026-01-02", published=True)]
        self.assertEqual(service.find_duplicate_ids(items), ["1"])

    def test_different_titles_groups_or_manual_items_are_untouched(self):
        items = [item("1", "a"), item("2", "b", title="B"), item("3", "c", group="grpBio"),
                 item("4", "d", source="manual", material=""), item("5", "e", source="manual", material="")]
        self.assertEqual(service.find_duplicate_ids(items), [])


class WiringTest(unittest.TestCase):
    def test_importer_skips_duplicates_before_storing(self):
        src = (ROOT / "teacher_app/atlas/importer.py").read_text(encoding="utf-8")
        self.assertLess(src.index("dup_key in existing_keys"), src.index("store_image_bytes("))

    def test_button_route_and_allowlist(self):
        self.assertIn("/api/atlas/dedupe", (ROOT / "teacher_app/atlas/routes.py").read_text(encoding="utf-8"))
        self.assertIn("removeAtlasDuplicates", (ROOT / "static/system-csp-actions.js").read_text(encoding="utf-8"))
        self.assertIn("atlas-dedupe-action", (ROOT / "static/system.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()


class ReleaseImageTest(unittest.TestCase):
    def test_draft_files_released_only_when_unreferenced(self):
        from unittest.mock import patch
        released = []
        draft = {"imageUrl": "/api/atlas/images/a.png", "published": False}
        with patch.object(service.repository, "list_items", return_value=[]):
            service._release_if_unused(draft, released.append)
        self.assertEqual(released, ["/api/atlas/images/a.png"])
        with patch.object(service.repository, "list_items", return_value=[dict(draft)]):
            service._release_if_unused(draft, released.append)
        self.assertEqual(len(released), 1)

    def test_published_items_never_released(self):
        released = []
        service._release_if_unused({"imageUrl": "/api/atlas/images/a.png", "published": True}, released.append)
        self.assertEqual(released, [])

    def test_delete_image_files_removes_local_and_thumb(self):
        import tempfile
        from teacher_app.atlas import image_store
        with tempfile.TemporaryDirectory() as root:
            d = image_store.image_directory(root)
            (d / "x.png").write_bytes(b"1")
            (d / "thumb-x.png").write_bytes(b"1")
            image_store.delete_image_files(root, "/api/atlas/images/x.png")
            self.assertFalse((d / "x.png").exists())
            self.assertFalse((d / "thumb-x.png").exists())
