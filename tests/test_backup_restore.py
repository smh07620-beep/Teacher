import json
import unittest
import zipfile
import io

from backup_restore import BACKUP_FORMAT, _zip_payload


class BackupRestoreTests(unittest.TestCase):
    def test_backup_zip_contains_single_manifest(self):
        payload = {'format': BACKUP_FORMAT, 'createdAt': 'now', 'version': '6.4.0', 'tables': {}}
        raw = _zip_payload(payload)
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            self.assertEqual(zf.namelist(), ['teacher-backup.json'])
            data = json.loads(zf.read('teacher-backup.json').decode('utf-8'))
            self.assertEqual(data['format'], BACKUP_FORMAT)


if __name__ == '__main__':
    unittest.main()
