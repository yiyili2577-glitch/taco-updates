import math

import pandas as pd


class PurchaseService:

    @staticmethod
    def to_number(value):
        try:
            if value is None:
                return 0.0
            if pd.isna(value):
                return 0.0
            if isinstance(value, str):
                value = value.replace(",", "").strip()
                if value == "":
                    return 0.0
            return float(value)
        except Exception:
            return 0.0

    @staticmethod
    def supplier_product_no(supplier):
        value = (
            supplier.get("product_no")
            or supplier.get("產品編號")
            or supplier.get("item_no")
            or supplier.get("料號")
            or ""
        )
        return str(value).strip()

    @staticmethod
    def build_supplier_map(suppliers):
        supplier_map = {}
        for supplier in suppliers:
            product_no = PurchaseService.supplier_product_no(supplier)
            if not product_no:
                continue
            supplier_map.setdefault(product_no, []).append(supplier)
        return supplier_map

    @staticmethod
    def get_suppliers_for_item(suppliers, product_no):
        product_no = str(product_no).strip()
        return [
            supplier
            for supplier in suppliers
            if PurchaseService.supplier_product_no(supplier) == product_no
        ]

    @staticmethod
    def find_supplier(suppliers, product_no, supplier_name):
        product_no = str(product_no).strip()
        supplier_name = str(supplier_name).strip()

        for supplier in suppliers:
            if (
                PurchaseService.supplier_product_no(supplier) == product_no
                and str(supplier.get("supplier", "")).strip() == supplier_name
            ):
                return supplier
        return None

    # =====================================================
    # 客戶需求
    # =====================================================

    @staticmethod
    def build_demand_map(customer_demand_df):
        result = {}

        if customer_demand_df is None or customer_demand_df.empty:
            return result

        if "產品編號" not in customer_demand_df.columns:
            return result

        for _, row in customer_demand_df.iterrows():
            product_no = str(row.get("產品編號", "")).strip()
            if not product_no:
                continue

            result[product_no] = {
                "產品編號": product_no,
                "產品名稱": str(row.get("產品名稱", "")).strip(),
                "客戶總需求量": PurchaseService.to_number(
                    row.get("總需求量", row.get("客戶總需求量", 0))
                ),
                "客戶直送需求": PurchaseService.to_number(
                    row.get("客戶直送量", row.get("客戶直送需求", 0))
                ),
                "供應商直送需求": PurchaseService.to_number(
                    row.get("供應商直送需求", row.get("客戶直送量", 0))
                ),
                "倉庫出貨需求": PurchaseService.to_number(
                    row.get("倉庫出貨需求", 0)
                ),
                "公司入庫需求": PurchaseService.to_number(
                    row.get("公司入庫量", row.get("公司入庫需求", 0))
                ),
                "計算用採購需求": PurchaseService.to_number(
                    row.get("計算用採購需求", row.get("總需求量", 0))
                ),
                "客戶數": int(round(PurchaseService.to_number(row.get("客戶數", 0)))),
                "最早到貨日": str(row.get("最早到貨日", "")).strip(),
                "客戶": str(row.get("客戶", "")).strip(),
            }

            # 三倉需求欄位名稱會跟使用者設定的倉名變動，因此動態保留。
            for column in customer_demand_df.columns:
                if str(column).endswith("出貨需求") and column not in result[product_no]:
                    result[product_no][str(column)] = PurchaseService.to_number(row.get(column, 0))

        return result

    @staticmethod
    def calculate_purchase_recommendations(
        inventory_df,
        suppliers,
        preferred_supplier_map=None,
        customer_demand_df=None,
    ):
        if inventory_df is None:
            inventory_df = pd.DataFrame()

        if preferred_supplier_map is None:
            preferred_supplier_map = {}

        supplier_map = PurchaseService.build_supplier_map(suppliers)
        demand_map = PurchaseService.build_demand_map(customer_demand_df)

        inventory_rows = []
        inventory_product_nos = set()

        if not inventory_df.empty:
            if "產品編號" not in inventory_df.columns:
                raise Exception("採購計算找不到「產品編號」。")

            for _, row in inventory_df.iterrows():
                product_no = str(row.get("產品編號", "")).strip()
                if not product_no:
                    continue
                inventory_product_nos.add(product_no)
                inventory_rows.append(row)

        # 客戶需求裡有、但庫存 Excel 沒有的產品也要列出來
        for product_no, demand in demand_map.items():
            if product_no in inventory_product_nos:
                continue

            inventory_rows.append(
                pd.Series({
                    "產品編號": product_no,
                    "產品名稱": demand.get("產品名稱", ""),
                    "平均月耗用量": 0,
                    "目前庫存": 0,
                    "預計到貨": 0,
                })
            )

        if not inventory_rows:
            return pd.DataFrame()

        results = []

        for row in inventory_rows:
            product_no = str(row.get("產品編號", "")).strip()
            available_suppliers = supplier_map.get(product_no, [])

            selected_supplier = None
            preferred_name = preferred_supplier_map.get(product_no)

            if preferred_name:
                for supplier in available_suppliers:
                    if str(supplier.get("supplier", "")).strip() == str(preferred_name).strip():
                        selected_supplier = supplier
                        break

            if selected_supplier is None and available_suppliers:
                selected_supplier = available_suppliers[0]

            results.append(
                PurchaseService.calculate_single_recommendation(
                    row,
                    selected_supplier,
                    demand_map.get(product_no, {})
                )
            )

        return pd.DataFrame(results)

    @staticmethod
    def calculate_single_recommendation(
        inventory_row,
        supplier,
        demand_record=None,
    ):
        if demand_record is None:
            demand_record = {}

        product_no = str(inventory_row.get("產品編號", "")).strip()
        product_name = str(inventory_row.get("產品名稱", "")).strip()

        if not product_name:
            product_name = str(demand_record.get("產品名稱", "")).strip()

        usage = PurchaseService.to_number(inventory_row.get("平均月耗用量", 0))
        stock = PurchaseService.to_number(inventory_row.get("目前庫存", 0))
        incoming = PurchaseService.to_number(inventory_row.get("預計到貨", 0))

        customer_total = PurchaseService.to_number(
            demand_record.get("客戶總需求量", 0)
        )
        direct_demand = PurchaseService.to_number(
            demand_record.get("客戶直送需求", 0)
        )
        supplier_direct_demand = PurchaseService.to_number(
            demand_record.get("供應商直送需求", direct_demand)
        )
        warehouse_out_demand = PurchaseService.to_number(
            demand_record.get("倉庫出貨需求", 0)
        )
        company_inbound_demand = PurchaseService.to_number(
            demand_record.get("公司入庫需求", 0)
        )
        calculation_demand = supplier_direct_demand + warehouse_out_demand

        customer_count = int(round(PurchaseService.to_number(
            demand_record.get("客戶數", 0)
        )))
        earliest_delivery = str(demand_record.get("最早到貨日", "")).strip()

        available_qty = stock + incoming
        # 只有「倉庫出貨」才扣公司庫存；供應商直送不可用公司庫存抵銷。
        stock_after_customer_demand = available_qty - warehouse_out_demand

        # 沒供應商時仍顯示需求與庫存缺口
        if supplier is None:
            immediate_gap = supplier_direct_demand + max(0, warehouse_out_demand - available_qty)

            if calculation_demand > 0:
                status = "🔴 有客戶需求／未設定供應商"
            else:
                status = "⚪ 未設定供應商"

            return {
                "狀態": status,
                "產品編號": product_no,
                "產品名稱": product_name,
                "平均月耗用量": round(usage, 2),
                "目前庫存": round(stock, 2),
                "預計到貨": round(incoming, 2),
                "客戶總需求量": round(customer_total, 2),
                "客戶直送需求": round(direct_demand, 2),
                "供應商直送需求": round(supplier_direct_demand, 2),
                "倉庫出貨需求": round(warehouse_out_demand, 2),
                "公司入庫需求": round(company_inbound_demand, 2),
                "計算用採購需求": round(calculation_demand, 2),
                "需求後剩餘庫存": round(stock_after_customer_demand, 2),
                "客戶需求即時缺口": round(immediate_gap, 2),
                "本次採購供應商": "",
                "總交期天數": 0,
                "交期預估耗用量": 0,
                "安全庫存月數": 0,
                "安全庫存量": 0,
                "目標總需求量": round(calculation_demand, 2),
                "原始建議量": round(immediate_gap, 2),
                "MOQ": 0,
                "採購倍數": 0,
                "建議採購量": 0,
                "現有可撐月數": (
                    round(available_qty / usage, 2)
                    if usage > 0
                    else 0
                ),
                "需求後可撐月數": (
                    round(max(0, stock_after_customer_demand) / usage, 2)
                    if usage > 0
                    else 0
                ),
                "採購後可撐月數": 0,
                "客戶數": customer_count,
                "最早到貨日": earliest_delivery,
            }

        supplier_name = str(supplier.get("supplier", "")).strip()
        lead_time_days = PurchaseService.to_number(
            supplier.get("lead_time_days", 0)
        )
        safety_months = PurchaseService.to_number(
            supplier.get("safety_months", 0)
        )
        moq = PurchaseService.to_number(
            supplier.get("moq", 0)
        )
        multiple = PurchaseService.to_number(
            supplier.get("order_multiple", 1)
        )

        if multiple <= 0:
            multiple = 1

        lead_months = lead_time_days / 30
        lead_usage = usage * lead_months
        safety_stock = usage * safety_months

        # 核心公式 V4：履約分流避免重複扣庫存。
        # 1) 供應商直送：一定形成新增採購需求，不能拿公司庫存抵銷。
        # 2) 倉庫出貨：先用公司庫存/在途支應，再補足交期耗用與安全庫存。
        # 3) 公司入庫：視為已安排入庫，不再重複列入「本次新增採購需求」。
        warehouse_replenishment_target = warehouse_out_demand + lead_usage + safety_stock
        warehouse_replenishment_gap = max(0, warehouse_replenishment_target - available_qty)
        target_total_demand = supplier_direct_demand + warehouse_replenishment_target
        raw_qty = supplier_direct_demand + warehouse_replenishment_gap

        immediate_gap = supplier_direct_demand + max(0, warehouse_out_demand - available_qty)

        final_qty = PurchaseService.apply_moq_and_multiple(
            raw_qty,
            moq,
            multiple
        )

        current_months = (
            available_qty / usage
            if usage > 0
            else 0
        )

        demand_after_available = max(0, stock_after_customer_demand)
        months_after_demand = (
            demand_after_available / usage
            if usage > 0
            else 0
        )

        months_after_purchase = (
            (available_qty + max(0, final_qty - supplier_direct_demand) - warehouse_out_demand) / usage
            if usage > 0
            else 0
        )

        if calculation_demand > 0 and immediate_gap > 0:
            status = "🔴 客戶需求已缺口／立即採購"
        elif usage <= 0 and calculation_demand > 0 and final_qty > 0:
            status = "🔴 有客戶需求／建議採購"
        elif usage <= 0 and calculation_demand <= 0:
            status = "⚪ 無耗用資料"
        elif final_qty <= 0:
            status = "🟢 暫不需採購"
        elif current_months < lead_months:
            status = "🔴 建議立即採購"
        else:
            status = "🟡 建議採購"

        return {
            "狀態": status,
            "產品編號": product_no,
            "產品名稱": product_name,
            "平均月耗用量": round(usage, 2),
            "目前庫存": round(stock, 2),
            "預計到貨": round(incoming, 2),
            "客戶總需求量": round(customer_total, 2),
            "客戶直送需求": round(direct_demand, 2),
            "供應商直送需求": round(supplier_direct_demand, 2),
            "倉庫出貨需求": round(warehouse_out_demand, 2),
            "公司入庫需求": round(company_inbound_demand, 2),
            "計算用採購需求": round(calculation_demand, 2),
            "需求後剩餘庫存": round(stock_after_customer_demand, 2),
            "客戶需求即時缺口": round(immediate_gap, 2),
            "本次採購供應商": supplier_name,
            "總交期天數": int(round(lead_time_days)),
            "交期預估耗用量": round(lead_usage, 2),
            "安全庫存月數": round(safety_months, 1),
            "安全庫存量": round(safety_stock, 2),
            "倉庫補貨缺口": round(warehouse_replenishment_gap, 2),
            "目標總需求量": round(target_total_demand, 2),
            "原始建議量": round(raw_qty, 2),
            "MOQ": int(round(moq)),
            "採購倍數": int(round(multiple)),
            "建議採購量": int(final_qty),
            "現有可撐月數": round(current_months, 2),
            "需求後可撐月數": round(months_after_demand, 2),
            "採購後可撐月數": round(max(0, months_after_purchase), 2),
            "客戶數": customer_count,
            "最早到貨日": earliest_delivery,
        }

    @staticmethod
    def apply_moq_and_multiple(qty, moq, multiple):
        qty = PurchaseService.to_number(qty)
        moq = PurchaseService.to_number(moq)
        multiple = PurchaseService.to_number(multiple)

        if qty <= 0:
            return 0

        if moq > 0:
            qty = max(qty, moq)

        if multiple <= 0:
            multiple = 1

        return int(
            math.ceil(qty / multiple) * multiple
        )
