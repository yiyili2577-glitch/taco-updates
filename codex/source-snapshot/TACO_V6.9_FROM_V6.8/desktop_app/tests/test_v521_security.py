import os
import shutil
import tempfile
import unittest

from services.audit_log_service import AuditLogService
from services.data_maintenance_service import DataMaintenanceService
from services.security import PermissionDeniedError
from services.system_settings_service import SystemSettingsService
from services.user_auth_service import UserAuthService


class V521SecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        data = os.path.join(self.tmp, 'data')
        os.makedirs(data, exist_ok=True)

        UserAuthService.DATA_DIR = data
        UserAuthService.DATA_FILE = os.path.join(data, 'users.json')
        UserAuthService._current_user = None

        SystemSettingsService.DATA_DIR = data
        SystemSettingsService.DATA_FILE = os.path.join(data, 'system_settings.json')

        DataMaintenanceService.DATA_DIR = data
        DataMaintenanceService.BACKUP_DIR = os.path.join(data, 'backups')

        AuditLogService.DATA_DIR = data
        AuditLogService.AUDIT_DIR = os.path.join(data, 'audit_logs')
        AuditLogService.LOG_FILE = os.path.join(AuditLogService.AUDIT_DIR, 'audit_log.jsonl')

        self.admin = UserAuthService.create_first_admin('admin', 'password1', role if False else 'Admin') if False else UserAuthService.create_first_admin('admin', 'password1', display_name='Admin')
        UserAuthService.authenticate('admin', 'password1')
        # ensure advanced tier is active for maintenance tests
        settings = SystemSettingsService.load()
        settings['license']['tier'] = 'advanced'
        settings['license']['development_mode'] = True
        SystemSettingsService.save(settings)

    def tearDown(self):
        UserAuthService._current_user = None
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_data_maintenance_denied_to_non_admin(self):
        UserAuthService.create_user('bob', 'password1', role='採購人員')
        UserAuthService.authenticate('bob', 'password1')
        with self.assertRaises(PermissionDeniedError):
            DataMaintenanceService.create_savepoint('should fail')

    def test_data_maintenance_allowed_to_admin(self):
        sp = DataMaintenanceService.create_savepoint('manual test')
        self.assertEqual(sp['kind'], 'manual')
        self.assertTrue(os.path.isdir(DataMaintenanceService.BACKUP_DIR))

    def test_audit_scope_blocks_other_users_for_regular_user(self):
        AuditLogService.log_event('採購建議', '修改', actor={'username':'admin','display_name':'Admin','role':'系統管理員'})
        UserAuthService.create_user('bob', 'password1', role='採購人員')
        UserAuthService.authenticate('bob', 'password1')
        AuditLogService.log_event('採購建議', '修改', actor={'username':'bob','display_name':'Bob','role':'採購人員'})
        rows = AuditLogService.load_logs(newest_first=False)
        self.assertTrue(rows)
        self.assertTrue(all((r.get('actor') or {}).get('username') == 'bob' for r in rows))

    def test_audit_integrity_uses_full_chain(self):
        AuditLogService.log_event('系統', '測試1')
        AuditLogService.log_event('系統', '測試2')
        result = AuditLogService.verify_integrity()
        self.assertTrue(result['ok'])
        self.assertGreaterEqual(result['checked'], 2)


if __name__ == '__main__':
    unittest.main()
