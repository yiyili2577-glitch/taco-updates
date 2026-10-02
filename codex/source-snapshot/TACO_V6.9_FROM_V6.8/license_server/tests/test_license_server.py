import os
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import license_store


class LicenseStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.db=str(Path(self.tmp.name)/'licenses.db')
        key=Ed25519PrivateKey.generate(); priv=Path(self.tmp.name)/'license_private_key.pem'
        priv.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        self.old=os.environ.get('LICENSE_PRIVATE_KEY_PATH'); os.environ['LICENSE_PRIVATE_KEY_PATH']=str(priv)
    def tearDown(self):
        if self.old is None: os.environ.pop('LICENSE_PRIVATE_KEY_PATH',None)
        else: os.environ['LICENSE_PRIVATE_KEY_PATH']=self.old
        self.tmp.cleanup()
    def test_issue_verify_signed_receipt(self):
        token=license_store.issue_license(self.db,'測試公司','advanced','2099-12-31',maintenance_until='2099-12-31',max_devices=2)
        r=license_store.verify_token(self.db,token,license_store.APP_ID,'6.5.1','device-a','PC-A')
        self.assertTrue(r['valid']); self.assertEqual(r['receipt']['tier'],'advanced'); self.assertTrue(r['signature'])
    def test_wrong_app_fails(self):
        token=license_store.issue_license(self.db,'測試','general')
        r=license_store.verify_token(self.db,token,'other','6.5.1','d1')
        self.assertFalse(r['valid']); self.assertEqual(r['code'],'wrong_app')
    def test_device_limit(self):
        token=license_store.issue_license(self.db,'測試','advanced',max_devices=1)
        self.assertTrue(license_store.verify_token(self.db,token,license_store.APP_ID,'6.5.1','d1')['valid'])
        r=license_store.verify_token(self.db,token,license_store.APP_ID,'6.5.1','d2')
        self.assertFalse(r['valid']); self.assertEqual(r['code'],'device_limit')
    def test_bad_expiry_fails_closed(self):
        token=license_store.issue_license(self.db,'測試','advanced')
        import sqlite3
        with closing(sqlite3.connect(self.db)) as c:
            c.execute("UPDATE licenses SET expires_at='2099-99-99'"); c.commit()
        r=license_store.verify_token(self.db,token,license_store.APP_ID,'6.5.1','d1')
        self.assertFalse(r['valid']); self.assertEqual(r['code'],'bad_expiry')
    def test_revoke_device(self):
        token=license_store.issue_license(self.db,'測試','advanced',max_devices=2)
        r=license_store.verify_token(self.db,token,license_store.APP_ID,'6.5.1','d1'); lid=r['receipt']['license_id']
        self.assertTrue(license_store.revoke_device(self.db,lid,'d1'))
        r=license_store.verify_token(self.db,token,license_store.APP_ID,'6.5.1','d1')
        self.assertFalse(r['valid']); self.assertEqual(r['code'],'device_revoked')

    def test_revoked_license_denial_includes_license_id(self):
        token=license_store.issue_license(self.db,'撤銷測試','advanced',max_devices=1)
        first=license_store.verify_token(self.db,token,license_store.APP_ID,'6.5.1','d1')
        lid=first['receipt']['license_id']
        self.assertTrue(license_store.revoke_license(self.db,token))
        r=license_store.verify_token(self.db,token,license_store.APP_ID,'6.5.1','d1')
        self.assertFalse(r['valid']); self.assertEqual(r['code'],'revoked'); self.assertEqual(r.get('license_id'),lid)


if __name__=='__main__': unittest.main()

class OfflineGraceTests(LicenseStoreTests):
    def test_default_offline_grace_is_72_hours(self):
        token=license_store.issue_license(self.db,'72小時','advanced','2099-12-31')
        r=license_store.verify_token(self.db,token,license_store.APP_ID,'6.5.1','d72')
        self.assertTrue(r['valid'])
        self.assertEqual(r['receipt']['offline_grace_hours'],72)
        self.assertIn('server_time',r['receipt'])

    def test_per_license_offline_grace_override(self):
        token=license_store.issue_license(self.db,'24小時','advanced','2099-12-31',offline_grace_hours=24)
        r=license_store.verify_token(self.db,token,license_store.APP_ID,'6.5.1','d24')
        self.assertTrue(r['valid'])
        self.assertEqual(r['receipt']['offline_grace_hours'],24)
        from datetime import datetime, timezone
        issued=datetime.fromisoformat(r['receipt']['issued_at'].replace('Z','+00:00'))
        until=datetime.fromisoformat(r['receipt']['receipt_expires_at'].replace('Z','+00:00'))
        self.assertAlmostEqual((until-issued).total_seconds(),24*3600,delta=5)
