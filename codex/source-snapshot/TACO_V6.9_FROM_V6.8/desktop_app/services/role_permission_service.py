from PyQt6.QtWidgets import QPushButton, QTableWidget, QAbstractItemView

from services import role_rules


class RolePermissionService:
    """畫面層的角色權限套用。

    純規則（誰能看哪頁、誰是唯讀）已經搬到不依賴 PyQt6 的 services/role_rules.py，
    這裡保留原本的公開介面（role/page_allowed/is_read_only/can_manage_users/
    apply_to_widget），只是內部改成呼叫 role_rules，維持對外行為完全不變、
    不用改動任何呼叫端程式碼。
    """

    PAGE_RULES = role_rules.PAGE_RULES
    READ_ONLY_ROLES = role_rules.READ_ONLY_ROLES

    MUTATION_MARKERS = [
        "儲存", "新增", "刪除", "清除", "修改", "套用", "重新計算", "實際採購量設為",
        "加入", "匯入", "取代", "啟用", "設定", "變更", "調撥", "履約", "出貨分流", "重新載入客戶需求",
    ]

    @staticmethod
    def role():
        return role_rules.current_role()

    @staticmethod
    def page_allowed(page_key):
        return role_rules.page_allowed(page_key)

    @staticmethod
    def is_read_only():
        return role_rules.is_read_only()

    @staticmethod
    def can_manage_users():
        return role_rules.can_manage_users()

    @staticmethod
    def apply_to_widget(root):
        read_only = RolePermissionService.is_read_only()

        for button in root.findChildren(QPushButton):
            was_role_disabled = bool(button.property("rolePermissionDisabled"))
            text = str(button.text() or "")
            should_disable = read_only and any(marker in text for marker in RolePermissionService.MUTATION_MARKERS)
            if should_disable:
                if button.isEnabled():
                    button.setProperty("rolePermissionDisabled", True)
                    button.setEnabled(False)
                    button.setToolTip("主管角色為唯讀模式，不能修改資料。")
            elif was_role_disabled:
                button.setProperty("rolePermissionDisabled", False)
                button.setEnabled(True)
                button.setToolTip("")

        for table in root.findChildren(QTableWidget):
            if table.property("roleOriginalEditTriggers") is None:
                table.setProperty("roleOriginalEditTriggers", int(table.editTriggers().value))
            if read_only:
                table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            else:
                try:
                    original = int(table.property("roleOriginalEditTriggers"))
                    table.setEditTriggers(QAbstractItemView.EditTrigger(original))
                except Exception:
                    pass
        return root
