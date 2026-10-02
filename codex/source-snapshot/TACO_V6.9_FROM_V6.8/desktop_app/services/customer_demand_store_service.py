import os
from datetime import datetime

import pandas as pd

from services.app_paths import AppPaths
from services.safe_storage import SafeStorage


class CustomerDemandStoreService:
    BASE_DIR = str(AppPaths.install_dir())
    DATA_DIR = str(AppPaths.data_dir())
    DATA_FILE = os.path.join(DATA_DIR, "customer_demand_snapshot.json")

    @staticmethod
    def ensure_data_folder():
        os.makedirs(CustomerDemandStoreService.DATA_DIR, exist_ok=True)

    @staticmethod
    def _to_json_safe(value):
        if value is None:
            return None
        try:
            if pd.isna(value):
                return None
        except Exception:
            pass
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        if hasattr(value, "item"):
            try:
                return value.item()
            except Exception:
                pass
        return value

    @staticmethod
    def dataframe_to_records(df):
        if df is None or df.empty:
            return []
        return [
            {
                str(column): CustomerDemandStoreService._to_json_safe(row.get(column))
                for column in df.columns
            }
            for _, row in df.iterrows()
        ]

    @staticmethod
    def save_snapshot(summary_df, detail_df=None, source_file=""):
        from services import security
        security.require_write_access("儲存客戶需求")
        """V4.7：除了彙總，也保存需求明細，供首頁日期區間與需求趨勢使用。"""
        CustomerDemandStoreService.ensure_data_folder()
        payload = {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "source_file": str(source_file or ""),
            "summary": CustomerDemandStoreService.dataframe_to_records(summary_df),
            "detail": CustomerDemandStoreService.dataframe_to_records(detail_df),
            "detail_count": int(len(detail_df)) if detail_df is not None else 0,
        }
        SafeStorage.atomic_write_json(CustomerDemandStoreService.DATA_FILE, payload, indent=4)
        return payload

    @staticmethod
    def load_snapshot():
        CustomerDemandStoreService.ensure_data_folder()
        default = {
            "updated_at": "",
            "source_file": "",
            "summary": [],
            "detail": [],
            "detail_count": 0,
        }
        data = SafeStorage.safe_read_json(CustomerDemandStoreService.DATA_FILE, default=None)
        if not isinstance(data, dict):
            return default
        return {
            "updated_at": str(data.get("updated_at", "")),
            "source_file": str(data.get("source_file", "")),
            "summary": data.get("summary", []) if isinstance(data.get("summary", []), list) else [],
            "detail": data.get("detail", []) if isinstance(data.get("detail", []), list) else [],
            "detail_count": int(data.get("detail_count", 0) or 0),
        }

    @staticmethod
    def _numeric_columns(df, columns):
        for column in columns:
            if column in df.columns:
                df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)
        return df

    @staticmethod
    def load_summary():
        snapshot = CustomerDemandStoreService.load_snapshot()
        rows = snapshot.get("summary", [])
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        return CustomerDemandStoreService._numeric_columns(
            df,
            [
                "總需求量", "客戶直送量", "公司入庫量", "需求筆數", "客戶數",
                "供應商直送需求", "倉庫出貨需求", "公司入庫需求",
                "倉庫1出貨需求", "倉庫2出貨需求", "倉庫3出貨需求",
            ],
        )

    @staticmethod
    def load_detail():
        snapshot = CustomerDemandStoreService.load_snapshot()
        rows = snapshot.get("detail", [])
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        return CustomerDemandStoreService._numeric_columns(df, ["數量", "需求數量", "箱數", "每箱數量"])

    @staticmethod
    def clear_snapshot():
        from services import security
        security.require_write_access("清除客戶需求")
        if os.path.exists(CustomerDemandStoreService.DATA_FILE):
            os.remove(CustomerDemandStoreService.DATA_FILE)

    @staticmethod
    def get_status():
        snapshot = CustomerDemandStoreService.load_snapshot()
        return {
            "updated_at": snapshot.get("updated_at", ""),
            "source_file": snapshot.get("source_file", ""),
            "product_count": len(snapshot.get("summary", [])),
            "detail_count": snapshot.get("detail_count", 0),
            "has_detail_snapshot": bool(snapshot.get("detail", [])),
        }
