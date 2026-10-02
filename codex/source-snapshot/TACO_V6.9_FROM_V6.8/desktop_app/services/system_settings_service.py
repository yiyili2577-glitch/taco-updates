import json
import os
import urllib.request
from copy import deepcopy
from datetime import datetime

from services.app_paths import AppPaths
from services.build_config import BuildConfig
from services.safe_storage import SafeStorage
from services import security


class SystemSettingsService:
    BASE_DIR = str(AppPaths.install_dir())
    DATA_DIR = str(AppPaths.data_dir())
    DATA_FILE = os.path.join(DATA_DIR, "system_settings.json")
    CURRENT_VERSION = BuildConfig.VERSION

    THEME_PRESETS = {
        "warm": {
            "name": "柔和米白",
            "window_bg": "#F6F3EF",
            "content_bg": "#F8F6F2",
            "card_bg": "#FFFFFF",
            "sidebar_bg": "#FBF8F4",
            "menu_text": "#3F4853",
            "content_text": "#18212B",
            "muted_text": "#728091",
            "accent": "#5DBDAD",
            "border": "#E5E1DB",
            "table_header_bg": "#F4F6F8",
        },
        "light": {
            "name": "清爽淺灰",
            "window_bg": "#EEF2F5",
            "content_bg": "#F4F7F9",
            "card_bg": "#FFFFFF",
            "sidebar_bg": "#F7F9FB",
            "menu_text": "#3E4A59",
            "content_text": "#17202A",
            "muted_text": "#667487",
            "accent": "#5F9FE8",
            "border": "#DCE3EA",
            "table_header_bg": "#F1F5F8",
        },
        "blue": {
            "name": "淡藍",
            "window_bg": "#EAF2F8",
            "content_bg": "#F1F7FB",
            "card_bg": "#FFFFFF",
            "sidebar_bg": "#E6F0F7",
            "menu_text": "#314A5F",
            "content_text": "#152C3B",
            "muted_text": "#668094",
            "accent": "#4D9BE6",
            "border": "#D3E1EC",
            "table_header_bg": "#EDF4F9",
        },
        "green": {
            "name": "淡綠",
            "window_bg": "#ECF5F1",
            "content_bg": "#F3F8F5",
            "card_bg": "#FFFFFF",
            "sidebar_bg": "#EAF4EF",
            "menu_text": "#355247",
            "content_text": "#17362B",
            "muted_text": "#668176",
            "accent": "#55B69A",
            "border": "#D4E5DE",
            "table_header_bg": "#EDF6F2",
        },
        "dark": {
            "name": "深色",
            "window_bg": "#151A20",
            "content_bg": "#1B222A",
            "card_bg": "#222B35",
            "sidebar_bg": "#171E25",
            "menu_text": "#D9E2EA",
            "content_text": "#F4F7FA",
            "muted_text": "#9BAABA",
            "accent": "#66C8B6",
            "border": "#34404C",
            "table_header_bg": "#26313C",
        },
    }

    DEFAULTS = {
        "warehouse": {"container_cbm": 66.5},
        "purchase": {
            "default_safety_months": 2.0,
            "default_production_days": 45,
            "default_shipping_days": 14,
            "default_customs_days": 7,
            "default_moq": 0,
            "default_multiple": 1,
        },
        "license": {
            "tier": "advanced" if BuildConfig.is_development() else "general",
            "development_mode": BuildConfig.is_development(),
            # V6.5.1：正式版 Token 改存 Windows DPAPI，這個欄位只留給舊資料相容，永遠不再寫入 Token。
            "license_key": "",
            "license_server_url": "",
            "license_status": "development" if BuildConfig.is_development() else "unverified",
            "license_id": "",
            "company": "",
            "expires_at": "",
            "maintenance_until": "",
            "max_devices": 1,
            "update_channel": "stable",
            "receipt_expires_at": "",
            "verified_at": "",
        },
        "appearance": {
            "preset": "warm",
            **{k: v for k, v in THEME_PRESETS["warm"].items() if k != "name"},
        },
        "export": {
            "default_folder": "exports",
            "include_timestamp": True,
            "default_excel": True,
            "default_pdf": True,
        },
        "account": {
            "display_name": "",
            "email": "",
            "role": "採購管理者",
            "company": "",
        },
        "connection": {
            "mode": "Excel / PDF",
            "server": "",
            "database": "",
            "username": "",
            "auth_type": "SQL Server 驗證",
            "driver": "ODBC Driver 18 for SQL Server",
            "timeout": 5,
            "read_only": True,
        },
        "update": {
            "current_version": CURRENT_VERSION,
            "update_url": "",
            "last_checked_at": "",
        },
    }

    TIER_NAMES = {"general": "一般版", "intermediate": "中階版", "advanced": "高級版"}
    TIER_FEATURES = {
        "general": [
            "產品主檔與供應商基本資料",
            "客戶需求 PDF / Excel 匯入",
            "基本庫存分析",
            "基本首頁儀表板",
            "Excel 匯出",
        ],
        "intermediate": [
            "一般版全部功能",
            "三倉庫存管理",
            "採購建議 / MOQ / 安全庫存",
            "客戶需求與庫存串接",
            "跨倉調撥建議",
            "PDF 匯出",
        ],
        "advanced": [
            "中階版全部功能",
            "進口貨櫃 / CBM / 混櫃規劃",
            "多供應商與幣別成本分析",
            "ERP SQL Server 連線",
            "進階儀表板 / 通知中心",
            "帳號 / 更新 / 授權管理",
            "資料儲存點 / 還原 / 安全清除",
            "資料歷程 / 操作紀錄 / 稽核中心",
        ],
    }

    @staticmethod
    def _ensure():
        os.makedirs(SystemSettingsService.DATA_DIR, exist_ok=True)

    @staticmethod
    def _merge(defaults, loaded):
        result = deepcopy(defaults)
        if not isinstance(loaded, dict):
            return result
        for key, value in loaded.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key].update(value)
            else:
                result[key] = value
        return result

    @staticmethod
    def load():
        SystemSettingsService._ensure()
        loaded = SafeStorage.safe_read_json(SystemSettingsService.DATA_FILE, default=None)
        result = SystemSettingsService._merge(SystemSettingsService.DEFAULTS, loaded)
        if BuildConfig.is_production():
            # 正式 EXE 的授權狀態不能直接相信從舊版搬入的 system_settings.json。
            # UI / service 只看 Ed25519 驗證過且仍有效的 signed receipt。
            lic = result.setdefault("license", {})
            lic["development_mode"] = False
            lic["license_key"] = ""
            try:
                from services.license_client_service import LicenseClientService
                receipt = LicenseClientService.current_receipt()
            except Exception:
                receipt = None
            if receipt:
                lic["tier"] = str(receipt.get("tier", "general"))
                lic["license_status"] = "valid"
                lic["license_id"] = str(receipt.get("license_id", ""))
                lic["company"] = str(receipt.get("company", ""))
                lic["expires_at"] = str(receipt.get("expires_at", ""))
                lic["maintenance_until"] = str(receipt.get("maintenance_until", ""))
                lic["max_devices"] = int(receipt.get("max_devices", 1) or 1)
                lic["update_channel"] = str(receipt.get("update_channel", "stable"))
                lic["receipt_expires_at"] = str(receipt.get("receipt_expires_at", ""))
            else:
                # 沒有可驗證 receipt 時一律 fail closed 成一般版未授權。
                lic["tier"] = "general"
                lic["license_status"] = "unverified"
                lic["license_id"] = ""
                lic["company"] = ""
                lic["expires_at"] = ""
                lic["maintenance_until"] = ""
                lic["receipt_expires_at"] = ""
        return result

    @staticmethod
    def save(settings):
        security.require_admin("修改系統設定")
        SystemSettingsService._ensure()
        merged = SystemSettingsService._merge(SystemSettingsService.DEFAULTS, settings)
        merged["update"]["current_version"] = SystemSettingsService.CURRENT_VERSION
        if BuildConfig.is_production():
            # 正式版不接受 JSON 自行開啟 development_mode / advanced，也不保存 Token 明碼。
            merged.setdefault("license", {})["development_mode"] = False
            merged["license"]["license_key"] = ""
            try:
                from services.license_client_service import LicenseClientService
                receipt = LicenseClientService.current_receipt()
            except Exception:
                receipt = None
            merged["license"]["tier"] = str((receipt or {}).get("tier", "general"))
            merged["license"]["license_status"] = "valid" if receipt else "unverified"
        SafeStorage.atomic_write_json(SystemSettingsService.DATA_FILE, merged)
        return merged

    @staticmethod
    def update_section(section, values):
        data = SystemSettingsService.load()
        if section not in data or not isinstance(data.get(section), dict):
            data[section] = {}
        data[section].update(values)
        return SystemSettingsService.save(data)

    @staticmethod
    def apply_theme_preset(preset):
        preset = str(preset or "warm")
        if preset not in SystemSettingsService.THEME_PRESETS:
            preset = "warm"
        colors = deepcopy(SystemSettingsService.THEME_PRESETS[preset])
        colors.pop("name", None)
        colors["preset"] = preset
        return SystemSettingsService.update_section("appearance", colors)

    @staticmethod
    def get_tier():
        if BuildConfig.is_production():
            try:
                from services.license_client_service import LicenseClientService
                return LicenseClientService.entitlement_tier()
            except Exception:
                return "general"
        return str(SystemSettingsService.load().get("license", {}).get("tier", "general"))

    @staticmethod
    def is_development_mode():
        # 正式 frozen build / TACO_BUILD_MODE=prod 永遠不能被 system_settings.json 打開開發模式。
        if BuildConfig.is_production():
            return False
        return bool(SystemSettingsService.load().get("license", {}).get("development_mode", True))

    @staticmethod
    def tier_rank(tier):
        return {"general": 1, "intermediate": 2, "advanced": 3}.get(str(tier), 1)

    @staticmethod
    def has_tier(required):
        return SystemSettingsService.tier_rank(SystemSettingsService.get_tier()) >= SystemSettingsService.tier_rank(required)

    @staticmethod
    def effective_has_tier(required):
        if SystemSettingsService.is_development_mode():
            return SystemSettingsService.has_tier(required)
        # 正式版只信任 Ed25519 簽章且仍在離線緩衝期限內的 receipt。
        try:
            from services.license_client_service import LicenseClientService
            receipt = LicenseClientService.current_receipt()
        except Exception:
            receipt = None
        if not receipt:
            return required == "general"
        tier = str(receipt.get("tier", "general"))
        return SystemSettingsService.tier_rank(tier) >= SystemSettingsService.tier_rank(required)

    @staticmethod
    def verify_license(token, server_url, timeout=8):
        from services.license_client_service import LicenseClientService
        receipt = LicenseClientService.verify_online(token, server_url, timeout=timeout)
        tier = str(receipt.get("tier", "general"))
        # 只保存公開 metadata；Token 本體已由 SecretStore 以 Windows DPAPI 儲存。
        SystemSettingsService.update_section("license", {
            "tier": tier,
            "development_mode": False,
            "license_key": "",
            "license_server_url": str(server_url or "").strip(),
            "license_status": "valid",
            "license_id": str(receipt.get("license_id", "")),
            "company": str(receipt.get("company", "")),
            "expires_at": str(receipt.get("expires_at", "")),
            "maintenance_until": str(receipt.get("maintenance_until", "")),
            "max_devices": int(receipt.get("max_devices", 1) or 1),
            "update_channel": str(receipt.get("update_channel", "stable")),
            "receipt_expires_at": str(receipt.get("receipt_expires_at", "")),
            "verified_at": datetime.now().isoformat(timespec="seconds"),
        })
        # 舊 UI 期待 data.get('tier')，維持相容。
        return {**receipt, "valid": True}

    @staticmethod
    def mark_update_checked():
        return SystemSettingsService.update_section("update", {"last_checked_at": datetime.now().isoformat(timespec="seconds")})
