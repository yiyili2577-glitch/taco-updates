import hashlib
import json
import os
import shutil
from datetime import datetime

from services.system_settings_service import SystemSettingsService
from services.user_auth_service import UserAuthService
from services.app_paths import AppPaths
from services.safe_storage import SafeStorage, get_logger
from services import security


class DataMaintenanceService:
    """TACO 業務資料儲存點、還原與安全清除。

    安全原則：
    - users.json 永遠不納入業務資料清除／還原。
    - system_settings.json 永遠保留，避免版本授權、帳號、ERP 連線與外觀設定被還原覆蓋。
    - backups/ 自己不被備份到自己裡面。
    - 還原與清除前會先建立自動安全儲存點。
    """

    BASE_DIR = str(AppPaths.install_dir())
    DATA_DIR = str(AppPaths.data_dir())
    BACKUP_DIR = str(AppPaths.backups_dir())
    MANIFEST = "manifest.json"

    PROTECTED_NAMES = {
        "users.json",
        "system_settings.json",
        "backups",
        "audit_logs",
        "_file_backups",
    }

    @staticmethod
    def _ensure():
        os.makedirs(DataMaintenanceService.DATA_DIR, exist_ok=True)
        os.makedirs(DataMaintenanceService.BACKUP_DIR, exist_ok=True)

    @staticmethod
    def _now():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _stamp():
        return datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    @staticmethod
    def _actor():
        user = UserAuthService.current_user() or {}
        return {
            "username": str(user.get("username", "")),
            "display_name": str(user.get("display_name", "")),
            "role": str(user.get("role", "")),
        }

    @staticmethod
    def _is_protected(name):
        return str(name) in DataMaintenanceService.PROTECTED_NAMES

    @staticmethod
    def _business_entries():
        DataMaintenanceService._ensure()
        result = []
        for name in sorted(os.listdir(DataMaintenanceService.DATA_DIR)):
            if DataMaintenanceService._is_protected(name):
                continue
            result.append(name)
        return result

    @staticmethod
    def _file_sha256(path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _collect_files(root):
        records = []
        if not os.path.exists(root):
            return records
        for base, _, files in os.walk(root):
            for filename in sorted(files):
                full = os.path.join(base, filename)
                rel = os.path.relpath(full, root).replace("\\", "/")
                try:
                    size = os.path.getsize(full)
                    digest = DataMaintenanceService._file_sha256(full)
                except Exception:
                    size = 0
                    digest = ""
                records.append({"path": rel, "size": size, "sha256": digest})
        return records

    @staticmethod
    def create_savepoint(note="", kind="manual"):
        security.require_admin("建立資料儲存點", allow_readonly_backup=True)
        from services.license_client_service import LicenseClientService
        if LicenseClientService.restricted_readonly_mode():
            if LicenseClientService.last_trusted_tier() != "advanced":
                raise security.PermissionDeniedError("資料儲存點需要高級版授權。")
        else:
            security.require_tier("advanced", "資料儲存點")
        DataMaintenanceService._ensure()
        folder_name = f"{DataMaintenanceService._stamp()}_{kind}"
        target = os.path.join(DataMaintenanceService.BACKUP_DIR, folder_name)
        payload = os.path.join(target, "data")
        os.makedirs(payload, exist_ok=False)

        copied_entries = []
        for name in DataMaintenanceService._business_entries():
            src = os.path.join(DataMaintenanceService.DATA_DIR, name)
            dst = os.path.join(payload, name)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            elif os.path.isfile(src):
                shutil.copy2(src, dst)
            copied_entries.append(name)

        files = DataMaintenanceService._collect_files(payload)
        manifest = {
            "id": folder_name,
            "created_at": DataMaintenanceService._now(),
            "kind": str(kind),
            "note": str(note or ""),
            "version": SystemSettingsService.CURRENT_VERSION,
            "actor": DataMaintenanceService._actor(),
            "entry_count": len(copied_entries),
            "file_count": len(files),
            "total_bytes": sum(int(x.get("size", 0)) for x in files),
            "entries": copied_entries,
            "files": files,
            "protected": sorted(DataMaintenanceService.PROTECTED_NAMES),
        }
        SafeStorage.atomic_write_json(
            os.path.join(target, DataMaintenanceService.MANIFEST),
            manifest,
            keep_backups=1,
            indent=2,
        )
        try:
            from services.audit_log_service import AuditLogService
            AuditLogService.log_event("資料維護", "建立儲存點", record_id=folder_name, after={"kind": kind, "note": note, "file_count": manifest.get("file_count")}, result="成功", severity="重要")
        except Exception:
            pass
        return manifest

    @staticmethod
    def list_savepoints():
        DataMaintenanceService._ensure()
        result = []
        for name in sorted(os.listdir(DataMaintenanceService.BACKUP_DIR), reverse=True):
            folder = os.path.join(DataMaintenanceService.BACKUP_DIR, name)
            if not os.path.isdir(folder):
                continue
            manifest_path = os.path.join(folder, DataMaintenanceService.MANIFEST)
            if not os.path.isfile(manifest_path):
                continue
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    item = json.load(f)
                item["folder"] = folder
                result.append(item)
            except Exception:
                continue
        return result

    @staticmethod
    def latest_savepoint():
        items = DataMaintenanceService.list_savepoints()
        return items[0] if items else None

    @staticmethod
    def _find_savepoint(savepoint_id):
        for item in DataMaintenanceService.list_savepoints():
            if str(item.get("id", "")) == str(savepoint_id):
                return item
        raise Exception("找不到指定的資料儲存點。")

    @staticmethod
    def _delete_business_entries():
        deleted = []
        for name in DataMaintenanceService._business_entries():
            path = os.path.join(DataMaintenanceService.DATA_DIR, name)
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                elif os.path.exists(path):
                    os.remove(path)
                deleted.append(name)
            except Exception as e:
                raise Exception(f"清除 {name} 失敗：{e}")
        return deleted

    @staticmethod
    def restore_savepoint(savepoint_id, create_safety_backup=True):
        security.require_admin("還原資料儲存點")
        security.require_tier("advanced", "資料還原")
        selected = DataMaintenanceService._find_savepoint(savepoint_id)
        payload = os.path.join(selected["folder"], "data")
        if not os.path.isdir(payload):
            raise Exception("此儲存點缺少備份資料內容，無法還原。")

        safety = None
        if create_safety_backup:
            safety = DataMaintenanceService.create_savepoint(
                note=f"還原 {savepoint_id} 前自動建立",
                kind="pre_restore",
            )

        DataMaintenanceService._delete_business_entries()
        restored = []
        for name in sorted(os.listdir(payload)):
            src = os.path.join(payload, name)
            dst = os.path.join(DataMaintenanceService.DATA_DIR, name)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            restored.append(name)

        result = {
            "restored_from": selected,
            "safety_savepoint": safety,
            "restored_entries": restored,
            "restored_at": DataMaintenanceService._now(),
        }
        try:
            from services.audit_log_service import AuditLogService
            AuditLogService.log_event("資料維護", "還原資料儲存點", record_id=savepoint_id, after={"restored_entries": restored}, result="成功", severity="重要")
        except Exception:
            pass
        return result

    @staticmethod
    def restore_latest(create_safety_backup=True):
        latest = DataMaintenanceService.latest_savepoint()
        if not latest:
            raise Exception("目前沒有任何資料儲存點可以還原。")
        return DataMaintenanceService.restore_savepoint(
            latest.get("id"),
            create_safety_backup=create_safety_backup,
        )

    @staticmethod
    def clear_business_data(create_safety_backup=True):
        security.require_admin("清除全部業務資料")
        security.require_tier("advanced", "安全清除資料")
        safety = None
        if create_safety_backup:
            safety = DataMaintenanceService.create_savepoint(
                note="全部業務資料清除前自動建立",
                kind="pre_clear",
            )
        deleted = DataMaintenanceService._delete_business_entries()
        result = {
            "deleted_entries": deleted,
            "safety_savepoint": safety,
            "cleared_at": DataMaintenanceService._now(),
        }
        try:
            from services.audit_log_service import AuditLogService
            AuditLogService.log_event("資料維護", "清除全部業務資料", after={"deleted_entries": deleted}, result="成功", severity="高風險")
        except Exception:
            pass
        return result

    @staticmethod
    def delete_savepoint(savepoint_id):
        security.require_admin("刪除資料儲存點")
        security.require_tier("advanced", "資料儲存點管理")
        selected = DataMaintenanceService._find_savepoint(savepoint_id)
        folder = selected.get("folder")
        if folder and os.path.isdir(folder):
            shutil.rmtree(folder)
        try:
            from services.audit_log_service import AuditLogService
            AuditLogService.log_event("資料維護", "刪除儲存點", record_id=savepoint_id, result="成功", severity="警告")
        except Exception:
            pass
        return True

    @staticmethod
    def stats():
        items = DataMaintenanceService.list_savepoints()
        latest = items[0] if items else None
        return {
            "count": len(items),
            "latest": latest,
            "business_entries": DataMaintenanceService._business_entries(),
        }
