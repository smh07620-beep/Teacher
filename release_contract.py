"""Single, explicit contract for the currently supported Teacher release."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENTRYPOINT = "pgy_app:app"


def version_file_value() -> str:
    return ROOT.joinpath("VERSION").read_text(encoding="utf-8").strip()


# VERSION is the single SemVer source.  Teacher 7.x module generations do not
# independently bump the formal release version.
RELEASE_VERSION = version_file_value()

# Runtime health and release validation consume this exact schema baseline.
# Keep the tuple ordered by migration/application order, including the distinct
# additive 0067 markers that existing databases may have recorded separately.
REQUIRED_MIGRATIONS = (
    "0064-baseline",
    "0065-architecture",
    "0066-additive-rbac-pgy-signing",
    "0067-smart-learning-content",
    "0067-render-worker-shared-staging",
    "0067-b-free-local-worker",
    "0068-external-interactive-media",
    "0069-user-profile-titles",
    "0070-material-search-and-atlas",
    "0071-pgy-learner-audience",
    "0072-course-bundle-idempotency",
    "0073-course-bundle-followups",
    "0074-assessment-list-indexes",
)

# Backward-compatible singular name used by older release checks.  It now
# means the newest migration required by the current release contract.
REQUIRED_RELEASE_MIGRATION = REQUIRED_MIGRATIONS[-1]
