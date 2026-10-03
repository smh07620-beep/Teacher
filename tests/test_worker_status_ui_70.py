"""Teacher 7.0 M3 Worker status exposure regressions."""
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class WorkerStatusUi70Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT.joinpath("static", "worker-status-70.js").read_text(encoding="utf-8")
        cls.frontend = ROOT.joinpath("pgy_frontend.py").read_text(encoding="utf-8")

    def test_worker_surface_is_system_admin_only(self):
        self.assertIn("window.TeacherRBAC681Ready", self.source)
        self.assertIn("const R = await", self.source)
        self.assertIn("if (!roles.has('system_admin')) return", self.source)
        self.assertIn("admin-nav-worker", self.source)
        self.assertIn("admin-section-worker", self.source)

    def test_worker_surface_uses_read_only_session_rbac(self):
        # The operational surface keeps a larger recent window so failed and
        # retrying jobs remain visible alongside the queue summary.
        self.assertIn("/api/material-jobs?limit=30", self.source)
        self.assertIn("credentials: 'same-origin'", self.source)
        fetch_start = self.source.index("const response = await fetch")
        fetch_end = self.source.index("const data = await response.json", fetch_start)
        request_block = self.source[fetch_start:fetch_end]
        for forbidden in ("X-Admin-Key", "Authorization", "MATERIAL_WORKER_TOKEN", "method: 'POST'", "method: 'DELETE'", "method: 'PATCH'"):
            self.assertNotIn(forbidden, request_block)

    def test_operational_fields_are_exposed(self):
        for marker in (
            "pendingJobs",
            "oldestPendingAgeSeconds",
            "recentFailureRate",
            "averageCompletedDurationSeconds",
            "processingJobs",
            "retryJobs",
            "failedJobs",
            "healthyProcessingJobs",
            "heartbeatDelayedJobs",
            "stalledJobs",
            "heartbeatWarningSeconds",
            "staleThresholdSeconds",
            "observabilityState",
            "heartbeatAgeSeconds",
            "problemJobs",
            "incidents",
            "incidentType",
            "occurrenceCount",
            "generation",
            "維運事件",
            "目前問題",
            "已恢復",
            "建議動作",
            "responseState",
            "assignedTo",
            "maintenanceActive",
            "runbook",
            "data-incident-action",
            "worker-incidents-70",
            "worker-problems-70",
            "workerVersion",
            "workerSha",
            "workerBranch",
            "currentJobId",
            "lastUpdateCheckAt",
            "updateAvailable",
            "ffmpeg",
            "libreOffice",
        ):
            self.assertIn(marker, self.source)

    def test_incident_actions_use_plain_links_and_route_by_domain(self):
        self.assertIn("function incidentActionMeta(incident)", self.source)
        self.assertIn("function incidentResponseMeta(incident)", self.source)
        self.assertIn("workspace=system&persona=system&from=incident&focus=storage", self.source)
        self.assertIn("workspace=assessment&persona=teacher&from=incident&focus=ai-question", self.source)
        self.assertIn("workspace=course-materials&persona=teacher&from=incident&focus=ai-media", self.source)
        self.assertIn("Boolean(window.TeacherWorkspace1014?.canTeach)", self.source)
        incident_block = self.source[
            self.source.index("function incidentCards"):
            self.source.index("function firstRunGuide")
        ]
        self.assertIn("data-incident-action", incident_block)
        self.assertNotIn("data-csp-click", incident_block)
        self.assertNotIn(".onclick", incident_block)

    def test_first_run_guide_is_explicit(self):
        for marker in (
            "本機 Worker 第一次安裝（只需要做一次）",
            "Python 3.12",
            "FFmpeg/FFprobe",
            "LibreOffice",
            "官方 MEGAcmd",
            "py -3.12 -m venv .venv",
            ".local-worker.env",
            "MATERIAL_WORKER_TOKEN",
            "run_material_worker_autostart.ps1",
            "Windows Task Scheduler",
            "自動 fast-forward",
        ):
            self.assertIn(marker, self.source)

    def test_worker_navigation_uses_single_csp_dispatch_owner(self):
        self.assertIn("button.dataset.adminWorkspace = 'worker'", self.source)
        self.assertIn('button.setAttribute(\'data-csp-click\', "switchAdminWorkspace(\'worker\',true)")', self.source)
        self.assertIn("button.onclick = null", self.source)
        self.assertNotIn("button.onclick = () => window.switchAdminWorkspace?.('worker', true)", self.source)
        self.assertIn('[data-admin-nav-group="operations"] .v580-admin-group-actions', self.source)
        self.assertIn("group.dataset.adminNavGroup = 'operations'", self.source)
        self.assertNotIn("label.textContent = 'Worker 與佇列'", self.source)

    def test_worker_asset_loads_after_role_workspace_shell(self):
        from pgy_frontend import ASSET_MANIFEST
        body = ASSET_MANIFEST["system"]["body"]
        self.assertLess(body.index('/workspace-shell-70.js'), body.index('/worker-status-70.js'))


if __name__ == "__main__":
    unittest.main()
