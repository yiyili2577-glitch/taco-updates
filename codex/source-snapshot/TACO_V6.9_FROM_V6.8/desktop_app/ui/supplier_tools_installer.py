from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QTableWidget, QMessageBox
)

from services.table_export_service import TableExportService
from ui.column_visibility_dialog import ColumnVisibilityDialog
from ui.responsive_action_bar import FlowLayout


class SupplierToolsInstaller:
    """不覆蓋既有 SupplierPage，也能替目前版本的供應商設定頁加上工具列。

    這樣可以保留使用者目前已完成的分類卡片、圖片與其他客製 UI。
    """

    _installed = False
    _attempts = 0

    @staticmethod
    def install_later():
        SupplierToolsInstaller._attempts = 0
        QTimer.singleShot(700, SupplierToolsInstaller._try_install)

    @staticmethod
    def _try_install():
        if SupplierToolsInstaller._installed:
            return

        SupplierToolsInstaller._attempts += 1
        app = QApplication.instance()
        if app is None:
            return

        supplier_page = None
        for top in app.topLevelWidgets():
            candidates = [top] + top.findChildren(QWidget)
            for widget in candidates:
                if widget.__class__.__name__ == "SupplierPage":
                    supplier_page = widget
                    break
            if supplier_page is not None:
                break

        if supplier_page is None or supplier_page.layout() is None:
            if SupplierToolsInstaller._attempts < 10:
                QTimer.singleShot(700, SupplierToolsInstaller._try_install)
            return

        if supplier_page.property("v43_table_tools_installed"):
            SupplierToolsInstaller._installed = True
            return

        toolbar_widget = QWidget(supplier_page)
        toolbar = FlowLayout(toolbar_widget, h_spacing=7, v_spacing=7)
        toolbar.setContentsMargins(0, 0, 0, 6)

        btn_hide = QPushButton("🙈 隱藏空白欄")
        btn_columns = QPushButton("⚙ 欄位顯示")
        btn_excel = QPushButton("📊 匯出 Excel")
        btn_pdf = QPushButton("📄 匯出 PDF")

        toolbar.addWidget(btn_hide)
        toolbar.addWidget(btn_columns)
        toolbar.addStretch()
        toolbar.addWidget(btn_excel)
        toolbar.addWidget(btn_pdf)

        try:
            supplier_page.layout().insertWidget(0, toolbar_widget)
        except Exception:
            supplier_page.layout().addWidget(toolbar_widget)

        def all_tables():
            return [t for t in supplier_page.findChildren(QTableWidget) if t.columnCount() > 0]

        def active_table():
            tables = all_tables()
            if not tables:
                return None
            for table in tables:
                if table.hasFocus() and table.isVisible():
                    return table
            for table in tables:
                if table.isVisible():
                    return table
            return tables[0]

        def table_name(table, index):
            # 依常見欄位判斷名稱，否則使用資料表序號。
            headers = []
            for col in range(table.columnCount()):
                item = table.horizontalHeaderItem(col)
                headers.append(item.text() if item else "")
            joined = " ".join(headers)
            if "供應商" in joined and "電話" in joined:
                return "供應商主檔"
            if "產品編號" in joined or "料號" in joined:
                if "MOQ" in joined or "採購倍數" in joined or "總交期" in joined:
                    return "產品供應商採購條件"
                return "產品資料"
            return f"供應商資料{index}"

        def hide_empty():
            table = active_table()
            if table is None:
                QMessageBox.information(supplier_page, "沒有表格", "目前供應商設定頁沒有可操作的表格。")
                return
            count = TableExportService.hide_empty_columns(table)
            QMessageBox.information(
                supplier_page,
                "欄位顯示",
                f"已在目前顯示的資料表暫時隱藏 {count} 個完全空白欄位。"
            )

        def choose_columns():
            table = active_table()
            if table is None:
                QMessageBox.information(supplier_page, "沒有表格", "目前供應商設定頁沒有可設定的表格。")
                return
            ColumnVisibilityDialog(table, supplier_page, "供應商設定 - 欄位顯示設定").exec()

        def export_excel():
            tables = all_tables()
            named = [(table_name(t, i + 1), t) for i, t in enumerate(tables)]
            TableExportService.export_tables_excel(
                supplier_page, named, "供應商設定.xlsx"
            )

        def export_pdf():
            tables = all_tables()
            named = [(table_name(t, i + 1), t) for i, t in enumerate(tables)]
            TableExportService.export_tables_pdf(
                supplier_page, named, "供應商設定", "供應商設定.pdf"
            )

        btn_hide.clicked.connect(hide_empty)
        btn_columns.clicked.connect(choose_columns)
        btn_excel.clicked.connect(export_excel)
        btn_pdf.clicked.connect(export_pdf)

        supplier_page.setProperty("v43_table_tools_installed", True)
        SupplierToolsInstaller._installed = True
