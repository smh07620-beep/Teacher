import unittest
from pathlib import Path

from teacher_app.auth.self_service import _email
from teacher_app.exams.windows import _parse

class AccountEmailSecurity93Tests(unittest.TestCase):
    def test_email_validation(self):
        self.assertEqual(_email(" USER@example.com "), "user@example.com")
        with self.assertRaises(ValueError):
            _email("not-an-email")

    def test_staff_email_defaults_to_smh_domain(self):
        source=Path(__file__).parents[1].joinpath("teacher_app","maintenance","account_email_migration.py").read_text(encoding="utf-8")
        self.assertIn("@smh.org.tw",source)
        self.assertIn("TRIM(emp_id)",source)
        self.assertIn("TRIM(email) = ''",source)

    def test_exam_window_normalizes_timezone(self):
        self.assertTrue(_parse("2026-09-30T23:59:00+08:00").endswith("+00:00"))

    def test_password_reset_and_account_pages_have_no_inline_handlers(self):
        root=Path(__file__).parents[1]
        for name in ("account.html","reset-password.html"):
            source=root.joinpath("static",name).read_text(encoding="utf-8")
            self.assertNotIn("onclick=",source)
            self.assertNotIn("<script>",source)

    def test_free_render_blueprint_has_no_paid_worker(self):
        root=Path(__file__).parents[1]
        render=root.joinpath("render.yaml").read_text(encoding="utf-8")
        workflow=root.joinpath(".github","workflows","email-reminders.yml").read_text(encoding="utf-8")
        worker=root.joinpath("ai_question_worker.py").read_text(encoding="utf-8")
        self.assertNotIn("type: worker",render)
        self.assertIn("scripts/send_email_reminders.py",workflow)
        self.assertNotIn("run_due_reminders",worker)

    def test_exam_creation_exposes_final_date(self):
        source=Path(__file__).parents[1].joinpath("static","teacher-content-studio-71.js").read_text(encoding="utf-8")
        self.assertIn("teacher77-exam-closes-at",source)
        self.assertIn("/api/exam-windows/",source)

if __name__=="__main__":
    unittest.main()
