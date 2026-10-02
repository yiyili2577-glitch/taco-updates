import os
import tempfile
import unittest
from unittest.mock import patch

from services.financial_service import FinancialService


class TestV62Finance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_file = FinancialService.DATA_FILE
        self.old_dir = FinancialService.DATA_DIR
        FinancialService.DATA_DIR = self.tmp.name
        FinancialService.DATA_FILE = os.path.join(self.tmp.name, 'finance_data.json')
        self.auth = patch.object(FinancialService, '_require_finance_write', staticmethod(lambda: None))
        self.audit = patch('services.financial_service.AuditLogService.log_event', return_value=None)
        self.auth.start(); self.audit.start()

    def tearDown(self):
        self.auth.stop(); self.audit.stop()
        FinancialService.DATA_FILE = self.old_file
        FinancialService.DATA_DIR = self.old_dir
        self.tmp.cleanup()

    def test_sales_price_upsert(self):
        FinancialService.upsert_sales_price('A醫院', 'P001', 12.5, 'TWD', '包')
        rec = FinancialService.get_sales_price('A醫院', 'P001')
        self.assertIsNotNone(rec)
        self.assertEqual(rec['currency'], 'TWD')
        self.assertAlmostEqual(rec['unit_price'], 12.5)
        FinancialService.upsert_sales_price('A醫院', 'P001', 13.0, 'TWD', '包')
        rows = FinancialService.load()['sales_prices']
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]['unit_price'], 13.0)

    def test_receivable_aging(self):
        data = FinancialService.load()
        data['receivables'] = [{
            'id':'AR-1','customer':'A醫院','product_no':'P1','product_name':'產品',
            'currency':'TWD','total_amount':1000,'received_amount':200,
            'invoice_date':'2026-06-01','due_date':'2026-07-01','status':'部分收款'
        }]
        FinancialService.save(data)
        df, s = FinancialService.receivable_aging('2026-08-13')
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]['帳齡區間'], '逾期31-60天')
        self.assertEqual(s['overdue_count'], 1)
        self.assertAlmostEqual(s['overdue_twd'], 800.0)

    def test_cashflow(self):
        data = FinancialService.load()
        data['receipts'] = [{'receipt_date':'2026-08-01','customer':'A','amount_twd':10000,'bank_fee_twd':100}]
        data['payments'] = [{'payment_date':'2026-08-02','supplier':'S','amount_twd':3000,'bank_fee_twd':50}]
        data['expenses'] = [{'expense_date':'2026-08-03','vendor':'V','amount_twd':500}]
        FinancialService.save(data)
        df, s = FinancialService.cashflow_analysis()
        self.assertEqual(len(df), 3)
        self.assertAlmostEqual(s['inflow_twd'], 10000)
        self.assertAlmostEqual(s['outflow_twd'], 3650)
        self.assertAlmostEqual(s['net_twd'], 6350)


if __name__ == '__main__':
    unittest.main()
