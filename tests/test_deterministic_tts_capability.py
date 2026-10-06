import os
import unittest
from unittest.mock import patch
from teacher_app.testing.deterministic_ai_provider import tts_capabilities


class TestCapability(unittest.TestCase):
    def test_requires_both_flags_and_preserves_production(self):
        original = {"kokoro": {"available": False}, "tts": {"provider": "kokoro-local"}}
        for test_mode, stub in [("0", "0"), ("1", "0"), ("0", "1")]:
            with patch.dict(os.environ, TEACHER_E2E_TEST_MODE=test_mode, TEACHER_E2E_DETERMINISTIC_STUBS=stub):
                self.assertIs(tts_capabilities(original), original)
        with patch.dict(os.environ, TEACHER_E2E_TEST_MODE="1", TEACHER_E2E_DETERMINISTIC_STUBS="1"):
            result = tts_capabilities(original)
            self.assertTrue(result["kokoro"]["available"])
            self.assertEqual(result["tts"]["inferenceMode"], "deterministic-e2e")
            self.assertFalse(original["kokoro"]["available"])
