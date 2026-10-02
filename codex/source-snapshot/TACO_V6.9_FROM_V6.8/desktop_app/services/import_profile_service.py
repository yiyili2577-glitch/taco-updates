import math
import os

from services.system_settings_service import SystemSettingsService
from services.app_paths import AppPaths
from services.safe_storage import SafeStorage


class ImportProfileService:
    BASE_DIR = str(AppPaths.install_dir())
    DATA_DIR = str(AppPaths.data_dir())
    DATA_FILE = os.path.join(DATA_DIR, "import_profiles.json")
    DEFAULT_CONTAINER_CBM = 66.5

    @staticmethod
    def _ensure():
        os.makedirs(ImportProfileService.DATA_DIR, exist_ok=True)

    @staticmethod
    def _key(product_no, supplier_name=""):
        return f"{str(product_no).strip()}||{str(supplier_name).strip()}"

    @staticmethod
    def load_all():
        ImportProfileService._ensure()
        data = SafeStorage.safe_read_json(ImportProfileService.DATA_FILE, default={})
        return data if isinstance(data, dict) else {}

    @staticmethod
    def get_raw_profile(product_no, supplier_name=""):
        data = ImportProfileService.load_all()
        value = data.get(ImportProfileService._key(product_no, supplier_name), {})
        return value if isinstance(value, dict) else {}

    @staticmethod
    def has_profile(product_no, supplier_name=""):
        return bool(ImportProfileService.get_raw_profile(product_no, supplier_name))

    @staticmethod
    def get_profile(product_no, supplier_name=""):
        data = ImportProfileService.load_all()
        profile = data.get(ImportProfileService._key(product_no, supplier_name), {})
        defaults = {
            "currency": "USD",
            "unit_price": 0.0,
            "price_unit": "包",
            "purchase_qty_unit": "包",
            "packing_method": "",
            "units_per_carton": 0.0,
            "carton_length_cm": 0.0,
            "carton_width_cm": 0.0,
            "carton_height_cm": 0.0,
            "container_cbm": float(SystemSettingsService.load().get("warehouse", {}).get("container_cbm", ImportProfileService.DEFAULT_CONTAINER_CBM)),
        }
        result = {**defaults, **profile}
        # V4.5：貨櫃容量由「系統設定 → 倉庫管理」集中管理，避免各品項留下舊容量。
        result["container_cbm"] = float(
            SystemSettingsService.load().get("warehouse", {}).get(
                "container_cbm", ImportProfileService.DEFAULT_CONTAINER_CBM
            ) or ImportProfileService.DEFAULT_CONTAINER_CBM
        )
        return result

    @staticmethod
    def save_profile(product_no, supplier_name, profile):
        from services import security
        security.require_write_access("儲存進口／包裝設定")
        data = ImportProfileService.load_all()
        data[ImportProfileService._key(product_no, supplier_name)] = profile
        ImportProfileService._ensure()
        SafeStorage.atomic_write_json(ImportProfileService.DATA_FILE, data)

    @staticmethod
    def calculate(actual_qty, profile):
        def n(key, default=0):
            try:
                return float(profile.get(key, default) or 0)
            except Exception:
                return float(default)
        qty = max(0.0, float(actual_qty or 0))
        units_per_carton = n("units_per_carton")
        L, W, H = n("carton_length_cm"), n("carton_width_cm"), n("carton_height_cm")
        global_container = float(SystemSettingsService.load().get("warehouse", {}).get("container_cbm", ImportProfileService.DEFAULT_CONTAINER_CBM) or ImportProfileService.DEFAULT_CONTAINER_CBM)
        container_cbm = n("container_cbm", global_container) or global_container
        purchase_unit = str(profile.get("purchase_qty_unit", "箱"))
        if purchase_unit == "箱":
            cartons = qty
            base_units = qty * units_per_carton if units_per_carton > 0 else qty
        else:
            base_units = qty
            cartons = math.ceil(qty / units_per_carton) if units_per_carton > 0 else 0
        carton_cbm = (L * W * H) / 1_000_000 if L > 0 and W > 0 and H > 0 else 0
        total_cbm = cartons * carton_cbm
        max_cartons = math.floor(container_cbm / carton_cbm) if carton_cbm > 0 else 0
        usage = (total_cbm / container_cbm * 100) if container_cbm > 0 else 0
        remaining = max(0.0, container_cbm - total_cbm)
        unit_price = n("unit_price")
        price_unit = str(profile.get("price_unit", "包"))
        if price_unit == "箱":
            price_qty = cartons
        else:
            price_qty = base_units
        total_price = price_qty * unit_price
        return {
            "包裝方式": str(profile.get("packing_method", "")),
            "採購數量單位": purchase_unit,
            "幣別": str(profile.get("currency", "USD")),
            "單價": round(unit_price, 6),
            "計價單位": price_unit,
            "每箱數量": round(units_per_carton, 2),
            "紙箱長CM": round(L, 2),
            "紙箱寬CM": round(W, 2),
            "紙箱高CM": round(H, 2),
            "單箱CBM": round(carton_cbm, 4),
            "換算箱數": int(math.ceil(cartons)) if cartons else 0,
            "本次CBM": round(total_cbm, 2),
            "貨櫃CBM": round(container_cbm, 2),
            "貨櫃最大箱數": max_cartons,
            "貨櫃使用率%": round(usage, 2),
            "剩餘CBM": round(remaining, 2),
            "計價數量": round(price_qty, 2),
            "商品總價": round(total_price, 2),
        }
