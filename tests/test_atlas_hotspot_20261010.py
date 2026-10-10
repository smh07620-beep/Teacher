"""Atlas annotations + "click the structure" (atlas_hotspot) question type."""
import json
import unittest
from unittest.mock import patch

from teacher_app.assessments import hotspot, runtime_questions
from teacher_app.atlas import annotations, service as atlas_service
from teacher_app.common.errors import ApiError
from teacher_app.exams import grading
from teacher_app.exams import service as exam_service


def mark(mark_id="m1", label="嗜中性球", x=0.2, y=0.3, w=0.1, h=0.1, detail="分葉核"):
    return {"id": mark_id, "label": label, "detail": detail, "x": x, "y": y, "w": w, "h": h}


def atlas_item(published=True, marks=None):
    return {
        "id": "atlas1", "published": published, "imageUrl": "/api/atlas/images/abc.jpg",
        "annotationJson": {"version": 1, "marks": marks if marks is not None else [mark()]},
    }


class AnnotationValidationTests(unittest.TestCase):
    def test_empty_inputs_mean_no_annotations(self):
        for value in (None, {}, [], "x", {"marks": None}, {"marks": []}):
            self.assertEqual(annotations.normalise(value), {})

    def test_valid_marks_are_canonicalised(self):
        out = annotations.normalise({"marks": [{"label": " 淋巴球 ", "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2}]})
        self.assertEqual(out["version"], 1)
        self.assertEqual(out["marks"][0]["label"], "淋巴球")
        self.assertTrue(out["marks"][0]["id"])  # auto id
        self.assertEqual(out["marks"][0]["detail"], "")

    def test_duplicate_ids_are_made_unique(self):
        out = annotations.normalise({"marks": [mark("a"), mark("a", label="B", x=0.5)]})
        ids = [m["id"] for m in out["marks"]]
        self.assertEqual(len(set(ids)), 2)

    def test_rejects_malformed_marks_instead_of_dropping_them(self):
        bad = [
            {"marks": "nope"},
            {"marks": ["x"]},
            {"marks": [mark(label="")]},
            {"marks": [mark(w=0.001)]},
            {"marks": [mark(x=-0.1)]},
            {"marks": [mark(x=0.95, w=0.2)]},
            {"marks": [mark(x="a")]},
            {"marks": [mark(x=float("nan"))]},
            {"marks": [mark(x=True)]},
            {"marks": [mark(str(i), x=0.01 * (i % 50)) for i in range(annotations.MAX_MARKS + 1)]},
        ]
        for value in bad:
            with self.subTest(value=str(value)[:60]):
                with self.assertRaises(ApiError) as ctx:
                    annotations.normalise(value)
                self.assertEqual(ctx.exception.status, 400)

    def test_label_and_detail_are_length_limited(self):
        out = annotations.normalise({"marks": [mark(label="a" * 500, detail="b" * 5000)]})
        self.assertEqual(len(out["marks"][0]["label"]), annotations.MAX_LABEL)
        self.assertEqual(len(out["marks"][0]["detail"]), annotations.MAX_DETAIL)


class GeometryTests(unittest.TestCase):
    region = {"x": 0.2, "y": 0.3, "w": 0.1, "h": 0.1}

    def test_inside_outside_and_tolerance(self):
        self.assertTrue(annotations.point_in_region({"x": 0.25, "y": 0.35}, self.region))
        self.assertTrue(annotations.point_in_region({"x": 0.2, "y": 0.3}, self.region))
        self.assertTrue(annotations.point_in_region({"x": 0.304, "y": 0.35}, self.region))  # within tolerance
        self.assertFalse(annotations.point_in_region({"x": 0.32, "y": 0.35}, self.region))
        self.assertFalse(annotations.point_in_region({"x": 0.25, "y": 0.5}, self.region))

    def test_garbage_points_never_pass(self):
        for point in (None, "x", [], {}, {"x": "a", "y": 1}, {"x": float("inf"), "y": 0.3}, {"x": 0.25}):
            self.assertFalse(annotations.point_in_region(point, self.region))
        self.assertFalse(annotations.point_in_region({"x": 0.25, "y": 0.35}, None))
        self.assertFalse(annotations.point_in_region({"x": 0.25, "y": 0.35}, {}))

    def test_smallest_box_wins_when_overlapping(self):
        ann = {"marks": [mark("big", x=0.1, y=0.1, w=0.5, h=0.5), mark("small", x=0.2, y=0.2, w=0.05, h=0.05)]}
        self.assertEqual(annotations.mark_at_point(ann, {"x": 0.22, "y": 0.22})["id"], "small")
        self.assertEqual(annotations.mark_at_point(ann, {"x": 0.5, "y": 0.5})["id"], "big")
        self.assertIsNone(annotations.mark_at_point(ann, {"x": 0.9, "y": 0.9}))


class AtlasServiceValidationTests(unittest.TestCase):
    manager = {"username": "t", "role": "system_admin", "roles": ["system_admin"]}

    def test_update_rejects_bad_annotation_before_touching_storage(self):
        item = {"id": "a1", "group": "grpBio"}
        with patch.object(atlas_service.repository, "get_item", return_value=item), \
                patch.object(atlas_service.repository, "update_item") as update, \
                patch.object(atlas_service, "can_manage", return_value=True):
            with self.assertRaises(ApiError):
                atlas_service.update_item(self.manager, "a1", {"annotationJson": {"marks": [mark(label="")]}})
            update.assert_not_called()

    def test_update_stores_canonical_annotation(self):
        item = {"id": "a1", "group": "grpBio"}
        with patch.object(atlas_service.repository, "get_item", return_value=item), \
                patch.object(atlas_service.repository, "update_item") as update, \
                patch.object(atlas_service, "can_manage", return_value=True):
            atlas_service.update_item(self.manager, "a1", {"annotationJson": {"marks": [mark()]}})
        stored = json.loads(update.call_args.args[1]["annotation_json"])
        self.assertEqual(stored["marks"][0]["label"], "嗜中性球")

    def test_update_without_annotation_leaves_it_alone(self):
        item = {"id": "a1", "group": "grpBio"}
        with patch.object(atlas_service.repository, "get_item", return_value=item), \
                patch.object(atlas_service.repository, "update_item") as update, \
                patch.object(atlas_service, "can_manage", return_value=True):
            atlas_service.update_item(self.manager, "a1", {"title": "新名稱"})
        self.assertNotIn("annotation_json", update.call_args.args[1])


class HotspotQuestionConfigTests(unittest.TestCase):
    def prepare(self, config, item=None):
        with patch.object(hotspot.atlas_repository, "get_item", return_value=item if item is not None else atlas_item()):
            return hotspot.prepare_config(config)

    def test_snapshot_of_region_label_and_image(self):
        config, image = self.prepare({"atlasItemId": "atlas1", "correctMarkId": "m1"})
        self.assertEqual(config["correctRegion"], {"x": 0.2, "y": 0.3, "w": 0.1, "h": 0.1})
        self.assertEqual(config["markLabel"], "嗜中性球")
        self.assertEqual(image, "/api/atlas/images/abc.jpg")

    def test_clear_teacher_messages_for_each_problem(self):
        cases = [
            ({}, None, "請先選擇一張圖譜"),
            ({"atlasItemId": "x", "correctMarkId": "m1"}, {}, "找不到指定的圖譜"),
            ({"atlasItemId": "atlas1", "correctMarkId": "m1"}, atlas_item(published=False), "尚未發布"),
            ({"atlasItemId": "atlas1"}, None, "請選擇要讓學員點出的標記"),
            ({"atlasItemId": "atlas1", "correctMarkId": "zzz"}, None, "找不到指定的標記"),
        ]
        for config, item, message in cases:
            with self.subTest(message=message):
                with self.assertRaises(ValueError) as ctx:
                    self.prepare(config, item)
                self.assertIn(message, str(ctx.exception))

    def test_resolve_for_attempt_refreshes_region_from_atlas(self):
        question = {"questionType": "atlas_hotspot", "answerConfig": {
            "atlasItemId": "atlas1", "correctMarkId": "m1", "markLabel": "舊",
            "correctRegion": {"x": 0, "y": 0, "w": 0.1, "h": 0.1}}}
        moved = atlas_item(marks=[mark(x=0.6, y=0.6)])
        with patch.object(hotspot.atlas_repository, "get_item", return_value=moved):
            out = hotspot.resolve_for_attempt(question)
        self.assertEqual(out["answerConfig"]["correctRegion"]["x"], 0.6)
        self.assertEqual(question["answerConfig"]["correctRegion"]["x"], 0)  # input untouched

    def test_resolve_keeps_saved_region_when_atlas_is_gone(self):
        saved = {"x": 0.2, "y": 0.3, "w": 0.1, "h": 0.1}
        question = {"questionType": "atlas_hotspot", "answerConfig": {
            "atlasItemId": "gone", "correctMarkId": "m1", "correctRegion": saved}}
        with patch.object(hotspot.atlas_repository, "get_item", return_value={}):
            out = hotspot.resolve_for_attempt(question)
        self.assertEqual(out["answerConfig"]["correctRegion"], saved)

    def test_resolve_ignores_other_question_types(self):
        question = {"questionType": "choice", "answerConfig": {}}
        with patch.object(hotspot.atlas_repository, "get_item", side_effect=AssertionError("must not query")):
            self.assertEqual(hotspot.resolve_for_attempt(question), question)


class QuestionNormalisationTests(unittest.TestCase):
    def normalise(self, data, existing=None, item=None):
        with patch.object(hotspot.atlas_repository, "get_item", return_value=item if item is not None else atlas_item()):
            return runtime_questions._normalized_common(data, existing=existing)

    def test_create_hotspot_question(self):
        out = self.normalise({"question": "請點出嗜中性球", "questionType": "atlas_hotspot",
                              "options": ["a", "b"], "answerConfig": {"atlasItemId": "atlas1", "correctMarkId": "m1"}})
        self.assertEqual(out["questionType"], "atlas_hotspot")
        self.assertEqual(out["options"], [])
        self.assertEqual(out["imageUrl"], "/api/atlas/images/abc.jpg")
        self.assertIn("correctRegion", out["answerConfig"])

    def test_hotspot_without_atlas_is_rejected(self):
        with self.assertRaises(ValueError):
            self.normalise({"question": "q", "questionType": "atlas_hotspot", "answerConfig": {}})

    def test_unrelated_edit_does_not_revalidate_against_atlas(self):
        existing = {"question": "q", "questionType": "atlas_hotspot", "imageUrl": "/api/atlas/images/abc.jpg",
                    "answerConfig": {"atlasItemId": "atlas1", "correctMarkId": "m1",
                                     "correctRegion": {"x": 0.2, "y": 0.3, "w": 0.1, "h": 0.1}}}
        # Atlas was un-published meanwhile; disabling the question must still work.
        out = self.normalise({"active": False}, existing=existing, item=atlas_item(published=False))
        self.assertEqual(out["answerConfig"]["correctMarkId"], "m1")
        self.assertFalse(out["active"])

    def test_inline_editor_without_mark_keeps_stored_definition(self):
        existing = {"question": "q", "questionType": "atlas_hotspot", "imageUrl": "/api/atlas/images/abc.jpg",
                    "answerConfig": {"atlasItemId": "atlas1", "correctMarkId": "m1", "markLabel": "嗜中性球",
                                     "correctRegion": {"x": 0.2, "y": 0.3, "w": 0.1, "h": 0.1}}}
        out = self.normalise({"question": "改寫後的題目", "questionType": "atlas_hotspot", "answerConfig": {},
                              "options": [], "correct": 0}, existing=existing, item=atlas_item(published=False))
        self.assertEqual(out["question"], "改寫後的題目")
        self.assertEqual(out["answerConfig"]["correctMarkId"], "m1")
        self.assertEqual(out["imageUrl"], "/api/atlas/images/abc.jpg")

    def test_changing_only_the_mark_reuses_the_stored_atlas(self):
        existing = {"question": "q", "questionType": "atlas_hotspot", "imageUrl": "/api/atlas/images/abc.jpg",
                    "answerConfig": {"atlasItemId": "atlas1", "correctMarkId": "m1"}}
        item = atlas_item(marks=[mark("m1"), mark("m2", label="淋巴球", x=0.6, y=0.6)])
        out = self.normalise({"answerConfig": {"correctMarkId": "m2"}}, existing=existing, item=item)
        self.assertEqual(out["answerConfig"]["markLabel"], "淋巴球")
        self.assertEqual(out["answerConfig"]["atlasItemId"], "atlas1")

    def test_switching_type_drops_hotspot_secrets(self):
        existing = {"question": "q", "questionType": "atlas_hotspot",
                    "answerConfig": {"correctRegion": {"x": 0}, "atlasItemId": "a"}}
        out = self.normalise({"questionType": "choice", "options": ["a", "b"],
                              "answerConfig": {"correctRegion": {"x": 0}, "atlasItemId": "a"}}, existing=existing)
        self.assertNotIn("correctRegion", out["answerConfig"])
        self.assertNotIn("atlasItemId", out["answerConfig"])

    def test_bulk_import_cannot_create_hotspot(self):
        self.assertNotIn("atlas_hotspot", runtime_questions.IMPORTABLE_TYPES)
        self.assertIn("atlas_hotspot", runtime_questions.QUESTION_TYPES)


class HotspotGradingTests(unittest.TestCase):
    question = {
        "id": "q1", "question": "請點出嗜中性球", "questionType": "atlas_hotspot",
        "imageUrl": "/api/atlas/images/abc.jpg", "explanation": "分葉核",
        "answerConfig": {"atlasItemId": "atlas1", "correctMarkId": "m1", "markLabel": "嗜中性球",
                         "correctRegion": {"x": 0.2, "y": 0.3, "w": 0.1, "h": 0.1}},
    }

    def test_scoring(self):
        self.assertTrue(grading.score_question(self.question, {"x": 0.25, "y": 0.35}))
        self.assertFalse(grading.score_question(self.question, {"x": 0.9, "y": 0.9}))
        self.assertFalse(grading.score_question(self.question, None))
        self.assertFalse(grading.score_question(self.question, 2))
        self.assertFalse(grading.score_question({**self.question, "answerConfig": {}}, {"x": 0.25, "y": 0.35}))

    def test_learner_payload_has_no_answer_location_or_name(self):
        safe = grading.sanitize_question(self.question)
        flat = json.dumps(safe, ensure_ascii=False)
        for secret in ("correctRegion", "correctMarkId", "markLabel", "atlasItemId", "嗜中性球分", "分葉核"):
            self.assertNotIn(secret, flat)
        self.assertEqual(safe["imageUrl"], "/api/atlas/images/abc.jpg")  # image itself is needed

    def test_review_projection_stays_secret_after_submission(self):
        flat = json.dumps(grading.review_question(self.question), ensure_ascii=False)
        for secret in ("correctRegion", "correctMarkId", "atlasItemId"):
            self.assertNotIn(secret, flat)

    def test_grade_attempt_counts_hotspot_and_records_click(self):
        result = grading.grade_attempt([self.question, self.question], [{"x": 0.25, "y": 0.35}, {"x": 0.9, "y": 0.9}], 50)
        self.assertEqual(result["correctCount"], 1)
        self.assertEqual(result["wrongCount"], 1)
        self.assertEqual(result["score"], 50)
        self.assertTrue(result["answersDetail"][0]["userAnswer"].startswith("點選位置"))
        self.assertEqual(result["status"], "合格")

    def test_unanswered_is_wrong_and_labelled(self):
        result = grading.grade_attempt([self.question], [None], 60)
        self.assertEqual(result["answersDetail"][0]["userAnswer"], "未答")
        self.assertEqual(result["wrongCount"], 1)


class ExamDrawTests(unittest.TestCase):
    def test_attempt_snapshot_uses_current_atlas_box_and_is_stripped_for_learner(self):
        stored = {"id": "q1", "question": "請點出嗜中性球", "questionType": "atlas_hotspot", "active": True,
                  "options": [], "correct": 0, "explanation": "", "tag": "血球",
                  "imageUrl": "/api/atlas/images/abc.jpg",
                  "answerConfig": {"atlasItemId": "atlas1", "correctMarkId": "m1", "markLabel": "舊",
                                   "correctRegion": {"x": 0, "y": 0, "w": 0.1, "h": 0.1}}}
        moved = atlas_item(marks=[mark(x=0.6, y=0.6)])
        with patch.object(exam_service.assessment_repository, "list_questions", return_value=[dict(stored)]), \
                patch.object(hotspot.atlas_repository, "get_item", return_value=moved):
            drawn = exam_service._draw_questions({"id": "quiz1"})
        snapshot = drawn[0]
        self.assertEqual(snapshot["answerConfig"]["correctRegion"]["x"], 0.6)
        # Grading uses the snapshot...
        self.assertTrue(grading.score_question(snapshot, {"x": 0.65, "y": 0.65}))
        self.assertFalse(grading.score_question(snapshot, {"x": 0.05, "y": 0.05}))
        # ...and the learner-facing projection of that snapshot leaks nothing.
        self.assertNotIn("correctRegion", json.dumps(grading.sanitize_question(snapshot)))

    def test_hotspot_is_a_known_quota_type(self):
        self.assertIn("atlas_hotspot", exam_service.QUESTION_TYPES)


if __name__ == "__main__":
    unittest.main()
