import io
import unittest
import zipfile

from upload_hardening import _magic_ok, _validate_zip_bytes
from teacher_app.materials.validation import normalize_material_filename, validate_zip_source


class _NoReadAllBytesIO(io.BytesIO):
    def read(self, size=-1):
        if size < 0:
            raise AssertionError('archive validator attempted an unbounded read')
        return super().read(size)


class UploadHardeningTests(unittest.TestCase):
    def test_filename_normalizes_nfc_strips_paths_and_controls(self):
        filename, ext = normalize_material_filename("..\\unsafe/path/e\u0301vil\x00\u202epdf.pdf")
        self.assertEqual(filename, "évilpdf.pdf")
        self.assertEqual(ext, ".pdf")

    def test_filename_rejects_svg_macro_office_and_excessive_length(self):
        for filename in ("diagram.svg", "lesson.docm", "sheet.xlsm", "slides.pptm"):
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                normalize_material_filename(filename)
        with self.assertRaisesRegex(ValueError, "過長"):
            normalize_material_filename("a" * 181 + ".pdf")

    def test_pdf_signature(self):
        self.assertTrue(_magic_ok('.pdf', b'%PDF-1.7\n'))
        self.assertFalse(_magic_ok('.pdf', b'not-a-pdf'))

    def test_docx_requires_document_xml(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('word/document.xml', '<w:document/>')
        _validate_zip_bytes(buf.getvalue(), '.docx')

    def test_docx_rejects_wrong_zip_structure(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('random.txt', 'x')
        with self.assertRaises(ValueError):
            _validate_zip_bytes(buf.getvalue(), '.docx')

    def test_docx_rejects_embedded_vba_payload(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('word/document.xml', '<w:document/>')
            zf.writestr('word/vbaProject.bin', b'macro')
        with self.assertRaisesRegex(ValueError, 'VBA'):
            _validate_zip_bytes(buf.getvalue(), '.docx')

    def test_zip_rejects_blocked_embedded_file_types(self):
        for filename in ('diagram.svg', 'macro.xlsm'):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(filename, b'x')
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                _validate_zip_bytes(buf.getvalue(), '.zip')

    def test_zip_rejects_traversal(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('../evil.txt', 'x')
        with self.assertRaises(ValueError):
            _validate_zip_bytes(buf.getvalue(), '.zip')

    def test_zip_file_like_validation_does_not_read_entire_stream(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('word/document.xml', '<w:document/>')
            zf.writestr('word/media/image.bin', bytes(range(256)) * 16)
        validate_zip_source(_NoReadAllBytesIO(buf.getvalue()), '.docx')


if __name__ == '__main__':
    unittest.main()
