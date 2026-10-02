from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox,
    QDialogButtonBox, QLabel
)
from services.import_profile_service import ImportProfileService


class ImportProfileDialog(QDialog):
    def __init__(self, product_no, product_name, supplier_name="", parent=None):
        super().__init__(parent)
        self.product_no = product_no
        self.supplier_name = supplier_name
        self.setWindowTitle("包裝／進口貨櫃設定")
        self.setMinimumWidth(520)
        layout = QFormLayout(self)
        layout.addRow("產品", QLabel(f"{product_no}  {product_name}"))
        layout.addRow("供應商", QLabel(supplier_name or "未指定"))
        p = ImportProfileService.get_profile(product_no, supplier_name)

        self.currency = QComboBox(); self.currency.addItems(["USD", "CNY", "TWD", "JPY", "EUR"]); self.currency.setCurrentText(p.get("currency", "USD"))
        self.unit_price = QDoubleSpinBox(); self.unit_price.setDecimals(6); self.unit_price.setRange(0, 999999999); self.unit_price.setValue(float(p.get("unit_price", 0) or 0))
        self.price_unit = QComboBox(); self.price_unit.addItems(["包", "箱", "KG", "個", "支", "雙", "盒"]); self.price_unit.setCurrentText(str(p.get("price_unit", "包")))
        self.purchase_unit = QComboBox(); self.purchase_unit.addItems(["箱", "包", "盒", "KG", "個", "支", "雙"]); self.purchase_unit.setCurrentText(str(p.get("purchase_qty_unit", "箱")))
        self.packing = QLineEdit(str(p.get("packing_method", "")))
        self.units_per_carton = QDoubleSpinBox(); self.units_per_carton.setDecimals(2); self.units_per_carton.setRange(0, 10000000); self.units_per_carton.setValue(float(p.get("units_per_carton", 0) or 0))
        self.L = QDoubleSpinBox(); self.L.setRange(0, 1000); self.L.setDecimals(2); self.L.setValue(float(p.get("carton_length_cm", 0) or 0))
        self.W = QDoubleSpinBox(); self.W.setRange(0, 1000); self.W.setDecimals(2); self.W.setValue(float(p.get("carton_width_cm", 0) or 0))
        self.H = QDoubleSpinBox(); self.H.setRange(0, 1000); self.H.setDecimals(2); self.H.setValue(float(p.get("carton_height_cm", 0) or 0))
        self.container = QDoubleSpinBox(); self.container.setRange(1, 1000); self.container.setDecimals(2); self.container.setValue(float(p.get("container_cbm", 66.5) or 66.5)); self.container.setEnabled(False); self.container.setToolTip("貨櫃容量由『系統設定 → 倉庫管理』集中管理")

        layout.addRow("幣別", self.currency)
        layout.addRow("單價", self.unit_price)
        layout.addRow("計價單位", self.price_unit)
        layout.addRow("實際採購量的單位", self.purchase_unit)
        layout.addRow("包裝方式", self.packing)
        layout.addRow("每箱數量", self.units_per_carton)
        layout.addRow("紙箱長 CM", self.L)
        layout.addRow("紙箱寬 CM", self.W)
        layout.addRow("紙箱高 CM", self.H)
        layout.addRow("貨櫃可用體積 CBM（系統設定）", self.container)
        help_label = QLabel("例如：採購建議中的 120,000 是『包』，這裡就選包；若採購量本身就是 100 箱，才選箱。此欄會直接影響換算箱數與 CBM。")
        help_label.setWordWrap(True)
        layout.addRow("說明", help_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def profile(self):
        return {
            "currency": self.currency.currentText(),
            "unit_price": self.unit_price.value(),
            "price_unit": self.price_unit.currentText(),
            "purchase_qty_unit": self.purchase_unit.currentText(),
            "packing_method": self.packing.text().strip(),
            "units_per_carton": self.units_per_carton.value(),
            "carton_length_cm": self.L.value(),
            "carton_width_cm": self.W.value(),
            "carton_height_cm": self.H.value(),
            "container_cbm": self.container.value(),
        }
