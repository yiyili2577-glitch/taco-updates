import unittest
import pandas as pd

from services.financial_service import FinancialService


class TestV65LegacyFinanceHotfix(unittest.TestCase):
    def test_missing_adjustment_amount_returns_aligned_zero_series(self):
        df = pd.DataFrame([
            {"id": "AP1", "total_amount": 5000, "paid_amount": 1000},
            {"id": "AP2", "total_amount": "2000", "paid_amount": None},
        ])
        adjusted = FinancialService._numeric_series(df, "adjustment_amount")
        self.assertEqual(list(adjusted), [0.0, 0.0])
        remaining = FinancialService._numeric_series(df, "total_amount") - FinancialService._numeric_series(df, "paid_amount") - adjusted
        self.assertEqual(list(remaining), [4000.0, 2000.0])

    def test_open_balance_includes_adjustments(self):
        payable = {"total_amount": 10000, "paid_amount": 3000, "adjustment_amount": 1500}
        receivable = {"total_amount": 10000, "received_amount": 3000, "adjustment_amount": 1500}
        self.assertEqual(FinancialService._open_payable(payable), 5500)
        self.assertEqual(FinancialService._open_receivable(receivable), 5500)


if __name__ == "__main__":
    unittest.main()
