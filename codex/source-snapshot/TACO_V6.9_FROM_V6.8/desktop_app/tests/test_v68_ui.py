import unittest
from pathlib import Path

from services.build_config import BuildConfig


class V68UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.desktop = cls.root / "desktop_app"

    def test_version_files_are_consistent(self):
        self.assertEqual(BuildConfig.VERSION, "6.9.0")
        self.assertEqual((self.desktop / "VERSION").read_text(encoding="utf-8").strip(), "6.9.0")
        setup_bat = (self.root / "build_tools" / "build_setup.bat").read_text(encoding="utf-8")
        self.assertIn("TACO_V690.iss", setup_bat)
        self.assertIn('set "VERSION=6.9.0"', setup_bat)
        self.assertIn("BUILD_VERSION.txt", setup_bat)
        windows_bat = (self.root / "build_tools" / "build_windows.bat").read_text(encoding="utf-8")
        self.assertIn("BUILD_VERSION.txt", windows_bat)
        iss = (self.root / "installer" / "TACO_V690.iss").read_text(encoding="utf-8")
        self.assertIn('#define MyAppVersion "6.9.0"', iss)
        self.assertIn("OutputBaseFilename=TACO_Setup_6.9.0", iss)
        version_info = (self.root / "build_tools" / "version_info.txt").read_text(encoding="utf-8")
        self.assertIn("6.9.0.0", version_info)

    def test_finance_uses_two_row_22_tab_layout(self):
        finance = (self.desktop / "ui" / "finance_page.py").read_text(encoding="utf-8")
        tabs = (self.desktop / "ui" / "two_row_tab_widget.py").read_text(encoding="utf-8")
        self.assertIn("TwoRowTabWidget(columns=11)", finance)
        self.assertEqual(finance.count("self.tabs.addTab("), 22)
        self.assertIn("row = index // self._columns", tabs)
        self.assertIn("col = index % self._columns", tabs)
        self.assertNotIn("QScrollArea", tabs)

    def test_core_pages_use_consistent_page_headers(self):
        header = (self.desktop / "ui" / "page_header.py").read_text(encoding="utf-8")
        self.assertIn('setObjectName("pageHeader")', header)
        self.assertIn('setObjectName("pageTitle")', header)
        self.assertIn('setObjectName("pageSubtitle")', header)
        for name in ["inventory_page.py", "purchase_page.py", "customer_demand_page.py", "supplier_page.py", "integration_center_page.py"]:
            text = (self.desktop / "ui" / name).read_text(encoding="utf-8")
            self.assertIn("add_page_header", text, name)

    def test_global_theme_contains_erp_readability_rules(self):
        theme = (self.desktop / "ui" / "ui_theme.py").read_text(encoding="utf-8")
        for selector in ["QFrame#pageHeader", 'QPushButton[tabButton="true"]', "QProgressBar", "QTableWidget::item:selected", "QScrollBar:vertical"]:
            self.assertIn(selector, theme)


if __name__ == "__main__":
    unittest.main()
