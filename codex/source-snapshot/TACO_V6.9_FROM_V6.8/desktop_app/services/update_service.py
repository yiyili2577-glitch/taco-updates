import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import urllib.parse
from pathlib import Path

from services.app_paths import AppPaths
from services.build_config import BuildConfig
from services.license_client_service import LicenseClientService
from services.signature_utils import verify_signed_payload
from services.versioning import is_newer


class UpdateError(RuntimeError):
    pass


class UpdateService:
    MAX_MANIFEST_BYTES = 128 * 1024
    MAX_PACKAGE_BYTES = 2 * 1024 * 1024 * 1024
    @staticmethod
    def public_key_path():
        override = str(os.environ.get("TACO_UPDATE_PUBLIC_KEY", "")).strip()
        if override:
            return Path(override)
        return AppPaths.resource_dir() / "resources" / "update_public_key.pem"

    @staticmethod
    def fetch_manifest(url, timeout=8):
        url = str(url or "").strip()
        if not url:
            raise UpdateError("尚未設定更新 Manifest URL。")
        scheme = urllib.parse.urlparse(url).scheme.lower()
        if scheme not in {"https", "file"}:
            raise UpdateError("更新 Manifest 只允許 HTTPS；file:// 僅供離線測試。")
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            raw = resp.read(UpdateService.MAX_MANIFEST_BYTES + 1)
        if len(raw) > UpdateService.MAX_MANIFEST_BYTES:
            raise UpdateError("更新 Manifest 超過大小限制。")
        try: response = json.loads(raw.decode("utf-8"))
        except Exception as exc: raise UpdateError("更新 Manifest 格式無效。") from exc
        if not isinstance(response,dict) or set(response)!={"manifest","signature"}:
            raise UpdateError("更新伺服器回應欄位不符。")
        payload = response.get("manifest")
        signature = str(response.get("signature", ""))
        if not isinstance(payload, dict) or not signature:
            raise UpdateError("更新伺服器回應缺少 manifest 或 signature。")
        pub = UpdateService.public_key_path()
        if not pub.exists():
            raise UpdateError("缺少更新 Public Key。")
        try:
            verify_signed_payload(payload, signature, pub)
        except Exception as exc:
            raise UpdateError("更新 Manifest 數位簽章驗證失敗。") from exc
        if str(payload.get("app", "")) != BuildConfig.APP_ID:
            raise UpdateError("更新檔不屬於此 TACO 應用程式。")
        allowed={"app","channel","latest_version","min_version","published_on","notes","packages","schema_version"}
        if any(k not in allowed for k in payload): raise UpdateError("更新 Manifest 含有未知欄位。")
        if str(payload.get("channel","stable")) not in {"stable","beta","internal"}: raise UpdateError("更新通道無效。")
        latest=str(payload.get("latest_version","")).strip()
        if not latest or not all(x.isdigit() for x in latest.split('.')[:3]) or len(latest.split('.'))<3: raise UpdateError("更新版本格式無效。")
        packages=payload.get("packages")
        if not isinstance(packages,dict): raise UpdateError("更新 Manifest 缺少 packages。")
        for package in packages.values():
            if not isinstance(package,dict): raise UpdateError("更新套件資料無效。")
            package_url=str(package.get("url","")).strip(); digest=str(package.get("sha256","")).strip()
            if urllib.parse.urlparse(package_url).scheme.lower() not in {"https","file"}: raise UpdateError("更新套件只允許 HTTPS。")
            if len(digest)!=64 or any(ch not in '0123456789abcdefABCDEF' for ch in digest): raise UpdateError("更新套件 SHA-256 格式無效。")
            size=package.get("size")
            if size is not None and (not isinstance(size,int) or size<=0 or size>UpdateService.MAX_PACKAGE_BYTES): raise UpdateError("更新套件大小無效。")
        return payload

    @staticmethod
    def check(url):
        manifest = UpdateService.fetch_manifest(url)
        latest = str(manifest.get("latest_version", ""))
        available = bool(latest and is_newer(latest, BuildConfig.VERSION))
        receipt = LicenseClientService.current_receipt(allow_expired=True) or {}
        maintenance_until = str(receipt.get("maintenance_until", "")).strip()
        published_on = str(manifest.get("published_on", "")).strip()
        eligible = True
        reason = ""
        receipt_channel = str(receipt.get("update_channel", "stable") or "stable")
        manifest_channel = str(manifest.get("channel", "stable") or "stable")
        if receipt and receipt_channel == "stable" and manifest_channel != "stable":
            eligible = False
            reason = "目前授權只允許 stable 更新通道。"
        if eligible and maintenance_until and published_on and published_on > maintenance_until:
            eligible = False
            reason = f"此版本發布日 {published_on} 超過維護更新期限 {maintenance_until}。"
        min_version=str(manifest.get("min_version","") or "").strip()
        if eligible and min_version and is_newer(min_version,BuildConfig.VERSION):
            eligible=False; reason=f"目前版本需先升級至 {min_version}，請使用橋接安裝包。"
        target_schema=int(manifest.get("schema_version",BuildConfig.SCHEMA_VERSION) or BuildConfig.SCHEMA_VERSION)
        if eligible and target_schema<BuildConfig.SCHEMA_VERSION:
            eligible=False; reason="更新要求降低資料 Schema，已安全阻擋。"
        return {"available": available, "eligible": eligible, "reason": reason, "manifest": manifest}

    @staticmethod
    def download_package(package_info, timeout=60):
        url = str((package_info or {}).get("url", "")).strip()
        expected = str((package_info or {}).get("sha256", "")).strip().lower()
        if not url or not expected:
            raise UpdateError("更新套件缺少 URL 或 SHA-256。")
        if urllib.parse.urlparse(url).scheme.lower() not in {"https","file"}: raise UpdateError("更新套件只允許 HTTPS。")
        expected_size=(package_info or {}).get("size")
        if expected_size is not None and (not isinstance(expected_size,int) or expected_size<=0 or expected_size>UpdateService.MAX_PACKAGE_BYTES): raise UpdateError("更新套件大小無效。")
        name = str((package_info or {}).get("filename") or os.path.basename(url) or "taco_update.zip")
        target = AppPaths.update_dir() / name
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")
        h = hashlib.sha256()
        with urllib.request.urlopen(url, timeout=timeout) as resp, open(tmp, "wb") as f:
            header_size=resp.headers.get('Content-Length')
            if header_size and int(header_size)>UpdateService.MAX_PACKAGE_BYTES: raise UpdateError("更新套件超過大小限制。")
            received=0
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                received+=len(chunk)
                if received>UpdateService.MAX_PACKAGE_BYTES: raise UpdateError("更新套件超過大小限制。")
                f.write(chunk); h.update(chunk)
            f.flush(); os.fsync(f.fileno())
        if expected_size is not None and received!=expected_size:
            tmp.unlink(missing_ok=True); raise UpdateError("更新套件大小不符。")
        actual = h.hexdigest().lower()
        if actual != expected:
            tmp.unlink(missing_ok=True)
            raise UpdateError("更新套件 SHA-256 驗證失敗，已取消更新。")
        os.replace(tmp, target)
        return target

    @staticmethod
    def write_pending_update(manifest, package_path):
        pending = {
            "manifest": manifest,
            "package_path": str(package_path),
            "install_dir": str(AppPaths.install_dir()),
            "restart_exe": sys.executable if bool(getattr(sys, "frozen", False)) else "",
        }
        path = AppPaths.update_dir() / "pending_update.json"
        path.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def launch_updater(pending_path):
        from services import security
        from services.data_maintenance_service import DataMaintenanceService
        security.require_admin('套用程式更新')
        pending_path=Path(pending_path); pending=json.loads(pending_path.read_text(encoding='utf-8'))
        manifest=pending.get('manifest') or {}; packages=manifest.get('packages') or {}; package_info=packages.get('win-x64') or packages.get('windows') or {}
        package=Path(str(pending.get('package_path',''))); expected=str(package_info.get('sha256',''))
        if not package.is_file(): raise UpdateError('待更新套件不存在。')
        h=hashlib.sha256()
        with package.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
        if h.hexdigest().lower()!=expected.lower(): raise UpdateError('套用前 SHA-256 二次驗證失敗。')
        DataMaintenanceService.create_savepoint(note=f"UPDATE_PRE_{manifest.get('latest_version','')}",kind='update_pre')
        source=AppPaths.install_dir()/'TACOUpdater.exe'
        if not source.is_file(): raise UpdateError('找不到獨立 TACOUpdater.exe。')
        runner=AppPaths.update_dir()/f"TACOUpdater_{manifest.get('latest_version','next')}.exe"; shutil.copy2(source,runner)
        args=[str(runner),'--package',str(package),'--install-dir',str(AppPaths.install_dir()),'--backup-dir',str(AppPaths.backups_dir()),'--restart',str(pending.get('restart_exe','')),'--wait-pid',str(os.getpid()),'--sha256',expected]
        return subprocess.Popen(args,cwd=str(AppPaths.update_dir()))
