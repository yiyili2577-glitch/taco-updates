import os

import pandas as pd

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QHeaderView,
    QAbstractItemView,
    QComboBox,
    QFrame,
    QLineEdit,
    QSpinBox,
    QCheckBox,
)

from PyQt6.QtCore import Qt

from PyQt6.QtGui import QColor

from services.customer_demand_service import CustomerDemandService
from services.product_alias_service import ProductAliasService
from services.product_master_service import ProductMasterService
from services.customer_demand_store_service import CustomerDemandStoreService
from services.customer_demand_import_service import CustomerDemandImportService
from services.customer_demand_pdf_safe_service import CustomerDemandPdfSafeService
from services.fulfillment_service import FulfillmentService
from ui.fulfillment_dialog import FulfillmentDialog
from services.table_export_service import TableExportService
from services.audit_log_service import AuditLogService
from ui.column_visibility_dialog import ColumnVisibilityDialog
from ui.supplier_tools_installer import SupplierToolsInstaller

from ui.responsive_action_bar import FlowLayout
from ui.page_header import add_page_header


class CustomerDemandPage(QWidget):

    def __init__(self):

        super().__init__()

        self.detail_df = pd.DataFrame()

        self.unmapped_df = pd.DataFrame()

        self.summary_df = pd.DataFrame()

        AuditLogService.log_event("客戶需求", "清除目前畫面需求資料", before={"需求明細": len(self.detail_df) if self.detail_df is not None else 0}, result="成功", severity="警告")
        self.current_pdf_path = ""

        self.pdf_page_count = 0

        self.products = []

        # 批次頁每一列的 ComboBox
        self.mapping_combos = {}

        # 每一列推薦資料
        self.mapping_suggestions = {}

        self.build_ui()

        # V4.3：不覆蓋既有 SupplierPage，也替供應商設定頁自動加上
        # 欄位顯示、Excel / PDF 匯出工具列。
        SupplierToolsInstaller.install_later()

    # =========================================================
    # UI
    # =========================================================

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
            10
        )

        # =====================================================
        # 頁面標題 / 作業說明
        # =====================================================
        add_page_header(
            main_layout,
            "客戶需求",
            "匯入 PDF / Excel 後先解析與驗證，再完成產品對應與履約分流；未確認前不直接寫入採購核心資料。",
        )

        # =====================================================
        # 上方按鈕
        # =====================================================

        toolbar = FlowLayout(h_spacing=7, v_spacing=7)

        self.btn_import_pdf = QPushButton(
            "📄 匯入採購憑單 PDF"
        )
        self.btn_import_pdf.setProperty("buttonRole", "primary")

        self.btn_import_excel = QPushButton(
            "📊 匯入客戶需求 Excel"
        )

        self.btn_reload_mapping = QPushButton(
            "🔄 重新套用產品對照"
        )

        self.btn_fulfillment = QPushButton(
            "🚚 履約／出貨分流"
        )

        self.btn_clear = QPushButton(
            "🧹 清除"
        )

        self.btn_hide_empty = QPushButton(
            "🙈 隱藏空白欄"
        )

        self.btn_columns = QPushButton(
            "⚙ 欄位顯示"
        )

        self.btn_export_excel = QPushButton(
            "📊 匯出 Excel"
        )

        self.btn_export_pdf = QPushButton(
            "📄 匯出 PDF"
        )

        self.file_label = QLabel(
            "尚未匯入 PDF"
        )

        for button in [
            self.btn_import_pdf,
            self.btn_import_excel,
            self.btn_reload_mapping,
            self.btn_fulfillment,
            self.btn_clear,
            self.btn_hide_empty,
            self.btn_columns,
            self.btn_export_excel,
            self.btn_export_pdf,
        ]:

            button.setMinimumHeight(
                38
            )

        toolbar.addWidget(
            self.btn_import_pdf
        )

        toolbar.addWidget(
            self.btn_import_excel
        )

        toolbar.addWidget(
            self.btn_reload_mapping
        )

        toolbar.addWidget(
            self.btn_fulfillment
        )

        toolbar.addWidget(
            self.btn_clear
        )

        toolbar.addWidget(
            self.btn_hide_empty
        )

        toolbar.addWidget(
            self.btn_columns
        )

        toolbar.addStretch()

        toolbar.addWidget(
            self.btn_export_excel
        )

        toolbar.addWidget(
            self.btn_export_pdf
        )

        toolbar.addWidget(
            self.file_label
        )

        main_layout.addLayout(
            toolbar
        )

        # =====================================================
        # 統計區
        # =====================================================

        stats_frame = QFrame()

        stats_frame.setFrameShape(
            QFrame.Shape.StyledPanel
        )

        stats_layout = QHBoxLayout(
            stats_frame
        )

        self.page_count_label = QLabel(
            "PDF頁數：0（Excel匯入時為0）"
        )

        self.detail_count_label = QLabel(
            "需求明細：0"
        )

        self.mapped_count_label = QLabel(
            "已對應：0"
        )

        self.unmapped_count_label = QLabel(
            "未對應：0"
        )

        self.product_count_label = QLabel(
            "產品：0"
        )

        for label in [
            self.page_count_label,
            self.detail_count_label,
            self.mapped_count_label,
            self.unmapped_count_label,
            self.product_count_label,
        ]:

            label.setStyleSheet("""
                QLabel {
                    font-size: 14px;
                    font-weight: 600;
                    padding: 7px 12px;
                }
            """)

            stats_layout.addWidget(
                label
            )

        stats_layout.addStretch()

        main_layout.addWidget(
            stats_frame
        )

        # =====================================================
        # Tabs
        # =====================================================

        self.tabs = QTabWidget()

        self.create_detail_tab()

        self.create_batch_mapping_tab()

        self.create_summary_tab()

        main_layout.addWidget(
            self.tabs,
            1
        )

        # =====================================================
        # Events
        # =====================================================

        self.btn_import_pdf.clicked.connect(
            self.import_pdf
        )

        self.btn_import_excel.clicked.connect(
            self.import_excel
        )

        self.btn_reload_mapping.clicked.connect(
            self.reload_mapping
        )

        self.btn_fulfillment.clicked.connect(
            self.open_fulfillment_dialog
        )

        self.btn_clear.clicked.connect(
            self.clear_data
        )

        self.btn_hide_empty.clicked.connect(
            self.hide_empty_columns
        )

        self.btn_columns.clicked.connect(
            self.choose_columns
        )

        self.btn_export_excel.clicked.connect(
            self.export_excel
        )

        self.btn_export_pdf.clicked.connect(
            self.export_pdf
        )

        self.detail_search.textChanged.connect(
            self.refresh_detail_table
        )

        self.btn_auto_suggest.clicked.connect(
            self.auto_suggest_all
        )

        self.btn_save_all_mappings.clicked.connect(
            self.save_all_mappings
        )

        self.btn_clear_mapping_choices.clicked.connect(
            self.clear_mapping_choices
        )

        self.mapping_search.textChanged.connect(
            self.refresh_batch_mapping_table
        )

        self.refresh_products()

    # =========================================================
    # 欄位顯示 / 匯出
    # =========================================================

    def current_table_for_tools(self):
        index = self.tabs.currentIndex()
        if index == 0:
            return self.detail_table
        if index == 1:
            return self.batch_mapping_table
        return self.summary_table

    def hide_empty_columns(self):
        table = self.current_table_for_tools()
        hidden = TableExportService.hide_empty_columns(table)
        QMessageBox.information(
            self,
            "欄位顯示",
            f"已在目前頁籤暫時隱藏 {hidden} 個完全空白欄位。\n0 / 0.0 不會被當成空白。"
        )

    def choose_columns(self):
        table = self.current_table_for_tools()
        if table.columnCount() == 0:
            QMessageBox.information(self, "沒有欄位", "目前頁籤還沒有可設定的欄位。")
            return
        title_map = {0: "客戶需求明細", 1: "未對應產品", 2: "需求彙總"}
        ColumnVisibilityDialog(
            table, self, f"{title_map.get(self.tabs.currentIndex(), '客戶需求')} - 欄位顯示設定"
        ).exec()

    def export_excel(self):
        TableExportService.export_tables_excel(
            self,
            [
                ("客戶需求明細", self.detail_table),
                ("未對應產品", self.batch_mapping_table),
                ("需求彙總", self.summary_table),
            ],
            "客戶需求.xlsx"
        )

    def export_pdf(self):
        TableExportService.export_tables_pdf(
            self,
            [
                ("客戶需求明細", self.detail_table),
                ("未對應產品", self.batch_mapping_table),
                ("需求彙總", self.summary_table),
            ],
            "客戶需求",
            "客戶需求.pdf"
        )

    # =========================================================
    # ① 客戶需求明細
    # =========================================================

    def create_detail_tab(self):

        page = QWidget()

        layout = QVBoxLayout(
            page
        )

        search_layout = QHBoxLayout()

        search_layout.addWidget(
            QLabel(
                "搜尋："
            )
        )

        self.detail_search = QLineEdit()

        self.detail_search.setPlaceholderText(
            "產品、客戶、採購單號、客戶訂號..."
        )

        search_layout.addWidget(
            self.detail_search,
            1
        )

        layout.addLayout(
            search_layout
        )

        self.detail_table = QTableWidget()

        self.setup_table(
            self.detail_table
        )

        layout.addWidget(
            self.detail_table
        )

        self.tabs.addTab(
            page,
            "① 客戶需求明細"
        )

    # =========================================================
    # ② 批次未對應產品
    # =========================================================

    def create_batch_mapping_tab(self):

        page = QWidget()

        layout = QVBoxLayout(
            page
        )

        # -----------------------------------------------------
        # 說明
        # -----------------------------------------------------

        help_label = QLabel(
            "系統會依 PDF 品名、規格、尺寸與產品主檔自動推薦。"
            "推薦只是輔助，請確認「實際選擇產品」後再儲存。"
        )

        help_label.setWordWrap(
            True
        )

        help_label.setStyleSheet("""
            QLabel {
                color: #555555;
                font-size: 13px;
            }
        """)

        layout.addWidget(
            help_label
        )

        # -----------------------------------------------------
        # 工具列
        # -----------------------------------------------------

        toolbar = FlowLayout(h_spacing=7, v_spacing=7)

        self.btn_auto_suggest = QPushButton(
            "🤖 全部自動推薦"
        )

        self.btn_auto_suggest.setMinimumHeight(
            40
        )

        toolbar.addWidget(
            self.btn_auto_suggest
        )

        toolbar.addWidget(
            QLabel(
                "自動帶入門檻："
            )
        )

        self.suggest_threshold = QSpinBox()

        self.suggest_threshold.setRange(
            0,
            100
        )

        self.suggest_threshold.setValue(
            65
        )

        self.suggest_threshold.setSuffix(
            "%"
        )

        self.suggest_threshold.setToolTip(
            "推薦分數達到此門檻時，"
            "系統會自動把推薦產品放入實際選擇欄。"
        )

        toolbar.addWidget(
            self.suggest_threshold
        )

        self.check_only_high_confidence = QCheckBox(
            "只自動選高可信度"
        )

        self.check_only_high_confidence.setChecked(
            True
        )

        toolbar.addWidget(
            self.check_only_high_confidence
        )

        toolbar.addSpacing(
            20
        )

        toolbar.addWidget(
            QLabel(
                "搜尋："
            )
        )

        self.mapping_search = QLineEdit()

        self.mapping_search.setPlaceholderText(
            "搜尋 PDF 品名..."
        )

        self.mapping_search.setMaximumWidth(
            300
        )

        toolbar.addWidget(
            self.mapping_search
        )

        toolbar.addStretch()

        self.btn_clear_mapping_choices = QPushButton(
            "🧹 清空選擇"
        )

        self.btn_clear_mapping_choices.setMinimumHeight(
            40
        )

        toolbar.addWidget(
            self.btn_clear_mapping_choices
        )

        self.btn_save_all_mappings = QPushButton(
            "💾 儲存全部產品對應"
        )

        self.btn_save_all_mappings.setMinimumHeight(
            40
        )

        self.btn_save_all_mappings.setStyleSheet("""
            QPushButton {
                background-color: #198754;
                color: white;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 5px;
            }

            QPushButton:hover {
                background-color: #157347;
            }
        """)

        toolbar.addWidget(
            self.btn_save_all_mappings
        )

        layout.addLayout(
            toolbar
        )

        # -----------------------------------------------------
        # 小提示
        # -----------------------------------------------------

        self.mapping_info_label = QLabel(
            "尚未有未對應產品"
        )

        self.mapping_info_label.setStyleSheet("""
            QLabel {
                padding: 5px 0;
                color: #555555;
            }
        """)

        layout.addWidget(
            self.mapping_info_label
        )

        # -----------------------------------------------------
        # 批次表格
        # -----------------------------------------------------

        self.batch_mapping_table = QTableWidget()

        self.batch_mapping_table.setAlternatingRowColors(
            True
        )

        self.batch_mapping_table.setSelectionBehavior(
            QAbstractItemView
            .SelectionBehavior
            .SelectRows
        )

        self.batch_mapping_table.setEditTriggers(
            QAbstractItemView
            .EditTrigger
            .NoEditTriggers
        )

        self.batch_mapping_table.verticalHeader().setDefaultSectionSize(
            42
        )

        self.batch_mapping_table.horizontalHeader().setSectionResizeMode(
            QHeaderView
            .ResizeMode
            .Interactive
        )

        layout.addWidget(
            self.batch_mapping_table,
            1
        )

        self.tabs.addTab(
            page,
            "② 未對應產品／批次對應"
        )

    # =========================================================
    # ③ 需求彙總
    # =========================================================

    def create_summary_tab(self):

        page = QWidget()

        layout = QVBoxLayout(
            page
        )

        label = QLabel(
            "需求彙總只會計算已完成產品編號對應，"
            "並通過 PDF 欄位驗證的資料。"
        )

        label.setWordWrap(
            True
        )

        layout.addWidget(
            label
        )

        self.summary_table = QTableWidget()

        self.setup_table(
            self.summary_table
        )

        layout.addWidget(
            self.summary_table
        )

        self.tabs.addTab(
            page,
            "③ 需求彙總"
        )

    # =========================================================
    # Table 共用設定
    # =========================================================

    def setup_table(
        self,
        table
    ):

        table.setAlternatingRowColors(
            True
        )

        table.setSelectionBehavior(
            QAbstractItemView
            .SelectionBehavior
            .SelectRows
        )

        table.setSelectionMode(
            QAbstractItemView
            .SelectionMode
            .SingleSelection
        )

        table.setEditTriggers(
            QAbstractItemView
            .EditTrigger
            .NoEditTriggers
        )

        table.horizontalHeader().setSectionResizeMode(
            QHeaderView
            .ResizeMode
            .Interactive
        )

        table.verticalHeader().setDefaultSectionSize(
            30
        )

    # =========================================================
    # 產品主檔
    # =========================================================

    def refresh_products(self):

        try:

            products = (
                ProductMasterService
                .load_products()
            )

            if not isinstance(
                products,
                list
            ):

                products = []

            self.products = products

        except Exception:

            self.products = []

    # =========================================================
    # Product Combo
    # =========================================================

    def create_product_combo(
        self,
        selected_product_no=""
    ):

        combo = QComboBox()

        combo.setEditable(
            True
        )

        combo.setInsertPolicy(
            QComboBox
            .InsertPolicy
            .NoInsert
        )

        combo.setMinimumWidth(
            320
        )

        combo.addItem(
            "— 尚未選擇 —",
            ""
        )

        selected_index = 0

        for index, product in enumerate(
            self.products,
            start=1
        ):

            product_no = str(
                product.get(
                    "產品編號",
                    ""
                )
            ).strip()

            product_name = str(
                product.get(
                    "產品名稱",
                    product.get(
                        "品名",
                        ""
                    )
                )
            ).strip()

            category = str(
                product.get(
                    "品項分類",
                    ""
                )
            ).strip()

            if not product_no:
                continue

            display_parts = [
                product_no,
                product_name,
            ]

            if category:

                display_parts.append(
                    category
                )

            display = " ｜ ".join(
                part
                for part
                in display_parts
                if part
            )

            combo.addItem(
                display,
                product_no
            )

            if (
                selected_product_no
                and
                product_no
                ==
                selected_product_no
            ):

                selected_index = (
                    combo.count()
                    -
                    1
                )

        combo.setCurrentIndex(
            selected_index
        )

        combo.setMaxVisibleItems(
            20
        )

        return combo

    # =========================================================
    # 匯入 PDF
    # =========================================================

    def import_pdf(self):

        file_path, _ = (
            QFileDialog
            .getOpenFileName(
                self,
                "選擇採購憑單 PDF",
                "",
                "PDF Files (*.pdf)"
            )
        )

        if not file_path:
            return

        try:

            self.file_label.setText(
                "正在讀取 PDF..."
            )

            try:
                result = (
                    CustomerDemandService
                    .read_pdf(
                        file_path
                    )
                )
            except Exception as primary_error:
                # V4.2：正常模式整份失敗時，改逐頁安全模式。
                result = CustomerDemandPdfSafeService.read_pdf(file_path)
                result["primary_error"] = str(primary_error)

            self.current_pdf_path = (
                file_path
            )

            self.pdf_page_count = int(
                result.get(
                    "pages",
                    0
                )
            )

            self.detail_df = (
                result[
                    "detail_df"
                ]
            )

            self.detail_df = CustomerDemandImportService.enrich_detail_df(
                self.detail_df
            )

            self.file_label.setText(
                result.get(
                    "source_file",
                    file_path
                )
            )

            self.rebuild_all()
            AuditLogService.log_event("客戶需求", "匯入 PDF", record_id=file_path, after={"需求明細": len(self.detail_df), "未對應產品": len(self.unmapped_df)}, result="成功")

            page_errors = (
                result.get(
                    "page_errors",
                    []
                )
            )

            message = (
                f"PDF 共 {self.pdf_page_count} 頁。\n"
                f"需求明細：{len(self.detail_df)} 筆。\n"
                f"未對應產品：{len(self.unmapped_df)} 種。"
            )

            if page_errors:

                message += (
                    f"\n\n另有 {len(page_errors)} 頁解析警告；其他頁仍已保留。"
                )

            if result.get("safe_mode"):
                message += "\n\n本次使用 PDF 逐頁安全模式完成匯入。"

            QMessageBox.information(
                self,
                "PDF 匯入完成",
                message
            )

        except Exception as e:

            self.file_label.setText(
                "❌ PDF 讀取失敗"
            )

            QMessageBox.critical(
                self,
                "PDF 需求匯入失敗",
                str(e)
            )

    # =========================================================
    # 匯入 Excel
    # =========================================================

    def import_excel(self):

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "選擇客戶需求 Excel",
            "",
            "Excel Files (*.xlsx *.xls *.xlsm)"
        )

        if not file_path:
            return

        try:
            self.file_label.setText("正在讀取 Excel...")
            result = CustomerDemandImportService.read_excel(file_path)
            self.current_pdf_path = file_path
            self.pdf_page_count = 0
            self.detail_df = result["detail_df"]
            self.file_label.setText(result.get("source_file", file_path))
            self.rebuild_all()
            AuditLogService.log_event("客戶需求", "匯入 Excel", record_id=file_path, after={"需求明細": len(self.detail_df), "未對應產品": len(self.unmapped_df), "讀取方式": result.get("read_method", "")}, result="成功")
            read_method = result.get("read_method", "")
            sheet_name = result.get("sheet_name", "")
            QMessageBox.information(
                self,
                "Excel 匯入完成",
                f"需求明細：{len(self.detail_df)} 筆。\n"
                f"未對應產品：{len(self.unmapped_df)} 種。\n"
                f"讀取方式：{read_method or '自動'}\n"
                f"工作表：{sheet_name or '-'}"
            )
        except Exception as e:
            self.file_label.setText("❌ Excel 讀取失敗")
            QMessageBox.critical(self, "Excel 需求匯入失敗", str(e))

    # =========================================================
    # 全部重新計算
    # =========================================================

    def rebuild_all(self):

        self.refresh_products()

        if (
            self.detail_df is None
            or
            self.detail_df.empty
        ):

            self.unmapped_df = (
                pd.DataFrame()
            )

            self.summary_df = (
                pd.DataFrame()
            )

            self.refresh_all_tables()

            self.refresh_cards()

            return

        self.detail_df = CustomerDemandImportService.enrich_detail_df(
            self.detail_df
        )

        self.detail_df = (
            ProductAliasService
            .apply_aliases(
                self.detail_df
            )
        )

        # V4.1：Excel 若本身已有 ERP 產品編號，直接以產品主檔對應。
        # 必須放在 Alias 後面，因為舊版 apply_aliases() 會重建「產品編號」欄。
        self.detail_df = CustomerDemandImportService.apply_product_master_mapping(
            self.detail_df,
            self.products
        )

        self.detail_df = (
            CustomerDemandService
            .attach_product_master(
                self.detail_df
            )
        )

        # 套用客戶需求履約／出貨來源設定。
        self.detail_df = FulfillmentService.apply_routes(
            self.detail_df
        )

        # 將原始品名規格拆解欄位移到前面，ERP 產品編號仍保留作為系統主鍵。
        preferred_detail = [
            "驗證狀態", "驗證問題", "自動修正", "對應狀態",
            "PDF頁碼", "採購單號", "採購日期", "採購廠商", "客戶", "客戶訂號",
            "PDF品名規格", "原始產品編號", "需求產品名稱", "規格", "材質", "尺寸", "基重",
            "產品編號", "產品名稱", "品項分類", "數量", "單位", "需求單位", "箱數", "每箱數量",
            "單價", "幣別", "總價", "包裝方式", "紙箱規格", "體積CBM", "到貨日期",
            "配送類型", "履約方式", "出貨倉", "配送地址", "配送內容", "來源類型", "來源檔案"
        ]
        ordered = [c for c in preferred_detail if c in self.detail_df.columns]
        ordered += [c for c in self.detail_df.columns if c not in ordered]
        self.detail_df = self.detail_df[ordered]

        self.unmapped_df = (
            CustomerDemandService
            .get_unmapped_products(
                self.detail_df
            )
        )

        self.summary_df = (
            CustomerDemandService
            .summarize_demand(
                self.detail_df
            )
        )

        # 新增履約分流彙總：供應商直送／倉庫出貨／公司入庫。
        fulfillment_summary = FulfillmentService.summarize(
            self.detail_df
        )
        if self.summary_df is not None and not self.summary_df.empty and not fulfillment_summary.empty:
            self.summary_df = self.summary_df.merge(
                fulfillment_summary,
                on="產品編號",
                how="left"
            )
            # pandas 3.x 已移除 to_numeric(errors="ignore")。
            # 履約彙總除了產品編號外都應是數值欄，因此安全轉成數值；
            # 無法轉換者以 0 處理，避免 PDF / Excel 匯入完成後在 rebuild_all() 中斷。
            for col in fulfillment_summary.columns:
                if col != "產品編號" and col in self.summary_df.columns:
                    self.summary_df[col] = pd.to_numeric(
                        self.summary_df[col], errors="coerce"
                    ).fillna(0)

        CustomerDemandStoreService.save_snapshot(
            self.summary_df,
            self.detail_df,
            (
                os.path.basename(
                    self.current_pdf_path
                )
                if self.current_pdf_path
                else ""
            )
        )

        self.refresh_all_tables()

        self.refresh_cards()

    # =========================================================
    # 更新所有表格
    # =========================================================

    def refresh_all_tables(self):

        self.refresh_detail_table()

        self.refresh_batch_mapping_table()

        self.display_dataframe(
            self.summary_table,
            self.summary_df,
            mode="summary"
        )

    # =========================================================
    # 明細搜尋
    # =========================================================

    def refresh_detail_table(self):

        if (
            self.detail_df is None
            or
            self.detail_df.empty
        ):

            self.display_dataframe(
                self.detail_table,
                pd.DataFrame(),
                mode="detail"
            )

            return

        keyword = (
            self.detail_search
            .text()
            .strip()
            .lower()
        )

        if not keyword:

            display_df = (
                self.detail_df
            )

        else:

            mask = (
                self.detail_df
                .astype(str)
                .apply(
                    lambda row:
                    row.str.lower()
                    .str.contains(
                        keyword,
                        regex=False
                    )
                    .any(),
                    axis=1
                )
            )

            display_df = (
                self.detail_df[
                    mask
                ]
            )

        self.display_dataframe(
            self.detail_table,
            display_df,
            mode="detail"
        )

    # =========================================================
    # 一般 dataframe table
    # =========================================================

    def display_dataframe(
        self,
        table,
        df,
        mode=""
    ):

        table.clear()

        if (
            df is None
            or
            df.empty
        ):

            table.setRowCount(
                0
            )

            table.setColumnCount(
                0
            )

            return

        table.setRowCount(
            len(df)
        )

        table.setColumnCount(
            len(df.columns)
        )

        table.setHorizontalHeaderLabels(
            [
                str(column)
                for column
                in df.columns
            ]
        )

        for row_index in range(
            len(df)
        ):

            for column_index in range(
                len(df.columns)
            ):

                column_name = (
                    df.columns[
                        column_index
                    ]
                )

                value = (
                    df.iloc[
                        row_index,
                        column_index
                    ]
                )

                try:

                    if pd.isna(value):
                        value = ""

                except Exception:
                    pass

                item = QTableWidgetItem(
                    str(value)
                )

                if mode == "detail":

                    validation_status = str(
                        df.iloc[
                            row_index
                        ].get(
                            "驗證狀態",
                            ""
                        )
                    )

                    mapping_status = str(
                        df.iloc[
                            row_index
                        ].get(
                            "對應狀態",
                            ""
                        )
                    )

                    if (
                        "需要人工確認"
                        in validation_status
                    ):

                        item.setBackground(
                            QColor(
                                "#FFD9D9"
                            )
                        )

                    elif (
                        "自動修正"
                        in validation_status
                    ):

                        item.setBackground(
                            QColor(
                                "#FFF4CC"
                            )
                        )

                    elif (
                        "未對應"
                        in mapping_status
                    ):

                        item.setBackground(
                            QColor(
                                "#FFECEC"
                            )
                        )

                table.setItem(
                    row_index,
                    column_index,
                    item
                )

        table.resizeColumnsToContents()

    # =========================================================
    # 批次未對應表
    # =========================================================

    def refresh_batch_mapping_table(self):

        self.mapping_combos = {}

        if (
            self.unmapped_df is None
            or
            self.unmapped_df.empty
        ):

            self.batch_mapping_table.clear()

            self.batch_mapping_table.setRowCount(
                0
            )

            self.batch_mapping_table.setColumnCount(
                0
            )

            self.mapping_info_label.setText(
                "目前沒有可以進行產品對應的未對應品項。"
            )

            return

        keyword = (
            self.mapping_search
            .text()
            .strip()
            .lower()
        )

        if keyword:

            working_df = (
                self.unmapped_df[
                    self.unmapped_df[
                        "PDF品名規格"
                    ]
                    .astype(str)
                    .str.lower()
                    .str.contains(
                        keyword,
                        regex=False
                    )
                ]
                .copy()
            )

        else:

            working_df = (
                self.unmapped_df
                .copy()
            )

        working_df = (
            working_df
            .reset_index(
                drop=True
            )
        )

        columns = [
            "PDF品名規格",
            "出現次數",
            "需求總量",
            "推薦分數",
            "系統推薦",
            "實際選擇產品",
            "狀態",
        ]

        self.batch_mapping_table.clear()

        self.batch_mapping_table.setRowCount(
            len(
                working_df
            )
        )

        self.batch_mapping_table.setColumnCount(
            len(columns)
        )

        self.batch_mapping_table.setHorizontalHeaderLabels(
            columns
        )

        threshold = (
            self.suggest_threshold
            .value()
        )

        high_count = 0

        medium_count = 0

        low_count = 0

        for row_index in range(
            len(
                working_df
            )
        ):

            pdf_name = str(
                working_df
                .iloc[
                    row_index
                ]
                .get(
                    "PDF品名規格",
                    ""
                )
            )

            occurrence = (
                working_df
                .iloc[
                    row_index
                ]
                .get(
                    "出現次數",
                    ""
                )
            )

            demand_qty = (
                working_df
                .iloc[
                    row_index
                ]
                .get(
                    "需求總量",
                    ""
                )
            )

            # -------------------------------------------------
            # 若之前已算過推薦就沿用
            # -------------------------------------------------

            suggestion = (
                self.mapping_suggestions
                .get(
                    pdf_name
                )
            )

            if suggestion is None:

                suggestion = {
                    "產品編號":
                        "",

                    "產品名稱":
                        "",

                    "分數":
                        0,
                }

            score = float(
                suggestion.get(
                    "分數",
                    0
                )
                or
                0
            )

            recommended_no = str(
                suggestion.get(
                    "產品編號",
                    ""
                )
            ).strip()

            recommended_name = str(
                suggestion.get(
                    "產品名稱",
                    ""
                )
            ).strip()

            # -------------------------------------------------
            # PDF Name
            # -------------------------------------------------

            pdf_item = QTableWidgetItem(
                pdf_name
            )

            self.batch_mapping_table.setItem(
                row_index,
                0,
                pdf_item
            )

            # -------------------------------------------------
            # 次數
            # -------------------------------------------------

            self.batch_mapping_table.setItem(
                row_index,
                1,
                QTableWidgetItem(
                    str(
                        occurrence
                    )
                )
            )

            # -------------------------------------------------
            # Demand
            # -------------------------------------------------

            self.batch_mapping_table.setItem(
                row_index,
                2,
                QTableWidgetItem(
                    str(
                        demand_qty
                    )
                )
            )

            # -------------------------------------------------
            # Score
            # -------------------------------------------------

            score_item = QTableWidgetItem(
                (
                    f"{score:.1f}%"
                    if score > 0
                    else ""
                )
            )

            self.batch_mapping_table.setItem(
                row_index,
                3,
                score_item
            )

            # -------------------------------------------------
            # Recommendation
            # -------------------------------------------------

            recommendation_text = ""

            if recommended_no:

                recommendation_text = (
                    f"{recommended_no}"
                )

                if recommended_name:

                    recommendation_text += (
                        f" ｜ {recommended_name}"
                    )

            self.batch_mapping_table.setItem(
                row_index,
                4,
                QTableWidgetItem(
                    recommendation_text
                )
            )

            # -------------------------------------------------
            # Combo
            # -------------------------------------------------

            auto_selected_product_no = ""

            if (
                recommended_no
                and
                score
                >=
                threshold
            ):

                auto_selected_product_no = (
                    recommended_no
                )

            combo = (
                self.create_product_combo(
                    auto_selected_product_no
                )
            )

            combo.setProperty(
                "pdf_name",
                pdf_name
            )

            self.batch_mapping_table.setCellWidget(
                row_index,
                5,
                combo
            )

            self.mapping_combos[
                pdf_name
            ] = combo

            # -------------------------------------------------
            # Status
            # -------------------------------------------------

            if score >= 85:

                status = (
                    "🟢 高可信度"
                )

                status_color = (
                    "#DFF4E5"
                )

                high_count += 1

            elif score >= threshold:

                status = (
                    "🟡 建議確認"
                )

                status_color = (
                    "#FFF4CC"
                )

                medium_count += 1

            elif score > 0:

                status = (
                    "🔴 低可信度"
                )

                status_color = (
                    "#FFD9D9"
                )

                low_count += 1

            else:

                status = (
                    "⚪ 尚未推薦"
                )

                status_color = (
                    "#F2F2F2"
                )

            status_item = QTableWidgetItem(
                status
            )

            status_item.setBackground(
                QColor(
                    status_color
                )
            )

            self.batch_mapping_table.setItem(
                row_index,
                6,
                status_item
            )

        header = (
            self.batch_mapping_table
            .horizontalHeader()
        )

        header.setSectionResizeMode(
            0,
            QHeaderView
            .ResizeMode
            .Stretch
        )

        header.setSectionResizeMode(
            1,
            QHeaderView
            .ResizeMode
            .ResizeToContents
        )

        header.setSectionResizeMode(
            2,
            QHeaderView
            .ResizeMode
            .ResizeToContents
        )

        header.setSectionResizeMode(
            3,
            QHeaderView
            .ResizeMode
            .ResizeToContents
        )

        header.setSectionResizeMode(
            4,
            QHeaderView
            .ResizeMode
            .Stretch
        )

        header.setSectionResizeMode(
            5,
            QHeaderView
            .ResizeMode
            .Stretch
        )

        header.setSectionResizeMode(
            6,
            QHeaderView
            .ResizeMode
            .ResizeToContents
        )

        self.mapping_info_label.setText(
            (
                f"目前未對應：{len(self.unmapped_df)} 種　"
                f"｜ 高可信度：{high_count}　"
                f"｜ 建議確認：{medium_count}　"
                f"｜ 低可信度：{low_count}"
            )
        )

    # =========================================================
    # 全部自動推薦
    # =========================================================

    def auto_suggest_all(self):

        if (
            self.unmapped_df is None
            or
            self.unmapped_df.empty
        ):

            QMessageBox.information(
                self,
                "沒有未對應產品",
                "目前沒有可以推薦的未對應產品。"
            )

            return

        self.refresh_products()

        if not self.products:

            QMessageBox.warning(
                self,
                "產品主檔為空",
                "目前產品主檔沒有產品資料。\n"
                "請先到供應商設定／產品主檔匯入產品。"
            )

            return

        self.mapping_suggestions = {}

        for _, row in (
            self.unmapped_df
            .iterrows()
        ):

            pdf_name = str(
                row.get(
                    "PDF品名規格",
                    ""
                )
            ).strip()

            if not pdf_name:
                continue

            suggestion = (
                ProductAliasService
                .suggest_product(
                    pdf_name,
                    self.products
                )
            )

            self.mapping_suggestions[
                pdf_name
            ] = suggestion

        self.refresh_batch_mapping_table()

        QMessageBox.information(
            self,
            "自動推薦完成",
            (
                f"已分析 {len(self.mapping_suggestions)} 個"
                "未對應 PDF 品名。\n\n"
                "綠色代表可信度較高；"
                "黃色請確認；紅色建議人工選擇。"
            )
        )

    # =========================================================
    # 清空 Combo
    # =========================================================

    def clear_mapping_choices(self):

        for combo in (
            self.mapping_combos
            .values()
        ):

            combo.setCurrentIndex(
                0
            )

    # =========================================================
    # 全部儲存
    # =========================================================

    def save_all_mappings(self):

        if not self.mapping_combos:

            QMessageBox.information(
                self,
                "沒有對應資料",
                "目前沒有可以儲存的產品對應。"
            )

            return

        mappings = {}

        skipped = 0

        for pdf_name, combo in (
            self.mapping_combos
            .items()
        ):

            product_no = str(
                combo.currentData()
                or
                ""
            ).strip()

            if not product_no:

                skipped += 1
                continue

            mappings[
                pdf_name
            ] = product_no

        if not mappings:

            QMessageBox.warning(
                self,
                "尚未選擇產品",
                "目前沒有任何一列選擇產品編號。"
            )

            return

        # -----------------------------------------------------
        # 顯示部分範例
        # -----------------------------------------------------

        preview_lines = []

        for index, (
            pdf_name,
            product_no
        ) in enumerate(
            mappings.items()
        ):

            if index >= 8:
                break

            preview_lines.append(
                f"{pdf_name}\n→ {product_no}"
            )

        preview = "\n\n".join(
            preview_lines
        )

        if len(
            mappings
        ) > 8:

            preview += (
                f"\n\n……另外還有 {len(mappings) - 8} 筆"
            )

        confirm = (
            QMessageBox.question(
                self,
                "確認批次產品對應",
                (
                    f"準備儲存 {len(mappings)} 筆產品對應。\n"
                    f"未選擇：{skipped} 筆。\n\n"
                    f"{preview}\n\n"
                    "確定儲存嗎？"
                ),
                QMessageBox
                .StandardButton
                .Yes
                |
                QMessageBox
                .StandardButton
                .No
            )
        )

        if (
            confirm
            !=
            QMessageBox
            .StandardButton
            .Yes
        ):

            return

        try:

            saved_count = (
                ProductAliasService
                .set_aliases_bulk(
                    mappings
                )
            )

            # 重新套用 Alias
            self.rebuild_all()
            AuditLogService.log_event("客戶需求", "批次產品對應", after={"儲存筆數": saved_count, "對應": mappings}, result="成功")

            QMessageBox.information(
                self,
                "產品對應完成",
                (
                    f"成功儲存 {saved_count} 筆產品對應。\n\n"
                    "PDF 明細與需求彙總已重新計算。"
                )
            )

        except Exception as e:

            QMessageBox.critical(
                self,
                "批次儲存失敗",
                str(e)
            )

    # =========================================================
    # 履約／出貨分流
    # =========================================================

    def open_fulfillment_dialog(self):

        if self.detail_df is None or self.detail_df.empty:
            QMessageBox.information(
                self,
                "尚無需求資料",
                "請先匯入 PDF 或 Excel 客戶需求資料。"
            )
            return

        dialog = FulfillmentDialog(
            self.detail_df,
            self
        )

        if dialog.exec() == dialog.DialogCode.Accepted:
            self.rebuild_all()
            AuditLogService.log_event("客戶需求", "修改履約／出貨分流", after={"需求明細": len(self.detail_df)}, result="成功")
            QMessageBox.information(
                self,
                "履約設定已套用",
                "需求彙總與採購 Snapshot 已重新計算。"
            )

    # =========================================================
    # 重新套用
    # =========================================================

    def reload_mapping(self):

        if (
            self.detail_df is None
            or
            self.detail_df.empty
        ):

            QMessageBox.information(
                self,
                "尚未匯入 PDF",
                "請先匯入採購憑單 PDF。"
            )

            return

        self.mapping_suggestions = {}

        self.rebuild_all()

        QMessageBox.information(
            self,
            "重新套用完成",
            "已重新讀取產品主檔與產品對應資料。"
        )

    # =========================================================
    # Cards
    # =========================================================

    def refresh_cards(self):

        self.page_count_label.setText(
            f"PDF頁數：{self.pdf_page_count}"
        )

        detail_count = (
            len(
                self.detail_df
            )
            if self.detail_df is not None
            else 0
        )

        mapped_count = 0

        if (
            self.detail_df is not None
            and
            not self.detail_df.empty
            and
            "產品編號"
            in self.detail_df.columns
        ):

            mapped_count = int(
                (
                    self.detail_df[
                        "產品編號"
                    ]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    !=
                    ""
                )
                .sum()
            )

        unmapped_count = (
            len(
                self.unmapped_df
            )
            if self.unmapped_df is not None
            else 0
        )

        product_count = (
            len(
                self.summary_df
            )
            if self.summary_df is not None
            else 0
        )

        self.detail_count_label.setText(
            f"需求明細：{detail_count}"
        )

        self.mapped_count_label.setText(
            f"已對應：{mapped_count}"
        )

        self.unmapped_count_label.setText(
            f"未對應：{unmapped_count}"
        )

        self.product_count_label.setText(
            f"產品：{product_count}"
        )

    # =========================================================
    # Clear
    # =========================================================

    def clear_data(self):

        self.detail_df = pd.DataFrame()

        self.unmapped_df = pd.DataFrame()

        self.summary_df = pd.DataFrame()

        self.mapping_suggestions = {}

        self.mapping_combos = {}

        self.current_pdf_path = ""

        self.pdf_page_count = 0

        CustomerDemandStoreService.clear_snapshot()

        self.file_label.setText(
            "尚未匯入 PDF"
        )

        self.refresh_all_tables()

        self.refresh_cards()