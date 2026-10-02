import os

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QHeaderView,
    QAbstractItemView,
    QFileDialog,
    QCheckBox,
    QComboBox,
    QStackedWidget,
    QLineEdit,
    QScrollArea,
    QFrame,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
)

from PyQt6.QtCore import (
    Qt,
    QSize,
)

from PyQt6.QtGui import (
    QPixmap,
)

from services.supplier_service import SupplierService
from services.vendor_master_service import VendorMasterService
from services.product_master_service import ProductMasterService
from ui.page_header import add_page_header


# =========================================================
# 單筆產品新增 / 編輯
# =========================================================

class ProductDialog(QDialog):

    def __init__(
        self,
        parent=None,
        product=None,
        default_category=""
    ):

        super().__init__(
            parent
        )

        self.setWindowTitle(
            "產品資料"
        )

        self.resize(
            550,
            320
        )

        product = (
            product
            or
            {}
        )

        layout = QVBoxLayout(
            self
        )

        form = QFormLayout()

        self.product_no_input = (
            QLineEdit()
        )

        self.product_name_input = (
            QLineEdit()
        )

        self.category_combo = (
            QComboBox()
        )

        self.category_combo.addItems(
            VendorMasterService
            .load_categories()
        )

        self.spec_input = (
            QLineEdit()
        )

        self.packing_input = (
            QLineEdit()
        )

        self.product_no_input.setText(
            str(
                product.get(
                    "產品編號",
                    ""
                )
            )
        )

        self.product_name_input.setText(
            str(
                product.get(
                    "產品名稱",
                    ""
                )
            )
        )

        category = str(
            product.get(
                "品項分類",
                ""
            )
            or
            default_category
        )

        if (
            category
            and
            self.category_combo.findText(
                category
            )
            >= 0
        ):

            self.category_combo.setCurrentText(
                category
            )

        self.spec_input.setText(
            str(
                product.get(
                    "規格",
                    ""
                )
            )
        )

        self.packing_input.setText(
            str(
                product.get(
                    "包裝方式",
                    ""
                )
            )
        )

        form.addRow(
            "產品編號",
            self.product_no_input
        )

        form.addRow(
            "產品名稱",
            self.product_name_input
        )

        form.addRow(
            "品項分類",
            self.category_combo
        )

        form.addRow(
            "規格",
            self.spec_input
        )

        form.addRow(
            "包裝方式",
            self.packing_input
        )

        layout.addLayout(
            form
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox
            .StandardButton
            .Save
            |
            QDialogButtonBox
            .StandardButton
            .Cancel
        )

        buttons.accepted.connect(
            self.accept
        )

        buttons.rejected.connect(
            self.reject
        )

        layout.addWidget(
            buttons
        )

    def get_data(self):

        return {
            "產品編號":
                self.product_no_input
                .text()
                .strip(),

            "產品名稱":
                self.product_name_input
                .text()
                .strip(),

            "品項分類":
                self.category_combo
                .currentText()
                .strip(),

            "規格":
                self.spec_input
                .text()
                .strip(),

            "包裝方式":
                self.packing_input
                .text()
                .strip(),
        }


# =========================================================
# 某品項底下的產品主檔
# =========================================================

class CategoryProductsDialog(QDialog):

    def __init__(
        self,
        category,
        parent=None
    ):

        super().__init__(
            parent
        )

        self.category = (
            category
        )

        self.current_products = []

        self.setWindowTitle(
            f"{category}－產品主檔"
        )

        self.resize(
            1050,
            650
        )

        self.build_ui()

        self.refresh_table()

    # =====================================================
    # UI
    # =====================================================

    def build_ui(self):

        layout = QVBoxLayout(
            self
        )

        # ===============================================
        # Toolbar
        # ===============================================

        toolbar = QHBoxLayout()

        self.search_input = (
            QLineEdit()
        )

        self.search_input.setPlaceholderText(
            "搜尋產品編號或產品名稱"
        )

        self.btn_import_excel = QPushButton(
            "📥 批次匯入 Excel"
        )

        self.btn_add = QPushButton(
            "＋ 新增產品"
        )

        self.btn_edit = QPushButton(
            "✏ 編輯"
        )

        self.btn_delete = QPushButton(
            "🗑 刪除"
        )

        toolbar.addWidget(
            self.search_input,
            1
        )

        toolbar.addWidget(
            self.btn_import_excel
        )

        toolbar.addWidget(
            self.btn_add
        )

        toolbar.addWidget(
            self.btn_edit
        )

        toolbar.addWidget(
            self.btn_delete
        )

        layout.addLayout(
            toolbar
        )

        # ===============================================
        # Hint
        # ===============================================

        hint = QLabel(
            "可一次選取多份訂購單 Excel。"
            "系統會自動尋找「產品編號／品名／規格／包裝方式」，"
            f"並先歸類到「{self.category}」。"
        )

        hint.setWordWrap(
            True
        )

        hint.setStyleSheet("""
            color: #666666;
            padding: 4px;
        """)

        layout.addWidget(
            hint
        )

        # ===============================================
        # Table
        # ===============================================

        self.table = QTableWidget()

        self.table.setColumnCount(
            5
        )

        self.table.setHorizontalHeaderLabels(
            [
                "產品編號",
                "產品名稱",
                "品項分類",
                "規格",
                "包裝方式",
            ]
        )

        self.table.setSelectionBehavior(
            QAbstractItemView
            .SelectionBehavior
            .SelectRows
        )

        self.table.setSelectionMode(
            QAbstractItemView
            .SelectionMode
            .SingleSelection
        )

        self.table.setEditTriggers(
            QAbstractItemView
            .EditTrigger
            .NoEditTriggers
        )

        header = (
            self.table
            .horizontalHeader()
        )

        header.setSectionResizeMode(
            QHeaderView
            .ResizeMode
            .Interactive
        )

        header.setStretchLastSection(
            True
        )

        self.table.setColumnWidth(
            0,
            180
        )

        self.table.setColumnWidth(
            1,
            320
        )

        self.table.setColumnWidth(
            2,
            120
        )

        self.table.setColumnWidth(
            3,
            180
        )

        layout.addWidget(
            self.table
        )

        # events
        self.search_input.textChanged.connect(
            self.refresh_table
        )

        self.btn_import_excel.clicked.connect(
            self.import_excel_files
        )

        self.btn_add.clicked.connect(
            self.add_product
        )

        self.btn_edit.clicked.connect(
            self.edit_product
        )

        self.btn_delete.clicked.connect(
            self.delete_product
        )

    # =====================================================
    # Import multiple
    # =====================================================

    def import_excel_files(self):

        file_paths, _ = (
            QFileDialog
            .getOpenFileNames(
                self,
                "選擇產品訂購單 Excel（可複選）",
                "",
                "Excel Files (*.xlsx *.xlsm)"
            )
        )

        if not file_paths:
            return

        try:

            result = (
                ProductMasterService
                .import_from_excels(
                    file_paths,
                    default_category=self.category
                )
            )

            self.refresh_table()

            error_count = len(
                result[
                    "errors"
                ]
            )

            message = (
                f"成功讀取 "
                f"{len(result['successful_files'])} "
                f"個檔案。\n\n"
                f"本次抓到 "
                f"{result['imported_count']} "
                f"個不同產品編號。"
            )

            if error_count > 0:

                message += (
                    f"\n\n另有 "
                    f"{error_count} "
                    f"個檔案無法讀取。"
                )

            QMessageBox.information(
                self,
                "批次匯入完成",
                message
            )

        except Exception as e:

            QMessageBox.critical(
                self,
                "批次匯入失敗",
                str(e)
            )

    # =====================================================
    # Filter
    # =====================================================

    def get_filtered_products(self):

        products = (
            ProductMasterService
            .get_products_by_category(
                self.category
            )
        )

        keyword = (
            self.search_input
            .text()
            .strip()
            .lower()
        )

        if not keyword:

            return products

        result = []

        for product in products:

            searchable = (
                str(
                    product.get(
                        "產品編號",
                        ""
                    )
                )
                +
                " "
                +
                str(
                    product.get(
                        "產品名稱",
                        ""
                    )
                )
            ).lower()

            if keyword in searchable:

                result.append(
                    product
                )

        return result

    # =====================================================
    # Table
    # =====================================================

    def refresh_table(self):

        self.current_products = (
            self.get_filtered_products()
        )

        self.table.setRowCount(
            len(
                self.current_products
            )
        )

        for row, product in enumerate(
            self.current_products
        ):

            values = [
                product.get(
                    "產品編號",
                    ""
                ),

                product.get(
                    "產品名稱",
                    ""
                ),

                product.get(
                    "品項分類",
                    ""
                ),

                product.get(
                    "規格",
                    ""
                ),

                product.get(
                    "包裝方式",
                    ""
                ),
            ]

            for column, value in enumerate(
                values
            ):

                self.table.setItem(
                    row,
                    column,
                    QTableWidgetItem(
                        str(value)
                    )
                )

    # =====================================================
    # Add
    # =====================================================

    def add_product(self):

        dialog = ProductDialog(
            self,
            default_category=self.category
        )

        if (
            dialog.exec()
            !=
            QDialog.DialogCode.Accepted
        ):

            return

        data = (
            dialog.get_data()
        )

        try:

            ProductMasterService.upsert_product(
                data[
                    "產品編號"
                ],
                data[
                    "產品名稱"
                ],
                data[
                    "品項分類"
                ],
                data[
                    "規格"
                ],
                data[
                    "包裝方式"
                ]
            )

            self.refresh_table()

        except Exception as e:

            QMessageBox.critical(
                self,
                "新增失敗",
                str(e)
            )

    # =====================================================
    # Edit
    # =====================================================

    def edit_product(self):

        row = (
            self.table
            .currentRow()
        )

        if (
            row < 0
            or
            row >= len(
                self.current_products
            )
        ):

            QMessageBox.warning(
                self,
                "尚未選擇",
                "請先選擇一個產品。"
            )

            return

        product = (
            self.current_products[
                row
            ]
        )

        dialog = ProductDialog(
            self,
            product=product,
            default_category=self.category
        )

        if (
            dialog.exec()
            !=
            QDialog.DialogCode.Accepted
        ):

            return

        data = (
            dialog.get_data()
        )

        ProductMasterService.upsert_product(
            data[
                "產品編號"
            ],
            data[
                "產品名稱"
            ],
            data[
                "品項分類"
            ],
            data[
                "規格"
            ],
            data[
                "包裝方式"
            ]
        )

        self.refresh_table()

    # =====================================================
    # Delete
    # =====================================================

    def delete_product(self):

        row = (
            self.table
            .currentRow()
        )

        if (
            row < 0
            or
            row >= len(
                self.current_products
            )
        ):

            return

        product = (
            self.current_products[
                row
            ]
        )

        result = QMessageBox.question(
            self,
            "確認刪除",
            (
                f"產品編號："
                f"{product.get('產品編號', '')}\n"
                f"產品名稱："
                f"{product.get('產品名稱', '')}\n\n"
                "確定刪除？"
            ),
            QMessageBox
            .StandardButton
            .Yes
            |
            QMessageBox
            .StandardButton
            .No
        )

        if (
            result
            !=
            QMessageBox
            .StandardButton
            .Yes
        ):

            return

        ProductMasterService.delete_product(
            product.get(
                "產品編號",
                ""
            )
        )

        self.refresh_table()


# =========================================================
# Supplier Page
# =========================================================

class SupplierPage(QWidget):

    def __init__(self):

        super().__init__()

        self.suppliers = (
            SupplierService
            .load_suppliers()
        )

        self.vendors = (
            VendorMasterService
            .load_vendors()
        )

        self.products = (
            ProductMasterService
            .load_products()
        )

        self.category_cards = {}

        self.current_relation_rows = []

        self.build_ui()

        self.refresh_everything()

    # =====================================================
    # Main UI
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
            "供應商設定",
            "集中管理供應商主檔、供應商品項分類，以及產品對應的交期、MOQ、採購倍數與進口條件。",
        )

        tabs = QHBoxLayout()

        self.btn_page_vendor = QPushButton(
            "① 供應商資料"
        )

        self.btn_page_category = QPushButton(
            "② 供應商品項分類"
        )

        self.btn_page_relation = QPushButton(
            "③ 產品編號 / 採購條件"
        )

        self.tab_buttons = [
            self.btn_page_vendor,
            self.btn_page_category,
            self.btn_page_relation,
        ]

        for button in self.tab_buttons:

            button.setMinimumHeight(
                48
            )

            tabs.addWidget(
                button
            )

        tabs.addStretch()

        main_layout.addLayout(
            tabs
        )

        self.pages = QStackedWidget()

        self.pages.addWidget(
            self.create_vendor_page()
        )

        self.pages.addWidget(
            self.create_category_page()
        )

        self.pages.addWidget(
            self.create_relation_page()
        )

        main_layout.addWidget(
            self.pages
        )

        self.btn_page_vendor.clicked.connect(
            lambda:
            self.change_page(0)
        )

        self.btn_page_category.clicked.connect(
            lambda:
            self.change_page(1)
        )

        self.btn_page_relation.clicked.connect(
            lambda:
            self.change_page(2)
        )

        self.change_page(0)

    # =====================================================
    # Tabs
    # =====================================================

    def change_page(
        self,
        index
    ):

        self.pages.setCurrentIndex(
            index
        )

        active = """
            QPushButton {
                background-color: #2D6CDF;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 15px;
                font-weight: bold;
                padding: 0 22px;
            }
        """

        inactive = """
            QPushButton {
                background-color: #E9EDF3;
                color: #333333;
                border: none;
                border-radius: 6px;
                font-size: 15px;
                padding: 0 22px;
            }
        """

        for button_index, button in enumerate(
            self.tab_buttons
        ):

            button.setStyleSheet(
                active
                if button_index == index
                else inactive
            )

        self.refresh_everything()

    # =====================================================
    # PAGE 1
    # =====================================================

    def create_vendor_page(self):

        page = QWidget()

        layout = QVBoxLayout(
            page
        )

        toolbar = QHBoxLayout()

        self.btn_import_vendor = QPushButton(
            "📂 匯入供應商 Excel"
        )

        self.vendor_count_label = QLabel(
            "供應商：0 家"
        )

        toolbar.addWidget(
            self.btn_import_vendor
        )

        toolbar.addWidget(
            self.vendor_count_label
        )

        toolbar.addStretch()

        layout.addLayout(
            toolbar
        )

        self.vendor_table = QTableWidget()

        self.vendor_table.setColumnCount(
            4
        )

        self.vendor_table.setHorizontalHeaderLabels(
            [
                "供應商名稱",
                "電話",
                "傳真",
                "地址",
            ]
        )

        self.vendor_table.horizontalHeader().setStretchLastSection(
            True
        )

        layout.addWidget(
            self.vendor_table
        )

        self.btn_import_vendor.clicked.connect(
            self.import_vendor_excel
        )

        return page

    # =====================================================
    # PAGE 2
    # =====================================================

    def create_category_page(self):

        page = QWidget()

        layout = QVBoxLayout(
            page
        )

        vendor_row = QHBoxLayout()

        vendor_row.addWidget(
            QLabel("供應商")
        )

        self.category_vendor_combo = (
            QComboBox()
        )

        vendor_row.addWidget(
            self.category_vendor_combo,
            1
        )

        layout.addLayout(
            vendor_row
        )

        add_row = QHBoxLayout()

        self.new_category_input = QLineEdit()

        self.new_category_input.setPlaceholderText(
            "新增品項"
        )

        self.btn_add_category = QPushButton(
            "＋ 新增品項"
        )

        add_row.addWidget(
            self.new_category_input,
            1
        )

        add_row.addWidget(
            self.btn_add_category
        )

        layout.addLayout(
            add_row
        )

        self.category_scroll = QScrollArea()

        self.category_scroll.setWidgetResizable(
            True
        )

        self.category_scroll.setMinimumHeight(
            500
        )

        self.category_container = QWidget()

        self.category_grid = QGridLayout(
            self.category_container
        )

        self.category_grid.setSpacing(
            15
        )

        self.category_scroll.setWidget(
            self.category_container
        )

        layout.addWidget(
            self.category_scroll,
            1
        )

        bottom = QHBoxLayout()

        self.btn_category_all = QPushButton(
            "☑ 全選"
        )

        self.btn_category_none = QPushButton(
            "☐ 全部取消"
        )

        self.btn_save_categories = QPushButton(
            "💾 儲存供應商品項分類"
        )

        bottom.addWidget(
            self.btn_category_all
        )

        bottom.addWidget(
            self.btn_category_none
        )

        bottom.addStretch()

        bottom.addWidget(
            self.btn_save_categories
        )

        layout.addLayout(
            bottom
        )

        self.category_vendor_combo.currentTextChanged.connect(
            self.category_vendor_changed
        )

        self.btn_add_category.clicked.connect(
            self.add_custom_category
        )

        self.btn_category_all.clicked.connect(
            self.select_all_categories
        )

        self.btn_category_none.clicked.connect(
            self.clear_all_categories
        )

        self.btn_save_categories.clicked.connect(
            self.save_vendor_categories
        )

        return page

    # =====================================================
    # PAGE 3
    # =====================================================

    def create_relation_page(self):

        page = QWidget()

        layout = QVBoxLayout(
            page
        )

        toolbar = QHBoxLayout()

        self.btn_import_product_excel = QPushButton(
            "📦 匯入產品 Excel / 更新產品主檔"
        )

        self.product_count_label = QLabel(
            "產品：0 筆"
        )

        toolbar.addWidget(
            self.btn_import_product_excel
        )

        toolbar.addWidget(
            self.product_count_label
        )

        toolbar.addStretch()

        layout.addLayout(
            toolbar
        )

        selector = QGridLayout()

        selector.addWidget(
            QLabel("產品編號"),
            0,
            0
        )

        self.product_combo = QComboBox()

        selector.addWidget(
            self.product_combo,
            0,
            1
        )

        selector.addWidget(
            QLabel("產品名稱"),
            0,
            2
        )

        self.product_name_label = QLabel(
            "-"
        )

        selector.addWidget(
            self.product_name_label,
            0,
            3
        )

        selector.addWidget(
            QLabel("品項分類"),
            1,
            0
        )

        self.product_category_label = QLabel(
            "-"
        )

        selector.addWidget(
            self.product_category_label,
            1,
            1
        )

        selector.addWidget(
            QLabel("可供應廠商"),
            1,
            2
        )

        self.product_supplier_label = QLabel(
            "尚未設定"
        )

        self.product_supplier_label.setWordWrap(
            True
        )

        selector.addWidget(
            self.product_supplier_label,
            1,
            3
        )

        layout.addLayout(
            selector
        )

        # ===============================================
        # Purchase conditions
        # ===============================================

        condition_frame = QFrame()

        condition_frame.setFrameShape(
            QFrame.Shape.StyledPanel
        )

        grid = QGridLayout(
            condition_frame
        )

        grid.addWidget(
            QLabel("供應商"),
            0,
            0
        )

        self.relation_supplier_combo = QComboBox()

        grid.addWidget(
            self.relation_supplier_combo,
            0,
            1,
            1,
            5
        )

        grid.addWidget(
            QLabel("生產天數"),
            1,
            0
        )

        self.input_production = QSpinBox()

        self.input_production.setRange(
            0,
            365
        )

        self.input_production.setValue(
            45
        )

        grid.addWidget(
            self.input_production,
            1,
            1
        )

        grid.addWidget(
            QLabel("運輸天數"),
            1,
            2
        )

        self.input_shipping = QSpinBox()

        self.input_shipping.setRange(
            0,
            365
        )

        self.input_shipping.setValue(
            14
        )

        grid.addWidget(
            self.input_shipping,
            1,
            3
        )

        grid.addWidget(
            QLabel("報關入庫"),
            1,
            4
        )

        self.input_customs = QSpinBox()

        self.input_customs.setRange(
            0,
            365
        )

        self.input_customs.setValue(
            7
        )

        grid.addWidget(
            self.input_customs,
            1,
            5
        )

        grid.addWidget(
            QLabel("MOQ"),
            2,
            0
        )

        self.input_moq = QSpinBox()

        self.input_moq.setRange(
            0,
            10000000
        )

        grid.addWidget(
            self.input_moq,
            2,
            1
        )

        grid.addWidget(
            QLabel("採購倍數"),
            2,
            2
        )

        self.input_multiple = QSpinBox()

        self.input_multiple.setRange(
            1,
            10000000
        )

        self.input_multiple.setValue(
            1
        )

        grid.addWidget(
            self.input_multiple,
            2,
            3
        )

        grid.addWidget(
            QLabel("安全庫存月"),
            2,
            4
        )

        self.input_safety = QDoubleSpinBox()

        self.input_safety.setRange(
            0,
            24
        )

        self.input_safety.setDecimals(
            1
        )

        self.input_safety.setValue(
            2.0
        )

        grid.addWidget(
            self.input_safety,
            2,
            5
        )

        self.total_lead_label = QLabel(
            "總交期：66 天"
        )

        grid.addWidget(
            self.total_lead_label,
            3,
            0,
            1,
            2
        )

        self.btn_add_relation = QPushButton(
            "＋ 將供應商加入此產品"
        )

        grid.addWidget(
            self.btn_add_relation,
            3,
            3,
            1,
            3
        )

        layout.addWidget(
            condition_frame
        )

        # ===============================================
        # Relation table
        # ===============================================

        self.relation_table = QTableWidget()

        self.relation_table.setColumnCount(
            10
        )

        self.relation_table.setHorizontalHeaderLabels(
            [
                "產品編號",
                "產品名稱",
                "供應商",
                "生產天數",
                "運輸天數",
                "報關入庫",
                "總交期",
                "MOQ",
                "採購倍數",
                "安全庫存月",
            ]
        )

        self.relation_table.setMinimumHeight(
            400
        )

        self.relation_table.setSelectionBehavior(
            QAbstractItemView
            .SelectionBehavior
            .SelectRows
        )

        self.relation_table.setSelectionMode(
            QAbstractItemView
            .SelectionMode
            .SingleSelection
        )

        layout.addWidget(
            self.relation_table,
            1
        )

        buttons = QHBoxLayout()

        self.btn_load_relation = QPushButton(
            "↥ 載入"
        )

        self.btn_update_relation = QPushButton(
            "✏ 修改"
        )

        self.btn_delete_relation = QPushButton(
            "🗑 刪除"
        )

        buttons.addWidget(
            self.btn_load_relation
        )

        buttons.addWidget(
            self.btn_update_relation
        )

        buttons.addWidget(
            self.btn_delete_relation
        )

        buttons.addStretch()

        layout.addLayout(
            buttons
        )

        self.btn_import_product_excel.clicked.connect(
            self.import_products
        )

        self.product_combo.currentTextChanged.connect(
            self.product_changed
        )

        self.btn_add_relation.clicked.connect(
            self.add_relation
        )

        self.btn_load_relation.clicked.connect(
            self.load_relation
        )

        self.btn_update_relation.clicked.connect(
            self.update_relation
        )

        self.btn_delete_relation.clicked.connect(
            self.delete_relation
        )

        self.input_production.valueChanged.connect(
            self.update_total_lead
        )

        self.input_shipping.valueChanged.connect(
            self.update_total_lead
        )

        self.input_customs.valueChanged.connect(
            self.update_total_lead
        )

        return page

    # =====================================================
    # Refresh
    # =====================================================

    def refresh_everything(self):

        self.vendors = (
            VendorMasterService
            .load_vendors()
        )

        self.products = (
            ProductMasterService
            .load_products()
        )

        self.suppliers = (
            SupplierService
            .load_suppliers()
        )

        self.refresh_vendor_table()
        self.refresh_category_vendor_combo()
        self.refresh_category_cards()
        self.refresh_relation_supplier_combo()
        self.refresh_product_combo()
        self.refresh_relation_table()

    # =====================================================
    # Vendors
    # =====================================================

    def import_vendor_excel(self):

        file_paths, _ = (
            QFileDialog
            .getOpenFileNames(
                self,
                "選擇供應商 Excel",
                "",
                "Excel Files (*.xlsx *.xlsm)"
            )
        )

        if not file_paths:
            return

        try:

            for file_path in file_paths:

                VendorMasterService.import_from_excel(
                    file_path
                )

            self.refresh_everything()

        except Exception as e:

            QMessageBox.critical(
                self,
                "匯入失敗",
                str(e)
            )

    def refresh_vendor_table(self):

        if not hasattr(
            self,
            "vendor_table"
        ):
            return

        self.vendor_table.setRowCount(
            len(self.vendors)
        )

        for row, vendor in enumerate(
            self.vendors
        ):

            values = [
                vendor.get(
                    "name",
                    ""
                ),
                vendor.get(
                    "phone",
                    ""
                ),
                vendor.get(
                    "fax",
                    ""
                ),
                vendor.get(
                    "address",
                    ""
                ),
            ]

            for column, value in enumerate(
                values
            ):

                self.vendor_table.setItem(
                    row,
                    column,
                    QTableWidgetItem(
                        str(value)
                    )
                )

        self.vendor_count_label.setText(
            f"供應商：{len(self.vendors)} 家"
        )

    # =====================================================
    # Category
    # =====================================================

    def refresh_category_vendor_combo(self):

        if not hasattr(
            self,
            "category_vendor_combo"
        ):
            return

        current = (
            self.category_vendor_combo
            .currentText()
        )

        names = [
            str(
                vendor.get(
                    "name",
                    ""
                )
            ).strip()
            for vendor in self.vendors
            if vendor.get(
                "name"
            )
        ]

        self.category_vendor_combo.blockSignals(
            True
        )

        self.category_vendor_combo.clear()

        self.category_vendor_combo.addItems(
            names
        )

        if current in names:

            self.category_vendor_combo.setCurrentText(
                current
            )

        self.category_vendor_combo.blockSignals(
            False
        )

    def refresh_category_cards(self):

        if not hasattr(
            self,
            "category_grid"
        ):
            return

        while (
            self.category_grid.count()
        ):

            item = (
                self.category_grid
                .takeAt(0)
            )

            widget = (
                item.widget()
            )

            if widget:

                widget.deleteLater()

        self.category_cards = {}

        categories = (
            VendorMasterService
            .load_categories()
        )

        image_map = (
            VendorMasterService
            .load_category_images()
        )

        columns = 4

        for index, category in enumerate(
            categories
        ):

            card = QFrame()

            card.setFrameShape(
                QFrame.Shape.StyledPanel
            )

            card.setFixedSize(
                190,
                235
            )

            card_layout = QVBoxLayout(
                card
            )

            image_label = QLabel(
                "尚未設定圖片"
            )

            image_label.setAlignment(
                Qt.AlignmentFlag
                .AlignCenter
            )

            image_label.setFixedSize(
                165,
                100
            )

            image_path = (
                image_map.get(
                    category
                )
            )

            if (
                image_path
                and
                os.path.exists(
                    image_path
                )
            ):

                pixmap = QPixmap(
                    image_path
                )

                pixmap = pixmap.scaled(
                    QSize(
                        155,
                        90
                    ),
                    Qt.AspectRatioMode
                    .KeepAspectRatio,
                    Qt.TransformationMode
                    .SmoothTransformation
                )

                image_label.setPixmap(
                    pixmap
                )

            card_layout.addWidget(
                image_label,
                alignment=Qt.AlignmentFlag.AlignCenter
            )

            checkbox = QCheckBox(
                category
            )

            card_layout.addWidget(
                checkbox,
                alignment=Qt.AlignmentFlag.AlignCenter
            )

            product_count = len(
                ProductMasterService
                .get_products_by_category(
                    category
                )
            )

            btn_products = QPushButton(
                f"查看產品（{product_count}）"
            )

            btn_products.clicked.connect(
                lambda checked=False,
                name=category:
                self.open_category_products(
                    name
                )
            )

            btn_image = QPushButton(
                "更換圖片"
            )

            btn_image.clicked.connect(
                lambda checked=False,
                name=category:
                self.change_category_image(
                    name
                )
            )

            card_layout.addWidget(
                btn_products
            )

            card_layout.addWidget(
                btn_image
            )

            self.category_cards[
                category
            ] = checkbox

            self.category_grid.addWidget(
                card,
                index // columns,
                index % columns
            )

        self.category_vendor_changed(
            self.category_vendor_combo
            .currentText()
        )

    def category_vendor_changed(
        self,
        vendor_name
    ):

        selected = []

        for vendor in self.vendors:

            if (
                str(
                    vendor.get(
                        "name",
                        ""
                    )
                ).strip()
                ==
                str(
                    vendor_name
                ).strip()
            ):

                selected = (
                    vendor.get(
                        "categories",
                        []
                    )
                )

                break

        for category, checkbox in (
            self.category_cards.items()
        ):

            checkbox.setChecked(
                category in selected
            )

    def save_vendor_categories(self):

        vendor_name = (
            self.category_vendor_combo
            .currentText()
            .strip()
        )

        selected = [
            category
            for category, checkbox
            in self.category_cards.items()
            if checkbox.isChecked()
        ]

        for vendor in self.vendors:

            if (
                str(
                    vendor.get(
                        "name",
                        ""
                    )
                ).strip()
                ==
                vendor_name
            ):

                vendor[
                    "categories"
                ] = selected

                break

        VendorMasterService.save_vendors(
            self.vendors
        )

        QMessageBox.information(
            self,
            "完成",
            "供應商品項分類已儲存。"
        )

    def add_custom_category(self):

        category = (
            self.new_category_input
            .text()
            .strip()
        )

        if not category:
            return

        VendorMasterService.add_category(
            category
        )

        self.new_category_input.clear()

        self.refresh_category_cards()

    def select_all_categories(self):

        for checkbox in (
            self.category_cards.values()
        ):

            checkbox.setChecked(
                True
            )

    def clear_all_categories(self):

        for checkbox in (
            self.category_cards.values()
        ):

            checkbox.setChecked(
                False
            )

    def open_category_products(
        self,
        category
    ):

        dialog = (
            CategoryProductsDialog(
                category,
                self
            )
        )

        dialog.exec()

        self.products = (
            ProductMasterService
            .load_products()
        )

        self.refresh_category_cards()
        self.refresh_product_combo()

    def change_category_image(
        self,
        category
    ):

        file_path, _ = (
            QFileDialog
            .getOpenFileName(
                self,
                "選擇圖片",
                "",
                "Images (*.png *.jpg *.jpeg *.webp)"
            )
        )

        if not file_path:
            return

        VendorMasterService.set_category_image(
            category,
            file_path
        )

        self.refresh_category_cards()

    # =====================================================
    # Product import - multi file
    # =====================================================

    def import_products(self):

        file_paths, _ = (
            QFileDialog
            .getOpenFileNames(
                self,
                "選擇產品 Excel（可一次選多份）",
                "",
                "Excel Files (*.xlsx *.xlsm)"
            )
        )

        if not file_paths:
            return

        try:

            result = (
                ProductMasterService
                .import_from_excels(
                    file_paths
                )
            )

            self.products = (
                ProductMasterService
                .load_products()
            )

            self.refresh_product_combo()

            QMessageBox.information(
                self,
                "產品匯入完成",
                (
                    f"成功讀取 "
                    f"{len(result['successful_files'])} "
                    f"份 Excel。\n\n"
                    f"本次取得 "
                    f"{result['imported_count']} "
                    f"個不同產品編號。\n\n"
                    f"產品主檔目前共有 "
                    f"{len(self.products)} 筆。"
                )
            )

        except Exception as e:

            QMessageBox.critical(
                self,
                "產品匯入失敗",
                str(e)
            )

    # =====================================================
    # Product combo
    # =====================================================

    def refresh_product_combo(self):

        if not hasattr(
            self,
            "product_combo"
        ):
            return

        current = (
            self.product_combo
            .currentText()
        )

        self.products = (
            ProductMasterService
            .load_products()
        )

        self.product_combo.blockSignals(
            True
        )

        self.product_combo.clear()

        for product in self.products:

            product_no = (
                product.get(
                    "產品編號",
                    ""
                )
            )

            if product_no:

                self.product_combo.addItem(
                    product_no
                )

        if (
            current
            and
            self.product_combo.findText(
                current
            )
            >= 0
        ):

            self.product_combo.setCurrentText(
                current
            )

        self.product_combo.blockSignals(
            False
        )

        self.product_count_label.setText(
            f"產品：{len(self.products)} 筆"
        )

        if (
            self.product_combo.count()
            > 0
        ):

            self.product_changed(
                self.product_combo
                .currentText()
            )

    # =====================================================
    # Product changed
    # =====================================================

    def product_changed(
        self,
        product_no
    ):

        product = None

        for item in self.products:

            if (
                item.get(
                    "產品編號"
                )
                ==
                product_no
            ):

                product = item

                break

        if product is None:

            self.product_name_label.setText(
                "-"
            )

            self.product_category_label.setText(
                "-"
            )

            return

        self.product_name_label.setText(
            product.get(
                "產品名稱",
                ""
            )
            or
            "-"
        )

        self.product_category_label.setText(
            product.get(
                "品項分類",
                ""
            )
            or
            "尚未分類"
        )

        supplier_names = []

        for relation in self.suppliers:

            relation_no = (
                relation.get(
                    "product_no"
                )
                or
                relation.get(
                    "產品編號"
                )
                or
                relation.get(
                    "item_no"
                )
                or
                relation.get(
                    "料號"
                )
                or
                ""
            )

            if (
                str(
                    relation_no
                ).strip()
                ==
                str(
                    product_no
                ).strip()
            ):

                supplier_name = (
                    str(
                        relation.get(
                            "supplier",
                            ""
                        )
                    ).strip()
                )

                if (
                    supplier_name
                    and
                    supplier_name
                    not in supplier_names
                ):

                    supplier_names.append(
                        supplier_name
                    )

        self.product_supplier_label.setText(
            " ｜ ".join(
                supplier_names
            )
            if supplier_names
            else
            "尚未設定"
        )

        self.refresh_relation_table(
            product_no
        )

    # =====================================================
    # Supplier combo
    # =====================================================

    def refresh_relation_supplier_combo(self):

        if not hasattr(
            self,
            "relation_supplier_combo"
        ):
            return

        current = (
            self.relation_supplier_combo
            .currentText()
        )

        names = sorted(
            {
                str(
                    vendor.get(
                        "name",
                        ""
                    )
                ).strip()

                for vendor in self.vendors

                if vendor.get(
                    "name"
                )
            }
        )

        self.relation_supplier_combo.blockSignals(
            True
        )

        self.relation_supplier_combo.clear()

        self.relation_supplier_combo.addItems(
            names
        )

        if current in names:

            self.relation_supplier_combo.setCurrentText(
                current
            )

        self.relation_supplier_combo.blockSignals(
            False
        )

    # =====================================================
    # Add relation
    # =====================================================

    def add_relation(self):

        product_no = (
            self.product_combo
            .currentText()
            .strip()
        )

        supplier_name = (
            self.relation_supplier_combo
            .currentText()
            .strip()
        )

        if not product_no:

            QMessageBox.warning(
                self,
                "沒有產品",
                "請先匯入或建立產品主檔。"
            )

            return

        if not supplier_name:

            QMessageBox.warning(
                self,
                "沒有供應商",
                "請先選擇供應商。"
            )

            return

        product_name = (
            self.product_name_label
            .text()
        )

        data = {
            "product_no":
                product_no,

            "產品編號":
                product_no,

            # 舊資料相容
            "item_no":
                product_no,

            "product_name":
                product_name,

            "產品名稱":
                product_name,

            "supplier":
                supplier_name,

            "production_days":
                self.input_production
                .value(),

            "shipping_days":
                self.input_shipping
                .value(),

            "customs_days":
                self.input_customs
                .value(),

            "lead_time_days":
                (
                    self.input_production
                    .value()
                    +
                    self.input_shipping
                    .value()
                    +
                    self.input_customs
                    .value()
                ),

            "moq":
                self.input_moq
                .value(),

            "order_multiple":
                self.input_multiple
                .value(),

            "safety_months":
                self.input_safety
                .value(),
        }

        existing_index = None

        for index, relation in enumerate(
            self.suppliers
        ):

            relation_no = (
                relation.get(
                    "product_no"
                )
                or
                relation.get(
                    "產品編號"
                )
                or
                relation.get(
                    "item_no"
                )
                or
                ""
            )

            if (
                str(
                    relation_no
                ).strip()
                ==
                product_no
                and
                str(
                    relation.get(
                        "supplier",
                        ""
                    )
                ).strip()
                ==
                supplier_name
            ):

                existing_index = index

                break

        if existing_index is None:

            self.suppliers.append(
                data
            )

        else:

            self.suppliers[
                existing_index
            ] = data

        SupplierService.save_suppliers(
            self.suppliers
        )

        self.product_changed(
            product_no
        )

    # =====================================================
    # Relation table
    # =====================================================

    def refresh_relation_table(
        self,
        product_no=None
    ):

        if not hasattr(
            self,
            "relation_table"
        ):
            return

        rows = []

        for relation in self.suppliers:

            relation_no = (
                relation.get(
                    "product_no"
                )
                or
                relation.get(
                    "產品編號"
                )
                or
                relation.get(
                    "item_no"
                )
                or
                relation.get(
                    "料號"
                )
                or
                ""
            )

            if (
                product_no
                and
                str(
                    relation_no
                ).strip()
                !=
                str(
                    product_no
                ).strip()
            ):

                continue

            rows.append(
                relation
            )

        self.current_relation_rows = (
            rows
        )

        self.relation_table.setRowCount(
            len(rows)
        )

        for row_index, data in enumerate(
            rows
        ):

            product_number = (
                data.get(
                    "product_no"
                )
                or
                data.get(
                    "產品編號"
                )
                or
                data.get(
                    "item_no"
                )
                or
                ""
            )

            product_name = (
                data.get(
                    "產品名稱"
                )
                or
                data.get(
                    "product_name"
                )
                or
                ""
            )

            values = [
                product_number,
                product_name,
                data.get(
                    "supplier",
                    ""
                ),
                data.get(
                    "production_days",
                    0
                ),
                data.get(
                    "shipping_days",
                    0
                ),
                data.get(
                    "customs_days",
                    0
                ),
                data.get(
                    "lead_time_days",
                    0
                ),
                data.get(
                    "moq",
                    0
                ),
                data.get(
                    "order_multiple",
                    1
                ),
                data.get(
                    "safety_months",
                    0
                ),
            ]

            for column, value in enumerate(
                values
            ):

                self.relation_table.setItem(
                    row_index,
                    column,
                    QTableWidgetItem(
                        str(value)
                    )
                )

    # =====================================================
    # Selected relation
    # =====================================================

    def get_selected_relation(self):

        row = (
            self.relation_table
            .currentRow()
        )

        if (
            row < 0
            or
            row >= len(
                self.current_relation_rows
            )
        ):

            return None

        return (
            self.current_relation_rows[
                row
            ]
        )

    def load_relation(self):

        data = (
            self.get_selected_relation()
        )

        if data is None:

            QMessageBox.warning(
                self,
                "尚未選擇",
                "請先選擇一筆資料。"
            )

            return

        supplier_name = str(
            data.get(
                "supplier",
                ""
            )
        )

        if (
            self.relation_supplier_combo
            .findText(
                supplier_name
            )
            >= 0
        ):

            self.relation_supplier_combo.setCurrentText(
                supplier_name
            )

        self.input_production.setValue(
            int(
                data.get(
                    "production_days",
                    0
                )
            )
        )

        self.input_shipping.setValue(
            int(
                data.get(
                    "shipping_days",
                    0
                )
            )
        )

        self.input_customs.setValue(
            int(
                data.get(
                    "customs_days",
                    0
                )
            )
        )

        self.input_moq.setValue(
            int(
                data.get(
                    "moq",
                    0
                )
            )
        )

        self.input_multiple.setValue(
            max(
                1,
                int(
                    data.get(
                        "order_multiple",
                        1
                    )
                )
            )
        )

        self.input_safety.setValue(
            float(
                data.get(
                    "safety_months",
                    0
                )
            )
        )

    def update_relation(self):

        old = (
            self.get_selected_relation()
        )

        if old is None:
            return

        product_no = (
            self.product_combo
            .currentText()
            .strip()
        )

        supplier_name = (
            self.relation_supplier_combo
            .currentText()
            .strip()
        )

        for index, relation in enumerate(
            self.suppliers
        ):

            if relation is old:

                self.suppliers[index] = {
                    "product_no":
                        product_no,

                    "產品編號":
                        product_no,

                    "item_no":
                        product_no,

                    "product_name":
                        self.product_name_label
                        .text(),

                    "產品名稱":
                        self.product_name_label
                        .text(),

                    "supplier":
                        supplier_name,

                    "production_days":
                        self.input_production
                        .value(),

                    "shipping_days":
                        self.input_shipping
                        .value(),

                    "customs_days":
                        self.input_customs
                        .value(),

                    "lead_time_days":
                        (
                            self.input_production
                            .value()
                            +
                            self.input_shipping
                            .value()
                            +
                            self.input_customs
                            .value()
                        ),

                    "moq":
                        self.input_moq
                        .value(),

                    "order_multiple":
                        self.input_multiple
                        .value(),

                    "safety_months":
                        self.input_safety
                        .value(),
                }

                break

        SupplierService.save_suppliers(
            self.suppliers
        )

        self.product_changed(
            product_no
        )

    def delete_relation(self):

        data = (
            self.get_selected_relation()
        )

        if data is None:
            return

        self.suppliers.remove(
            data
        )

        SupplierService.save_suppliers(
            self.suppliers
        )

        self.product_changed(
            self.product_combo
            .currentText()
        )

    def update_total_lead(self):

        total = (
            self.input_production
            .value()
            +
            self.input_shipping
            .value()
            +
            self.input_customs
            .value()
        )

        self.total_lead_label.setText(
            f"總交期：{total} 天"
        )