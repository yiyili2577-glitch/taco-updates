"""service 層權限檢查的單元測試（security.py + UserAuthService 的整合）。

驗證重點：畫面按鈕停用之外，底層 service 函式本身也要擋下沒有權限的呼叫，
不能被繞過。這個測試不需要 PyQt6（role_rules.py 是純 Python，不依賴 PyQt6）。

執行方式：python -m unittest discover -s tests -v
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.user_auth_service import UserAuthService
from services.system_settings_service import SystemSettingsService
from services.security import PermissionDeniedError


class ServicePermissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        data_dir = os.path.join(self.tmp_dir, "data")
        UserAuthService.DATA_DIR = data_dir
        UserAuthService.DATA_FILE = os.path.join(data_dir, "users.json")
        UserAuthService._current_user = None
        SystemSettingsService.DATA_DIR = data_dir
        SystemSettingsService.DATA_FILE = os.path.join(data_dir, "system_settings.json")

        self.admin = UserAuthService.create_first_admin("admin", "password1", "系統管理員")

    def tearDown(self):
        UserAuthService._current_user = None
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_bootstrap_creates_admin_role(self):
        self.assertEqual(self.admin["role"], "系統管理員")

    def test_second_bootstrap_is_rejected(self):
        with self.assertRaises(ValueError):
            UserAuthService.create_first_admin("admin2", "password1")

    def test_create_user_denied_when_not_logged_in(self):
        UserAuthService._current_user = None
        with self.assertRaises(PermissionDeniedError):
            UserAuthService.create_user("bob", "password1", role="採購人員")

    def test_create_user_allowed_for_admin(self):
        UserAuthService.authenticate("admin", "password1")
        bob = UserAuthService.create_user("bob", "password1", role="採購人員")
        self.assertEqual(bob["username"], "bob")

    def test_non_admin_cannot_change_other_users_password(self):
        UserAuthService.authenticate("admin", "password1")
        UserAuthService.create_user("bob", "password1", role="採購人員")
        UserAuthService.authenticate("bob", "password1")
        with self.assertRaises(PermissionDeniedError):
            UserAuthService.change_password("admin", "newpassword1")

    def test_user_can_change_own_password(self):
        UserAuthService.authenticate("admin", "password1")
        UserAuthService.create_user("bob", "password1", role="採購人員")
        UserAuthService.authenticate("bob", "password1")
        UserAuthService.change_password("bob", "newpassword2")
        # 用新密碼登入應該要成功，證明密碼真的被改了
        result = UserAuthService.authenticate("bob", "newpassword2")
        self.assertEqual(result["username"], "bob")

    def test_non_admin_cannot_delete_users(self):
        UserAuthService.authenticate("admin", "password1")
        UserAuthService.create_user("bob", "password1", role="採購人員")
        UserAuthService.authenticate("bob", "password1")
        with self.assertRaises(PermissionDeniedError):
            UserAuthService.delete_user("admin")

    def test_non_admin_cannot_promote_self_to_admin(self):
        # 就算改的是自己的資料，涉及角色（role）一律要求系統管理員權限，
        # 避免使用者透過改自己的角色來自我提權。
        UserAuthService.authenticate("admin", "password1")
        UserAuthService.create_user("bob", "password1", role="採購人員")
        UserAuthService.authenticate("bob", "password1")
        with self.assertRaises(PermissionDeniedError):
            UserAuthService.update_user("bob", role="系統管理員")

    def test_non_admin_can_edit_own_display_name(self):
        UserAuthService.authenticate("admin", "password1")
        UserAuthService.create_user("bob", "password1", role="採購人員")
        UserAuthService.authenticate("bob", "password1")
        updated = UserAuthService.update_user("bob", display_name="Bob Chen")
        self.assertEqual(updated["display_name"], "Bob Chen")

    def test_non_admin_cannot_save_system_settings(self):
        UserAuthService.authenticate("admin", "password1")
        UserAuthService.create_user("bob", "password1", role="採購人員")
        UserAuthService.authenticate("bob", "password1")
        with self.assertRaises(PermissionDeniedError):
            SystemSettingsService.save(SystemSettingsService.load())

    def test_admin_can_save_system_settings(self):
        UserAuthService.authenticate("admin", "password1")
        result = SystemSettingsService.save(SystemSettingsService.load())
        self.assertIn("license", result)

    def test_last_admin_cannot_be_deleted(self):
        UserAuthService.authenticate("admin", "password1")
        with self.assertRaises(ValueError):
            UserAuthService.delete_user("admin")


if __name__ == "__main__":
    unittest.main()
