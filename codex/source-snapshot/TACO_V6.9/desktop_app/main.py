import os
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from .domain import AllocationPolicy, ReceiptBusinessRules, ScanWorkflow
from .security import PermissionService
from .storage import IntegrationEventStore
from .ui import ScannerCenter, UpdateCenter, configure_theme


def demo_resolver(code):
    if code.startswith("PO-"):
        return "order", {"order_no": code}
    if code.startswith("SKU-"):
        group = "cold" if code.endswith("COLD") else "default"
        return "item", {"sku": code, "product_group": group, "expected_quantity": 999}
    if code.startswith("BIN-"):
        return "location", {"location": code, "zone": "RECEIVING"}
    if code.startswith("BOX-"):
        return "container", {"container": code, "default_location": "STAGING-A", "zone": "RECEIVING"}
    return "unknown", {}


class DemoInventoryService:
    """Demonstration-only idempotent boundary; replace with the V6.8 inventory service."""

    def __init__(self):
        self.receipts = {}

    def commit_receipt(self, idempotency_key, **data):
        if idempotency_key not in self.receipts:
            self.receipts[idempotency_key] = f"DEMO-{len(self.receipts) + 1:04d}"
        return self.receipts[idempotency_key]


def main():
    root = tk.Tk()
    root.title("TACO V6.9｜安全更新與智慧掃碼")
    root.geometry("1360x900")
    root.minsize(1120, 760)
    configure_theme(root)
    data_root = Path(os.environ.get("PROGRAMDATA", str(Path.home()))) / "TACO"
    event_store = IntegrationEventStore(data_root / "integration.db")
    policy = AllocationPolicy({"group:cold": {"location": "COLD-01", "zone": "COLD", "rule_id": "cold-chain"}})
    workflow = ScanWorkflow("demo-user", demo_resolver, event_store.record_scan, policy)
    tabs = ttk.Notebook(root)
    tabs.pack(fill="both", expand=True)
    scanner = ScannerCenter(
        tabs,
        workflow,
        DemoInventoryService(),
        PermissionService({"demo-user": {"inventory.receive"}}),
        ReceiptBusinessRules(),
        event_store,
    )
    tabs.add(scanner, text="智慧掃碼中心")
    tabs.add(UpdateCenter(tabs), text="版本更新")
    root.mainloop()


if __name__ == "__main__":
    main()
