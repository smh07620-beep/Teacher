"""Per-slide AI narration, Taiwan wording and the pronunciation table (2026-10-10)."""
import io
import json
import shutil
import subprocess
import sys
import textwrap
import unittest
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from teacher_app.materials import media_audio_runtime as runtime  # noqa: E402
from teacher_app.materials import service as material_service  # noqa: E402
from teacher_app.materials import tts_text  # noqa: E402


def make_wav(seconds: float, rate: int = 24000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x01\x00" * int(rate * seconds))
    return buffer.getvalue()


class SplitSegmentsTests(unittest.TestCase):
    def test_one_segment_per_paragraph_and_review_note_is_not_spoken(self):
        body = "第一張的講解。\n接著第二句。\n\n第二張的講解。\n\n※ 本講稿需由授課教師確認後方可用於正式教學影音。"
        self.assertEqual(tts_text.split_script_segments(body), ["第一張的講解。 接著第二句。", "第二張的講解。"])

    def test_placeholder_paragraph_keeps_its_slide_but_is_silent(self):
        body = "甲。\n\n【需教師補充】\n\n丙。"
        self.assertEqual(tts_text.split_script_segments(body), ["甲。", "", "丙。"])

    def test_windows_newlines_are_handled(self):
        self.assertEqual(tts_text.split_script_segments("甲。\r\n\r\n乙。"), ["甲。", "乙。"])


class PronunciationAndWordingTests(unittest.TestCase):
    def test_abbreviations_units_and_symbols_are_spoken_as_words(self):
        spoken = tts_text.apply_pronunciation("HbA1c 5.7% 以上，單位 mg/dL；37°C 下 PT 與 aPTT；IU/L。")
        self.assertIn("糖化血色素", spoken)
        self.assertIn("百分之5.7", spoken)
        self.assertIn("毫克每分升", spoken)
        self.assertIn("攝氏37度", spoken)
        self.assertIn("凝血酶原時間", spoken)
        self.assertIn("活化部分凝血活酶時間", spoken)
        self.assertIn("國際單位每公升", spoken)
        self.assertNotIn("%", spoken)

    def test_abbreviations_inside_other_words_are_left_alone(self):
        self.assertEqual(tts_text.apply_pronunciation("OPTIMAL 與 PTX"), "OPTIMAL 與 PTX")

    def test_standard_number_is_read_digit_by_digit(self):
        self.assertIn("一五一八九", tts_text.apply_pronunciation("依 ISO 15189 辦理"))

    def test_display_text_is_not_changed_by_pronunciation(self):
        # The helper returns a new string; the stored script keeps the original wording.
        original = "HbA1c 為 6.5%"
        tts_text.apply_pronunciation(original)
        self.assertEqual(original, "HbA1c 為 6.5%")

    def test_table_file_is_valid_and_every_rule_compiles(self):
        table = json.loads(tts_text.TABLE_PATH.read_text(encoding="utf-8"))
        self.assertTrue(table["terms"])
        for rule in table["terms"]:
            self.assertTrue(rule["match"] and rule["say"], rule)
        regex_rules, term_pattern, terms = tts_text._compiled_table()
        self.assertEqual(len(regex_rules), len(table["regex"]))
        self.assertIsNotNone(term_pattern)
        self.assertEqual(len(terms), len({rule["match"] for rule in table["terms"]}))

    def test_taiwan_wording_replaces_only_unambiguous_mainland_terms(self):
        self.assertEqual(
            tts_text.apply_taiwan_terms("室內質控與信息系統、網絡軟件，質量管理"),
            "內部品質管制與資訊系統、網路軟體，品質管理",
        )
        # Ambiguous words stay as the teacher wrote them.
        self.assertEqual(tts_text.apply_taiwan_terms("質譜儀測量質量與樣本"), "質譜儀測量質量與樣本")


class BuildSegmentedWavTests(unittest.TestCase):
    def test_timeline_matches_audio_and_keeps_a_gap_between_slides(self):
        durations = {"甲": 1.0, "乙": 2.0}
        wav_bytes, segments = runtime.build_segmented_wav(["甲", "乙"], lambda text: make_wav(durations[text]), gap_ms=400)
        self.assertEqual(segments, [
            {"page": 0, "startMs": 0, "endMs": 1000},
            {"page": 1, "startMs": 1400, "endMs": 3400},
        ])
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
            self.assertAlmostEqual(wav.getnframes() / wav.getframerate(), 3.4, places=2)

    def test_empty_paragraph_keeps_page_without_audio(self):
        _wav, segments = runtime.build_segmented_wav(["甲", "", "丙"], lambda text: make_wav(1.0), gap_ms=400)
        self.assertEqual([item["page"] for item in segments], [0, 1, 2])
        self.assertEqual(segments[1]["startMs"], segments[1]["endMs"])
        self.assertEqual(segments[2]["startMs"], 1400)

    def test_all_empty_is_an_error(self):
        with self.assertRaises(RuntimeError):
            runtime.build_segmented_wav(["", ""], lambda text: make_wav(1.0))

    def test_mismatched_audio_format_is_rejected(self):
        pieces = iter([make_wav(1.0, 24000), make_wav(1.0, 16000)])
        with self.assertRaises(RuntimeError):
            runtime.build_segmented_wav(["甲", "乙"], lambda text: next(pieces))


class SegmentPlanTests(unittest.TestCase):
    def test_split_per_slide_only_when_paragraphs_match_page_count(self):
        script = {"body": "甲。\n\n乙。\n\n丙。"}
        self.assertEqual(runtime._segment_plan(script, {"pageCount": 3}), ["甲。", "乙。", "丙。"])
        aligned = runtime._segment_plan(script, {"pageCount": 4})  # mismatch → auto-aligned, still 4 slides
        self.assertEqual(len(aligned), 4)
        self.assertEqual(" ".join(aligned).replace("  ", " ").count("。"), 3)
        self.assertIsNone(runtime._segment_plan(script, {"pageCount": 0}))
        self.assertIsNone(runtime._segment_plan(script, {}))

    def test_mismatch_is_explained_to_the_teacher(self):
        note = runtime._segment_note({"body": "甲。\n\n乙。"}, {"pageCount": 5})
        self.assertIn("2", note)
        self.assertIn("5", note)
        self.assertEqual(runtime._segment_note({"body": "甲。\n\n乙。"}, {"pageCount": 2}), "")


class GenerateAudioIntegrationTests(unittest.TestCase):
    def _run(self, script_body, page_count, current_version=3):
        client = MagicMock()
        stored = {}

        def put_object(**kwargs):
            stored["body"] = kwargs["Body"]

        client.put_object.side_effect = put_object
        spoken = []

        def fake_synth(text, *, voice, instructions):
            spoken.append(text)
            return make_wav(1.0), "Kokoro-test"

        captured = {}

        def fake_insert(entry):
            captured["entry"] = entry
            return entry

        script = {"id": "s1", "status": "approved", "approvedBy": "t", "approvedAt": "2026-10-10", "title": "T", "body": script_body}
        source = {"id": "m1", "title": "教材", "pageCount": page_count, "currentVersion": current_version}
        with patch.object(runtime.providers, "r2_is_configured", return_value=True), \
             patch.object(runtime.providers, "r2_client", return_value=client), \
             patch.object(runtime.material_repository, "get_material", return_value=None), \
             patch.object(runtime, "_existing_r2", return_value=0), \
             patch.object(runtime, "_synthesize", side_effect=fake_synth), \
             patch.object(runtime, "_insert_material_if_missing", side_effect=fake_insert), \
             patch.object(runtime.r2_budget, "reserve_upload"), \
             patch.object(runtime.r2_budget, "release_reservation"), \
             patch.object(runtime.r2_ledger, "record_object"):
            result = runtime.generate_audio(job_id="job1", script=script, source=source, voice="zf_001")
        return result, captured["entry"], stored["body"], spoken

    def test_matching_script_is_split_per_slide_with_timeline_and_pronunciation(self):
        result, entry, wav_bytes, spoken = self._run("看 HbA1c。\n\n看 CBC。\n\n※ 本講稿需由授課教師確認。", 2)
        self.assertTrue(result["segmented"])
        self.assertEqual(result["segmentCount"], 2)
        meta = json.loads(entry["storage_meta"])
        self.assertTrue(meta["segmented"])
        self.assertEqual(meta["sourceVersion"], 3)
        self.assertEqual(meta["segments"], [
            {"page": 0, "startMs": 0, "endMs": 1000},
            {"page": 1, "startMs": 1400, "endMs": 2400},
        ])
        self.assertEqual(meta["durationMs"], 2400)
        self.assertEqual(spoken, ["看 糖化血色素。", "看 全血球計數。"])
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
            self.assertAlmostEqual(wav.getnframes() / wav.getframerate(), 2.4, places=2)

    def test_mismatching_script_is_auto_aligned_to_every_slide(self):
        result, entry, _wav, spoken = self._run("甲甲甲。\n\n乙乙乙。\n\n丙丙丙。", 5)
        self.assertTrue(result["segmented"])
        self.assertEqual(result["segmentCount"], 5)
        self.assertIn("5", result["segmentNote"])
        meta = json.loads(entry["storage_meta"])
        self.assertEqual([seg["page"] for seg in meta["segments"]], [0, 1, 2, 3, 4])


class LearnerPayloadTests(unittest.TestCase):
    def _items(self, meta, current_version=2):
        source = {"id": "m1", "title": "教材", "currentVersion": current_version, "storageMeta": {}}
        audio = {"id": "a1", "title": "AI 語音", "dateAdded": "2026-10-10", "storageMeta": meta}
        return material_service._attach_narrations([source, audio])

    def test_segmented_ai_narration_carries_segments(self):
        meta = {"mediaKind": "ai_narration", "sourceMaterialId": "m1", "segmented": True, "sourceVersion": 2,
                "durationMs": 2400, "segments": [{"page": 0, "startMs": 0, "endMs": 1000}, {"page": 1, "startMs": 1400, "endMs": 2400}]}
        items = self._items(meta)
        self.assertEqual(len(items), 1)
        narration = items[0]["narration"]
        self.assertEqual(narration["kind"], "ai")
        self.assertFalse(narration["stale"])
        self.assertEqual(len(narration["segments"]), 2)

    def test_deck_changed_after_narration_is_marked_stale(self):
        meta = {"mediaKind": "ai_narration", "sourceMaterialId": "m1", "segmented": True, "sourceVersion": 1,
                "segments": [{"page": 0, "startMs": 0, "endMs": 1000}]}
        self.assertTrue(self._items(meta, current_version=2)[0]["narration"]["stale"])

    def test_old_single_track_narration_payload_is_unchanged(self):
        meta = {"mediaKind": "ai_narration", "sourceMaterialId": "m1"}
        narration = self._items(meta)[0]["narration"]
        self.assertNotIn("kind", narration)
        self.assertNotIn("segments", narration)


@unittest.skipUnless(shutil.which("node"), "node is required for the player behaviour test")
class LearnerPlayerBehaviourTests(unittest.TestCase):
    SCRIPT = textwrap.dedent(
        r"""
        const fs = require('fs'), vm = require('vm');
        const code = fs.readFileSync('static/learner-narration-1100.js', 'utf8');
        const intervals = [], audios = [], store = {};
        class FakeAudio {
          constructor(url) { this.url = url; this.currentTime = 0; this.paused = true; this.muted = false; this.readyState = 4; this.plays = 0; this.listeners = {}; audios.push(this); }
          addEventListener(n, f) { (this.listeners[n] = this.listeners[n] || []).push(f); }
          removeAttribute() {}
          play() { this.paused = false; this.plays++; return Promise.resolve(); }
          pause() { this.paused = true; }
        }
        function el() { return { style: {}, setAttribute() {}, addEventListener(n, f) { this.onclick = f; }, appendChild() {}, remove() {}, textContent: '' }; }
        const window = { slideViewerState: { materialId: 'm1', index: 0 }, addEventListener() {}, openMaterial() {}, cachedSlidesList: [] };
        const context = {
          window, console,
          document: { readyState: 'complete', body: { appendChild() {} }, createElement: el, addEventListener() {},
            getElementById: (id) => id === 'slide-viewer-modal' ? { classList: { contains: () => false } } : null },
          localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } },
          Audio: FakeAudio, fetch: () => Promise.resolve({ ok: false }),
          setInterval: (f) => { intervals.push(f); return intervals.length; },
          clearInterval: (id) => { intervals[id - 1] = null; },
          setTimeout: () => 0, clearTimeout() {},
        };
        vm.createContext(context);
        vm.runInContext(code, context);
        const tick = () => intervals.forEach((f) => f && f());
        const out = {};
        function open(narration) {
          window.cachedSlidesList = [{ id: 'm1', narration }];
          window.slideViewerState.index = 0;
          window.openMaterial('m1');
        }
        // 1) segmented narration: stop at the end of each slide, resume only after the page changes
        open({ id: 'a1', kind: 'ai', viewUrl: '/view/a1', stale: false,
               segments: [{ page: 0, startMs: 0, endMs: 2000 }, { page: 1, startMs: 2400, endMs: 5000 }, { page: 2, startMs: 5000, endMs: 5000 }] });
        const a = audios[audios.length - 1];
        tick();
        out.startsOnFirstPage = a.plays === 1 && a.currentTime === 0 && a.paused === false;
        a.currentTime = 2.05; tick();
        out.stopsAtEndOfSlide = a.paused === true;
        const playsAfterStop = a.plays; a.currentTime = 2.2; tick(); tick();
        out.staysStoppedUntilPageChanges = a.paused === true && a.plays === playsAfterStop;
        window.slideViewerState.index = 1; tick();
        out.nextSlidePlaysItsOwnSegment = a.paused === false && Math.abs(a.currentTime - 2.4) < 0.001;
        a.currentTime = 5.0; tick();
        out.stopsAgain = a.paused === true;
        window.slideViewerState.index = 0; tick();
        out.goingBackReplaysThatSlide = a.paused === false && a.currentTime === 0;
        window.slideViewerState.index = 2; tick();
        out.emptySegmentStaysSilent = a.paused === true;
        // 2) muted learner: pages change, nothing plays
        store['teacher.narration.muted'] = '1';
        open({ id: 'a2', kind: 'ai', viewUrl: '/view/a2', stale: false, segments: [{ page: 0, startMs: 0, endMs: 2000 }] });
        const b = audios[audios.length - 1]; tick();
        out.mutedNeverPlays = b.plays === 0;
        store['teacher.narration.muted'] = '0';
        // 3) stale / legacy narration keeps the old whole-track behaviour (plays at once, no per-slide stop)
        open({ id: 'a3', kind: 'ai', viewUrl: '/view/a3', stale: true, segments: [{ page: 0, startMs: 0, endMs: 2000 }] });
        const c = audios[audios.length - 1];
        out.staleStillPlaysWholeTrack = c.plays === 1;
        c.currentTime = 9; tick();
        out.staleIsNotCutOff = c.paused === false;
        open({ id: 'a4', viewUrl: '/view/a4' });
        const d = audios[audios.length - 1];
        out.legacyStillPlays = d.plays === 1;
        // 4) pure helpers
        const api = window.LearnerNarration1100;
        out.helpers = api.isSegmented({ kind: 'ai', segments: [{}] }) === true && api.isSegmented({ kind: 'ai', stale: true, segments: [{}] }) === false
          && api.isSegmented({ kind: 'teacher', segments: [{}] }) === false && api.segmentForPage([{ page: 1, startMs: 1, endMs: 2 }], 1).endMs === 2
          && api.segmentForPage([], 0) === null && api.reachedEnd(2.0, 2000) === true && api.reachedEnd(1.5, 2000) === false;
        console.log(JSON.stringify(out));
        """
    )

    def test_player_stops_after_each_slide_and_waits_for_the_learner_to_turn_the_page(self):
        result = subprocess.run(["node", "-e", self.SCRIPT], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        outcome = json.loads(result.stdout.strip().splitlines()[-1])
        for name, ok in outcome.items():
            self.assertTrue(ok, f"{name} failed: {outcome}")




class HeavyCharPronunciationTests(unittest.TestCase):
    def test_chong_words_use_first_tone_homophone(self):
        from teacher_app.materials import tts_text
        tts_text._compiled_table.cache_clear()
        for word in ("重採", "重抽", "重新", "重來", "重做", "重複", "重測"):
            self.assertEqual(tts_text.apply_pronunciation(word), "蟲" + word[1:], word)

    def test_zhong_words_are_unchanged(self):
        from teacher_app.materials import tts_text
        for word in ("重要", "嚴重", "體重", "重量", "重點", "比重", "重視", "尊重"):
            self.assertEqual(tts_text.apply_pronunciation(word), word, word)


if __name__ == "__main__":
    unittest.main()
