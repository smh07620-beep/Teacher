# Accessibility regression gate

The release UI workflow includes a deterministic Playwright accessibility guard in `tests/playwright/accessibility-regression.spec.js`.

This is a high-signal regression gate for the project’s current learner and workspace surfaces. It is **not a complete axe/WCAG conformance audit** and does not replace periodic manual assistive-technology review.

## Browser coverage

The deterministic UI harness checks these surfaces at both mobile (`390x844`) and desktop (`1440x1000`) widths:

- learner home `/`
- Internal Training `/internal`
- PGY `/pgy`
- learning/admin workspace `/system?area=internal&group=grpBio&module=materials`

The guard fails on missing document language, duplicate IDs, missing alternative text, positive `tabindex`, unnamed interactive controls, ambiguous navigation landmarks, focusable content inside visible `aria-hidden="true"` containers, unnamed dialogs, and responsive horizontal overflow.

It also exercises keyboard tab focus visibility and keyboard opening/closing of the learner profile dialog, including focus ownership while the modal is open.

## Release workflow

`.github/workflows/playwright-ui-checks.yml` runs this guard after the existing deterministic responsive regression and before the real Flask browser smoke suite. It reuses the same Playwright/Chromium runtime already installed by that workflow.

This gate changes no RBAC, scope, CSRF or other authority boundary.
