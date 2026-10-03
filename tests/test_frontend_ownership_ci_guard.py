from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
OWNERSHIP_DOC = ROOT / "docs" / "FRONTEND_JS_OWNERSHIP.md"


# Whole-document observers are intentionally exceptional.  This table is a
# review boundary: adding another document.body/documentElement observer must
# explain how it stays bounded (selector filtering, one-shot disconnect, or a
# narrow compatibility role).
BROAD_OBSERVER_CONTRACT = {
    "system-csp-actions.js": ("attributeFilter", "LEGACY_TO_DATA", "addedNodes"),
    "review-links-66.js": ("scanCreateForms",),
    "rbac-ui-681.js": ("record.addedNodes", "guardSensitiveGeneratedActions"),
    "home-profile-title-71.js": ("mutationTouchesIdentity",),
    "teacher-ui-resilience-1014.js": ("mutationTouchesWorkerSurface",),
    "teacher-ux-convergence-72.js": ("mutationNeedsReconcile",),
    "course-wizard-runtime-fix-1014.js": ("mutationNeedsConverge",),
    "course-wizard-group-fix-1014.js": ("nodeContainsWizard", "observer?.disconnect()"),
    "teacher-authoring-source-fix-1017.js": ("mutationNeedsInstall", "scheduleInstallAll"),
    "teacher-assignment-experience-1014.js": ("mutationNeedsConverge",),
    "teacher-ai-material-convergence-1014.js": ("nodeTouchesTarget", "observer?.disconnect()"),
    "teacher-ai-media-controls-1023.js": ("teacher-media-source-1018", "if (!shared) return"),
    "teacher-media-help-1014.js": ("observer.disconnect()",),
    "teacher-media-free-tts-1014.js": ("observer.disconnect()",),
    "teacher-media-mvp-status-1014.js": ("observer.disconnect()",),
    "teacher-media-source-fix-1014.js": ("observer.disconnect()",),
    "teacher-media-status-fix-1014.js": ("observer.disconnect()",),
    "teacher-paper-template-manager-1014.js": ("observer.disconnect()",),
    "teacher-ai-video-1015.js": ("observer.disconnect()",),
    "teacher-media-audio-1014.js": ("observer.disconnect()",),
    "teacher-media-recorder-1014.js": ("observer.disconnect()",),
    "teacher-media-script-1014.js": ("observer.disconnect()",),
    "teacher-ai-material-1014.js": ("observer.disconnect()",),
}

BROAD_OBSERVER_RE = re.compile(
    r"observe\s*\(\s*document\.(?:body|documentElement)\s*,\s*\{"
    r"(?=[^}]*childList\s*:\s*true)"
    r"(?=[^}]*subtree\s*:\s*true)",
    re.DOTALL,
)

NAV_CAPTURE_RE = re.compile(
    r"document\.addEventListener\s*\(\s*['\"]click['\"][\s\S]{0,700}?"
    r"closest\s*\(\s*['\"]\.admin-nav-btn['\"]",
)
ALLOWED_NAV_CAPTURE_FILES = {"teacher-content-studio-71.js"}


def _ownership_contract() -> dict[str, set[str]]:
    """Read allowed owner/wrapper files directly from the reviewed markdown map."""
    contract: dict[str, set[str]] = {}
    for line in OWNERSHIP_DOC.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or "static/" not in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells:
            continue
        globals_in_cell = [
            token
            for token in re.findall(r"`([A-Za-z_$][A-Za-z0-9_$]*)`", cells[0])
            if not token.startswith("static")
        ]
        files = set(re.findall(r"`(static/[^\`]+\.js)`", line))
        for name in globals_in_cell:
            if files:
                contract.setdefault(name, set()).update(files)
    return contract


def _assignment_hits(source: str, name: str) -> list[int]:
    patterns = (
        re.compile(rf"\b(?:window|globalThis)\.{re.escape(name)}\s*=\s*(?!=)"),
        re.compile(rf"(?m)^\s*{re.escape(name)}\s*=\s*(?!=)"),
    )
    hits: list[int] = []
    for pattern in patterns:
        hits.extend(match.start() for match in pattern.finditer(source))
    return sorted(set(hits))


class FrontendOwnershipCiGuardTests(unittest.TestCase):
    def test_documented_globals_cannot_gain_undocumented_assignment_owner(self):
        contract = _ownership_contract()
        self.assertIn("switchAdminWorkspace", contract)
        self.assertIn("createAdminUserAccount", contract)
        self.assertIn("renderAdminMaterials", contract)

        violations: list[str] = []
        sources = {
            path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8")
            for path in STATIC.glob("*.js")
        }
        for name, allowed in sorted(contract.items()):
            for path, source in sources.items():
                hits = _assignment_hits(source, name)
                if hits and path not in allowed:
                    violations.append(
                        f"{name}: undocumented assignment owner {path}; allowed={sorted(allowed)}"
                    )
        self.assertEqual([], violations, "\n" + "\n".join(violations))

    def test_document_wide_mutation_observers_are_explicitly_bounded_or_registered(self):
        observed: set[str] = set()
        for path in STATIC.glob("*.js"):
            source = path.read_text(encoding="utf-8")
            if not BROAD_OBSERVER_RE.search(source):
                continue
            observed.add(path.name)
            self.assertIn(
                path.name,
                BROAD_OBSERVER_CONTRACT,
                f"{path.name} adds a broad MutationObserver without an ownership contract",
            )
            for marker in BROAD_OBSERVER_CONTRACT[path.name]:
                self.assertIn(marker, source, f"{path.name} is missing observer guard marker {marker!r}")

        stale = set(BROAD_OBSERVER_CONTRACT) - observed
        self.assertEqual(
            set(),
            stale,
            f"remove stale broad-observer exemptions after narrowing/removing the observer: {sorted(stale)}",
        )

    def test_admin_navigation_capture_handler_has_one_registered_interceptor(self):
        owners = set()
        for path in STATIC.glob("*.js"):
            source = path.read_text(encoding="utf-8")
            if NAV_CAPTURE_RE.search(source):
                owners.add(path.name)
        self.assertEqual(ALLOWED_NAV_CAPTURE_FILES, owners)

    def test_dynamic_csp_workspace_navigation_clears_direct_onclick(self):
        violations = []
        for path in STATIC.glob("*.js"):
            source = path.read_text(encoding="utf-8")
            if "setAttribute('data-csp-click'" not in source and 'setAttribute("data-csp-click"' not in source:
                continue
            if "switchAdminWorkspace(" not in source:
                continue
            clears_property = ".onclick = null" in source or ".onclick=null" in source
            clears_attribute = "removeAttribute('onclick')" in source or 'removeAttribute("onclick")' in source
            if not (clears_property and clears_attribute):
                violations.append(path.name)
        self.assertEqual(
            [],
            violations,
            "dynamic CSP workspace navigation must clear both onclick property and attribute",
        )

    def test_csp_delegate_remains_canonical(self):
        source = (STATIC / "system-csp-actions.js").read_text(encoding="utf-8")
        self.assertIn("const ATTRIBUTE_BY_EVENT", source)
        self.assertIn("click: 'data-csp-click'", source)
        self.assertIn("const target = delegatedTarget", source)
        self.assertIn("runProgram(target.getAttribute(attribute)", source)


if __name__ == "__main__":
    unittest.main()
