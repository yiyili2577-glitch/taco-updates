from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog,
    QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView, QDialog,
    QFormLayout, QLineEdit, QDialogButtonBox, QAbstractItemView
)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt

from services.excel_service import ExcelService
from services.inventory_service import InventoryService
from services.warehouse_service import WarehouseService
from services.table_export_service import TableExportService
from ui.column_visibility_dialog import ColumnVisibilityDialog
from services.customer_demand_store_service import CustomerDemandStoreService
from services.warehouse_transfer_service import WarehouseTransferService
from ui.warehouse_transfer_dialog import WarehouseTransferDialog
from services.dashboard_data_service import DashboardDataService
from services.audit_log_service import AuditLogService

from ui.responsive_action_bar import FlowLayout
from ui.page_header import add_page_header


class WarehouseSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("三倉名稱設定")
        self.setMinimumWidth(420)
        layout = QFormLayout(self)
        names = WarehouseService.load_names()
        self.inputs = []
        for i in range(3):
            edit = QLineEdit(names[i])
            self.inputs.append(edit)
            layout.addRow(f"倉別 {i + 1}", edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self):
        return [x.text().strip() for x in self.inputs]


class InventoryPage(QWidget):
    def __init__(self):
        super().__init__()
        self.df = None
        self.warehouse_names = WarehouseService.load_names()
        self.customer_demand_df = None
        self.transfer_result = {"summary_df": None, "transfer_df": None}
        self.build_ui()

    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 18, 20, 20)
        main_layout.setSpacing(12)

        add_page_header(
            main_layout,
            "庫存分析",
            "三倉庫存、客戶需求與跨倉調撥集中作業。先匯入或載入庫存，再進行三倉調整、調撥分析與匯出。",
        )

        toolbar = FlowLayout(h_spacing=7, v_spacing=7)
        self.btn_import = QPushButton("📂 選擇正航 Excel")
        self.btn_import.setFixedHeight(42)
        self.btn_import.setProperty("buttonRole", "primary")
        self.btn_warehouse_names = QPushButton("🏬 三倉名稱設定")
        self.btn_save_warehouse = QPushButton("💾 儲存三倉庫存")
        self.btn_transfer_analysis = QPushButton("🔄 套用客需／調撥分析")
        self.btn_open_transfer = QPushButton("🏬 查看調撥建議")
        self.btn_hide_empty = QPushButton("🙈 隱藏空白欄")
        self.btn_columns = QPushButton("⚙ 欄位顯示")
        self.btn_export_excel = QPushButton("📊 匯出 Excel")
        self.btn_export_pdf = QPushButton("📄 匯出 PDF")
        self.file_label = QLabel("尚未選擇 Excel")
        toolbar.addWidget(self.btn_import)
        toolbar.addWidget(self.btn_warehouse_names)
        toolbar.addWidget(self.btn_save_warehouse)
        toolbar.addWidget(self.btn_transfer_analysis)
        toolbar.addWidget(self.btn_open_transfer)
        toolbar.addWidget(self.btn_hide_empty)
        toolbar.addWidget(self.btn_columns)
        toolbar.addStretch()
        toolbar.addWidget(self.btn_export_excel)
        toolbar.addWidget(self.btn_export_pdf)
        toolbar.addWidget(self.file_label)
        main_layout.addLayout(toolbar)

        self.status_label = QLabel("匯入正航 ERP Excel 後，可直接編輯三個倉別的庫存數量。")
        self.status_label.setProperty("muted", True)
        main_layout.addWidget(self.status_label)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        main_layout.addWidget(self.table)

        self.btn_import.clicked.connect(self.select_excel)
        self.btn_warehouse_names.clicked.connect(self.edit_warehouse_names)
        self.btn_save_warehouse.clicked.connect(self.save_warehouse_inventory)
        self.btn_transfer_analysis.clicked.connect(self.apply_transfer_analysis)
        self.btn_open_transfer.clicked.connect(self.open_transfer_dialog)
        self.btn_hide_empty.clicked.connect(self.hide_empty_columns)
        self.btn_columns.clicked.connect(self.choose_columns)
        self.btn_export_excel.clicked.connect(self.export_excel)
        self.btn_export_pdf.clicked.connect(self.export_pdf)
        self.table.itemChanged.connect(self.on_item_changed)

    def select_excel(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "選擇正航 Excel", "", "Excel Files (*.xlsx *.xls *.xlsm)")
        if not file_path:
            return
        try:
            self.file_label.setText(file_path)
            self.status_label.setText("正在讀取 Excel...")
            raw = ExcelService.read_excel(file_path)
            self.df = InventoryService.clean_inventory_data(raw)
            self.warehouse_names = WarehouseService.load_names()
            self.df = WarehouseService.enrich_dataframe(self.df, initialize_from_current=True)
            # 三倉總和成為後續採購真正的目前庫存基礎。
            self.df["目前庫存"] = self.df["三倉庫存合計"]
            self._enrich_transfer_analysis(silent=True)
            self.display_dataframe(self.df)
            DashboardDataService.save_inventory_snapshot(self.df, file_path)
            AuditLogService.log_event("庫存", "匯入庫存 Excel", record_id=file_path, after={"產品數": len(self.df)}, result="成功")
            self.status_label.setText(f"讀取成功：{len(self.df)} 個產品。三倉欄位可直接編輯，完成後按『儲存三倉庫存』。")
        except Exception as e:
            QMessageBox.critical(self, "Excel 讀取失敗", str(e))
            self.status_label.setText("Excel 讀取失敗")

    def edit_warehouse_names(self):
        dlg = WarehouseSettingsDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        before_names = WarehouseService.load_names()
        self.warehouse_names = WarehouseService.save_names(dlg.values())
        AuditLogService.log_event("庫存", "修改倉庫名稱", before=before_names, after=self.warehouse_names, result="成功")
        if self.df is not None and not self.df.empty:
            self.df = WarehouseService.enrich_dataframe(self.df, initialize_from_current=True)
            self.df["目前庫存"] = self.df["三倉庫存合計"]
            self.display_dataframe(self.df)
        QMessageBox.information(self, "完成", "三個倉別名稱已儲存。")

    def save_warehouse_inventory(self):
        if self.df is None or self.df.empty:
            QMessageBox.warning(self, "沒有資料", "請先匯入庫存 Excel。")
            return
        self._sync_table_to_df()
        count = WarehouseService.save_from_dataframe(self.df)
        self.df = WarehouseService.enrich_dataframe(self.df, initialize_from_current=False)
        self.df["目前庫存"] = self.df["三倉庫存合計"]
        self._enrich_transfer_analysis(silent=True)
        self.display_dataframe(self.df)
        DashboardDataService.save_inventory_snapshot(self.df, self.file_label.text())
        AuditLogService.log_event("庫存", "儲存三倉庫存", after={"產品數": count}, result="成功")
        QMessageBox.information(self, "完成", f"已儲存 {count} 個產品的三倉庫存。")

    def _sync_table_to_df(self):
        if self.df is None or self.df.empty:
            return
        for name in WarehouseService.load_names():
            if name not in self.df.columns:
                continue
            col = self.df.columns.get_loc(name)
            for row in range(self.table.rowCount()):
                item = self.table.item(row, col)
                if item is None:
                    continue
                try:
                    value = float(item.text().replace(",", "").strip() or 0)
                except Exception:
                    value = 0.0
                self.df.iat[row, col] = value
        names = WarehouseService.load_names()
        self.df["三倉庫存合計"] = self.df[names].apply(lambda s: s.astype(float), axis=1).sum(axis=1)
        self.df["目前庫存"] = self.df["三倉庫存合計"]

    def on_item_changed(self, item):
        if self.df is None or self.df.empty:
            return
        col_name = self.df.columns[item.column()] if item.column() < len(self.df.columns) else ""
        if col_name not in WarehouseService.load_names():
            return
        try:
            value = float(item.text().replace(",", "").strip() or 0)
            if value < 0:
                raise ValueError()
        except Exception:
            item.setText("0")
            return
        old_value = self.df.iat[item.row(), item.column()]
        self.df.iat[item.row(), item.column()] = value
        product_no = str(self.df.iloc[item.row()].get("產品編號", ""))
        if str(old_value) != str(value):
            AuditLogService.log_event("庫存", "人工調整倉庫庫存", record_id=product_no, before={col_name: old_value}, after={col_name: value}, result="成功", severity="重要")
        names = WarehouseService.load_names()
        self.df["三倉庫存合計"] = self.df[names].apply(lambda s: s.astype(float), axis=1).sum(axis=1)
        self.df["目前庫存"] = self.df["三倉庫存合計"]
        if "三倉庫存合計" in self.df.columns:
            total_col = self.df.columns.get_loc("三倉庫存合計")
            self.table.blockSignals(True)
            self.table.setItem(item.row(), total_col, QTableWidgetItem(str(round(self.df.iloc[item.row()]["三倉庫存合計"], 2))))
            self.table.blockSignals(False)

    def _enrich_transfer_analysis(self, silent=False):
        if self.df is None or self.df.empty:
            return
        try:
            self.customer_demand_df = CustomerDemandStoreService.load_summary()
            self.transfer_result = WarehouseTransferService.calculate(
                self.df, self.customer_demand_df
            )
            summary = self.transfer_result.get("summary_df")
            if summary is None or summary.empty:
                return
            keep = ["產品編號"]
            for col in summary.columns:
                if col in {"產品編號", "產品名稱", "三倉現有庫存"}:
                    continue
                keep.append(col)
            existing = [c for c in keep if c != "產品編號" and c in self.df.columns]
            if existing:
                self.df = self.df.drop(columns=existing)
            self.df = self.df.merge(summary[keep], on="產品編號", how="left")
        except Exception as e:
            if not silent:
                QMessageBox.warning(self, "調撥分析失敗", str(e))

    def apply_transfer_analysis(self):
        if self.df is None or self.df.empty:
            QMessageBox.warning(self, "沒有資料", "請先匯入庫存 Excel。")
            return
        self._sync_table_to_df()
        self._enrich_transfer_analysis(silent=False)
        self.display_dataframe(self.df)
        DashboardDataService.save_inventory_snapshot(self.df, self.file_label.text())
        status = CustomerDemandStoreService.get_status()
        AuditLogService.log_event("跨倉調撥", "重新分析跨倉調撥", after={"產品數": len(self.df)}, result="成功")
        QMessageBox.information(
            self, "完成",
            f"已重新套用客戶需求與跨倉調撥分析。\n客戶需求更新：{status.get('updated_at', '') or '無'}"
        )

    def open_transfer_dialog(self):
        if self.df is None or self.df.empty:
            QMessageBox.warning(self, "沒有資料", "請先匯入庫存 Excel。")
            return
        self._sync_table_to_df()
        self._enrich_transfer_analysis(silent=False)
        self.display_dataframe(self.df)
        WarehouseTransferDialog(self.transfer_result, self).exec()

    def display_dataframe(self, df):
        self.table.blockSignals(True)
        self.table.setSortingEnabled(False)
        self.table.clear()
        self.table.setRowCount(len(df))
        self.table.setColumnCount(len(df.columns))
        self.table.setHorizontalHeaderLabels([str(c) for c in df.columns])
        status_idx = df.columns.get_loc("狀態") if "狀態" in df.columns else None
        editable = set(WarehouseService.load_names())
        for r in range(len(df)):
            status = str(df.iloc[r, status_idx]) if status_idx is not None else ""
            for c, col_name in enumerate(df.columns):
                value = df.iloc[r, c]
                if str(value) == "nan":
                    value = ""
                item = QTableWidgetItem(str(value))
                if col_name in editable:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                    item.setBackground(QColor("#FFF2B2"))
                else:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    if "急需採購" in status:
                        item.setBackground(QColor("#FFE4E6"))
                    elif "注意" in status:
                        item.setBackground(QColor("#FFF4CC"))
                    elif "正常" in status:
                        item.setBackground(QColor("#E8F7EE"))
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        for name in ["產品名稱", "規格", "材質", "包裝方式"]:
            if name in df.columns:
                self.table.setColumnWidth(df.columns.get_loc(name), 220)
        self.table.blockSignals(False)

    def hide_empty_columns(self):
        hidden = TableExportService.hide_empty_columns(self.table)
        QMessageBox.information(self, "欄位顯示", f"已暫時隱藏 {hidden} 個完全空白的欄位。\n0 仍視為有效資料，不會被隱藏。")

    def choose_columns(self):
        if self.table.columnCount() == 0:
            QMessageBox.information(self, "沒有欄位", "請先匯入庫存資料。")
            return
        ColumnVisibilityDialog(self.table, self, "庫存分析 - 欄位顯示設定").exec()

    def export_excel(self):
        TableExportService.export_tables_excel(
            self, [("庫存分析", self.table)], "庫存分析.xlsx"
        )

    def export_pdf(self):
        TableExportService.export_tables_pdf(
            self, [("庫存分析", self.table)], "庫存分析", "庫存分析.pdf"
        )
