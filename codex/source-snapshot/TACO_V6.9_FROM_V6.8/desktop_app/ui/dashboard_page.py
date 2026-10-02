from PyQt6.QtCore import Qt, QRectF, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QFont, QBrush
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QScrollArea, QSizePolicy
)

from services.dashboard_data_service import DashboardDataService
from services.system_settings_service import SystemSettingsService
from ui.responsive_action_bar import FlowLayout, compact_button
from ui.notification_center_dialog import NotificationCenterDialog
from services.notification_service import NotificationService
from services.financial_service import FinancialService


class MiniBarChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.labels = []
        self.values = []
        self.setMinimumHeight(130)
        self.setMaximumHeight(160)

    def set_data(self, labels, values):
        self.labels = list(labels)
        self.values = [float(v or 0) for v in values]
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(12, 10, -12, -25)
        if not self.values:
            p.setPen(QColor(SystemSettingsService.load().get('appearance',{}).get('muted_text','#94A3B8')))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '尚無資料')
            return
        max_v = max(self.values) or 1
        n = max(1, len(self.values))
        gap = max(14, int(rect.width() * 0.025))
        bar_w = max(24, min(110, (rect.width() - gap * (n + 1)) / n))
        colors = [QColor(SystemSettingsService.load().get('appearance',{}).get('accent','#65C5B6')), QColor(SystemSettingsService.load().get('appearance',{}).get('accent','#6CA8F6')), QColor('#F5B760')]
        for i, value in enumerate(self.values):
            h = max(2, (rect.height() - 25) * value / max_v) if value > 0 else 0
            x = rect.left() + gap + i * (bar_w + gap)
            y = rect.bottom() - h
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(colors[i % len(colors)])
            if h > 0:
                p.drawRoundedRect(QRectF(x, y, bar_w, h), 7, 7)
            p.setPen(QColor(SystemSettingsService.load().get('appearance',{}).get('muted_text','#475569')))
            label = self.labels[i] if i < len(self.labels) else ''
            p.drawText(QRectF(x - 20, rect.bottom() + 3, bar_w + 40, 18), Qt.AlignmentFlag.AlignCenter, label)
            p.setPen(QColor(SystemSettingsService.load().get('appearance',{}).get('content_text','#111827')))
            p.drawText(QRectF(x - 24, max(rect.top(), y - 20), bar_w + 48, 18), Qt.AlignmentFlag.AlignCenter, f'{value:,.0f}')


class TrendChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.labels = []
        self.values = []
        self.setMinimumHeight(145)
        self.setMaximumHeight(175)

    def set_data(self, labels, values):
        self.labels = list(labels)
        self.values = [float(v or 0) for v in values]
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(35, 12, -14, -28)
        p.setPen(QPen(QColor(SystemSettingsService.load().get('appearance',{}).get('border','#EEF1F4')), 1))
        for i in range(4):
            y = rect.top() + rect.height() * i / 3
            p.drawLine(int(rect.left()), int(y), int(rect.right()), int(y))
        if not self.values:
            p.setPen(QColor(SystemSettingsService.load().get('appearance',{}).get('muted_text','#94A3B8')))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '重新匯入客戶需求後可顯示日期趨勢')
            return
        max_v = max(self.values) or 1
        n = len(self.values)
        points = []
        for i, value in enumerate(self.values):
            x = rect.left() + (rect.width() * i / max(1, n - 1))
            y = rect.bottom() - (rect.height() * value / max_v)
            points.append((x, y))
        pen = QPen(QColor(SystemSettingsService.load().get('appearance',{}).get('accent','#6CA8F6')), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        for i in range(len(points) - 1):
            p.drawLine(int(points[i][0]), int(points[i][1]), int(points[i + 1][0]), int(points[i + 1][1]))
        p.setBrush(QColor(SystemSettingsService.load().get('appearance',{}).get('accent','#6CA8F6')))
        p.setPen(Qt.PenStyle.NoPen)
        for x, y in points:
            p.drawEllipse(QRectF(x - 4, y - 4, 8, 8))
        p.setPen(QColor(SystemSettingsService.load().get('appearance',{}).get('muted_text','#64748B')))
        step = max(1, n // 6)
        for i, label in enumerate(self.labels):
            if i % step == 0 or i == n - 1:
                x = points[i][0]
                p.drawText(QRectF(x - 28, rect.bottom() + 6, 56, 18), Qt.AlignmentFlag.AlignCenter, label)


class DonutWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = 0
        self.total = 1
        self.caption = ''
        self.center_text = ''
        self.setMinimumSize(135, 135)
        self.setMaximumSize(165, 165)

    def set_data(self, value, total, caption, center_text=''):
        self.value = max(0.0, float(value or 0))
        self.total = max(1.0, float(total or 1))
        self.caption = str(caption)
        self.center_text = str(center_text or '')
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height()) - 36
        r = QRectF((self.width() - side) / 2, 5, side, side)
        bg = QPen(QColor(SystemSettingsService.load().get('appearance',{}).get('border','#E9EEF3')), 14)
        bg.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(bg)
        p.drawArc(r, 0, 360 * 16)
        ratio = min(1.0, self.value / self.total)
        fg = QPen(QColor(SystemSettingsService.load().get('appearance',{}).get('accent','#65C5B6')), 14)
        fg.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(fg)
        p.drawArc(r, 90 * 16, int(-360 * 16 * ratio))
        p.setPen(QColor(SystemSettingsService.load().get('appearance',{}).get('content_text','#111827')))
        font = QFont(); font.setPointSize(14); font.setBold(True); p.setFont(font)
        text = self.center_text or f'{ratio * 100:.0f}%'
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
        font.setPointSize(8); font.setBold(False); p.setFont(font); p.setPen(QColor(SystemSettingsService.load().get('appearance',{}).get('muted_text','#64748B')))
        p.drawText(QRectF(0, self.height() - 23, self.width(), 18), Qt.AlignmentFlag.AlignCenter, self.caption)


class MetricCard(QFrame):
    clicked = pyqtSignal(str)

    def __init__(self, key, title, hint, accent='#65C5B6', parent=None):
        super().__init__(parent)
        self.key = key
        self.setObjectName('metricCard')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(82)
        self.setMaximumHeight(92)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(13, 10, 13, 9)
        lay.setSpacing(2)
        header = QHBoxLayout(); header.setSpacing(5)
        dot = QLabel('●'); dot.setStyleSheet(f'color:{accent};font-size:11px;background:transparent;')
        title_lab = QLabel(title); title_lab.setObjectName('metricTitle')
        header.addWidget(dot); header.addWidget(title_lab); header.addStretch()
        self.value_label = QLabel('0'); self.value_label.setObjectName('metricValue')
        self.hint_label = QLabel(hint); self.hint_label.setObjectName('muted')
        self.hint_label.setWordWrap(False)
        lay.addLayout(header); lay.addWidget(self.value_label); lay.addWidget(self.hint_label)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.key)
        super().mousePressEvent(event)


class DashboardPage(QWidget):
    navigateRequested = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.cards = {}
        self.metric_cards = []
        self.build_ui()
        self.refresh_data()

    def build_ui(self):
        self.apply_theme()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        self.content = QWidget()
        self.content.setStyleSheet(f"background:{SystemSettingsService.load().get('appearance',{}).get('content_bg','#F8F6F2')};")
        scroll.setWidget(self.content)
        root = QVBoxLayout(self.content)
        root.setContentsMargins(18, 14, 18, 16)
        root.setSpacing(10)

        top = QHBoxLayout(); top.setSpacing(8)
        titles = QVBoxLayout(); titles.setSpacing(1)
        title = QLabel('首頁儀表板'); title.setObjectName('dashboardTitle')
        self.subtitle = QLabel('庫存、需求、採購、調撥與進口作業即時總覽'); self.subtitle.setObjectName('muted')
        titles.addWidget(title); titles.addWidget(self.subtitle)
        top.addLayout(titles); top.addStretch()
        self.range_combo = QComboBox()
        self.range_combo.addItem('全部資料', None)
        self.range_combo.addItem('最近 7 天', 7)
        self.range_combo.addItem('最近 30 天', 30)
        self.range_combo.addItem('最近 90 天', 90)
        top.addWidget(QLabel('需求區間'))
        top.addWidget(self.range_combo)
        self.tier_label = QLabel(''); self.tier_label.setStyleSheet('background:#E9F7F3;color:#187565;padding:5px 9px;border-radius:9px;font-weight:800;')
        top.addWidget(self.tier_label)
        self.btn_notify = compact_button(QPushButton('🔔 通知中心')); self.btn_notify.clicked.connect(self.show_notifications); top.addWidget(self.btn_notify)
        self.btn_refresh = compact_button(QPushButton('⟳ 重新整理')); top.addWidget(self.btn_refresh)
        root.addLayout(top)

        self.cards_layout = QGridLayout()
        self.cards_layout.setHorizontalSpacing(9); self.cards_layout.setVerticalSpacing(9)
        specs = [
            ('inventory', '三倉總庫存', '目前三倉現貨合計', '#65C5B6'),
            ('customer', '客戶需求量', '依目前需求區間', '#6CA8F6'),
            ('purchase', '需採購品項', '實際採購量 > 0', '#FF9C66'),
            ('urgent', '低庫存 / 急需', '需要優先處理', '#F06D78'),
            ('amount', '採購金額', '依產品報價設定', '#B28EE8'),
            ('container', '貨櫃使用率', '最後一櫃 CBM', '#F3C45A'),
            ('finance_ar', '逾期應收', '逾期未收 TWD', '#E87979'),
            ('cash', '淨現金流', '收款－付款－費用', '#55B899'),
        ]
        for key, label, hint, accent in specs:
            card = MetricCard(key, label, hint, accent)
            card.clicked.connect(self.navigateRequested.emit)
            self.cards[key] = card; self.metric_cards.append(card)
        self._reflow_metric_cards(4)
        root.addLayout(self.cards_layout)

        # 今日任務縮成一列，避免佔用過多垂直空間。
        task_card = QFrame(); task_card.setObjectName('sectionCard')
        tl = QHBoxLayout(task_card); tl.setContentsMargins(14, 9, 14, 9); tl.setSpacing(10)
        text_box = QVBoxLayout(); text_box.setSpacing(0)
        task_title = QLabel('今日需要處理'); task_title.setObjectName('sectionTitle')
        task_hint = QLabel('點擊任務直接前往對應頁面'); task_hint.setObjectName('muted')
        text_box.addWidget(task_title); text_box.addWidget(task_hint); tl.addLayout(text_box)
        task_bar = FlowLayout(h_spacing=6, v_spacing=6)
        self.task_buttons = {}
        for key, label, bg in [
            ('purchase', '急需採購', '#FCE8E8'), ('unmapped', '未對應需求', '#F3ECFF'),
            ('transfer', '跨倉調撥', '#E8F5FF'), ('shortage', '調撥後仍缺貨', '#FFF0E3')
        ]:
            btn = QPushButton(label)
            btn.setStyleSheet(f'QPushButton{{background:{bg};border:1px solid #E6EAF0;border-radius:9px;padding:6px 10px;font-weight:800;color:#334155;}} QPushButton:hover{{border-color:#BAC5D1;}}')
            btn.setMinimumHeight(31)
            btn.clicked.connect(lambda checked=False, k=key: self.navigateRequested.emit(k))
            self.task_buttons[key] = btn; task_bar.addWidget(btn)
        tl.addLayout(task_bar, 1)
        root.addWidget(task_card)

        # 第一列圖表：三倉 + 庫存健康 + 貨櫃
        charts = QHBoxLayout(); charts.setSpacing(10)
        wh_card = self._section('三倉庫存分布', '目前三個倉別的現貨分布')
        self.wh_chart = MiniBarChart(); wh_card.layout().addWidget(self.wh_chart)
        charts.addWidget(wh_card, 2)

        health_card = self._section('庫存健康度', '正常品項占庫存快照比例')
        self.health_donut = DonutWidget(); health_card.layout().addWidget(self.health_donut, alignment=Qt.AlignmentFlag.AlignCenter)
        charts.addWidget(health_card, 1)

        container_card = self._section('進口貨櫃', '依目前實際採購量與包裝 CBM 計算')
        self.container_donut = DonutWidget(); container_card.layout().addWidget(self.container_donut, alignment=Qt.AlignmentFlag.AlignCenter)
        self.container_hint = QLabel(''); self.container_hint.setObjectName('muted'); self.container_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_card.layout().addWidget(self.container_hint)
        charts.addWidget(container_card, 1)
        root.addLayout(charts)

        # 第二列：需求趨勢 + 資料狀態。高度刻意壓低。
        trends = QHBoxLayout(); trends.setSpacing(10)
        demand_card = self._section('客戶需求趨勢', '依到貨日期 / 採購日期彙整')
        self.demand_trend = TrendChart(); demand_card.layout().addWidget(self.demand_trend)
        trends.addWidget(demand_card, 2)

        status_card = self._section('資料狀態', '各模組最後一次快照')
        self.status_labels = []
        for _ in range(4):
            lab = QLabel(''); lab.setWordWrap(False)
            lab.setObjectName('statusLine')
            self.status_labels.append(lab); status_card.layout().addWidget(lab)
        status_card.layout().addStretch()
        trends.addWidget(status_card, 1)
        root.addLayout(trends)

        # 最下面改成「三欄緊湊區」，不再用 230px 高表格造成畫面被截掉。
        bottom = QHBoxLayout(); bottom.setSpacing(10)
        alert_card = self._section('需要注意的產品', '低庫存 / 缺貨 / 注意')
        self.alert_table = self._make_table(['產品編號', '產品名稱', '狀態', '庫存'], 5)
        alert_card.layout().addWidget(self.alert_table); bottom.addWidget(alert_card, 4)

        pcard = self._section('採購量 Top 8', '依實際採購量排序')
        self.top_purchase_table = self._make_table(['產品編號', '產品名稱', '採購量'], 5)
        pcard.layout().addWidget(self.top_purchase_table); bottom.addWidget(pcard, 3)

        dcard = self._section('客戶需求 Top 8', '依選定需求區間排序')
        self.top_demand_table = self._make_table(['產品編號', '產品名稱', '需求量'], 5)
        dcard.layout().addWidget(self.top_demand_table); bottom.addWidget(dcard, 3)
        root.addLayout(bottom)

        # 供應商金額區：只用一張緊湊表，避免 Dashboard 再往下長太多。
        spend_card = self._section('供應商採購金額', '不同幣別分開計算，不做錯誤加總')
        spend_top = QHBoxLayout()
        self.amount_summary = QLabel('尚無金額資料'); self.amount_summary.setObjectName('amountSummary')
        spend_top.addWidget(self.amount_summary); spend_top.addStretch(); spend_card.layout().addLayout(spend_top)
        self.supplier_spend_table = self._make_table(['供應商', '幣別', '金額'], 5)
        spend_card.layout().addWidget(self.supplier_spend_table)
        root.addWidget(spend_card)

        self.btn_refresh.clicked.connect(self.refresh_data)
        self.range_combo.currentIndexChanged.connect(self.refresh_data)

    def apply_theme(self):
        a = SystemSettingsService.load().get("appearance", {})
        bg = a.get("content_bg", "#F8F6F2")
        card = a.get("card_bg", "#FFFFFF")
        text = a.get("content_text", "#18212B")
        muted = a.get("muted_text", "#728091")
        accent = a.get("accent", "#5DBDAD")
        border = a.get("border", "#E5E1DB")
        header = a.get("table_header_bg", "#F4F6F8")
        self.setStyleSheet(f"""
            DashboardPage {{ background:{bg}; }}
            QLabel {{ background:transparent; color:{text}; }}
            QLabel#dashboardTitle {{ font-size:22px;font-weight:900;color:{text}; }}
            QFrame#metricCard, QFrame#sectionCard {{ background:{card}; border:1px solid {border}; border-radius:14px; }}
            QFrame#metricCard:hover {{ border-color:{accent}; }}
            QLabel#muted {{ color:{muted}; font-size:11px; }}
            QLabel#metricTitle {{ color:{muted}; font-size:11px; font-weight:700; }}
            QLabel#metricValue {{ color:{text}; font-size:20px; font-weight:800; }}
            QLabel#sectionTitle {{ color:{text}; font-size:14px; font-weight:800; }}
            QLabel#amountSummary {{ color:{text};font-size:13px;font-weight:800; }}
            QLabel#statusLine {{ padding:5px 1px;border-bottom:1px solid {border};color:{muted};background:transparent; }}
            QTableWidget {{ background:{card}; color:{text}; border:none; gridline-color:{border}; }}
            QHeaderView::section {{ background:{header}; color:{text}; border:none; border-bottom:1px solid {border}; padding:5px; font-weight:700; }}
            QComboBox {{ background:{card}; color:{text}; border:1px solid {border}; border-radius:7px; padding:5px 9px; min-width:105px; }}
        """)
        if hasattr(self, "content"):
            self.content.setStyleSheet(f"background:{bg};")
        self.update()

    def show_notifications(self):
        dlg = NotificationCenterDialog(self)
        dlg.navigateRequested.connect(self.navigateRequested.emit)
        dlg.exec()

    def _section(self, title, hint=''):
        card = QFrame(); card.setObjectName('sectionCard')
        lay = QVBoxLayout(card); lay.setContentsMargins(14, 10, 14, 10); lay.setSpacing(4)
        t = QLabel(title); t.setObjectName('sectionTitle'); lay.addWidget(t)
        if hint:
            h = QLabel(hint); h.setObjectName('muted'); lay.addWidget(h)
        return card

    def _make_table(self, headers, visible_rows=5):
        table = QTableWidget()
        table.setColumnCount(len(headers)); table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(False)
        table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        row_h = 25
        table.verticalHeader().setDefaultSectionSize(row_h)
        table.setFixedHeight(31 + visible_rows * row_h + 4)
        return table

    def _reflow_metric_cards(self, columns):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
        for idx, card in enumerate(self.metric_cards):
            self.cards_layout.addWidget(card, idx // columns, idx % columns)
        for c in range(columns):
            self.cards_layout.setColumnStretch(c, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        columns = 6 if w >= 1450 else (3 if w >= 900 else 2)
        current_positions = []
        for i in range(self.cards_layout.count()):
            index = self.cards_layout.getItemPosition(i)
            current_positions.append(index)
        expected_rows = (len(self.metric_cards) + columns - 1) // columns
        # 只有欄數真的改變才重新排版。
        if getattr(self, '_metric_columns', None) != columns:
            self._metric_columns = columns
            self._reflow_metric_cards(columns)

    def showEvent(self, event):
        super().showEvent(event)
        self.apply_theme()
        self.refresh_data()

    def refresh_data(self):
        days = self.range_combo.currentData() if hasattr(self, 'range_combo') else None
        data = DashboardDataService.summary(days=days)
        settings = SystemSettingsService.load()
        # 正式 EXE 不直接顯示舊 system_settings.json 裡的 tier/development_mode；
        # 必須使用經 BuildConfig + Signed Receipt 計算後的有效授權狀態。
        tier = SystemSettingsService.get_tier()
        tier_name = SystemSettingsService.TIER_NAMES.get(tier, '一般版')
        dev = SystemSettingsService.is_development_mode()
        if dev:
            tier_status = f"{tier_name} · 開發測試"
        else:
            try:
                from services.license_client_service import LicenseClientService
                receipt = LicenseClientService.current_receipt()
            except Exception:
                receipt = None
            tier_status = f"{tier_name} · 正式授權" if receipt else f"{tier_name} · 未授權"
        self.tier_label.setText(tier_status)
        intermediate = SystemSettingsService.effective_has_tier('intermediate')
        advanced = SystemSettingsService.effective_has_tier('advanced')
        for key in ['purchase', 'urgent']:
            self.cards[key].setEnabled(intermediate)
        for key in ['amount', 'container', 'finance_ar', 'cash']:
            self.cards[key].setEnabled(advanced)
        self.btn_notify.setEnabled(advanced)
        self.btn_notify.setToolTip('' if advanced else '通知中心需要高級版')
        if advanced:
            count = len([x for x in NotificationService.build_notifications() if x.get('level') != 'ok'])
            self.btn_notify.setText(f'🔔 通知中心 {count}' if count else '🔔 通知中心')
        else:
            self.btn_notify.setText('🔒 通知中心')

        self.cards['inventory'].value_label.setText(f"{data['total_stock']:,.0f}")
        self.cards['customer'].value_label.setText(f"{data['demand_total']:,.0f}")
        self.cards['purchase'].value_label.setText(f"{data['need_purchase_count']:,}")
        self.cards['urgent'].value_label.setText(f"{max(data['urgent_purchase_count'], data['low_stock_count']):,}")
        self.cards['amount'].value_label.setText(data['purchase_amount_primary'])
        self.cards['amount'].hint_label.setText('不同幣別分開統計')
        self.cards['container'].value_label.setText(f"{data['last_container_usage']:.0f}%" if data['container_count'] else '0%')
        self.cards['container'].hint_label.setText(f"{data['total_cbm']:.1f} / {data['container_cbm']:.1f} CBM")
        finance = FinancialService.summary() if advanced else {}
        self.cards['finance_ar'].value_label.setText(f"{finance.get('overdue_twd',0):,.0f}" if advanced else '🔒')
        self.cards['finance_ar'].hint_label.setText(f"逾期 {finance.get('overdue_count',0)} 筆" if advanced else '高級版功能')
        self.cards['cash'].value_label.setText(f"{finance.get('cash_net_twd',0):,.0f}" if advanced else '🔒')
        self.cards['cash'].hint_label.setText('TWD 淨現金流' if advanced else '高級版功能')
        if not intermediate:
            self.cards['purchase'].value_label.setText('🔒')
            self.cards['urgent'].value_label.setText('🔒')
        if not advanced:
            self.cards['amount'].value_label.setText('🔒')
            self.cards['amount'].hint_label.setText('高級版功能')
            self.cards['container'].value_label.setText('🔒')
            self.cards['container'].hint_label.setText('高級版功能')
            self.cards['finance_ar'].value_label.setText('🔒'); self.cards['finance_ar'].hint_label.setText('高級版功能')
            self.cards['cash'].value_label.setText('🔒'); self.cards['cash'].hint_label.setText('高級版功能')

        self.task_buttons['purchase'].setText(f"急需採購  {data['urgent_purchase_count']} 項" if intermediate else '🔒 採購建議 · 中階版')
        self.task_buttons['unmapped'].setText(f"未對應需求  {data['unmapped_count']} 項")
        self.task_buttons['transfer'].setText(f"跨倉調撥  {data['transfer_count']} 筆" if intermediate else '🔒 跨倉調撥 · 中階版')
        self.task_buttons['shortage'].setText(f"調撥後仍缺貨  {data['transfer_remaining_shortage']} 項" if intermediate else '🔒 調撥分析 · 中階版')

        self.wh_chart.set_data(data['warehouse_names'], data['warehouse_totals'])
        health_total = sum(data['inventory_health'].values()) or 1
        self.health_donut.set_data(data['inventory_health'].get('正常', 0), health_total, '正常品項 / 庫存快照')
        self.container_donut.set_data(data['last_container_usage'], 100, '最後一櫃使用率')
        self.container_hint.setText(f"總計 {data['total_cbm']:.1f} CBM · 約 {data['container_count']} 櫃")
        self.demand_trend.set_data(data['demand_trend_labels'], data['demand_trend_values'])

        self._fill_rows(self.alert_table, [[x['產品編號'], x['產品名稱'], x['狀態'], f"{x['目前庫存']:,.0f}"] for x in data['alerts']])
        self._fill_rows(self.top_purchase_table, [[x['產品編號'], x['產品名稱'], f"{x['數量']:,.0f}"] for x in data['top_purchase']])
        self._fill_rows(self.top_demand_table, [[x['產品編號'], x['產品名稱'], f"{x['數量']:,.0f}"] for x in data['top_demand']])
        self._fill_rows(self.supplier_spend_table, [[x['供應商'], x['幣別'], f"{x['金額']:,.2f}"] for x in data['supplier_spend']])
        self.amount_summary.setText(data['currency_summary'])

        updates = [
            ('客戶需求', data['customer_updated_at']), ('庫存分析', data['inventory_updated_at']),
            ('採購建議', data['purchase_updated_at']), ('產品主檔', f"{data['product_count']} 個產品"),
        ]
        for lab, (name, value) in zip(self.status_labels, updates):
            lab.setText(f"● {name}　{value or '尚無快照'}")

        if not data['has_demand_detail'] and days:
            self.subtitle.setText('目前舊快照沒有需求日期明細；重新匯入一次 PDF / Excel 後即可使用日期區間與趨勢')
        else:
            self.subtitle.setText('庫存、需求、採購、調撥與進口作業即時總覽')

    def _fill_rows(self, table, rows):
        table.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for c, value in enumerate(values):
                table.setItem(r, c, QTableWidgetItem(str(value)))
