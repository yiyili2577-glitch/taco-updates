import os
import pandas as pd

from services.app_paths import AppPaths
from services.safe_storage import SafeStorage


class WarehouseService:
    BASE_DIR = str(AppPaths.install_dir())
    DATA_DIR = str(AppPaths.data_dir())
    SETTINGS_FILE = os.path.join(DATA_DIR, "warehouse_settings.json")
    INVENTORY_FILE = os.path.join(DATA_DIR, "warehouse_inventory.json")
    DEFAULT_NAMES = ["倉庫1", "倉庫2", "倉庫3"]

    @staticmethod
    def _ensure():
        os.makedirs(WarehouseService.DATA_DIR, exist_ok=True)

    @staticmethod
    def load_names():
        WarehouseService._ensure()
        data = SafeStorage.safe_read_json(WarehouseService.SETTINGS_FILE, default={})
        names = data.get("names", []) if isinstance(data, dict) else []
        names = [str(x).strip() for x in names if str(x).strip()]
        if len(names) >= 3:
            return names[:3]
        return WarehouseService.DEFAULT_NAMES.copy()

    @staticmethod
    def save_names(names):
        from services import security
        security.require_write_access("修改倉庫名稱")
        WarehouseService._ensure()
        names = [(str(x).strip() or WarehouseService.DEFAULT_NAMES[i]) for i, x in enumerate((names + WarehouseService.DEFAULT_NAMES)[:3])]
        SafeStorage.atomic_write_json(WarehouseService.SETTINGS_FILE, {"names": names})
        return names

    @staticmethod
    def load_inventory():
        WarehouseService._ensure()
        data = SafeStorage.safe_read_json(WarehouseService.INVENTORY_FILE, default={})
        return data if isinstance(data, dict) else {}

    @staticmethod
    def save_inventory(data):
        from services import security
        security.require_write_access("儲存倉庫庫存")
        WarehouseService._ensure()
        SafeStorage.atomic_write_json(WarehouseService.INVENTORY_FILE, data)

    @staticmethod
    def enrich_dataframe(df, initialize_from_current=True):
        if df is None or df.empty or "產品編號" not in df.columns:
            return df
        result = df.copy()
        names = WarehouseService.load_names()
        saved = WarehouseService.load_inventory()
        for i, name in enumerate(names):
            values = []
            for _, row in result.iterrows():
                pno = str(row.get("產品編號", "")).strip()
                record = saved.get(pno, {})
                if str(i) in record:
                    value = record.get(str(i), 0)
                elif initialize_from_current and i == 0:
                    value = row.get("目前庫存", 0)
                else:
                    value = 0
                try:
                    value = float(value)
                except Exception:
                    value = 0.0
                values.append(value)
            result[name] = values
        result["三倉庫存合計"] = result[names].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
        return result

    @staticmethod
    def save_from_dataframe(df):
        if df is None or df.empty or "產品編號" not in df.columns:
            return 0
        names = WarehouseService.load_names()
        data = WarehouseService.load_inventory()
        count = 0
        for _, row in df.iterrows():
            pno = str(row.get("產品編號", "")).strip()
            if not pno:
                continue
            rec = {}
            for i, name in enumerate(names):
                try:
                    rec[str(i)] = float(row.get(name, 0) or 0)
                except Exception:
                    rec[str(i)] = 0.0
            data[pno] = rec
            count += 1
        WarehouseService.save_inventory(data)
        return count
