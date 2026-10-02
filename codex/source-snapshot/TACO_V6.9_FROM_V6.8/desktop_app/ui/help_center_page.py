from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QListWidget, QTextBrowser, QSplitter, QFrame
)
from services.help_content_service import HelpContentService


class HelpCenterPage(QWidget):
    navigateRequested = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.build_ui()

    def build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(10)

        title = QLabel("TACO 操作說明")
        title.setObjectName("pageTitle")
        sub = QLabel("完整操作流程、功能用途、計算邏輯、版本權限與常見問題。")
        sub.setProperty("muted", True)
        root.addWidget(title)
        root.addWidget(sub)

        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜尋：採購、庫存、PDF、Excel、跨倉、貨櫃、帳號...")
        self.search.setMaximumWidth(520)
        btn_search = QPushButton("搜尋")
        btn_all = QPushButton("顯示完整手冊")
        btn_dashboard = QPushButton("回首頁")
        btn_settings = QPushButton("系統設定")
        btn_search.clicked.connect(self.do_search)
        btn_all.clicked.connect(self.show_all)
        btn_dashboard.clicked.connect(lambda: self.navigateRequested.emit("dashboard"))
        btn_settings.clicked.connect(lambda: self.navigateRequested.emit("settings"))
        self.search.returnPressed.connect(self.do_search)
        for w in [self.search, btn_search, btn_all, btn_dashboard, btn_settings]:
            bar.addWidget(w)
        bar.addStretch()
        root.addLayout(bar)

        splitter = QSplitter()
        self.sections = QListWidget()
        self.sections.setMaximumWidth(230)
        self.sections.setMinimumWidth(180)
        for name in HelpContentService.names():
            self.sections.addItem(name)
        self.sections.currentRowChanged.connect(self.show_section)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        splitter.addWidget(self.sections)
        splitter.addWidget(self.browser)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        footer = QFrame()
        fl = QHBoxLayout(footer); fl.setContentsMargins(0,0,0,0)
        hint = QLabel("建議新使用者先閱讀：快速開始 → 系統設定 → 供應商設定 → 庫存分析 → 客戶需求 → 採購建議。")
        hint.setProperty("muted", True)
        fl.addWidget(hint); fl.addStretch()
        root.addWidget(footer)

        self.sections.setCurrentRow(0)

    def show_section(self, row):
        self.browser.setHtml(HelpContentService.wrap_html(HelpContentService.section_html(row)))

    def show_all(self):
        self.sections.clearSelection()
        self.browser.setHtml(HelpContentService.full_html())

    def do_search(self):
        self.sections.clearSelection()
        self.browser.setHtml(HelpContentService.search_html(self.search.text()))
