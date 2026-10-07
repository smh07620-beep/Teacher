import sqlite3
import tempfile
import unittest
from pathlib import Path

from teacher_app.maintenance import backup, recovery_audit


class F6RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=str(Path(self.tmp.name)/"recovery.sqlite")

        def connect():
            conn=sqlite3.connect(self.path)
            conn.row_factory=sqlite3.Row
            conn.isolation_level=None
            return conn,"sqlite"
        self.connect=connect

    def test_backup_contract_includes_late_phase_operational_tables(self):
        for table in (
            "training_interventions",
            "material_derivative_publications",
            "learning_assignments",
            "material_versions",
            "email_delivery_attempts",
            "r2_usage_ledger",
        ):
            self.assertIn(table,backup.DEFAULT_TABLES)

    def test_restore_rehearsal_never_writes_and_reports_compatibility(self):
        conn,_=self.connect()
        conn.execute("CREATE TABLE materials(id TEXT PRIMARY KEY,title TEXT)")
        conn.close()
        payload={
            "format":backup.BACKUP_FORMAT,
            "createdAt":"now","version":"6.8.1",
            "tables":{"materials":[{"id":"m1","title":"SOP","unknown":"x"}]},
        }
        report=backup.restore_rehearsal(payload,self.connect)
        self.assertTrue(report["safeToAttemptRestore"])
        self.assertEqual(report["tables"]["materials"]["compatibleRows"],1)
        self.assertEqual(report["tables"]["materials"]["missingColumns"],["unknown"])
        conn,_=self.connect()
        count=conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
        conn.close()
        self.assertEqual(count,0)

    def test_recovery_audit_detects_orphan_material_version(self):
        conn,_=self.connect()
        conn.execute("CREATE TABLE materials(id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE material_versions(material_id TEXT,version INTEGER)")
        conn.execute("INSERT INTO material_versions(material_id,version) VALUES('missing',1)")
        conn.close()
        report=recovery_audit.build_recovery_audit(self.connect)
        item=next(row for row in report["checks"] if row["key"]=="orphan_material_versions")
        self.assertEqual(item["count"],1)
        self.assertFalse(report["ok"])

    def _orphan_versions_with_audit(self,deleted_ids):
        conn,_=self.connect()
        conn.execute("CREATE TABLE materials(id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE material_versions(material_id TEXT,version INTEGER)")
        conn.execute("CREATE TABLE audit_events(action TEXT,target_type TEXT,target_id TEXT)")
        for material_id in ("deleted-on-purpose","truly-missing"):
            conn.execute("INSERT INTO material_versions(material_id,version) VALUES(?,1)",(material_id,))
        for material_id in deleted_ids:
            conn.execute(
                "INSERT INTO audit_events(action,target_type,target_id) VALUES('material.delete','material',?)",
                (material_id,),
            )
        conn.close()
        report=recovery_audit.build_recovery_audit(self.connect)
        return report,{row["key"]:row for row in report["checks"]}

    def test_versions_of_deliberately_deleted_material_are_retained_history_not_errors(self):
        report,items=self._orphan_versions_with_audit(["deleted-on-purpose"])
        self.assertEqual(items["orphan_material_versions"]["count"],1)
        self.assertEqual(items["retained_material_versions"]["count"],1)
        self.assertEqual(items["retained_material_versions"]["severity"],"info")
        self.assertTrue(items["retained_material_versions"]["ok"])
        self.assertFalse(report["ok"])
        self.assertEqual(report["errorCount"],1)

    def test_only_retained_history_leaves_audit_healthy(self):
        report,items=self._orphan_versions_with_audit(["deleted-on-purpose","truly-missing"])
        self.assertEqual(items["orphan_material_versions"]["count"],0)
        self.assertEqual(items["retained_material_versions"]["count"],2)
        self.assertTrue(report["ok"])
        self.assertEqual(report["status"],"healthy")
        self.assertEqual((report["errorCount"],report["warningCount"]),(0,0))


if __name__=="__main__":
    unittest.main()
