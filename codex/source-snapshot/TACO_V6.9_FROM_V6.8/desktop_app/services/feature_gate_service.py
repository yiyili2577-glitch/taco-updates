from PyQt6.QtWidgets import QPushButton, QTabWidget, QAbstractItemView, QTableView
from services.system_settings_service import SystemSettingsService
from services.license_client_service import LicenseClientService


class FeatureGateService:
    """把版本層級實際套用到現有 UI 控制項。

    開發測試模式仍依「目前選擇版本」顯示差異，方便測試三種商品層級。
    """

    BUTTON_RULES = [
        ("財務", "advanced"),
        ("付款", "advanced"),
        ("匯率", "advanced"),
        ("混櫃", "advanced"),
        ("包裝 / 進口", "advanced"),
        ("包裝／進口", "advanced"),
        ("進口設定", "advanced"),
        ("CBM", "advanced"),
        ("SQL", "advanced"),
        ("三倉調撥", "intermediate"),
        ("跨倉", "intermediate"),
        ("調撥", "intermediate"),
        ("匯出目前表 PDF", "intermediate"),
        ("匯出 PDF", "intermediate"),
        ("PDF 匯出", "intermediate"),
        ("三倉名稱", "intermediate"),
        ("三倉庫存", "intermediate"),
    ]


    READONLY_ALLOWED_BUTTON_MARKERS = (
        "查看", "重新整理", "搜尋", "篩選", "匯出", "備份", "列印",
        "重新驗證", "使用新的授權", "新授權", "關閉", "取消", "操作說明",
    )

    @staticmethod
    def _readonly_button_allowed(text):
        text = str(text or "")
        return any(marker in text for marker in FeatureGateService.READONLY_ALLOWED_BUTTON_MARKERS)
    @staticmethod
    def allowed(required):
        return SystemSettingsService.effective_has_tier(required)

    @staticmethod
    def required_for_button(text):
        text = str(text or "")
        for marker, tier in FeatureGateService.BUTTON_RULES:
            if marker in text:
                return tier
        return "general"

    @staticmethod
    def apply_to_widget(root):
        readonly = LicenseClientService.restricted_readonly_mode()
        for button in root.findChildren(QPushButton):
            required = FeatureGateService.required_for_button(button.text())
            allowed = FeatureGateService.allowed(required)
            gate_disabled = bool(button.property("featureGateDisabled"))
            readonly_disabled = bool(button.property("licenseReadonlyDisabled"))
            if not allowed:
                button.setEnabled(False)
                button.setProperty("featureGateDisabled", True)
                button.setToolTip(f"此功能需要 {SystemSettingsService.TIER_NAMES.get(required, required)} 或以上版本。")
            elif readonly and not FeatureGateService._readonly_button_allowed(button.text()):
                button.setEnabled(False)
                button.setProperty("licenseReadonlyDisabled", True)
                button.setToolTip("授權需重新連線驗證，目前為只讀／備份模式。")
            else:
                if gate_disabled:
                    button.setProperty("featureGateDisabled", False)
                if readonly_disabled:
                    button.setProperty("licenseReadonlyDisabled", False)
                if gate_disabled or readonly_disabled:
                    button.setEnabled(True)
                    button.setToolTip("")

        for table in root.findChildren(QTableView):
            if table.property("licenseOriginalEditTriggers") is None:
                table.setProperty("licenseOriginalEditTriggers", int(table.editTriggers().value))
            if readonly:
                table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                table.setProperty("licenseReadonlyTable", True)
            elif bool(table.property("licenseReadonlyTable")):
                try:
                    original = int(table.property("licenseOriginalEditTriggers"))
                    table.setEditTriggers(QAbstractItemView.EditTrigger(original))
                except Exception:
                    pass
                table.setProperty("licenseReadonlyTable", False)
        return root
