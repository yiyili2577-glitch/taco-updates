from services.system_settings_service import SystemSettingsService


def get_theme():
    return SystemSettingsService.load().get("appearance", {})


def build_app_style(theme=None):
    t = theme or get_theme()
    content = t.get("content_text", "#18212B")
    muted = t.get("muted_text", "#728091")
    card = t.get("card_bg", "#FFFFFF")
    bg = t.get("content_bg", "#F8F6F2")
    border = t.get("border", "#E5E1DB")
    accent = t.get("accent", "#5DBDAD")
    header = t.get("table_header_bg", "#F4F6F8")
    accent_soft = "#E7F6F2"
    panel_soft = "#FCFBF9"
    return f"""
QWidget {{
    font-family: "Microsoft JhengHei", "Microsoft YaHei", sans-serif;
    color: {content};
    font-size: 13px;
}}
QMainWindow, QDialog {{ background: {bg}; }}
QLabel {{ background: transparent; color: {content}; }}
QLabel#pageTitle {{ font-size: 28px; font-weight: 900; letter-spacing: 0.5px; }}
QLabel#pageSubtitle {{ color: {muted}; font-size: 13px; line-height: 1.4; padding-bottom: 4px; }}
QFrame#pageHeader {{
    background: {card};
    border: 1px solid {border};
    border-radius: 12px;
}}
QLabel#sectionTitle {{ font-size: 16px; font-weight: 900; }}
QLabel#statusText {{ color: {muted}; font-size: 12px; }}
QLabel[muted="true"] {{ color: {muted}; }}
QFrame#contentFrame {{ background: {bg}; }}
QPushButton {{
    background: {card}; color: {content}; border: 1px solid {border};
    border-radius: 9px; padding: 7px 12px; min-height: 24px; font-weight: 700;
}}
QPushButton:hover {{ border-color: {accent}; background: {panel_soft}; }}
QPushButton:pressed {{ background: {header}; }}
QPushButton:disabled {{ color: {muted}; background: {header}; }}
QPushButton[buttonRole="primary"] {{ background: {accent}; color: #FFFFFF; border-color: {accent}; }}
QPushButton[buttonRole="danger"] {{ color: #B42318; background: #FFF7F5; border-color: #F9D6D1; }}
QPushButton[tabButton="true"] {{
    background: {card};
    color: {content};
    border: 1px solid {border};
    border-radius: 10px;
    padding: 8px 10px;
    min-height: 36px;
    text-align: center;
    font-weight: 700;
}}
QPushButton[tabButton="true"]:hover {{ border-color: {accent}; background: {panel_soft}; }}
QPushButton[tabButton="true"]:checked,
QPushButton[tabButton="true"][active="true"] {{
    background: {accent_soft};
    border: 1px solid {accent};
    color: {content};
    font-weight: 900;
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit {{
    background: {card}; color: {content}; border: 1px solid {border};
    border-radius: 8px; padding: 6px 9px; min-height: 25px;
}}
QCheckBox {{ color: {content}; spacing: 7px; }}
QPlainTextEdit, QTextEdit {{
    background: {card}; color: {content}; border: 1px solid {border};
    border-radius: 9px; padding: 7px; selection-background-color: {accent};
}}
QProgressBar {{
    background: {header}; border: 1px solid {border}; border-radius: 8px;
    text-align: center; min-height: 18px; font-weight: 700;
}}
QProgressBar::chunk {{ background: {accent}; border-radius: 7px; }}
QToolTip {{ background: {content}; color: {card}; border: none; padding: 6px; }}
QGroupBox {{
    color: {content}; border: 1px solid {border}; border-radius: 12px;
    margin-top: 10px; padding: 12px 10px 10px 10px; background: {card};
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; font-weight: 800; }}
QTableWidget {{
    background: {card}; color: {content}; alternate-background-color: {bg};
    border: 1px solid {border}; border-radius: 10px; gridline-color: {border};
}}
QTableWidget::item {{ padding: 5px; }}
QTableWidget::item:selected {{ background: {accent_soft}; color: {content}; }}
QTableWidget:focus {{ border-color: {accent}; }}
QHeaderView::section {{
    background: {header}; color: {content}; border: none; border-bottom: 1px solid {border};
    padding: 8px; font-weight: 800;
}}
QTabWidget::pane {{ border: 1px solid {border}; border-radius: 10px; background:{card}; top: -1px; }}
QTabBar::tab {{ background:{header}; color:{content}; padding:8px 12px; margin-right:4px; border-radius:8px; min-height: 20px; }}
QTabBar::tab:selected {{ background:{card}; color:{content}; font-weight:800; }}
QWidget#erpTabBar {{
    background: {card};
    border: 1px solid {border};
    border-radius: 12px;
    padding: 10px;
}}
QStackedWidget#erpTabStack {{
    background: transparent;
}}
QScrollArea {{ border:none; background:transparent; }}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {border}; min-height: 30px; border-radius: 5px; }}
QScrollBar::handle:vertical:hover {{ background: {muted}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {border}; min-width: 30px; border-radius: 5px; }}
QScrollBar::handle:horizontal:hover {{ background: {muted}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
"""


APP_STYLE = build_app_style(SystemSettingsService.THEME_PRESETS["warm"])
