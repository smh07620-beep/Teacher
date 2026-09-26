"""Single, explicit contract for the currently supported Teacher release."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENTRYPOINT = "pgy_app:app"


def version_file_value() -> str:
    return ROOT.joinpath("VERSION").read_text(encoding="utf-8").strip()


# VERSION is the single SemVer source.  Teacher 7.x module generations do not
# independently bump the formal release version.  The current repository has
# internal UI/convergence work through the 7.9 / RC79 generation; that label is
# intentionally distinct from the deployable SemVer contract.
RELEASE_VERSION = version_file_value()
INTERNAL_GENERATION = "7.9 / RC79"

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
    "0067-r2-free-budget-guard",
    "0068-external-interactive-media",
    "0069-user-profile-titles",
    "0070-material-search-and-atlas",
    "0071-pgy-learner-audience",
    "0072-course-bundle-idempotency",
    "0073-course-bundle-followups",
    "0074-assessment-list-indexes",
    "0075-ai-question-jobs",
    "0076-assessment-reviewer-identity",
    "0077-general-audit-events",
    "0078-item-analytics-metrics",
    "0079-provider-publish-receipts",
    "0080-external-media-verification",
    "0081-question-version-history",
    "0082-version-aware-item-analytics",
    "0083-learning-assignments",
    "0084-material-version-retraining",
    "0086-notification-read-state",
    "0087-course-feedback",
    "0088-saved-learning-items",
    "0090-completion-certificates",
)

# Backward-compatible singular name used by older release checks.  It now
# means the newest migration required by the current release contract.
REQUIRED_RELEASE_MIGRATION = REQUIRED_MIGRATIONS[-1]
