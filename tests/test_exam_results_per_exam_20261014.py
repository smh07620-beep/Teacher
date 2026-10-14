"""Results screens must keep each exam separate (考卷主題 / 考卷篩選 / 台灣時間)."""
from pathlib import Path
import unittest

from teacher_app.learning.progress_service import record_to_dict

ROOT = Path(__file__).resolve().parents[1]


def _row(**extra):
    base = {
        "id": "r1", "created_at": "2026-10-14T12:36:01.926122+00:00", "name": "許晉誠", "emp_id": "07620",
        "role": "system_admin", "evaluator_name": "", "evaluator_title": "", "quiz_title": "c503 操作與維護",
        "score": 100, "status": "合格", "answers_detail": "[]", "group_key": "grpBio", "training_area": "internal",
        "course_id": "", "review_status": "completed", "quiz_category_id": "cat-1", "passing_score": 80,
    }
    base.update(extra)
    return base


class ExamResultsPerExamTests(unittest.TestCase):
    def test_record_dict_exposes_quiz_title_for_the_frontend(self):
        record = record_to_dict(_row())
        self.assertEqual(record["quizTitle"], "c503 操作與維護")
        self.assertEqual(record["quizCategoryId"], "cat-1")

    def test_missing_title_is_empty_string_not_none(self):
        row = _row()
        row.pop("quiz_title")
        self.assertEqual(record_to_dict(row)["quizTitle"], "")

    def test_legacy_host_serializer_also_exposes_quiz_title(self):
        source = (ROOT / "teacher_app" / "legacy_host.py").read_text(encoding="utf-8")
        self.assertIn('r["quizTitle"] = str(r.get("quiz_title", "") or "")', source)

    def test_results_screen_has_exam_filter_and_taipei_time(self):
        data = (ROOT / "static" / "admin-results-data.js").read_text(encoding="utf-8")
        html = (ROOT / "static" / "system.html").read_text(encoding="utf-8")
        self.assertIn('id="admin-results-exam"', html)
        self.assertIn('id="admin-results-attempts"', html)
        self.assertIn("Asia/Taipei", data)
        self.assertIn("filterByExam(records)", data)

    def test_csv_export_follows_exam_filter(self):
        export = (ROOT / "static" / "admin-results-export.js").read_text(encoding="utf-8")
        self.assertIn("adminResultsFilterByExam", export)
        self.assertIn("第幾次作答", export)

    def test_assessment_history_and_analytics_have_exam_filter(self):
        inline = (ROOT / "static" / "teacher-assessment-inline-1031.js").read_text(encoding="utf-8")
        self.assertIn('data-assess-exam="history"', inline)
        self.assertIn('data-assess-exam="analytics"', inline)


if __name__ == "__main__":
    unittest.main()
