import base64
import io
import json
import os
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from services.app_paths import AppPaths
from services.build_config import BuildConfig
from services.license_client_service import LicenseClientService
from services.signature_utils import canonical_json_bytes
from services.update_service import UpdateService


class V651RuntimeSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{'TACO_RUNTIME_ROOT':str(self.root/'runtime'),'TACO_BUILD_MODE':'prod'},clear=False); self.env.start()
        AppPaths.ensure_runtime_dirs()
        self.lic=Ed25519PrivateKey.generate(); self.lic_pub=self.root/'license_public_key.pem'; self.lic_pub.write_bytes(self.lic.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
        self.upd=Ed25519PrivateKey.generate(); self.upd_pub=self.root/'update_public_key.pem'; self.upd_pub.write_bytes(self.upd.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
        self.keyenv=patch.dict(os.environ,{'TACO_LICENSE_PUBLIC_KEY':str(self.lic_pub),'TACO_UPDATE_PUBLIC_KEY':str(self.upd_pub)},clear=False); self.keyenv.start()
    def tearDown(self):
        self.keyenv.stop(); self.env.stop(); self.tmp.cleanup()
    def test_production_paths_separate_program_data(self):
        self.assertEqual(AppPaths.data_dir(),self.root/'runtime'/'Data')
        self.assertEqual(AppPaths.audit_dir(),self.root/'runtime'/'AuditLogs')
        self.assertEqual(AppPaths.backups_dir(),self.root/'runtime'/'Backups')
    def test_production_settings_ignore_legacy_dev_advanced_without_signed_receipt(self):
        from services.system_settings_service import SystemSettingsService
        settings_file=self.root/'runtime'/'Data'/'system_settings.json'
        settings_file.parent.mkdir(parents=True,exist_ok=True)
        settings_file.write_text(json.dumps({'license':{'tier':'advanced','development_mode':True,'license_status':'development'}},ensure_ascii=False),encoding='utf-8')
        with patch.object(SystemSettingsService,'DATA_DIR',str(settings_file.parent)), patch.object(SystemSettingsService,'DATA_FILE',str(settings_file)), patch('services.license_client_service.LicenseClientService.current_receipt',return_value=None):
            out=SystemSettingsService.load()
        self.assertEqual(out['license']['tier'],'general')
        self.assertFalse(out['license']['development_mode'])
        self.assertEqual(out['license']['license_status'],'unverified')
    def test_signed_license_receipt_validates(self):
        now=datetime.now(timezone.utc)
        receipt={'app':BuildConfig.APP_ID,'license_id':'LIC-TEST','company':'測試','tier':'advanced','expires_at':'2099-12-31','maintenance_until':'2099-12-31','max_devices':2,'update_channel':'stable','device_id':LicenseClientService.device_id(),'issued_at':now.isoformat().replace('+00:00','Z'),'receipt_expires_at':(now+timedelta(days=7)).isoformat().replace('+00:00','Z')}
        sig=base64.b64encode(self.lic.sign(canonical_json_bytes(receipt))).decode('ascii')
        out=LicenseClientService.validate_response({'valid':True,'receipt':receipt,'signature':sig})
        self.assertEqual(out['tier'],'advanced')
    def test_tampered_license_receipt_is_rejected(self):
        now=datetime.now(timezone.utc); receipt={'app':BuildConfig.APP_ID,'license_id':'L','company':'X','tier':'general','expires_at':'2099-12-31','maintenance_until':'','max_devices':1,'update_channel':'stable','device_id':LicenseClientService.device_id(),'issued_at':now.isoformat().replace('+00:00','Z'),'receipt_expires_at':(now+timedelta(days=1)).isoformat().replace('+00:00','Z')}
        sig=base64.b64encode(self.lic.sign(canonical_json_bytes(receipt))).decode('ascii'); receipt['tier']='advanced'
        with self.assertRaises(ValueError): LicenseClientService.validate_response({'valid':True,'receipt':receipt,'signature':sig})
    def test_signed_update_manifest_validates(self):
        payload={'app':BuildConfig.APP_ID,'channel':'stable','latest_version':'6.6.0','published_on':'2026-08-13','packages':{'win-x64':{'url':'https://example.invalid/a.zip','sha256':'0'*64}}}
        sig=base64.b64encode(self.upd.sign(canonical_json_bytes(payload))).decode('ascii'); f=self.root/'update.json'; f.write_text(json.dumps({'manifest':payload,'signature':sig}),encoding='utf-8')
        out=UpdateService.fetch_manifest(f.as_uri()); self.assertEqual(out['latest_version'],'6.6.0')

    def _valid_license_response(self, tier="advanced"):
        now=datetime.now(timezone.utc)
        receipt={
            'app':BuildConfig.APP_ID,'license_id':'LIC-CACHED','company':'快取測試',
            'tier':tier,'expires_at':'2099-12-31','maintenance_until':'2099-12-31',
            'max_devices':2,'update_channel':'stable','device_id':LicenseClientService.device_id(),
            'issued_at':now.isoformat().replace('+00:00','Z'),
            'receipt_expires_at':(now+timedelta(days=7)).isoformat().replace('+00:00','Z')
        }
        sig=base64.b64encode(self.lic.sign(canonical_json_bytes(receipt))).decode('ascii')
        return {'valid':True,'receipt':receipt,'signature':sig}

    def test_authoritative_revocation_clears_cached_receipt_for_same_token(self):
        response=self._valid_license_response()
        LicenseClientService.save_signed_receipt(response)
        token='same-token'
        body=json.dumps({'valid':False,'code':'revoked','message':'這組授權碼已被停用。'}).encode('utf-8')
        err=urllib.error.HTTPError('http://127.0.0.1:5000/verify',403,'Forbidden',None,io.BytesIO(body))
        with patch.object(LicenseClientService,'load_token',return_value=token), \
             patch.object(LicenseClientService,'clear_token') as clear_token, \
             patch('urllib.request.urlopen',side_effect=err):
            with self.assertRaises(ValueError):
                LicenseClientService.verify_online(token,'http://127.0.0.1:5000/verify')
        self.assertIsNone(LicenseClientService.load_signed_receipt())
        clear_token.assert_called_once()

    def test_network_failure_preserves_offline_receipt(self):
        response=self._valid_license_response()
        LicenseClientService.save_signed_receipt(response)
        token='same-token'
        with patch.object(LicenseClientService,'load_token',return_value=token), \
             patch('urllib.request.urlopen',side_effect=urllib.error.URLError('offline')):
            with self.assertRaises(ValueError):
                LicenseClientService.verify_online(token,'http://127.0.0.1:5000/verify')
        self.assertIsNotNone(LicenseClientService.load_signed_receipt())
        self.assertEqual(LicenseClientService.current_receipt()['tier'],'advanced')

    def test_invalid_new_token_does_not_destroy_existing_valid_license(self):
        response=self._valid_license_response()
        LicenseClientService.save_signed_receipt(response)
        cached='current-good-token'; attempted='different-bad-token'
        body=json.dumps({'valid':False,'code':'not_found','message':'授權碼不存在或不正確。'}).encode('utf-8')
        err=urllib.error.HTTPError('http://127.0.0.1:5000/verify',403,'Forbidden',None,io.BytesIO(body))
        with patch.object(LicenseClientService,'load_token',return_value=cached), \
             patch.object(LicenseClientService,'clear_token') as clear_token, \
             patch('urllib.request.urlopen',side_effect=err):
            with self.assertRaises(ValueError):
                LicenseClientService.verify_online(attempted,'http://127.0.0.1:5000/verify')
        self.assertIsNotNone(LicenseClientService.load_signed_receipt())
        clear_token.assert_not_called()

    def test_authoritative_revocation_matches_cached_license_id_even_if_dpapi_unavailable(self):
        response=self._valid_license_response()
        response['receipt']['license_id']='LIC-CACHED'
        # re-sign after changing receipt id
        response['signature']=base64.b64encode(self.lic.sign(canonical_json_bytes(response['receipt']))).decode('ascii')
        LicenseClientService.save_signed_receipt(response, token='same-token')
        body=json.dumps({'valid':False,'code':'revoked','message':'這組授權碼已被停用。','license_id':'LIC-CACHED'}).encode('utf-8')
        err=urllib.error.HTTPError('http://127.0.0.1:5000/verify',403,'Forbidden',None,io.BytesIO(body))
        with patch.object(LicenseClientService,'load_token',return_value=''), \
             patch.object(LicenseClientService,'clear_token') as clear_token, \
             patch('urllib.request.urlopen',side_effect=err):
            with self.assertRaises(ValueError):
                LicenseClientService.verify_online('same-token','http://127.0.0.1:5000/verify')
        self.assertIsNone(LicenseClientService.load_signed_receipt())
        clear_token.assert_called_once()

    def test_revocation_matches_local_token_fingerprint_when_server_has_no_license_id(self):
        response=self._valid_license_response()
        LicenseClientService.save_signed_receipt(response, token='fingerprinted-token')
        body=json.dumps({'valid':False,'code':'revoked','message':'這組授權碼已被停用。'}).encode('utf-8')
        err=urllib.error.HTTPError('http://127.0.0.1:5000/verify',403,'Forbidden',None,io.BytesIO(body))
        with patch.object(LicenseClientService,'load_token',return_value=''), \
             patch.object(LicenseClientService,'clear_token') as clear_token, \
             patch('urllib.request.urlopen',side_effect=err):
            with self.assertRaises(ValueError):
                LicenseClientService.verify_online('fingerprinted-token','http://127.0.0.1:5000/verify')
        self.assertIsNone(LicenseClientService.load_signed_receipt())
        clear_token.assert_called_once()


    def test_local_credential_status_active(self):
        response=self._valid_license_response()
        LicenseClientService.save_signed_receipt(response)
        with patch.object(LicenseClientService,'load_token',return_value='saved-token'):
            info=LicenseClientService.local_credential_status()
        self.assertEqual(info['state'],'active')
        self.assertTrue(info['token_saved'])
        self.assertEqual(info['receipt']['license_id'],'LIC-CACHED')

    def test_local_credential_status_receipt_expired_but_signed_metadata_trusted(self):
        response=self._valid_license_response()
        response['receipt']['receipt_expires_at']=(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat().replace('+00:00','Z')
        response['signature']=base64.b64encode(self.lic.sign(canonical_json_bytes(response['receipt']))).decode('ascii')
        LicenseClientService.save_signed_receipt(response)
        with patch.object(LicenseClientService,'load_token',return_value='saved-token'):
            info=LicenseClientService.local_credential_status()
        self.assertEqual(info['state'],'receipt_expired')
        self.assertTrue(info['token_saved'])
        self.assertEqual(info['receipt']['company'],'快取測試')

    def test_local_credential_status_tampered_receipt_is_invalid(self):
        response=self._valid_license_response()
        LicenseClientService.save_signed_receipt(response)
        path=LicenseClientService._receipt_path()
        raw=json.loads(path.read_text(encoding='utf-8'))
        raw['receipt']['expires_at']='2099-01-01' if raw['receipt']['expires_at']!='2099-01-01' else '2098-01-01'
        path.write_text(json.dumps(raw,ensure_ascii=False),encoding='utf-8')
        with patch.object(LicenseClientService,'load_token',return_value='saved-token'):
            info=LicenseClientService.local_credential_status()
        self.assertEqual(info['state'],'invalid_receipt')
        self.assertIsNone(info['receipt'])

    def test_local_credential_status_saved_token_only_is_not_entitlement(self):
        LicenseClientService.clear_signed_receipt()
        with patch.object(LicenseClientService,'load_token',return_value='saved-token'):
            info=LicenseClientService.local_credential_status()
            self.assertEqual(LicenseClientService.entitlement_tier(),'general')
        self.assertEqual(info['state'],'saved_token_only')
        self.assertTrue(info['token_saved'])


    def test_local_credential_status_remembers_authoritative_revocation_for_ui(self):
        with patch.object(LicenseClientService,'load_token',return_value=''):
            LicenseClientService.invalidate_cached_license(code='revoked',message='這組授權碼已被停用。',clear_token=False)
            info=LicenseClientService.local_credential_status()
        self.assertEqual(info['state'],'revoked')
        self.assertEqual(info['denial_code'],'revoked')
        self.assertIn('停用',info['denial_message'])



if __name__=='__main__': unittest.main()

# V6.5.1 Offline 72h / clock rollback / readonly additions
class V651OfflineGraceSecurityTests(V651RuntimeSecurityTests):
    def test_clock_rollback_is_rejected(self):
        response=self._valid_license_response()
        fixed=datetime(2026,8,13,12,0,tzinfo=timezone.utc)
        guard={'max_seen_utc':(fixed+timedelta(hours=2)).isoformat().replace('+00:00','Z')}
        with patch.object(LicenseClientService,'_utc_now',return_value=fixed), \
             patch.object(LicenseClientService,'_load_clock_guard',return_value=guard), \
             patch.object(LicenseClientService,'_advance_clock_guard'):
            with self.assertRaises(ValueError) as ctx:
                LicenseClientService.validate_response(response)
        self.assertIn('時間異常倒退',str(ctx.exception))

    def test_expired_offline_receipt_enters_restricted_readonly(self):
        response=self._valid_license_response()
        response['receipt']['receipt_expires_at']=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat().replace('+00:00','Z')
        response['signature']=base64.b64encode(self.lic.sign(canonical_json_bytes(response['receipt']))).decode('ascii')
        LicenseClientService.save_signed_receipt(response)
        with patch.object(LicenseClientService,'_load_clock_guard',return_value={}), \
             patch.object(LicenseClientService,'load_token',return_value='saved'):
            self.assertEqual(LicenseClientService.local_credential_status()['state'],'receipt_expired')
            self.assertTrue(LicenseClientService.restricted_readonly_mode())
            self.assertEqual(LicenseClientService.access_mode(),'restricted_readonly')

    def test_security_blocks_writes_but_allows_backup_in_restricted_mode(self):
        from services import security
        with patch.object(LicenseClientService,'restricted_readonly_mode',return_value=True):
            with self.assertRaises(security.PermissionDeniedError):
                security.require_write_access('修改庫存')
            self.assertTrue(security.require_write_access('建立資料儲存點',allow_backup=True))
