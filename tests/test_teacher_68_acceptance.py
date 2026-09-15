"""Teacher 6.8 acceptance regressions; these cover new release behavior."""
import unittest
from pathlib import Path

from external_media_68 import validate_external_url
from question_bank_68 import _draw
from smart_learning_67 import media_completion, resolved_completion


class MediaCompletion68Tests(unittest.TestCase):
    def test_seek_to_end_and_client_completed_cannot_bypass_coverage(self):
        self.assertFalse(media_completion(100, [9]))  # seek only
        self.assertFalse(resolved_completion(100, [9], True, True))
        self.assertTrue(resolved_completion(0, [], True, False))  # legacy document
        self.assertFalse(media_completion(100, list(range(8))))
        self.assertTrue(media_completion(100, list(range(9))))


class BlueprintQuota68Tests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"id":"a","topic":"A","difficulty":"easy","cognitive_level":"apply"},
            {"id":"b","topic":"A","difficulty":"hard","cognitive_level":"analyze"},
            {"id":"c","topic":"B","difficulty":"medium","cognitive_level":"apply"},
            {"id":"d","topic":"B","difficulty":"medium","cognitive_level":"understand"},
        ]
        self.quotas={"topic":{"A":2,"B":1},"difficulty":{"easy":1,"hard":1,"medium":1},"cognitive_level":{"apply":2,"analyze":1}}

    def test_cross_dimensional_quotas_and_exact_count(self):
        chosen=_draw(self.rows,3,self.quotas)
        self.assertEqual(len(chosen),3)
        self.assertEqual(sum(q["topic"]=="A" for q in chosen),2)
        self.assertEqual(sum(q["difficulty"]=="medium" for q in chosen),1)
        self.assertEqual(sum(q["cognitive_level"]=="apply" for q in chosen),2)

    def test_impossible_and_excluded_recent_are_refused(self):
        with self.assertRaises(ValueError): _draw(self.rows,3,{"topic":{"A":3}})
        with self.assertRaises(ValueError): _draw(self.rows,3,self.quotas,{"b"})


class ExternalAndElevation68Tests(unittest.TestCase):
    def test_youtube_shorts_is_canonicalized(self):
        item=validate_external_url("https://www.youtube.com/shorts/dQw4w9WgXcQ")
        self.assertEqual(item,{"provider":"youtube","canonicalUrl":"https://www.youtube.com/watch?v=dQw4w9WgXcQ","videoId":"dQw4w9WgXcQ"})

    def test_single_flight_never_persists_secret(self):
        source=Path(__file__).parents[1].joinpath("static","admin-elevation-68.js").read_text(encoding="utf-8")
        self.assertIn("let inFlight",source)
        self.assertIn("finally(() => { inFlight = null; })",source)
        self.assertNotIn("localStorage",source)
        self.assertNotIn("sessionStorage",source)
        legacy=Path(__file__).parents[1].joinpath("static","system-admin.js").read_text(encoding="utf-8")
        self.assertIn("window.adminElevationFlight",legacy)
        self.assertIn("/api/admin/elevation",legacy)
        self.assertNotIn("sessionStorage.setItem('admin_key'",legacy)
