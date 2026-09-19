import unittest
from unittest.mock import patch

from teacher_app.pgy import signing_facade


class PgySigningDispatchConvergenceTests(unittest.TestCase):
    def setUp(self):
        self.teacher = {
            "username": "teacher1",
            "role": "clinical_teacher",
            "roles": ["clinical_teacher"],
        }
        self.admin = {
            "username": "admin1",
            "role": "education_admin",
            "roles": ["education_admin"],
        }

    def test_legacy_teacher_sign_uses_established_canonical_workflow(self):
        payload = {"comment": "legacy"}
        expected = {"id": "a1", "status": "teacher_signed"}
        with patch.object(signing_facade, "get_sign_mode", return_value="legacy"), patch.object(
            signing_facade.pgy_service,
            "teacher_sign_assignment",
            return_value=expected,
        ) as legacy, patch.object(signing_facade.signing, "sign_assignment") as modern:
            result = signing_facade.teacher_sign_assignment(self.teacher, "a1", payload)

        self.assertEqual(result, expected)
        legacy.assert_called_once_with(self.teacher, "a1", payload)
        modern.assert_not_called()

    def test_new_teacher_sign_uses_signing_service(self):
        payload = {"comment": "single"}
        expected = {"id": "a2", "status": "finalized"}
        with patch.object(signing_facade, "get_sign_mode", return_value="single"), patch.object(
            signing_facade.signing,
            "sign_assignment",
            return_value=expected,
        ) as modern, patch.object(signing_facade.pgy_service, "teacher_sign_assignment") as legacy:
            result = signing_facade.teacher_sign_assignment(self.teacher, "a2", payload)

        self.assertEqual(result, expected)
        modern.assert_called_once_with(self.teacher, "a2", payload)
        legacy.assert_not_called()

    def test_legacy_countersign_and_reopen_keep_existing_workflow(self):
        with patch.object(signing_facade, "get_sign_mode", return_value="legacy"), patch.object(
            signing_facade.pgy_service,
            "group_countersign_assignment",
            return_value={"id": "a3"},
        ) as countersign, patch.object(
            signing_facade.pgy_service,
            "reopen_assignment",
            return_value={"id": "a4"},
        ) as reopen:
            signing_facade.countersign_assignment(self.teacher, "a3", {})
            signing_facade.reopen_assignment(self.admin, "a4", {"reason": "修正"})

        countersign.assert_called_once_with(self.teacher, "a3", {})
        reopen.assert_called_once_with(self.admin, "a4", {"reason": "修正"})

    def test_update_without_sign_mode_delegates_unchanged(self):
        payload = {"title": "新版標題"}
        expected = {"id": "a5", "title": "新版標題"}
        with patch.object(
            signing_facade.pgy_service,
            "update_assignment",
            return_value=expected,
        ) as update, patch.object(signing_facade, "update_sign_mode") as sign_mode:
            result = signing_facade.update_assignment(self.admin, "a5", payload)

        self.assertEqual(result, expected)
        update.assert_called_once_with(self.admin, "a5", payload)
        sign_mode.assert_not_called()

    def test_mixed_update_preserves_legacy_fields_before_sign_mode(self):
        payload = {"title": "新版標題", "signMode": "dual"}
        expected = {"id": "a6", "signMode": "dual"}
        calls = []

        def update_side_effect(*args):
            calls.append("legacy-fields")
            return {"id": "a6"}

        def sign_mode_side_effect(*args):
            calls.append("sign-mode")
            return expected

        with patch.object(
            signing_facade.pgy_service,
            "update_assignment",
            side_effect=update_side_effect,
        ) as update, patch.object(
            signing_facade,
            "update_sign_mode",
            side_effect=sign_mode_side_effect,
        ) as sign_mode:
            result = signing_facade.update_assignment(self.admin, "a6", payload)

        self.assertEqual(result, expected)
        self.assertEqual(calls, ["legacy-fields", "sign-mode"])
        update.assert_called_once_with(self.admin, "a6", payload)
        sign_mode.assert_called_once_with(self.admin, "a6", "dual")


if __name__ == "__main__":
    unittest.main()
