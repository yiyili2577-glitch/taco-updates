import json
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from services.app_paths import AppPaths
from services.build_config import BuildConfig


class BootstrapService:
    CORE_NAMES = {
        "users.json", "system_settings.json", "product_master.json", "suppliers.json",
        "warehouse_inventory.json", "customer_demand_snapshot.json", "finance_data.json",
    }

    @staticmethod
    def _has_business_data(path):
        p = Path(path)
        if not p.exists():
            return False
        return any((p / name).exists() for name in BootstrapService.CORE_NAMES)

    @staticmethod
    def _backup_legacy(source):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = AppPaths.backups_dir() / f"MIGRATION_PRE_V651_{stamp}.zip"
        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(source):
                for name in files:
                    src = Path(root) / name
                    try:
                        arc = str(src.relative_to(source))
                    except Exception:
                        arc = name
                    zf.write(src, arcname=arc)
        return out

    @staticmethod
    def migrate_legacy_if_needed():
        """正式 EXE 首次啟動時，把舊 Erp_app/data 安全搬到 ProgramData。

        規則：只有新資料區尚未有核心資料才會自動搬；搬之前一定先 ZIP 備份。
        """
        if not BuildConfig.is_production():
            return {"migrated": False, "reason": "development"}
        AppPaths.ensure_runtime_dirs()
        target = AppPaths.data_dir()
        if BootstrapService._has_business_data(target):
            return {"migrated": False, "reason": "target_has_data"}

        for source in AppPaths.legacy_data_candidates():
            try:
                source = source.resolve()
            except Exception:
                pass
            if source == target or not BootstrapService._has_business_data(source):
                continue
            backup = BootstrapService._backup_legacy(source)
            target.mkdir(parents=True, exist_ok=True)
            for item in source.iterdir():
                # 舊的人工儲存點搬到新版 Backups；audit logs 搬到 AuditLogs。
                if item.name == "backups" and item.is_dir():
                    shutil.copytree(item, AppPaths.backups_dir(), dirs_exist_ok=True)
                    continue
                if item.name == "audit_logs" and item.is_dir():
                    shutil.copytree(item, AppPaths.audit_dir(), dirs_exist_ok=True)
                    continue
                dst = target / item.name
                if item.is_dir():
                    shutil.copytree(item, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dst)
            marker = AppPaths.config_dir() / "migration_state.json"
            marker.write_text(json.dumps({
                "version": BuildConfig.VERSION,
                "migrated_at": datetime.now().isoformat(timespec="seconds"),
                "source": str(source),
                "backup": str(backup),
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"migrated": True, "source": str(source), "backup": str(backup)}
        return {"migrated": False, "reason": "legacy_not_found"}


    @staticmethod
    def sanitize_legacy_secrets():
        """正式版清理舊授權狀態：Token 搬進 DPAPI，舊 dev/advanced 不得沿用。"""
        if not BuildConfig.is_production():
            return False
        path = AppPaths.data_dir() / "system_settings.json"
        if not path.exists():
            return False
        try:
            from services.safe_storage import SafeStorage
            from services.secret_store import SecretStore
            data = SafeStorage.safe_read_json(str(path), default={})
            if not isinstance(data, dict):
                return False
            lic = data.get("license") if isinstance(data.get("license"), dict) else {}
            changed = False
            token = str(lic.get("license_key", "") or "").strip()
            if token:
                SecretStore.set_secret("license_token", token)
                lic["license_key"] = ""
                changed = True

            # 舊開發版可能保存 advanced + development_mode=True；正式版不得信任。
            try:
                from services.license_client_service import LicenseClientService
                receipt = LicenseClientService.current_receipt()
            except Exception:
                receipt = None
            lic["development_mode"] = False
            if receipt:
                lic["tier"] = str(receipt.get("tier", "general"))
                lic["license_status"] = "valid"
                lic["license_id"] = str(receipt.get("license_id", ""))
                lic["company"] = str(receipt.get("company", ""))
                lic["expires_at"] = str(receipt.get("expires_at", ""))
                lic["maintenance_until"] = str(receipt.get("maintenance_until", ""))
                lic["receipt_expires_at"] = str(receipt.get("receipt_expires_at", ""))
            else:
                lic["tier"] = "general"
                lic["license_status"] = "unverified"
                lic["license_id"] = ""
                lic["company"] = ""
                lic["expires_at"] = ""
                lic["maintenance_until"] = ""
                lic["receipt_expires_at"] = ""
            changed = True
            data["license"] = lic
            if changed:
                SafeStorage.atomic_write_json(str(path), data)
            return changed
        except Exception:
            return False

    @staticmethod
    def prepare_runtime():
        AppPaths.ensure_runtime_dirs()
        result = BootstrapService.migrate_legacy_if_needed()
        BootstrapService.sanitize_legacy_secrets()
        return result
