import unittest
from unittest.mock import Mock

from teacher_app.maintenance import production_readiness


class F6ProductionReadinessTests(unittest.TestCase):
    def runtime(self, *, active=True, shared=True):
        runtime=Mock()
        runtime.staging_capability.return_value={"backend":"r2","available":True,"shared":shared}
        runtime.operations_status.return_value={
            "workerStatusAvailable":True,
            "workers":[{"workerId":"hospital-1","status":"online" if active else "offline"}],
            "failedJobs":0,"pendingJobs":0,"processingJobs":0,
        }
        return runtime

    def test_all_required_evidence_produces_ready(self):
        health_payload={
            "ok":True,"status":"ready",
            "deployment":{"provider":"render","branch":"main","commit":"abcdef123456"},
            "database":{"ok":True,"kind":"postgres"},
            "migrations":{"ok":True,"missing":[]},
            "configuration":{"ok":True,"warnings":[]},
        }
        backup=lambda _factory=None:{
            "format":"teacher-backup-v1","createdAt":"now","sha256":"abc",
            "tables":{"materials":[{"id":"m1"}]},
        }
        email=lambda:{
            "schedule":{"health":"healthy","issue":""},"today":{"sent":1,"failed":0}
        }
        from unittest.mock import patch
        with patch.object(production_readiness.health,"ready_state",return_value=(health_payload,200)):
            data=production_readiness.build_acceptance(
                material_runtime=self.runtime(),
                connection_factory=lambda:None,
                backup_builder=backup,
                email_builder=email,
                rehearsal_builder=lambda _backup,_factory=None:{
                    "safeToAttemptRestore":True,
                    "totals":{"compatibleRows":1,"skippedRows":0},
                },
                recovery_builder=lambda _factory=None:{
                    "ok":True,"errorCount":0,"warningCount":0,
                },
            )
        self.assertTrue(data["ready"])
        self.assertEqual(data["status"],"production_ready")
        self.assertEqual(data["storage"]["backend"],"r2")
        self.assertEqual(data["worker"]["active"],1)
        self.assertTrue(data["backup"]["restoreRehearsalOk"])
        self.assertTrue(data["recovery"]["ok"])
        self.assertTrue(data["gate"]["productionReady"])

    def test_worker_offline_and_unshared_storage_are_blockers(self):
        health_payload={
            "ok":True,"status":"ready",
            "deployment":{"provider":"render","branch":"main","commit":"abcdef123456"},
            "database":{"ok":True,"kind":"postgres"},
            "migrations":{"ok":True,"missing":[]},
            "configuration":{"ok":True,"warnings":[]},
        }
        from unittest.mock import patch
        with patch.object(production_readiness.health,"ready_state",return_value=(health_payload,200)):
            data=production_readiness.build_acceptance(
                material_runtime=self.runtime(active=False,shared=False),
                backup_builder=lambda _factory=None:{"format":"teacher-backup-v1","sha256":"abc","tables":{}},
                email_builder=lambda:{"schedule":{"health":"healthy"}},
                rehearsal_builder=lambda _backup,_factory=None:{
                    "safeToAttemptRestore":True,
                    "totals":{"compatibleRows":1,"skippedRows":0},
                },
                recovery_builder=lambda _factory=None:{
                    "ok":True,"errorCount":0,"warningCount":0,
                },
            )
        keys={item["key"] for item in data["blockers"]}
        self.assertIn("shared_storage",keys)
        self.assertIn("worker",keys)
        self.assertFalse(data["ready"])

    def test_email_is_warning_not_release_blocker(self):
        health_payload={
            "ok":True,"status":"ready",
            "deployment":{"provider":"render","branch":"main","commit":"abcdef123456"},
            "database":{"ok":True,"kind":"postgres"},
            "migrations":{"ok":True,"missing":[]},
            "configuration":{"ok":True,"warnings":[]},
        }
        from unittest.mock import patch
        with patch.object(production_readiness.health,"ready_state",return_value=(health_payload,200)):
            data=production_readiness.build_acceptance(
                material_runtime=self.runtime(),
                backup_builder=lambda _factory=None:{"format":"teacher-backup-v1","sha256":"abc","tables":{}},
                email_builder=lambda:{"schedule":{"health":"missing_run","issue":"missing"}},
                rehearsal_builder=lambda _backup,_factory=None:{
                    "safeToAttemptRestore":True,
                    "totals":{"compatibleRows":1,"skippedRows":0},
                },
                recovery_builder=lambda _factory=None:{
                    "ok":True,"errorCount":0,"warningCount":0,
                },
            )
        self.assertTrue(data["ready"])
        self.assertEqual(data["warnings"][0]["key"],"email")


if __name__=="__main__":
    unittest.main()
