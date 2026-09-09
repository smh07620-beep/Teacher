import unittest

import schema_migrations


class SchemaMigrationTests(unittest.TestCase):
    def test_baseline_registered_once(self):
        versions = [v for v, _ in schema_migrations.MIGRATIONS]
        self.assertIn('0064-baseline', versions)
        self.assertEqual(len(versions), len(set(versions)))


if __name__ == '__main__':
    unittest.main()
