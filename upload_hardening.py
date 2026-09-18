"""Compatibility module alias for canonical upload security routes."""
import sys

from teacher_app.materials import upload_routes as _routes
from teacher_app.materials import validation as _validation


for _name in (
    "IMAGE_EXT", "MEDIA_EXT", "OLE_EXT", "PDF_EXT", "TEXT_EXT", "ZIP_EXT",
    "_magic_ok", "_validate_zip_bytes", "validate_filestorage",
):
    setattr(_routes, _name, getattr(_validation, _name))

sys.modules[__name__] = _routes
