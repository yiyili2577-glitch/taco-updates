from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox
)
from PyQt6.QtGui import QColor

from services.table_export_service import TableExportService


class WarehouseTransferDialog(QDialog):
    def __init__(self, result, parent=None):
        super().__init__(parent)
        self.result = result or {}
        self.summary_df = self.result.get("summary_df")
        self.transfer_df = self.result.get("transfer_df")

        self.setWindowTitle("三倉實際需求分配／跨倉調撥建議")
        self.resize(1350, 760)
        self.build_ui()

    def build_ui(self):
        layout = QVBoxLayout(self)

        summary_count = 0 if self.summary_df is None else len(self.summary_df)
        transfer_count = 0 if self.transfer_df is None else len(self.transfer_df)
        residual_gap = 0.0
        if self.summary_df is not None and not self.summary_df.empty and "調撥後缺口" in self.summary_df.columns:
            try:
                residual_gap = float(self.summary_df["調撥後缺口"].sum())
            except Exception:
                residual_gap = 0.0

        info = QLabel(
            f"分析產品：{summary_count}　｜　建議調撥：{transfer_count} 筆　｜　調撥後總缺口：{residual_gap:g}\n"
            "邏輯：先由指定出貨倉支應客戶需求，再以其他倉的剩餘現貨補缺；仍不足才保留為缺口。"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        toolbar = QHBoxLayout()
        btn_excel = QPushButton("📊 匯出 Excel")
        btn_pdf = QPushButton("📄 匯出 PDF")
        btn_close = QPushButton("關閉")
        toolbar.addWidget(btn_excel)
        toolbar.addWidget(btn_pdf)
        toolbar.addStretch()
        toolbar.addWidget(btn_close)
        layout.addLayout(toolbar)

        tabs = QTabWidget()
        self.summary_table = QTableWidget()
        self.transfer_table = QTableWidget()
        tabs.addTab(self._wrap(self.summary_table), "① 各產品三倉分配")
        tabs.addTab(self._wrap(self.transfer_table), "② 實際調撥清單")
        layout.addWidget(tabs, 1)

        self.fill_table(self.summary_table, self.summary_df, mode="summary")
        self.fill_table(self.transfer_table, self.transfer_df, mode="transfer")

        btn_excel.clicked.connect(self.export_excel)
        btn_pdf.clicked.connect(self.export_pdf)
        btn_close.clicked.connect(self.accept)

    def _wrap(self, table):
        page = QWidget()
        layout = QVBoxLayout(page)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        layout.addWidget(table)
        return page

    def fill_table(self, table, df, mode=""):
        table.clear()
        if df is None or df.empty:
            table.setRowCount(0)
            table.setColumnCount(0)
            return
        table.setRowCount(len(df))
        table.setColumnCount(len(df.columns))
        table.setHorizontalHeaderLabels([str(c) for c in df.columns])
        for r in range(len(df)):
            for c, col in enumerate(df.columns):
                value = df.iloc[r, c]
                if str(value) == "nan":
                    value = ""
                item = QTableWidgetItem(str(value))
                if mode == "summary":
                    try:
                        if float(df.iloc[r].get("調撥後缺口", 0) or 0) > 0:
                            item.setBackground(QColor("#FFE4E6"))
                        elif float(df.iloc[r].get("可由他倉調撥", 0) or 0) > 0:
                            item.setBackground(QColor("#FFF4CC"))
                    except Exception:
                        pass
                self_table = table
                self_table.setItem(r, c, item)
        table.resizeColumnsToContents()

    def export_excel(self):
        ok = TableExportService.export_tables_excel(
            self,
            [("三倉需求分配", self.summary_table), ("跨倉調撥清單", self.transfer_table)],
            "三倉需求分配_跨倉調撥建議.xlsx"
        )
        if ok is False:
            return

    def export_pdf(self):
        ok = TableExportService.export_tables_pdf(
            self,
            [("三倉需求分配", self.summary_table), ("跨倉調撥清單", self.transfer_table)],
            "三倉需求分配與跨倉調撥建議",
            "三倉需求分配_跨倉調撥建議.pdf"
        )
        if ok is False:
            return
