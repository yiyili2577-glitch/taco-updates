from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QLineEdit
)

from services.erp_sql_connector_service import (
    ErpSqlConnectorService, SqlImportNotConfiguredError, UnsafeSqlError,
)


class SqlImportDialog(QDialog):
    """讓使用者從正航 SQL Server 預覽、匯入庫存或客戶需求資料，取代手動匯入 Excel。

    密碼只存在這個視窗的欄位裡，關閉視窗後就消失，不會被寫進任何檔案
    （跟系統設定 > 連線資料分頁的「密碼（不儲存）」欄位是同一個設計原則）。
    """

    PURPOSE_LABELS = {"庫存": "inventory", "客戶需求": "customer_demand"}

    def __init__(self, password="", parent=None):
        super().__init__(parent)
        self._initial_password = password
        self.setWindowTitle("從 SQL Server 匯入資料")
        self.resize(900, 560)
        self.build_ui()

    def build_ui(self):
        layout = QVBoxLayout(self)

        note = QLabel(
            "會用「系統設定 → 連線資料」分頁裡儲存的伺服器/帳號資訊連線，密碼只在這個視窗使用一次、不會被儲存。\n"
            "建議先按「預覽」確認欄位與資料看起來正確，再按「確認匯入」寫入 TACO；匯入會覆蓋 TACO 目前對應的資料。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        row = QHBoxLayout()
        row.addWidget(QLabel("匯入項目"))
        self.purpose_combo = QComboBox()
        self.purpose_combo.addItems(list(self.PURPOSE_LABELS.keys()))
        row.addWidget(self.purpose_combo)

        row.addWidget(QLabel("密碼"))
        self.password_field = QLineEdit()
        self.password_field.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_field.setText(self._initial_password)
        row.addWidget(self.password_field)

        self.btn_preview = QPushButton("🔍 SQL 預覽")
        self.btn_preview.clicked.connect(self.do_preview)
        row.addWidget(self.btn_preview)
        row.addStretch()
        layout.addLayout(row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        layout.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        self.btn_import = QPushButton("📥 SQL 確認匯入")
        self.btn_import.clicked.connect(self.do_import)
        btn_close = QPushButton("關閉")
        btn_close.clicked.connect(self.reject)
        bottom.addWidget(self.btn_import)
        bottom.addStretch()
        bottom.addWidget(btn_close)
        layout.addLayout(bottom)

    def _current_purpose(self):
        return self.PURPOSE_LABELS[self.purpose_combo.currentText()]

    def do_preview(self):
        purpose = self._current_purpose()
        password = self.password_field.text()
        self.status_label.setText("正在查詢預覽資料...")
        try:
            result = ErpSqlConnectorService.preview(purpose, password, limit=20)
        except SqlImportNotConfiguredError as e:
            QMessageBox.warning(self, "尚未設定查詢", str(e))
            self.status_label.setText("")
            return
        except UnsafeSqlError as e:
            QMessageBox.critical(self, "查詢被拒絕", str(e))
            self.status_label.setText("")
            return
        except Exception as e:
            QMessageBox.critical(self, "預覽失敗", str(e))
            self.status_label.setText("")
            return
        self._fill_table(result["columns"], result["rows"])
        self.status_label.setText(
            f"預覽 {result['row_count']} 筆（最多顯示 20 筆，僅供確認欄位與資料是否正確，尚未寫入 TACO）。"
        )

    def do_import(self):
        purpose = self._current_purpose()
        password = self.password_field.text()
        label = self.purpose_combo.currentText()
        answer = QMessageBox.question(
            self, "確認匯入",
            f"確定要從 SQL Server 匯入「{label}」嗎？這會覆蓋 TACO 目前對應的資料，建議先預覽確認過。"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.status_label.setText("正在匯入...")
        try:
            if purpose == "inventory":
                result = ErpSqlConnectorService.import_inventory_from_sql(password)
            else:
                result = ErpSqlConnectorService.import_customer_demand_from_sql(password)
        except SqlImportNotConfiguredError as e:
            QMessageBox.warning(self, "尚未設定查詢", str(e))
            self.status_label.setText("")
            return
        except UnsafeSqlError as e:
            QMessageBox.critical(self, "查詢被拒絕", str(e))
            self.status_label.setText("")
            return
        except Exception as e:
            QMessageBox.critical(self, "匯入失敗", str(e))
            self.status_label.setText("")
            return
        count = result.get("count", 0)
        self.status_label.setText(f"匯入完成，共 {count} 筆。")
        QMessageBox.information(self, "完成", f"已從 SQL Server 匯入「{label}」，共 {count} 筆。")

    def _fill_table(self, columns, rows):
        self.table.clear()
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, col in enumerate(columns):
                value = row.get(col, "")
                self.table.setItem(r, c, QTableWidgetItem(str(value)))
