import json
import os
import zipfile
from datetime import datetime
from pathlib import Path

from services.app_paths import AppPaths
from services.build_config import BuildConfig


class DataMigrationService:
    FILE_NAME = "schema_version.json"

    @staticmethod
    def current_schema_version():
        path = AppPaths.data_dir() / DataMigrationService.FILE_NAME
        if not path.exists():
            return 1
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return max(1, int(data.get("schema_version", 1)))
        except Exception:
            return 1

    @staticmethod
    def _write_version(version):
        path = AppPaths.data_dir() / DataMigrationService.FILE_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "schema_version": int(version),
            "app_version": BuildConfig.VERSION,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    @staticmethod
    def _backup_data(label):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = AppPaths.backups_dir() / f"{label}_{stamp}.zip"
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(AppPaths.data_dir()):
                for name in files:
                    src = Path(root) / name
                    # SQLite WAL/SHM 可能在執行中短暫存在；升級發生於 UI 啟動前，
                    # 仍將當下存在的檔案一併保存，避免 integration.db 狀態遺漏。
                    try:
                        zf.write(src, arcname=str(src.relative_to(AppPaths.data_dir())))
                    except FileNotFoundError:
                        pass
        return target

    @staticmethod
    def _migrate_1_to_2():
        """V6.6 schema 1 -> 2：建立 Local Integration Layer。

        既有產品/供應商/庫存/財務 JSON 不改欄位、不搬資料。
        只初始化新的 integration.db 表結構，因此可安全重跑且具冪等性。
        """
        from services.integration_db_service import IntegrationDbService
        IntegrationDbService.initialize()

    @staticmethod
    def migrate_to_latest():
        current = DataMigrationService.current_schema_version()
        original = current
        target = BuildConfig.SCHEMA_VERSION

        if current > target:
            raise RuntimeError(f"資料版本 {current} 高於程式支援的 {target}，請勿使用較舊 TACO 開啟。")
        if current == target:
            DataMigrationService._write_version(target)
            return {"changed": False, "from": current, "to": target}

        backup = DataMigrationService._backup_data(f"SCHEMA_PRE_{current}_TO_{target}")
        while current < target:
            fn = getattr(DataMigrationService, f"_migrate_{current}_to_{current + 1}", None)
            if fn is None:
                raise RuntimeError(f"缺少資料升級程序：{current} → {current + 1}")
            fn()
            current += 1
            DataMigrationService._write_version(current)

        return {"changed": True, "from": original, "to": target, "backup": str(backup)}
