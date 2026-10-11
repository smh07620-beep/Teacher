import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from teacher_app.materials import teacher_narration_routes as routes


def slide(material_id, **extra):
    base = {
        "id": material_id, "group": "grpBio", "area": "internal", "viewerMode": "slides",
        "pageCount": 5, "currentVersion": 1, "storageMeta": {}, "title": material_id,
    }
    base.update(extra)
    return base


def narration(audio_id, source_id, **extra):
    base = {
        "id": audio_id, "group": "grpBio", "area": "internal", "viewerMode": "audio",
        "storageBackend": "mega", "storageKey": "key-" + audio_id, "slidesPrefix": "pre",
        "storageMeta": {
            "mediaKind": "teacher_narration", "sourceMaterialId": source_id, "sourceVersion": 3,
            "timeline": [{"page": 0, "startMs": 0}, {"page": 1, "startMs": 4000}], "durationMs": 9000,
        },
    }
    base.update(extra)
    return base


class MoveNarrationTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.user = {"username": "teacher1"}
        routes.register_teacher_narration_routes(SimpleNamespace(app=self.app, _current_user=lambda: self.user))
        self.client = self.app.test_client()
        self.materials = {"old": slide("old", currentVersion=3), "new": slide("new")}
        self.audios = [narration("aud-1", "old")]
        self.saved = {}
        self.events = []
        self.denied = None

        def update_storage(material_id, **kwargs):
            self.saved[material_id] = kwargs

        def scoped(owner, permission, groups):
            return (None, self.denied) if self.denied else (self.user, None)

        patches = [
            patch.object(routes.material_repository, "get_material", side_effect=lambda mid: self.materials.get(mid)),
            patch.object(routes.material_repository, "list_uploaded_materials",
                         side_effect=lambda legacy_base=None, include_inactive=False: list(self.audios)),
            patch.object(routes.material_repository, "update_material_storage", side_effect=update_storage),
            patch.object(routes.scope_filter, "scoped_groups", side_effect=scoped),
            patch.object(routes.audit, "record_event", side_effect=lambda **kw: self.events.append(kw)),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def move(self, **body):
        payload = {"fromSourceId": "old"}
        payload.update(body)
        return self.client.post("/api/materials/new/teacher-narration/move", json=payload)

    def test_moves_binding_keeps_recording_location_and_timeline(self):
        response = self.move()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["moved"], 1)
        saved = self.saved["aud-1"]
        meta = json.loads(saved["storage_meta_json"])
        self.assertEqual(meta["sourceMaterialId"], "new")
        self.assertEqual(meta["sourceVersion"], 1)
        self.assertEqual(meta["movedFromMaterialId"], "old")
        self.assertEqual(meta["movedBy"], "teacher1")
        self.assertEqual(meta["timeline"][1], {"page": 1, "startMs": 4000})
        self.assertEqual(meta["durationMs"], 9000)
        self.assertEqual((saved["backend"], saved["storage_key"], saved["slides_prefix"]), ("mega", "key-aud-1", "pre"))
        self.assertEqual(self.events[0]["action"], "material.teacher_narration.move")
        self.assertEqual(self.events[0]["before"], {"sourceMaterialId": "old"})
        self.assertEqual(self.events[0]["after"], {"sourceMaterialId": "new"})

    def test_page_count_mismatch_is_refused_and_nothing_changes(self):
        self.materials["new"] = slide("new", pageCount=6)
        response = self.move()
        self.assertEqual(response.status_code, 409)
        self.assertIn("頁數不同", response.get_json()["error"])
        self.assertEqual(self.saved, {})

    def test_requires_login(self):
        self.user = None
        self.assertEqual(self.move().status_code, 401)

    def test_scope_denial_blocks_move(self):
        self.denied = self.app.response_class("no", status=403)
        self.assertEqual(self.move().status_code, 403)
        self.assertEqual(self.saved, {})

    def test_cross_group_is_refused(self):
        self.materials["new"] = slide("new", group="grpMicro")
        self.assertEqual(self.move().status_code, 400)
        self.assertEqual(self.saved, {})

    def test_does_not_overwrite_existing_narration_on_target(self):
        self.audios.append(narration("aud-2", "new"))
        response = self.move()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.saved, {})

    def test_nothing_to_move_and_bad_requests(self):
        self.audios = []
        self.assertEqual(self.move().status_code, 404)
        self.assertEqual(self.move(fromSourceId="").status_code, 400)
        self.assertEqual(self.move(fromSourceId="new").status_code, 400)
        self.assertEqual(self.move(fromSourceId="ghost").status_code, 404)

    def test_target_must_be_a_slide_material(self):
        self.materials["new"] = slide("new", viewerMode="video")
        self.assertEqual(self.move().status_code, 400)

    def test_moves_every_recording_bound_to_old_material(self):
        self.audios = [narration("aud-1", "old"), narration("aud-3", "old")]
        self.assertEqual(self.move().get_json()["moved"], 2)
        self.assertEqual(set(self.saved), {"aud-1", "aud-3"})


class RecorderPanelWiringTests(unittest.TestCase):
    def test_panel_offers_reuse_and_calls_the_move_endpoint_without_innerhtml(self):
        from pathlib import Path

        src = (Path(__file__).resolve().parents[1] / "static" / "teacher-slide-narration-1109.js").read_text(encoding="utf-8")
        self.assertIn("沿用舊教材的旁白", src)
        self.assertIn("/teacher-narration/move", src)
        self.assertIn("fromSourceId", src)
        self.assertNotIn("innerHTML", src)


if __name__ == "__main__":
    unittest.main()
