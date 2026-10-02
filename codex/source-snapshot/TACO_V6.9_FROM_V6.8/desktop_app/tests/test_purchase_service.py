"""services/purchase_service.py 的單元測試。

這是全系統最核心也風險最高的計算邏輯（採購建議量），原本完全沒有測試覆蓋。
這份測試涵蓋：MOQ / 訂購倍數的無條件進位規則，以及沒有供應商、庫存充足、
庫存不足、供應商直送與倉庫出貨不能互相抵銷這幾種關鍵情境，確保之後修改
公式時，一旦不小心改壞既有行為，測試會立刻失敗提醒。

執行方式（不需要安裝 PyQt6，因為 PurchaseService 本身不依賴 PyQt6）：
    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.purchase_service import PurchaseService


def make_inventory_row(product_no="P001", product_name="測試產品", usage=100, stock=50, incoming=0):
    return pd.Series({
        "產品編號": product_no,
        "產品名稱": product_name,
        "平均月耗用量": usage,
        "目前庫存": stock,
        "預計到貨": incoming,
    })


def make_supplier(name="供應商A", lead_time_days=30, safety_months=1, moq=0, order_multiple=1):
    return {
        "supplier": name,
        "lead_time_days": lead_time_days,
        "safety_months": safety_months,
        "moq": moq,
        "order_multiple": order_multiple,
    }


def make_demand(total=0, direct=0, supplier_direct=None, warehouse_out=0, company_inbound=0, customer_count=0):
    return {
        "客戶總需求量": total,
        "客戶直送需求": direct,
        "供應商直送需求": supplier_direct if supplier_direct is not None else direct,
        "倉庫出貨需求": warehouse_out,
        "公司入庫需求": company_inbound,
        "客戶數": customer_count,
        "最早到貨日": "",
    }


class ApplyMoqAndMultipleTests(unittest.TestCase):
    def test_zero_or_negative_qty_returns_zero(self):
        self.assertEqual(PurchaseService.apply_moq_and_multiple(0, moq=100, multiple=10), 0)
        self.assertEqual(PurchaseService.apply_moq_and_multiple(-5, moq=100, multiple=10), 0)

    def test_qty_below_moq_rounds_up_to_moq(self):
        # 需求只有 30，但 MOQ 是 200 -> 至少要訂 200
        self.assertEqual(PurchaseService.apply_moq_and_multiple(30, moq=200, multiple=1), 200)

    def test_qty_rounds_up_to_next_multiple(self):
        # 205 在 multiple=50 時，應該無條件進位到 250，不能只進位到 200（低於需求）
        self.assertEqual(PurchaseService.apply_moq_and_multiple(205, moq=0, multiple=50), 250)

    def test_multiple_zero_defaults_to_one(self):
        self.assertEqual(PurchaseService.apply_moq_and_multiple(37, moq=0, multiple=0), 37)

    def test_moq_and_multiple_combined(self):
        # 需求 30，MOQ 200，multiple 150 -> 先頂到 200，再無條件進位到 150 的倍數 = 300
        self.assertEqual(PurchaseService.apply_moq_and_multiple(30, moq=200, multiple=150), 300)


class CalculateSingleRecommendationTests(unittest.TestCase):
    def test_no_supplier_no_demand_is_neutral_status(self):
        row = make_inventory_row(usage=0, stock=0, incoming=0)
        result = PurchaseService.calculate_single_recommendation(row, supplier=None, demand_record={})
        self.assertEqual(result["建議採購量"], 0)
        self.assertIn("未設定供應商", result["狀態"])
        self.assertNotIn("🔴", result["狀態"])

    def test_no_supplier_with_demand_flags_red_status(self):
        row = make_inventory_row(usage=100, stock=0, incoming=0)
        demand = make_demand(warehouse_out=50)
        result = PurchaseService.calculate_single_recommendation(row, supplier=None, demand_record=demand)
        self.assertIn("🔴", result["狀態"])
        # 沒有供應商時，即時缺口應該還是要算出來，讓使用者知道有多少缺口待處理
        self.assertEqual(result["客戶需求即時缺口"], 50)

    def test_sufficient_stock_needs_no_purchase(self):
        # 庫存遠高於需求 + 安全庫存 + 交期耗用，理論上不用採購
        row = make_inventory_row(usage=10, stock=1000, incoming=0)
        supplier = make_supplier(lead_time_days=30, safety_months=1)
        demand = make_demand(warehouse_out=20)
        result = PurchaseService.calculate_single_recommendation(row, supplier, demand)
        self.assertEqual(result["建議採購量"], 0)
        self.assertIn("暫不需採購", result["狀態"])

    def test_insufficient_stock_triggers_purchase(self):
        row = make_inventory_row(usage=100, stock=50, incoming=0)
        supplier = make_supplier(lead_time_days=30, safety_months=1)
        demand = make_demand(warehouse_out=500)
        result = PurchaseService.calculate_single_recommendation(row, supplier, demand)
        self.assertGreater(result["建議採購量"], 0)

    def test_supplier_direct_demand_is_never_offset_by_company_stock(self):
        # 核心規則：供應商直送需求無論公司庫存多高，都必須形成新增採購量，
        # 因為公司庫存不會拿去給供應商直送的訂單抵用。
        row = make_inventory_row(usage=10, stock=100000, incoming=0)
        supplier = make_supplier(lead_time_days=0, safety_months=0)
        demand = make_demand(supplier_direct=300, warehouse_out=0)
        result = PurchaseService.calculate_single_recommendation(row, supplier, demand)
        self.assertGreaterEqual(result["建議採購量"], 300)

    def test_moq_is_applied_to_final_recommended_qty(self):
        row = make_inventory_row(usage=0, stock=0, incoming=0)
        supplier = make_supplier(lead_time_days=0, safety_months=0, moq=500, order_multiple=1)
        demand = make_demand(supplier_direct=10)
        result = PurchaseService.calculate_single_recommendation(row, supplier, demand)
        self.assertEqual(result["建議採購量"], 500)

    def test_zero_demand_and_zero_gap_needs_no_purchase(self):
        row = make_inventory_row(usage=50, stock=200, incoming=0)
        supplier = make_supplier(lead_time_days=15, safety_months=0.5)
        demand = make_demand()
        result = PurchaseService.calculate_single_recommendation(row, supplier, demand)
        self.assertEqual(result["建議採購量"], 0)


class BuildSupplierMapTests(unittest.TestCase):
    def test_groups_suppliers_by_product_no(self):
        suppliers = [
            {"product_no": "P001", "supplier": "A"},
            {"product_no": "P001", "supplier": "B"},
            {"product_no": "P002", "supplier": "C"},
        ]
        supplier_map = PurchaseService.build_supplier_map(suppliers)
        self.assertEqual(len(supplier_map["P001"]), 2)
        self.assertEqual(len(supplier_map["P002"]), 1)

    def test_suppliers_without_product_no_are_skipped(self):
        suppliers = [{"supplier": "NoProductNo"}]
        supplier_map = PurchaseService.build_supplier_map(suppliers)
        self.assertEqual(supplier_map, {})


if __name__ == "__main__":
    unittest.main()
