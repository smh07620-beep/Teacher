import unittest
from pathlib import Path

JS = (Path(__file__).resolve().parents[1] / "static" / "teaching.js").read_text(encoding="utf-8")


class CourseCardPrimaryActionTests(unittest.TestCase):
    def test_single_state_driven_primary_button(self):
        self.assertIn("function teachingPrimaryAction(", JS)
        for label in ("開始閱讀", "繼續閱讀（", "前往考試", "未通過｜複習第", "已完成"):
            self.assertIn(label, JS)
        self.assertIn("${primaryAction}", JS)

    def test_old_ungated_exam_copy_is_gone(self):
        self.assertNotIn("看完教材即可直接考核，不需先按完成標記", JS)


if __name__ == "__main__":
    unittest.main()


class CourseStepListTests(unittest.TestCase):
    def test_only_current_step_opens_by_default_and_choice_is_remembered(self):
        self.assertIn("function teachingStepWrap(", JS)
        self.assertIn("teachingStepChoice", JS)
        self.assertIn("teachingStepWrap(course.id, m.id,", JS)
        self.assertIn("Boolean(next && next.id === m.id)", JS)
        self.assertIn("function teachingExamStep(", JS)


class ResumeCardTests(unittest.TestCase):
    def test_resume_card_uses_last_viewed_and_seeds_bookmark(self):
        self.assertIn("async function teachingLoadResume(", JS)
        self.assertIn("lastViewedAt", JS)
        self.assertIn("data-material-resume", JS)
        self.assertIn("teachingBookmarkKey(button.dataset.materialResume)", JS)

    def test_progress_api_exposes_last_viewed_at(self):
        src = (Path(__file__).resolve().parents[1] / "teacher_app" / "learning" / "routes.py").read_text(encoding="utf-8")
        self.assertIn('"lastViewedAt": str(data.get("last_viewed_at") or "")', src)


class HomeResumeTests(unittest.TestCase):
    def test_home_card_links_to_learning_center_with_resume_param(self):
        nav = (Path(__file__).resolve().parents[1] / "static" / "portal-navigation-73.js").read_text(encoding="utf-8")
        self.assertIn("&resume=${encodeURIComponent(item.materialId)}", nav)
        self.assertIn("location.pathname!=='/'", nav)

    def test_learning_center_auto_opens_resume_material_once(self):
        self.assertIn("function teachingAutoResume(", JS)
        self.assertIn("params.get('resume')", JS)
        self.assertIn("history.replaceState", JS)

    def test_progress_payload_carries_title_and_scope(self):
        src = (Path(__file__).resolve().parents[1] / "teacher_app" / "learning" / "routes.py").read_text(encoding="utf-8")
        self.assertIn('"materialTitle"', src)


class ReaderBreadcrumbTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1] / "static"

    def test_breadcrumb_shows_course_material_and_page(self):
        js = (self.ROOT / "system-learner.js").read_text(encoding="utf-8")
        html = (self.ROOT / "system.html").read_text(encoding="utf-8")
        self.assertIn('id="reader-breadcrumb"', html)
        self.assertIn("function paintReaderBreadcrumb(", js)
        self.assertIn("paintReaderBreadcrumb(total);", js)
        self.assertIn("function readerGoToCourse(", js)
        self.assertIn("aria-current=\"page\"", js)


class ExamPhoneLayoutTests(unittest.TestCase):
    JS_EXAM = (Path(__file__).resolve().parents[1] / "static" / "system-exam.js").read_text(encoding="utf-8")

    def test_one_question_per_page_progress_and_unanswered_list(self):
        for needle in ("function applyExamPaging(", "function showExamPage(", "exam-pager-label",
                       "第 ${examPagedIndex + 1} / ${total} 題", "function askUnansweredBeforeSubmit(",
                       "applyExamPaging();updateQuickJumpButtons();"):
            self.assertIn(needle, self.JS_EXAM)
        self.assertNotIn("尚有 ${unanswered} 題未作答，確定要直接提交", self.JS_EXAM)


class ExamResultPageTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1] / "static"

    def test_score_comes_before_report_title_and_wrong_list_has_review_jumps(self):
        html = (self.ROOT / "system.html").read_text(encoding="utf-8")
        self.assertLess(html.index('id="final-score-text"'), html.index("測驗成績結算報告"))
        js = (self.ROOT / "system-exam.js").read_text(encoding="utf-8")
        self.assertIn("function renderWrongQuestionList(", js)
        self.assertIn("前往第 ${Number(source.page)} 頁複習", js)
        self.assertIn("renderExamRemediation(result.remediation||null);\n    renderWrongQuestionList();", js.replace("\r\n", "\n"))


class SkeletonAndHumanErrorTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1] / "static"

    def test_shared_helpers_exist(self):
        api = (self.ROOT / "api-client.js").read_text(encoding="utf-8")
        for name in ("function skeletonBlocks(", "function skeletonRows(", "function humanError("):
            self.assertIn(name, api)
        self.assertIn("恢復連線後會自動補送", api)

    def test_course_list_and_grade_table_use_skeletons_and_plain_errors(self):
        learner = (self.ROOT / "system-learner.js").read_text(encoding="utf-8")
        results = (self.ROOT / "admin-results-data.js").read_text(encoding="utf-8")
        self.assertIn("skeletonBlocks", learner)
        self.assertIn("humanError", learner)
        self.assertIn("skeletonRows", results)
        self.assertIn("humanError", results)
        self.assertIn("重新載入", results)

    def test_unsent_reading_progress_is_kept_when_network_fails(self):
        js = (self.ROOT / "smart-learning-67.js").read_text(encoding="utf-8")
        self.assertIn("if(result===null)", js)
