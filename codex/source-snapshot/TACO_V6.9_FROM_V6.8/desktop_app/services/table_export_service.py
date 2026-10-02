import html
import os
import re

import pandas as pd

from PyQt6.QtWidgets import QFileDialog, QMessageBox, QTableWidget, QComboBox
from PyQt6.QtGui import QTextDocument, QPageLayout, QPageSize
from PyQt6.QtPrintSupport import QPrinter

from services.system_settings_service import SystemSettingsService
from services.app_paths import AppPaths
from datetime import datetime


class TableExportService:
    """共用表格匯出與欄位顯示工具。

    設計原則：
    1. 匯出時只匯出目前「可見欄位」，方便使用者先隱藏不需要的資料再匯出。
    2. 0 / 0.0 是有效資料，不視為空白欄。
    3. QComboBox 等 cellWidget 也會取目前顯示文字。
    """

    @staticmethod
    def _cell_text(table: QTableWidget, row: int, col: int) -> str:
        widget = table.cellWidget(row, col)
        if widget is not None:
            if isinstance(widget, QComboBox):
                return widget.currentText().strip()
            if hasattr(widget, "text"):
                try:
                    return str(widget.text()).strip()
                except Exception:
                    pass

        item = table.item(row, col)
        if item is None:
            return ""
        return str(item.text()).strip()

    @staticmethod
    def visible_column_indexes(table: QTableWidget):
        return [
            col
            for col in range(table.columnCount())
            if not table.isColumnHidden(col)
        ]

    @staticmethod
    def table_to_dataframe(table: QTableWidget, visible_only=True):
        if table is None:
            return pd.DataFrame()

        columns = (
            TableExportService.visible_column_indexes(table)
            if visible_only
            else list(range(table.columnCount()))
        )

        headers = []
        used = {}
        for col in columns:
            header_item = table.horizontalHeaderItem(col)
            name = header_item.text().strip() if header_item else f"欄位{col + 1}"
            if not name:
                name = f"欄位{col + 1}"
            # 避免重複欄名讓 DataFrame / Excel 難以閱讀
            used[name] = used.get(name, 0) + 1
            if used[name] > 1:
                name = f"{name}_{used[name]}"
            headers.append(name)

        rows = []
        for row in range(table.rowCount()):
            values = [
                TableExportService._cell_text(table, row, col)
                for col in columns
            ]
            rows.append(values)

        return pd.DataFrame(rows, columns=headers)

    @staticmethod
    def is_column_empty(table: QTableWidget, col: int):
        """只有真正空字串才視為空欄；0 不算空白。"""
        for row in range(table.rowCount()):
            value = TableExportService._cell_text(table, row, col)
            if value != "":
                return False
        return True

    @staticmethod
    def hide_empty_columns(table: QTableWidget):
        if table is None:
            return 0
        hidden = 0
        for col in range(table.columnCount()):
            if TableExportService.is_column_empty(table, col):
                if not table.isColumnHidden(col):
                    table.setColumnHidden(col, True)
                    hidden += 1
        return hidden

    @staticmethod
    def show_all_columns(table: QTableWidget):
        if table is None:
            return
        for col in range(table.columnCount()):
            table.setColumnHidden(col, False)

    @staticmethod
    def _safe_sheet_name(name, fallback):
        name = re.sub(r"[\\/*?:\[\]]", "_", str(name or fallback)).strip()
        return (name or fallback)[:31]

    @staticmethod
    def _default_export_path(default_name):
        settings = SystemSettingsService.load().get("export", {})
        folder = str(settings.get("default_folder", "exports") or "exports").strip()
        if not os.path.isabs(folder):
            folder = str(AppPaths.exports_dir() / folder) if folder not in {"exports", "Exports"} else str(AppPaths.exports_dir())
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception:
            folder = ""
        name = str(default_name)
        if settings.get("include_timestamp", True):
            stem, ext = os.path.splitext(name)
            name = f"{stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        return os.path.join(folder, name) if folder else name

    @staticmethod
    def export_tables_excel(parent, named_tables, default_name="匯出資料.xlsx"):
        """named_tables: [(名稱, QTableWidget), ...]"""
        usable = []
        for name, table in named_tables:
            if table is None:
                continue
            df = TableExportService.table_to_dataframe(table, visible_only=True)
            if df.empty and table.rowCount() == 0:
                continue
            usable.append((name, df))

        if not usable:
            QMessageBox.warning(parent, "沒有資料", "目前沒有可匯出的表格資料。")
            return ""

        path, _ = QFileDialog.getSaveFileName(
            parent,
            "匯出 Excel",
            TableExportService._default_export_path(default_name),
            "Excel Files (*.xlsx)",
        )
        if not path:
            return ""
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        try:
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                seen = set()
                for index, (name, df) in enumerate(usable, start=1):
                    sheet = TableExportService._safe_sheet_name(name, f"資料{index}")
                    base = sheet
                    suffix = 2
                    while sheet in seen:
                        sheet = TableExportService._safe_sheet_name(f"{base}_{suffix}", f"資料{index}")
                        suffix += 1
                    seen.add(sheet)
                    df.to_excel(writer, sheet_name=sheet, index=False)
                    ws = writer.book[sheet]
                    ws.freeze_panes = "A2"
                    ws.auto_filter.ref = ws.dimensions
                    for cell in ws[1]:
                        cell.font = cell.font.copy(bold=True)
                    # 適度調整欄寬，避免極端 autofit
                    for col_cells in ws.columns:
                        letter = col_cells[0].column_letter
                        max_len = 8
                        for cell in col_cells[:200]:
                            value = "" if cell.value is None else str(cell.value)
                            max_len = max(max_len, min(len(value), 38))
                        ws.column_dimensions[letter].width = min(max_len + 2, 40)

            try:
                from services.audit_log_service import AuditLogService
                AuditLogService.log_event("匯出", "匯出 Excel", record_id=path, after={"工作表數": len(usable)}, result="成功")
            except Exception:
                pass
            QMessageBox.information(parent, "匯出完成", f"Excel 已匯出：\n{path}")
            return path
        except Exception as e:
            QMessageBox.critical(parent, "Excel 匯出失敗", str(e))
            return ""

    @staticmethod
    def export_tables_pdf(parent, named_tables, title="資料匯出", default_name="匯出資料.pdf"):
        usable = []
        for name, table in named_tables:
            if table is None:
                continue
            df = TableExportService.table_to_dataframe(table, visible_only=True)
            if df.empty and table.rowCount() == 0:
                continue
            usable.append((name, df))

        if not usable:
            QMessageBox.warning(parent, "沒有資料", "目前沒有可匯出的表格資料。")
            return ""

        path, _ = QFileDialog.getSaveFileName(
            parent,
            "匯出 PDF",
            TableExportService._default_export_path(default_name),
            "PDF Files (*.pdf)",
        )
        if not path:
            return ""
        if not path.lower().endswith(".pdf"):
            path += ".pdf"

        try:
            parts = [
                "<html><head><meta charset='utf-8'><style>",
                "body{font-family:'Microsoft JhengHei','Microsoft YaHei','Noto Sans CJK TC',sans-serif;font-size:8pt;}",
                "h1{font-size:16pt;margin:0 0 10px 0;} h2{font-size:11pt;margin:14px 0 6px 0;}",
                "table{border-collapse:collapse;width:100%;margin-bottom:10px;}",
                "th,td{border:1px solid #888;padding:3px 4px;vertical-align:top;word-wrap:break-word;}",
                "th{background:#eeeeee;font-weight:bold;}",
                "</style></head><body>",
                f"<h1>{html.escape(title)}</h1>",
            ]

            for section_name, df in usable:
                parts.append(f"<h2>{html.escape(str(section_name))}</h2>")
                parts.append("<table><thead><tr>")
                for col in df.columns:
                    parts.append(f"<th>{html.escape(str(col))}</th>")
                parts.append("</tr></thead><tbody>")
                for _, row in df.iterrows():
                    parts.append("<tr>")
                    for col in df.columns:
                        value = "" if pd.isna(row[col]) else str(row[col])
                        parts.append(f"<td>{html.escape(value)}</td>")
                    parts.append("</tr>")
                parts.append("</tbody></table>")

            parts.append("</body></html>")

            document = QTextDocument()
            document.setHtml("".join(parts))

            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(path)
            printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
            printer.setPageOrientation(QPageLayout.Orientation.Landscape)
            document.print(printer)

            if not os.path.exists(path) or os.path.getsize(path) == 0:
                raise Exception("PDF 沒有成功建立。")

            try:
                from services.audit_log_service import AuditLogService
                AuditLogService.log_event("匯出", "匯出 PDF", record_id=path, after={"區塊數": len(usable)}, result="成功")
            except Exception:
                pass
            QMessageBox.information(parent, "匯出完成", f"PDF 已匯出：\n{path}")
            return path
        except Exception as e:
            QMessageBox.critical(parent, "PDF 匯出失敗", str(e))
            return ""
