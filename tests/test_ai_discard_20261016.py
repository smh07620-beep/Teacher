"""Immediate discard of unpublished AI decks/videos (shares the 24h purge safety rules)."""
import unittest

from teacher_app.maintenance import retention
from tests.test_retention_20261008 import FRESH, FakeRuntime, RetentionTests


class DiscardTests(RetentionTests):
    # Reuse the fixture only; do not re-run the parent's tests here.
    def test_unpublished_expired_products_are_removed_published_and_fresh_are_kept(self): pass
    def test_deck_behind_a_kept_video_is_not_removed(self): pass

    def test_discard_fresh_draft_deletes_row_and_artifact(self):
        self._pres("p1", "draft", FRESH)
        retention.discard_presentation("p1", storage_runtime=FakeRuntime())
        self.assertEqual(self._count("ai_presentations"), 0)
        self.assertIn("k/p1", self.deleted)

    def test_published_deck_cannot_be_discarded(self):
        self._pres("p1", "published", FRESH)
        with self.assertRaises(retention.DiscardBlocked) as caught:
            retention.discard_presentation("p1", storage_runtime=FakeRuntime())
        self.assertEqual(caught.exception.code, "published")
        self.assertEqual(self._count("ai_presentations"), 1)

    def test_deck_used_by_a_video_is_blocked_until_video_is_discarded(self):
        self._pres("p1", "approved", FRESH)
        self._video("v1", "draft", FRESH, pres="p1")
        with self.assertRaises(retention.DiscardBlocked) as caught:
            retention.discard_presentation("p1", storage_runtime=FakeRuntime())
        self.assertEqual(caught.exception.code, "in_use")
        retention.discard_video("v1", storage_runtime=FakeRuntime())
        retention.discard_presentation("p1", storage_runtime=FakeRuntime())
        self.assertEqual((self._count("ai_presentations"), self._count("ai_presentation_videos")), (0, 0))

    def test_published_video_cannot_be_discarded_and_missing_is_not_found(self):
        self._video("v1", "published", FRESH)
        with self.assertRaises(retention.DiscardBlocked):
            retention.discard_video("v1", storage_runtime=FakeRuntime())
        with self.assertRaises(retention.DiscardBlocked) as caught:
            retention.discard_video("nope", storage_runtime=FakeRuntime())
        self.assertEqual(caught.exception.code, "not_found")


if __name__ == "__main__":
    unittest.main()
