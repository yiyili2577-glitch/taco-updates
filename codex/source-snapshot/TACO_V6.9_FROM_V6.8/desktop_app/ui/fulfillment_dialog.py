from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox, QComboBox, QMessageBox, QLineEdit
)
from PyQt6.QtCore import Qt

from services.fulfillment_service import FulfillmentService
from services.warehouse_service import WarehouseService


class FulfillmentDialog(QDialog):
    def __init__(self, detail_df, parent=None):
        super().__init__(parent)
        self.detail_df = FulfillmentService.apply_routes(detail_df.copy())
        self.warehouse_names = WarehouseService.load_names()
        self.setWindowTitle("客戶需求履約／出貨分流")
        self.resize(1280, 720)
        self._build_ui()
        self.refresh_table()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        note = QLabel(
            "供應商直送＝不扣公司庫存；倉庫出貨＝扣指定倉庫庫存；"
            "公司入庫＝視為已安排入庫，不列入本次新增採購需求。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        tools = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("搜尋客戶、產品編號、產品名稱、採購單號...")
        self.btn_select_all = QPushButton("☑ 全選")
        self.btn_clear = QPushButton("☐ 取消全選")
        self.bulk_mode = QComboBox(); self.bulk_mode.addItems([
            FulfillmentService.MODE_SUPPLIER_DIRECT,
            FulfillmentService.MODE_WAREHOUSE,
            FulfillmentService.MODE_COMPANY_INBOUND,
        ])
        self.bulk_warehouse = QComboBox(); self.bulk_warehouse.addItems(self.warehouse_names)
        self.btn_apply = QPushButton("套用到勾選列")
        self.btn_save = QPushButton("💾 儲存履約設定")
        tools.addWidget(QLabel("搜尋")); tools.addWidget(self.search, 1)
        tools.addWidget(self.btn_select_all); tools.addWidget(self.btn_clear)
        tools.addWidget(QLabel("批次方式")); tools.addWidget(self.bulk_mode)
        tools.addWidget(QLabel("出貨倉")); tools.addWidget(self.bulk_warehouse)
        tools.addWidget(self.btn_apply); tools.addWidget(self.btn_save)
        layout.addLayout(tools)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        layout.addWidget(self.table, 1)

        self.search.textChanged.connect(self.refresh_table)
        self.btn_select_all.clicked.connect(lambda: self._set_checks(True))
        self.btn_clear.clicked.connect(lambda: self._set_checks(False))
        self.btn_apply.clicked.connect(self.apply_bulk)
        self.btn_save.clicked.connect(self.save_all)

    def _filtered_df(self):
        keyword = self.search.text().strip().lower()
        if not keyword:
            return self.detail_df.copy().reset_index(drop=False).rename(columns={"index": "_source_index"})
        mask = self.detail_df.astype(str).apply(
            lambda r: r.str.lower().str.contains(keyword, regex=False).any(), axis=1
        )
        return self.detail_df[mask].copy().reset_index(drop=False).rename(columns={"index": "_source_index"})

    def refresh_table(self):
        df = self._filtered_df()
        headers = ["選取", "採購單號", "客戶", "產品編號", "產品名稱", "PDF品名規格", "數量", "原配送類型", "履約方式", "出貨倉"]
        self.table.clear(); self.table.setRowCount(len(df)); self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self._row_source_indexes = {}
        for r, (_, row) in enumerate(df.iterrows()):
            self._row_source_indexes[r] = int(row["_source_index"])
            check = QCheckBox(); check.setChecked(False); self.table.setCellWidget(r, 0, check)
            vals = [row.get("採購單號", ""), row.get("客戶", ""), row.get("產品編號", ""), row.get("產品名稱", ""), row.get("PDF品名規格", ""), row.get("數量", ""), row.get("配送類型", "")]
            for c, value in enumerate(vals, start=1):
                self.table.setItem(r, c, QTableWidgetItem(str(value)))
            mode = QComboBox(); mode.addItems([
                FulfillmentService.MODE_SUPPLIER_DIRECT,
                FulfillmentService.MODE_WAREHOUSE,
                FulfillmentService.MODE_COMPANY_INBOUND,
            ]); mode.setCurrentText(str(row.get("履約方式", FulfillmentService.MODE_SUPPLIER_DIRECT)))
            wh = QComboBox(); wh.addItem(""); wh.addItems(self.warehouse_names); wh.setCurrentText(str(row.get("出貨倉", "")))
            mode.currentTextChanged.connect(lambda text, combo=wh: combo.setEnabled(text == FulfillmentService.MODE_WAREHOUSE))
            wh.setEnabled(mode.currentText() == FulfillmentService.MODE_WAREHOUSE)
            self.table.setCellWidget(r, 8, mode); self.table.setCellWidget(r, 9, wh)
        self.table.setColumnWidth(4, 200); self.table.setColumnWidth(5, 260)

    def _set_checks(self, checked):
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 0)
            if isinstance(w, QCheckBox): w.setChecked(checked)

    def apply_bulk(self):
        mode = self.bulk_mode.currentText()
        wh = self.bulk_warehouse.currentText() if mode == FulfillmentService.MODE_WAREHOUSE else ""
        count = 0
        for r in range(self.table.rowCount()):
            check = self.table.cellWidget(r, 0)
            if not isinstance(check, QCheckBox) or not check.isChecked():
                continue
            self.table.cellWidget(r, 8).setCurrentText(mode)
            self.table.cellWidget(r, 9).setCurrentText(wh)
            count += 1
        if count == 0:
            QMessageBox.information(self, "沒有勾選", "請先勾選要批次設定的需求列。")

    def save_all(self):
        records = []
        for r in range(self.table.rowCount()):
            src = self._row_source_indexes[r]
            row = self.detail_df.loc[src]
            key = FulfillmentService.row_key(row)
            mode = self.table.cellWidget(r, 8).currentText()
            wh = self.table.cellWidget(r, 9).currentText() if mode == FulfillmentService.MODE_WAREHOUSE else ""
            records.append({"key": key, "mode": mode, "warehouse": wh})
        count = FulfillmentService.save_bulk(records)
        self.detail_df = FulfillmentService.apply_routes(self.detail_df)
        QMessageBox.information(self, "完成", f"已儲存 {count} 筆履約／出貨設定。")
        self.accept()
