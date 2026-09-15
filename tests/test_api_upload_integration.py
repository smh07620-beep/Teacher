import io
import os
import unittest
import zipfile
from unittest.mock import patch

from flask import Flask, jsonify

import upload_hardening


def make_zip(files):
    buffer = io.BytesIO()

    with zipfile.ZipFile(
        buffer,
        "w",
        zipfile.ZIP_DEFLATED,
    ) as zf:
        for name, body in files.items():
            zf.writestr(
                name,
                body,
            )

    return buffer.getvalue()


class UploadApiIntegrationTests(
    unittest.TestCase
):
    def setUp(self):
        self.app = Flask(
            __name__
        )

        self.app.config.update(
            TESTING=True,
        )

        class Base:
            pass

        self.base = Base()
        self.base.app = self.app

        upload_hardening.register_upload_hardening(
            self.base
        )

        @self.app.post(
            "/upload-test"
        )
        def upload_test():
            return jsonify(
                {"ok": True}
            )

        self.client = (
            self.app.test_client()
        )

    def upload(
        self,
        raw,
        filename,
    ):
        return self.client.post(
            "/upload-test",
            data={
                "file": (
                    io.BytesIO(raw),
                    filename,
                )
            },
            content_type=(
                "multipart/form-data"
            ),
        )

    def test_fake_pdf_is_rejected(self):
        response = self.upload(
            b"this is not pdf",
            "fake.pdf",
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertIn(
            "副檔名不符",
            response.get_json()[
                "error"
            ],
        )

    def test_fake_docx_is_rejected(self):
        response = self.upload(
            b"PK\x03\x04"
            b"not-a-real-zip",
            "fake.docx",
        )

        self.assertEqual(
            response.status_code,
            400,
        )

    def test_fake_xlsx_structure_is_rejected(self):
        raw = make_zip(
            {
                "docProps/core.xml":
                    b"<xml/>",
            }
        )

        response = self.upload(
            raw,
            "fake.xlsx",
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertIn(
            "XLSX",
            response.get_json()[
                "error"
            ],
        )

    def test_zip_path_traversal_is_rejected(self):
        raw = make_zip(
            {
                "../outside.txt":
                    b"bad",
                "normal.txt":
                    b"ok",
            }
        )

        response = self.upload(
            raw,
            "unsafe.zip",
        )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertIn(
            "不安全路徑",
            response.get_json()[
                "error"
            ],
        )

    def test_high_compression_ratio_is_rejected(self):
        raw = make_zip(
            {
                "huge.txt":
                    b"A" * 200_000,
            }
        )

        with patch.dict(
            os.environ,
            {
                "UPLOAD_ZIP_MAX_RATIO":
                    "10",
            },
        ):
            response = self.upload(
                raw,
                "bomb.zip",
            )

        self.assertEqual(
            response.status_code,
            400,
        )

        self.assertIn(
            "ZIP bomb",
            response.get_json()[
                "error"
            ],
        )

    def test_valid_minimal_pdf_passes_validator(self):
        response = self.upload(
            (
                b"%PDF-1.4\n"
                b"1 0 obj\n"
                b"<<>>\n"
                b"endobj\n"
                b"%%EOF\n"
            ),
            "valid.pdf",
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.get_json(),
            {"ok": True},
        )

    def test_valid_minimal_docx_structure_passes_validator(self):
        raw = make_zip(
            {
                "word/document.xml":
                    b"<document/>",
            }
        )

        response = self.upload(
            raw,
            "valid.docx",
        )

        self.assertEqual(
            response.status_code,
            200,
            response.get_data(
                as_text=True
            ),
        )

        self.assertEqual(
            response.get_json(),
            {"ok": True},
        )


if __name__ == "__main__":
    unittest.main()
