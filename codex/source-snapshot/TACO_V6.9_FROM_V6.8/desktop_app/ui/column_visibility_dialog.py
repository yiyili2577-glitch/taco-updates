from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QCheckBox, QDialogButtonBox
)


class ColumnVisibilityDialog(QDialog):
    """讓使用者自行決定表格要顯示哪些欄位。"""

    def __init__(self, table, parent=None, title="欄位顯示設定"):
        super().__init__(parent)
        self.table = table
        self.setWindowTitle(title)
        self.resize(440, 560)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("勾選要顯示的欄位。取消勾選後只會暫時隱藏，不會刪除資料。"))

        quick = QHBoxLayout()
        btn_all = QPushButton("☑ 全部顯示")
        btn_none = QPushButton("☐ 全部隱藏")
        quick.addWidget(btn_all)
        quick.addWidget(btn_none)
        quick.addStretch()
        layout.addLayout(quick)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        self.checkboxes = []

        for col in range(table.columnCount()):
            item = table.horizontalHeaderItem(col)
            name = item.text() if item else f"欄位 {col + 1}"
            cb = QCheckBox(name)
            cb.setChecked(not table.isColumnHidden(col))
            cb.setProperty("column_index", col)
            self.checkboxes.append(cb)
            body_layout.addWidget(cb)

        body_layout.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(buttons)

        btn_all.clicked.connect(lambda: self._set_all(True))
        btn_none.clicked.connect(lambda: self._set_all(False))
        buttons.button(QDialogButtonBox.StandardButton.Apply).setText("套用")
        buttons.accepted.connect(self.apply_and_accept)
        buttons.rejected.connect(self.reject)

    def _set_all(self, checked):
        for cb in self.checkboxes:
            cb.setChecked(checked)

    def apply_and_accept(self):
        # 至少保留一欄，避免整張表看起來消失。
        if not any(cb.isChecked() for cb in self.checkboxes) and self.checkboxes:
            self.checkboxes[0].setChecked(True)

        for cb in self.checkboxes:
            col = int(cb.property("column_index"))
            self.table.setColumnHidden(col, not cb.isChecked())
        self.accept()
