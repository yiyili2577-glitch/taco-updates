from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .domain import ScanStage


STAGE_LABEL = {
    ScanStage.ORDER: "1／4　等待單號",
    ScanStage.ITEMS: "2／4　連續掃描品項，完成後掃容器／儲位",
    ScanStage.REVIEW: "3／4　分配完成，等待安全覆核",
    ScanStage.COMMITTED: "4／4　已安全入庫",
    ScanStage.CANCELLED: "批次已取消",
}


class ScannerCenter(ttk.Frame):
    def __init__(self, master, workflow, inventory_service=None, permission_service=None,
                 business_rules=None, event_store=None):
        super().__init__(master, padding=20)
        self.workflow = workflow
        self.inventory_service = inventory_service
        self.permission_service = permission_service
        self.business_rules = business_rules
        self.event_store = event_store
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)

        ttk.Label(self, text="智慧掃碼中心", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            self,
            text="掃單號 → 連續掃多個貨品條碼 → 掃容器／儲位 → 權限、規則、稽核與事件層覆核入庫",
            style="Hint.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(3, 14))

        steps = ttk.Frame(self)
        steps.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        for index, label in enumerate(("1  單號", "2  多品項", "3  容器／儲位", "4  安全覆核")):
            steps.columnconfigure(index, weight=1)
            ttk.Label(steps, text=label, style="Step.TLabel", anchor="center", padding=(14, 10)).grid(
                row=0, column=index, sticky="ew", padx=(0 if index == 0 else 5, 0)
            )

        barcode = ttk.LabelFrame(self, text="大型條碼輸入區（掃碼焦點固定）", padding=20)
        barcode.grid(row=3, column=0, sticky="ew")
        barcode.columnconfigure(0, weight=1)
        self.entry = ttk.Entry(barcode, font=("Microsoft JhengHei UI", 30, "bold"), justify="center")
        self.entry.grid(row=0, column=0, sticky="ew", ipady=24)
        self.entry.bind("<Return>", self._scan)
        self.status = ttk.Label(barcode, text=STAGE_LABEL[self.workflow.session.stage], style="Status.TLabel")
        self.status.grid(row=1, column=0, sticky="w", pady=(15, 0))
        self.summary = ttk.Label(barcode, text="品項 0 種｜總數量 0｜尚未指定目的地", style="Hint.TLabel")
        self.summary.grid(row=2, column=0, sticky="w", pady=(4, 0))

        table_area = ttk.Frame(self)
        table_area.grid(row=4, column=0, sticky="nsew", pady=14)
        table_area.columnconfigure(0, weight=1)
        table_area.rowconfigure(0, weight=1)
        columns = ("sku", "qty", "container", "location", "zone", "rule")
        self.table = ttk.Treeview(table_area, columns=columns, show="headings", height=14)
        specs = (
            ("sku", "品項", 230), ("qty", "數量", 90), ("container", "容器", 150),
            ("location", "儲位", 180), ("zone", "區域", 140), ("rule", "分配規則", 180),
        )
        for key, title, width in specs:
            self.table.heading(key, text=title)
            self.table.column(key, width=width, minwidth=80, anchor="center")
        scrollbar = ttk.Scrollbar(table_area, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        actions = ttk.Frame(self)
        actions.grid(row=5, column=0, sticky="ew")
        ttk.Button(actions, text="取消本批", command=self._cancel).pack(side="left")
        ttk.Button(actions, text="建立下一批", command=self._new_batch).pack(side="left", padx=8)
        self.commit_button = ttk.Button(
            actions, text="權限與規則檢查後確認入庫", style="Primary.TButton", command=self._commit
        )
        self.commit_button.pack(side="right")
        self.after_idle(self.entry.focus_set)

    def _scan(self, _event=None):
        code = self.entry.get().strip()
        self.entry.delete(0, "end")
        try:
            self.workflow.scan(code)
            self.status.configure(text=STAGE_LABEL[self.workflow.session.stage], style="Status.TLabel")
        except Exception as exc:
            self.status.configure(text=str(exc), style="Error.TLabel")
            self.bell()
        self._refresh()
        self.entry.focus_set()

    def _refresh(self):
        self.table.delete(*self.table.get_children())
        session = self.workflow.session
        allocation_by_sku = {item.sku: item for item in session.allocations}
        for item in session.items.values():
            allocation = allocation_by_sku.get(item.sku)
            values = (
                item.sku, item.quantity, allocation.container if allocation else "—",
                allocation.location if allocation else "—", allocation.zone if allocation else "—",
                allocation.rule_id if allocation else "等待目的地",
            )
            self.table.insert("", "end", values=values)
        destination = session.destination.code if session.destination else "尚未指定目的地"
        self.summary.configure(text=f"品項 {len(session.items)} 種｜總數量 {session.total_quantity}｜{destination}")
        self.commit_button.configure(state="normal" if session.stage == ScanStage.REVIEW else "disabled")

    def _commit(self):
        if not self.inventory_service or not self.permission_service:
            messagebox.showwarning("安全覆核", "尚未連接正式 InventoryService；不會修改庫存。")
            return
        try:
            receipt = self.workflow.commit(
                self.inventory_service, self.permission_service, self.business_rules, self.event_store
            )
            self.status.configure(text=f"4／4　安全入庫完成：{receipt}", style="Status.TLabel")
            self._refresh()
        except Exception as exc:
            self.status.configure(text=f"入庫失敗：{exc}", style="Error.TLabel")
            messagebox.showerror("入庫失敗", str(exc))
        self.entry.focus_set()

    def _cancel(self):
        try:
            self.workflow.cancel("使用者取消")
            self.status.configure(text=STAGE_LABEL[ScanStage.CANCELLED])
        except Exception as exc:
            messagebox.showerror("無法取消", str(exc))
        self._refresh()

    def _new_batch(self):
        self.workflow.new_session()
        self.status.configure(text=STAGE_LABEL[ScanStage.ORDER], style="Status.TLabel")
        self._refresh()
        self.entry.focus_set()


class UpdateCenter(ttk.Frame):
    def __init__(self, master, current_version="6.9.0"):
        super().__init__(master, padding=24)
        ttk.Label(self, text="安全自動更新中心", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self, text="簽章驗證、維護權限、備份、替換、健康檢查與失敗回復", style="Hint.TLabel").pack(
            anchor="w", pady=(3, 20)
        )
        card = ttk.LabelFrame(self, text="版本狀態", padding=22)
        card.pack(fill="x")
        for label, value in (("目前版本", current_version), ("更新通道", "Stable"), ("資料 Schema", "2"),
                             ("狀態", "等待安全檢查")):
            row = ttk.Frame(card)
            row.pack(fill="x", pady=5)
            ttk.Label(row, text=label, width=18, style="Field.TLabel").pack(side="left")
            ttk.Label(row, text=value).pack(side="left")
        ttk.Label(
            self,
            text="正式環境需設定 HTTPS manifest URL 與內建 Ed25519 公鑰；私鑰永遠只留在離線發佈端。",
            style="Hint.TLabel",
            wraplength=900,
        ).pack(anchor="w", pady=18)


def configure_theme(root):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    root.configure(background="#F4F7FA")
    style.configure("TFrame", background="#F4F7FA")
    style.configure("TLabelframe", background="#FFFFFF", bordercolor="#C8D4DF", relief="solid")
    style.configure("TLabelframe.Label", font=("Microsoft JhengHei UI", 11, "bold"), foreground="#23445E")
    style.configure("TLabel", background="#F4F7FA", font=("Microsoft JhengHei UI", 10))
    style.configure("Title.TLabel", font=("Microsoft JhengHei UI", 23, "bold"), foreground="#16324F")
    style.configure("Hint.TLabel", font=("Microsoft JhengHei UI", 10), foreground="#546779")
    style.configure("Field.TLabel", font=("Microsoft JhengHei UI", 10, "bold"), foreground="#23445E")
    style.configure("Step.TLabel", font=("Microsoft JhengHei UI", 11, "bold"), background="#E4EEF6", foreground="#174C6E")
    style.configure("Status.TLabel", font=("Microsoft JhengHei UI", 12, "bold"), foreground="#176B4D")
    style.configure("Error.TLabel", font=("Microsoft JhengHei UI", 12, "bold"), foreground="#B42318")
    style.configure("Primary.TButton", font=("Microsoft JhengHei UI", 11, "bold"), padding=(18, 12))
    style.configure("Treeview", rowheight=34, font=("Microsoft JhengHei UI", 10), background="#FFFFFF")
    style.configure("Treeview.Heading", font=("Microsoft JhengHei UI", 10, "bold"), padding=(6, 8))
