from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import ssl
import stat
import tempfile
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Callable

from .security import LicenseState, maintenance_allows_update


MAX_MANIFEST_BYTES = 128 * 1024
MAX_PACKAGE_BYTES = 2 * 1024 * 1024 * 1024
MAX_EXTRACTED_BYTES = 4 * 1024 * 1024 * 1024
MAX_ZIP_ENTRIES = 20_000
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?$")


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpdateManifest:
    version: str
    channel: str
    package_sha256: str
    package_url: str
    package_size: int
    min_version: str
    schema_version: int
    published_at: str
    release_notes: str

    @classmethod
    def parse(cls, raw: bytes) -> "UpdateManifest":
        if len(raw) > MAX_MANIFEST_BYTES:
            raise UpdateError("manifest 超過大小限制")
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UpdateError("manifest 格式無效") from exc
        allowed = {
            "version", "channel", "package_sha256", "package_url", "package_size",
            "min_version", "schema_version", "published_at", "release_notes",
        }
        if not isinstance(value, dict) or set(value) != allowed:
            raise UpdateError("manifest 欄位不符")
        if value["channel"] not in {"stable", "beta", "internal"}:
            raise UpdateError("未知更新通道")
        _version(value["version"])
        _version(value["min_version"])
        if not re.fullmatch(r"[0-9a-fA-F]{64}", str(value["package_sha256"])):
            raise UpdateError("package_sha256 格式無效")
        if not isinstance(value["package_size"], int) or not 0 < value["package_size"] <= MAX_PACKAGE_BYTES:
            raise UpdateError("package_size 超出限制")
        if not isinstance(value["schema_version"], int) or value["schema_version"] < 1:
            raise UpdateError("schema_version 無效")
        if not str(value["package_url"]).lower().startswith("https://"):
            raise UpdateError("更新包只允許 HTTPS")
        try:
            datetime.fromisoformat(str(value["published_at"]).replace("Z", "+00:00"))
        except ValueError as exc:
            raise UpdateError("published_at 無效") from exc
        if len(str(value["release_notes"])) > 20_000:
            raise UpdateError("release notes 過長")
        return cls(**value)


def canonical_manifest(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def verify_ed25519(public_key_pem: bytes, message: bytes, signature_b64: str) -> None:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        key = load_pem_public_key(public_key_pem)
        if not isinstance(key, Ed25519PublicKey):
            raise TypeError("not Ed25519")
        key.verify(base64.b64decode(signature_b64, validate=True), message)
    except Exception as exc:
        raise UpdateError("更新簽章驗證失敗") from exc


def verify_package(path: Path, expected_sha256: str, expected_size: int | None = None) -> None:
    if expected_size is not None and path.stat().st_size != expected_size:
        raise UpdateError("更新包大小不符")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if not _constant_hex_equal(digest.hexdigest(), expected_sha256):
        raise UpdateError("更新包 SHA-256 不符")


def _constant_hex_equal(left: str, right: str) -> bool:
    import hmac
    return hmac.compare_digest(left.lower(), right.lower())


def safe_extract(package: Path, destination: Path) -> None:
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    total = 0
    with zipfile.ZipFile(package) as archive:
        members = archive.infolist()
        if len(members) > MAX_ZIP_ENTRIES:
            raise UpdateError("更新包檔案數量超過限制")
        for member in members:
            normalized = member.filename.replace("\\", "/")
            posix = PurePosixPath(normalized)
            if posix.is_absolute() or ".." in posix.parts or re.match(r"^[A-Za-z]:", normalized):
                raise UpdateError("更新包含不安全路徑")
            key = normalized.casefold().rstrip("/")
            if key in seen:
                raise UpdateError("更新包含重複路徑")
            seen.add(key)
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise UpdateError("更新包不可包含符號連結")
            total += member.file_size
            if total > MAX_EXTRACTED_BYTES:
                raise UpdateError("更新包解壓大小超過限制")
            target = (destination / Path(*posix.parts)).resolve()
            if destination != target and destination not in target.parents:
                raise UpdateError("更新包含不安全路徑")
        archive.extractall(destination)


def update_is_allowed(manifest: UpdateManifest, current_version: str, license_state: LicenseState, schema_version: int) -> tuple[bool, str]:
    if license_state.update_channel != manifest.channel:
        return False, "channel_mismatch"
    if _version(manifest.version) <= _version(current_version):
        return False, "not_newer"
    if _version(current_version) < _version(manifest.min_version):
        return False, "manual_bridge_required"
    published = datetime.fromisoformat(manifest.published_at.replace("Z", "+00:00")).date()
    if not maintenance_allows_update(license_state, published):
        return False, "maintenance_expired"
    if manifest.schema_version < schema_version:
        return False, "schema_downgrade_blocked"
    return True, "allowed"


def _version(value: str) -> tuple[int, int, int, tuple]:
    match = SEMVER.fullmatch(str(value))
    if not match:
        raise UpdateError(f"版本格式無效：{value}")
    major, minor, patch, prerelease = match.groups()
    # Stable sorts after pre-release with the same numeric version.
    tail = (1,) if prerelease is None else (0, prerelease)
    return int(major), int(minor), int(patch), tail


def download_https(url: str, destination: Path, max_bytes: int, timeout: float = 30.0) -> Path:
    if not url.lower().startswith("https://"):
        raise UpdateError("下載只允許 HTTPS")
    request = urllib.request.Request(url, headers={"User-Agent": "TACO-Updater/6.9"})
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response, destination.open("wb") as output:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                raise UpdateError("下載內容超過限制")
            received = 0
            while chunk := response.read(1024 * 1024):
                received += len(chunk)
                if received > max_bytes:
                    raise UpdateError("下載內容超過限制")
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
    except UpdateError:
        destination.unlink(missing_ok=True)
        raise
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise UpdateError("安全下載失敗") from exc
    return destination


class UpdateClient:
    def __init__(self, public_key_pem: bytes, downloader: Callable = download_https):
        self.public_key_pem = public_key_pem
        self.downloader = downloader

    def fetch_manifest(self, manifest_url: str, signature_url: str, work_dir: Path) -> tuple[UpdateManifest, bytes]:
        work_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = self.downloader(manifest_url, work_dir / "manifest.json", MAX_MANIFEST_BYTES)
        signature_path = self.downloader(signature_url, work_dir / "manifest.sig", 4096)
        raw = manifest_path.read_bytes()
        verify_ed25519(self.public_key_pem, raw, signature_path.read_text(encoding="ascii").strip())
        return UpdateManifest.parse(raw), raw

    def download_package(self, manifest: UpdateManifest, work_dir: Path) -> Path:
        package = self.downloader(manifest.package_url, work_dir / "update.zip", manifest.package_size)
        verify_package(package, manifest.package_sha256, manifest.package_size)
        return package


class AtomicUpdater:
    """Offline updater: stage, backup, swap Program Files payload, health-check, rollback."""

    def __init__(self, install_dir: Path, program_data: Path):
        self.install_dir = install_dir.resolve()
        self.program_data = program_data.resolve()
        if self.install_dir == self.program_data or self.program_data in self.install_dir.parents:
            raise UpdateError("安裝目錄不可位於 ProgramData")
        if self.install_dir in self.program_data.parents:
            raise UpdateError("ProgramData 不可位於安裝目錄")

    def stage(self, package: Path) -> Path:
        staging = Path(tempfile.mkdtemp(prefix="taco-update-"))
        safe_extract(package, staging)
        payload = staging / "app"
        if not payload.is_dir() or not (payload / "BUILD_VERSION.txt").is_file():
            shutil.rmtree(staging, ignore_errors=True)
            raise UpdateError("更新包缺少 app/BUILD_VERSION.txt")
        return staging

    def backup(self, backup_dir: Path) -> Path:
        target = backup_dir.resolve()
        if target.exists():
            raise UpdateError("備份目錄已存在")
        shutil.copytree(self.install_dir, target)
        return target

    def apply(self, staging: Path, backup_dir: Path, health_check: Callable[[Path], bool]) -> None:
        payload = (staging / "app").resolve()
        if not payload.is_dir():
            raise UpdateError("staging payload 不存在")
        parent = self.install_dir.parent
        candidate = parent / f".{self.install_dir.name}.candidate-{uuid.uuid4().hex}"
        retired = parent / f".{self.install_dir.name}.retired-{uuid.uuid4().hex}"
        self.backup(backup_dir)
        shutil.copytree(payload, candidate)
        try:
            os.replace(self.install_dir, retired)
            os.replace(candidate, self.install_dir)
            if not health_check(self.install_dir):
                raise UpdateError("更新後健康檢查失敗")
        except Exception:
            if self.install_dir.exists() and retired.exists():
                failed = parent / f".{self.install_dir.name}.failed-{uuid.uuid4().hex}"
                os.replace(self.install_dir, failed)
                os.replace(retired, self.install_dir)
                shutil.rmtree(failed, ignore_errors=True)
            elif retired.exists():
                os.replace(retired, self.install_dir)
            shutil.rmtree(candidate, ignore_errors=True)
            raise
        else:
            shutil.rmtree(retired, ignore_errors=True)


def build_manifest(package: Path, version: str, channel: str, package_url: str, min_version: str,
                   schema_version: int, published_at: str, release_notes: str) -> dict:
    _version(version)
    _version(min_version)
    return {
        "channel": channel,
        "min_version": min_version,
        "package_sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
        "package_size": package.stat().st_size,
        "package_url": package_url,
        "published_at": published_at,
        "release_notes": release_notes,
        "schema_version": schema_version,
        "version": version,
    }
