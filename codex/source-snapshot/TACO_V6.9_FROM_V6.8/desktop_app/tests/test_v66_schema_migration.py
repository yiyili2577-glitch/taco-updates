import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.data_migration_service import DataMigrationService
from services.integration_db_service import IntegrationDbService


class V66SchemaMigrationTests(unittest.TestCase):
    def test_schema_1_to_2_creates_integration_db_and_version(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = root / 'Data'
            backups = root / 'Backups'
            data.mkdir()
            (data / 'product_master.json').write_text('[]', encoding='utf-8')
            with patch('services.data_migration_service.AppPaths.data_dir', return_value=data), \
                 patch('services.data_migration_service.AppPaths.backups_dir', return_value=backups), \
                 patch('services.integration_db_service.AppPaths.data_dir', return_value=data):
                result = DataMigrationService.migrate_to_latest()
                self.assertTrue(result['changed'])
                self.assertEqual(result['from'], 1)
                self.assertEqual(result['to'], 2)
                self.assertTrue((data / 'integration.db').exists())
                v = json.loads((data / 'schema_version.json').read_text(encoding='utf-8'))
                self.assertEqual(v['schema_version'], 2)
                self.assertTrue(Path(result['backup']).exists())
                health = IntegrationDbService.health()
                self.assertTrue(health['ok'])

    def test_schema_2_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = root / 'Data'
            backups = root / 'Backups'
            data.mkdir()
            (data / 'schema_version.json').write_text('{"schema_version":2}', encoding='utf-8')
            with patch('services.data_migration_service.AppPaths.data_dir', return_value=data), \
                 patch('services.data_migration_service.AppPaths.backups_dir', return_value=backups):
                result = DataMigrationService.migrate_to_latest()
                self.assertFalse(result['changed'])
                self.assertEqual(result['from'], 2)
                self.assertEqual(result['to'], 2)


if __name__ == '__main__':
    unittest.main()
