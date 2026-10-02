import os
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from services.financial_service import FinancialService
from services.container_planning_service import ContainerPlanningService
from services.import_profile_service import ImportProfileService


class V60FinanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_finance = FinancialService.DATA_FILE
        self.old_import = ImportProfileService.DATA_FILE
        FinancialService.DATA_FILE = os.path.join(self.tmp.name, "finance.json")
        ImportProfileService.DATA_FILE = os.path.join(self.tmp.name, "profiles.json")
        ImportProfileService.DATA_DIR = self.tmp.name

    def tearDown(self):
        FinancialService.DATA_FILE = self.old_finance
        ImportProfileService.DATA_FILE = self.old_import
        self.tmp.cleanup()

    def test_import_profile_calculates_cartons_cbm_and_amount(self):
        profile = {
            "currency":"USD", "unit_price":0.0221, "price_unit":"包",
            "purchase_qty_unit":"包", "packing_method":"10包/束 10束/袋 1200包/箱",
            "units_per_carton":1200, "carton_length_cm":42, "carton_width_cm":30,
            "carton_height_cm":40, "container_cbm":66.5,
        }
        m = ImportProfileService.calculate(120000, profile)
        self.assertEqual(m["換算箱數"], 100)
        self.assertAlmostEqual(m["單箱CBM"], 0.0504, places=4)
        self.assertAlmostEqual(m["本次CBM"], 5.04, places=2)
        self.assertAlmostEqual(m["商品總價"], 2652.0, places=2)

    @patch("services.financial_service.FinancialService._require_finance_write")
    @patch("services.financial_service.AuditLogService.log_event")
    @patch("services.financial_service.DashboardDataService.load_purchase_df")
    def test_sync_payables_and_payment(self, load_purchase, _log, _perm):
        load_purchase.return_value = (pd.DataFrame([{
            "產品編號":"A01", "產品名稱":"測試品", "本次採購供應商":"供應商甲",
            "實際採購量":1000, "採購數量單位":"包", "幣別":"USD", "單價":0.5,
            "計價單位":"包", "計價數量":1000, "商品總價":500,
        }]), {"updated_at":"2026-08-13T01:00:00"})
        result = FinancialService.sync_payables_from_purchase()
        self.assertEqual(result["created"], 1)
        data = FinancialService.load(); p = data["payables"][0]
        self.assertEqual(p["total_amount"], 500)
        FinancialService.upsert_rate("USD", 30.0, "2026-08-13")
        FinancialService.record_payment(p["id"], 200, "2026-08-13", 30.0, 100)
        p2 = FinancialService.load()["payables"][0]
        self.assertEqual(p2["status"], "部分付款")
        self.assertEqual(p2["paid_amount"], 200)

    def test_container_plan_explains_missing_profile(self):
        df = pd.DataFrame([{
            "產品編號":"A01", "產品名稱":"測試品", "本次採購供應商":"供應商甲", "實際採購量":100,
        }])
        result = ContainerPlanningService.build_plan(df)
        self.assertEqual(len(result["valid_df"]), 0)
        self.assertEqual(len(result["issues_df"]), 1)
        self.assertIn("尚未建立包裝", result["issues_df"].iloc[0]["問題"])


if __name__ == "__main__":
    unittest.main()
