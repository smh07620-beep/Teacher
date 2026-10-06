import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MaterialReaderModes20261006Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.learner = ROOT.joinpath("static", "system-learner.js").read_text(encoding="utf-8")
        cls.css = ROOT.joinpath("static", "learner.css").read_text(encoding="utf-8")

    def test_powerpoint_preview_is_detected_as_presentation_reader(self):
        self.assertIn("function inferPdfReaderMode(entry = {})", self.learner)
        self.assertIn("/\\.(ppt|pptx|pps|ppsx|odp)$/", self.learner)
        self.assertIn("meta.derivativeType", self.learner)
        self.assertIn("entry.sourcePresentationId", self.learner)
        self.assertIn("readerMode: inferPdfReaderMode(entry)", self.learner)

    def test_presentation_contract_wins_over_generic_pdf_hint(self):
        presentation_hint = self.learner.index("['presentation', 'slides', 'powerpoint'")
        document_hint = self.learner.index("['document', 'continuous', 'pdf', 'sop']")
        self.assertLess(presentation_hint, document_hint)
        self.assertIn("window.goToSlidePage = goToSlidePage", self.learner)
        self.assertIn("window.slideViewerPrev = slideViewerPrev", self.learner)
        self.assertIn("window.slideViewerNext = slideViewerNext", self.learner)
        self.assertIn("window.slideViewerState = slideViewerState", self.learner)
        self.assertIn("window.cachedSlidesList = cachedSlidesList", self.learner)

    def test_presentation_pdf_is_page_fit_and_wheel_cannot_scroll_native_pdf(self):
        block = self.learner[
            self.learner.index("function updateSlideViewerPdf()"):
            self.learner.index("function updateSlideViewerImage()")
        ]
        self.assertIn("reader_page=${page}", block)
        self.assertIn("swapPresentationPdfFrame(wanted,page)", block)
        self.assertIn("scrollbar=0&view=Fit", block)
        self.assertIn("scrollbar=1&view=FitH", block)
        self.assertIn("initPdfPresentationWheel()", self.learner)
        self.assertIn("presentation-preview-mode", self.learner)
        self.assertIn(".presentation-preview-mode #slide-viewer-pdf", self.css)
        self.assertIn("pointer-events:none", self.css)
        paging = self.learner[self.learner.index("function goToSlidePage"):self.learner.index("function closeSlideViewer")]
        self.assertIn("renderSlideThumbs();", paging)
        swap = self.learner[self.learner.index("function swapPresentationPdfFrame"):self.learner.index("function updateSlideViewerPdf")]
        self.assertIn("incoming.style.opacity='0'", swap)
        self.assertIn("window.setTimeout", swap)
        self.assertIn("incoming.id='slide-viewer-pdf'", swap)

    def test_document_pdf_keeps_continuous_scroll_mode(self):
        self.assertIn("document-preview-mode", self.learner)
        self.assertIn("文件模式・可上下捲動閱讀", self.learner)
        self.assertIn(".document-preview-mode #slide-viewer-pdf", self.css)
        self.assertIn("pointer-events:auto", self.css)

    def test_material_titles_do_not_collapse_when_layout_is_narrow(self):
        self.assertIn("material-card-title", self.learner)
        self.assertIn("course-material-title", self.learner)
        self.assertIn("#slides-grid{", self.css.replace("\n", ""))
        self.assertIn("repeat(auto-fit,minmax(min(100%,22rem),1fr))", self.css)
        self.assertIn("text-size-adjust:100%", self.css)
        self.assertIn("course-material-row .course-row-actions", self.css)


if __name__ == "__main__":
    unittest.main()
