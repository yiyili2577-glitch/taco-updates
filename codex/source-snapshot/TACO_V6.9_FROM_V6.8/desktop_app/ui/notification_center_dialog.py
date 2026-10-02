from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QScrollArea, QWidget
from services.notification_service import NotificationService


class NotificationCenterDialog(QDialog):
    navigateRequested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("通知中心")
        self.resize(650, 540)
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        title = QLabel("通知中心"); title.setStyleSheet("font-size:22px;font-weight:900;")
        refresh = QPushButton("⟳ 重新整理"); refresh.clicked.connect(self.refresh)
        top.addWidget(title); top.addStretch(); top.addWidget(refresh); root.addLayout(top)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(self.scroll, 1)
        self.refresh()

    def refresh(self):
        holder = QWidget(); lay = QVBoxLayout(holder); lay.setContentsMargins(2, 2, 2, 2); lay.setSpacing(8)
        colors = {"urgent": "#FCE8E8", "warning": "#FFF3D9", "info": "#E8F3FF", "ok": "#E7F6EF"}
        for item in NotificationService.build_notifications():
            card = QFrame(); card.setStyleSheet(f"QFrame{{background:{colors.get(item['level'], '#FFFFFF')};border:1px solid rgba(120,120,120,45);border-radius:10px;}}")
            row = QHBoxLayout(card); row.setContentsMargins(12, 10, 12, 10)
            txt = QVBoxLayout(); t = QLabel(item["title"]); t.setStyleSheet("font-weight:800;font-size:14px;")
            m = QLabel(item["message"]); m.setWordWrap(True)
            txt.addWidget(t); txt.addWidget(m); row.addLayout(txt, 1)
            btn = QPushButton("前往處理")
            btn.clicked.connect(lambda _=False, k=item["target"]: self._go(k))
            row.addWidget(btn)
            lay.addWidget(card)
        lay.addStretch(); self.scroll.setWidget(holder)

    def _go(self, key):
        self.navigateRequested.emit(key)
        self.accept()
