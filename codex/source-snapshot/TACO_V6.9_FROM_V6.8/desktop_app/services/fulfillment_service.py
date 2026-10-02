import os
import hashlib
import pandas as pd

from services.warehouse_service import WarehouseService
from services.app_paths import AppPaths
from services.safe_storage import SafeStorage


class FulfillmentService:
    """客戶需求履約/出貨來源設定。

    預設規則：
    - 原配送類型=公司入庫 -> 公司入庫（已安排入庫，不再當成新的採購需求）
    - 其他 -> 供應商直送（不使用公司庫存）

    使用者可將客戶直送改成任一倉庫出貨，該需求才會扣公司庫存。
    """

    BASE_DIR = str(AppPaths.install_dir())
    DATA_DIR = str(AppPaths.data_dir())
    DATA_FILE = os.path.join(DATA_DIR, "fulfillment_routes.json")

    MODE_SUPPLIER_DIRECT = "供應商直送"
    MODE_WAREHOUSE = "倉庫出貨"
    MODE_COMPANY_INBOUND = "公司入庫"

    @staticmethod
    def _ensure():
        os.makedirs(FulfillmentService.DATA_DIR, exist_ok=True)

    @staticmethod
    def _text(value):
        if value is None:
            return ""
        try:
            if pd.isna(value):
                return ""
        except Exception:
            pass
        return str(value).strip()

    @staticmethod
    def row_key(row):
        fields = [
            "來源檔案", "PDF頁碼", "採購單號", "採購日期", "客戶", "客戶訂號",
            "PDF品名規格", "原始產品編號", "產品編號", "數量", "到貨日期", "配送內容"
        ]
        raw = "||".join(FulfillmentService._text(row.get(k, "")) for k in fields)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def load_routes():
        FulfillmentService._ensure()
        data = SafeStorage.safe_read_json(FulfillmentService.DATA_FILE, default={})
        return data if isinstance(data, dict) else {}

    @staticmethod
    def save_routes(routes):
        from services import security
        security.require_write_access("儲存履約／出貨分流")
        FulfillmentService._ensure()
        SafeStorage.atomic_write_json(FulfillmentService.DATA_FILE, routes)

    @staticmethod
    def default_route(row):
        delivery_type = FulfillmentService._text(row.get("配送類型", ""))
        if delivery_type == "公司入庫":
            return {"mode": FulfillmentService.MODE_COMPANY_INBOUND, "warehouse": ""}
        return {"mode": FulfillmentService.MODE_SUPPLIER_DIRECT, "warehouse": ""}

    @staticmethod
    def apply_routes(df):
        if df is None or df.empty:
            return df
        result = df.copy()
        saved = FulfillmentService.load_routes()
        modes = []
        warehouses = []
        keys = []
        for _, row in result.iterrows():
            key = FulfillmentService.row_key(row)
            rule = saved.get(key) or FulfillmentService.default_route(row)
            mode = FulfillmentService._text(rule.get("mode", ""))
            warehouse = FulfillmentService._text(rule.get("warehouse", ""))
            if mode not in {
                FulfillmentService.MODE_SUPPLIER_DIRECT,
                FulfillmentService.MODE_WAREHOUSE,
                FulfillmentService.MODE_COMPANY_INBOUND,
            }:
                rule = FulfillmentService.default_route(row)
                mode = rule["mode"]
                warehouse = rule["warehouse"]
            if mode != FulfillmentService.MODE_WAREHOUSE:
                warehouse = ""
            modes.append(mode)
            warehouses.append(warehouse)
            keys.append(key)
        result["履約方式"] = modes
        result["出貨倉"] = warehouses
        result["履約Key"] = keys
        return result

    @staticmethod
    def save_row_route(row, mode, warehouse=""):
        key = FulfillmentService.row_key(row)
        routes = FulfillmentService.load_routes()
        if mode != FulfillmentService.MODE_WAREHOUSE:
            warehouse = ""
        routes[key] = {"mode": str(mode).strip(), "warehouse": str(warehouse).strip()}
        FulfillmentService.save_routes(routes)
        return key

    @staticmethod
    def save_bulk(records):
        routes = FulfillmentService.load_routes()
        count = 0
        for record in records:
            key = str(record.get("key", "")).strip()
            if not key:
                continue
            mode = str(record.get("mode", "")).strip()
            warehouse = str(record.get("warehouse", "")).strip()
            if mode != FulfillmentService.MODE_WAREHOUSE:
                warehouse = ""
            routes[key] = {"mode": mode, "warehouse": warehouse}
            count += 1
        FulfillmentService.save_routes(routes)
        return count

    @staticmethod
    def summarize(detail_df):
        columns = [
            "產品編號", "供應商直送需求", "倉庫出貨需求", "公司入庫需求", "計算用採購需求"
        ]
        if detail_df is None or detail_df.empty or "產品編號" not in detail_df.columns:
            return pd.DataFrame(columns=columns)

        df = FulfillmentService.apply_routes(detail_df)
        df = df[df["產品編號"].fillna("").astype(str).str.strip() != ""].copy()
        if "驗證狀態" in df.columns:
            # 紅色人工確認資料不進計算；正常/自動修正/舊版格式都可進
            df = df[~df["驗證狀態"].astype(str).str.contains("人工確認", na=False)]
        if df.empty:
            return pd.DataFrame(columns=columns)

        df["數量"] = pd.to_numeric(df["數量"], errors="coerce").fillna(0) if "數量" in df.columns else 0.0
        warehouse_names = WarehouseService.load_names()
        rows = []
        for product_no, group in df.groupby("產品編號", dropna=False):
            supplier_direct = group.loc[group["履約方式"] == FulfillmentService.MODE_SUPPLIER_DIRECT, "數量"].sum()
            warehouse_out = group.loc[group["履約方式"] == FulfillmentService.MODE_WAREHOUSE, "數量"].sum()
            company_inbound = group.loc[group["履約方式"] == FulfillmentService.MODE_COMPANY_INBOUND, "數量"].sum()
            row = {
                "產品編號": str(product_no).strip(),
                "供應商直送需求": float(supplier_direct),
                "倉庫出貨需求": float(warehouse_out),
                "公司入庫需求": float(company_inbound),
                "計算用採購需求": float(supplier_direct + warehouse_out),
            }
            for name in warehouse_names:
                qty = group.loc[
                    (group["履約方式"] == FulfillmentService.MODE_WAREHOUSE)
                    & (group["出貨倉"].astype(str) == name),
                    "數量"
                ].sum()
                row[f"{name}出貨需求"] = float(qty)
            rows.append(row)
        return pd.DataFrame(rows)
