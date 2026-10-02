import hashlib
import hmac
import os
import secrets
from copy import deepcopy
from datetime import datetime

from services.app_paths import AppPaths
from services.safe_storage import SafeStorage, get_logger
from services import security


class UserAuthService:
    BASE_DIR = str(AppPaths.install_dir())
    DATA_DIR = str(AppPaths.data_dir())
    DATA_FILE = os.path.join(DATA_DIR, "users.json")

    ROLE_LABELS = ["系統管理員", "採購管理者", "採購人員", "倉管", "主管", "財務人員"]
    _current_user = None

    @staticmethod
    def _ensure():
        os.makedirs(UserAuthService.DATA_DIR, exist_ok=True)

    @staticmethod
    def _normalize_username(username):
        return str(username or "").strip().lower()

    @staticmethod
    def _public_user(user):
        if not isinstance(user, dict):
            return None
        return {
            "username": str(user.get("username", "")),
            "display_name": str(user.get("display_name", "")),
            "email": str(user.get("email", "")),
            "role": str(user.get("role", "採購人員")),
            "company": str(user.get("company", "")),
            "enabled": bool(user.get("enabled", True)),
            "created_at": str(user.get("created_at", "")),
            "last_login_at": str(user.get("last_login_at", "")),
        }

    @staticmethod
    def load_users():
        UserAuthService._ensure()
        data = SafeStorage.safe_read_json(UserAuthService.DATA_FILE, default={})
        users = data.get("users", []) if isinstance(data, dict) else []
        return users if isinstance(users, list) else []

    @staticmethod
    def save_users(users):
        UserAuthService._ensure()
        SafeStorage.atomic_write_json(UserAuthService.DATA_FILE, {"users": users})

    @staticmethod
    def has_users():
        return len(UserAuthService.load_users()) > 0

    @staticmethod
    def _hash_password(password, salt=None, iterations=220000):
        password = str(password or "")
        salt_bytes = bytes.fromhex(salt) if salt else secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, iterations)
        return {
            "salt": salt_bytes.hex(),
            "hash": digest.hex(),
            "iterations": iterations,
        }

    @staticmethod
    def _verify_password(password, user):
        try:
            expected = bytes.fromhex(str(user.get("password_hash", "")))
            salt = str(user.get("password_salt", ""))
            iterations = int(user.get("password_iterations", 220000))
            actual = bytes.fromhex(UserAuthService._hash_password(password, salt, iterations)["hash"])
            return hmac.compare_digest(expected, actual)
        except Exception:
            return False

    @staticmethod
    def create_user(username, password, display_name="", email="", role="採購人員", company="", enabled=True):
        username = UserAuthService._normalize_username(username)
        password = str(password or "")
        display_name = str(display_name or "").strip()
        if len(username) < 3:
            raise ValueError("帳號至少需要 3 個字元。")
        if len(password) < 6:
            raise ValueError("密碼至少需要 6 個字元。")
        if role not in UserAuthService.ROLE_LABELS:
            raise ValueError("未知的使用者角色。")
        # 第一位管理員建立後，後續新增帳號只能由系統管理員執行。
        if UserAuthService.has_users():
            security.require_admin("新增使用者帳號")
        users = UserAuthService.load_users()
        if any(UserAuthService._normalize_username(u.get("username")) == username for u in users):
            raise ValueError("這個登入帳號已存在。")
        p = UserAuthService._hash_password(password)
        user = {
            "username": username,
            "display_name": display_name or username,
            "email": str(email or "").strip(),
            "role": role,
            "company": str(company or "").strip(),
            "enabled": bool(enabled),
            "password_salt": p["salt"],
            "password_hash": p["hash"],
            "password_iterations": p["iterations"],
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "last_login_at": "",
        }
        users.append(user)
        UserAuthService.save_users(users)
        try:
            from services.audit_log_service import AuditLogService
            AuditLogService.log_event('使用者帳號', '建立使用者', record_id=username, after=UserAuthService._public_user(user), result='成功')
        except Exception:
            pass
        return UserAuthService._public_user(user)

    @staticmethod
    def create_first_admin(username, password, display_name="", email="", company=""):
        if UserAuthService.has_users():
            raise ValueError("系統已經存在使用者，不能再次建立第一位管理員。")
        return UserAuthService.create_user(
            username, password, display_name, email, "系統管理員", company, True
        )

    @staticmethod
    def authenticate(username, password):
        username = UserAuthService._normalize_username(username)
        users = UserAuthService.load_users()
        for idx, user in enumerate(users):
            if UserAuthService._normalize_username(user.get("username")) != username:
                continue
            if not bool(user.get("enabled", True)):
                try:
                    from services.audit_log_service import AuditLogService
                    AuditLogService.log_event("登入", "登入失敗", record_id=username, result="失敗", severity="警告", note="帳號已停用")
                except Exception:
                    get_logger().warning("寫入登入失敗稽核紀錄失敗", exc_info=True)
                raise ValueError("此帳號已停用，請聯絡系統管理員。")
            if not UserAuthService._verify_password(password, user):
                try:
                    from services.audit_log_service import AuditLogService
                    AuditLogService.log_event("登入", "登入失敗", record_id=username, result="失敗", severity="警告", note="密碼錯誤")
                except Exception:
                    get_logger().warning("寫入登入失敗稽核紀錄失敗", exc_info=True)
                raise ValueError("帳號或密碼不正確。")
            user["last_login_at"] = datetime.now().isoformat(timespec="seconds")
            users[idx] = user
            UserAuthService.save_users(users)
            UserAuthService._current_user = UserAuthService._public_user(user)
            try:
                from services.audit_log_service import AuditLogService
                AuditLogService.log_event("登入", "登入成功", record_id=username, result="成功")
            except Exception:
                pass
            return deepcopy(UserAuthService._current_user)
        raise ValueError("帳號或密碼不正確。")

    @staticmethod
    def current_user():
        return deepcopy(UserAuthService._current_user)

    @staticmethod
    def logout():
        UserAuthService._current_user = None

    @staticmethod
    def update_user(username, display_name=None, email=None, role=None, company=None, enabled=None):
        username = UserAuthService._normalize_username(username)
        current = UserAuthService.current_user() or {}
        is_self = username and UserAuthService._normalize_username(current.get("username", "")) == username
        # 角色與啟用狀態屬於權限本身，禁止使用者自我提權；修改他人資料也限管理員。
        if role is not None or enabled is not None or not is_self:
            security.require_admin("修改使用者帳號")
        users = UserAuthService.load_users()
        original_public = None
        found = False
        for idx, user in enumerate(users):
            if UserAuthService._normalize_username(user.get("username")) != username:
                continue
            original_public = UserAuthService._public_user(user)
            if role is not None:
                if role not in UserAuthService.ROLE_LABELS:
                    raise ValueError("未知的使用者角色。")
                user["role"] = role
            if display_name is not None:
                user["display_name"] = str(display_name).strip()
            if email is not None:
                user["email"] = str(email).strip()
            if company is not None:
                user["company"] = str(company).strip()
            if enabled is not None:
                user["enabled"] = bool(enabled)
            users[idx] = user
            found = True
            break
        if not found:
            raise ValueError("找不到指定使用者。")
        UserAuthService.save_users(users)
        updated_public = UserAuthService._public_user(users[idx])
        if UserAuthService._current_user and UserAuthService._current_user.get("username") == username:
            UserAuthService._current_user = updated_public
        try:
            from services.audit_log_service import AuditLogService
            AuditLogService.log_event("使用者帳號", "修改使用者", record_id=username, before=original_public, after=updated_public, result="成功")
        except Exception:
            pass
        return updated_public

    @staticmethod
    def change_password(username, new_password):
        username = UserAuthService._normalize_username(username)
        security.require_self_or_admin(username, "修改使用者密碼")
        new_password = str(new_password or "")
        if len(new_password) < 6:
            raise ValueError("新密碼至少需要 6 個字元。")
        users = UserAuthService.load_users()
        for idx, user in enumerate(users):
            if UserAuthService._normalize_username(user.get("username")) == username:
                p = UserAuthService._hash_password(new_password)
                user["password_salt"] = p["salt"]
                user["password_hash"] = p["hash"]
                user["password_iterations"] = p["iterations"]
                users[idx] = user
                UserAuthService.save_users(users)
                try:
                    from services.audit_log_service import AuditLogService
                    AuditLogService.log_event("使用者帳號", "修改密碼", record_id=username, result="成功", note="密碼內容不寫入稽核紀錄")
                except Exception:
                    pass
                return True
        raise ValueError("找不到指定使用者。")

    @staticmethod
    def delete_user(username):
        security.require_admin("刪除使用者帳號")
        username = UserAuthService._normalize_username(username)
        users = UserAuthService.load_users()
        target = next((u for u in users if UserAuthService._normalize_username(u.get("username")) == username), None)
        if target is None:
            raise ValueError("找不到指定使用者。")
        if str(target.get("role")) == "系統管理員":
            admin_count = sum(1 for u in users if str(u.get("role")) == "系統管理員" and bool(u.get("enabled", True)))
            if admin_count <= 1:
                raise ValueError("至少必須保留一位啟用中的系統管理員。")
        users = [u for u in users if UserAuthService._normalize_username(u.get("username")) != username]
        UserAuthService.save_users(users)
        try:
            from services.audit_log_service import AuditLogService
            AuditLogService.log_event("使用者帳號", "刪除使用者", record_id=username, before=UserAuthService._public_user(target), result="成功", severity="警告")
        except Exception:
            pass
        return True
