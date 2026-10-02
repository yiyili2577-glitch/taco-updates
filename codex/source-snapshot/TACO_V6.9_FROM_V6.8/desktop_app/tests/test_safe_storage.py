"""services/safe_storage.py 的單元測試：原子寫入、自動備份、損毀復原、輪替。"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.safe_storage import SafeStorage


class SafeStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp_dir, "data", "sample.json")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_write_then_read_roundtrip(self):
        SafeStorage.atomic_write_json(self.path, {"a": 1})
        self.assertEqual(SafeStorage.safe_read_json(self.path), {"a": 1})

    def test_missing_file_returns_default(self):
        missing = os.path.join(self.tmp_dir, "data", "does_not_exist.json")
        self.assertEqual(SafeStorage.safe_read_json(missing, default={"x": 0}), {"x": 0})

    def test_second_write_creates_one_backup_of_previous_version(self):
        SafeStorage.atomic_write_json(self.path, {"a": 1})
        SafeStorage.atomic_write_json(self.path, {"a": 2})
        backups = SafeStorage._list_backups(self.path)
        self.assertEqual(len(backups), 1)

    def test_corrupted_main_file_falls_back_to_latest_backup(self):
        SafeStorage.atomic_write_json(self.path, {"a": 1})
        SafeStorage.atomic_write_json(self.path, {"a": 2})
        # 第二次寫入前，會先把「當時的主檔內容」({"a": 1}) 備份起來，
        # 所以此時最新一份備份存的是 {"a": 1}，主檔案才是 {"a": 2}。
        SafeStorage.atomic_write_json(self.path, {"a": 3})
        # 模擬檔案損毀（例如寫檔中途被中斷），驗證會改用「上一版」備份 {"a": 2}
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{this is not valid json")
        recovered = SafeStorage.safe_read_json(self.path, default="SHOULD_NOT_BE_USED")
        self.assertEqual(recovered, {"a": 2})

    def test_all_backups_corrupted_falls_back_to_default(self):
        SafeStorage.atomic_write_json(self.path, {"a": 1})
        for backup_name in SafeStorage._list_backups(self.path):
            backup_path = os.path.join(SafeStorage._backup_dir_for(self.path), backup_name)
            with open(backup_path, "w", encoding="utf-8") as f:
                f.write("also not valid json")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("not valid json either")
        recovered = SafeStorage.safe_read_json(self.path, default={"fallback": True})
        self.assertEqual(recovered, {"fallback": True})

    def test_backup_rotation_keeps_only_configured_count(self):
        for i in range(SafeStorage.DEFAULT_KEEP_BACKUPS + 5):
            SafeStorage.atomic_write_json(self.path, {"a": i})
        backups = SafeStorage._list_backups(self.path)
        self.assertEqual(len(backups), SafeStorage.DEFAULT_KEEP_BACKUPS)

    def test_write_failure_does_not_leave_partial_file(self):
        # 正常寫入一次，之後刻意用一個「不能被 json 序列化」的物件觸發寫入失敗，
        # 驗證原本的正式檔案內容仍然完好無缺（不會被寫壞或截斷）。
        SafeStorage.atomic_write_json(self.path, {"a": 1})
        with self.assertRaises(TypeError):
            SafeStorage.atomic_write_json(self.path, {"bad": object()})
        self.assertEqual(SafeStorage.safe_read_json(self.path), {"a": 1})
        # 也不應該留下暫存檔垃圾
        leftover_tmp = [f for f in os.listdir(os.path.dirname(self.path)) if f.endswith(".tmp")]
        self.assertEqual(leftover_tmp, [])


if __name__ == "__main__":
    unittest.main()
