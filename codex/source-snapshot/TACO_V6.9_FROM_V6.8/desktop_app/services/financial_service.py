import os
import uuid
from datetime import datetime, timedelta
import calendar

import pandas as pd

from services.app_paths import AppPaths
from services.safe_storage import SafeStorage
from services.dashboard_data_service import DashboardDataService
from services.audit_log_service import AuditLogService
from services.customer_demand_store_service import CustomerDemandStoreService


class FinancialService:
    """TACO 財務資料服務。

    V6.5 延伸 V6.4：加入銷售退貨／折讓、進貨退貨、發票折讓、沖帳與月結鎖帳。
    客戶對帳、付款排程與既有財務流程全部保留。
    所有寫入仍走 SafeStorage，並在 service 層再次檢查高級版與角色權限。
    """

    @staticmethod
    def _require_finance_write():
        from services.security import require_tier, PermissionDeniedError
        from services import role_rules
        from services.safe_storage import get_logger
        require_tier("advanced", "財務資料寫入")
        role = role_rules.current_role()
        if role not in {"系統管理員", "財務人員", "採購管理者"}:
            get_logger().warning("財務權限拒絕：角色「%s」嘗試修改財務資料。", role)
            raise PermissionDeniedError("目前角色沒有修改財務資料的權限。")

    BASE_DIR = str(AppPaths.install_dir())
    DATA_DIR = str(AppPaths.data_dir())
    DATA_FILE = os.path.join(DATA_DIR, "finance_data.json")

    DEFAULT = {
        "payables": [],
        "payments": [],
        "shipments": [],
        "exchange_rates": [
            {"currency": "TWD", "rate_to_twd": 1.0, "date": "", "note": "本位幣"},
        ],
        "receivables": [],
        "receipts": [],
        "expenses": [],
        "sales_prices": [],
        "customer_terms": [],
        "invoices": [],
        "cashflow_plans": [],
        "cash_settings": {"opening_cash_twd": 0.0},
        "sales_orders": [],
        "deliveries": [],
        "collection_actions": [],
        "sales_returns": [],
        "purchase_returns": [],
        "invoice_allowances": [],
        "settlements": [],
        "month_closes": [],
    }

    @staticmethod
    def _now():
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def _num(v):
        try:
            if v is None or pd.isna(v):
                return 0.0
            if isinstance(v, str):
                v = v.replace(",", "").strip()
            return float(v or 0)
        except Exception:
            return 0.0

    @staticmethod
    def _text(v):
        if v is None:
            return ""
        try:
            if pd.isna(v):
                return ""
        except Exception:
            pass
        return str(v).strip()

    @staticmethod
    def _numeric_series(df, column, default=0.0):
        """Return a numeric Series aligned to df.index even if a legacy column is absent."""
        if column in df.columns:
            return pd.to_numeric(df[column], errors="coerce").fillna(default)
        return pd.Series(default, index=df.index, dtype="float64")

    @staticmethod
    def _open_receivable(record):
        """應收未沖餘額 = 原始應收 - 現金收款 - 退貨／折讓沖帳。"""
        return max(0.0, FinancialService._num(record.get("total_amount"))
                   - FinancialService._num(record.get("received_amount"))
                   - FinancialService._num(record.get("adjustment_amount")))

    @staticmethod
    def _open_payable(record):
        """應付未沖餘額 = 原始應付 - 現金付款 - 進貨退回沖帳。"""
        return max(0.0, FinancialService._num(record.get("total_amount"))
                   - FinancialService._num(record.get("paid_amount"))
                   - FinancialService._num(record.get("adjustment_amount")))

    @staticmethod
    def _period_key(value):
        d = FinancialService._date_value(value)
        return d.strftime("%Y-%m") if d else ""

    @staticmethod
    def is_period_closed(value):
        period = value if isinstance(value, str) and len(value) == 7 else FinancialService._period_key(value)
        if not period:
            return False
        rows = [x for x in FinancialService.load().get("month_closes", [])
                if FinancialService._text(x.get("period")) == period]
        if not rows:
            return False
        return FinancialService._text(rows[-1].get("status")) == "已結帳"

    @staticmethod
    def _ensure_period_open(value, action="財務異動"):
        d = FinancialService._date_value(value)
        if not d:
            raise ValueError("日期格式錯誤，請使用 YYYY-MM-DD")
        if FinancialService.is_period_closed(d.isoformat()):
            raise ValueError(f"{d.strftime('%Y-%m')} 已完成月結，不能執行「{action}」。如需更正，請由系統管理員先重開該月份。")
        return d

    @staticmethod
    def _refresh_receivable_status(record):
        remaining = FinancialService._open_receivable(record)
        if remaining <= 1e-9:
            record["status"] = "已沖清" if FinancialService._num(record.get("adjustment_amount")) > 0 else "已收款"
        elif FinancialService._num(record.get("adjustment_amount")) > 0:
            record["status"] = "部分沖帳"
        elif FinancialService._num(record.get("received_amount")) > 0:
            record["status"] = "部分收款"
        elif FinancialService._text(record.get("invoice_no")):
            record["status"] = "未收款"
        else:
            record["status"] = "待開票"

    @staticmethod
    def _refresh_payable_status(record):
        remaining = FinancialService._open_payable(record)
        if remaining <= 1e-9:
            record["status"] = "已沖清" if FinancialService._num(record.get("adjustment_amount")) > 0 else "已付款"
        elif FinancialService._num(record.get("adjustment_amount")) > 0:
            record["status"] = "部分沖帳"
        elif FinancialService._num(record.get("paid_amount")) > 0:
            record["status"] = "部分付款"
        else:
            record["status"] = "未付款"

    @staticmethod
    def load():
        os.makedirs(FinancialService.DATA_DIR, exist_ok=True)
        data = SafeStorage.safe_read_json(FinancialService.DATA_FILE, default={})
        if not isinstance(data, dict):
            data = {}
        merged = {}
        for k, default in FinancialService.DEFAULT.items():
            value = data.get(k, default)
            merged[k] = list(value) if isinstance(value, list) else list(default) if isinstance(default, list) else value
        # 保留未來擴充欄位。
        for k, v in data.items():
            if k not in merged:
                merged[k] = v
        return merged

    @staticmethod
    def save(data):
        os.makedirs(FinancialService.DATA_DIR, exist_ok=True)
        SafeStorage.atomic_write_json(FinancialService.DATA_FILE, data, indent=2)

    # ------------------------------------------------------------------
    # 匯率
    # ------------------------------------------------------------------
    @staticmethod
    def get_rate(currency):
        currency = FinancialService._text(currency).upper()
        if currency == "TWD":
            return 1.0
        rates = FinancialService.load().get("exchange_rates", [])
        matches = [r for r in rates if FinancialService._text(r.get("currency")).upper() == currency]
        if not matches:
            return 0.0
        return FinancialService._num(matches[-1].get("rate_to_twd", 0))

    @staticmethod
    def upsert_rate(currency, rate, date="", note=""):
        FinancialService._require_finance_write()
        currency = FinancialService._text(currency).upper()
        if not currency:
            raise ValueError("幣別不可空白")
        if currency != "TWD" and FinancialService._num(rate) <= 0:
            raise ValueError("匯率必須大於 0")
        data = FinancialService.load()
        rows = data["exchange_rates"]
        rows.append({
            "currency": currency,
            "rate_to_twd": FinancialService._num(rate),
            "date": str(date),
            "note": str(note),
            "updated_at": FinancialService._now(),
        })
        data["exchange_rates"] = rows[-500:]
        FinancialService.save(data)
        AuditLogService.log_event("財務", "更新匯率", record_id=currency,
                                  after={"rate_to_twd": rate, "date": date}, result="成功")

    # ------------------------------------------------------------------
    # 採購應付 / 付款
    # ------------------------------------------------------------------
    @staticmethod
    def sync_payables_from_purchase():
        FinancialService._require_finance_write()
        purchase_df, meta = DashboardDataService.load_purchase_df()
        if purchase_df is None or purchase_df.empty:
            return {"created": 0, "updated": 0, "skipped_paid": 0,
                    "source_updated_at": meta.get("updated_at", "")}
        data = FinancialService.load()
        payables = data["payables"]
        index = {str(x.get("source_key")): x for x in payables if x.get("source_key")}
        created = updated = skipped_paid = 0
        for _, row in purchase_df.iterrows():
            qty = FinancialService._num(row.get("實際採購量", row.get("建議採購量", 0)))
            if qty <= 0:
                continue
            pno = FinancialService._text(row.get("產品編號"))
            supplier = FinancialService._text(row.get("本次採購供應商"))
            if not pno or not supplier:
                continue
            key = f"current||{pno}||{supplier}"
            amount = FinancialService._num(row.get("商品總價", 0))
            record = {
                "source_key": key,
                "source_type": "purchase_snapshot",
                "product_no": pno,
                "product_name": FinancialService._text(row.get("產品名稱")),
                "supplier": supplier,
                "qty": qty,
                "purchase_qty_unit": FinancialService._text(row.get("採購數量單位")),
                "currency": FinancialService._text(row.get("幣別")) or "USD",
                "unit_price": FinancialService._num(row.get("單價", 0)),
                "price_unit": FinancialService._text(row.get("計價單位")),
                "pricing_qty": FinancialService._num(row.get("計價數量", 0)),
                "total_amount": amount,
                "source_updated_at": meta.get("updated_at", ""),
                "updated_at": FinancialService._now(),
            }
            old = index.get(key)
            if old:
                if FinancialService._num(old.get("paid_amount", 0)) > 0:
                    skipped_paid += 1
                    continue
                old.update(record)
                old["status"] = "未付款"
                updated += 1
            else:
                record.update({
                    "id": "AP-" + uuid.uuid4().hex[:10].upper(),
                    "created_at": FinancialService._now(),
                    "paid_amount": 0.0,
                    "status": "未付款",
                })
                payables.append(record)
                index[key] = record
                created += 1
        data["payables"] = payables
        FinancialService.save(data)
        AuditLogService.log_event("財務", "同步採購應付",
                                  after={"created": created, "updated": updated,
                                         "skipped_paid": skipped_paid}, result="成功")
        return {"created": created, "updated": updated, "skipped_paid": skipped_paid,
                "source_updated_at": meta.get("updated_at", "")}

    @staticmethod
    def record_payment(payable_id, amount, payment_date, fx_rate=0, bank_fee_twd=0, note=""):
        FinancialService._require_finance_write()
        data = FinancialService.load()
        target = next((p for p in data["payables"] if p.get("id") == payable_id), None)
        if not target:
            raise ValueError("找不到應付資料")
        amount = FinancialService._num(amount)
        FinancialService._ensure_period_open(payment_date, "供應商付款")
        remaining = FinancialService._open_payable(target)
        if amount <= 0 or amount > remaining + 1e-9:
            raise ValueError(f"付款金額必須大於 0 且不可超過未付款金額 {remaining:,.2f}")
        currency = FinancialService._text(target.get("currency")) or "TWD"
        rate = FinancialService._num(fx_rate) or FinancialService.get_rate(currency)
        if currency != "TWD" and rate <= 0:
            raise ValueError("外幣付款需要有效的台幣匯率")
        if currency == "TWD":
            rate = 1.0
        payment = {
            "id": "PAY-" + uuid.uuid4().hex[:10].upper(),
            "payable_id": payable_id,
            "supplier": target.get("supplier", ""),
            "currency": currency,
            "amount": amount,
            "payment_date": str(payment_date),
            "fx_rate": rate,
            "amount_twd": round(amount * rate, 2),
            "bank_fee_twd": round(FinancialService._num(bank_fee_twd), 2),
            "note": str(note),
            "created_at": FinancialService._now(),
        }
        data["payments"].append(payment)
        target["paid_amount"] = round(FinancialService._num(target.get("paid_amount")) + amount, 6)
        FinancialService._refresh_payable_status(target)
        FinancialService.save(data)
        AuditLogService.log_event("財務", "供應商付款", record_id=payable_id,
                                  after=payment, result="成功")
        return payment

    # ------------------------------------------------------------------
    # 客戶應收 / 收款
    # ------------------------------------------------------------------
    @staticmethod
    def sync_receivables_from_customer_demand():
        """從客戶需求明細建立應收。

        只有存在「客戶 + 正式產品編號 + 金額」的明細才同步。
        金額優先使用總價；總價為 0 時才用 單價 × 數量。
        PDF 通常沒有銷售單價，因此會列入 skipped_no_amount，不會亂補價格。
        """
        FinancialService._require_finance_write()
        snapshot = CustomerDemandStoreService.load_snapshot()
        detail = CustomerDemandStoreService.load_detail()
        if detail is None or detail.empty:
            return {"created": 0, "updated": 0, "skipped_received": 0,
                    "skipped_no_amount": 0, "skipped_no_product": 0,
                    "source_updated_at": snapshot.get("updated_at", "")}

        data = FinancialService.load()
        receivables = data["receivables"]
        index = {str(x.get("source_key")): x for x in receivables if x.get("source_key")}
        created = updated = skipped_received = skipped_no_amount = skipped_no_product = 0

        for idx, row in detail.reset_index(drop=True).iterrows():
            customer = FinancialService._text(row.get("客戶"))
            pno = FinancialService._text(row.get("產品編號"))
            if not customer or not pno:
                skipped_no_product += 1
                continue
            qty = FinancialService._num(row.get("需求數量", row.get("數量", 0)))
            unit_price = FinancialService._num(row.get("單價", 0))
            total = FinancialService._num(row.get("總價", 0))
            if total <= 0 and unit_price > 0 and qty > 0:
                total = unit_price * qty
            currency = FinancialService._text(row.get("幣別")) or "TWD"
            if total <= 0:
                price_rec = FinancialService.get_sales_price(customer, pno)
                if price_rec and qty > 0:
                    unit_price = FinancialService._num(price_rec.get("unit_price", 0))
                    currency = FinancialService._text(price_rec.get("currency")) or currency
                    total = unit_price * qty
                else:
                    skipped_no_amount += 1
                    continue
            order_no = FinancialService._text(row.get("客戶訂號")) or FinancialService._text(row.get("採購單號"))
            source_file = snapshot.get("source_file", "")
            key = f"demand||{source_file}||{order_no}||{pno}||{customer}||{idx}"
            record = {
                "source_key": key,
                "source_type": "customer_demand_snapshot",
                "customer": customer,
                "customer_order_no": order_no,
                "product_no": pno,
                "product_name": FinancialService._text(row.get("產品名稱")),
                "qty": qty,
                "qty_unit": FinancialService._text(row.get("需求單位", row.get("單位", ""))),
                "currency": currency,
                "unit_price": unit_price,
                "total_amount": round(total, 6),
                "invoice_date": "",
                "due_date": "",
                "sales_order_date": FinancialService._text(row.get("採購日期")),
                "source_updated_at": snapshot.get("updated_at", ""),
                "updated_at": FinancialService._now(),
            }
            old = index.get(key)
            if old:
                if FinancialService._num(old.get("received_amount", 0)) > 0:
                    skipped_received += 1
                    continue
                invoice_no = FinancialService._text(old.get("invoice_no"))
                old.update(record)
                old["status"] = "未收款" if invoice_no else "待開票"
                if invoice_no:
                    old["invoice_no"] = invoice_no
                updated += 1
            else:
                record.update({
                    "id": "AR-" + uuid.uuid4().hex[:10].upper(),
                    "created_at": FinancialService._now(),
                    "received_amount": 0.0,
                    "status": "待開票",
                    "note": "由客戶需求同步，待正式開票",
                })
                receivables.append(record)
                index[key] = record
                created += 1
        data["receivables"] = receivables
        FinancialService.save(data)
        AuditLogService.log_event(
            "財務", "同步客戶應收",
            after={"created": created, "updated": updated,
                   "skipped_received": skipped_received,
                   "skipped_no_amount": skipped_no_amount,
                   "skipped_no_product": skipped_no_product},
            result="成功",
        )
        return {"created": created, "updated": updated,
                "skipped_received": skipped_received,
                "skipped_no_amount": skipped_no_amount,
                "skipped_no_product": skipped_no_product,
                "source_updated_at": snapshot.get("updated_at", "")}

    @staticmethod
    def create_receivable(customer, product_no="", product_name="", qty=0, qty_unit="",
                          currency="TWD", unit_price=0, total_amount=0,
                          invoice_date="", due_date="", customer_order_no="", note=""):
        FinancialService._require_finance_write()
        customer = FinancialService._text(customer)
        if not customer:
            raise ValueError("客戶不可空白")
        qty = FinancialService._num(qty)
        unit_price = FinancialService._num(unit_price)
        total_amount = FinancialService._num(total_amount) or (qty * unit_price)
        if total_amount <= 0:
            raise ValueError("應收金額必須大於 0")
        currency = FinancialService._text(currency).upper() or "TWD"
        rate = FinancialService.get_rate(currency)
        if currency == "TWD":
            rate = 1.0
        additional_twd = total_amount * (rate if rate > 0 else 0)
        credit = FinancialService.check_credit(customer, additional_twd)
        if not credit.get("allowed", True):
            raise ValueError(f"客戶信用額度不足：預估使用 TWD {credit.get('projected_twd',0):,.0f}，額度 TWD {credit.get('credit_limit_twd',0):,.0f}")
        data = FinancialService.load()
        record = {
            "id": "AR-" + uuid.uuid4().hex[:10].upper(),
            "source_key": "manual||" + uuid.uuid4().hex,
            "source_type": "manual",
            "customer": customer,
            "customer_order_no": FinancialService._text(customer_order_no),
            "product_no": FinancialService._text(product_no),
            "product_name": FinancialService._text(product_name),
            "qty": qty,
            "qty_unit": FinancialService._text(qty_unit),
            "currency": currency,
            "unit_price": unit_price,
            "total_amount": round(total_amount, 6),
            "received_amount": 0.0,
            "invoice_date": FinancialService._text(invoice_date),
            "due_date": FinancialService._text(due_date),
            "status": "未收款",
            "credit_status_at_create": credit.get("status", ""),
            "note": FinancialService._text(note),
            "created_at": FinancialService._now(),
            "updated_at": FinancialService._now(),
        }
        data["receivables"].append(record)
        FinancialService.save(data)
        AuditLogService.log_event("財務", "新增客戶應收", record_id=record["id"],
                                  after=record, result="成功")
        return record

    @staticmethod
    def record_receipt(receivable_id, amount, receipt_date, fx_rate=0, bank_fee_twd=0, note=""):
        FinancialService._require_finance_write()
        data = FinancialService.load()
        target = next((x for x in data["receivables"] if x.get("id") == receivable_id), None)
        if not target:
            raise ValueError("找不到應收資料")
        amount = FinancialService._num(amount)
        FinancialService._ensure_period_open(receipt_date, "客戶收款")
        remaining = FinancialService._open_receivable(target)
        if amount <= 0 or amount > remaining + 1e-9:
            raise ValueError(f"收款金額必須大於 0 且不可超過未收金額 {remaining:,.2f}")
        currency = FinancialService._text(target.get("currency")) or "TWD"
        rate = FinancialService._num(fx_rate) or FinancialService.get_rate(currency)
        if currency != "TWD" and rate <= 0:
            raise ValueError("外幣收款需要有效的台幣匯率")
        if currency == "TWD":
            rate = 1.0
        receipt = {
            "id": "RCV-" + uuid.uuid4().hex[:10].upper(),
            "receivable_id": receivable_id,
            "customer": target.get("customer", ""),
            "currency": currency,
            "amount": amount,
            "receipt_date": str(receipt_date),
            "fx_rate": rate,
            "amount_twd": round(amount * rate, 2),
            "bank_fee_twd": round(FinancialService._num(bank_fee_twd), 2),
            "note": str(note),
            "created_at": FinancialService._now(),
        }
        data["receipts"].append(receipt)
        target["received_amount"] = round(FinancialService._num(target.get("received_amount")) + amount, 6)
        FinancialService._refresh_receivable_status(target)
        FinancialService.save(data)
        AuditLogService.log_event("財務", "客戶收款", record_id=receivable_id,
                                  after=receipt, result="成功")
        return receipt

    # ------------------------------------------------------------------
    # 費用
    # ------------------------------------------------------------------
    @staticmethod
    def create_expense(expense_date, category, amount, currency="TWD", fx_rate=0,
                       vendor="", reference_no="", note=""):
        FinancialService._require_finance_write()
        FinancialService._ensure_period_open(expense_date, "費用入帳")
        amount = FinancialService._num(amount)
        if amount <= 0:
            raise ValueError("費用金額必須大於 0")
        currency = FinancialService._text(currency).upper() or "TWD"
        rate = 1.0 if currency == "TWD" else (FinancialService._num(fx_rate) or FinancialService.get_rate(currency))
        if currency != "TWD" and rate <= 0:
            raise ValueError("外幣費用需要有效的台幣匯率")
        data = FinancialService.load()
        record = {
            "id": "EXP-" + uuid.uuid4().hex[:10].upper(),
            "expense_date": FinancialService._text(expense_date),
            "category": FinancialService._text(category) or "其他",
            "vendor": FinancialService._text(vendor),
            "reference_no": FinancialService._text(reference_no),
            "currency": currency,
            "amount": amount,
            "fx_rate": rate,
            "amount_twd": round(amount * rate, 2),
            "note": FinancialService._text(note),
            "created_at": FinancialService._now(),
        }
        data["expenses"].append(record)
        FinancialService.save(data)
        AuditLogService.log_event("財務", "新增費用", record_id=record["id"],
                                  after=record, result="成功")
        return record

    # ------------------------------------------------------------------
    # 進口成本
    # ------------------------------------------------------------------
    @staticmethod
    def create_import_shipment(valid_df, summary, note=""):
        FinancialService._require_finance_write()
        if valid_df is None or valid_df.empty:
            raise ValueError("目前沒有可建立進口成本批次的品項")
        data = FinancialService.load()
        rows = []
        for _, r in valid_df.iterrows():
            rows.append({str(c): (None if pd.isna(r.get(c)) else r.get(c)) for c in valid_df.columns})
        shipment = {
            "id": "IMP-" + datetime.now().strftime("%Y%m%d-%H%M%S"),
            "created_at": FinancialService._now(),
            "note": str(note),
            "capacity_cbm": FinancialService._num(summary.get("capacity_cbm", 66.5)),
            "total_cbm": FinancialService._num(summary.get("total_cbm", 0)),
            "container_count": int(summary.get("container_count", 0) or 0),
            "rows": rows,
            "costs_twd": {
                "ocean_freight": 0, "customs": 0, "tariff": 0, "import_tax": 0,
                "trucking": 0, "storage": 0, "document_fee": 0, "bank_fee": 0, "other": 0,
            },
        }
        data["shipments"].append(shipment)
        FinancialService.save(data)
        AuditLogService.log_event("財務", "建立進口成本批次", record_id=shipment["id"],
                                  after={"total_cbm": shipment["total_cbm"], "items": len(rows)},
                                  result="成功")
        return shipment

    @staticmethod
    def update_shipment_costs(shipment_id, costs):
        FinancialService._require_finance_write()
        data = FinancialService.load()
        shipment = next((x for x in data["shipments"] if x.get("id") == shipment_id), None)
        if not shipment:
            raise ValueError("找不到進口成本批次")
        before = dict(shipment.get("costs_twd", {}))
        shipment["costs_twd"] = {k: round(FinancialService._num(v), 2) for k, v in costs.items()}
        shipment["updated_at"] = FinancialService._now()
        FinancialService.save(data)
        AuditLogService.log_event("財務", "修改進口共同成本", record_id=shipment_id,
                                  before=before, after=shipment["costs_twd"], result="成功")

    @staticmethod
    def shipment_analysis(shipment):
        rows = pd.DataFrame(shipment.get("rows", []))
        if rows.empty:
            return pd.DataFrame(), {}
        total_cbm = max(0.0, FinancialService._num(shipment.get("total_cbm", 0)))
        shared = sum(FinancialService._num(v) for v in shipment.get("costs_twd", {}).values())
        out = []
        merchandise_twd_total = 0.0
        for _, r in rows.iterrows():
            currency = FinancialService._text(r.get("幣別")) or "TWD"
            amount = FinancialService._num(r.get("商品總價", 0))
            rate = FinancialService.get_rate(currency)
            amount_twd = amount * rate if rate > 0 else 0.0
            merchandise_twd_total += amount_twd
            cbm = FinancialService._num(r.get("本次CBM", 0))
            share = (cbm / total_cbm) if total_cbm > 0 else (1 / len(rows))
            allocated = shared * share
            landed_total = amount_twd + allocated
            price_qty = FinancialService._num(r.get("計價數量", 0)) or FinancialService._num(r.get("實際採購量", 0))
            out.append({
                "產品編號": r.get("產品編號", ""),
                "產品名稱": r.get("產品名稱", ""),
                "供應商": r.get("本次採購供應商", ""),
                "幣別": currency,
                "商品原幣金額": round(amount, 2),
                "換算匯率": round(rate, 6),
                "商品台幣金額": round(amount_twd, 2),
                "本次CBM": round(cbm, 4),
                "CBM分攤比例%": round(share * 100, 2),
                "共同成本分攤TWD": round(allocated, 2),
                "落地總成本TWD": round(landed_total, 2),
                "計價數量": round(price_qty, 2),
                "落地單位成本TWD": round(landed_total / price_qty, 6) if price_qty > 0 else 0,
            })
        result = pd.DataFrame(out)
        summary = {
            "merchandise_twd": round(merchandise_twd_total, 2),
            "shared_cost_twd": round(shared, 2),
            "landed_total_twd": round(merchandise_twd_total + shared, 2),
        }
        return result, summary

    @staticmethod
    def latest_landed_cost_map():
        """取得每個產品最近一批進口的落地單位成本。"""
        data = FinancialService.load()
        result = {}
        shipments = sorted(data.get("shipments", []), key=lambda x: str(x.get("created_at", "")))
        for shipment in shipments:
            df, _ = FinancialService.shipment_analysis(shipment)
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                pno = FinancialService._text(row.get("產品編號"))
                cost = FinancialService._num(row.get("落地單位成本TWD"))
                if pno and cost > 0:
                    result[pno] = {
                        "unit_cost_twd": cost,
                        "shipment_id": shipment.get("id", ""),
                        "updated_at": shipment.get("updated_at", shipment.get("created_at", "")),
                    }
        return result

    # ------------------------------------------------------------------
    # 毛利估算
    # ------------------------------------------------------------------
    @staticmethod
    def gross_margin_analysis():
        data = FinancialService.load()
        cost_map = FinancialService.latest_landed_cost_map()
        rows = []
        for r in data.get("receivables", []):
            currency = FinancialService._text(r.get("currency")) or "TWD"
            rate = FinancialService.get_rate(currency)
            revenue = FinancialService._num(r.get("total_amount")) * (rate if rate > 0 else 0)
            qty = FinancialService._num(r.get("qty"))
            pno = FinancialService._text(r.get("product_no"))
            cost_info = cost_map.get(pno, {})
            unit_cost = FinancialService._num(cost_info.get("unit_cost_twd"))
            total_cost = qty * unit_cost if qty > 0 and unit_cost > 0 else 0.0
            gross = revenue - total_cost if revenue > 0 and total_cost > 0 else 0.0
            margin = gross / revenue * 100 if revenue > 0 and total_cost > 0 else 0.0
            rows.append({
                "應收編號": r.get("id", ""),
                "客戶": r.get("customer", ""),
                "產品編號": pno,
                "產品名稱": r.get("product_name", ""),
                "數量": qty,
                "收入原幣": FinancialService._num(r.get("total_amount")),
                "幣別": currency,
                "收入匯率": rate,
                "收入TWD": round(revenue, 2),
                "最近落地單位成本TWD": round(unit_cost, 6),
                "估算銷貨成本TWD": round(total_cost, 2),
                "估算毛利TWD": round(gross, 2),
                "估算毛利率%": round(margin, 2),
                "成本來源批次": cost_info.get("shipment_id", ""),
                "成本狀態": "已取得" if unit_cost > 0 else "缺少落地成本",
            })
        df = pd.DataFrame(rows)
        if df.empty:
            return df, {"revenue_twd": 0, "cost_twd": 0, "gross_profit_twd": 0, "margin_pct": 0,
                        "missing_cost_count": 0}
        revenue = pd.to_numeric(df["收入TWD"], errors="coerce").fillna(0).sum()
        cost = pd.to_numeric(df["估算銷貨成本TWD"], errors="coerce").fillna(0).sum()
        gross = pd.to_numeric(df["估算毛利TWD"], errors="coerce").fillna(0).sum()
        comparable_revenue = pd.to_numeric(
            df.loc[df["成本狀態"] == "已取得", "收入TWD"], errors="coerce"
        ).fillna(0).sum()
        margin = gross / comparable_revenue * 100 if comparable_revenue > 0 else 0
        return df, {
            "revenue_twd": round(revenue, 2),
            "cost_twd": round(cost, 2),
            "gross_profit_twd": round(gross, 2),
            "margin_pct": round(margin, 2),
            "missing_cost_count": int((df["成本狀態"] != "已取得").sum()),
        }

    # ------------------------------------------------------------------
    # V6.2 客戶銷售價格主檔
    # ------------------------------------------------------------------
    @staticmethod
    def upsert_sales_price(customer, product_no, unit_price, currency="TWD", qty_unit="", note=""):
        FinancialService._require_finance_write()
        customer = FinancialService._text(customer)
        product_no = FinancialService._text(product_no)
        unit_price = FinancialService._num(unit_price)
        currency = FinancialService._text(currency).upper() or "TWD"
        if not customer or not product_no:
            raise ValueError("客戶與產品編號不可空白")
        if unit_price <= 0:
            raise ValueError("銷售單價必須大於 0")
        data = FinancialService.load()
        rows = data.setdefault("sales_prices", [])
        old = next((x for x in rows if FinancialService._text(x.get("customer")) == customer and FinancialService._text(x.get("product_no")) == product_no), None)
        before = dict(old) if old else None
        payload = {
            "customer": customer,
            "product_no": product_no,
            "currency": currency,
            "unit_price": round(unit_price, 6),
            "qty_unit": FinancialService._text(qty_unit),
            "note": FinancialService._text(note),
            "updated_at": FinancialService._now(),
        }
        if old:
            old.update(payload)
        else:
            payload["id"] = "SP-" + uuid.uuid4().hex[:10].upper()
            payload["created_at"] = FinancialService._now()
            rows.append(payload)
        FinancialService.save(data)
        AuditLogService.log_event("財務", "更新客戶銷售價格", record_id=f"{customer}||{product_no}", before=before, after=payload, result="成功")
        return payload

    @staticmethod
    def delete_sales_price(price_id):
        FinancialService._require_finance_write()
        data = FinancialService.load()
        rows = data.setdefault("sales_prices", [])
        old = next((x for x in rows if x.get("id") == price_id), None)
        if not old:
            raise ValueError("找不到銷售價格資料")
        data["sales_prices"] = [x for x in rows if x.get("id") != price_id]
        FinancialService.save(data)
        AuditLogService.log_event("財務", "刪除客戶銷售價格", record_id=price_id, before=old, result="成功")

    @staticmethod
    def get_sales_price(customer, product_no):
        customer = FinancialService._text(customer)
        product_no = FinancialService._text(product_no)
        rows = FinancialService.load().get("sales_prices", [])
        exact = [x for x in rows if FinancialService._text(x.get("customer")) == customer and FinancialService._text(x.get("product_no")) == product_no]
        return exact[-1] if exact else None

    # ------------------------------------------------------------------
    # V6.2 應收帳齡 / 逾期
    # ------------------------------------------------------------------
    @staticmethod
    def _date_value(value):
        text = FinancialService._text(value)
        if not text:
            return None
        try:
            ts = pd.to_datetime(text, errors="coerce")
            if not pd.isna(ts):
                return ts.date()
        except Exception:
            pass
        try:
            import re
            m = re.search(r"(\d{2,3})/(\d{1,2})/(\d{1,2})", text)
            if m:
                y, mo, d = map(int, m.groups())
                if y < 1911:
                    y += 1911
                return datetime(y, mo, d).date()
        except Exception:
            pass
        return None

    @staticmethod
    def receivable_aging(as_of=None):
        today = FinancialService._date_value(as_of) if as_of else datetime.now().date()
        rows = []
        for r in FinancialService.load().get("receivables", []):
            total = FinancialService._num(r.get("total_amount"))
            received = FinancialService._num(r.get("received_amount"))
            adjusted = FinancialService._num(r.get("adjustment_amount"))
            remaining = max(0.0, total - received - adjusted)
            if remaining <= 1e-9:
                continue
            currency = FinancialService._text(r.get("currency")) or "TWD"
            rate = FinancialService.get_rate(currency)
            remaining_twd = remaining * (rate if rate > 0 else (1 if currency == "TWD" else 0))
            due = FinancialService._date_value(r.get("due_date")) or FinancialService._date_value(r.get("invoice_date"))
            overdue_days = max(0, (today - due).days) if due else 0
            if not due:
                bucket = "未設定到期日"
                overdue = False
            elif overdue_days <= 0:
                bucket = "未到期"
                overdue = False
            elif overdue_days <= 30:
                bucket = "逾期1-30天"
                overdue = True
            elif overdue_days <= 60:
                bucket = "逾期31-60天"
                overdue = True
            elif overdue_days <= 90:
                bucket = "逾期61-90天"
                overdue = True
            else:
                bucket = "逾期90天以上"
                overdue = True
            rows.append({
                "應收編號": r.get("id", ""), "客戶": r.get("customer", ""),
                "客戶訂號": r.get("customer_order_no", ""), "產品編號": r.get("product_no", ""),
                "產品名稱": r.get("product_name", ""), "幣別": currency,
                "應收金額": round(total, 2), "已收金額": round(received, 2), "退貨/折讓沖帳": round(adjusted, 2), "未收金額": round(remaining, 2),
                "未收TWD": round(remaining_twd, 2), "開立日期": r.get("invoice_date", ""),
                "到期日": r.get("due_date", ""), "逾期天數": overdue_days,
                "帳齡區間": bucket, "逾期": "是" if overdue else "否", "狀態": r.get("status", ""),
            })
        df = pd.DataFrame(rows)
        buckets = {k: 0.0 for k in ["未到期", "逾期1-30天", "逾期31-60天", "逾期61-90天", "逾期90天以上", "未設定到期日"]}
        if not df.empty:
            for k, g in df.groupby("帳齡區間"):
                buckets[k] = round(pd.to_numeric(g["未收TWD"], errors="coerce").fillna(0).sum(), 2)
        overdue_count = int((df["逾期"] == "是").sum()) if not df.empty else 0
        overdue_twd = round(pd.to_numeric(df.loc[df["逾期"] == "是", "未收TWD"], errors="coerce").fillna(0).sum(), 2) if not df.empty else 0
        return df, {"buckets": buckets, "overdue_count": overdue_count, "overdue_twd": overdue_twd}

    # ------------------------------------------------------------------
    # V6.2 現金流 / 管理排行
    # ------------------------------------------------------------------
    @staticmethod
    def cashflow_analysis():
        data = FinancialService.load()
        events = []
        for x in data.get("receipts", []):
            events.append({"日期": x.get("receipt_date", ""), "類型": "客戶收款", "對象": x.get("customer", ""), "流入TWD": FinancialService._num(x.get("amount_twd")), "流出TWD": FinancialService._num(x.get("bank_fee_twd")), "單號": x.get("receivable_id", "")})
        for x in data.get("payments", []):
            events.append({"日期": x.get("payment_date", ""), "類型": "供應商付款", "對象": x.get("supplier", ""), "流入TWD": 0.0, "流出TWD": FinancialService._num(x.get("amount_twd")) + FinancialService._num(x.get("bank_fee_twd")), "單號": x.get("payable_id", "")})
        for x in data.get("expenses", []):
            events.append({"日期": x.get("expense_date", ""), "類型": "費用", "對象": x.get("vendor", ""), "流入TWD": 0.0, "流出TWD": FinancialService._num(x.get("amount_twd")), "單號": x.get("reference_no", "")})
        df = pd.DataFrame(events)
        if df.empty:
            return df, {"inflow_twd": 0, "outflow_twd": 0, "net_twd": 0, "monthly": []}
        df["流入TWD"] = pd.to_numeric(df["流入TWD"], errors="coerce").fillna(0)
        df["流出TWD"] = pd.to_numeric(df["流出TWD"], errors="coerce").fillna(0)
        df["淨流量TWD"] = df["流入TWD"] - df["流出TWD"]
        df["_date"] = df["日期"].apply(FinancialService._date_value)
        df["月份"] = df["_date"].apply(lambda d: d.strftime("%Y-%m") if d else "未設定日期")
        monthly = df.groupby("月份")[["流入TWD", "流出TWD", "淨流量TWD"]].sum().reset_index().sort_values("月份")
        return df.drop(columns=["_date"]), {
            "inflow_twd": round(df["流入TWD"].sum(), 2),
            "outflow_twd": round(df["流出TWD"].sum(), 2),
            "net_twd": round(df["淨流量TWD"].sum(), 2),
            "monthly": monthly.to_dict("records"),
        }

    @staticmethod
    def margin_rankings():
        df, _ = FinancialService.gross_margin_analysis()
        empty = {"product": pd.DataFrame(), "customer": pd.DataFrame(), "supplier": pd.DataFrame()}
        if df is None or df.empty:
            return empty
        valid = df[df["成本狀態"] == "已取得"].copy()
        if valid.empty:
            return empty
        def grouped(cols):
            g = valid.groupby(cols, dropna=False).agg(
                收入TWD=("收入TWD", "sum"),
                銷貨成本TWD=("估算銷貨成本TWD", "sum"),
                毛利TWD=("估算毛利TWD", "sum"),
            ).reset_index()
            g["毛利率%"] = g.apply(lambda r: (r["毛利TWD"] / r["收入TWD"] * 100) if r["收入TWD"] else 0, axis=1)
            return g.sort_values("毛利TWD", ascending=False)
        product = grouped(["產品編號", "產品名稱"])
        customer = grouped(["客戶"])
        # 供應商來源來自落地成本批次；以成本來源批次回查供應商。
        ship_supplier = {}
        for s in FinancialService.load().get("shipments", []):
            sdf, _ = FinancialService.shipment_analysis(s)
            if sdf is not None and not sdf.empty:
                for _, rr in sdf.iterrows():
                    ship_supplier[(s.get("id", ""), FinancialService._text(rr.get("產品編號")))] = FinancialService._text(rr.get("供應商")) or "未設定供應商"
        temp = valid.copy()
        temp["供應商"] = temp.apply(lambda r: ship_supplier.get((r.get("成本來源批次", ""), FinancialService._text(r.get("產品編號"))), "未設定供應商"), axis=1)
        supplier = temp.groupby(["供應商"], dropna=False).agg(收入TWD=("收入TWD", "sum"), 銷貨成本TWD=("估算銷貨成本TWD", "sum"), 毛利TWD=("估算毛利TWD", "sum")).reset_index()
        supplier["毛利率%"] = supplier.apply(lambda r: (r["毛利TWD"] / r["收入TWD"] * 100) if r["收入TWD"] else 0, axis=1)
        supplier = supplier.sort_values("毛利TWD", ascending=False)
        return {"product": product, "customer": customer, "supplier": supplier}


    # ------------------------------------------------------------------
    # V6.3 客戶信用 / 帳款條件
    # ------------------------------------------------------------------
    @staticmethod
    def calculate_due_date(invoice_date, term_code="NET30"):
        d = FinancialService._date_value(invoice_date)
        if not d:
            return ""
        code = FinancialService._text(term_code).upper() or "NET30"
        if code in {"CASH", "現金"}:
            due = d
        elif code.startswith("NET"):
            try:
                due = d + timedelta(days=int(code[3:] or 0))
            except Exception:
                due = d + timedelta(days=30)
        elif code.startswith("EOM"):
            last = calendar.monthrange(d.year, d.month)[1]
            due = d.replace(day=last)
            try:
                extra = int(code[3:] or 0)
            except Exception:
                extra = 0
            due = due + timedelta(days=extra)
        else:
            due = d + timedelta(days=30)
        return due.isoformat()

    @staticmethod
    def upsert_customer_terms(customer, credit_limit_twd=0, term_code="NET30",
                              default_currency="TWD", warning_pct=80,
                              credit_policy="警示", note=""):
        FinancialService._require_finance_write()
        customer = FinancialService._text(customer)
        if not customer:
            raise ValueError("客戶不可空白")
        credit_limit_twd = max(0.0, FinancialService._num(credit_limit_twd))
        warning_pct = min(100.0, max(1.0, FinancialService._num(warning_pct) or 80.0))
        term_code = FinancialService._text(term_code).upper() or "NET30"
        data = FinancialService.load()
        rows = data.get("customer_terms", [])
        old = next((x for x in rows if FinancialService._text(x.get("customer")) == customer), None)
        before = dict(old) if old else None
        record = {
            "id": old.get("id") if old else "CUS-" + uuid.uuid4().hex[:10].upper(),
            "customer": customer,
            "credit_limit_twd": credit_limit_twd,
            "term_code": term_code,
            "default_currency": FinancialService._text(default_currency).upper() or "TWD",
            "warning_pct": warning_pct,
            "credit_policy": FinancialService._text(credit_policy) or "警示",
            "note": FinancialService._text(note),
            "updated_at": FinancialService._now(),
        }
        if old:
            old.update(record)
        else:
            rows.append(record)
        data["customer_terms"] = rows
        FinancialService.save(data)
        AuditLogService.log_event("財務", "更新客戶信用條件", record_id=record["id"],
                                  before=before, after=record, result="成功")
        return record

    @staticmethod
    def delete_customer_terms(record_id):
        FinancialService._require_finance_write()
        data = FinancialService.load()
        rows = data.get("customer_terms", [])
        old = next((x for x in rows if x.get("id") == record_id), None)
        data["customer_terms"] = [x for x in rows if x.get("id") != record_id]
        FinancialService.save(data)
        AuditLogService.log_event("財務", "刪除客戶信用條件", record_id=record_id, before=old, result="成功")

    @staticmethod
    def get_customer_terms(customer):
        customer = FinancialService._text(customer)
        return next((x for x in FinancialService.load().get("customer_terms", [])
                     if FinancialService._text(x.get("customer")) == customer), None)

    @staticmethod
    def customer_credit_status():
        data = FinancialService.load()
        profiles = {FinancialService._text(x.get("customer")): x for x in data.get("customer_terms", [])}
        customers = set(profiles)
        customers.update(FinancialService._text(x.get("customer")) for x in data.get("receivables", []) if FinancialService._text(x.get("customer")))
        rows = []
        for customer in sorted(customers):
            p = profiles.get(customer, {})
            outstanding_twd = 0.0
            overdue_twd = 0.0
            overdue_count = 0
            today = datetime.now().date()
            for ar in data.get("receivables", []):
                if FinancialService._text(ar.get("customer")) != customer:
                    continue
                rem = FinancialService._open_receivable(ar)
                cur = FinancialService._text(ar.get("currency")) or "TWD"
                rate = FinancialService.get_rate(cur)
                twd = rem * (rate if rate > 0 else (1.0 if cur == "TWD" else 0.0))
                outstanding_twd += twd
                due = FinancialService._date_value(ar.get("due_date"))
                if due and due < today and rem > 0:
                    overdue_twd += twd
                    overdue_count += 1
            limit = FinancialService._num(p.get("credit_limit_twd"))
            utilization = (outstanding_twd / limit * 100) if limit > 0 else 0.0
            available = max(0.0, limit - outstanding_twd) if limit > 0 else 0.0
            warning = FinancialService._num(p.get("warning_pct")) or 80.0
            if limit <= 0:
                status = "未設定額度"
            elif outstanding_twd > limit:
                status = "超額"
            elif utilization >= warning:
                status = "接近額度"
            else:
                status = "正常"
            rows.append({
                "客戶": customer, "信用額度TWD": round(limit, 2),
                "目前未收TWD": round(outstanding_twd, 2), "可用額度TWD": round(available, 2),
                "使用率%": round(utilization, 2), "逾期未收TWD": round(overdue_twd, 2),
                "逾期筆數": overdue_count, "帳款條件": p.get("term_code", "NET30"),
                "預設幣別": p.get("default_currency", "TWD"), "信用政策": p.get("credit_policy", "警示"),
                "狀態": status, "備註": p.get("note", ""), "設定ID": p.get("id", ""),
            })
        return pd.DataFrame(rows)

    @staticmethod
    def check_credit(customer, additional_twd=0):
        df = FinancialService.customer_credit_status()
        if df.empty:
            return {"status": "未設定額度", "allowed": True, "projected_twd": FinancialService._num(additional_twd)}
        row = df[df["客戶"] == FinancialService._text(customer)]
        if row.empty:
            return {"status": "未設定額度", "allowed": True, "projected_twd": FinancialService._num(additional_twd)}
        r = row.iloc[0]
        limit = FinancialService._num(r.get("信用額度TWD"))
        projected = FinancialService._num(r.get("目前未收TWD")) + FinancialService._num(additional_twd)
        profile = FinancialService.get_customer_terms(customer) or {}
        policy = FinancialService._text(profile.get("credit_policy")) or "警示"
        over = limit > 0 and projected > limit + 1e-9
        return {
            "status": "超額" if over else r.get("狀態", "正常"),
            "allowed": not (over and policy == "禁止超額"),
            "projected_twd": round(projected, 2), "credit_limit_twd": round(limit, 2),
            "policy": policy,
        }

    # ------------------------------------------------------------------
    # V6.3 正式發票 / 應收流程
    # ------------------------------------------------------------------
    @staticmethod
    def issue_invoice_from_receivable(receivable_id, invoice_no, invoice_date, tax_rate=5.0, term_code=""):
        FinancialService._require_finance_write()
        data = FinancialService.load()
        ar = next((x for x in data.get("receivables", []) if x.get("id") == receivable_id), None)
        if not ar:
            raise ValueError("找不到應收資料")
        invoice_no = FinancialService._text(invoice_no)
        if not invoice_no:
            raise ValueError("發票號碼不可空白")
        invoice_date = FinancialService._text(invoice_date)
        if not FinancialService._date_value(invoice_date):
            raise ValueError("發票日期格式錯誤，請使用 YYYY-MM-DD")
        FinancialService._ensure_period_open(invoice_date, "開立銷售發票")
        if any(FinancialService._text(x.get("invoice_no")) == invoice_no for x in data.get("invoices", [])):
            raise ValueError("發票號碼已存在")
        if FinancialService._text(ar.get("invoice_no")):
            raise ValueError("這筆應收已經開立發票")
        customer = FinancialService._text(ar.get("customer"))
        profile = FinancialService.get_customer_terms(customer) or {}
        term = FinancialService._text(term_code).upper() or FinancialService._text(profile.get("term_code")) or "NET30"
        due_date = FinancialService.calculate_due_date(invoice_date, term)
        total = FinancialService._num(ar.get("total_amount"))
        cur = FinancialService._text(ar.get("currency")) or "TWD"
        rate = FinancialService.get_rate(cur)
        total_twd = total * (rate if rate > 0 else (1.0 if cur == "TWD" else 0.0))
        credit = FinancialService.check_credit(customer, 0)
        tax_rate = max(0.0, FinancialService._num(tax_rate))
        subtotal = total / (1 + tax_rate / 100.0) if tax_rate > 0 else total
        tax_amount = total - subtotal
        inv = {
            "id": "INV-" + uuid.uuid4().hex[:10].upper(),
            "invoice_no": invoice_no, "invoice_date": invoice_date,
            "due_date": due_date, "term_code": term, "customer": customer,
            "customer_order_no": ar.get("customer_order_no", ""), "currency": cur,
            "subtotal": round(subtotal, 6), "tax_rate": tax_rate, "tax_amount": round(tax_amount, 6),
            "total_amount": round(total, 6), "receivable_id": receivable_id,
            "product_no": ar.get("product_no", ""), "product_name": ar.get("product_name", ""),
            "qty": ar.get("qty", 0), "qty_unit": ar.get("qty_unit", ""),
            "status": "已開立", "credit_status": credit.get("status", ""),
            "created_at": FinancialService._now(),
        }
        data.setdefault("invoices", []).append(inv)
        ar["invoice_no"] = invoice_no
        ar["invoice_id"] = inv["id"]
        ar["invoice_date"] = inv["invoice_date"]
        ar["due_date"] = due_date
        ar["term_code"] = term
        if FinancialService._num(ar.get("received_amount")) <= 0:
            ar["status"] = "未收款"
        FinancialService.save(data)
        AuditLogService.log_event("財務", "開立銷售發票", record_id=inv["id"], after=inv, result="成功")
        return inv

    @staticmethod
    def invoice_dataframe():
        rows = []
        data = FinancialService.load()
        for x in data.get("invoices", []):
            ar = next((r for r in data.get("receivables", []) if r.get("id") == x.get("receivable_id")), {})
            received = FinancialService._num(ar.get("received_amount"))
            total = FinancialService._num(x.get("total_amount"))
            due = FinancialService._date_value(x.get("due_date"))
            today = datetime.now().date()
            adjusted = FinancialService._num(ar.get("adjustment_amount"))
            remaining = max(0.0, total - received - adjusted)
            if remaining <= 1e-9:
                display_status = "已收款"
            elif received > 0:
                display_status = "部分收款"
            elif due and due < today:
                display_status = "逾期未收"
            else:
                display_status = "未收款"
            overdue_days = max(0, (today - due).days) if due and remaining > 1e-9 else 0
            rows.append({
                "發票編號": x.get("id", ""), "發票號碼": x.get("invoice_no", ""),
                "開立日期": x.get("invoice_date", ""), "到期日": x.get("due_date", ""),
                "帳款條件": x.get("term_code", ""), "客戶": x.get("customer", ""),
                "客戶訂號": x.get("customer_order_no", ""), "產品編號": x.get("product_no", ""),
                "產品名稱": x.get("product_name", ""), "幣別": x.get("currency", ""),
                "未稅金額": round(FinancialService._num(x.get("subtotal")), 2),
                "稅額": round(FinancialService._num(x.get("tax_amount")), 2),
                "含稅總額": round(total, 2), "已收金額": round(received, 2),
                "退貨/折讓沖帳": round(adjusted, 2), "未收金額": round(remaining, 2), "逾期天數": overdue_days,
                "信用狀態": x.get("credit_status", ""), "狀態": display_status,
                "應收編號": x.get("receivable_id", ""),
            })
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # V6.3 預計付款 / 現金流預測
    # ------------------------------------------------------------------
    @staticmethod
    def set_payable_expected_date(payable_id, expected_payment_date):
        FinancialService._require_finance_write()
        data = FinancialService.load()
        p = next((x for x in data.get("payables", []) if x.get("id") == payable_id), None)
        if not p:
            raise ValueError("找不到應付資料")
        expected_payment_date = FinancialService._text(expected_payment_date)
        if expected_payment_date and not FinancialService._date_value(expected_payment_date):
            raise ValueError("預計付款日格式錯誤，請使用 YYYY-MM-DD")
        before = p.get("expected_payment_date", "")
        p["expected_payment_date"] = expected_payment_date
        p["updated_at"] = FinancialService._now()
        FinancialService.save(data)
        AuditLogService.log_event("財務", "設定預計付款日", record_id=payable_id, before=before, after=p["expected_payment_date"], result="成功")

    @staticmethod
    def set_opening_cash(amount_twd):
        FinancialService._require_finance_write()
        data = FinancialService.load()
        data.setdefault("cash_settings", {})["opening_cash_twd"] = FinancialService._num(amount_twd)
        FinancialService.save(data)
        AuditLogService.log_event("財務", "設定現金流期初餘額", after={"opening_cash_twd": amount_twd}, result="成功")

    @staticmethod
    def add_cashflow_plan(plan_date, direction, amount, currency="TWD", category="其他", counterparty="", note=""):
        FinancialService._require_finance_write()
        cur = FinancialService._text(currency).upper() or "TWD"
        rate = FinancialService.get_rate(cur)
        if cur == "TWD": rate = 1.0
        if rate <= 0:
            raise ValueError("缺少有效匯率")
        amount = FinancialService._num(amount)
        if amount <= 0:
            raise ValueError("預計金額必須大於 0")
        plan_date = FinancialService._text(plan_date)
        if not FinancialService._date_value(plan_date):
            raise ValueError("預計日期格式錯誤，請使用 YYYY-MM-DD")
        rec = {
            "id": "CFP-" + uuid.uuid4().hex[:10].upper(), "plan_date": plan_date,
            "direction": "流入" if FinancialService._text(direction) == "流入" else "流出",
            "category": FinancialService._text(category) or "其他", "counterparty": FinancialService._text(counterparty),
            "currency": cur, "amount": amount, "fx_rate": rate, "amount_twd": round(amount * rate, 2),
            "note": FinancialService._text(note), "created_at": FinancialService._now(),
        }
        data = FinancialService.load(); data.setdefault("cashflow_plans", []).append(rec); FinancialService.save(data)
        AuditLogService.log_event("財務", "新增現金流預測項目", record_id=rec["id"], after=rec, result="成功")
        return rec

    @staticmethod
    def delete_cashflow_plan(plan_id):
        FinancialService._require_finance_write()
        data = FinancialService.load(); rows = data.get("cashflow_plans", [])
        old = next((x for x in rows if x.get("id") == plan_id), None)
        data["cashflow_plans"] = [x for x in rows if x.get("id") != plan_id]; FinancialService.save(data)
        AuditLogService.log_event("財務", "刪除現金流預測項目", record_id=plan_id, before=old, result="成功")

    @staticmethod
    def cashflow_forecast(days=90, as_of=None):
        today = FinancialService._date_value(as_of) if as_of else datetime.now().date()
        horizon = today + timedelta(days=max(1, int(days or 90)))
        data = FinancialService.load()
        events = []
        missing_fx_count = 0
        # 應收：依正式到期日預估收款；逾期者視為今天待收。
        for ar in data.get("receivables", []):
            rem = FinancialService._open_receivable(ar)
            if rem <= 0: continue
            due = FinancialService._date_value(ar.get("due_date"))
            if not due: continue
            when = max(due, today)
            if when > horizon: continue
            cur = FinancialService._text(ar.get("currency")) or "TWD"; rate = FinancialService.get_rate(cur)
            if cur != "TWD" and rate <= 0:
                missing_fx_count += 1
                continue
            twd = rem * (rate if rate > 0 else 1.0)
            events.append({"日期": when.isoformat(), "來源": "應收預計收款", "對象": ar.get("customer", ""), "流入TWD": twd, "流出TWD": 0.0, "單號": ar.get("invoice_no") or ar.get("id", "")})
        # 應付：優先使用預計付款日；未設定時用建立日 + 30 天。
        for ap in data.get("payables", []):
            rem = FinancialService._open_payable(ap)
            if rem <= 0: continue
            due = FinancialService._date_value(ap.get("expected_payment_date"))
            if not due:
                base = FinancialService._date_value(FinancialService._text(ap.get("created_at"))[:10]) or today
                due = base + timedelta(days=30)
            when = max(due, today)
            if when > horizon: continue
            cur = FinancialService._text(ap.get("currency")) or "TWD"; rate = FinancialService.get_rate(cur)
            if cur != "TWD" and rate <= 0:
                missing_fx_count += 1
                continue
            twd = rem * (rate if rate > 0 else 1.0)
            events.append({"日期": when.isoformat(), "來源": "應付預計付款", "對象": ap.get("supplier", ""), "流入TWD": 0.0, "流出TWD": twd, "單號": ap.get("id", "")})
        for p in data.get("cashflow_plans", []):
            d = FinancialService._date_value(p.get("plan_date"))
            if not d or d < today or d > horizon: continue
            twd = FinancialService._num(p.get("amount_twd"))
            events.append({"日期": d.isoformat(), "來源": "計畫-" + FinancialService._text(p.get("category")), "對象": p.get("counterparty", ""), "流入TWD": twd if p.get("direction") == "流入" else 0.0, "流出TWD": twd if p.get("direction") != "流入" else 0.0, "單號": p.get("id", "")})
        df = pd.DataFrame(events)
        opening = FinancialService._num(data.get("cash_settings", {}).get("opening_cash_twd", 0))
        if df.empty:
            return df, {"opening_cash_twd": opening, "forecast_inflow_twd": 0.0, "forecast_outflow_twd": 0.0, "forecast_net_twd": 0.0, "ending_cash_twd": opening, "min_cash_twd": opening, "negative_date": "", "missing_fx_count": missing_fx_count}
        df["流入TWD"] = pd.to_numeric(df["流入TWD"], errors="coerce").fillna(0); df["流出TWD"] = pd.to_numeric(df["流出TWD"], errors="coerce").fillna(0)
        df = df.sort_values(["日期", "來源"]).reset_index(drop=True)
        df["淨流量TWD"] = df["流入TWD"] - df["流出TWD"]
        # 同一天內的收付款先以「日終淨額」判斷資金缺口，避免事件排序造成假性負餘額。
        daily = df.groupby("日期", as_index=False)["淨流量TWD"].sum().sort_values("日期")
        daily["日終餘額TWD"] = opening + daily["淨流量TWD"].cumsum()
        balance_map = dict(zip(daily["日期"], daily["日終餘額TWD"]))
        df["預估日終餘額TWD"] = df["日期"].map(balance_map)
        neg = daily[daily["日終餘額TWD"] < 0]
        return df, {
            "opening_cash_twd": round(opening, 2), "forecast_inflow_twd": round(df["流入TWD"].sum(), 2),
            "forecast_outflow_twd": round(df["流出TWD"].sum(), 2), "forecast_net_twd": round(df["淨流量TWD"].sum(), 2),
            "ending_cash_twd": round(daily["日終餘額TWD"].iloc[-1], 2), "min_cash_twd": round(daily["日終餘額TWD"].min(), 2),
            "negative_date": str(neg.iloc[0]["日期"]) if not neg.empty else "",
            "missing_fx_count": missing_fx_count,
        }

    # ------------------------------------------------------------------
    # V6.4 銷售訂單 / 出貨 / 發票整合
    # ------------------------------------------------------------------
    @staticmethod
    def sync_sales_orders_from_customer_demand():
        """從客戶需求明細同步成正式銷售訂單。

        此流程與舊版「直接同步應收」並存；V6.4 建議正式流程使用：
        客戶需求 → 銷售訂單 → 出貨 → 應收 → 發票 → 收款。
        """
        FinancialService._require_finance_write()
        snapshot = CustomerDemandStoreService.load_snapshot()
        detail = CustomerDemandStoreService.load_detail()
        if detail is None or detail.empty:
            return {"created": 0, "updated": 0, "skipped": 0,
                    "source_updated_at": snapshot.get("updated_at", "")}
        data = FinancialService.load()
        orders = data.setdefault("sales_orders", [])
        index = {FinancialService._text(x.get("source_key")): x for x in orders if x.get("source_key")}
        created = updated = skipped = 0
        source_file = snapshot.get("source_file", "")
        for idx, row in detail.reset_index(drop=True).iterrows():
            customer = FinancialService._text(row.get("客戶"))
            pno = FinancialService._text(row.get("產品編號"))
            qty = FinancialService._num(row.get("需求數量", row.get("數量", 0)))
            if not customer or not pno or qty <= 0:
                skipped += 1
                continue
            order_no = FinancialService._text(row.get("客戶訂號")) or FinancialService._text(row.get("採購單號"))
            key = f"demand||{source_file}||{order_no}||{pno}||{customer}||{idx}"
            unit_price = FinancialService._num(row.get("單價", 0))
            currency = FinancialService._text(row.get("幣別")) or "TWD"
            price_rec = None
            if unit_price <= 0:
                price_rec = FinancialService.get_sales_price(customer, pno)
                if price_rec:
                    unit_price = FinancialService._num(price_rec.get("unit_price", 0))
                    currency = FinancialService._text(price_rec.get("currency")) or currency
            total = FinancialService._num(row.get("總價", 0))
            if total <= 0 and unit_price > 0:
                total = qty * unit_price
            credit_twd = 0.0
            rate = FinancialService.get_rate(currency)
            if currency == "TWD": rate = 1.0
            if total > 0 and rate > 0:
                credit_twd = total * rate
            credit = FinancialService.check_credit(customer, credit_twd)
            rec = {
                "source_key": key,
                "source_type": "customer_demand_snapshot",
                "customer": customer,
                "customer_order_no": order_no,
                "order_date": FinancialService._text(row.get("採購日期")) or datetime.now().date().isoformat(),
                "promised_date": FinancialService._text(row.get("到貨日期")),
                "product_no": pno,
                "product_name": FinancialService._text(row.get("產品名稱")),
                "order_qty": qty,
                "qty_unit": FinancialService._text(row.get("需求單位", row.get("單位", ""))) or FinancialService._text((price_rec or {}).get("qty_unit")),
                "currency": currency,
                "unit_price": unit_price,
                "total_amount": round(total, 6),
                "credit_status": credit.get("status", ""),
                "source_updated_at": snapshot.get("updated_at", ""),
                "updated_at": FinancialService._now(),
            }
            old = index.get(key)
            if old:
                # 已有出貨時，不覆蓋數量 / 價格，避免破壞已發生交易。
                if FinancialService._num(old.get("delivered_qty")) > 0:
                    skipped += 1
                    continue
                old.update(rec)
                old.setdefault("delivered_qty", 0.0)
                old.setdefault("invoiced_qty", 0.0)
                old["status"] = "待出貨"
                updated += 1
            else:
                rec.update({
                    "id": "SO-" + uuid.uuid4().hex[:10].upper(),
                    "created_at": FinancialService._now(),
                    "delivered_qty": 0.0,
                    "invoiced_qty": 0.0,
                    "status": "待出貨",
                    "note": "由客戶需求同步",
                })
                orders.append(rec); index[key] = rec; created += 1
        data["sales_orders"] = orders
        FinancialService.save(data)
        AuditLogService.log_event("財務", "同步銷售訂單", after={"created":created,"updated":updated,"skipped":skipped}, result="成功")
        return {"created":created,"updated":updated,"skipped":skipped,"source_updated_at":snapshot.get("updated_at","")}

    @staticmethod
    def create_sales_order(customer, customer_order_no, product_no, product_name, qty, qty_unit="",
                           currency="TWD", unit_price=0, order_date="", promised_date="", note=""):
        FinancialService._require_finance_write()
        customer = FinancialService._text(customer)
        product_no = FinancialService._text(product_no)
        qty = FinancialService._num(qty)
        if not customer: raise ValueError("客戶不可空白")
        if not product_no: raise ValueError("產品編號不可空白")
        if qty <= 0: raise ValueError("訂購數量必須大於 0")
        currency = FinancialService._text(currency).upper() or "TWD"
        unit_price = FinancialService._num(unit_price)
        if unit_price <= 0:
            price = FinancialService.get_sales_price(customer, product_no)
            if price:
                unit_price = FinancialService._num(price.get("unit_price"))
                currency = FinancialService._text(price.get("currency")) or currency
                qty_unit = FinancialService._text(qty_unit) or FinancialService._text(price.get("qty_unit"))
        total = qty * unit_price if unit_price > 0 else 0.0
        rate = FinancialService.get_rate(currency); rate = 1.0 if currency == "TWD" else rate
        credit = FinancialService.check_credit(customer, total * rate if rate > 0 else 0)
        if not credit.get("allowed", True):
            raise ValueError("客戶信用額度不足，信用政策設定為禁止超額。")
        rec = {
            "id":"SO-"+uuid.uuid4().hex[:10].upper(), "source_key":"manual||"+uuid.uuid4().hex,
            "source_type":"manual", "customer":customer, "customer_order_no":FinancialService._text(customer_order_no),
            "order_date":FinancialService._text(order_date) or datetime.now().date().isoformat(),
            "promised_date":FinancialService._text(promised_date), "product_no":product_no,
            "product_name":FinancialService._text(product_name), "order_qty":qty, "qty_unit":FinancialService._text(qty_unit),
            "currency":currency, "unit_price":unit_price, "total_amount":round(total,6), "delivered_qty":0.0,
            "invoiced_qty":0.0, "credit_status":credit.get("status",""), "status":"待出貨",
            "note":FinancialService._text(note), "created_at":FinancialService._now(), "updated_at":FinancialService._now(),
        }
        data=FinancialService.load(); data.setdefault("sales_orders",[]).append(rec); FinancialService.save(data)
        AuditLogService.log_event("財務","新增銷售訂單",record_id=rec["id"],after=rec,result="成功")
        return rec

    @staticmethod
    def record_delivery(sales_order_id, qty, delivery_date, delivery_no="", warehouse="", carrier="", note=""):
        FinancialService._require_finance_write()
        data=FinancialService.load(); order=next((x for x in data.get("sales_orders",[]) if x.get("id")==sales_order_id),None)
        if not order: raise ValueError("找不到銷售訂單")
        qty=FinancialService._num(qty); ordered=FinancialService._num(order.get("order_qty")); delivered=FinancialService._num(order.get("delivered_qty")); remain=max(0,ordered-delivered)
        if qty<=0 or qty>remain+1e-9: raise ValueError(f"出貨數量必須大於 0 且不可超過未出貨數量 {remain:,.2f}")
        delivery_date=FinancialService._text(delivery_date)
        if not FinancialService._date_value(delivery_date): raise ValueError("出貨日期格式錯誤，請使用 YYYY-MM-DD")
        rec={"id":"DEL-"+uuid.uuid4().hex[:10].upper(),"sales_order_id":sales_order_id,"customer":order.get("customer",""),
             "customer_order_no":order.get("customer_order_no",""),"product_no":order.get("product_no",""),"product_name":order.get("product_name",""),
             "qty":qty,"qty_unit":order.get("qty_unit",""),"delivery_date":delivery_date,"delivery_no":FinancialService._text(delivery_no),
             "warehouse":FinancialService._text(warehouse),"carrier":FinancialService._text(carrier),"currency":order.get("currency","TWD"),
             "unit_price":FinancialService._num(order.get("unit_price")),"amount":round(qty*FinancialService._num(order.get("unit_price")),6),
             "receivable_id":"","invoice_no":"","note":FinancialService._text(note),"created_at":FinancialService._now()}
        data.setdefault("deliveries",[]).append(rec); order["delivered_qty"]=round(delivered+qty,6); remaining=max(0,ordered-order["delivered_qty"])
        order["status"]="已出貨" if remaining<=1e-9 else "部分出貨"; order["updated_at"]=FinancialService._now(); FinancialService.save(data)
        AuditLogService.log_event("財務","銷售出貨",record_id=rec["id"],after=rec,result="成功")
        return rec

    @staticmethod
    def create_receivable_from_delivery(delivery_id):
        FinancialService._require_finance_write()
        data=FinancialService.load(); d=next((x for x in data.get("deliveries",[]) if x.get("id")==delivery_id),None)
        if not d: raise ValueError("找不到出貨資料")
        if FinancialService._text(d.get("receivable_id")):
            old=next((x for x in data.get("receivables",[]) if x.get("id")==d.get("receivable_id")),None)
            if old: return old
        amount=FinancialService._num(d.get("amount"))
        if amount<=0: raise ValueError("此出貨資料沒有有效銷售價格，請先建立客戶銷售價格或補上訂單單價。")
        ar={"id":"AR-"+uuid.uuid4().hex[:10].upper(),"source_key":"delivery||"+delivery_id,"source_type":"sales_delivery",
            "customer":d.get("customer",""),"customer_order_no":d.get("customer_order_no",""),"product_no":d.get("product_no",""),"product_name":d.get("product_name",""),
            "qty":FinancialService._num(d.get("qty")),"qty_unit":d.get("qty_unit",""),"currency":d.get("currency","TWD"),"unit_price":FinancialService._num(d.get("unit_price")),
            "total_amount":round(amount,6),"received_amount":0.0,"invoice_date":"","due_date":"","status":"待開票","note":"由正式出貨建立", "delivery_id":delivery_id,
            "created_at":FinancialService._now(),"updated_at":FinancialService._now()}
        data.setdefault("receivables",[]).append(ar); d["receivable_id"]=ar["id"]
        order=next((x for x in data.get("sales_orders",[]) if x.get("id")==d.get("sales_order_id")),None)
        if order: order["invoiced_qty"]=round(FinancialService._num(order.get("invoiced_qty"))+FinancialService._num(d.get("qty")),6)
        FinancialService.save(data); AuditLogService.log_event("財務","出貨建立應收",record_id=ar["id"],after=ar,result="成功")
        return ar

    @staticmethod
    def issue_invoice_from_delivery(delivery_id, invoice_no, invoice_date, tax_rate=5.0, term_code=""):
        ar=FinancialService.create_receivable_from_delivery(delivery_id)
        inv=FinancialService.issue_invoice_from_receivable(ar["id"],invoice_no,invoice_date,tax_rate,term_code)
        data=FinancialService.load(); d=next((x for x in data.get("deliveries",[]) if x.get("id")==delivery_id),None)
        if d: d["invoice_no"]=inv.get("invoice_no",""); FinancialService.save(data)
        return inv

    @staticmethod
    def sales_order_dataframe():
        rows=[]
        for x in FinancialService.load().get("sales_orders",[]):
            ordered=FinancialService._num(x.get("order_qty")); delivered=FinancialService._num(x.get("delivered_qty")); remain=max(0,ordered-delivered)
            rows.append({"銷售訂單":x.get("id",""),"狀態":x.get("status",""),"訂單日期":x.get("order_date",""),"預計交貨日":x.get("promised_date",""),
                         "客戶":x.get("customer",""),"客戶訂號":x.get("customer_order_no",""),"產品編號":x.get("product_no",""),"產品名稱":x.get("product_name",""),
                         "訂購數量":ordered,"已出貨":delivered,"未出貨":remain,"單位":x.get("qty_unit",""),"幣別":x.get("currency",""),"單價":x.get("unit_price",0),
                         "訂單金額":x.get("total_amount",0),"信用狀態":x.get("credit_status",""),"備註":x.get("note","")})
        return pd.DataFrame(rows)

    @staticmethod
    def delivery_dataframe():
        rows=[]
        for x in FinancialService.load().get("deliveries",[]):
            rows.append({"出貨編號":x.get("id",""),"出貨日期":x.get("delivery_date",""),"銷售訂單":x.get("sales_order_id",""),"客戶":x.get("customer",""),
                         "客戶訂號":x.get("customer_order_no",""),"產品編號":x.get("product_no",""),"產品名稱":x.get("product_name",""),"出貨數量":x.get("qty",0),
                         "單位":x.get("qty_unit",""),"出貨單號":x.get("delivery_no",""),"出貨倉":x.get("warehouse",""),"承運商":x.get("carrier",""),
                         "幣別":x.get("currency",""),"出貨金額":x.get("amount",0),"應收編號":x.get("receivable_id",""),"發票號碼":x.get("invoice_no",""),"備註":x.get("note","")})
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # V6.4 客戶對帳單 / 催收管理
    # ------------------------------------------------------------------
    @staticmethod
    def customer_statement(customer, start_date="", end_date=""):
        customer=FinancialService._text(customer); data=FinancialService.load()
        if not customer: return pd.DataFrame(), {"opening":0.0,"debit":0.0,"credit":0.0,"closing":0.0,"currency":""}
        start=FinancialService._date_value(start_date) if start_date else None; end=FinancialService._date_value(end_date) if end_date else None
        ar_map={x.get("id"):x for x in data.get("receivables",[])}; movements=[]; opening=0.0; currencies=set()
        for inv in data.get("invoices",[]):
            if FinancialService._text(inv.get("customer"))!=customer: continue
            d=FinancialService._date_value(inv.get("invoice_date")); amount=FinancialService._num(inv.get("total_amount")); cur=FinancialService._text(inv.get("currency")) or "TWD"; currencies.add(cur)
            if start and d and d<start: opening+=amount
            elif (not start or not d or d>=start) and (not end or not d or d<=end):
                movements.append({"日期":inv.get("invoice_date",""),"類型":"發票","單號":inv.get("invoice_no",""),"摘要":f"{inv.get('product_no','')} {inv.get('product_name','')}","幣別":cur,"應收":amount,"收款":0.0})
        for rc in data.get("receipts",[]):
            if FinancialService._text(rc.get("customer"))!=customer: continue
            d=FinancialService._date_value(rc.get("receipt_date")); amount=FinancialService._num(rc.get("amount")); ar=ar_map.get(rc.get("receivable_id"),{}); cur=FinancialService._text(rc.get("currency")) or FinancialService._text(ar.get("currency")) or "TWD"; currencies.add(cur)
            if start and d and d<start: opening-=amount
            elif (not start or not d or d>=start) and (not end or not d or d<=end):
                movements.append({"日期":rc.get("receipt_date",""),"類型":"收款","單號":ar.get("invoice_no",rc.get("receivable_id","")),"摘要":rc.get("note","") or "客戶收款","幣別":cur,"應收":0.0,"收款":amount})
        for st in data.get("settlements", []):
            if FinancialService._text(st.get("direction")) != "AR" or FinancialService._text(st.get("customer")) != customer:
                continue
            d=FinancialService._date_value(st.get("settlement_date")); amount=FinancialService._num(st.get("amount")); cur=FinancialService._text(st.get("currency")) or "TWD"; currencies.add(cur)
            if start and d and d<start: opening-=amount
            elif (not start or not d or d>=start) and (not end or not d or d<=end):
                movements.append({"日期":st.get("settlement_date",""),"類型":"退貨/折讓沖帳","單號":st.get("adjustment_id",""),"摘要":st.get("adjustment_type",""),"幣別":cur,"應收":0.0,"收款":amount})
        # 不同幣別不做跨幣別餘額相加；畫面仍列明幣別，摘要僅在單一幣別時可直接使用。
        df=pd.DataFrame(movements)
        if not df.empty: df=df.sort_values(["日期","類型"]).reset_index(drop=True); df["本期淨額"]=df["應收"]-df["收款"]
        debit=float(df["應收"].sum()) if not df.empty else 0.0; credit=float(df["收款"].sum()) if not df.empty else 0.0
        one_currency=next(iter(currencies)) if len(currencies)==1 else ("多幣別" if currencies else "")
        return df,{"opening":round(opening,2),"debit":round(debit,2),"credit":round(credit,2),"closing":round(opening+debit-credit,2),"currency":one_currency}

    @staticmethod
    def collection_queue(as_of=None):
        today=FinancialService._date_value(as_of) if as_of else datetime.now().date(); data=FinancialService.load(); actions=data.get("collection_actions",[]); rows=[]
        for ar in data.get("receivables",[]):
            rem=FinancialService._open_receivable(ar)
            if rem<=1e-9: continue
            due=FinancialService._date_value(ar.get("due_date")); overdue=max(0,(today-due).days) if due and due<today else 0
            related=[a for a in actions if a.get("receivable_id")==ar.get("id")]; related.sort(key=lambda x:(x.get("action_date",""),x.get("created_at","")))
            last=related[-1] if related else {}; next_date=last.get("next_followup","")
            if overdue>=91: priority="🔴 最高"
            elif overdue>=31: priority="🟠 高"
            elif overdue>0: priority="🟡 中"
            else: priority="🟢 正常"
            rows.append({"優先級":priority,"客戶":ar.get("customer",""),"發票號碼":ar.get("invoice_no",""),"應收編號":ar.get("id",""),"到期日":ar.get("due_date",""),"逾期天數":overdue,
                         "幣別":ar.get("currency",""),"未收金額":round(rem,2),"最後催收日":last.get("action_date",""),"最後方式":last.get("method",""),"最後結果":last.get("result",""),"下次追蹤":next_date,"催收次數":len(related)})
        return pd.DataFrame(rows).sort_values(["逾期天數","未收金額"],ascending=[False,False]).reset_index(drop=True) if rows else pd.DataFrame()

    @staticmethod
    def add_collection_action(receivable_id, action_date, method, result="", next_followup="", note=""):
        FinancialService._require_finance_write(); data=FinancialService.load(); ar=next((x for x in data.get("receivables",[]) if x.get("id")==receivable_id),None)
        if not ar: raise ValueError("找不到應收資料")
        if not FinancialService._date_value(action_date): raise ValueError("催收日期格式錯誤，請使用 YYYY-MM-DD")
        if next_followup and not FinancialService._date_value(next_followup): raise ValueError("下次追蹤日期格式錯誤")
        rec={"id":"COL-"+uuid.uuid4().hex[:10].upper(),"receivable_id":receivable_id,"customer":ar.get("customer",""),"invoice_no":ar.get("invoice_no",""),
             "action_date":FinancialService._text(action_date),"method":FinancialService._text(method) or "電話","result":FinancialService._text(result),"next_followup":FinancialService._text(next_followup),"note":FinancialService._text(note),"created_at":FinancialService._now()}
        data.setdefault("collection_actions",[]).append(rec); FinancialService.save(data); AuditLogService.log_event("財務","應收催收紀錄",record_id=rec["id"],after=rec,result="成功"); return rec

    @staticmethod
    def collection_action_dataframe():
        return pd.DataFrame(FinancialService.load().get("collection_actions",[]))

    # ------------------------------------------------------------------
    # V6.4 供應商付款排程
    # ------------------------------------------------------------------
    @staticmethod
    def payment_schedule(days=90, as_of=None):
        today=FinancialService._date_value(as_of) if as_of else datetime.now().date(); horizon=today+timedelta(days=max(1,int(days or 90))); rows=[]; missing_fx=0
        for ap in FinancialService.load().get("payables",[]):
            rem=FinancialService._open_payable(ap)
            if rem<=1e-9: continue
            d=FinancialService._date_value(ap.get("expected_payment_date")); source="已設定"
            if not d:
                base=FinancialService._date_value(FinancialService._text(ap.get("created_at"))[:10]) or today; d=base+timedelta(days=30); source="預設+30天"
            if d>horizon: continue
            delta=(d-today).days
            if delta<0: priority="🔴 已逾期"
            elif delta<=7: priority="🟠 7天內"
            elif delta<=30: priority="🟡 30天內"
            else: priority="🟢 後續"
            cur=FinancialService._text(ap.get("currency")) or "TWD"; rate=FinancialService.get_rate(cur); rate=1.0 if cur=="TWD" else rate
            if rate<=0: missing_fx+=1; twd=0.0
            else: twd=rem*rate
            rows.append({"優先級":priority,"預計付款日":d.isoformat(),"日期來源":source,"應付編號":ap.get("id",""),"供應商":ap.get("supplier",""),"產品編號":ap.get("product_no",""),
                         "幣別":cur,"未付原幣":round(rem,2),"換算TWD":round(twd,2),"付款狀態":ap.get("status","")})
        df=pd.DataFrame(rows)
        if not df.empty: df=df.sort_values(["預計付款日","換算TWD"],ascending=[True,False]).reset_index(drop=True)
        return df,{"count":len(rows),"total_twd":round(sum(x["換算TWD"] for x in rows),2),"missing_fx_count":missing_fx,"days":days}

    # ------------------------------------------------------------------
    # V6.5 退貨 / 折讓 / 沖帳
    # ------------------------------------------------------------------
    @staticmethod
    def create_sales_return(receivable_id, return_date, qty=0, amount=0, reason="", restock=True, note=""):
        FinancialService._require_finance_write()
        FinancialService._ensure_period_open(return_date, "銷售退貨")
        data=FinancialService.load(); ar=next((x for x in data.get("receivables",[]) if x.get("id")==receivable_id),None)
        if not ar: raise ValueError("找不到應收資料")
        qty=max(0.0,FinancialService._num(qty)); amount=FinancialService._num(amount)
        if amount<=0 and qty>0: amount=qty*FinancialService._num(ar.get("unit_price"))
        if amount<=0: raise ValueError("退貨金額必須大於 0")
        issued=sum(FinancialService._num(x.get("amount")) for x in data.get("sales_returns",[]) if x.get("receivable_id")==receivable_id and x.get("status")!="作廢")
        issued+=sum(FinancialService._num(x.get("amount")) for x in data.get("invoice_allowances",[]) if x.get("receivable_id")==receivable_id and x.get("status")!="作廢")
        if issued+amount>FinancialService._num(ar.get("total_amount"))+1e-9: raise ValueError("退貨／折讓累計金額不可超過原始應收金額")
        rec={"id":"SRT-"+uuid.uuid4().hex[:10].upper(),"receivable_id":receivable_id,"invoice_no":ar.get("invoice_no",""),"customer":ar.get("customer",""),
             "product_no":ar.get("product_no",""),"product_name":ar.get("product_name",""),"return_date":FinancialService._text(return_date),"qty":qty,"qty_unit":ar.get("qty_unit",""),
             "currency":ar.get("currency","TWD"),"amount":round(amount,6),"settled_amount":0.0,"restock":bool(restock),"inventory_status":"待退貨入庫" if bool(restock) else "不入庫","reason":FinancialService._text(reason),"note":FinancialService._text(note),"status":"待沖帳","created_at":FinancialService._now()}
        data.setdefault("sales_returns",[]).append(rec); FinancialService.save(data); AuditLogService.log_event("財務","銷售退貨",record_id=rec["id"],after=rec,result="成功"); return rec

    @staticmethod
    def create_invoice_allowance(receivable_id, allowance_no, allowance_date, amount, reason="", note=""):
        FinancialService._require_finance_write(); FinancialService._ensure_period_open(allowance_date,"發票折讓")
        data=FinancialService.load(); ar=next((x for x in data.get("receivables",[]) if x.get("id")==receivable_id),None)
        if not ar: raise ValueError("找不到應收資料")
        if not FinancialService._text(ar.get("invoice_no")): raise ValueError("此應收尚未開立正式發票，不能建立發票折讓")
        allowance_no=FinancialService._text(allowance_no)
        if not allowance_no: raise ValueError("折讓單號不可空白")
        if any(FinancialService._text(x.get("allowance_no"))==allowance_no for x in data.get("invoice_allowances",[])): raise ValueError("折讓單號已存在")
        amount=FinancialService._num(amount)
        if amount<=0: raise ValueError("折讓金額必須大於 0")
        issued=sum(FinancialService._num(x.get("amount")) for x in data.get("sales_returns",[]) if x.get("receivable_id")==receivable_id and x.get("status")!="作廢")
        issued+=sum(FinancialService._num(x.get("amount")) for x in data.get("invoice_allowances",[]) if x.get("receivable_id")==receivable_id and x.get("status")!="作廢")
        if issued+amount>FinancialService._num(ar.get("total_amount"))+1e-9: raise ValueError("退貨／折讓累計金額不可超過原始應收金額")
        rec={"id":"IAL-"+uuid.uuid4().hex[:10].upper(),"allowance_no":allowance_no,"receivable_id":receivable_id,"invoice_no":ar.get("invoice_no",""),"customer":ar.get("customer",""),
             "allowance_date":FinancialService._text(allowance_date),"currency":ar.get("currency","TWD"),"amount":round(amount,6),"settled_amount":0.0,"reason":FinancialService._text(reason),"note":FinancialService._text(note),"status":"待沖帳","created_at":FinancialService._now()}
        data.setdefault("invoice_allowances",[]).append(rec); FinancialService.save(data); AuditLogService.log_event("財務","發票折讓",record_id=rec["id"],after=rec,result="成功"); return rec

    @staticmethod
    def create_purchase_return(payable_id, return_date, qty=0, amount=0, reason="", note=""):
        FinancialService._require_finance_write(); FinancialService._ensure_period_open(return_date,"進貨退貨")
        data=FinancialService.load(); ap=next((x for x in data.get("payables",[]) if x.get("id")==payable_id),None)
        if not ap: raise ValueError("找不到應付資料")
        qty=max(0.0,FinancialService._num(qty)); amount=FinancialService._num(amount)
        if amount<=0 and qty>0:
            unit=FinancialService._num(ap.get("unit_price")); amount=qty*unit
        if amount<=0: raise ValueError("退貨金額必須大於 0")
        issued=sum(FinancialService._num(x.get("amount")) for x in data.get("purchase_returns",[]) if x.get("payable_id")==payable_id and x.get("status")!="作廢")
        if issued+amount>FinancialService._num(ap.get("total_amount"))+1e-9: raise ValueError("進貨退貨累計金額不可超過原始應付金額")
        rec={"id":"PRT-"+uuid.uuid4().hex[:10].upper(),"payable_id":payable_id,"supplier":ap.get("supplier",""),"product_no":ap.get("product_no",""),"product_name":ap.get("product_name",""),
             "return_date":FinancialService._text(return_date),"qty":qty,"qty_unit":ap.get("purchase_qty_unit",""),"currency":ap.get("currency","TWD"),"amount":round(amount,6),"settled_amount":0.0,
             "inventory_status":"待出庫確認","reason":FinancialService._text(reason),"note":FinancialService._text(note),"status":"待沖帳","created_at":FinancialService._now()}
        data.setdefault("purchase_returns",[]).append(rec); FinancialService.save(data); AuditLogService.log_event("財務","進貨退貨",record_id=rec["id"],after=rec,result="成功"); return rec

    @staticmethod
    def settle_adjustment(adjustment_type, adjustment_id, amount=0, settlement_date=""):
        FinancialService._require_finance_write(); settlement_date=FinancialService._text(settlement_date) or datetime.now().date().isoformat(); FinancialService._ensure_period_open(settlement_date,"沖帳")
        mapping={"銷售退貨":("sales_returns","AR","receivable_id"),"發票折讓":("invoice_allowances","AR","receivable_id"),"進貨退貨":("purchase_returns","AP","payable_id")}
        if adjustment_type not in mapping: raise ValueError("不支援的沖帳類型")
        key,direction,target_field=mapping[adjustment_type]; data=FinancialService.load(); adj=next((x for x in data.get(key,[]) if x.get("id")==adjustment_id),None)
        if not adj: raise ValueError("找不到退貨／折讓資料")
        remain_adj=max(0.0,FinancialService._num(adj.get("amount"))-FinancialService._num(adj.get("settled_amount")))
        amount=FinancialService._num(amount) or remain_adj
        if amount<=0 or amount>remain_adj+1e-9: raise ValueError(f"沖帳金額不可超過待沖金額 {remain_adj:,.2f}")
        target_id=adj.get(target_field); rows=data.get("receivables" if direction=="AR" else "payables",[]); target=next((x for x in rows if x.get("id")==target_id),None)
        if not target: raise ValueError("找不到原始應收／應付")
        target_open=FinancialService._open_receivable(target) if direction=="AR" else FinancialService._open_payable(target)
        if amount>target_open+1e-9: raise ValueError(f"沖帳金額不可超過目前未沖餘額 {target_open:,.2f}")
        adj["settled_amount"]=round(FinancialService._num(adj.get("settled_amount"))+amount,6); adj["status"]="已沖帳" if adj["settled_amount"]>=FinancialService._num(adj.get("amount"))-1e-9 else "部分沖帳"
        target["adjustment_amount"]=round(FinancialService._num(target.get("adjustment_amount"))+amount,6)
        if direction=="AR": FinancialService._refresh_receivable_status(target)
        else: FinancialService._refresh_payable_status(target)
        rec={"id":"SET-"+uuid.uuid4().hex[:10].upper(),"direction":direction,"adjustment_type":adjustment_type,"adjustment_id":adjustment_id,"target_id":target_id,
             "customer":target.get("customer",""),"supplier":target.get("supplier",""),"currency":target.get("currency","TWD"),"amount":round(amount,6),"settlement_date":settlement_date,"created_at":FinancialService._now()}
        data.setdefault("settlements",[]).append(rec); FinancialService.save(data); AuditLogService.log_event("財務","退貨折讓沖帳",record_id=rec["id"],after=rec,result="成功"); return rec

    @staticmethod
    def sales_adjustment_dataframes():
        data=FinancialService.load()
        sr=pd.DataFrame(data.get("sales_returns",[])); ia=pd.DataFrame(data.get("invoice_allowances",[]))
        return sr,ia

    @staticmethod
    def purchase_return_dataframe():
        return pd.DataFrame(FinancialService.load().get("purchase_returns",[]))

    @staticmethod
    def settlement_dataframe():
        return pd.DataFrame(FinancialService.load().get("settlements",[]))

    # ------------------------------------------------------------------
    # V6.5 月結 / 鎖帳
    # ------------------------------------------------------------------
    @staticmethod
    def month_close_preview(period):
        period=FinancialService._text(period)
        try: start=datetime.strptime(period+"-01","%Y-%m-%d").date()
        except Exception: raise ValueError("月份格式錯誤，請使用 YYYY-MM")
        last=calendar.monthrange(start.year,start.month)[1]; end=start.replace(day=last); data=FinancialService.load()
        def in_month(value):
            d=FinancialService._date_value(value); return bool(d and start<=d<=end)
        invoices=[x for x in data.get("invoices",[]) if in_month(x.get("invoice_date"))]
        receipts=[x for x in data.get("receipts",[]) if in_month(x.get("receipt_date"))]
        payments=[x for x in data.get("payments",[]) if in_month(x.get("payment_date"))]
        expenses=[x for x in data.get("expenses",[]) if in_month(x.get("expense_date"))]
        sr=[x for x in data.get("sales_returns",[]) if in_month(x.get("return_date"))]
        ia=[x for x in data.get("invoice_allowances",[]) if in_month(x.get("allowance_date"))]
        pr=[x for x in data.get("purchase_returns",[]) if in_month(x.get("return_date"))]
        st=[x for x in data.get("settlements",[]) if in_month(x.get("settlement_date"))]
        def twd_of(rows, amount_key, currency_key="currency", rate_key="fx_rate"):
            total=0.0; missing=0
            for x in rows:
                amt=FinancialService._num(x.get(amount_key)); cur=FinancialService._text(x.get(currency_key)) or "TWD"; rate=FinancialService._num(x.get(rate_key)) or FinancialService.get_rate(cur)
                if cur=="TWD": rate=1.0
                if rate<=0: missing+=1; continue
                total+=amt*rate
            return round(total,2),missing
        sales_twd,miss1=twd_of(invoices,"total_amount")
        receipt_twd=sum(FinancialService._num(x.get("amount_twd")) for x in receipts)
        payment_twd=sum(FinancialService._num(x.get("amount_twd"))+FinancialService._num(x.get("bank_fee_twd")) for x in payments)
        expense_twd=sum(FinancialService._num(x.get("amount_twd")) for x in expenses)
        ar_adj_twd,miss2=twd_of(sr+ia,"amount"); ap_adj_twd,miss3=twd_of(pr,"amount")
        rows=[
            {"項目":"銷售發票","筆數":len(invoices),"TWD金額":sales_twd},
            {"項目":"客戶收款","筆數":len(receipts),"TWD金額":round(receipt_twd,2)},
            {"項目":"銷售退貨/發票折讓","筆數":len(sr)+len(ia),"TWD金額":ar_adj_twd},
            {"項目":"供應商付款","筆數":len(payments),"TWD金額":round(payment_twd,2)},
            {"項目":"進貨退貨","筆數":len(pr),"TWD金額":ap_adj_twd},
            {"項目":"費用","筆數":len(expenses),"TWD金額":round(expense_twd,2)},
            {"項目":"沖帳紀錄","筆數":len(st),"TWD金額":0.0},
        ]
        open_ar=sum(FinancialService._open_receivable(x)*(1 if FinancialService._text(x.get("currency"))=="TWD" else FinancialService.get_rate(x.get("currency"))) for x in data.get("receivables",[]))
        open_ap=sum(FinancialService._open_payable(x)*(1 if FinancialService._text(x.get("currency"))=="TWD" else FinancialService.get_rate(x.get("currency"))) for x in data.get("payables",[]))
        summary={"period":period,"sales_twd":sales_twd,"receipts_twd":round(receipt_twd,2),"payments_twd":round(payment_twd,2),"expenses_twd":round(expense_twd,2),
                 "ar_adjustments_twd":ar_adj_twd,"ap_adjustments_twd":ap_adj_twd,"open_ar_twd":round(open_ar,2),"open_ap_twd":round(open_ap,2),"missing_fx_count":miss1+miss2+miss3}
        return pd.DataFrame(rows),summary

    @staticmethod
    def close_month(period, note=""):
        FinancialService._require_finance_write(); period=FinancialService._text(period)
        if FinancialService.is_period_closed(period): raise ValueError(f"{period} 已經完成月結")
        df,summary=FinancialService.month_close_preview(period)
        if summary.get("missing_fx_count",0)>0: raise ValueError("本月仍有缺少匯率的外幣資料，請補齊後再月結")
        data=FinancialService.load(); rec={"id":"CLOSE-"+uuid.uuid4().hex[:10].upper(),"period":period,"status":"已結帳","note":FinancialService._text(note),"snapshot":summary,"created_at":FinancialService._now()}
        data.setdefault("month_closes",[]).append(rec); FinancialService.save(data); AuditLogService.log_event("財務","月結鎖帳",record_id=rec["id"],after=rec,result="成功"); return rec

    @staticmethod
    def reopen_month(period, reason=""):
        FinancialService._require_finance_write()
        from services import role_rules
        if not role_rules.is_admin(): raise PermissionError("只有系統管理員可以重開已月結月份")
        period=FinancialService._text(period)
        if not FinancialService.is_period_closed(period): raise ValueError(f"{period} 目前不是已結帳狀態")
        reason=FinancialService._text(reason)
        if not reason: raise ValueError("重開月份必須填寫原因")
        data=FinancialService.load(); rec={"id":"REOPEN-"+uuid.uuid4().hex[:10].upper(),"period":period,"status":"已重開","reason":reason,"created_at":FinancialService._now()}
        data.setdefault("month_closes",[]).append(rec); FinancialService.save(data); AuditLogService.log_event("財務","重開月結",record_id=rec["id"],after=rec,result="成功"); return rec

    @staticmethod
    def month_close_history_dataframe():
        rows=[]
        for x in reversed(FinancialService.load().get("month_closes",[])):
            snap=x.get("snapshot",{}) or {}
            rows.append({"紀錄編號":x.get("id",""),"月份":x.get("period",""),"狀態":x.get("status",""),"建立時間":x.get("created_at",""),"銷售TWD":snap.get("sales_twd",0),"收款TWD":snap.get("receipts_twd",0),"付款TWD":snap.get("payments_twd",0),"費用TWD":snap.get("expenses_twd",0),"未收TWD":snap.get("open_ar_twd",0),"未付TWD":snap.get("open_ap_twd",0),"備註/原因":x.get("note","") or x.get("reason","")})
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # 摘要
    # ------------------------------------------------------------------
    @staticmethod
    def summary():
        data = FinancialService.load()
        payables = data["payables"]
        payments = data["payments"]
        receivables = data.get("receivables", [])
        receipts = data.get("receipts", [])
        expenses = data.get("expenses", [])

        unpaid_by_currency = {}
        payable_by_currency = {}
        for p in payables:
            c = FinancialService._text(p.get("currency")) or "TWD"
            total = FinancialService._num(p.get("total_amount"))
            paid = FinancialService._num(p.get("paid_amount"))
            payable_by_currency[c] = payable_by_currency.get(c, 0) + total
            unpaid_by_currency[c] = unpaid_by_currency.get(c, 0) + FinancialService._open_payable(p)

        uncollected_by_currency = {}
        receivable_by_currency = {}
        for r in receivables:
            c = FinancialService._text(r.get("currency")) or "TWD"
            total = FinancialService._num(r.get("total_amount"))
            received = FinancialService._num(r.get("received_amount"))
            receivable_by_currency[c] = receivable_by_currency.get(c, 0) + total
            uncollected_by_currency[c] = uncollected_by_currency.get(c, 0) + FinancialService._open_receivable(r)

        paid_twd = sum(FinancialService._num(x.get("amount_twd")) +
                       FinancialService._num(x.get("bank_fee_twd")) for x in payments)
        received_twd = sum(FinancialService._num(x.get("amount_twd")) -
                           FinancialService._num(x.get("bank_fee_twd")) for x in receipts)
        expense_twd = sum(FinancialService._num(x.get("amount_twd")) for x in expenses)
        import_shared = sum(sum(FinancialService._num(v) for v in s.get("costs_twd", {}).values())
                            for s in data["shipments"])
        _, margin = FinancialService.gross_margin_analysis()
        _, aging = FinancialService.receivable_aging()
        _, cashflow = FinancialService.cashflow_analysis()
        credit_df = FinancialService.customer_credit_status()
        over_credit_count = int((credit_df["狀態"] == "超額").sum()) if not credit_df.empty else 0
        near_credit_count = int((credit_df["狀態"] == "接近額度").sum()) if not credit_df.empty else 0
        _, forecast30 = FinancialService.cashflow_forecast(30)
        collection_df = FinancialService.collection_queue()
        pay_sched_df, pay_sched_summary = FinancialService.payment_schedule(30)
        sales_orders = data.get("sales_orders", [])
        pending_sales_orders = sum(1 for x in sales_orders if max(0.0, FinancialService._num(x.get("order_qty")) - FinancialService._num(x.get("delivered_qty"))) > 1e-9)
        pending_delivery_qty = sum(max(0.0, FinancialService._num(x.get("order_qty")) - FinancialService._num(x.get("delivered_qty"))) for x in sales_orders)
        return {
            "payable_count": len(payables),
            "payment_count": len(payments),
            "shipment_count": len(data["shipments"]),
            "payable_by_currency": payable_by_currency,
            "unpaid_by_currency": unpaid_by_currency,
            "paid_twd": round(paid_twd, 2),
            "import_shared_cost_twd": round(import_shared, 2),
            "receivable_count": len(receivables),
            "receipt_count": len(receipts),
            "receivable_by_currency": receivable_by_currency,
            "uncollected_by_currency": uncollected_by_currency,
            "received_twd": round(received_twd, 2),
            "expense_count": len(expenses),
            "expense_twd": round(expense_twd, 2),
            "gross_profit_twd": margin.get("gross_profit_twd", 0),
            "gross_margin_pct": margin.get("margin_pct", 0),
            "missing_cost_count": margin.get("missing_cost_count", 0),
            "overdue_count": aging.get("overdue_count", 0),
            "overdue_twd": aging.get("overdue_twd", 0),
            "cash_inflow_twd": cashflow.get("inflow_twd", 0),
            "cash_outflow_twd": cashflow.get("outflow_twd", 0),
            "cash_net_twd": cashflow.get("net_twd", 0),
            "sales_price_count": len(data.get("sales_prices", [])),
            "invoice_count": len(data.get("invoices", [])),
            "customer_terms_count": len(data.get("customer_terms", [])),
            "over_credit_count": over_credit_count,
            "near_credit_count": near_credit_count,
            "forecast_30d_inflow_twd": forecast30.get("forecast_inflow_twd", 0),
            "forecast_30d_outflow_twd": forecast30.get("forecast_outflow_twd", 0),
            "forecast_30d_net_twd": forecast30.get("forecast_net_twd", 0),
            "forecast_30d_ending_cash_twd": forecast30.get("ending_cash_twd", 0),
            "forecast_30d_negative_date": forecast30.get("negative_date", ""),
            "forecast_30d_missing_fx_count": forecast30.get("missing_fx_count", 0),
            "sales_order_count": len(sales_orders),
            "pending_sales_order_count": pending_sales_orders,
            "pending_delivery_qty": round(pending_delivery_qty, 2),
            "delivery_count": len(data.get("deliveries", [])),
            "collection_due_count": int(len(collection_df)) if collection_df is not None else 0,
            "payment_schedule_30d_count": pay_sched_summary.get("count", 0),
            "payment_schedule_30d_twd": pay_sched_summary.get("total_twd", 0),
            "sales_return_count": len(data.get("sales_returns", [])),
            "purchase_return_count": len(data.get("purchase_returns", [])),
            "invoice_allowance_count": len(data.get("invoice_allowances", [])),
            "settlement_count": len(data.get("settlements", [])),
            "closed_month_count": len({x.get("period") for x in data.get("month_closes", []) if x.get("status") == "已結帳"}),
        }
