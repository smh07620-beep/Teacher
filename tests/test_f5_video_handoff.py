import unittest
from pathlib import Path


ROOT=Path(__file__).parents[1]


class F5VideoHandoffTests(unittest.TestCase):
    def test_approved_presentation_has_direct_video_handoff(self):
        source=ROOT.joinpath("static","teacher-ai-presentation-video-handoff-f5.js").read_text(encoding="utf-8")
        self.assertIn("🎬 製作教學影片",source)
        self.assertIn("teacher-ai-presentation-video-request",source)
        self.assertIn("item.materialId",source)
        self.assertIn("['approved','published']",source)

    def test_media_studio_accepts_exact_presentation_revision(self):
        source=ROOT.joinpath("static","teacher-ai-media-studio-1018.js").read_text(encoding="utf-8")
        self.assertIn("teacher-ai-presentation-video-request",source)
        self.assertIn("select.value=presentationId",source)
        self.assertIn("showMode('video')",source)
        self.assertIn("選擇旁白聲音後即可建立教學影片",source)

    def test_video_runtime_remains_worker_only_kokoro_ffmpeg_pipeline(self):
        source=ROOT.joinpath("teacher_app","materials","ai_video_runtime.py").read_text(encoding="utf-8")
        self.assertIn("_synthesize(narration",source)
        self.assertIn("segments_to_vtt",source)
        self.assertIn("segments_to_srt",source)
        self.assertIn("FFmpeg 合成 MP4",source)
        self.assertIn("storage.store(",source)


if __name__=="__main__":
    unittest.main()
