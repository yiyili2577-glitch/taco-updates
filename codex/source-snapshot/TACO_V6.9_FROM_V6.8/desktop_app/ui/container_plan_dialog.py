import pandas as pd
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QMessageBox, QTabWidget,
    QWidget, QAbstractItemView, QInputDialog
)

from services.container_planning_service import ContainerPlanningService
from services.financial_service import FinancialService
from ui.import_profile_dialog import ImportProfileDialog


class ContainerPlanDialog(QDialog):
    def __init__(self, purchase_df, parent=None):
        super().__init__(parent)
        self.df = purchase_df.copy() if purchase_df is not None else pd.DataFrame()
        self.result = None
        self.setWindowTitle("進口混櫃規劃｜資料自我檢查")
        self.resize(1360, 780)
        self._build_ui(); self.refresh()

    def _build_ui(self):
        layout=QVBoxLayout(self)
        intro=QLabel("混櫃資料來源：採購建議的「實際採購量＋本次供應商」＋「包裝／進口設定」的每箱數量、紙箱尺寸、單價與幣別。缺資料的品項會列在第二頁，不再只顯示空表。")
        intro.setWordWrap(True); layout.addWidget(intro)
        tools=QHBoxLayout(); self.supplier=QComboBox(); self.supplier.addItem("全部供應商")
        suppliers=sorted({str(x).strip() for x in self.df.get("本次採購供應商",[]) if str(x).strip()})
        self.supplier.addItems(suppliers); self.summary=QLabel(""); self.btn_refresh=QPushButton("🔄 重新檢查")
        self.btn_edit=QPushButton("✏ 補所選品項資料"); self.btn_finance=QPushButton("💰 建立進口成本批次")
        for x in [QLabel("供應商"),self.supplier,self.summary,self.btn_refresh,self.btn_edit,self.btn_finance]: tools.addWidget(x,1 if x is self.summary else 0)
        layout.addLayout(tools)
        self.tabs=QTabWidget(); layout.addWidget(self.tabs,1)
        self.valid_table=self._table(); self.issue_table=self._table()
        p1=QWidget(); l1=QVBoxLayout(p1); l1.addWidget(self.valid_table)
        p2=QWidget(); l2=QVBoxLayout(p2); l2.addWidget(QLabel("只有實際採購量 > 0 的品項才會檢查。以下資料補齊後即可回到『可裝櫃』。")); l2.addWidget(self.issue_table)
        self.tabs.addTab(p1,"① 可裝櫃品項"); self.tabs.addTab(p2,"② 缺少資料／不能計算")
        note=QLabel("CBM 為理論體積。正式裝櫃仍需考慮重量上限、棧板、裝載空隙與實際貨櫃內尺寸。建立『進口成本批次』後，可到財務中心輸入海運、報關、關稅、拖車等共同成本並按 CBM 分攤。")
        note.setWordWrap(True); layout.addWidget(note)
        self.supplier.currentTextChanged.connect(self.refresh); self.btn_refresh.clicked.connect(self.refresh); self.btn_edit.clicked.connect(self.edit_selected); self.btn_finance.clicked.connect(self.create_finance_batch)

    def _table(self):
        t=QTableWidget(); t.setAlternatingRowColors(True); t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection); t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers); t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive); return t

    def _show(self, table, df):
        table.clear()
        if df is None or df.empty: table.setRowCount(0); table.setColumnCount(0); return
        table.setRowCount(len(df)); table.setColumnCount(len(df.columns)); table.setHorizontalHeaderLabels([str(c) for c in df.columns])
        for r,(_,row) in enumerate(df.iterrows()):
            for c,col in enumerate(df.columns): table.setItem(r,c,QTableWidgetItem(str(row.get(col,""))))
        table.resizeColumnsToContents()

    def refresh(self):
        self.result=ContainerPlanningService.build_plan(self.df,self.supplier.currentText())
        valid=self.result["valid_df"]; issues=self.result["issues_df"]; s=self.result["summary"]
        cols=["產品編號","產品名稱","本次採購供應商","實際採購量","採購數量單位","包裝方式","每箱數量","換算箱數","紙箱長CM","紙箱寬CM","紙箱高CM","單箱CBM","本次CBM","幣別","單價","計價單位","計價數量","商品總價"]
        self._show(self.valid_table, valid[[c for c in cols if c in valid.columns]] if not valid.empty else valid)
        self._show(self.issue_table, issues)
        amounts="；".join(f"{k} {v:,.2f}" for k,v in s["amounts_by_currency"].items() if k) or "尚無商品金額"
        self.summary.setText(f"可裝櫃 {s['valid_count']}｜缺資料 {s['issue_count']}｜零採購量略過 {s['skipped_zero_count']}｜總CBM {s['total_cbm']:.2f}｜預估 {s['container_count']} 櫃｜末櫃 {s['last_container_usage_pct']:.1f}%｜{amounts}")
        self.tabs.setTabText(0,f"① 可裝櫃品項（{len(valid)}）"); self.tabs.setTabText(1,f"② 缺少資料／不能計算（{len(issues)}）")

    def _selected_product(self):
        table=self.issue_table if self.tabs.currentIndex()==1 else self.valid_table
        row=table.currentRow()
        if row<0: return None
        headers={table.horizontalHeaderItem(c).text():c for c in range(table.columnCount()) if table.horizontalHeaderItem(c)}
        def text(name):
            c=headers.get(name); item=table.item(row,c) if c is not None else None; return item.text().strip() if item else ""
        return text("產品編號"), text("產品名稱"), text("供應商") or text("本次採購供應商")

    def edit_selected(self):
        selected=self._selected_product()
        if not selected: QMessageBox.information(self,"請選品項","請先在表格選取一個產品。"); return
        pno,pname,supplier=selected
        d=ImportProfileDialog(pno,pname,supplier,self)
        if d.exec()!=QDialog.DialogCode.Accepted: return
        from services.import_profile_service import ImportProfileService
        ImportProfileService.save_profile(pno,supplier,d.profile()); self.refresh(); QMessageBox.information(self,"完成","包裝／進口設定已儲存並重新檢查。")

    def create_finance_batch(self):
        if not self.result or self.result["valid_df"].empty: QMessageBox.warning(self,"沒有可建立資料","目前沒有完整的可裝櫃品項。請先到第二頁補齊資料。"); return
        text,ok=QInputDialog.getText(self,"建立進口成本批次","備註（可留空，例如：2026/08 中國混櫃）：")
        if not ok: return
        try:
            shipment=FinancialService.create_import_shipment(self.result["valid_df"],self.result["summary"],text.strip())
            QMessageBox.information(self,"已建立",f"進口成本批次：{shipment['id']}\n品項：{len(shipment['rows'])}\n總 CBM：{shipment['total_cbm']:.2f}\n\n接著請到『財務中心 → 進口成本』輸入海運、報關、關稅等共同成本。")
        except Exception as e: QMessageBox.critical(self,"建立失敗",str(e))
