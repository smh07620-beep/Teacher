"""Compatibility module alias for the packaged legacy Flask host.

Production composition now lives in :mod:`teacher_app.factory`.  Keeping this
module alias preserves historical ``import app`` callers and test monkeypatches
while ensuring the root file owns no database, provider, or business logic.
"""

import sys

from teacher_app import legacy_host as _legacy_host


sys.modules[__name__] = _legacy_host
