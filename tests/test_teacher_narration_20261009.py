import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from teacher_app.materials import service as material_service
from teacher_app.materials import teacher_narration_routes as routes


def _slides(**extra):
    base = {
        "id": "slide-1", "group": "grpBio", "area": "internal", "viewerMode": "slides",
        "pageCount": 5, "currentVersion": 2, "storageMeta": {}, "title": "血糖原理",
    }
    base.update(extra)
    return base


def _audio(**extra):
    base = {
        "id": "audio-1", "group": "grpBio", "area": "internal", "viewerMode": "audio",
        "storageBackend": "mega", "storageKey": "k", "slidesPrefix": "", "storageMeta": {},
        "title": "旁白", "dateAdded": "2026-10-09T10:00:00",
    }
    base.update(extra)
    return base


class TimelineNormalizationTests(unittest.TestCase):
    def test_accepts_ordered_timeline_and_forces_first_start_to_zero(self):
        result = routes.normalize_timeline(
            [{"page": 0, "startMs": 300}, {"page": 1, "startMs": 8000}, {"page": 2, "startMs": 15000}],
            page_count=5, duration_ms=20000,
        )
        self.assertEqual(result, [
            {"page": 0, "startMs": 0}, {"page": 1, "startMs": 8000}, {"page": 2, "startMs": 15000},
        ])

    def test_merges_repeated_page_and_keeps_earliest_start(self):
        result = routes.normalize_timeline(
            [{"page": 0, "startMs": 0}, {"page": 1, "startMs": 1000}, {"page": 1, "startMs": 2000}],
        )
        self.assertEqual(result, [{"page": 0, "startMs": 0}, {"page": 1, "startMs": 1000}])

    def test_allows_going_back_to_an_earlier_page(self):
        result = routes.normalize_timeline(
            [{"page": 0, "startMs": 0}, {"page": 2, "startMs": 1000}, {"page": 1, "startMs": 2000}],
        )
        self.assertEqual([item["page"] for item in result], [0, 2, 1])

    def test_rejects_bad_input(self):
        bad_cases = [
            "not a list",
            [],
            [{"page": "x", "startMs": 0}],
            [{"page": -1, "startMs": 0}],
            [{"page": 0, "startMs": -5}],
            [{"page": 0, "startMs": 0}, {"page": 1, "startMs": 5000}, {"page": 2, "startMs": 1000}],
            ["oops"],
            [{"page": 0, "startMs": 0}] * 601,
        ]
        for raw in bad_cases:
            with self.subTest(raw=str(raw)[:40]):
                with self.assertRaises(routes.TimelineError):
                    routes.normalize_timeline(raw)

    def test_rejects_page_beyond_material_and_time_beyond_audio(self):
        with self.assertRaises(routes.TimelineError):
            routes.normalize_timeline([{"page": 0, "startMs": 0}, {"page": 5, "startMs": 10}], page_count=5)
        with self.assertRaises(routes.TimelineError):
            routes.normalize_timeline([{"page": 0, "startMs": 0}, {"page": 1, "startMs": 30000}], duration_ms=20000)


class AttachNarrationTests(unittest.TestCase):
    def test_teacher_narration_is_folded_into_source_with_timeline(self):
        timeline = [{"page": 0, "startMs": 0}, {"page": 1, "startMs": 5000}]
        audio = _audio(storageMeta={
            "mediaKind": "teacher_narration", "sourceMaterialId": "slide-1",
            "sourceVersion": 2, "timeline": timeline, "durationMs": 9000,
        })
        result = material_service._attach_narrations([_slides(), audio])
        self.assertEqual([item["id"] for item in result], ["slide-1"])
        narration = result[0]["narration"]
        self.assertEqual(narration["id"], "audio-1")
        self.assertEqual(narration["kind"], "teacher")
        self.assertEqual(narration["timeline"], timeline)
        self.assertEqual(narration["viewUrl"], "/view/audio-1")
        self.assertFalse(narration["stale"])

    def test_teacher_narration_is_stale_after_source_version_changes(self):
        audio = _audio(storageMeta={
            "mediaKind": "teacher_narration", "sourceMaterialId": "slide-1",
            "sourceVersion": 1, "timeline": [{"page": 0, "startMs": 0}],
        })
        result = material_service._attach_narrations([_slides(currentVersion=3), audio])
        self.assertTrue(result[0]["narration"]["stale"])

    def test_ai_narration_payload_is_unchanged(self):
        audio = _audio(storageMeta={"mediaKind": "ai_narration", "sourceMaterialId": "slide-1"})
        result = material_service._attach_narrations([_slides(), audio])
        self.assertEqual(result[0]["narration"], {"id": "audio-1", "title": "旁白", "viewUrl": "/view/audio-1"})


class BindRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.user = {"username": "teacher1"}
        owner = SimpleNamespace(app=self.app, _current_user=lambda: self.user)
        routes.register_teacher_narration_routes(owner)
        self.client = self.app.test_client()
        self.materials = {"slide-1": _slides(), "audio-1": _audio()}
        self.saved = {}

        def update_storage(material_id, **kwargs):
            self.saved[material_id] = kwargs

        patches = [
            patch.object(routes.material_repository, "get_material", side_effect=lambda mid: self.materials.get(mid)),
            patch.object(routes.material_repository, "update_material_storage", side_effect=update_storage),
            patch.object(routes.scope_filter, "scoped_groups", return_value=(self.user, None)),
            patch.object(routes.audit, "record_event", return_value=None),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def _post(self, **body):
        payload = {"audioMaterialId": "audio-1", "durationMs": 20000,
                   "timeline": [{"page": 0, "startMs": 0}, {"page": 1, "startMs": 6000}]}
        payload.update(body)
        return self.client.post("/api/materials/slide-1/teacher-narration", json=payload)

    def test_binds_audio_and_stores_timeline_in_storage_meta(self):
        response = self._post()
        self.assertEqual(response.status_code, 200)
        meta = json.loads(self.saved["audio-1"]["storage_meta_json"])
        self.assertEqual(meta["mediaKind"], "teacher_narration")
        self.assertEqual(meta["sourceMaterialId"], "slide-1")
        self.assertEqual(meta["sourceVersion"], 2)
        self.assertEqual(meta["timeline"][1], {"page": 1, "startMs": 6000})
        self.assertEqual(meta["boundBy"], "teacher1")
        # The audio file's own storage location is passed through untouched.
        self.assertEqual(self.saved["audio-1"]["backend"], "mega")
        self.assertEqual(self.saved["audio-1"]["storage_key"], "k")

    def test_requires_login(self):
        self.user = None
        self.assertEqual(self._post().status_code, 401)

    def test_scope_denial_blocks_binding(self):
        denied = (jsonify_denied := self.app.response_class("no", status=403))
        with patch.object(routes.scope_filter, "scoped_groups", return_value=(None, denied)):
            response = self._post()
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("audio-1", self.saved)

    def test_rejects_cross_group_audio(self):
        self.materials["audio-1"] = _audio(group="grpMicro")
        self.assertEqual(self._post().status_code, 400)
        self.assertNotIn("audio-1", self.saved)

    def test_rejects_non_slide_source_and_non_audio_recording(self):
        self.materials["slide-1"] = _slides(viewerMode="video")
        self.assertEqual(self._post().status_code, 400)
        self.materials["slide-1"] = _slides()
        self.materials["audio-1"] = _audio(viewerMode="video")
        self.assertEqual(self._post().status_code, 400)

    def test_rejects_audio_used_by_ai_narration_or_other_slide(self):
        self.materials["audio-1"] = _audio(storageMeta={"mediaKind": "ai_narration", "sourceMaterialId": "slide-9"})
        self.assertEqual(self._post().status_code, 409)
        self.materials["audio-1"] = _audio(storageMeta={"mediaKind": "teacher_narration", "sourceMaterialId": "slide-9"})
        self.assertEqual(self._post().status_code, 409)

    def test_worker_transcoded_audio_with_generic_kind_can_be_bound(self):
        # The Worker stamps uploads with mediaKind "audio"; that must not block the bind.
        self.materials["audio-1"] = _audio(storageMeta={"mediaKind": "audio"})
        self.assertEqual(self._post().status_code, 200)

    def test_rebinding_same_pair_is_allowed_to_replace_timeline(self):
        self.materials["audio-1"] = _audio(storageMeta={"mediaKind": "teacher_narration", "sourceMaterialId": "slide-1"})
        self.assertEqual(self._post().status_code, 200)

    def test_bad_timeline_returns_400_with_message(self):
        response = self._post(timeline=[{"page": 0, "startMs": 0}, {"page": 9, "startMs": 10}])
        self.assertEqual(response.status_code, 400)
        self.assertIn("只有 5 頁", response.get_json()["error"])
        self.assertNotIn("audio-1", self.saved)


ROOT = Path(__file__).resolve().parents[1]


class FrontendWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recorder = (ROOT / "static" / "teacher-slide-narration-1109.js").read_text(encoding="utf-8")
        cls.player = (ROOT / "static" / "learner-narration-1100.js").read_text(encoding="utf-8")
        cls.assets = (ROOT / "teacher_app" / "frontend" / "assets.py").read_text(encoding="utf-8")

    def test_recorder_is_registered_after_upload_client_and_learner_player(self):
        self.assertIn("/teacher-slide-narration-1109.js", self.assets)
        self.assertLess(self.assets.index("/material-upload-client.js"), self.assets.index("/teacher-slide-narration-1109.js"))
        self.assertLess(self.assets.index("/learner-narration-1100.js"), self.assets.index("/teacher-slide-narration-1109.js"))

    def test_recorder_is_limited_to_teaching_roles_with_material_manage(self):
        self.assertIn("material.manage", self.recorder)
        for role in ("clinical_teacher", "group_leader", "education_admin"):
            self.assertIn(role, self.recorder)

    def test_recorder_uses_existing_upload_lane_and_binding_endpoint(self):
        self.assertIn("MaterialUploadClient.enqueue", self.recorder)
        self.assertIn("waitForAdminMaterialJobs", self.recorder)
        self.assertIn("/teacher-narration", self.recorder)
        # Page turns are read from the viewer state so keyboard/thumbnail navigation is captured too.
        self.assertIn("slideViewerState", self.recorder)

    def test_recorder_silences_learner_player_and_warns_about_privacy(self):
        self.assertIn("__teacherNarrationRecording", self.recorder)
        self.assertIn("__teacherNarrationRecording", self.player)
        self.assertIn("病歷號", self.recorder)

    def test_subtitle_draft_is_opt_out_checkbox_with_retry_button(self):
        self.assertIn("wantSubtitle", self.recorder)
        self.assertIn("queueSubtitle", self.recorder)
        self.assertIn("/api/media-subtitles/generate", self.recorder)
        self.assertNotIn("window.confirm('要順便產生字幕", self.recorder)

    def test_recorder_cannot_recurse_between_tick_and_stop(self):
        self.assertIn("stopping", self.recorder)

    def test_player_keeps_existing_contract_and_adds_sync_and_captions(self):
        for needle in ("audio.play()", "teacher.narration.muted", "goToSlidePage", "subtitles/approved", "narration.kind"):
            self.assertIn(needle, self.player)
        # Only the teacher-approved subtitle endpoint is used; never the draft list.
        self.assertNotIn("/api/media-subtitles?", self.player)

    def test_entry_is_only_in_material_lists_and_recorder_is_armed_by_open(self):
        static = ROOT / "static"
        wizard = (static / "course-wizard-681.js").read_text(encoding="utf-8")
        overview = (static / "admin-course-material.js").read_text(encoding="utf-8")
        questions = (static / "admin-ai-questions.js").read_text(encoding="utf-8")
        self.assertIn("TeacherSlideNarration1109", wizard)
        self.assertIn("recorder.open", wizard)
        self.assertIn('data-cw-mat-action="narrate"', wizard)
        self.assertIn("TeacherSlideNarration1109", overview)
        self.assertIn("recorder.open", overview)
        self.assertIn("data-material-narrate", overview)
        self.assertIn("teacher_narration", overview)
        self.assertIn("teacher_narration", questions)
        self.assertIn("armed", self.recorder)
        self.assertIn("open", self.recorder)
        # No other script may call the recorder.
        for path in static.glob("*.js"):
            if path.name in {"course-wizard-681.js", "admin-course-material.js", "teacher-slide-narration-1109.js"}:
                continue
            self.assertNotIn("TeacherSlideNarration1109", path.read_text(encoding="utf-8", errors="ignore"), path.name)


if __name__ == "__main__":
    unittest.main()
