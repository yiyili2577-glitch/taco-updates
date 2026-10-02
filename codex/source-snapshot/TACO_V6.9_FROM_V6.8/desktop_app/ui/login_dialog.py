from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFormLayout, QGroupBox, QMessageBox, QStackedWidget, QWidget
)

from services.user_auth_service import UserAuthService


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TACO 智慧採購助理｜登入")
        self.setModal(True)
        self.setMinimumWidth(470)
        self.setMaximumWidth(560)
        self.build_ui()

    def build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        title = QLabel("TACO 智慧採購助理")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size:25px;font-weight:900;")
        subtitle = QLabel("登入後依使用者角色開啟可使用的採購、庫存與管理功能。")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#6B7785;")
        root.addWidget(title)
        root.addWidget(subtitle)

        self.stack = QStackedWidget()
        root.addWidget(self.stack)
        self._build_login_page()
        self._build_bootstrap_page()

        if UserAuthService.has_users():
            self.stack.setCurrentIndex(0)
        else:
            self.stack.setCurrentIndex(1)

    def _build_login_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        box = QGroupBox("帳號登入"); form = QFormLayout(box)
        self.username = QLineEdit(); self.username.setPlaceholderText("登入帳號")
        self.password = QLineEdit(); self.password.setEchoMode(QLineEdit.EchoMode.Password); self.password.setPlaceholderText("密碼")
        form.addRow("帳號", self.username); form.addRow("密碼", self.password)
        layout.addWidget(box)
        row = QHBoxLayout(); row.addStretch()
        login = QPushButton("登入 TACO"); login.setMinimumHeight(40); login.setDefault(True); login.clicked.connect(self.do_login)
        cancel = QPushButton("離開"); cancel.clicked.connect(self.reject)
        row.addWidget(cancel); row.addWidget(login); layout.addLayout(row)
        self.password.returnPressed.connect(self.do_login)
        self.stack.addWidget(page)

    def _build_bootstrap_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        notice = QLabel("第一次啟動需要建立第一位「系統管理員」。建立後，下次開啟程式就會直接進入登入畫面。")
        notice.setWordWrap(True); notice.setStyleSheet("color:#7A5B18;padding:6px;")
        layout.addWidget(notice)
        box = QGroupBox("建立第一位系統管理員"); form = QFormLayout(box)
        self.admin_username = QLineEdit(); self.admin_username.setPlaceholderText("例如：admin")
        self.admin_display = QLineEdit(); self.admin_display.setPlaceholderText("顯示名稱")
        self.admin_email = QLineEdit(); self.admin_company = QLineEdit()
        self.admin_password = QLineEdit(); self.admin_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.admin_password2 = QLineEdit(); self.admin_password2.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("登入帳號", self.admin_username); form.addRow("顯示名稱", self.admin_display)
        form.addRow("Email", self.admin_email); form.addRow("公司名稱", self.admin_company)
        form.addRow("密碼", self.admin_password); form.addRow("確認密碼", self.admin_password2)
        layout.addWidget(box)
        row = QHBoxLayout(); row.addStretch()
        cancel = QPushButton("離開"); cancel.clicked.connect(self.reject)
        create = QPushButton("建立管理員並登入"); create.setMinimumHeight(40); create.clicked.connect(self.create_admin)
        row.addWidget(cancel); row.addWidget(create); layout.addLayout(row)
        self.stack.addWidget(page)

    def do_login(self):
        try:
            UserAuthService.authenticate(self.username.text(), self.password.text())
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "登入失敗", str(e))

    def create_admin(self):
        if self.admin_password.text() != self.admin_password2.text():
            QMessageBox.warning(self, "密碼不一致", "兩次輸入的密碼不同。")
            return
        try:
            UserAuthService.create_first_admin(
                self.admin_username.text(), self.admin_password.text(), self.admin_display.text(),
                self.admin_email.text(), self.admin_company.text()
            )
            UserAuthService.authenticate(self.admin_username.text(), self.admin_password.text())
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "建立帳號失敗", str(e))
