"""Adding files to an existing course must not send a made-up bundle workflow id (server answers 409)."""
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1].joinpath("static", "course-wizard-681.js").read_text(encoding="utf-8")


class AddFilesTests(unittest.TestCase):
    def test_add_files_uses_plain_upload(self):
        start = SRC.index("async function addFilesToCourse()")
        body = SRC[start:start + 1600]
        self.assertNotIn("newWorkflowId()", body)
        self.assertIn("workflowId:''", body)

    def test_bundle_fields_only_sent_with_a_workflow(self):
        start = SRC.index("function buildUploadForm(")
        body = SRC[start:start + 1400]
        self.assertIn("if(workflowId){", body)
        self.assertIn("form.append('bundleWorkflowId',workflowId);", body)


if __name__ == "__main__":
    unittest.main()
