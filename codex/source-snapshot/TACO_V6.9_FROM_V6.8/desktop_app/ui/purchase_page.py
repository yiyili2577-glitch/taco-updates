import pandas as pd

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QHeaderView,
    QFileDialog,
    QAbstractItemView,
    QComboBox,
    QProgressBar,
    QApplication,
)

from PyQt6.QtGui import QColor

from PyQt6.QtCore import Qt

from services.excel_service import ExcelService
from services.inventory_service import InventoryService
from services.supplier_service import SupplierService
from services.purchase_service import PurchaseService
from services.product_master_service import ProductMasterService
from services.customer_demand_store_service import CustomerDemandStoreService
from services.warehouse_service import WarehouseService
from services.import_profile_service import ImportProfileService
from ui.import_profile_dialog import ImportProfileDialog
from ui.container_plan_dialog import ContainerPlanDialog
from services.table_export_service import TableExportService
from ui.column_visibility_dialog import ColumnVisibilityDialog
from services.warehouse_transfer_service import WarehouseTransferService
from ui.warehouse_transfer_dialog import WarehouseTransferDialog
from services.dashboard_data_service import DashboardDataService
from services.audit_log_service import AuditLogService

from ui.responsive_action_bar import FlowLayout
from ui.page_header import add_page_header


class PurchasePage(QWidget):

    def __init__(self):

        super().__init__()

        self.inventory_df = None

        self.purchase_df = None

        self.suppliers = []

        self.customer_demand_df = pd.DataFrame()

        self.demand_snapshot_status = {}

        self.transfer_result = {"summary_df": pd.DataFrame(), "transfer_df": pd.DataFrame()}

        self.build_ui()

    # =====================================================
    # UI
    # =====================================================

    def build_ui(self):

        main_layout = QVBoxLayout(
            self
        )

        main_layout.setContentsMargins(
            20,
            18,
            20,
            20
        )

        main_layout.setSpacing(
            12
        )

        add_page_header(
            main_layout,
            "採購建議",
            "整合客戶需求、三倉庫存、在途、供應商交期、安全庫存、MOQ 與採購倍數，形成可執行的採購工作清單。",
        )

        toolbar = FlowLayout(h_spacing=7, v_spacing=7)

        self.btn_import = QPushButton(
            "📂 選擇正航庫存 Excel"
        )

        self.btn_calculate = QPushButton(
            "🧮 重新計算"
        )
        self.btn_calculate.setProperty("buttonRole", "primary")

        self.btn_reset = QPushButton(
            "↩ 實際量重設為建議量"
        )

        self.btn_reload_demand = QPushButton(
            "👥 重新載入客戶需求"
        )

        self.btn_import_profile = QPushButton(
            "📦 包裝／進口設定"
        )

        self.btn_container_plan = QPushButton(
            "🚢 混櫃規劃"
        )

        self.btn_transfer_plan = QPushButton(
            "🏬 三倉調撥建議"
        )

        self.btn_hide_empty = QPushButton(
            "🙈 隱藏空白欄"
        )

        self.btn_columns = QPushButton(
            "⚙ 欄位顯示"
        )

        self.btn_export_current_excel = QPushButton(
            "📊 匯出目前表 Excel"
        )

        self.btn_export_current_pdf = QPushButton(
            "📄 匯出目前表 PDF"
        )

        self.btn_export = QPushButton(
            "📤 只匯出要採購的品項"
        )

        toolbar.addWidget(
            self.btn_import
        )

        toolbar.addWidget(
            self.btn_calculate
        )

        toolbar.addWidget(
            self.btn_reset
        )

        toolbar.addWidget(
            self.btn_reload_demand
        )

        toolbar.addWidget(
            self.btn_import_profile
        )

        toolbar.addWidget(
            self.btn_container_plan
        )

        toolbar.addWidget(
            self.btn_transfer_plan
        )

        toolbar.addWidget(
            self.btn_hide_empty
        )

        toolbar.addWidget(
            self.btn_columns
        )

        toolbar.addStretch()

        toolbar.addWidget(
            self.btn_export_current_excel
        )

        toolbar.addWidget(
            self.btn_export_current_pdf
        )

        toolbar.addWidget(
            self.btn_export
        )

        main_layout.addLayout(
            toolbar
        )

        status_row = QHBoxLayout()

        self.status_label = QLabel(
            "尚未載入資料"
        )
        self.status_label.setProperty("muted", True)

        self.progress_bar = QProgressBar()

        self.progress_bar.setRange(
            0,
            100
        )

        self.progress_bar.setValue(
            0
        )

        self.progress_bar.setMaximumWidth(
            320
        )

        status_row.addWidget(
            self.status_label,
            1
        )

        status_row.addWidget(
            self.progress_bar
        )

        main_layout.addLayout(
            status_row
        )

        self.table = QTableWidget()

        self.table.setAlternatingRowColors(
            True
        )

        self.table.setSelectionBehavior(
            QAbstractItemView
            .SelectionBehavior
            .SelectRows
        )

        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView
            .ResizeMode
            .Interactive
        )

        main_layout.addWidget(
            self.table
        )

        self.btn_import.clicked.connect(
            self.select_excel
        )

        self.btn_calculate.clicked.connect(
            self.calculate_recommendations
        )

        self.btn_reset.clicked.connect(
            self.reset_actual_qty
        )

        self.btn_reload_demand.clicked.connect(
            self.reload_customer_demand
        )

        self.btn_import_profile.clicked.connect(
            self.edit_import_profile
        )

        self.btn_container_plan.clicked.connect(
            self.open_container_plan
        )

        self.btn_transfer_plan.clicked.connect(
            self.open_transfer_plan
        )

        self.btn_hide_empty.clicked.connect(
            self.hide_empty_columns
        )

        self.btn_columns.clicked.connect(
            self.choose_columns
        )

        self.btn_export_current_excel.clicked.connect(
            self.export_current_excel
        )

        self.btn_export_current_pdf.clicked.connect(
            self.export_current_pdf
        )

        self.btn_export.clicked.connect(
            self.export_excel
        )

        self.table.itemChanged.connect(
            self.on_item_changed
        )

    # =====================================================
    # 欄位顯示 / 完整匯出
    # =====================================================

    def hide_empty_columns(self):
        hidden = TableExportService.hide_empty_columns(self.table)
        QMessageBox.information(
            self,
            "欄位顯示",
            f"已暫時隱藏 {hidden} 個完全空白欄位。\n0 / 0.0 是有效資料，不會被隱藏。"
        )

    def choose_columns(self):
        if self.table.columnCount() == 0:
            QMessageBox.information(self, "沒有欄位", "請先載入採購建議資料。")
            return
        ColumnVisibilityDialog(
            self.table, self, "採購建議 - 欄位顯示設定"
        ).exec()

    def export_current_excel(self):
        TableExportService.export_tables_excel(
            self, [("採購建議", self.table)], "採購建議_目前顯示.xlsx"
        )

    def export_current_pdf(self):
        TableExportService.export_tables_pdf(
            self, [("採購建議", self.table)], "採購建議", "採購建議_目前顯示.pdf"
        )

    # =====================================================
    # Progress
    # =====================================================

    def set_progress(
        self,
        value,
        text
    ):

        self.progress_bar.setValue(
            value
        )

        self.status_label.setText(
            text
        )

        QApplication.processEvents()

    # =====================================================
    # Import
    # =====================================================

    def select_excel(self):

        file_path, _ = (
            QFileDialog
            .getOpenFileName(
                self,
                "選擇正航庫存 Excel",
                "",
                "Excel Files (*.xlsx *.xlsm)"
            )
        )

        if not file_path:
            return

        try:

            self.btn_import.setEnabled(
                False
            )

            self.set_progress(
                10,
                "正在讀取 Excel..."
            )

            raw_df = (
                ExcelService
                .read_excel(
                    file_path
                )
            )

            if raw_df is None:

                raise Exception(
                    "Excel 沒有回傳資料。"
                )

            if raw_df.empty:

                raise Exception(
                    "Excel 內容為空白。"
                )

            self.set_progress(
                30,
                "正在辨識產品編號..."
            )

            normalized_df = (
                ProductMasterService
                .normalize_columns(
                    raw_df
                )
            )

            if (
                "產品編號"
                not in normalized_df.columns
            ):

                raise Exception(
                    "找不到「產品編號」欄位。\n\n"
                    "目前讀到的欄位：\n"
                    +
                    "、".join(
                        str(column)
                        for column
                        in normalized_df.columns
                    )
                )

            self.set_progress(
                50,
                "正在整理庫存資料..."
            )

            self.inventory_df = (
                InventoryService
                .clean_inventory_data(
                    normalized_df
                )
            )

            self.inventory_df = WarehouseService.enrich_dataframe(
                self.inventory_df,
                initialize_from_current=True
            )
            if "三倉庫存合計" in self.inventory_df.columns:
                self.inventory_df["目前庫存"] = self.inventory_df["三倉庫存合計"]

            self.set_progress(
                70,
                "正在載入供應商資料..."
            )

            self.suppliers = (
                SupplierService
                .load_suppliers()
            )

            self.load_customer_demand_snapshot()

            self.set_progress(
                85,
                "正在整合客戶需求並計算採購建議..."
            )

            self._calculate_purchase_data()

            self.set_progress(
                100,
                f"完成，共 {len(self.purchase_df)} 個產品。"
            )
            AuditLogService.log_event("採購建議", "匯入庫存並計算採購", record_id=file_path, after={"產品數": len(self.purchase_df)}, result="成功")

        except Exception as e:

            self.progress_bar.setValue(
                0
            )

            self.status_label.setText(
                "❌ 讀取失敗"
            )

            QMessageBox.critical(
                self,
                "採購建議讀取失敗",
                str(e)
            )

        finally:

            self.btn_import.setEnabled(
                True
            )

    # =====================================================
    # Supplier map
    # =====================================================

    def get_current_supplier_map(self):

        result = {}

        if (
            self.purchase_df is None
            or
            self.purchase_df.empty
        ):

            return result

        for _, row in (
            self.purchase_df
            .iterrows()
        ):

            product_no = str(
                row.get(
                    "產品編號",
                    ""
                )
            ).strip()

            supplier_name = str(
                row.get(
                    "本次採購供應商",
                    ""
                )
            ).strip()

            if (
                product_no
                and
                supplier_name
            ):

                result[
                    product_no
                ] = supplier_name

        return result

    # =====================================================
    # Customer demand snapshot
    # =====================================================

    def load_customer_demand_snapshot(self):

        self.customer_demand_df = (
            CustomerDemandStoreService
            .load_summary()
        )

        self.demand_snapshot_status = (
            CustomerDemandStoreService
            .get_status()
        )

    def reload_customer_demand(self):

        try:

            self.load_customer_demand_snapshot()

            product_count = int(
                self.demand_snapshot_status.get(
                    "product_count",
                    0
                )
                or
                0
            )

            updated_at = str(
                self.demand_snapshot_status.get(
                    "updated_at",
                    ""
                )
            )

            if self.inventory_df is not None:
                self._calculate_purchase_data()

            AuditLogService.log_event("採購建議", "重新載入客戶需求", after={"需求產品數": len(self.customer_demand_df) if self.customer_demand_df is not None else 0}, result="成功")
            QMessageBox.information(
                self,
                "客戶需求已載入",
                (
                    f"已載入 {product_count} 個已對應產品的客戶需求。\n"
                    f"更新時間：{updated_at or '無'}"
                )
            )

        except Exception as e:

            QMessageBox.critical(
                self,
                "載入客戶需求失敗",
                str(e)
            )

    # =====================================================
    # Calculate
    # =====================================================

    def calculate_recommendations(self):

        if self.inventory_df is None:

            QMessageBox.warning(
                self,
                "尚未載入",
                "請先選擇庫存 Excel。"
            )

            return

        try:

            self.set_progress(
                80,
                "正在重新計算..."
            )

            self.suppliers = (
                SupplierService
                .load_suppliers()
            )

            self.load_customer_demand_snapshot()

            self._calculate_purchase_data()

            self.set_progress(
                100,
                "重新計算完成"
            )

        except Exception as e:

            self.set_progress(
                0,
                "❌ 計算失敗"
            )

            QMessageBox.critical(
                self,
                "採購計算失敗",
                str(e)
            )

    def _calculate_purchase_data(self):

        preferred_map = (
            self.get_current_supplier_map()
        )

        self.purchase_df = (
            PurchaseService
            .calculate_purchase_recommendations(
                self.inventory_df,
                self.suppliers,
                preferred_map,
                self.customer_demand_df
            )
        )

        if self.purchase_df is None:

            raise Exception(
                "採購計算沒有回傳資料。"
            )

        if self.purchase_df.empty:

            self.display_dataframe(
                self.purchase_df
            )

            return

        self.purchase_df[
            "建議採購量"
        ] = pd.to_numeric(
            self.purchase_df[
                "建議採購量"
            ],
            errors="coerce"
        ).fillna(0).round().astype(
            int
        )

        self.purchase_df[
            "實際採購量"
        ] = self.purchase_df[
            "建議採購量"
        ].copy()

        self.attach_warehouse_columns()
        self.refresh_transfer_metrics()
        self.refresh_import_metrics()

        self.display_dataframe(
            self.purchase_df
        )

        DashboardDataService.save_purchase_snapshot(self.purchase_df)
        self.update_status_summary()

    # =====================================================
    # Display
    # =====================================================

    def display_dataframe(
        self,
        df
    ):

        self.table.blockSignals(
            True
        )

        self.table.clear()

        self.table.setRowCount(
            len(df)
        )

        self.table.setColumnCount(
            len(df.columns)
        )

        self.table.setHorizontalHeaderLabels(
            [
                str(column)
                for column
                in df.columns
            ]
        )

        supplier_index = None

        if (
            "本次採購供應商"
            in df.columns
        ):

            supplier_index = (
                df.columns
                .get_loc(
                    "本次採購供應商"
                )
            )

        for row_index in range(
            len(df)
        ):

            status = str(
                df.iloc[
                    row_index
                ].get(
                    "狀態",
                    ""
                )
            )

            product_no = str(
                df.iloc[
                    row_index
                ].get(
                    "產品編號",
                    ""
                )
            ).strip()

            for column_index in range(
                len(
                    df.columns
                )
            ):

                column_name = (
                    df.columns[
                        column_index
                    ]
                )

                if (
                    column_name
                    ==
                    "本次採購供應商"
                ):

                    continue

                value = (
                    df.iloc[
                        row_index,
                        column_index
                    ]
                )

                if pd.isna(
                    value
                ):

                    value = ""

                item = QTableWidgetItem(
                    str(value)
                )

                if (
                    column_name
                    ==
                    "實際採購量"
                ):

                    item.setFlags(
                        item.flags()
                        |
                        Qt.ItemFlag
                        .ItemIsEditable
                    )

                    item.setBackground(
                        QColor(
                            "#FFF2B2"
                        )
                    )

                else:

                    item.setFlags(
                        item.flags()
                        &
                        ~Qt.ItemFlag
                        .ItemIsEditable
                    )

                    if (
                        "立即採購"
                        in status
                    ):

                        item.setBackground(
                            QColor(
                                "#FFE4E6"
                            )
                        )

                    elif (
                        "建議採購"
                        in status
                    ):

                        item.setBackground(
                            QColor(
                                "#FFF4CC"
                            )
                        )

                    elif (
                        "暫不需採購"
                        in status
                    ):

                        item.setBackground(
                            QColor(
                                "#E8F7EE"
                            )
                        )

                self.table.setItem(
                    row_index,
                    column_index,
                    item
                )

            # ===========================================
            # Supplier dropdown
            # ===========================================

            if (
                supplier_index
                is not None
            ):

                combo = QComboBox()

                supplier_records = (
                    PurchaseService
                    .get_suppliers_for_item(
                        self.suppliers,
                        product_no
                    )
                )

                names = []

                for supplier in (
                    supplier_records
                ):

                    name = str(
                        supplier.get(
                            "supplier",
                            ""
                        )
                    ).strip()

                    if (
                        name
                        and
                        name not in names
                    ):

                        names.append(
                            name
                        )

                current_name = str(
                    df.iloc[
                        row_index
                    ].get(
                        "本次採購供應商",
                        ""
                    )
                ).strip()

                if names:

                    combo.addItems(
                        names
                    )

                    if (
                        current_name
                        in names
                    ):

                        combo.setCurrentText(
                            current_name
                        )

                else:

                    combo.addItem(
                        "未設定供應商"
                    )

                    combo.setEnabled(
                        False
                    )

                combo.currentTextChanged.connect(
                    lambda supplier_name,
                    row=row_index:
                    self.on_supplier_changed(
                        row,
                        supplier_name
                    )
                )

                self.table.setCellWidget(
                    row_index,
                    supplier_index,
                    combo
                )

        self.table.resizeColumnsToContents()

        self.table.blockSignals(
            False
        )

    # =====================================================
    # Supplier changed
    # =====================================================

    def on_supplier_changed(
        self,
        row_index,
        supplier_name
    ):

        if (
            self.purchase_df is None
            or
            self.inventory_df is None
        ):

            return

        if (
            supplier_name
            ==
            "未設定供應商"
        ):

            return

        product_no = str(
            self.purchase_df
            .iloc[
                row_index
            ]
            .get(
                "產品編號",
                ""
            )
        ).strip()

        matches = (
            self.inventory_df[
                self.inventory_df[
                    "產品編號"
                ]
                .astype(str)
                .str.strip()
                ==
                product_no
            ]
        )

        demand_map = (
            PurchaseService
            .build_demand_map(
                self.customer_demand_df
            )
        )

        if matches.empty:

            demand_record = demand_map.get(
                product_no,
                {}
            )

            inventory_row = pd.Series(
                {
                    "產品編號": product_no,
                    "產品名稱": demand_record.get(
                        "產品名稱",
                        ""
                    ),
                    "平均月耗用量": 0,
                    "目前庫存": 0,
                    "預計到貨": 0,
                }
            )

        else:

            inventory_row = matches.iloc[0]

        supplier = (
            PurchaseService
            .find_supplier(
                self.suppliers,
                product_no,
                supplier_name
            )
        )

        if supplier is None:
            return

        new_result = (
            PurchaseService
            .calculate_single_recommendation(
                inventory_row,
                supplier,
                demand_map.get(
                    product_no,
                    {}
                )
            )
        )

        df_index = (
            self.purchase_df
            .index[
                row_index
            ]
        )

        for key, value in (
            new_result.items()
        ):

            if (
                key
                in
                self.purchase_df.columns
            ):

                self.purchase_df.at[
                    df_index,
                    key
                ] = value

        self.purchase_df.at[
            df_index,
            "實際採購量"
        ] = int(
            new_result.get(
                "建議採購量",
                0
            )
        )

        self.display_dataframe(
            self.purchase_df
        )

        DashboardDataService.save_purchase_snapshot(self.purchase_df)
        self.update_status_summary()

    # =====================================================
    # Manual qty
    # =====================================================

    def on_item_changed(
        self,
        item
    ):

        if self.purchase_df is None:
            return

        column_index = (
            item.column()
        )

        if (
            column_index
            >=
            len(
                self.purchase_df
                .columns
            )
        ):

            return

        column_name = (
            self.purchase_df
            .columns[
                column_index
            ]
        )

        if (
            column_name
            !=
            "實際採購量"
        ):

            return

        try:

            text = (
                item.text()
                .replace(",", "")
                .strip()
            )

            value = (
                0
                if not text
                else
                float(text)
            )

            if value < 0:

                raise ValueError()

            value = int(
                round(
                    value
                )
            )

        except Exception:

            QMessageBox.warning(
                self,
                "數量錯誤",
                "實際採購量只能輸入 0 或正數。"
            )

            return

        df_index = (
            self.purchase_df
            .index[
                item.row()
            ]
        )

        old_value = self.purchase_df.at[df_index, "實際採購量"]
        self.purchase_df.at[
            df_index,
            "實際採購量"
        ] = value
        product_no = str(self.purchase_df.at[df_index, "產品編號"]) if "產品編號" in self.purchase_df.columns else ""
        if str(old_value) != str(value):
            AuditLogService.log_event("採購建議", "修改實際採購量", record_id=product_no, before={"實際採購量": old_value}, after={"實際採購量": value}, result="成功", severity="重要")

        self.refresh_import_metrics()
        self.display_dataframe(self.purchase_df)
        DashboardDataService.save_purchase_snapshot(self.purchase_df)
        self.update_status_summary()

    # =====================================================
    # 三倉欄位 + 進口貨櫃計算
    # =====================================================

    def attach_warehouse_columns(self):
        if self.purchase_df is None or self.purchase_df.empty or self.inventory_df is None:
            return
        names = WarehouseService.load_names()
        cols = [c for c in names + ["三倉庫存合計"] if c in self.inventory_df.columns]
        if not cols:
            return
        base = self.inventory_df[["產品編號"] + cols].copy()
        self.purchase_df = self.purchase_df.merge(base, on="產品編號", how="left", suffixes=("", "_倉"))

    def refresh_transfer_metrics(self):
        if self.purchase_df is None or self.purchase_df.empty:
            self.transfer_result = {"summary_df": pd.DataFrame(), "transfer_df": pd.DataFrame()}
            return

        self.transfer_result = WarehouseTransferService.calculate(
            self.purchase_df,
            self.customer_demand_df
        )
        summary = self.transfer_result.get("summary_df", pd.DataFrame())
        if summary is None or summary.empty:
            return

        keep = ["產品編號"]
        for col in summary.columns:
            if col in {"產品編號", "產品名稱", "三倉現有庫存"}:
                continue
            keep.append(col)

        # 重新計算時避免重複欄位。
        existing = [c for c in keep if c != "產品編號" and c in self.purchase_df.columns]
        if existing:
            self.purchase_df = self.purchase_df.drop(columns=existing)
        self.purchase_df = self.purchase_df.merge(
            summary[keep],
            on="產品編號",
            how="left"
        )

    def open_transfer_plan(self):
        if self.purchase_df is None or self.purchase_df.empty:
            QMessageBox.warning(self, "沒有資料", "請先載入並計算採購建議。")
            return
        self.load_customer_demand_snapshot()
        self.refresh_transfer_metrics()
        self.display_dataframe(self.purchase_df)
        WarehouseTransferDialog(self.transfer_result, self).exec()

    def refresh_import_metrics(self):
        if self.purchase_df is None or self.purchase_df.empty:
            return
        metric_rows = []
        for _, row in self.purchase_df.iterrows():
            pno = str(row.get("產品編號", "")).strip()
            supplier = str(row.get("本次採購供應商", "")).strip()
            qty = row.get("實際採購量", row.get("建議採購量", 0))
            profile = ImportProfileService.get_profile(pno, supplier)
            metric_rows.append(ImportProfileService.calculate(qty, profile))
        metrics = pd.DataFrame(metric_rows, index=self.purchase_df.index)
        for col in metrics.columns:
            self.purchase_df[col] = metrics[col]

    def edit_import_profile(self):
        if self.purchase_df is None or self.purchase_df.empty:
            QMessageBox.warning(self, "沒有資料", "請先載入採購建議資料。")
            return
        row = self.table.currentRow()
        if row < 0 or row >= len(self.purchase_df):
            QMessageBox.information(self, "請選產品", "請先在採購表選取一個產品列。")
            return
        data = self.purchase_df.iloc[row]
        pno = str(data.get("產品編號", "")).strip()
        pname = str(data.get("產品名稱", "")).strip()
        supplier = str(data.get("本次採購供應商", "")).strip()
        dialog = ImportProfileDialog(pno, pname, supplier, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        ImportProfileService.save_profile(pno, supplier, dialog.profile())
        self.refresh_import_metrics()
        self.display_dataframe(self.purchase_df)
        DashboardDataService.save_purchase_snapshot(self.purchase_df)
        QMessageBox.information(self, "完成", "包裝、單價、幣別與貨櫃設定已儲存。")

    # =====================================================
    # 混櫃規劃
    # =====================================================

    def open_container_plan(self):
        if self.purchase_df is None or self.purchase_df.empty:
            QMessageBox.warning(self, "沒有資料", "請先載入並計算採購建議。")
            return
        self.refresh_import_metrics()
        dialog = ContainerPlanDialog(self.purchase_df, self)
        dialog.exec()

    # =====================================================
    # Reset
    # =====================================================

    def reset_actual_qty(self):

        if (
            self.purchase_df is None
            or
            self.purchase_df.empty
        ):

            return

        self.purchase_df[
            "實際採購量"
        ] = pd.to_numeric(
            self.purchase_df[
                "建議採購量"
            ],
            errors="coerce"
        ).fillna(0).round().astype(
            int
        )

        self.refresh_import_metrics()
        self.display_dataframe(
            self.purchase_df
        )

        DashboardDataService.save_purchase_snapshot(self.purchase_df)
        self.update_status_summary()

    # =====================================================
    # Summary
    # =====================================================

    def update_status_summary(self):

        if (
            self.purchase_df is None
            or
            self.purchase_df.empty
        ):

            return

        quantities = pd.to_numeric(
            self.purchase_df[
                "實際採購量"
            ],
            errors="coerce"
        ).fillna(0)

        self.purchase_df[
            "實際採購量"
        ] = (
            quantities
            .round()
            .astype(int)
        )

        buy_rows = (
            self.purchase_df[
                self.purchase_df[
                    "實際採購量"
                ]
                > 0
            ]
        )

        total_qty = int(
            buy_rows[
                "實際採購量"
            ].sum()
        )

        demand_product_count = (
            len(self.customer_demand_df)
            if self.customer_demand_df is not None
            else 0
        )

        self.status_label.setText(
            (
                f"共 {len(self.purchase_df)} 個產品 ｜ "
                f"客戶需求 {demand_product_count} 項 ｜ "
                f"要採購 {len(buy_rows)} 項 ｜ "
                f"採購總量 {total_qty}"
            )
        )

    # =====================================================
    # Export
    # =====================================================

    def export_excel(self):

        if (
            self.purchase_df is None
            or
            self.purchase_df.empty
        ):

            QMessageBox.warning(
                self,
                "沒有資料",
                "目前沒有採購資料。"
            )

            return

        export_df = (
            self.purchase_df
            .copy()
        )

        export_df[
            "實際採購量"
        ] = pd.to_numeric(
            export_df[
                "實際採購量"
            ],
            errors="coerce"
        ).fillna(0).round().astype(
            int
        )

        export_df = (
            export_df[
                export_df[
                    "實際採購量"
                ] > 0
            ]
            .copy()
        )

        if export_df.empty:

            QMessageBox.warning(
                self,
                "沒有採購品項",
                "實際採購量全部為 0。"
            )

            return

        warehouse_names = WarehouseService.load_names()

        export_columns = [
            "狀態",
            "產品編號",
            "產品名稱",
            *warehouse_names,
            "三倉庫存合計",
            "本次採購供應商",
            "平均月耗用量",
            "目前庫存",
            "預計到貨",
            "客戶總需求量",
            "客戶直送需求",
            "供應商直送需求",
            "倉庫出貨需求",
            "公司入庫需求",
            "計算用採購需求",
            "需求後剩餘庫存",
            "客戶需求即時缺口",
            "現有可撐月數",
            "需求後可撐月數",
            "總交期天數",
            "交期預估耗用量",
            "安全庫存月數",
            "安全庫存量",
            "倉庫補貨缺口",
            "目標總需求量",
            "原始建議量",
            "MOQ",
            "採購倍數",
            "建議採購量",
            "實際採購量",
            "包裝方式",
            "幣別",
            "單價",
            "計價單位",
            "每箱數量",
            "換算箱數",
            "單箱CBM",
            "本次CBM",
            "商品總價",
            "採購後可撐月數",
            "客戶數",
            "最早到貨日",
        ]

        export_columns = [
            column
            for column
            in export_columns
            if column
            in export_df.columns
        ]

        export_df = (
            export_df[
                export_columns
            ]
        )

        file_path, _ = (
            QFileDialog
            .getSaveFileName(
                self,
                "儲存正式採購清單",
                "正式採購清單.xlsx",
                "Excel Files (*.xlsx)"
            )
        )

        if not file_path:
            return

        if not (
            file_path
            .lower()
            .endswith(
                ".xlsx"
            )
        ):

            file_path += ".xlsx"

        try:

            export_df.to_excel(
                file_path,
                index=False
            )

            QMessageBox.information(
                self,
                "完成",
                f"成功匯出 {len(export_df)} 筆採購品項。"
            )

        except Exception as e:

            QMessageBox.critical(
                self,
                "匯出失敗",
                str(e)
            )