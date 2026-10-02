"""純角色權限規則，不依賴 PyQt6。

原本這些規則（誰能看哪個頁面、誰是唯讀角色）跟畫面套用邏輯
（RolePermissionService.apply_to_widget，需要 import PyQt6 的 QPushButton /
QTableWidget）寫在同一個檔案裡。這造成一個不必要的耦合：任何只是想「檢查
目前使用者是不是管理員」的程式碼（例如 service 層的權限檢查），都會被迫
連帶載入 PyQt6，即使它跟畫面完全無關。

把純規則搬到這個獨立檔案，好處：
1. service 層（security.py）做權限檢查時不需要牽動 UI framework，
   耦合更少、也更容易個別測試。
2. 未來如果要幫這套系統加自動化測試、或改成 Web/API 版本，這些角色規則
   可以直接重用，不必連 PyQt6 一起搬過去。

ui/main_window.py 和 services/role_permission_service.py 都改成從這裡讀取
規則，維持行為完全不變。
"""

PAGE_RULES = {
    "系統管理員": {"dashboard", "inventory", "purchase", "customer", "supplier", "finance", "settings", "help", "audit", "integration"},
    "採購管理者": {"dashboard", "inventory", "purchase", "customer", "supplier", "finance", "help", "audit", "integration"},
    "採購人員": {"dashboard", "inventory", "purchase", "customer", "supplier", "help", "audit", "integration"},
    "倉管": {"dashboard", "inventory", "customer", "help", "audit", "integration"},
    "主管": {"dashboard", "inventory", "purchase", "customer", "supplier", "finance", "help", "audit", "integration"},
    "財務人員": {"dashboard", "finance", "supplier", "help", "audit"},
}

READ_ONLY_ROLES = {"主管"}

ADMIN_ROLE = "系統管理員"


def current_role():
    # 延遲匯入，避免和 user_auth_service 之間形成模組載入時的循環匯入。
    from services.user_auth_service import UserAuthService
    user = UserAuthService.current_user() or {}
    return str(user.get("role", "主管"))


def page_allowed(page_key, role=None):
    role = role if role is not None else current_role()
    return page_key in PAGE_RULES.get(role, {"dashboard"})


def is_read_only(role=None):
    role = role if role is not None else current_role()
    return role in READ_ONLY_ROLES


def can_manage_users(role=None):
    role = role if role is not None else current_role()
    return role == ADMIN_ROLE


def is_admin(role=None):
    role = role if role is not None else current_role()
    return role == ADMIN_ROLE
