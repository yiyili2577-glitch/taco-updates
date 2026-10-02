from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QPushButton, QStackedWidget, QSizePolicy


class TwoRowTabWidget(QWidget):
    """A lightweight multi-row tab control used for dense ERP workflows.

    Goals:
    - keep all finance workflow tabs visible without horizontal scrolling
    - preserve a simple addTab / setCurrentIndex API similar to QTabWidget
    - allow 2 fixed rows by default for faster scanning
    """

    currentChanged = pyqtSignal(int)

    def __init__(self, columns=11, parent=None):
        super().__init__(parent)
        self._columns = max(1, int(columns))
        self._buttons = []
        self._pages = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        self.tab_bar_widget = QWidget(self)
        self.tab_bar_widget.setObjectName('erpTabBar')
        self.grid = QGridLayout(self.tab_bar_widget)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(8)
        root.addWidget(self.tab_bar_widget)

        self.stack = QStackedWidget(self)
        self.stack.setObjectName('erpTabStack')
        self.stack.currentChanged.connect(self.currentChanged.emit)
        root.addWidget(self.stack, 1)

    def addTab(self, widget, label):
        index = len(self._buttons)
        button = QPushButton(label)
        button.setCheckable(True)
        button.setProperty('tabButton', True)
        button.setProperty('tabIndex', index)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.setMinimumHeight(36)
        button.clicked.connect(lambda checked=False, i=index: self.setCurrentIndex(i))
        row = index // self._columns
        col = index % self._columns
        self.grid.addWidget(button, row, col)
        self._buttons.append(button)
        self._pages.append(widget)
        self.stack.addWidget(widget)
        if index == 0:
            self.setCurrentIndex(0)
        return index

    def count(self):
        return self.stack.count()

    def currentIndex(self):
        return self.stack.currentIndex()

    def widget(self, index):
        return self.stack.widget(index)

    def setCurrentIndex(self, index):
        if not (0 <= index < self.stack.count()):
            return
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self._buttons):
            button.setChecked(i == index)
            button.setProperty('active', i == index)
            button.style().unpolish(button)
            button.style().polish(button)
        self.tab_bar_widget.update()
