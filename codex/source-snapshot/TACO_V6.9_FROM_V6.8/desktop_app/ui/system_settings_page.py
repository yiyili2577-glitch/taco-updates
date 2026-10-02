import urllib.request

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QTabWidget, QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QCheckBox,
    QGroupBox, QMessageBox, QFileDialog, QFrame, QColorDialog, QSizePolicy,
    QTableWidget, QTableWidgetItem, QHeaderView, QInputDialog, QAbstractItemView, QApplication
)

from services.warehouse_service import WarehouseService
from services.system_settings_service import SystemSettingsService
from services.user_auth_service import UserAuthService
from services.role_permission_service import RolePermissionService
from services.data_maintenance_service import DataMaintenanceService
from services.audit_log_service import AuditLogService
from services.build_config import BuildConfig
from services.license_client_service import LicenseClientService
from services.update_service import UpdateService


class SystemSettingsPage(QWidget):
    FIELD_WIDTH = 620
    SMALL_FIELD_WIDTH = 280
    CARD_WIDTH = 980

    def __init__(self):
        super().__init__()
        self.color_buttons = {}
        self.build_ui()
        self.load_values()

    def _form_box(self, title):
        box = QGroupBox(title)
        box.setMaximumWidth(self.CARD_WIDTH)
        box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(8)
        return box, form

    def _field(self, widget, width=None):
        widget.setMaximumWidth(width or self.FIELD_WIDTH)
        widget.setMinimumWidth(min(240, width or self.FIELD_WIDTH))
        return widget

    def _left_row(self, *widgets):
        row = QHBoxLayout(); row.setSpacing(8)
        for w in widgets:
            row.addWidget(w)
        row.addStretch()
        return row

    def build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 18)
        title = QLabel("系統設定"); title.setObjectName("pageTitle")
        sub = QLabel("集中管理倉庫、採購預設值、版本授權、外觀配色、匯出、帳號與 ERP 連線設定。"); sub.setObjectName("pageSubtitle")
        sub.setProperty("muted", True)
        root.addWidget(title); root.addWidget(sub)
        self.tabs = QTabWidget(); root.addWidget(self.tabs, 1)
        self._warehouse_tab(); self._purchase_tab(); self._license_tab(); self._appearance_tab()
        self._export_tab(); self._account_tab(); self._update_tab(); self._connection_tab(); self._maintenance_tab()

    def _warehouse_tab(self):
        w = QWidget(); lay = QVBoxLayout(w); lay.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        box, form = self._form_box("倉庫管理")
        names = WarehouseService.load_names()
        self.wh_inputs = [self._field(QLineEdit(names[i])) for i in range(3)]
        for i, edit in enumerate(self.wh_inputs): form.addRow(f"倉庫 {i+1} 名稱", edit)
        self.container_cbm = self._field(QDoubleSpinBox(), self.SMALL_FIELD_WIDTH)
        self.container_cbm.setRange(1, 200); self.container_cbm.setDecimals(2); self.container_cbm.setSuffix(" CBM")
        form.addRow("預設進口貨櫃容量", self.container_cbm)
        btn = QPushButton("💾 儲存倉庫設定"); btn.clicked.connect(self.save_warehouse)
        lay.addWidget(box); lay.addLayout(self._left_row(btn)); lay.addStretch(); self.tabs.addTab(w, "倉庫管理")

    def _purchase_tab(self):
        w = QWidget(); lay = QVBoxLayout(w); lay.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        box, form = self._form_box("採購／安全庫存預設值")
        self.safety = self._field(QDoubleSpinBox(), self.SMALL_FIELD_WIDTH); self.safety.setRange(0,24); self.safety.setSingleStep(0.5)
        self.production = self._field(QSpinBox(), self.SMALL_FIELD_WIDTH); self.production.setRange(0,365)
        self.shipping = self._field(QSpinBox(), self.SMALL_FIELD_WIDTH); self.shipping.setRange(0,365)
        self.customs = self._field(QSpinBox(), self.SMALL_FIELD_WIDTH); self.customs.setRange(0,365)
        self.moq = self._field(QSpinBox(), self.SMALL_FIELD_WIDTH); self.moq.setRange(0,100000000)
        self.multiple = self._field(QSpinBox(), self.SMALL_FIELD_WIDTH); self.multiple.setRange(1,100000000)
        for label, wid in [("預設安全庫存月",self.safety),("預設生產天數",self.production),("預設運輸天數",self.shipping),("預設報關入庫天數",self.customs),("預設 MOQ",self.moq),("預設採購倍數",self.multiple)]: form.addRow(label,wid)
        note = QLabel("此頁設定為新增供應商／採購條件的預設值；既有產品供應商條件不會被批次覆寫。"); note.setProperty("muted", True)
        btn = QPushButton("💾 儲存採購預設值"); btn.clicked.connect(self.save_purchase)
        lay.addWidget(box); lay.addWidget(note); lay.addLayout(self._left_row(btn)); lay.addStretch(); self.tabs.addTab(w,"採購 / 安全庫存")

    def _license_tab(self):
        w = QWidget(); lay = QVBoxLayout(w); lay.setContentsMargins(8,8,8,8)
        self.license_status = QLabel(""); self.license_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.license_status.setStyleSheet("font-size:16px;font-weight:800;padding:10px;")
        lay.addWidget(self.license_status)

        self.license_credential_status = QLabel("")
        self.license_credential_status.setWordWrap(True)
        self.license_credential_status.setMaximumWidth(self.CARD_WIDTH)
        self.license_credential_status.setStyleSheet(
            "QLabel{background:#F6F8FA;border:1px solid #D8DEE4;border-radius:9px;padding:10px 12px;color:#334155;}"
        )
        lay.addWidget(self.license_credential_status)

        cards = QHBoxLayout(); cards.setSpacing(12); self.tier_buttons = {}
        for tier in ["general","intermediate","advanced"]:
            frame = QFrame(); frame.setObjectName("tierCard"); frame.setStyleSheet("QFrame#tierCard{border:1px solid palette(midlight);border-radius:12px;padding:4px;}")
            fl = QVBoxLayout(frame); fl.setContentsMargins(14,12,14,12); fl.setSpacing(7)
            name = QLabel(SystemSettingsService.TIER_NAMES[tier]); name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name.setStyleSheet("font-size:23px;font-weight:900;padding:5px;")
            fl.addWidget(name)
            for feature in SystemSettingsService.TIER_FEATURES[tier]:
                lab = QLabel("✓ " + feature); lab.setWordWrap(True); lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lab.setStyleSheet("font-size:14px;padding:3px 4px;")
                fl.addWidget(lab)
            fl.addStretch()
            btn = QPushButton("選擇 / 測試此版本"); btn.setMinimumHeight(38)
            btn.clicked.connect(lambda _=False,t=tier:self.select_tier(t)); self.tier_buttons[tier]=btn; fl.addWidget(btn)
            cards.addWidget(frame, 1)
        lay.addLayout(cards)

        self.dev_mode = QCheckBox("開發測試模式（開發期間可切換三種版本；正式販售由購買授權驗證決定）")
        lay.addWidget(self.dev_mode)

        auth_box, form = self._form_box("正式授權")
        self.license_server = self._field(QLineEdit()); self.license_server.setPlaceholderText("授權伺服器 API URL")
        form.addRow("授權伺服器", self.license_server)
        explain = QLabel(
            "「重新驗證目前授權」只會重新確認這台電腦先前已合法保存的 License，"
            "不會免費升級版本；要更換授權時才使用新的 Token。"
        )
        explain.setWordWrap(True); explain.setProperty("muted", True)
        form.addRow("", explain)
        lay.addWidget(auth_box)

        self.btn_reverify_license = QPushButton("🔄 重新驗證目前授權")
        self.btn_reverify_license.clicked.connect(self.reverify_saved_license)
        self.btn_use_new_license = QPushButton("🔑 使用新的授權 Token")
        self.btn_use_new_license.clicked.connect(self.show_new_license_input)
        lay.addLayout(self._left_row(self.btn_reverify_license, self.btn_use_new_license))

        self.new_license_box = QGroupBox("輸入新的授權 Token")
        new_form = QFormLayout(self.new_license_box)
        self.license_key = self._field(QLineEdit()); self.license_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.license_key.setPlaceholderText("貼上新取得的授權 Token；成功後會以 Windows DPAPI 安全保存")
        new_form.addRow("新授權 Token", self.license_key)
        new_note = QLabel("成功啟用新 License 後，畫面不會顯示或回填已保存的 Token 明碼。")
        new_note.setWordWrap(True); new_note.setProperty("muted", True)
        new_form.addRow("", new_note)
        new_row = QHBoxLayout()
        self.btn_activate_new_license = QPushButton("🔐 驗證並啟用新授權")
        self.btn_activate_new_license.clicked.connect(self.activate_new_license)
        self.btn_cancel_new_license = QPushButton("取消")
        self.btn_cancel_new_license.clicked.connect(self.hide_new_license_input)
        new_row.addWidget(self.btn_activate_new_license); new_row.addWidget(self.btn_cancel_new_license); new_row.addStretch()
        new_form.addRow("", new_row)
        self.new_license_box.hide()
        lay.addWidget(self.new_license_box)

        lay.addStretch(); self.tabs.addTab(w,"ERP 版本 / 授權")
        if BuildConfig.is_production():
            self.dev_mode.setChecked(False); self.dev_mode.hide()
            for _btn in self.tier_buttons.values():
                _btn.setText("正式版由 License 決定"); _btn.setEnabled(False)

    def _appearance_tab(self):
        w = QWidget(); lay = QVBoxLayout(w); lay.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        box, form = self._form_box("整體版面與文字配色")
        self.theme_preset = self._field(QComboBox(), 360)
        for key, spec in SystemSettingsService.THEME_PRESETS.items(): self.theme_preset.addItem(spec["name"], key)
        self.theme_preset.currentIndexChanged.connect(self.apply_preset_preview)
        form.addRow("配色範本", self.theme_preset)
        color_defs = [
            ("window_bg","視窗背景"),("content_bg","內容背景"),("card_bg","卡片 / 表格背景"),("sidebar_bg","功能表背景"),
            ("menu_text","功能表文字"),("content_text","內容主要文字"),("muted_text","說明 / 次要文字"),("accent","重點色"),
            ("border","框線顏色"),("table_header_bg","表頭背景"),
        ]
        for key, label in color_defs:
            btn = QPushButton(); btn.setMinimumWidth(210); btn.setMaximumWidth(260); btn.setMinimumHeight(32)
            btn.clicked.connect(lambda _=False,k=key:self.choose_color(k)); self.color_buttons[key]=btn; form.addRow(label, btn)
        note = QLabel("功能表文字與內容文字分開設定；切換深色背景時可個別調整，避免文字看不清楚。")
        note.setProperty("muted", True)
        save = QPushButton("🎨 儲存並立即套用配色"); save.setProperty("buttonRole","primary"); save.clicked.connect(self.save_appearance)
        reset = QPushButton("↺ 套用目前範本"); reset.clicked.connect(self.apply_preset_preview)
        lay.addWidget(box); lay.addWidget(note); lay.addLayout(self._left_row(save, reset)); lay.addStretch(); self.tabs.addTab(w,"外觀 / 配色")

    def _export_tab(self):
        w=QWidget(); lay=QVBoxLayout(w); lay.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft)
        box,form=self._form_box("匯出設定")
        row=QHBoxLayout(); self.export_folder=self._field(QLineEdit(),560); browse=QPushButton("選擇..."); browse.clicked.connect(self.choose_export_folder); row.addWidget(self.export_folder); row.addWidget(browse); row.addStretch()
        wrapper=QWidget(); wrapper.setLayout(row); form.addRow("預設匯出資料夾",wrapper)
        self.include_timestamp=QCheckBox("檔名自動加入日期時間"); self.default_excel=QCheckBox("預設提供 Excel"); self.default_pdf=QCheckBox("預設提供 PDF")
        form.addRow("",self.include_timestamp); form.addRow("",self.default_excel); form.addRow("",self.default_pdf)
        btn=QPushButton("💾 儲存匯出設定"); btn.clicked.connect(self.save_export)
        lay.addWidget(box); lay.addLayout(self._left_row(btn)); lay.addStretch(); self.tabs.addTab(w,"匯出設定")

    def _account_tab(self):
        w=QWidget(); lay=QVBoxLayout(w); lay.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft)

        current = UserAuthService.current_user() or {}
        box,form=self._form_box("目前登入帳號")
        self.account_username = QLabel(str(current.get("username", "")))
        self.display_name=self._field(QLineEdit())
        self.email=self._field(QLineEdit())
        self.company=self._field(QLineEdit())
        self.current_role_label = QLabel(str(current.get("role", "")))
        form.addRow("登入帳號", self.account_username)
        form.addRow("顯示名稱",self.display_name)
        form.addRow("Email",self.email)
        form.addRow("角色", self.current_role_label)
        form.addRow("公司名稱",self.company)
        save_profile=QPushButton("💾 儲存我的帳號資料"); save_profile.clicked.connect(self.save_account)
        change_pwd=QPushButton("🔑 修改我的密碼"); change_pwd.clicked.connect(self.change_my_password)
        lay.addWidget(box); lay.addLayout(self._left_row(save_profile, change_pwd))

        manage = QGroupBox("使用者帳號管理（僅系統管理員）")
        manage.setMaximumWidth(self.CARD_WIDTH)
        ml = QVBoxLayout(manage)
        self.user_table = QTableWidget(0, 7)
        self.user_table.setHorizontalHeaderLabels(["登入帳號","顯示名稱","Email","角色","公司","狀態","最後登入"])
        self.user_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.user_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.user_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.user_table.horizontalHeader().setStretchLastSection(True)
        self.user_table.setMaximumHeight(230)
        ml.addWidget(self.user_table)

        create_box = QGroupBox("新增使用者")
        cf = QFormLayout(create_box)
        self.new_username = self._field(QLineEdit(), 300)
        self.new_display = self._field(QLineEdit(), 300)
        self.new_email = self._field(QLineEdit(), 360)
        self.new_role = self._field(QComboBox(), 260); self.new_role.addItems(UserAuthService.ROLE_LABELS)
        self.new_company = self._field(QLineEdit(), 360)
        self.new_password = self._field(QLineEdit(), 300); self.new_password.setEchoMode(QLineEdit.EchoMode.Password)
        cf.addRow("登入帳號", self.new_username); cf.addRow("顯示名稱", self.new_display)
        cf.addRow("Email", self.new_email); cf.addRow("角色", self.new_role)
        cf.addRow("公司名稱", self.new_company); cf.addRow("初始密碼", self.new_password)
        ml.addWidget(create_box)
        row=QHBoxLayout()
        self.btn_create_user=QPushButton("＋ 建立使用者"); self.btn_create_user.clicked.connect(self.create_user)
        self.btn_reset_user_pwd=QPushButton("🔑 重設選取帳號密碼"); self.btn_reset_user_pwd.clicked.connect(self.reset_selected_password)
        self.btn_toggle_user=QPushButton("啟用 / 停用選取帳號"); self.btn_toggle_user.clicked.connect(self.toggle_selected_user)
        self.btn_delete_user=QPushButton("🗑 刪除選取帳號"); self.btn_delete_user.clicked.connect(self.delete_selected_user)
        for b in [self.btn_create_user,self.btn_reset_user_pwd,self.btn_toggle_user,self.btn_delete_user]: row.addWidget(b)
        row.addStretch(); ml.addLayout(row)
        lay.addWidget(manage)
        note=QLabel("密碼只以 PBKDF2 雜湊方式保存在本機 users.json，不保存明碼。正式多人雲端版可再改由伺服器驗證。")
        note.setProperty("muted",True); lay.addWidget(note); lay.addStretch(); self.tabs.addTab(w,"使用者帳號")
        self.refresh_user_table()

    def refresh_user_table(self):
        if not hasattr(self, "user_table"):
            return
        users = UserAuthService.load_users()
        self.user_table.setRowCount(len(users))
        for r, u in enumerate(users):
            values = [u.get("username",""),u.get("display_name",""),u.get("email",""),u.get("role",""),u.get("company",""),"啟用" if u.get("enabled",True) else "停用",u.get("last_login_at","")]
            for c, v in enumerate(values):
                self.user_table.setItem(r,c,QTableWidgetItem(str(v)))
        admin = RolePermissionService.can_manage_users()
        multi_user_allowed = admin and SystemSettingsService.effective_has_tier("advanced")
        for b in [self.btn_create_user,self.btn_reset_user_pwd,self.btn_toggle_user,self.btn_delete_user]:
            b.setEnabled(multi_user_allowed)
            b.setToolTip("" if multi_user_allowed else "多使用者角色管理需要高級版與系統管理員權限。")
        self.new_username.setEnabled(multi_user_allowed); self.new_display.setEnabled(multi_user_allowed); self.new_email.setEnabled(multi_user_allowed); self.new_role.setEnabled(multi_user_allowed); self.new_company.setEnabled(multi_user_allowed); self.new_password.setEnabled(multi_user_allowed)

    def selected_username(self):
        row = self.user_table.currentRow() if hasattr(self, "user_table") else -1
        if row < 0:
            return ""
        item = self.user_table.item(row, 0)
        return item.text().strip() if item else ""

    def create_user(self):
        if not RolePermissionService.can_manage_users():
            QMessageBox.warning(self,"權限不足","只有系統管理員可以建立使用者。")
            return
        try:
            UserAuthService.create_user(self.new_username.text(),self.new_password.text(),self.new_display.text(),self.new_email.text(),self.new_role.currentText(),self.new_company.text(),True)
            self.new_username.clear(); self.new_password.clear(); self.new_display.clear(); self.new_email.clear(); self.new_company.clear()
            self.refresh_user_table(); QMessageBox.information(self,"完成","使用者已建立。")
        except Exception as e:
            QMessageBox.warning(self,"建立失敗",str(e))

    def reset_selected_password(self):
        username=self.selected_username()
        if not username:
            QMessageBox.information(self,"請選擇帳號","請先在使用者表格選取一個帳號。")
            return
        pwd, ok = QInputDialog.getText(self,"重設密碼",f"輸入 {username} 的新密碼（至少 6 碼）：",QLineEdit.EchoMode.Password)
        if not ok: return
        try:
            UserAuthService.change_password(username,pwd); QMessageBox.information(self,"完成","密碼已重設。")
        except Exception as e: QMessageBox.warning(self,"重設失敗",str(e))

    def toggle_selected_user(self):
        username=self.selected_username()
        if not username: return
        current=next((u for u in UserAuthService.load_users() if str(u.get("username","")).lower()==username.lower()),None)
        if not current: return
        if UserAuthService.current_user() and UserAuthService.current_user().get("username")==username and current.get("enabled",True):
            QMessageBox.warning(self,"不能停用自己","目前登入中的帳號不能停用自己。")
            return
        try:
            UserAuthService.update_user(username,enabled=not bool(current.get("enabled",True))); self.refresh_user_table()
        except Exception as e: QMessageBox.warning(self,"修改失敗",str(e))

    def delete_selected_user(self):
        username=self.selected_username()
        if not username: return
        if UserAuthService.current_user() and UserAuthService.current_user().get("username")==username:
            QMessageBox.warning(self,"不能刪除自己","目前登入中的帳號不能刪除自己。")
            return
        if QMessageBox.question(self,"刪除使用者",f"確定刪除帳號 {username} 嗎？") != QMessageBox.StandardButton.Yes: return
        try:
            UserAuthService.delete_user(username); self.refresh_user_table()
        except Exception as e: QMessageBox.warning(self,"刪除失敗",str(e))

    def change_my_password(self):
        user=UserAuthService.current_user() or {}; username=str(user.get("username", ""))
        if not username: return
        pwd, ok = QInputDialog.getText(self,"修改密碼","輸入新密碼（至少 6 碼）：",QLineEdit.EchoMode.Password)
        if not ok: return
        try:
            UserAuthService.change_password(username,pwd); QMessageBox.information(self,"完成","密碼已修改。")
        except Exception as e: QMessageBox.warning(self,"修改失敗",str(e))

    def _update_tab(self):
        w=QWidget(); lay=QVBoxLayout(w); lay.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft)
        box,form=self._form_box("版本更新")
        self.version_label=QLabel(SystemSettingsService.CURRENT_VERSION); self.update_url=self._field(QLineEdit()); self.update_url.setPlaceholderText("例如 update.json / API URL"); self.last_checked=QLabel("尚未檢查")
        form.addRow("目前版本",self.version_label); form.addRow("更新檢查網址",self.update_url); form.addRow("上次檢查",self.last_checked)
        save=QPushButton("💾 儲存更新設定"); save.clicked.connect(self.save_update); check=QPushButton("🔄 檢查更新"); check.clicked.connect(self.check_update)
        self.btn_secure_update=QPushButton("⬇ 安全下載更新"); self.btn_secure_update.setEnabled(False); self.btn_secure_update.clicked.connect(self.download_secure_update)
        self._last_update_check=None
        lay.addWidget(box); lay.addLayout(self._left_row(save,check,self.btn_secure_update)); lay.addStretch(); self.tabs.addTab(w,"版本更新")

    def _connection_tab(self):
        w=QWidget(); lay=QVBoxLayout(w); lay.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft)
        box,form=self._form_box("ERP / SQL Server 連線設定")
        self.conn_mode=self._field(QComboBox(),420); self.conn_mode.addItems(["Excel / PDF","SQL Server"])
        self.server=self._field(QLineEdit()); self.database=self._field(QLineEdit()); self.username=self._field(QLineEdit()); self.password=self._field(QLineEdit()); self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.auth_type=self._field(QComboBox(),420); self.auth_type.addItems(["SQL Server 驗證","Windows 驗證"]); self.driver=self._field(QLineEdit()); self.timeout=self._field(QSpinBox(),self.SMALL_FIELD_WIDTH); self.timeout.setRange(1,60); self.read_only=QCheckBox("唯讀模式（建議保持開啟）")
        for label,wid in [("資料來源模式",self.conn_mode),("SQL Server",self.server),("Database",self.database),("帳號",self.username),("密碼（不儲存）",self.password),("驗證方式",self.auth_type),("ODBC Driver",self.driver),("逾時秒數",self.timeout),("",self.read_only)]: form.addRow(label,wid)
        save=QPushButton("💾 儲存連線設定"); save.clicked.connect(self.save_connection); test=QPushButton("🔌 測試 SQL 連線"); test.clicked.connect(self.test_connection)
        note=QLabel("正式連線正航 ERP 時，建議由 IT 建立唯讀 SQL 帳號，避免桌面工具具有寫入 ERP 的權限。"); note.setProperty("muted",True)
        lay.addWidget(box); lay.addLayout(self._left_row(save,test)); lay.addWidget(note); lay.addStretch(); self.tabs.addTab(w,"連線資料")

    def _maintenance_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        status_box, status_form = self._form_box("資料儲存點")
        self.backup_latest_label = QLabel("尚無儲存點")
        self.backup_count_label = QLabel("0")
        self.backup_protect_label = QLabel("使用者帳號、版本授權、外觀與 ERP 連線設定不會被業務資料還原覆蓋。")
        self.backup_protect_label.setWordWrap(True)
        self.backup_protect_label.setProperty("muted", True)
        status_form.addRow("上一次儲存點", self.backup_latest_label)
        status_form.addRow("儲存點數量", self.backup_count_label)
        status_form.addRow("保留資料", self.backup_protect_label)

        self.btn_create_savepoint = QPushButton("💾 建立新儲存點")
        self.btn_create_savepoint.clicked.connect(self.create_data_savepoint)
        self.btn_restore_latest = QPushButton("↩ 還原上一次儲存點")
        self.btn_restore_latest.clicked.connect(self.restore_latest_savepoint)
        self.btn_refresh_backups = QPushButton("🔄 重新整理備份紀錄")
        self.btn_refresh_backups.clicked.connect(self.refresh_backup_history)

        lay.addWidget(status_box)
        lay.addLayout(self._left_row(self.btn_create_savepoint, self.btn_restore_latest, self.btn_refresh_backups))

        history = QGroupBox("備份紀錄")
        hl = QVBoxLayout(history)
        self.backup_table = QTableWidget(0, 7)
        self.backup_table.setHorizontalHeaderLabels(["建立時間", "類型", "版本", "建立者", "檔案數", "大小", "備註"])
        self.backup_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.backup_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.backup_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.backup_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.backup_table.horizontalHeader().setStretchLastSection(True)
        self.backup_table.setMinimumHeight(230)
        hl.addWidget(self.backup_table)
        row = QHBoxLayout()
        self.btn_restore_selected = QPushButton("↩ 還原選取儲存點")
        self.btn_restore_selected.clicked.connect(self.restore_selected_savepoint)
        self.btn_delete_backup = QPushButton("🗑 刪除選取備份")
        self.btn_delete_backup.clicked.connect(self.delete_selected_savepoint)
        row.addWidget(self.btn_restore_selected)
        row.addWidget(self.btn_delete_backup)
        row.addStretch()
        hl.addLayout(row)
        lay.addWidget(history)

        danger = QGroupBox("⚠ 危險操作")
        danger.setStyleSheet("QGroupBox{border:1px solid #D9534F;border-radius:8px;margin-top:8px;padding-top:10px;} QGroupBox::title{color:#B42318;font-weight:800;}")
        dl = QVBoxLayout(danger)
        warn = QLabel(
            "全部業務資料刪除會清除產品、供應商、三倉庫存、客戶需求、產品對應、採購 / Dashboard 快照、履約與調撥等 data 資料。\n"
            "系統會先自動建立安全儲存點；使用者帳號與 system_settings.json 會保留。"
        )
        warn.setWordWrap(True)
        warn.setStyleSheet("color:#B42318;font-weight:700;")
        dl.addWidget(warn)
        self.btn_clear_business = QPushButton("🧨 全部業務資料刪除")
        self.btn_clear_business.setStyleSheet("QPushButton{background:#B42318;color:white;font-weight:800;padding:8px 14px;border-radius:7px;}")
        self.btn_clear_business.clicked.connect(self.clear_all_business_data)
        dl.addLayout(self._left_row(self.btn_clear_business))
        lay.addWidget(danger)

        gate_note = QLabel("此頁僅限：高級版＋系統管理員。主管、採購人員、倉管與一般 / 中階版不可執行。")
        gate_note.setProperty("muted", True)
        lay.addWidget(gate_note)
        lay.addStretch()
        self.tabs.addTab(w, "資料維護 / 備份")
        self.refresh_backup_history()

    def _maintenance_allowed(self):
        return RolePermissionService.can_manage_users() and SystemSettingsService.effective_has_tier("advanced")

    @staticmethod
    def _human_bytes(value):
        size = float(value or 0)
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"

    def refresh_backup_history(self):
        if not hasattr(self, "backup_table"):
            return
        items = DataMaintenanceService.list_savepoints()
        self.backup_table.setRowCount(len(items))
        for r, item in enumerate(items):
            actor = item.get("actor", {}) or {}
            values = [
                item.get("created_at", ""),
                item.get("kind", ""),
                item.get("version", ""),
                actor.get("display_name") or actor.get("username", ""),
                item.get("file_count", 0),
                self._human_bytes(item.get("total_bytes", 0)),
                item.get("note", ""),
            ]
            for c, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if c == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, str(item.get("id", "")))
                self.backup_table.setItem(r, c, cell)
        latest = items[0] if items else None
        self.backup_count_label.setText(str(len(items)))
        if latest:
            actor = latest.get("actor", {}) or {}
            who = actor.get("display_name") or actor.get("username", "") or "未知"
            self.backup_latest_label.setText(f"{latest.get('created_at','')} ｜ {who} ｜ {latest.get('version','')}")
        else:
            self.backup_latest_label.setText("尚無儲存點")
        allowed = self._maintenance_allowed()
        for b in [self.btn_create_savepoint, self.btn_restore_latest, self.btn_restore_selected, self.btn_delete_backup, self.btn_clear_business]:
            b.setEnabled(allowed)
            b.setToolTip("" if allowed else "需要高級版＋系統管理員權限。")

    def _selected_savepoint_id(self):
        row = self.backup_table.currentRow() if hasattr(self, "backup_table") else -1
        if row < 0:
            return ""
        item = self.backup_table.item(row, 0)
        return str(item.data(Qt.ItemDataRole.UserRole) or "") if item else ""

    def create_data_savepoint(self):
        if not self._maintenance_allowed():
            QMessageBox.warning(self, "權限不足", "資料維護需要高級版＋系統管理員權限。")
            return
        note, ok = QInputDialog.getText(self, "建立資料儲存點", "可輸入備註（可留白）：")
        if not ok:
            return
        try:
            item = DataMaintenanceService.create_savepoint(note=note, kind="manual")
            self.refresh_backup_history()
            QMessageBox.information(self, "儲存點完成", f"已建立資料儲存點：\n{item.get('created_at')}\n檔案：{item.get('file_count',0)} 個")
        except Exception as e:
            QMessageBox.critical(self, "建立失敗", str(e))

    def _confirm_restore(self, savepoint_id):
        items = {str(x.get("id")): x for x in DataMaintenanceService.list_savepoints()}
        selected = items.get(str(savepoint_id))
        if not selected:
            QMessageBox.warning(self, "找不到儲存點", "指定的儲存點不存在。")
            return False
        answer = QMessageBox.question(
            self,
            "確認資料還原",
            f"即將把業務資料還原至：\n{selected.get('created_at','')}\n備註：{selected.get('note','')}\n\n"
            "還原前會再自動建立一個安全儲存點。使用者帳號與系統設定不會被覆蓋。\n\n確定繼續嗎？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        text, ok = QInputDialog.getText(self, "最後確認", "請輸入「還原」後繼續：")
        return bool(ok and text.strip() == "還原")

    def restore_latest_savepoint(self):
        latest = DataMaintenanceService.latest_savepoint()
        if not latest:
            QMessageBox.information(self, "沒有儲存點", "目前沒有資料儲存點可還原。")
            return
        self._restore_savepoint(str(latest.get("id", "")))

    def restore_selected_savepoint(self):
        savepoint_id = self._selected_savepoint_id()
        if not savepoint_id:
            QMessageBox.information(self, "請選擇備份", "請先在備份紀錄選取一筆。")
            return
        self._restore_savepoint(savepoint_id)

    def _restore_savepoint(self, savepoint_id):
        if not self._maintenance_allowed():
            QMessageBox.warning(self, "權限不足", "資料維護需要高級版＋系統管理員權限。")
            return
        if not self._confirm_restore(savepoint_id):
            return
        try:
            result = DataMaintenanceService.restore_savepoint(savepoint_id, create_safety_backup=True)
            self.refresh_backup_history()
            QMessageBox.information(
                self,
                "資料還原完成",
                f"已還原 {len(result.get('restored_entries', []))} 個業務資料項目。\n"
                "還原前的目前資料也已自動建立安全儲存點。\n\n建議關閉並重新開啟 TACO，讓所有頁面重新載入資料。",
            )
        except Exception as e:
            QMessageBox.critical(self, "還原失敗", str(e))

    def delete_selected_savepoint(self):
        if not self._maintenance_allowed():
            return
        savepoint_id = self._selected_savepoint_id()
        if not savepoint_id:
            QMessageBox.information(self, "請選擇備份", "請先選取要刪除的備份紀錄。")
            return
        if QMessageBox.question(self, "刪除備份", "只會刪除此備份紀錄，不會刪除目前業務資料。確定嗎？") != QMessageBox.StandardButton.Yes:
            return
        try:
            DataMaintenanceService.delete_savepoint(savepoint_id)
            self.refresh_backup_history()
        except Exception as e:
            QMessageBox.warning(self, "刪除失敗", str(e))

    def clear_all_business_data(self):
        if not self._maintenance_allowed():
            QMessageBox.warning(self, "權限不足", "全部資料刪除只允許高級版系統管理員執行。")
            return
        answer = QMessageBox.warning(
            self,
            "高風險操作：全部業務資料刪除",
            "此操作會清除目前所有業務資料。\n\n"
            "會保留：使用者帳號、系統設定、版本授權、外觀與 ERP 連線設定。\n"
            "刪除前會自動建立安全儲存點。\n\n是否繼續？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        text, ok = QInputDialog.getText(self, "最後確認", "請完整輸入：刪除全部業務資料")
        if not ok or text.strip() != "刪除全部業務資料":
            QMessageBox.information(self, "已取消", "確認文字不符，沒有刪除任何資料。")
            return
        try:
            result = DataMaintenanceService.clear_business_data(create_safety_backup=True)
            self.refresh_backup_history()
            QMessageBox.information(
                self,
                "清除完成",
                f"已清除 {len(result.get('deleted_entries', []))} 個業務資料項目。\n"
                "刪除前狀態已自動備份，可從本頁還原。\n\n建議關閉並重新開啟 TACO。",
            )
        except Exception as e:
            QMessageBox.critical(self, "清除失敗", str(e))

    def load_values(self):
        s=SystemSettingsService.load()
        self.container_cbm.setValue(float(s["warehouse"].get("container_cbm",66.5)))
        p=s["purchase"]; self.safety.setValue(float(p.get("default_safety_months",2))); self.production.setValue(int(p.get("default_production_days",45))); self.shipping.setValue(int(p.get("default_shipping_days",14))); self.customs.setValue(int(p.get("default_customs_days",7))); self.moq.setValue(int(p.get("default_moq",0))); self.multiple.setValue(int(p.get("default_multiple",1)))
        lic=s["license"]; self.dev_mode.setChecked(False if BuildConfig.is_production() else bool(lic.get("development_mode",True))); self.license_key.setText(""); self.license_server.setText(str(lic.get("license_server_url","")));
        self.hide_new_license_input()
        self._refresh_license_controls()
        app=s.get("appearance",{}); preset=str(app.get("preset","warm")); idx=self.theme_preset.findData(preset); self.theme_preset.blockSignals(True); self.theme_preset.setCurrentIndex(max(0,idx)); self.theme_preset.blockSignals(False); self._set_color_buttons(app)
        e=s["export"]; self.export_folder.setText(str(e.get("default_folder","exports"))); self.include_timestamp.setChecked(bool(e.get("include_timestamp",True))); self.default_excel.setChecked(bool(e.get("default_excel",True))); self.default_pdf.setChecked(bool(e.get("default_pdf",True)))
        current=UserAuthService.current_user() or {}
        self.display_name.setText(str(current.get("display_name", ""))); self.email.setText(str(current.get("email", ""))); self.company.setText(str(current.get("company", ""))); self.current_role_label.setText(str(current.get("role", ""))); self.account_username.setText(str(current.get("username", ""))); self.refresh_user_table()
        u=s["update"]; self.version_label.setText(SystemSettingsService.CURRENT_VERSION); self.update_url.setText(str(u.get("update_url",""))); self.last_checked.setText(str(u.get("last_checked_at","") or "尚未檢查"))
        c=s["connection"]; self.conn_mode.setCurrentText(str(c.get("mode","Excel / PDF"))); self.server.setText(str(c.get("server",""))); self.database.setText(str(c.get("database",""))); self.username.setText(str(c.get("username",""))); self.auth_type.setCurrentText(str(c.get("auth_type","SQL Server 驗證"))); self.driver.setText(str(c.get("driver","ODBC Driver 18 for SQL Server"))); self.timeout.setValue(int(c.get("timeout",5))); self.read_only.setChecked(bool(c.get("read_only",True)))
        self.apply_tier_tabs()

    def apply_tier_tabs(self):
        # 0 倉庫、1 採購、2 授權、3 外觀、4 匯出、5 帳號、6 更新、7 連線、8 資料維護
        intermediate = SystemSettingsService.effective_has_tier("intermediate")
        advanced = SystemSettingsService.effective_has_tier("advanced")
        for idx in [0, 1]:
            self.tabs.setTabEnabled(idx, intermediate)
            self.tabs.setTabToolTip(idx, "" if intermediate else "需要中階版或以上版本")
        # 登入帳號本身屬基礎安全功能；多使用者新增/停用/重設密碼仍由高級版控制。
        self.tabs.setTabEnabled(5, True)
        self.tabs.setTabToolTip(5, "")
        for idx in [6, 7]:
            self.tabs.setTabEnabled(idx, advanced)
            self.tabs.setTabToolTip(idx, "" if advanced else "需要高級版")
        maintenance_allowed = advanced and RolePermissionService.can_manage_users()
        self.tabs.setTabEnabled(8, maintenance_allowed)
        self.tabs.setTabToolTip(8, "" if maintenance_allowed else "需要高級版＋系統管理員權限")
        self.refresh_user_table()
        self.refresh_backup_history()

    def save_warehouse(self):
        WarehouseService.save_names([x.text().strip() for x in self.wh_inputs]); SystemSettingsService.update_section("warehouse",{"container_cbm":self.container_cbm.value()}); QMessageBox.information(self,"完成","三倉名稱與貨櫃容量已儲存。")

    def save_purchase(self):
        SystemSettingsService.update_section("purchase",{"default_safety_months":self.safety.value(),"default_production_days":self.production.value(),"default_shipping_days":self.shipping.value(),"default_customs_days":self.customs.value(),"default_moq":self.moq.value(),"default_multiple":self.multiple.value()}); QMessageBox.information(self,"完成","採購／安全庫存預設值已儲存。")

    def select_tier(self,tier):
        if BuildConfig.is_production():
            QMessageBox.information(self,"正式版本","正式 EXE 的版本層級只能由簽章 License 決定，不能在本機切換。")
            return
        if not self.dev_mode.isChecked(): QMessageBox.information(self,"需要購買授權","正式模式下，中階版與高級版需由購買／授權伺服器開通。若已購買，請在下方輸入 Token 並驗證。"); return
        SystemSettingsService.update_section("license",{"tier":tier,"development_mode":True,"license_status":"development"}); self._refresh_license_label(); self.apply_tier_tabs(); self._notify_main_window_permissions(); QMessageBox.information(self,"開發測試模式",f"已切換為 {SystemSettingsService.TIER_NAMES.get(tier)} 測試；功能權限已重新套用。")

    def show_new_license_input(self):
        self.new_license_box.show()
        self.license_key.clear()
        self.license_key.setFocus()

    def hide_new_license_input(self):
        if hasattr(self, "license_key"):
            self.license_key.clear()
        if hasattr(self, "new_license_box"):
            self.new_license_box.hide()

    def reverify_saved_license(self):
        if (not BuildConfig.is_production()) and self.dev_mode.isChecked():
            QMessageBox.information(self, "目前為開發模式", "若要測試正式購買授權，請先取消勾選「開發測試模式」。")
            return
        if not str(LicenseClientService.load_token() or "").strip():
            QMessageBox.information(
                self, "沒有已保存授權",
                "這台電腦目前沒有由 Windows DPAPI 保存的授權 Token。\n請按「使用新的授權 Token」進行啟用。",
            )
            self.show_new_license_input()
            return
        try:
            data = SystemSettingsService.verify_license("", self.license_server.text().strip())
            self.hide_new_license_input()
            self._refresh_license_controls(); self.apply_tier_tabs(); self._notify_main_window_permissions()
            QMessageBox.information(
                self, "重新驗證成功",
                f"已重新驗證目前保存的 {SystemSettingsService.TIER_NAMES.get(str(data.get('tier')),'一般版')} License。\n"
                "這是重新確認原本已核發的授權，不是免費升級。",
            )
        except Exception as e:
            # revoked / expired / device_revoked 等權威拒絕會由 service 層先失效舊 receipt。
            self._refresh_license_controls(); self.apply_tier_tabs(); self._notify_main_window_permissions()
            QMessageBox.warning(self, "授權重新驗證失敗", str(e))

    def activate_new_license(self):
        if (not BuildConfig.is_production()) and self.dev_mode.isChecked():
            QMessageBox.information(self, "目前為開發模式", "若要測試正式購買授權，請先取消勾選「開發測試模式」。")
            return
        token = self.license_key.text().strip()
        if not token:
            QMessageBox.information(self, "請輸入新授權 Token", "請先貼上新取得的授權 Token，再按「驗證並啟用新授權」。")
            self.license_key.setFocus()
            return
        try:
            data = SystemSettingsService.verify_license(token, self.license_server.text().strip())
            self.hide_new_license_input()
            self._refresh_license_controls(); self.apply_tier_tabs(); self._notify_main_window_permissions()
            QMessageBox.information(self, "授權成功", f"已啟用 {SystemSettingsService.TIER_NAMES.get(str(data.get('tier')),'一般版')}。")
        except Exception as e:
            # 使用新 Token 失敗時，底層只會在確認「拒絕的就是目前 License」時才清除舊 receipt。
            self._refresh_license_controls(); self.apply_tier_tabs(); self._notify_main_window_permissions()
            QMessageBox.warning(self, "新授權驗證失敗", str(e))

    # 保留舊方法名稱，避免其他頁面或舊測試仍呼叫 activate_license。
    def activate_license(self):
        self.activate_new_license()

    def _refresh_license_controls(self):
        self._refresh_license_label()
        if not BuildConfig.is_production():
            saved = bool(str(LicenseClientService.load_token() or "").strip())
            self.btn_reverify_license.setEnabled(saved)
            self.license_credential_status.setText(
                "開發版可使用測試模式；若要測正式 License，請關閉開發測試模式。"
                + (" 此電腦另有已保存的測試授權 Token。" if saved else "")
            )
            return

        info = LicenseClientService.local_credential_status()
        state = str(info.get("state", "unlicensed"))
        token_saved = bool(info.get("token_saved"))
        receipt = info.get("receipt") if isinstance(info.get("receipt"), dict) else {}
        company = str(receipt.get("company", "")).strip()
        license_id = str(receipt.get("license_id", "")).strip()
        exp = str(receipt.get("expires_at", "")).strip()
        offline_until = str(receipt.get("receipt_expires_at", "")).strip()
        identity = " / ".join(x for x in [company, license_id] if x)

        if state == "active":
            text = "✅ 正式 License 已驗證有效。"
            if identity: text += f" 目前授權：{identity}。"
            if exp: text += f" 正式到期：{exp}。"
            if offline_until: text += f" 本機離線收據有效至：{offline_until}。"
            if token_saved:
                text += " Windows 已安全保存 Token，可用「重新驗證目前授權」同步撤銷狀態並更新離線收據。"
        elif state == "receipt_expired":
            text = "⚠ 離線授權寬限已到期，TACO 已進入只讀／備份模式。可查看、備份與匯出資料，但新增、修改、刪除及高風險作業暫停；請連線重新驗證原授權。"
            if identity: text += f" 原授權：{identity}。"
            if token_saved: text += " Windows 仍安全保存原 Token，可直接按「重新驗證目前授權」。"
        elif state == "license_expired":
            text = "⚠ 原正式 License 已到期，TACO 已進入只讀／備份模式。可查看、備份與匯出資料，資料不會被刪除。"
            if identity: text += f" 原授權：{identity}。"
            if exp: text += f" 到期日：{exp}。"
            text += " 如已續約，可重新驗證；如取得新 License，請使用新的授權 Token。"
        elif state == "clock_rollback":
            text = "⏰ 偵測到 Windows 系統時間異常倒退，為防止延長離線授權，TACO 已進入只讀／備份模式。請校正系統時間並連線重新驗證。"
            if identity: text += f" 原授權：{identity}。"
            if token_saved: text += " Windows 仍安全保存原 Token。"
        elif state == "invalid_receipt":
            text = "❌ 本機授權收據驗證失敗或內容不可信，因此高級功能已停用。"
            if token_saved:
                text += " Windows 仍保存授權 Token；若收據只是損壞，可連線重新驗證。"
            else:
                text += " 請使用新的授權 Token 重新啟用。"
        elif state in {"revoked", "device_revoked", "server_denied"}:
            denial_message = str(info.get("denial_message", "")).strip()
            if state == "revoked":
                text = "⛔ License Server 已撤銷這組正式授權，因此目前只開放一般版功能。"
            elif state == "device_revoked":
                text = "⛔ License Server 已撤銷這台電腦的授權啟用，因此目前只開放一般版功能。"
            else:
                text = "⛔ License Server 已拒絕目前授權，因此目前只開放一般版功能。"
            if denial_message:
                text += f" 原因：{denial_message}"
            if token_saved:
                text += " 若管理端已修正授權狀態，可重新驗證；否則請使用新的授權 Token。"
            else:
                text += " 請由管理端處理後再重新啟用，或使用新的授權 Token。"
        elif state == "saved_token_only":
            text = (
                "ℹ 此電腦已由 Windows DPAPI 安全保存一組既有授權憑證，但目前沒有有效的離線收據。"
                " 按「重新驗證目前授權」只會確認原本已核發的 License，不會免費升級版本。"
            )
        else:
            text = "ℹ 此電腦尚未啟用正式 License，也沒有保存授權 Token。請使用新的授權 Token 進行第一次啟用。"

        self.license_credential_status.setText(text)
        self.btn_reverify_license.setEnabled(token_saved)
        self.btn_reverify_license.setToolTip(
            "重新向 License Server 驗證 Windows DPAPI 已保存的既有 Token；不會改變成未購買的版本。"
            if token_saved else "此電腦沒有已保存的授權 Token。"
        )
        self.btn_use_new_license.setText("🔑 更換 / 使用新的授權 Token" if token_saved else "🔑 使用新的授權 Token")

    def _refresh_license_label(self):
        s=SystemSettingsService.load(); lic=s["license"]
        if BuildConfig.is_production():
            info = LicenseClientService.local_credential_status()
            state = str(info.get("state", "unlicensed"))
            receipt = info.get("receipt") if isinstance(info.get("receipt"), dict) else {}
            if state == "active":
                tier = str(receipt.get("tier", "general")); status = "正式授權有效"
            elif state == "receipt_expired":
                tier = "general"; status = "只讀／備份模式（離線寬限已到期）"
            elif state == "license_expired":
                tier = "general"; status = "只讀／備份模式（正式授權已到期）"
            elif state == "clock_rollback":
                tier = "general"; status = "只讀／備份模式（系統時間異常）"
            elif state == "invalid_receipt":
                tier = "general"; status = "本機授權收據無效"
            elif state == "revoked":
                tier = "general"; status = "正式授權已撤銷"
            elif state == "device_revoked":
                tier = "general"; status = "此裝置授權已撤銷"
            elif state == "server_denied":
                tier = "general"; status = "授權伺服器已拒絕目前授權"
            elif state == "saved_token_only":
                tier = "general"; status = "已保存授權憑證，需重新驗證"
            else:
                tier = "general"; status = "尚未啟用正式授權"
            company = str(receipt.get("company", "")).strip(); exp = str(receipt.get("expires_at", "")).strip()
            self.license_status.setText(
                f"目前：{SystemSettingsService.TIER_NAMES.get(tier,'一般版')} ｜ {status}"
                + (f" ｜ {company}" if company else "")
                + (f" ｜ 到期：{exp}" if exp else "")
            )
            return
        tier=lic.get("tier","general"); dev=lic.get("development_mode",True); status="開發測試模式" if dev else ("正式授權有效" if lic.get("license_status")=="valid" else "尚未驗證"); exp=str(lic.get("expires_at","")).strip(); self.license_status.setText(f"目前：{SystemSettingsService.TIER_NAMES.get(tier,'一般版')} ｜ {status}" + (f" ｜ 到期：{exp}" if exp else ""))

    def _set_color_buttons(self, colors):
        for key, btn in self.color_buttons.items():
            color=str(colors.get(key,SystemSettingsService.THEME_PRESETS["warm"].get(key,"#FFFFFF")))
            btn.setProperty("selectedColor",color); btn.setText(color); fg="#FFFFFF" if QColor(color).lightness()<120 else "#17202A"; btn.setStyleSheet(f"background:{color};color:{fg};border:1px solid #9AA5B1;border-radius:7px;font-weight:800;")

    def apply_preset_preview(self, *_):
        key=self.theme_preset.currentData() or "warm"; self._set_color_buttons(SystemSettingsService.THEME_PRESETS.get(key,SystemSettingsService.THEME_PRESETS["warm"]))

    def choose_color(self,key):
        current=str(self.color_buttons[key].property("selectedColor") or "#FFFFFF"); color=QColorDialog.getColor(QColor(current),self,f"選擇顏色：{key}")
        if color.isValid(): self._set_color_buttons({k:(color.name() if k==key else str(b.property('selectedColor') or '#FFFFFF')) for k,b in self.color_buttons.items()})

    def save_appearance(self):
        values={"preset":str(self.theme_preset.currentData() or "custom")}
        for key,btn in self.color_buttons.items(): values[key]=str(btn.property("selectedColor") or "#FFFFFF")
        SystemSettingsService.update_section("appearance",values); win=self.window()
        if hasattr(win,"apply_current_theme"): win.apply_current_theme()
        QMessageBox.information(self,"完成","版面與文字配色已儲存並套用。")

    def _notify_main_window_permissions(self):
        win=self.window()
        if hasattr(win,"refresh_permissions"): win.refresh_permissions()
        if hasattr(win,"dashboard_page") and hasattr(win.dashboard_page,"refresh_data"):
            try: win.dashboard_page.refresh_data()
            except Exception: pass
        if hasattr(win,"apply_current_theme"): win.apply_current_theme()

    def choose_export_folder(self):
        folder=QFileDialog.getExistingDirectory(self,"選擇預設匯出資料夾",self.export_folder.text() or "")
        if folder:self.export_folder.setText(folder)
    def save_export(self):
        SystemSettingsService.update_section("export",{"default_folder":self.export_folder.text().strip() or "exports","include_timestamp":self.include_timestamp.isChecked(),"default_excel":self.default_excel.isChecked(),"default_pdf":self.default_pdf.isChecked()}); QMessageBox.information(self,"完成","匯出設定已儲存。")
    def save_account(self):
        user=UserAuthService.current_user() or {}; username=str(user.get("username", ""))
        if not username: return
        try:
            updated=UserAuthService.update_user(username,display_name=self.display_name.text(),email=self.email.text(),company=self.company.text())
            SystemSettingsService.update_section("account",{"display_name":updated.get("display_name",""),"email":updated.get("email",""),"role":updated.get("role",""),"company":updated.get("company","")})
            self.refresh_user_table(); win=self.window();
            if hasattr(win,"refresh_permissions"): win.refresh_permissions()
            QMessageBox.information(self,"完成","我的帳號資料已儲存。")
        except Exception as e: QMessageBox.warning(self,"儲存失敗",str(e))
    def save_update(self):
        SystemSettingsService.update_section("update",{"update_url":self.update_url.text().strip()}); QMessageBox.information(self,"完成","版本更新設定已儲存。")
    def check_update(self):
        url=self.update_url.text().strip(); SystemSettingsService.mark_update_checked(); self.last_checked.setText(SystemSettingsService.load()["update"].get("last_checked_at",""))
        self.btn_secure_update.setEnabled(False); self._last_update_check=None
        if not url: QMessageBox.information(self,"更新檢查",f"目前版本：{SystemSettingsService.CURRENT_VERSION}\n尚未設定已簽章 Manifest URL。"); return
        try:
            result=UpdateService.check(url); self._last_update_check=result
            manifest=result.get("manifest",{}); latest=str(manifest.get("latest_version","") or "")
            if not result.get("available"):
                QMessageBox.information(self,"更新檢查",f"目前版本 {SystemSettingsService.CURRENT_VERSION} 已是最新版本。")
            elif not result.get("eligible"):
                QMessageBox.warning(self,"目前授權不可更新",result.get("reason") or "目前維護更新資格不包含此版本。")
            else:
                self.btn_secure_update.setEnabled(True)
                QMessageBox.information(self,"發現新版本",f"目前：{SystemSettingsService.CURRENT_VERSION}\n最新：{latest}\n\nManifest 的 Ed25519 簽章已驗證通過。可按「安全下載更新」。")
        except Exception as e: QMessageBox.warning(self,"檢查更新失敗",str(e))

    def download_secure_update(self):
        result=self._last_update_check or {}; manifest=result.get("manifest",{}) if isinstance(result,dict) else {}
        if not result.get("available") or not result.get("eligible"):
            QMessageBox.information(self,"沒有可下載更新","請先執行「檢查更新」。"); return
        try:
            packages=manifest.get("packages",{}) if isinstance(manifest,dict) else {}; pkg=packages.get("win-x64") or packages.get("windows")
            if not isinstance(pkg,dict): raise ValueError("Manifest 沒有 win-x64 更新套件。")
            path=UpdateService.download_package(pkg); pending=UpdateService.write_pending_update(manifest,path)
            answer=QMessageBox.question(self,"安全下載完成",f"更新套件 SHA-256 驗證通過。\n\n版本：{manifest.get('latest_version','')}\n下載位置：\n{path}\n\n要立即建立更新前資料儲存點、關閉 TACO 並安全更新嗎？")
            if answer==QMessageBox.StandardButton.Yes:
                UpdateService.launch_updater(pending); QApplication.quit()
        except Exception as e: QMessageBox.warning(self,"下載更新失敗",str(e))

    def save_connection(self):
        SystemSettingsService.update_section("connection",{"mode":self.conn_mode.currentText(),"server":self.server.text().strip(),"database":self.database.text().strip(),"username":self.username.text().strip(),"auth_type":self.auth_type.currentText(),"driver":self.driver.text().strip(),"timeout":self.timeout.value(),"read_only":self.read_only.isChecked()}); QMessageBox.information(self,"完成","連線資料已儲存。密碼不會寫入 JSON。")
    def test_connection(self):
        if not SystemSettingsService.effective_has_tier("advanced"): QMessageBox.information(self,"高級版功能","SQL Server 連線需要高級版授權。"); return
        if self.conn_mode.currentText()!="SQL Server": QMessageBox.information(self,"目前模式","目前使用 Excel / PDF，不需要測試 SQL Server。"); return
        try:
            import pyodbc
            driver=self.driver.text().strip(); server=self.server.text().strip(); database=self.database.text().strip(); timeout=self.timeout.value()
            if self.auth_type.currentText()=="Windows 驗證": conn_str=f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};Trusted_Connection=yes;TrustServerCertificate=yes;"
            else: conn_str=f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};UID={self.username.text().strip()};PWD={self.password.text()};TrustServerCertificate=yes;"
            conn=pyodbc.connect(conn_str,timeout=timeout); cur=conn.cursor(); cur.execute("SELECT 1"); cur.fetchone(); conn.close(); QMessageBox.information(self,"連線成功","SQL Server 測試成功。正式 ERP 查詢仍建議使用唯讀帳號。")
        except Exception as e: QMessageBox.critical(self,"SQL Server 連線失敗",str(e))
