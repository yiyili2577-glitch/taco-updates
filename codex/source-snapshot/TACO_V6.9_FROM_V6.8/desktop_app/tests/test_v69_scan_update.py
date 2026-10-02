import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import updater
from services.integration_db_service import IntegrationDbService
from services.scan_receipt_service import ScanReceiptError,ScanReceiptService,ScanReceiptSession


def product(code,name='',group=''):
    return {'barcode':code,'product_no':code,'product_name':name or code,'binding':{'qty_per_scan':1},'product':{'產品分類':group},'found':True}


class V69ScanReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.inventory={}; self.saved=[]
        self.patches=[
            patch('services.integration_db_service.AppPaths.data_dir',return_value=self.tmp.name),
            patch('services.security.require_write_access',return_value=True),
            patch('services.security.require_tier',return_value=True),
            patch('services.audit_log_service.AuditLogService.log_event',return_value=True),
            patch('services.scan_receipt_service.AuditLogService.log_event',return_value=True),
            patch('services.scan_receipt_service.WarehouseService.load_names',return_value=['倉庫1','倉庫2','倉庫3']),
            patch('services.scan_receipt_service.WarehouseService.load_inventory',side_effect=lambda:self.inventory.copy()),
            patch('services.scan_receipt_service.WarehouseService.save_inventory',side_effect=self._save),
        ]
        for item in self.patches:item.start()
    def tearDown(self):
        for item in reversed(self.patches):item.stop()
        self.tmp.cleanup()
    def _save(self,value): self.inventory=value; self.saved.append(value)
    def _resolver(self,code): return product(code,'A') if code.startswith('SKU-') else {'found':False}
    def _ready(self):
        service=ScanReceiptService()
        with patch('services.scan_receipt_service.ScannerService.resolve',side_effect=self._resolver):
            service.scan('PO:1001','倉庫1'); service.scan('SKU-A','倉庫1'); service.scan('SKU-B','倉庫1'); service.scan('SKU-A','倉庫1'); service.scan('BOX-01','倉庫1')
        return service
    def test_required_order_then_multi_item_destination(self):
        service=self._ready(); self.assertEqual(service.session.order_no,'1001'); self.assertEqual(service.session.stage,ScanReceiptSession.REVIEW); self.assertEqual(service.session.items['SKU-A']['quantity'],2); self.assertEqual(len(service.session.allocations),2)
    def test_scan_never_writes_inventory(self):
        self._ready(); self.assertEqual(self.saved,[]); self.assertEqual(self.inventory,{})
    def test_commit_writes_once_after_security_and_business_rules(self):
        service=self._ready(); receipt=service.commit(); self.assertTrue(receipt.startswith('RCV-')); self.assertEqual(len(self.saved),1); self.assertEqual(self.inventory['SKU-A']['0'],2); self.assertEqual(IntegrationDbService.list_receipts()[0]['status'],'committed')
    def test_item_rule_can_route_to_another_warehouse(self):
        IntegrationDbService.upsert_storage_rule(product_no='SKU-B',warehouse='倉庫2',location='B-01',zone='冷藏',priority=1)
        service=self._ready(); allocations={x['product_no']:x for x in service.session.allocations}; self.assertEqual(allocations['SKU-A']['warehouse'],'倉庫1'); self.assertEqual(allocations['SKU-B']['warehouse'],'倉庫2'); self.assertEqual(allocations['SKU-B']['location'],'B-01')
    def test_destination_before_item_and_unknown_code_rejected(self):
        service=ScanReceiptService(); service.scan('PO-1','倉庫1')
        with patch('services.scan_receipt_service.ScannerService.resolve',return_value={'found':False}):
            with self.assertRaises(ScanReceiptError): service.scan('BOX-01','倉庫1')
            with self.assertRaises(ScanReceiptError): service.scan('UNKNOWN','倉庫1')
    def test_failed_inventory_marks_receipt_failed(self):
        service=self._ready()
        with patch('services.scan_receipt_service.WarehouseService.save_inventory',side_effect=OSError('disk')):
            with self.assertRaises(OSError): service.commit()
        self.assertEqual(IntegrationDbService.list_receipts()[0]['status'],'failed')


class V69UpdaterTests(unittest.TestCase):
    def test_zip_slip_backslash_duplicate_and_symlink_are_blocked(self):
        entries=['../x','..\\x','C:/x','/x']
        for name in entries:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as td:
                package=Path(td)/'x.zip'
                with zipfile.ZipFile(package,'w') as archive: archive.writestr(name,'x')
                with self.assertRaises(RuntimeError): updater.safe_extract(package,Path(td)/'out')
        with tempfile.TemporaryDirectory() as td:
            package=Path(td)/'x.zip'
            with zipfile.ZipFile(package,'w') as archive: archive.writestr('A.txt','1'); archive.writestr('a.TXT','2')
            with self.assertRaises(RuntimeError): updater.safe_extract(package,Path(td)/'out')
    def test_hash_verification(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'x'; path.write_bytes(b'ok'); updater.verify_sha256(path,hashlib.sha256(b'ok').hexdigest())
            with self.assertRaises(RuntimeError): updater.verify_sha256(path,'0'*64)
    def _package(self,root,value='new'):
        package=root/'update.zip'
        with zipfile.ZipFile(package,'w') as archive:
            archive.writestr('app/TACO.exe',value); archive.writestr('app/TACOUpdater.exe','updater'); archive.writestr('app/BUILD_VERSION.txt','6.9.1')
        return package
    def test_apply_success_and_health_rollback(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); install=root/'ProgramFiles'/'TACO'; data=root/'ProgramData'/'TACO'/'Backups'; install.mkdir(parents=True); data.mkdir(parents=True); (install/'TACO.exe').write_text('old'); package=self._package(root)
            updater.apply_update(package,install,data); self.assertEqual((install/'TACO.exe').read_text(),'new'); self.assertTrue(list(data.glob('APP_UPDATE_PRE_*.zip')))
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); install=root/'ProgramFiles'/'TACO'; data=root/'ProgramData'/'TACO'/'Backups'; install.mkdir(parents=True); data.mkdir(parents=True); (install/'TACO.exe').write_text('old'); package=root/'bad.zip'
            with zipfile.ZipFile(package,'w') as archive: archive.writestr('app/BUILD_VERSION.txt','6.9.1')
            with self.assertRaises(RuntimeError): updater.apply_update(package,install,data)
            self.assertEqual((install/'TACO.exe').read_text(),'old')
    def test_programdata_boundary(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); install=root/'ProgramData'/'TACO'; backup=install/'Backups'; install.mkdir(parents=True); backup.mkdir(); (install/'TACO.exe').write_text('old'); package=self._package(root)
            with self.assertRaises(RuntimeError): updater.apply_update(package,install,backup)


if __name__=='__main__': unittest.main()
