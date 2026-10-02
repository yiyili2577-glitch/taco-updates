import os
import tempfile
import unittest
from unittest.mock import patch

from services.financial_service import FinancialService


class TestV64Finance(unittest.TestCase):
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

    def test_sales_order_delivery_receivable_invoice_flow(self):
        FinancialService.upsert_customer_terms('A醫院', 100000, 'NET30', 'TWD', 80, '警示')
        order = FinancialService.create_sales_order(
            'A醫院', 'PO-001', 'P001', '紗布', 100, '包', 'TWD', 10,
            '2026-08-13', '2026-08-20'
        )
        self.assertEqual(order['status'], '待出貨')
        d1 = FinancialService.record_delivery(order['id'], 40, '2026-08-15', 'D001', '總倉')
        data = FinancialService.load()
        o = data['sales_orders'][0]
        self.assertEqual(o['status'], '部分出貨')
        self.assertAlmostEqual(o['delivered_qty'], 40)
        ar = FinancialService.create_receivable_from_delivery(d1['id'])
        self.assertAlmostEqual(ar['total_amount'], 400)
        inv = FinancialService.issue_invoice_from_delivery(d1['id'], 'AB12340001', '2026-08-15', 5)
        self.assertEqual(inv['due_date'], '2026-09-14')
        data = FinancialService.load()
        self.assertEqual(data['deliveries'][0]['invoice_no'], 'AB12340001')

    def test_customer_statement(self):
        ar = FinancialService.create_receivable('B醫院', 'P1', '商品', 1, '件', 'TWD', total_amount=1000)
        FinancialService.issue_invoice_from_receivable(ar['id'], 'INV001', '2026-08-01', 5, 'NET30')
        FinancialService.record_receipt(ar['id'], 400, '2026-08-10')
        df, s = FinancialService.customer_statement('B醫院', '2026-08-01', '2026-08-31')
        self.assertEqual(len(df), 2)
        self.assertAlmostEqual(s['debit'], 1000)
        self.assertAlmostEqual(s['credit'], 400)
        self.assertAlmostEqual(s['closing'], 600)

    def test_collection_queue_and_action(self):
        ar = FinancialService.create_receivable('C醫院', 'P1', '商品', 1, '件', 'TWD', total_amount=1000,
                                                invoice_date='2026-06-01', due_date='2026-06-30')
        q = FinancialService.collection_queue('2026-08-13')
        self.assertEqual(len(q), 1)
        self.assertGreater(int(q.iloc[0]['逾期天數']), 30)
        FinancialService.add_collection_action(ar['id'], '2026-08-13', '電話', '承諾付款', '2026-08-20')
        q = FinancialService.collection_queue('2026-08-13')
        self.assertEqual(q.iloc[0]['最後方式'], '電話')
        self.assertEqual(q.iloc[0]['下次追蹤'], '2026-08-20')

    def test_payment_schedule(self):
        data = FinancialService.load()
        data['payables'] = [
            {'id':'AP1','supplier':'供應商A','product_no':'P1','currency':'TWD','total_amount':5000,'paid_amount':1000,
             'expected_payment_date':'2026-08-20','created_at':'2026-08-01T00:00:00','status':'部分付款'},
            {'id':'AP2','supplier':'供應商B','product_no':'P2','currency':'TWD','total_amount':2000,'paid_amount':0,
             'expected_payment_date':'2026-12-20','created_at':'2026-08-01T00:00:00','status':'未付款'},
        ]
        FinancialService.save(data)
        df, s = FinancialService.payment_schedule(30, '2026-08-13')
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]['應付編號'], 'AP1')
        self.assertAlmostEqual(s['total_twd'], 4000)


if __name__ == '__main__':
    unittest.main()
