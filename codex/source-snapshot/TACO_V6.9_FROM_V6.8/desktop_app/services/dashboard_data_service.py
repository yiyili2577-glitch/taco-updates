import math
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta

import pandas as pd

from services.product_master_service import ProductMasterService
from services.supplier_service import SupplierService
from services.warehouse_service import WarehouseService
from services.customer_demand_store_service import CustomerDemandStoreService
from services.import_profile_service import ImportProfileService
from services.system_settings_service import SystemSettingsService
from services.app_paths import AppPaths
from services.safe_storage import SafeStorage, get_logger


class DashboardDataService:
    BASE_DIR = str(AppPaths.install_dir())
    DATA_DIR = str(AppPaths.data_dir())
    INVENTORY_FILE = os.path.join(DATA_DIR, "dashboard_inventory_snapshot.json")
    PURCHASE_FILE = os.path.join(DATA_DIR, "dashboard_purchase_snapshot.json")

    @staticmethod
    def _ensure():
        os.makedirs(DashboardDataService.DATA_DIR, exist_ok=True)

    @staticmethod
    def _safe(v):
        if v is None:
            return None
        try:
            if pd.isna(v):
                return None
        except Exception:
            pass
        if hasattr(v, "item"):
            try:
                return v.item()
            except Exception:
                pass
        return v

    @staticmethod
    def _records(df, limit=None):
        if df is None or df.empty:
            return []
        working = df.head(limit) if limit else df
        return [
            {str(c): DashboardDataService._safe(row.get(c)) for c in working.columns}
            for _, row in working.iterrows()
        ]

    @staticmethod
    def _write(path, payload):
        DashboardDataService._ensure()
        SafeStorage.atomic_write_json(path, payload)

    @staticmethod
    def _read(path):
        data = SafeStorage.safe_read_json(path, default={})
        return data if isinstance(data, dict) else {}

    @staticmethod
    def save_inventory_snapshot(df, source_file=""):
        if df is None:
            return
        DashboardDataService._write(DashboardDataService.INVENTORY_FILE, {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "source_file": str(source_file or ""),
            "rows": DashboardDataService._records(df),
        })

    @staticmethod
    def save_purchase_snapshot(df):
        if df is None:
            return
        DashboardDataService._write(DashboardDataService.PURCHASE_FILE, {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "rows": DashboardDataService._records(df),
        })

    @staticmethod
    def load_inventory_df():
        data = DashboardDataService._read(DashboardDataService.INVENTORY_FILE)
        return pd.DataFrame(data.get("rows", [])), data

    @staticmethod
    def load_purchase_df():
        data = DashboardDataService._read(DashboardDataService.PURCHASE_FILE)
        return pd.DataFrame(data.get("rows", [])), data

    @staticmethod
    def _num(v):
        try:
            return float(v or 0)
        except Exception:
            return 0.0

    @staticmethod
    def _parse_date(value):
        text = str(value or "").strip()
        if not text:
            return None
        # ISO / Gregorian
        try:
            ts = pd.to_datetime(text, errors="coerce")
            if not pd.isna(ts):
                return ts.to_pydatetime().date()
        except Exception:
            pass
        # ROC date 115/08/07
        m = re.search(r"\b(\d{2,3})/(\d{1,2})/(\d{1,2})\b", text)
        if m:
            try:
                y, mo, d = map(int, m.groups())
                if y < 1911:
                    y += 1911
                return datetime(y, mo, d).date()
            except Exception:
                return None
        return None

    @staticmethod
    def _date_filtered_detail(detail_df, days):
        if detail_df is None or detail_df.empty or not days:
            return detail_df.copy() if detail_df is not None else pd.DataFrame()
        work = detail_df.copy()
        date_col = next((c for c in ["到貨日期", "採購日期", "需求日期", "日期"] if c in work.columns), None)
        if not date_col:
            return work
        work["_dashboard_date"] = work[date_col].apply(DashboardDataService._parse_date)
        cutoff = datetime.now().date() - timedelta(days=max(0, int(days) - 1))
        return work[work["_dashboard_date"].apply(lambda d: d is not None and d >= cutoff)].copy()

    @staticmethod
    def _top_records(df, qty_col, limit=10):
        if df is None or df.empty or not qty_col or qty_col not in df.columns:
            return []
        work = df.copy()
        work["_qty"] = pd.to_numeric(work[qty_col], errors="coerce").fillna(0)
        work = work[work["_qty"] > 0].sort_values("_qty", ascending=False).head(limit)
        return [
            {
                "產品編號": str(row.get("產品編號", "")),
                "產品名稱": str(row.get("產品名稱", "")),
                "數量": float(row.get("_qty", 0)),
                "狀態": str(row.get("狀態", "")),
            }
            for _, row in work.iterrows()
        ]

    @staticmethod
    def _demand_metrics(summary_df, detail_df, days):
        filtered_detail = DashboardDataService._date_filtered_detail(detail_df, days)
        if days and filtered_detail is not None and not filtered_detail.empty:
            qty_col = next((c for c in ["數量", "需求數量", "總需求量"] if c in filtered_detail.columns), None)
            if qty_col:
                filtered_detail["_qty"] = pd.to_numeric(filtered_detail[qty_col], errors="coerce").fillna(0)
                demand_total = float(filtered_detail["_qty"].sum())
                group_cols = [c for c in ["產品編號", "產品名稱"] if c in filtered_detail.columns]
                top_demand = []
                if group_cols:
                    grouped = filtered_detail.groupby(group_cols, dropna=False)["_qty"].sum().reset_index().sort_values("_qty", ascending=False).head(10)
                    for _, row in grouped.iterrows():
                        top_demand.append({
                            "產品編號": str(row.get("產品編號", "")),
                            "產品名稱": str(row.get("產品名稱", "")),
                            "數量": float(row.get("_qty", 0)),
                        })
                return demand_total, top_demand, filtered_detail
        demand_total = 0.0
        top_demand = []
        if summary_df is not None and not summary_df.empty and "總需求量" in summary_df.columns:
            work = summary_df.copy()
            work["_qty"] = pd.to_numeric(work["總需求量"], errors="coerce").fillna(0)
            demand_total = float(work["_qty"].sum())
            for _, row in work.sort_values("_qty", ascending=False).head(10).iterrows():
                top_demand.append({
                    "產品編號": str(row.get("產品編號", "")),
                    "產品名稱": str(row.get("產品名稱", "")),
                    "數量": float(row.get("_qty", 0)),
                })
        return demand_total, top_demand, filtered_detail

    @staticmethod
    def _demand_trend(detail_df):
        if detail_df is None or detail_df.empty:
            return [], []
        qty_col = next((c for c in ["數量", "需求數量", "總需求量"] if c in detail_df.columns), None)
        date_col = next((c for c in ["到貨日期", "採購日期", "需求日期", "日期"] if c in detail_df.columns), None)
        if not qty_col or not date_col:
            return [], []
        work = detail_df.copy()
        work["_date"] = work[date_col].apply(DashboardDataService._parse_date)
        work["_qty"] = pd.to_numeric(work[qty_col], errors="coerce").fillna(0)
        work = work[work["_date"].notna()]
        if work.empty:
            return [], []
        grouped = work.groupby("_date")["_qty"].sum().sort_index()
        # 最多顯示最近 12 個日期點，避免首頁過密。
        grouped = grouped.tail(12)
        return [d.strftime("%m/%d") for d in grouped.index], [float(v) for v in grouped.values]

    @staticmethod
    def _purchase_cost_and_cbm(purchase_df):
        by_supplier_currency = defaultdict(float)
        currency_totals = defaultdict(float)
        total_cbm = 0.0
        line_count = 0
        if purchase_df is None or purchase_df.empty:
            return by_supplier_currency, currency_totals, 0.0, 0
        qty_col = "實際採購量" if "實際採購量" in purchase_df.columns else ("建議採購量" if "建議採購量" in purchase_df.columns else None)
        if not qty_col:
            return by_supplier_currency, currency_totals, 0.0, 0
        for _, row in purchase_df.iterrows():
            qty = DashboardDataService._num(row.get(qty_col, 0))
            if qty <= 0:
                continue
            product_no = str(row.get("產品編號", "")).strip()
            supplier = str(row.get("本次採購供應商", "")).strip()
            profile = ImportProfileService.get_profile(product_no, supplier)
            calc = ImportProfileService.calculate(qty, profile)
            currency = str(calc.get("幣別", "USD") or "USD")
            amount = DashboardDataService._num(calc.get("商品總價", 0))
            cbm = DashboardDataService._num(calc.get("本次CBM", 0))
            by_supplier_currency[(supplier or "未設定供應商", currency)] += amount
            currency_totals[currency] += amount
            total_cbm += cbm
            line_count += 1
        return by_supplier_currency, currency_totals, total_cbm, line_count

    @staticmethod
    def summary(days=None):
        products = ProductMasterService.load_products()
        suppliers = SupplierService.load_suppliers()
        warehouse_names = WarehouseService.load_names()
        warehouse_inventory = WarehouseService.load_inventory()
        customer_status = CustomerDemandStoreService.get_status()
        demand_df = CustomerDemandStoreService.load_summary()
        demand_detail_df = CustomerDemandStoreService.load_detail()
        inventory_df, inventory_meta = DashboardDataService.load_inventory_df()
        purchase_df, purchase_meta = DashboardDataService.load_purchase_df()

        warehouse_totals = [0.0, 0.0, 0.0]
        for rec in warehouse_inventory.values():
            if not isinstance(rec, dict):
                continue
            for i in range(3):
                warehouse_totals[i] += DashboardDataService._num(rec.get(str(i), 0))
        total_stock = sum(warehouse_totals)

        demand_total, top_demand, filtered_detail = DashboardDataService._demand_metrics(demand_df, demand_detail_df, days)
        trend_labels, trend_values = DashboardDataService._demand_trend(filtered_detail)

        unmapped = 0
        if demand_df is not None and not demand_df.empty and "需求筆數" in demand_df.columns:
            mapped_detail = int(pd.to_numeric(demand_df["需求筆數"], errors="coerce").fillna(0).sum())
            unmapped = max(0, int(customer_status.get("detail_count", 0)) - mapped_detail)

        need_purchase = urgent = 0
        purchase_total = 0.0
        qty_col = None
        if purchase_df is not None and not purchase_df.empty:
            if "實際採購量" in purchase_df.columns:
                qty_col = "實際採購量"
            elif "建議採購量" in purchase_df.columns:
                qty_col = "建議採購量"
            if qty_col:
                q = pd.to_numeric(purchase_df[qty_col], errors="coerce").fillna(0)
                need_purchase = int((q > 0).sum())
                purchase_total = float(q.sum())
            if "狀態" in purchase_df.columns:
                urgent = int(purchase_df["狀態"].astype(str).str.contains("立即|急需|缺口", regex=True).sum())

        # 庫存健康度
        health = {"正常": 0, "注意": 0, "缺貨": 0, "無資料": 0}
        alerts = []
        if inventory_df is not None and not inventory_df.empty:
            for _, row in inventory_df.iterrows():
                status = str(row.get("狀態", "")).strip()
                if re.search(r"缺貨|急需", status):
                    health["缺貨"] += 1
                elif re.search(r"注意|偏低|不足", status):
                    health["注意"] += 1
                elif re.search(r"正常", status):
                    health["正常"] += 1
                else:
                    health["無資料"] += 1
            working = inventory_df.copy()
            if "狀態" in working.columns:
                working = working[working["狀態"].astype(str).str.contains("急需|注意|缺貨|不足|偏低", regex=True)]
            for _, row in working.head(8).iterrows():
                alerts.append({
                    "產品編號": str(row.get("產品編號", "")),
                    "產品名稱": str(row.get("產品名稱", "")),
                    "狀態": str(row.get("狀態", "")),
                    "目前庫存": DashboardDataService._num(row.get("目前庫存", row.get("三倉庫存合計", 0))),
                })
        low_stock = health["注意"] + health["缺貨"]
        health_total = sum(health.values())
        health_ratio = (health["正常"] / health_total * 100) if health_total else 0.0

        unique_suppliers = set()
        for s in suppliers:
            if isinstance(s, dict):
                name = str(s.get("supplier", s.get("name", ""))).strip()
                if name:
                    unique_suppliers.add(name)

        transfer_count = 0
        transfer_remaining_shortage = 0
        try:
            from services.warehouse_transfer_service import WarehouseTransferService
            if inventory_df is not None and not inventory_df.empty and demand_df is not None and not demand_df.empty:
                transfer_result = WarehouseTransferService.calculate(inventory_df, demand_df)
                tdf = transfer_result.get("transfer_df")
                sdf = transfer_result.get("summary_df")
                if tdf is not None:
                    transfer_count = len(tdf)
                if sdf is not None and not sdf.empty and "調撥後缺口" in sdf.columns:
                    transfer_remaining_shortage = int((pd.to_numeric(sdf["調撥後缺口"], errors="coerce").fillna(0) > 0).sum())
        except Exception:
            # 跨倉調撥試算失敗時，儀表板會靜靜顯示 0 筆調撥／0 缺口，容易誤導使用者
            # 以為「調撥後沒有缺貨」。記一筆警告，方便之後追查是不是資料格式有問題。
            get_logger().warning("首頁儀表板計算跨倉調撥摘要時發生錯誤，本次調撥數字以 0 顯示。", exc_info=True)

        by_supplier_currency, currency_totals, total_cbm, priced_lines = DashboardDataService._purchase_cost_and_cbm(purchase_df)
        supplier_spend = [
            {"供應商": supplier, "幣別": currency, "金額": amount}
            for (supplier, currency), amount in sorted(by_supplier_currency.items(), key=lambda x: x[1], reverse=True)[:8]
        ]
        container_cbm = DashboardDataService._num(
            SystemSettingsService.load().get("warehouse", {}).get("container_cbm", 66.5)
        ) or 66.5
        container_count = int(math.ceil(total_cbm / container_cbm)) if total_cbm > 0 else 0
        last_container_usage = 0.0
        if total_cbm > 0 and container_cbm > 0:
            remainder = total_cbm % container_cbm
            last_container_usage = ((remainder if remainder else container_cbm) / container_cbm) * 100

        top_purchase = DashboardDataService._top_records(purchase_df, qty_col, 8) if qty_col else []

        currency_summary = " / ".join(f"{c} {v:,.0f}" for c, v in sorted(currency_totals.items())) or "尚無金額資料"
        purchase_amount_primary = "尚無報價"
        if len(currency_totals) == 1:
            c, v = next(iter(currency_totals.items()))
            purchase_amount_primary = f"{c} {v:,.0f}"
        elif len(currency_totals) > 1:
            purchase_amount_primary = f"{len(currency_totals)} 種幣別"

        return {
            "product_count": len(products),
            "supplier_count": len(unique_suppliers),
            "total_stock": total_stock,
            "warehouse_names": warehouse_names,
            "warehouse_totals": warehouse_totals,
            "demand_total": demand_total,
            "demand_product_count": int(customer_status.get("product_count", 0)),
            "unmapped_count": unmapped,
            "need_purchase_count": need_purchase,
            "urgent_purchase_count": urgent,
            "purchase_total": purchase_total,
            "low_stock_count": low_stock,
            "inventory_health": health,
            "inventory_health_ratio": health_ratio,
            "transfer_count": transfer_count,
            "transfer_remaining_shortage": transfer_remaining_shortage,
            "customer_updated_at": customer_status.get("updated_at", ""),
            "inventory_updated_at": inventory_meta.get("updated_at", ""),
            "purchase_updated_at": purchase_meta.get("updated_at", ""),
            "top_purchase": top_purchase,
            "top_demand": top_demand,
            "alerts": alerts,
            "demand_trend_labels": trend_labels,
            "demand_trend_values": trend_values,
            "supplier_spend": supplier_spend,
            "currency_totals": dict(currency_totals),
            "currency_summary": currency_summary,
            "purchase_amount_primary": purchase_amount_primary,
            "total_cbm": total_cbm,
            "container_cbm": container_cbm,
            "container_count": container_count,
            "last_container_usage": last_container_usage,
            "priced_purchase_lines": priced_lines,
            "has_demand_detail": bool(customer_status.get("has_detail_snapshot", False)),
        }
