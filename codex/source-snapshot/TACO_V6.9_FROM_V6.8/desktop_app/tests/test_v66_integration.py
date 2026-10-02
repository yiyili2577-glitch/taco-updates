import tempfile, unittest
from unittest.mock import patch
from services.integration_db_service import IntegrationDbService
from services.mapping_service import MappingService

class V66IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.p=patch('services.integration_db_service.AppPaths.data_dir', return_value=self.t.name); self.p.start()
        self.sec=patch('services.security.require_write_access', return_value=True); self.sec.start()
    def tearDown(self): self.sec.stop(); self.p.stop(); self.t.cleanup()
    def test_initialize_wal_and_integrity(self):
        h=IntegrationDbService.health(); self.assertTrue(h['ok']); self.assertEqual(h['journal_mode'].lower(),'wal')
    def test_barcode_roundtrip(self):
        IntegrationDbService.upsert_barcode('471001','P001','包',12); r=IntegrationDbService.barcode('471001'); self.assertEqual(r['product_no'],'P001'); self.assertEqual(r['qty_per_scan'],12)
    def test_mapping_profile(self):
        pid=IntegrationDbService.save_mapping_profile('A','Excel',{'貨號':'product_no','數':'quantity'}); p=IntegrationDbService.get_mapping_profile(pid); self.assertEqual(p['mappings']['貨號'],'product_no'); self.assertEqual(MappingService.standardize_row({'貨號':'X','數':3},p['mappings']),{'product_no':'X','quantity':3})
    def test_mapping_duplicate_target(self): self.assertTrue(MappingService.validate_mapping({'A':'product_no','B':'product_no'}))
    def test_queue_idempotency(self):
        IntegrationDbService.enqueue('x','1','upsert',{'a':1},'idem-1'); IntegrationDbService.enqueue('x','1','upsert',{'a':2},'idem-1'); self.assertEqual(len(IntegrationDbService.list_queue()),1)
    def test_scan_idempotency(self):
        IntegrationDbService.record_scan(barcode='x',action='查詢',idempotency_key='s1'); IntegrationDbService.record_scan(barcode='x',action='查詢',idempotency_key='s1'); self.assertEqual(len(IntegrationDbService.list_scans()),1)
if __name__=='__main__': unittest.main()
