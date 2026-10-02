import os
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from services.financial_service import FinancialService


class V61FinanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_file = FinancialService.DATA_FILE
        FinancialService.DATA_FILE = os.path.join(self.tmp.name, "finance.json")

    def tearDown(self):
        FinancialService.DATA_FILE = self.old_file
        self.tmp.cleanup()

    @patch("services.financial_service.FinancialService._require_finance_write")
    @patch("services.financial_service.AuditLogService.log_event")
    def test_manual_receivable_and_partial_receipt(self, _log, _perm):
        ar = FinancialService.create_receivable(
            customer="客戶甲", product_no="A01", product_name="測試品",
            qty=100, qty_unit="包", currency="TWD", unit_price=20,
            invoice_date="2026-08-13"
        )
        self.assertEqual(ar["total_amount"], 2000)
        FinancialService.record_receipt(ar["id"], 800, "2026-08-13")
        ar2 = FinancialService.load()["receivables"][0]
        self.assertEqual(ar2["received_amount"], 800)
        self.assertEqual(ar2["status"], "部分收款")

    @patch("services.financial_service.FinancialService._require_finance_write")
    @patch("services.financial_service.AuditLogService.log_event")
    @patch("services.financial_service.CustomerDemandStoreService.load_snapshot")
    @patch("services.financial_service.CustomerDemandStoreService.load_detail")
    def test_sync_receivable_only_when_amount_exists(self, load_detail, load_snapshot, _log, _perm):
        load_snapshot.return_value = {"updated_at":"2026-08-13T02:00:00", "source_file":"需求.xlsx"}
        load_detail.return_value = pd.DataFrame([
            {"客戶":"A醫院","產品編號":"P01","產品名稱":"紗布","數量":10,"單價":30,"總價":0,"幣別":"TWD","客戶訂號":"O1"},
            {"客戶":"B醫院","產品編號":"P02","產品名稱":"棉棒","數量":20,"單價":0,"總價":0,"幣別":"TWD","客戶訂號":"O2"},
        ])
        result = FinancialService.sync_receivables_from_customer_demand()
        self.assertEqual(result["created"], 1)
        self.assertEqual(result["skipped_no_amount"], 1)
        ar = FinancialService.load()["receivables"][0]
        self.assertEqual(ar["total_amount"], 300)

    @patch("services.financial_service.FinancialService._require_finance_write")
    @patch("services.financial_service.AuditLogService.log_event")
    def test_expense_converts_to_twd(self, _log, _perm):
        FinancialService.upsert_rate("USD", 30.5, "2026-08-13")
        exp = FinancialService.create_expense("2026-08-13", "差旅", 100, "USD", 30.5)
        self.assertEqual(exp["amount_twd"], 3050)

    @patch("services.financial_service.FinancialService._require_finance_write")
    @patch("services.financial_service.AuditLogService.log_event")
    def test_gross_margin_uses_latest_landed_cost(self, _log, _perm):
        FinancialService.upsert_rate("USD", 30, "2026-08-13")
        data = FinancialService.load()
        data["shipments"] = [{
            "id":"IMP-1", "created_at":"2026-08-13T01:00:00", "total_cbm":1,
            "costs_twd":{"ocean_freight":1000},
            "rows":[{"產品編號":"P01","產品名稱":"紗布","本次採購供應商":"S1","幣別":"USD","商品總價":100,"本次CBM":1,"計價數量":100}]
        }]
        data["receivables"] = [{
            "id":"AR-1","customer":"C1","product_no":"P01","product_name":"紗布",
            "qty":10,"currency":"TWD","total_amount":600,"received_amount":0
        }]
        FinancialService.save(data)
        df, summary = FinancialService.gross_margin_analysis()
        # landed = USD100*30 + shared1000 = 4000 / 100 = 40 per unit; cost 400; GP 200
        self.assertAlmostEqual(df.iloc[0]["最近落地單位成本TWD"], 40, places=4)
        self.assertAlmostEqual(summary["gross_profit_twd"], 200, places=2)
        self.assertAlmostEqual(summary["margin_pct"], 33.3333, places=2)


if __name__ == "__main__":
    unittest.main()
