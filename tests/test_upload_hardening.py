import io
import unittest
import zipfile

from upload_hardening import _magic_ok, _validate_zip_bytes


class UploadHardeningTests(unittest.TestCase):
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

    def test_zip_rejects_traversal(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('../evil.txt', 'x')
        with self.assertRaises(ValueError):
            _validate_zip_bytes(buf.getvalue(), '.zip')


if __name__ == '__main__':
    unittest.main()
