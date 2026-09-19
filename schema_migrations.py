"""Compatibility module alias for canonical maintenance migrations."""
import sys

from teacher_app.maintenance import migrations as _migrations


sys.modules[__name__] = _migrations
