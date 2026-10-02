import json

from PyQt6.QtCore import Qt, QDate
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QDateEdit, QCheckBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QAbstractItemView
)

from services.audit_log_service import AuditLogService
from services.table_export_service import TableExportService
from services.user_auth_service import UserAuthService
from services.role_permission_service import RolePermissionService


class AuditCenterPage(QWidget):
    def __init__(self):
        super().__init__()
        self.build_ui()
        self.refresh_filters()
        self.refresh_data()

    def build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 18)
        root.setSpacing(10)

        title = QLabel("資料歷程 / 操作紀錄 / 稽核中心")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        sub = QLabel("查看 TACO 重要資料異動、登入、匯入、採購、庫存、備份與系統管理紀錄。稽核紀錄本身不提供人工修改。")
        sub.setObjectName("pageSubtitle")
        sub.setProperty("muted", True)
        sub.setWordWrap(True)
        root.addWidget(sub)

        summary = QHBoxLayout()
        self.total_label = QLabel("全部紀錄：0")
        self.today_label = QLabel("今日操作：0")
        self.error_label = QLabel("異常／失敗：0")
        self.integrity_label = QLabel("完整性：尚未檢查")
        for lab in [self.total_label, self.today_label, self.error_label, self.integrity_label]:
            lab.setStyleSheet("font-size:14px;font-weight:700;padding:7px 12px;border:1px solid palette(midlight);border-radius:8px;")
            summary.addWidget(lab)
        summary.addStretch()
        root.addLayout(summary)

        filters = QHBoxLayout()
        self.keyword = QLineEdit(); self.keyword.setPlaceholderText("搜尋產品編號、備註、修改前後內容..."); self.keyword.setMaximumWidth(300)
        self.module_combo = QComboBox(); self.action_combo = QComboBox(); self.user_combo = QComboBox(); self.severity_combo = QComboBox()
        self.use_dates = QCheckBox("日期區間")
        self.date_from = QDateEdit(QDate.currentDate().addDays(-30)); self.date_from.setCalendarPopup(True); self.date_from.setDisplayFormat("yyyy-MM-dd")
        self.date_to = QDateEdit(QDate.currentDate()); self.date_to.setCalendarPopup(True); self.date_to.setDisplayFormat("yyyy-MM-dd")
        filters.addWidget(self.keyword, 2)
        for label, wid in [("模組", self.module_combo), ("操作", self.action_combo), ("使用者", self.user_combo), ("等級", self.severity_combo)]:
            filters.addWidget(QLabel(label)); filters.addWidget(wid)
        filters.addWidget(self.use_dates); filters.addWidget(self.date_from); filters.addWidget(QLabel("～")); filters.addWidget(self.date_to)
        root.addLayout(filters)

        actions = QHBoxLayout()
        btn_refresh = QPushButton("🔄 重新整理"); btn_refresh.clicked.connect(self.refresh_data)
        btn_verify = QPushButton("🛡 驗證紀錄完整性"); btn_verify.clicked.connect(self.verify_integrity)
        btn_excel = QPushButton("📊 匯出 Excel"); btn_excel.clicked.connect(self.export_excel)
        btn_pdf = QPushButton("📄 匯出 PDF"); btn_pdf.clicked.connect(self.export_pdf)
        actions.addWidget(btn_refresh); actions.addWidget(btn_verify); actions.addStretch(); actions.addWidget(btn_excel); actions.addWidget(btn_pdf)
        root.addLayout(actions)

        self.table = QTableWidget()
        self.table.setColumnCount(12)
        self.table.setHorizontalHeaderLabels([
            "日期時間", "帳號", "顯示名稱", "角色", "模組", "操作", "資料編號",
            "修改前", "修改後", "結果", "等級", "備註"
        ])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(34)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        root.addWidget(self.table, 1)

        self.keyword.returnPressed.connect(self.refresh_data)
        for combo in [self.module_combo, self.action_combo, self.user_combo, self.severity_combo]:
            combo.currentIndexChanged.connect(self.refresh_data)
        self.use_dates.toggled.connect(self.refresh_data)
        self.date_from.dateChanged.connect(self.refresh_data); self.date_to.dateChanged.connect(self.refresh_data)

    def _allowed_rows(self, rows):
        role = RolePermissionService.role()
        user = UserAuthService.current_user() or {}
        username = str(user.get("username", ""))
        if role == "系統管理員" or role == "主管":
            return rows
        if role == "採購管理者":
            allowed_modules = {"採購建議", "供應商", "客戶需求", "庫存", "跨倉調撥", "登入", "匯出"}
            return [x for x in rows if str(x.get("module", "")) in allowed_modules]
        if role == "倉管":
            allowed_modules = {"庫存", "跨倉調撥", "客戶需求", "登入"}
            return [x for x in rows if str(x.get("module", "")) in allowed_modules]
        # 採購人員預設只看自己的紀錄
        return [x for x in rows if str((x.get("actor") or {}).get("username", "")) == username]

    def refresh_filters(self):
        values = AuditLogService.distinct_values()
        current = {
            "module": self.module_combo.currentText() if self.module_combo.count() else "全部",
            "action": self.action_combo.currentText() if self.action_combo.count() else "全部",
            "user": self.user_combo.currentText() if self.user_combo.count() else "全部",
            "severity": self.severity_combo.currentText() if self.severity_combo.count() else "全部",
        }
        for combo, key, source in [
            (self.module_combo, "module", values["modules"]), (self.action_combo, "action", values["actions"]),
            (self.user_combo, "user", values["users"]), (self.severity_combo, "severity", values["severities"])
        ]:
            combo.blockSignals(True); combo.clear(); combo.addItem("全部"); combo.addItems(source)
            idx = combo.findText(current[key]); combo.setCurrentIndex(max(0, idx)); combo.blockSignals(False)

    @staticmethod
    def _fmt(value):
        if value in (None, "", [], {}):
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return str(value)

    def refresh_data(self):
        self.refresh_filters()
        date_from = self.date_from.date().toString("yyyy-MM-dd") if self.use_dates.isChecked() else ""
        date_to = self.date_to.date().toString("yyyy-MM-dd") if self.use_dates.isChecked() else ""
        rows = AuditLogService.query_logs(
            keyword=self.keyword.text(), module=self.module_combo.currentText(), action=self.action_combo.currentText(),
            username=self.user_combo.currentText(), severity=self.severity_combo.currentText(), date_from=date_from, date_to=date_to,
        )
        rows = self._allowed_rows(rows)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            actor = row.get("actor") or {}
            values = [
                row.get("timestamp", ""), actor.get("username", ""), actor.get("display_name", ""), actor.get("role", ""),
                row.get("module", ""), row.get("action", ""), row.get("record_id", ""), row.get("before"), row.get("after"),
                row.get("result", ""), row.get("severity", ""), row.get("note", "")
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(self._fmt(value)); item.setToolTip(self._fmt(value)); self.table.setItem(r, c, item)
        stats = AuditLogService.stats()
        self.total_label.setText(f"全部紀錄：{stats['total']:,}")
        self.today_label.setText(f"今日操作：{stats['today']:,}")
        self.error_label.setText(f"異常／失敗：{stats['errors']:,}")

    def verify_integrity(self):
        result = AuditLogService.verify_integrity()
        if result.get("ok"):
            self.integrity_label.setText(f"完整性：✅ {result.get('checked',0)} 筆通過")
            QMessageBox.information(self, "稽核紀錄完整性", f"共驗證 {result.get('checked',0)} 筆紀錄，雜湊鏈完整。")
        else:
            self.integrity_label.setText("完整性：❌ 發現異常")
            QMessageBox.warning(self, "稽核紀錄完整性異常", f"第 {result.get('broken_at')} 筆發現問題：{result.get('reason')}")

    def export_excel(self):
        TableExportService.export_tables_excel(self, [("稽核紀錄", self.table)], "TACO_稽核紀錄.xlsx")

    def export_pdf(self):
        TableExportService.export_tables_pdf(self, [("稽核紀錄", self.table)], "TACO 稽核紀錄", "TACO_稽核紀錄.pdf")
