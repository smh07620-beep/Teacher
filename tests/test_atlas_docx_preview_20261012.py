"""DOCX -> Atlas preview: text boxes are read once, and each picture gets a thumbnail."""
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

from teacher_app.atlas import importer

NS = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
    'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
    'xmlns:v="urn:schemas-microsoft-com:vml"'
)


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (200, 40, 40)).save(buf, "PNG")
    return buf.getvalue()


def _textbox(*lines):
    paragraphs = "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in lines)
    return f"<w:txbxContent>{paragraphs}</w:txbxContent>"


def _docx(tmp):
    # Word writes every text box twice: mc:Choice (modern) and mc:Fallback (VML).
    box = (
        "<mc:AlternateContent><mc:Choice><wps:wsp><wps:txbx>"
        + _textbox("A：Fiber", "B：Ca-oxalate")
        + "</wps:txbx></wps:wsp></mc:Choice><mc:Fallback><w:pict><v:textbox>"
        + _textbox("A：Fiber", "B：Ca-oxalate")
        + "</v:textbox></w:pict></mc:Fallback></mc:AlternateContent>"
    )
    picture = (
        '<w:drawing><wp:inline><a:graphic><a:graphicData><a:blip r:embed="rId9"/>'
        "</a:graphicData></a:graphic></wp:inline></w:drawing>"
    )
    document = (
        f'<?xml version="1.0" encoding="UTF-8"?><w:document {NS}><w:body>'
        f"<w:p><w:r>{picture}</w:r><w:r>{box}</w:r></w:p></w:body></w:document>"
    )
    rels = (
        '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId9" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        'Target="media/image1.png"/></Relationships>'
    )
    path = Path(tmp) / "boxes.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", document)
        archive.writestr("word/_rels/document.xml.rels", rels)
        archive.writestr("word/media/image1.png", _png())
    return path


class DocxPreviewTests(unittest.TestCase):
    def test_text_box_is_read_once_and_lines_are_separated(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = importer.preview_docx_atlas(_docx(tmp))
        item = result["images"][0]
        self.assertEqual(item["caption"], "A：Fiber B：Ca-oxalate")

    def test_every_picture_gets_a_small_jpeg_thumbnail(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = importer.preview_docx_atlas(_docx(tmp))
        thumb = result["images"][0]["thumbnail"]
        self.assertTrue(thumb.startswith("data:image/jpeg;base64,"))
        self.assertLess(len(thumb), 60_000)

    def test_wizard_shows_the_thumbnail(self):
        src = (Path(__file__).resolve().parents[1] / "static" / "atlas-docx-wizard-70.js").read_text(encoding="utf-8")
        self.assertIn("item.thumbnail", src)



class PlainLanguageWizardTests(unittest.TestCase):
    """Teachers are not engineers: no raw codes or developer words in the wizard."""

    SRC = (Path(__file__).resolve().parents[1] / "static" / "atlas-docx-wizard-70.js").read_text(encoding="utf-8")

    def test_no_developer_words_in_teacher_text(self):
        for word in ("圖片 metadata", "共用 metadata", "覆寫", "DOCX → Atlas", "inline", "SmartArt", "OLE", "Atlas 草稿"):
            with self.subTest(word=word):
                self.assertNotIn(word, self.SRC)

    def test_every_field_has_a_visible_label_not_only_a_placeholder(self):
        for text in ("圖片名稱", "圖片類型", "難易度", "排列順序", "關鍵字", "圖片說明", "辨別重點", "教學提醒"):
            with self.subTest(text=text):
                self.assertIn(text, self.SRC)
        self.assertNotIn("placeholder=", self.SRC)

    def test_group_key_is_not_shown_to_teachers(self):
        self.assertIn('type="hidden" name="${prefix}group"', self.SRC)


if __name__ == "__main__":
    unittest.main()
