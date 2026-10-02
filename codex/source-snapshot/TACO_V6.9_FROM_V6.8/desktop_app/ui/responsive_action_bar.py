from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtWidgets import QLayout, QSizePolicy, QSpacerItem, QWidgetItem


class FlowLayout(QLayout):
    """會依視窗寬度自動換行的工具列 Layout。

    目的：避免原本 QHBoxLayout 在視窗縮小時，把按鈕文字壓到消失。
    可以直接像一般 layout 使用 addWidget / addLayout；addStretch 會加入柔性空白。
    """

    def __init__(self, parent=None, margin=0, h_spacing=8, v_spacing=8):
        super().__init__(parent)
        self._items = []
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self._items.append(item)

    def addStretch(self, stretch=0):
        spacer = QSpacerItem(16, 1, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.addItem(spacer)

    def addSpacing(self, size):
        """相容 QBoxLayout.addSpacing()。

        舊頁面原本使用 QHBoxLayout，因此會呼叫 addSpacing。
        FlowLayout 改成響應式後也提供同名方法，避免頁面啟動時 AttributeError。
        """
        try:
            size = max(0, int(size))
        except Exception:
            size = 0
        spacer = QSpacerItem(size, 1, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self.addItem(spacer)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective.x()
        y = effective.y()
        line_height = 0

        for item in self._items:
            # Expanding spacer：在 flow 中視為小間隔，不強迫把後面的按鈕推到畫面外。
            if isinstance(item, QSpacerItem):
                x += 8
                continue

            hint = item.sizeHint()
            next_x = x + hint.width() + self._h_spacing
            if next_x - self._h_spacing > effective.right() and line_height > 0:
                x = effective.x()
                y += line_height + self._v_spacing
                next_x = x + hint.width() + self._h_spacing
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))

            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + margins.bottom()


def compact_button(button, primary=False, danger=False):
    """統一既有按鈕尺寸。文字不會因為縮小視窗而被壓成 0 寬。"""
    button.setMinimumHeight(34)
    button.setMinimumWidth(max(72, button.sizeHint().width()))
    button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    role = "primary" if primary else ("danger" if danger else "secondary")
    button.setProperty("buttonRole", role)
    return button
