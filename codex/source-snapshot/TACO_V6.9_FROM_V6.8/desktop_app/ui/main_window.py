from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QStackedWidget, QFrame
)

from ui.dashboard_page import DashboardPage
from ui.inventory_page import InventoryPage
from ui.purchase_page import PurchasePage
from ui.customer_demand_page import CustomerDemandPage
from ui.supplier_page import SupplierPage
from ui.system_settings_page import SystemSettingsPage
from ui.ui_theme import build_app_style
from services.system_settings_service import SystemSettingsService
from services.feature_gate_service import FeatureGateService
from services.user_auth_service import UserAuthService
from services.role_permission_service import RolePermissionService
from ui.login_dialog import LoginDialog
from ui.help_center_page import HelpCenterPage
from ui.audit_center_page import AuditCenterPage
from ui.finance_page import FinancePage
from ui.integration_center_page import IntegrationCenterPage

try:
    from ui.supplier_tools_installer import SupplierToolsInstaller
except Exception:
    SupplierToolsInstaller = None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        login = LoginDialog()
        if login.exec() != LoginDialog.DialogCode.Accepted:
            raise SystemExit(0)
        self.setWindowTitle('TACO 智慧採購助理')
        self.resize(1560, 920)
        self.setMinimumSize(1040, 680)
        self.nav_buttons = []
        self.nav_requirements = []
        self.page_key_to_index = {}
        self.build_ui()
        self.apply_current_theme()
        self.refresh_permissions()
        if SupplierToolsInstaller is not None:
            SupplierToolsInstaller.install_later()

    def build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        root = QHBoxLayout(central); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        self.sidebar = QFrame(); self.sidebar.setObjectName('sidebar'); self.sidebar.setFixedWidth(208)
        sl = QVBoxLayout(self.sidebar); sl.setContentsMargins(12,16,12,14); sl.setSpacing(5)
        self.brand_label = QLabel('TACO 智慧採購助理'); self.brand_label.setObjectName('brandLabel'); sl.addWidget(self.brand_label)

        self.pages = QStackedWidget()
        self.dashboard_page = DashboardPage()
        self.inventory_page = InventoryPage()
        self.purchase_page = PurchasePage()
        self.customer_page = CustomerDemandPage()
        self.supplier_page = SupplierPage()
        self.finance_page = FinancePage()
        self.integration_page = IntegrationCenterPage()
        self.settings_page = SystemSettingsPage()
        self.help_page = HelpCenterPage()
        self.audit_page = AuditCenterPage()

        page_defs = [
            ('dashboard', '▦  首頁總覽', self.dashboard_page, 'general'),
            ('inventory', '▤  庫存分析', self.inventory_page, 'general'),
            ('purchase', '◈  採購建議', self.purchase_page, 'intermediate'),
            ('customer', '☷  客戶需求', self.customer_page, 'general'),
            ('supplier', '♟  供應商設定', self.supplier_page, 'general'),
            ('finance', '💰  財務中心', self.finance_page, 'advanced'),
            ('integration', '📷  智慧掃碼 / Mapping', self.integration_page, 'intermediate'),
        ]

        for index, (key, label, page, required_tier) in enumerate(page_defs):
            self.pages.addWidget(page); self.page_key_to_index[key] = index
            btn = QPushButton(label); btn.setProperty('pageKey', key); btn.setCheckable(True); btn.setAutoExclusive(True); btn.setMinimumHeight(39)
            btn.clicked.connect(lambda checked=False, i=index: self.switch_page(i))
            self.nav_buttons.append(btn); self.nav_requirements.append(required_tier); sl.addWidget(btn)

        audit_index = self.pages.count(); self.pages.addWidget(self.audit_page); self.page_key_to_index['audit'] = audit_index
        audit_btn = QPushButton('🧾  稽核中心'); audit_btn.setCheckable(True); audit_btn.setAutoExclusive(True); audit_btn.setMinimumHeight(39)
        audit_btn.setProperty('pageKey', 'audit')
        audit_btn.clicked.connect(lambda checked=False, i=audit_index: self.switch_page(i)); self.nav_buttons.append(audit_btn); self.nav_requirements.append('advanced'); sl.addWidget(audit_btn)

        help_index = self.pages.count(); self.pages.addWidget(self.help_page); self.page_key_to_index['help'] = help_index
        help_btn = QPushButton('？  操作說明'); help_btn.setCheckable(True); help_btn.setAutoExclusive(True); help_btn.setMinimumHeight(39)
        help_btn.setProperty('pageKey', 'help')
        help_btn.clicked.connect(lambda checked=False, i=help_index: self.switch_page(i)); self.nav_buttons.append(help_btn); self.nav_requirements.append('general'); sl.addWidget(help_btn)

        sl.addStretch()
        self.quick_button = QPushButton('＋  快速新增 / 匯入'); self.quick_button.setObjectName('quickAction')
        self.quick_button.clicked.connect(lambda: self.switch_to_key('customer')); sl.addWidget(self.quick_button)

        settings_index = self.pages.count(); self.pages.addWidget(self.settings_page); self.page_key_to_index['settings'] = settings_index
        settings_btn = QPushButton('⚙  系統設定'); settings_btn.setCheckable(True); settings_btn.setAutoExclusive(True); settings_btn.setMinimumHeight(39)
        settings_btn.setProperty('pageKey', 'settings')
        settings_btn.clicked.connect(lambda: self.switch_page(settings_index)); self.nav_buttons.append(settings_btn); self.nav_requirements.append('general'); sl.addWidget(settings_btn)

        self.license_label = QLabel(''); self.license_label.setObjectName('licenseLabel'); sl.addWidget(self.license_label)
        self.user_label = QLabel(''); self.user_label.setObjectName('userLabel'); self.user_label.setWordWrap(True); sl.addWidget(self.user_label)
        self.logout_button = QPushButton('⇥  登出'); self.logout_button.setObjectName('logoutButton'); self.logout_button.clicked.connect(self.logout); sl.addWidget(self.logout_button)

        root.addWidget(self.sidebar)
        self.content_frame = QFrame(); self.content_frame.setObjectName('contentFrame')
        cl = QVBoxLayout(self.content_frame); cl.setContentsMargins(0,0,0,0); cl.addWidget(self.pages)
        root.addWidget(self.content_frame, 1)

        self.nav_buttons[0].setChecked(True); self.pages.setCurrentIndex(0)
        self.dashboard_page.navigateRequested.connect(self.handle_dashboard_navigation)
        self.help_page.navigateRequested.connect(self.switch_to_key)

    def apply_current_theme(self):
        a = SystemSettingsService.load().get('appearance', {})
        self.setStyleSheet(build_app_style(a))
        sidebar_bg = a.get('sidebar_bg', '#FBF8F4'); menu_text = a.get('menu_text', '#3F4853')
        content_text = a.get('content_text', '#18212B'); muted = a.get('muted_text', '#728091')
        accent = a.get('accent', '#5DBDAD'); border = a.get('border', '#E5E1DB'); content_bg = a.get('content_bg', '#F8F6F2')
        self.sidebar.setStyleSheet(f'''
            QFrame#sidebar {{ background:{sidebar_bg}; border-right:1px solid {border}; }}
            QLabel {{ background:transparent; color:{menu_text}; }}
            QLabel#brandLabel {{ color:{menu_text};font-size:16px;font-weight:900;padding:7px 7px 14px 7px; }}
            QLabel#licenseLabel {{ color:{muted};font-size:11px;padding:7px; }}
            QLabel#userLabel {{ color:{menu_text};font-size:12px;font-weight:700;padding:8px 7px 2px 7px; }}
            QPushButton {{ color:{menu_text};text-align:left;border:none;border-radius:8px;padding:9px 11px;font-size:13px;background:transparent;min-height:24px; }}
            QPushButton:hover {{ border:1px solid {accent}; }}
            QPushButton:checked {{ background:{accent};color:#FFFFFF;font-weight:800; }}
            QPushButton:disabled {{ color:{muted}; }}
            QPushButton#quickAction {{ background:{content_text};color:#FFFFFF;border:none;border-radius:9px;padding:10px 12px;font-weight:800;text-align:center; }}
            QPushButton#quickAction:hover {{ background:{accent}; }}
        ''')
        self.content_frame.setStyleSheet(f'QFrame#contentFrame{{background:{content_bg};border:none;}}')
        if hasattr(self.dashboard_page, 'apply_theme'):
            self.dashboard_page.apply_theme()
        self.update()

    def refresh_permissions(self):
        tier = SystemSettingsService.get_tier(); dev = SystemSettingsService.is_development_mode()
        for btn, required in zip(self.nav_buttons, self.nav_requirements):
            page_key = str(btn.property('pageKey') or '')
            tier_allowed = FeatureGateService.allowed(required)
            role_allowed = RolePermissionService.page_allowed(page_key) if page_key else True
            allowed = tier_allowed and role_allowed
            btn.setEnabled(allowed)
            if not tier_allowed:
                btn.setToolTip(f"需要 {SystemSettingsService.TIER_NAMES.get(required, required)} 或以上版本")
            elif not role_allowed:
                btn.setToolTip(f"目前角色「{RolePermissionService.role()}」沒有此頁面權限")
            else:
                btn.setToolTip('')
        # 版本層級 + 使用者角色兩層權限都套用到現有頁面。
        for page in [self.inventory_page, self.purchase_page, self.customer_page, self.supplier_page, self.finance_page, self.integration_page, self.settings_page, self.audit_page]:
            FeatureGateService.apply_to_widget(page)
            RolePermissionService.apply_to_widget(page)
        tier_name = SystemSettingsService.TIER_NAMES.get(tier, '一般版')
        if dev:
            mode = '開發測試'
        else:
            try:
                from services.license_client_service import LicenseClientService
                mode = '正式授權' if LicenseClientService.current_receipt() else '未授權 / 需重新驗證'
            except Exception:
                mode = '未授權 / 需重新驗證'
        self.license_label.setText(f'{tier_name} · {mode}')
        user = UserAuthService.current_user() or {}
        display = user.get('display_name') or user.get('username') or '使用者'
        role = user.get('role') or ''
        self.user_label.setText(f'👤 {display}\n{role}')
        # 若目前正停在被降級鎖住的頁面，回 Dashboard。
        idx = self.pages.currentIndex()
        if idx < len(self.nav_buttons) and idx < len(self.nav_requirements):
            if not FeatureGateService.allowed(self.nav_requirements[idx]):
                self.switch_to_key('dashboard')

    def switch_page(self, index):
        if not (0 <= index < self.pages.count()): return
        if index < len(self.nav_requirements) and not FeatureGateService.allowed(self.nav_requirements[index]): return
        if index < len(self.nav_buttons):
            key = str(self.nav_buttons[index].property('pageKey') or '')
            if key and not RolePermissionService.page_allowed(key): return
        try:
            self._show_all_rows(getattr(self.purchase_page, 'table', None)); self._show_all_rows(getattr(self.inventory_page, 'table', None))
        except Exception: pass
        self.pages.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons): btn.setChecked(i == index)
        if index == self.page_key_to_index.get('dashboard') and hasattr(self.dashboard_page, 'refresh_data'):
            self.dashboard_page.refresh_data()
        if index == self.page_key_to_index.get('finance') and hasattr(self.finance_page, 'refresh_all'):
            self.finance_page.refresh_all()

    def switch_to_key(self, key):
        index = self.page_key_to_index.get(key)
        if index is not None: self.switch_page(index)

    def handle_dashboard_navigation(self, key):
        mapping = {'dashboard':'dashboard','inventory':'inventory','customer':'customer','unmapped':'customer','supplier':'supplier','purchase':'purchase','urgent':'purchase','amount':'finance','container':'purchase','transfer':'purchase','shortage':'inventory','finance':'finance','finance_ar':'finance','cash':'finance'}
        target = mapping.get(key, 'dashboard'); self.switch_to_key(target); self._apply_dashboard_context(key)

    def logout(self):
        from PyQt6.QtWidgets import QMessageBox
        from services.audit_log_service import AuditLogService
        answer = QMessageBox.question(self, '登出 TACO', '確定要登出目前帳號嗎？')
        if answer != QMessageBox.StandardButton.Yes:
            return
        AuditLogService.log_event('登入', '登出', result='成功')
        UserAuthService.logout()
        self.hide()
        dialog = LoginDialog(self)
        if dialog.exec() == LoginDialog.DialogCode.Accepted:
            self.refresh_permissions()
            self.apply_current_theme()
            self.switch_to_key('dashboard')
            self.show()
        else:
            self.close()

    def _show_all_rows(self, table):
        if table is None: return
        for row in range(table.rowCount()): table.setRowHidden(row, False)

    def _header_index(self, table, candidates):
        if table is None: return None
        for col in range(table.columnCount()):
            item = table.horizontalHeaderItem(col); text = item.text().strip() if item else ''
            if text in candidates: return col
        return None

    def _apply_dashboard_context(self, key):
        try:
            if key == 'unmapped':
                if hasattr(self.customer_page, 'tabs'): self.customer_page.tabs.setCurrentIndex(1)
                return
            if key in ('purchase','urgent','amount','container'):
                table = getattr(self.purchase_page, 'table', None); self._show_all_rows(table)
                if table is None: return
                if key == 'purchase':
                    qty_col = self._header_index(table, {'實際採購量','建議採購量'})
                    if qty_col is not None:
                        for row in range(table.rowCount()):
                            item = table.item(row, qty_col)
                            try: qty = float((item.text() if item else '0').replace(',',''))
                            except Exception: qty = 0
                            table.setRowHidden(row, qty <= 0)
                elif key == 'urgent':
                    status_col = self._header_index(table, {'狀態'})
                    if status_col is not None:
                        for row in range(table.rowCount()):
                            item = table.item(row,status_col); text=item.text() if item else ''
                            table.setRowHidden(row, not any(word in text for word in ['急需','立即','缺口','缺貨']))
                return
            if key == 'shortage':
                table=getattr(self.inventory_page,'table',None); self._show_all_rows(table); status_col=self._header_index(table,{'狀態'})
                if table is not None and status_col is not None:
                    for row in range(table.rowCount()):
                        item=table.item(row,status_col); text=item.text() if item else ''
                        table.setRowHidden(row, not any(word in text for word in ['急需','注意','缺貨','不足','偏低']))
        except Exception: pass

    def refresh_dashboard(self):
        if hasattr(self.dashboard_page, 'refresh_data'): self.dashboard_page.refresh_data()
