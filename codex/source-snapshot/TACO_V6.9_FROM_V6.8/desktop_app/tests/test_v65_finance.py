import os
import tempfile
import unittest
from unittest.mock import patch

from services.financial_service import FinancialService


class TestV65Finance(unittest.TestCase):
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

    def test_sales_return_then_settlement_reduces_ar(self):
        ar = FinancialService.create_receivable('A醫院', 'P1', '紗布', 10, '包', 'TWD', unit_price=100)
        ret = FinancialService.create_sales_return(ar['id'], '2026-08-13', qty=2, amount=200, reason='退貨')
        self.assertEqual(ret['status'], '待沖帳')
        data = FinancialService.load(); ar0 = data['receivables'][0]
        self.assertAlmostEqual(FinancialService._open_receivable(ar0), 1000)
        FinancialService.settle_adjustment('銷售退貨', ret['id'], 200, '2026-08-13')
        data = FinancialService.load(); ar1 = data['receivables'][0]
        self.assertAlmostEqual(FinancialService._open_receivable(ar1), 800)
        self.assertAlmostEqual(ar1['adjustment_amount'], 200)

    def test_invoice_allowance_requires_invoice_and_can_settle(self):
        ar = FinancialService.create_receivable('B醫院', 'P1', '商品', 1, '件', 'TWD', total_amount=1000)
        with self.assertRaises(ValueError):
            FinancialService.create_invoice_allowance(ar['id'], 'AL001', '2026-08-13', 100)
        FinancialService.issue_invoice_from_receivable(ar['id'], 'INV001', '2026-08-13', 5, 'NET30')
        al = FinancialService.create_invoice_allowance(ar['id'], 'AL001', '2026-08-14', 100, '價格折讓')
        FinancialService.settle_adjustment('發票折讓', al['id'], 100, '2026-08-14')
        df = FinancialService.invoice_dataframe()
        self.assertAlmostEqual(float(df.iloc[0]['未收金額']), 900)
        self.assertAlmostEqual(float(df.iloc[0]['退貨/折讓沖帳']), 100)

    def test_purchase_return_then_settlement_reduces_ap(self):
        data = FinancialService.load()
        data['payables'] = [{'id':'AP1','supplier':'供應商A','product_no':'P1','product_name':'棉棒','currency':'TWD','total_amount':5000,'paid_amount':1000,'adjustment_amount':0,'status':'部分付款'}]
        FinancialService.save(data)
        ret = FinancialService.create_purchase_return('AP1', '2026-08-13', qty=1, amount=500, reason='品質不良')
        FinancialService.settle_adjustment('進貨退貨', ret['id'], 500, '2026-08-13')
        ap = FinancialService.load()['payables'][0]
        self.assertAlmostEqual(FinancialService._open_payable(ap), 3500)
        df, summary = FinancialService.payment_schedule(90, '2026-08-13')
        self.assertAlmostEqual(summary['total_twd'], 3500)

    def test_customer_statement_includes_adjustment_settlement(self):
        ar = FinancialService.create_receivable('C醫院', 'P1', '商品', 1, '件', 'TWD', total_amount=1000)
        FinancialService.issue_invoice_from_receivable(ar['id'], 'INV-C', '2026-08-01', 5, 'NET30')
        ret = FinancialService.create_sales_return(ar['id'], '2026-08-10', amount=200)
        FinancialService.settle_adjustment('銷售退貨', ret['id'], 200, '2026-08-10')
        df, summary = FinancialService.customer_statement('C醫院', '2026-08-01', '2026-08-31')
        self.assertIn('退貨/折讓沖帳', set(df['類型']))
        self.assertAlmostEqual(summary['closing'], 800)

    def test_month_close_locks_posting_and_reopen_unlocks(self):
        ar = FinancialService.create_receivable('D醫院', 'P1', '商品', 1, '件', 'TWD', total_amount=1000)
        FinancialService.issue_invoice_from_receivable(ar['id'], 'INV-D', '2026-08-01', 5, 'NET30')
        FinancialService.close_month('2026-08', '測試月結')
        self.assertTrue(FinancialService.is_period_closed('2026-08'))
        with self.assertRaises(ValueError):
            FinancialService.record_receipt(ar['id'], 100, '2026-08-20')
        with patch('services.role_rules.is_admin', return_value=True):
            FinancialService.reopen_month('2026-08', '補登銀行入帳')
        self.assertFalse(FinancialService.is_period_closed('2026-08'))
        FinancialService.record_receipt(ar['id'], 100, '2026-08-20')
        self.assertAlmostEqual(FinancialService.load()['receivables'][0]['received_amount'], 100)

    def test_month_close_preview(self):
        ar = FinancialService.create_receivable('E醫院', 'P1', '商品', 1, '件', 'TWD', total_amount=1000)
        FinancialService.issue_invoice_from_receivable(ar['id'], 'INV-E', '2026-08-01', 5, 'NET30')
        FinancialService.record_receipt(ar['id'], 400, '2026-08-05')
        FinancialService.create_expense('2026-08-06', '運費', 100, 'TWD')
        df, summary = FinancialService.month_close_preview('2026-08')
        self.assertGreaterEqual(len(df), 7)
        self.assertAlmostEqual(summary['sales_twd'], 1000)
        self.assertAlmostEqual(summary['receipts_twd'], 400)
        self.assertAlmostEqual(summary['expenses_twd'], 100)


if __name__ == '__main__':
    unittest.main()
