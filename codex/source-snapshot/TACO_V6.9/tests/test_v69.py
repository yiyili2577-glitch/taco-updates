import base64
import hashlib
import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from desktop_app.domain import (
    AllocationPolicy, BusinessRuleError, ReceiptBusinessRules, ScanError, ScanStage, ScanWorkflow,
)
from desktop_app.security import (
    AccessDenied, LicenseState, PermissionService, evaluate_license, license_mode, maintenance_allows_update,
)
from desktop_app.storage import IntegrationEventStore, SafeStorage, initialize_integration_db
from desktop_app.updater import (
    AtomicUpdater, UpdateError, UpdateManifest, build_manifest, canonical_manifest, safe_extract,
    update_is_allowed, verify_ed25519, verify_package,
)


def resolver(code):
    if code.startswith("PO-"):
        return "order", {"order_no": code}
    if code.startswith("SKU-"):
        return "item", {"sku": code, "product_group": "cold" if code.endswith("C") else "default"}
    if code.startswith("OVER-"):
        return "item", {"sku": code, "expected_quantity": 1, "quantity": 2}
    if code.startswith("BIN-"):
        return "location", {"location": code, "zone": "RECEIVING"}
    if code.startswith("BOX-"):
        return "container", {"container": code, "default_location": "A-01", "zone": "RECEIVING"}
    if code == "BADBOX":
        return "container", {"container": code}
    return "unknown", {}


class FakeInventory:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail
        self.receipts = {}

    def commit_receipt(self, **data):
        self.calls.append(data)
        if self.fail:
            raise RuntimeError("db down")
        key = data["idempotency_key"]
        self.receipts.setdefault(key, f"R-{len(self.receipts) + 1}")
        return self.receipts[key]


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.audit = []

    def flow(self, policy=None):
        return ScanWorkflow("u1", resolver, self.audit.append, policy)

    def ready(self, destination="BIN-X"):
        flow = self.flow()
        flow.scan("PO-1")
        flow.scan("SKU-A")
        flow.scan(destination)
        return flow

    def test_order_required_first(self):
        with self.assertRaises(ScanError):
            self.flow().scan("SKU-A")

    def test_empty_barcode_rejected(self):
        with self.assertRaises(ScanError):
            self.flow().scan("  ")

    def test_multi_item_and_repeat_quantity(self):
        flow = self.flow()
        for code in ("PO-1", "SKU-A", "SKU-B", "SKU-A", "BIN-X"):
            flow.scan(code)
        self.assertEqual(flow.session.stage, ScanStage.REVIEW)
        self.assertEqual(flow.session.items["SKU-A"].quantity, 2)
        self.assertEqual(flow.session.total_quantity, 3)
        self.assertEqual(len(flow.session.allocations), 2)

    def test_destination_requires_item(self):
        flow = self.flow()
        flow.scan("PO-1")
        with self.assertRaises(ScanError):
            flow.scan("BIN-X")

    def test_container_maps_default_location(self):
        flow = self.ready("BOX-1")
        self.assertEqual(flow.session.container, "BOX-1")
        self.assertEqual(flow.session.location, "A-01")

    def test_container_without_mapping_rejected(self):
        flow = self.flow()
        flow.scan("PO-1")
        flow.scan("SKU-A")
        with self.assertRaises(ScanError):
            flow.scan("BADBOX")

    def test_per_item_allocation_rule(self):
        policy = AllocationPolicy({"group:cold": {"location": "COLD-01", "zone": "COLD", "rule_id": "cold"}})
        flow = self.flow(policy)
        for code in ("PO-1", "SKU-A", "SKU-C", "BIN-X"):
            flow.scan(code)
        allocations = {a.sku: a for a in flow.session.allocations}
        self.assertEqual(allocations["SKU-C"].location, "COLD-01")
        self.assertEqual(allocations["SKU-A"].location, "BIN-X")

    def test_scan_does_not_mutate_inventory(self):
        inventory = FakeInventory()
        self.ready()
        self.assertEqual(inventory.calls, [])

    def test_commit_requires_permission(self):
        with self.assertRaises(AccessDenied):
            self.ready().commit(FakeInventory(), PermissionService({"u1": set()}))

    def test_readonly_blocks_commit(self):
        permission = PermissionService({"u1": {"inventory.receive"}}, readonly=True)
        with self.assertRaises(AccessDenied):
            self.ready().commit(FakeInventory(), permission)

    def test_business_rule_blocks_over_receipt(self):
        flow = self.flow()
        for code in ("PO-1", "OVER-A", "BIN-X"):
            flow.scan(code)
        with self.assertRaises(BusinessRuleError):
            flow.commit(FakeInventory(), PermissionService({"u1": {"inventory.receive"}}))

    def test_authorized_commit_is_idempotency_keyed(self):
        inventory = FakeInventory()
        flow = self.ready()
        receipt = flow.commit(inventory, PermissionService({"u1": {"inventory.receive"}}))
        self.assertEqual(receipt, "R-1")
        self.assertEqual(inventory.calls[0]["idempotency_key"], flow.session.session_id)
        self.assertEqual(flow.session.stage, ScanStage.COMMITTED)

    def test_committed_session_cannot_scan_or_cancel(self):
        flow = self.ready()
        flow.commit(FakeInventory(), PermissionService({"u1": {"inventory.receive"}}))
        with self.assertRaises(ScanError):
            flow.scan("SKU-B")
        with self.assertRaises(ScanError):
            flow.cancel("no")

    def test_cancel_and_new_session(self):
        flow = self.flow()
        old = flow.session.session_id
        flow.cancel("operator")
        self.assertEqual(flow.session.stage, ScanStage.CANCELLED)
        flow.new_session()
        self.assertNotEqual(old, flow.session.session_id)
        self.assertEqual(flow.session.stage, ScanStage.ORDER)

    def test_each_successful_scan_is_audited(self):
        flow = self.ready()
        self.assertEqual(len(self.audit), 3)
        self.assertTrue(all(event.session_id == flow.session.session_id for event in self.audit))


class SecurityTests(unittest.TestCase):
    def test_72h_grace(self):
        now = datetime.now(timezone.utc)
        decision = evaluate_license(LicenseState(now - timedelta(hours=71), now), now)
        self.assertEqual(decision.mode, "active")
        self.assertGreater(decision.offline_remaining, timedelta())

    def test_expired_grace_is_readonly(self):
        now = datetime.now(timezone.utc)
        self.assertEqual(license_mode(LicenseState(now - timedelta(hours=73), now), now), "readonly")

    def test_clock_rollback_is_readonly(self):
        now = datetime.now(timezone.utc)
        decision = evaluate_license(LicenseState(now, now + timedelta(hours=1)), now)
        self.assertEqual((decision.mode, decision.reason), ("readonly", "clock_rollback"))

    def test_revoked_and_expired_are_readonly(self):
        now = datetime.now(timezone.utc)
        self.assertEqual(evaluate_license(LicenseState(now, now, revoked=True), now).reason, "revoked")
        state = LicenseState(now, now, expires_on=now.date() - timedelta(days=1))
        self.assertEqual(evaluate_license(state, now).reason, "license_expired")

    def test_license_2_only(self):
        now = datetime.now(timezone.utc)
        state = LicenseState(now, now, license_version="1.0")
        self.assertEqual(evaluate_license(state, now).reason, "unsupported_license_version")

    def test_maintenance_right(self):
        now = datetime.now(timezone.utc)
        state = LicenseState(now, now, maintenance_until=date(2026, 8, 14))
        self.assertTrue(maintenance_allows_update(state, date(2026, 8, 14)))
        self.assertFalse(maintenance_allows_update(state, date(2026, 8, 15)))


class StorageTests(unittest.TestCase):
    def test_safe_storage_atomic_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = SafeStorage(Path(directory))
            storage.write_json("Data/x.json", {"中文": 1})
            self.assertEqual(storage.read_json("Data/x.json"), {"中文": 1})

    def test_safe_storage_blocks_escape_and_absolute(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = SafeStorage(Path(directory))
            with self.assertRaises(ValueError):
                storage.write_json("../x", {})
            with self.assertRaises(ValueError):
                storage.write_json(str(Path(directory).resolve() / "x"), {})

    def test_integration_db_preserves_mapping_and_wal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "integration.db"
            initialize_integration_db(path)
            with closing(sqlite3.connect(path)) as db:
                db.execute("INSERT INTO mapping_profiles VALUES('p','t','{}',1)")
                db.commit()
            initialize_integration_db(path)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute("SELECT count(*) FROM mapping_profiles").fetchone()[0], 1)
                self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")

    def test_event_store_commit_and_failure_states(self):
        with tempfile.TemporaryDirectory() as directory:
            store = IntegrationEventStore(Path(directory) / "integration.db")
            permission = PermissionService({"u1": {"inventory.receive"}})
            flow = ScanWorkflow("u1", resolver, store.record_scan)
            for code in ("PO-1", "SKU-A", "BIN-X"):
                flow.scan(code)
            session_id = flow.session.session_id
            flow.commit(FakeInventory(), permission, event_store=store)
            self.assertEqual(store.outbox_state(session_id), "committed")
            failed = ScanWorkflow("u1", resolver, store.record_scan)
            for code in ("PO-2", "SKU-B", "BIN-Y"):
                failed.scan(code)
            failed_id = failed.session.session_id
            with self.assertRaises(RuntimeError):
                failed.commit(FakeInventory(fail=True), permission, event_store=store)
            self.assertEqual(store.outbox_state(failed_id), "failed")


def manifest_bytes(**overrides):
    value = {
        "version": "6.9.1", "channel": "stable", "package_sha256": "a" * 64,
        "package_url": "https://updates.example/TACO.zip", "package_size": 12,
        "min_version": "6.9.0", "schema_version": 2, "published_at": "2026-08-14T00:00:00Z",
        "release_notes": "修正",
    }
    value.update(overrides)
    return canonical_manifest(value)


class UpdateTests(unittest.TestCase):
    def test_manifest_strict_and_https(self):
        self.assertEqual(UpdateManifest.parse(manifest_bytes()).version, "6.9.1")
        with self.assertRaises(UpdateError):
            UpdateManifest.parse(manifest_bytes(extra=True))
        with self.assertRaises(UpdateError):
            UpdateManifest.parse(manifest_bytes(package_url="http://bad"))

    def test_manifest_hash_size_semver_and_channel_validation(self):
        for kwargs in ({"package_sha256": "x"}, {"package_size": 0}, {"version": "v6.9"}, {"channel": "nightly"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(UpdateError):
                UpdateManifest.parse(manifest_bytes(**kwargs))

    def test_ed25519_signature(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

        private = Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
        raw = manifest_bytes()
        verify_ed25519(public, raw, base64.b64encode(private.sign(raw)).decode())
        with self.assertRaises(UpdateError):
            verify_ed25519(public, raw + b"x", base64.b64encode(private.sign(raw)).decode())

    def test_package_hash_and_size(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "package.zip"
            path.write_bytes(b"ok")
            verify_package(path, hashlib.sha256(b"ok").hexdigest(), 2)
            with self.assertRaises(UpdateError):
                verify_package(path, "0" * 64)
            with self.assertRaises(UpdateError):
                verify_package(path, hashlib.sha256(b"ok").hexdigest(), 3)

    def test_zip_slip_backslash_absolute_duplicate_and_symlink_blocked(self):
        bad_entries = ("../escape.txt", "..\\escape.txt", "/absolute.txt", "C:/drive.txt")
        for name in bad_entries:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                package = Path(directory) / "x.zip"
                with zipfile.ZipFile(package, "w") as archive:
                    archive.writestr(name, "bad")
                with self.assertRaises(UpdateError):
                    safe_extract(package, Path(directory) / "out")
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "x.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("A.txt", "1")
                archive.writestr("a.TXT", "2")
            with self.assertRaises(UpdateError):
                safe_extract(package, Path(directory) / "out")
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "x.zip"
            info = zipfile.ZipInfo("link")
            info.external_attr = (0o120777 << 16)
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr(info, "target")
            with self.assertRaises(UpdateError):
                safe_extract(package, Path(directory) / "out")

    def test_update_eligibility(self):
        now = datetime.now(timezone.utc)
        state = LicenseState(now, now, maintenance_until=date(2026, 12, 31), update_channel="stable")
        manifest = UpdateManifest.parse(manifest_bytes())
        self.assertEqual(update_is_allowed(manifest, "6.9.0", state, 2), (True, "allowed"))
        self.assertEqual(update_is_allowed(manifest, "6.9.1", state, 2)[1], "not_newer")
        beta = LicenseState(now, now, update_channel="beta")
        self.assertEqual(update_is_allowed(manifest, "6.9.0", beta, 2)[1], "channel_mismatch")
        expired = LicenseState(now, now, maintenance_until=date(2026, 1, 1), update_channel="stable")
        self.assertEqual(update_is_allowed(manifest, "6.9.0", expired, 2)[1], "maintenance_expired")

    def test_programdata_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            data.mkdir()
            with self.assertRaises(UpdateError):
                AtomicUpdater(data / "app", data)
            install = root / "app"
            install.mkdir()
            with self.assertRaises(UpdateError):
                AtomicUpdater(install, install / "data")

    def test_atomic_apply_success_and_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install, data, staging = root / "TACO", root / "ProgramData", root / "staging"
            install.mkdir(); data.mkdir(); (staging / "app").mkdir(parents=True)
            (install / "value.txt").write_text("old")
            (staging / "app" / "value.txt").write_text("new")
            (staging / "app" / "BUILD_VERSION.txt").write_text("6.9.1")
            updater = AtomicUpdater(install, data)
            updater.apply(staging, root / "backup", lambda path: (path / "value.txt").read_text() == "new")
            self.assertEqual((install / "value.txt").read_text(), "new")
            self.assertEqual((root / "backup" / "value.txt").read_text(), "old")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install, data, staging = root / "TACO", root / "ProgramData", root / "staging"
            install.mkdir(); data.mkdir(); (staging / "app").mkdir(parents=True)
            (install / "value.txt").write_text("old")
            (staging / "app" / "value.txt").write_text("bad")
            (staging / "app" / "BUILD_VERSION.txt").write_text("6.9.1")
            with self.assertRaises(UpdateError):
                AtomicUpdater(install, data).apply(staging, root / "backup", lambda _path: False)
            self.assertEqual((install / "value.txt").read_text(), "old")

    def test_stage_requires_version_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install, data = root / "TACO", root / "ProgramData"
            install.mkdir(); data.mkdir()
            package = root / "x.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("app/file.txt", "x")
            with self.assertRaises(UpdateError):
                AtomicUpdater(install, data).stage(package)

    def test_build_manifest_matches_package(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "x.zip"
            package.write_bytes(b"package")
            value = build_manifest(package, "6.9.1", "stable", "https://x/x.zip", "6.9.0", 2,
                                   "2026-08-14T00:00:00Z", "notes")
            self.assertEqual(value["package_size"], 7)
            self.assertEqual(value["package_sha256"], hashlib.sha256(b"package").hexdigest())


if __name__ == "__main__":
    unittest.main()
