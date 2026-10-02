import os
import tempfile
import unittest
from unittest.mock import patch

from services.financial_service import FinancialService


class TestV63Finance(unittest.TestCase):
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

    def test_due_date_rules(self):
        self.assertEqual(FinancialService.calculate_due_date('2026-08-13', 'NET30'), '2026-09-12')
        self.assertEqual(FinancialService.calculate_due_date('2026-08-13', 'CASH'), '2026-08-13')
        self.assertEqual(FinancialService.calculate_due_date('2026-08-13', 'EOM30'), '2026-09-30')

    def test_credit_limit_and_policy(self):
        FinancialService.upsert_customer_terms('A醫院', 1000, 'NET30', 'TWD', 80, '禁止超額')
        FinancialService.create_receivable('A醫院', 'P1', '商品', 1, '件', 'TWD', total_amount=600)
        status = FinancialService.check_credit('A醫院', 300)
        self.assertTrue(status['allowed'])
        self.assertAlmostEqual(status['projected_twd'], 900)
        with self.assertRaises(ValueError):
            FinancialService.create_receivable('A醫院', 'P2', '商品2', 1, '件', 'TWD', total_amount=500)

    def test_issue_invoice_uses_customer_terms(self):
        FinancialService.upsert_customer_terms('B醫院', 50000, 'NET45', 'TWD', 80, '警示')
        ar = FinancialService.create_receivable('B醫院', 'P1', '紗布', 10, '包', 'TWD', unit_price=100)
        inv = FinancialService.issue_invoice_from_receivable(ar['id'], 'AB12345678', '2026-08-13', 5)
        self.assertEqual(inv['term_code'], 'NET45')
        self.assertEqual(inv['due_date'], '2026-09-27')
        data = FinancialService.load()
        self.assertEqual(len(data['invoices']), 1)
        ar2 = data['receivables'][0]
        self.assertEqual(ar2['invoice_no'], 'AB12345678')
        self.assertEqual(ar2['due_date'], '2026-09-27')

    def test_cashflow_forecast(self):
        data = FinancialService.load()
        data['cash_settings'] = {'opening_cash_twd': 10000}
        data['receivables'] = [{
            'id':'AR1','customer':'C','currency':'TWD','total_amount':5000,'received_amount':0,
            'due_date':'2026-08-20','status':'未收款'
        }]
        data['payables'] = [{
            'id':'AP1','supplier':'S','currency':'TWD','total_amount':8000,'paid_amount':0,
            'expected_payment_date':'2026-08-25','created_at':'2026-08-01T00:00:00'
        }]
        FinancialService.save(data)
        df, s = FinancialService.cashflow_forecast(30, '2026-08-13')
        self.assertEqual(len(df), 2)
        self.assertAlmostEqual(s['forecast_inflow_twd'], 5000)
        self.assertAlmostEqual(s['forecast_outflow_twd'], 8000)
        self.assertAlmostEqual(s['ending_cash_twd'], 7000)
        self.assertEqual(s['negative_date'], '')

    def test_manual_cashflow_plan(self):
        FinancialService.set_opening_cash(1000)
        FinancialService.add_cashflow_plan('2026-08-15', '流出', 1200, 'TWD', '薪資')
        _, s = FinancialService.cashflow_forecast(30, '2026-08-13')
        self.assertEqual(s['negative_date'], '2026-08-15')
        self.assertAlmostEqual(s['ending_cash_twd'], -200)

    def test_invalid_business_dates_are_rejected(self):
        ar = FinancialService.create_receivable('日期測試客戶', 'P1', '商品', 1, '件', 'TWD', total_amount=100)
        with self.assertRaises(ValueError):
            FinancialService.issue_invoice_from_receivable(ar['id'], 'INV001', '2026/99/99', 5)
        with self.assertRaises(ValueError):
            FinancialService.add_cashflow_plan('not-a-date', '流出', 100, 'TWD', '其他')

    def test_invoice_status_tracks_receipts(self):
        ar = FinancialService.create_receivable('收款測試客戶', 'P1', '商品', 1, '件', 'TWD', total_amount=1000)
        FinancialService.issue_invoice_from_receivable(ar['id'], 'AB12345678', '2026-08-13', 5, 'NET30')
        df = FinancialService.invoice_dataframe()
        self.assertEqual(df.iloc[0]['狀態'], '未收款')
        FinancialService.record_receipt(ar['id'], 400, '2026-08-20')
        df = FinancialService.invoice_dataframe()
        self.assertEqual(df.iloc[0]['狀態'], '部分收款')
        FinancialService.record_receipt(ar['id'], 600, '2026-08-21')
        df = FinancialService.invoice_dataframe()
        self.assertEqual(df.iloc[0]['狀態'], '已收款')

    def test_forecast_reports_missing_fx(self):
        data = FinancialService.load()
        data['cash_settings'] = {'opening_cash_twd': 10000}
        data['receivables'] = [{
            'id':'ARUSD','customer':'外幣客戶','currency':'USD','total_amount':100,'received_amount':0,
            'due_date':'2026-08-20','status':'未收款'
        }]
        FinancialService.save(data)
        df, summary = FinancialService.cashflow_forecast(30, '2026-08-13')
        self.assertTrue(df.empty)
        self.assertEqual(summary['missing_fx_count'], 1)
        self.assertEqual(summary['ending_cash_twd'], 10000)


if __name__ == '__main__':
    unittest.main()
