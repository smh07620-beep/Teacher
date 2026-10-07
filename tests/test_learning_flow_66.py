import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class LearningFlow66Tests(
    unittest.TestCase
):
    def source(self, rel):
        return ROOT.joinpath(
            rel
        ).read_text(
            encoding="utf-8"
        )

    def test_reader_next_unlocks_immediately_after_completion(self):
        source = self.source(
            "static/teaching.js"
        )

        for marker in (
            "Teacher 6.6 M3 · sequential reader unlock",
            "teacher66SyncReaderNext",
            "teacher66CurrentMaterialDone",
            "不再強制完成標記才解鎖",
            "下一份教材 →",
            "requestAnimationFrame",
        ):
            self.assertIn(
                marker,
                source,
            )

        self.assertIn(
            "currentDone",
            source,
        )

        self.assertIn(
            "!currentDone",
            source,
        )

    def test_material_completion_has_one_canonical_writer(self):
        learner = self.source("static/system-learner.js")
        teaching = self.source("static/teaching.js")
        self.assertEqual(learner.count("fetch('/api/material-progress'"), 1)
        self.assertNotIn("fetch('/api/material-progress'", teaching)
        self.assertIn("window.LearnerMaterialProgress = Object.freeze", learner)
        self.assertIn("window.LearnerMaterialProgress?.complete", teaching)
        self.assertIn("return true;", learner)
        self.assertIn("return false;", learner)

    def test_teaching_completion_wrapper_only_adds_identity_and_reader_sync(self):
        source = self.source("static/teaching.js")
        start = source.index("const teacher66OriginalMarkComplete")
        end = source.index("const teacher66OriginalNextMaterial", start)
        wrapper = source[start:end]
        self.assertIn("teachingSetIdentityFields(", wrapper)
        self.assertIn("teacher66SyncReaderNext", wrapper)
        self.assertIn("requestAnimationFrame", wrapper)
        self.assertNotIn("/api/material-progress", wrapper)

    def test_course_overview_has_one_global_owner_and_a_registered_presenter(self):
        learner = self.source("static/system-learner.js")
        teaching = self.source("static/teaching.js")
        self.assertIn("function renderCourseOverview()", learner)
        self.assertIn("function renderCourseOverviewBase()", learner)
        self.assertIn("window.LearnerCourseOverview = Object.freeze", learner)
        self.assertNotIn("function renderCourseOverview() {", teaching)
        self.assertIn("function renderTeachingCourseOverview()", teaching)
        self.assertIn("window.TeachingCourseOverview66 = Object.freeze", teaching)

    def test_teaching_course_presenter_runs_shared_learner_finalizer(self):
        source = self.source("static/teaching.js")
        start = source.index("function renderTeachingCourseOverview()")
        end = source.index("window.TeachingCourseOverview66 = Object.freeze", start)
        presenter = source[start:end]
        self.assertIn("LearnerCourseOverview?.ensureSupportData?.()", presenter)
        self.assertIn("LearnerCourseOverview?.finalize?.(grid, courses)", presenter)
        self.assertIn("learning-search", presenter)
        self.assertIn("learning-filter", presenter)
        self.assertIn("learningObjectives", presenter)

    def test_course_overview_base_fails_closed_to_current_area(self):
        learner = self.source("static/system-learner.js")
        start = learner.index("function renderCourseOverviewBase()")
        end = learner.index("function renderCourseOverview()", start)
        base = learner[start:end]
        self.assertIn("(m.area||currentTrainingArea)===currentTrainingArea", base)
        self.assertIn("(c.area||currentTrainingArea)===currentTrainingArea", base)

    def test_empty_exam_has_explicit_not_ready_state(self):
        source = self.source(
            "static/teaching.js"
        )

        for marker in (
            "Teacher 6.6 M3 · empty exam guard",
            "teacher66ShowEmptyExam",
            "此考卷尚待題庫建置",
            "尚待題庫建置・目前 0 題",
            "data-empty-exam",
            "data-exam-not-ready",
        ):
            self.assertIn(
                marker,
                source,
            )

        self.assertIn(
            "if (bank === 0)",
            source,
        )

        self.assertIn(
            "loaded.questions.length",
            source,
        )

    def test_m3_teaching_asset_is_cache_busted(self):
        html = self.source(
            "static/system.html"
        )

        self.assertIn(
            "teaching.js?v=6603",
            html,
        )

        # Preserve M2 direct-exam asset.
        self.assertIn(
            "system-exam.js?v=8500",
            html,
        )


if __name__ == "__main__":
    unittest.main()
