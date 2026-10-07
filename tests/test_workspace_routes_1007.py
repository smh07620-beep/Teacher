"""Eleven back-office workspaces, four product areas, one route table."""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from pgy_frontend import _apply_asset_manifest
from teacher_app.common import workspace_routes as py_routes
from teacher_app.notifications.events import _href

ROOT = Path(__file__).parents[1]
STATIC = ROOT / "static"
REGISTRY_JS = STATIC / "workspace-routes-1007.js"
# Files allowed to talk about workspace names without going through the registry.
LITERAL_ALLOWED = {"admin-workspace.js", "workspace-routes-1007.js"}


def _node_registry():
    node = shutil.which("node")
    if not node:
        return None
    script = (
        "const fs=require('fs');global.window={};"
        f"eval(fs.readFileSync({json.dumps(str(REGISTRY_JS))},'utf8'));"
        "const R=window.AppWorkspaceRoutes;"
        "console.log(JSON.stringify({areas:Object.fromEntries(Object.entries(R.AREAS).map(([k,v])=>[k,v.label])),"
        "workspaces:Object.fromEntries(Object.entries(R.WORKSPACES).map(([k,v])=>[k,v.area])),"
        "aliases:R.ALIASES,default:R.DEFAULT_WORKSPACE,"
        "urls:[R.url('course-materials',{area:'internal',group:'grpBio',persona:'teacher',from:'notification-center',params:{courseId:'c1'}}),"
        "R.url('worker',{from:'notification-center'}),R.url('questions')]}))"
    )
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise AssertionError(out.stderr)
    return json.loads(out.stdout)


class RouteTableTests(unittest.TestCase):
    def test_eleven_workspaces_fall_into_exactly_the_documented_areas(self):
        self.assertEqual(len(py_routes.WORKSPACE_AREAS), 11)
        self.assertEqual(set(py_routes.AREAS), {"learning", "teaching", "assessment", "system"})
        self.assertTrue(set(py_routes.WORKSPACE_AREAS.values()) <= set(py_routes.AREAS) - {"learning"})
        for area in ("teaching", "assessment", "system"):
            self.assertIn(area, py_routes.WORKSPACE_AREAS.values(), area)

    def test_system_area_is_exactly_the_platform_governance_workspaces(self):
        system = {k for k, v in py_routes.WORKSPACE_AREAS.items() if v == "system"}
        self.assertEqual(system, {"people", "system", "maintenance", "audit", "worker"})

    def test_aliases_point_at_real_workspaces(self):
        for alias, target in py_routes.ALIASES.items():
            self.assertNotIn(alias, py_routes.WORKSPACE_AREAS)
            self.assertIn(target, py_routes.WORKSPACE_AREAS)

    def test_behaviour_suite_passes_in_node(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        result = subprocess.run(
            [node, "--test", str(ROOT / "tests" / "js" / "workspace-routes-1007.test.js")],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout[-2500:] + result.stderr[-1000:])

    def test_python_and_javascript_tables_are_identical(self):
        js = _node_registry()
        if js is None:
            self.skipTest("node is not installed")
        self.assertEqual(js["areas"], py_routes.AREAS)
        self.assertEqual(js["workspaces"], py_routes.WORKSPACE_AREAS)
        self.assertEqual(js["aliases"], py_routes.ALIASES)
        self.assertEqual(js["default"], py_routes.DEFAULT_WORKSPACE)

    def test_python_and_javascript_build_the_same_urls(self):
        js = _node_registry()
        if js is None:
            self.skipTest("node is not installed")
        expected = [
            py_routes.workspace_url("course-materials", area="internal", group="grpBio", persona="teacher",
                                    source="notification-center", params={"courseId": "c1"}),
            py_routes.workspace_url("worker", source="notification-center"),
            py_routes.workspace_url("questions"),
        ]
        self.assertEqual(js["urls"], expected)

    def test_urls_keep_the_legacy_link_shape(self):
        self.assertEqual(
            py_routes.workspace_url("worker", source="notification-center"),
            "/system?admin=1&workspace=worker&persona=system&from=notification-center",
        )
        self.assertEqual(
            py_routes.workspace_url("course-materials", area="internal", group="grpBio"),
            "/system?area=internal&group=grpBio&admin=1&workspace=course-materials",
        )

    def test_unknown_workspace_is_rejected_instead_of_building_a_dead_link(self):
        with self.assertRaises(ValueError):
            py_routes.workspace_url("assesment")

    def test_notification_links_are_unchanged(self):
        self.assertEqual(
            _href({"target": "worker"}),
            "/system?admin=1&workspace=worker&persona=system&from=notification-center",
        )
        self.assertEqual(
            _href({"target": "course-materials", "area": "internal", "group": "grpBio", "courseId": "c9"}),
            "/system?area=internal&group=grpBio&admin=1&workspace=course-materials"
            "&persona=teacher&from=notification-center&courseId=c9",
        )


class NavigationMarkupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (STATIC / "system.html").read_text(encoding="utf-8")

    def test_every_static_nav_button_sits_in_the_group_of_its_area(self):
        groups = re.findall(
            r'<section class="v580-admin-group[^"]*" data-admin-area="(\w+)">(.*?)</section>',
            self.html, re.S,
        )
        self.assertEqual([area for area, _ in groups], ["teaching", "assessment", "system"])
        seen = set()
        for area, body in groups:
            for key in re.findall(r'id="admin-nav-([a-z-]+)"', body):
                self.assertEqual(py_routes.WORKSPACE_AREAS[key], area, key)
                seen.add(key)
        self.assertEqual(seen, {"course-materials", "word", "assessment", "teacher", "results", "compliance", "people", "system"})

    def test_static_click_handlers_only_name_known_workspaces(self):
        for name in re.findall(r"switchAdminWorkspace\('([a-z-]+)'", self.html):
            self.assertIn(py_routes.normalize(name), py_routes.WORKSPACE_AREAS, name)


class NoHandWrittenRoutesTests(unittest.TestCase):
    """New links must go through AppWorkspaceRoutes, not hand-written strings."""

    def scripts(self):
        for path in sorted(STATIC.glob("*.js")):
            if path.name not in LITERAL_ALLOWED:
                yield path, path.read_text(encoding="utf-8")

    def test_no_script_hand_writes_a_workspace_url(self):
        names = "|".join(sorted(set(py_routes.WORKSPACE_AREAS) | set(py_routes.ALIASES)))
        pattern = re.compile(rf"workspace=(?:{names})\b")
        offenders = [p.name for p, text in self.scripts() if pattern.search(text)]
        self.assertEqual(offenders, [])

    def test_no_script_calls_the_router_with_a_literal_name(self):
        pattern = re.compile(r"(?:openAdminWorkspace|switchAdminWorkspace)\??\.?\(\s*['\"][a-z-]+['\"]")
        offenders = []
        for path, text in self.scripts():
            for line in text.splitlines():
                if pattern.search(line) and "data-csp-click" not in line:
                    offenders.append(f"{path.name}: {line.strip()[:90]}")
        self.assertEqual(offenders, [])

    def test_no_script_keeps_its_own_copy_of_the_system_workspace_list(self):
        pattern = re.compile(r"'people'\s*,\s*'system'\s*,\s*'worker'")
        offenders = [p.name for p, text in self.scripts() if pattern.search(text)]
        self.assertEqual(offenders, [])

    def test_registry_is_injected_first_on_every_page_that_links_to_workspaces(self):
        system = _apply_asset_manifest(
            '<html><body><script defer src="/shared-core.js"></script>'
            '<script defer src="/system-admin.js"></script></body></html>', "system")
        order = re.findall(r'src="([^"]+)"', system)
        self.assertEqual(order.count("/workspace-routes-1007.js"), 1)
        self.assertEqual(order.index("/workspace-routes-1007.js"), order.index("/shared-core.js") + 1)
        portal = _apply_asset_manifest(
            '<html><body><script defer src="/shared-core.js"></script>'
            '<script defer src="/portal-v56.js"></script></body></html>', "portal")
        order = re.findall(r'src="([^"]+)"', portal)
        self.assertEqual(order.count("/workspace-routes-1007.js"), 1)
        self.assertLess(order.index("/workspace-routes-1007.js"), order.index("/portal-v56.js"))


if __name__ == "__main__":
    unittest.main()
