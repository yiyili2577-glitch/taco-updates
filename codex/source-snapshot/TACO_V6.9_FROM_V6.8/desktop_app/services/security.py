from services.safe_storage import get_logger
from services import role_rules


class PermissionDeniedError(PermissionError):
    """使用者權限不足，無法執行此動作。"""


def _current_role():
    return role_rules.current_role()


def is_admin():
    return role_rules.is_admin(_current_role())



def require_write_access(action_desc="", allow_backup=False):
    """離線寬限逾期或偵測到時鐘倒退時，正式版進入只讀/備份模式。

    - 仍允許查看、匯出與資料儲存點備份。
    - 阻擋新增、修改、刪除、付款、月結、資料還原等寫入。
    - 開發模式不受此限制。
    """
    try:
        from services.build_config import BuildConfig
        from services.license_client_service import LicenseClientService
        if BuildConfig.is_development():
            return True
        if not LicenseClientService.restricted_readonly_mode():
            return True
        if allow_backup:
            return True
        get_logger().warning("只讀模式拒絕寫入：角色「%s」嘗試執行「%s」。", _current_role(), action_desc or "資料修改")
        raise PermissionDeniedError(
            "目前正式授權需要重新連線驗證，TACO 已進入只讀／備份模式。"
            "可查看、備份與匯出資料，但暫停新增、修改、刪除及高風險作業。"
        )
    except PermissionDeniedError:
        raise
    except Exception:
        # 授權狀態檢查本身若失敗，正式版採 fail-closed。
        from services.build_config import BuildConfig
        if BuildConfig.is_production():
            raise PermissionDeniedError("無法確認正式授權寫入狀態，已暫停資料修改。")
        return True

def require_admin(action_desc="", allow_readonly_backup=False):
    """限制只有系統管理員可以執行的動作。

    這是 service 層的防線：原本的權限控制（RolePermissionService /
    FeatureGateService）只有停用畫面上的按鈕，任何人只要直接呼叫底層的
    service 函式（例如寫一段小程式、或用互動式 shell）就能完全繞過。
    這裡在資料真正被寫入之前再檢查一次角色，非管理員呼叫時會丟出
    PermissionDeniedError，並在 log 留一筆紀錄方便事後追查。
    """
    require_write_access(action_desc, allow_backup=allow_readonly_backup)
    if not is_admin():
        get_logger().warning("權限拒絕：角色「%s」嘗試執行「%s」。", _current_role(), action_desc or "管理動作")
        detail = f"：{action_desc}" if action_desc else "。"
        raise PermissionDeniedError(f"這個動作需要系統管理員權限{detail}")


def require_self_or_admin(target_username, action_desc=""):
    """只允許「本人」或「系統管理員」執行的動作（例如修改自己的密碼）。"""
    require_write_access(action_desc)
    from services.user_auth_service import UserAuthService
    current = UserAuthService.current_user() or {}
    current_username = str(current.get("username", "")).strip().lower()
    target = str(target_username or "").strip().lower()
    if current_username and current_username == target:
        return
    require_admin(action_desc)


def require_tier(required, action_desc=""):
    """service 層版本權限檢查，避免只靠 UI 按鈕停用。"""
    require_write_access(action_desc)
    from services.system_settings_service import SystemSettingsService
    if not SystemSettingsService.effective_has_tier(required):
        label = SystemSettingsService.TIER_NAMES.get(required, required)
        get_logger().warning("版本權限拒絕：角色「%s」嘗試執行「%s」，需要 %s。", _current_role(), action_desc or "受限功能", label)
        raise PermissionDeniedError(f"此功能需要 {label} 或以上版本。")
