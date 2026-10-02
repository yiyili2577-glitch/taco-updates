import hashlib
import json
import os
import threading
from datetime import datetime

from services.app_paths import AppPaths
from services.safe_storage import get_logger


class AuditLogService:
    """TACO append-only 操作稽核紀錄。

    每筆紀錄帶有 previous_hash / hash，形成簡單雜湊鏈。
    目的不是取代專業不可竄改日誌平台，而是讓本機版 TACO 可檢查
    紀錄是否被人工改寫或中途刪除。
    """

    BASE_DIR = str(AppPaths.install_dir())
    DATA_DIR = str(AppPaths.data_dir())
    AUDIT_DIR = str(AppPaths.audit_dir())
    LOG_FILE = os.path.join(AUDIT_DIR, "audit_log.jsonl")
    _lock = threading.RLock()

    @staticmethod
    def _ensure():
        os.makedirs(AuditLogService.AUDIT_DIR, exist_ok=True)

    @staticmethod
    def _now():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _actor():
        try:
            from services.user_auth_service import UserAuthService
            user = UserAuthService.current_user() or {}
        except Exception:
            user = {}
        return {
            "username": str(user.get("username", "")),
            "display_name": str(user.get("display_name", "")),
            "role": str(user.get("role", "")),
        }

    @staticmethod
    def _last_hash():
        AuditLogService._ensure()
        if not os.path.isfile(AuditLogService.LOG_FILE):
            return ""
        try:
            with open(AuditLogService.LOG_FILE, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                if size == 0:
                    return ""
                pos = size - 1
                while pos > 0:
                    f.seek(pos)
                    if f.read(1) == b"\n" and pos < size - 1:
                        break
                    pos -= 1
                if pos == 0:
                    f.seek(0)
                line = f.readline().decode("utf-8", errors="replace").strip()
            return str(json.loads(line).get("hash", "")) if line else ""
        except Exception:
            # 若尾端異常，改由完整讀取最後一筆有效紀錄。
            items = AuditLogService._load_all_logs(limit=1, newest_first=True)
            return str(items[0].get("hash", "")) if items else ""

    @staticmethod
    def _canonical_payload(record):
        clean = dict(record)
        clean.pop("hash", None)
        return json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def log_event(module, action, record_id="", before=None, after=None,
                  result="成功", note="", actor=None, severity="資訊"):
        AuditLogService._ensure()
        with AuditLogService._lock:
            previous_hash = AuditLogService._last_hash()
            record = {
                "timestamp": AuditLogService._now(),
                "actor": actor or AuditLogService._actor(),
                "module": str(module or "系統"),
                "action": str(action or "操作"),
                "record_id": str(record_id or ""),
                "before": before,
                "after": after,
                "result": str(result or ""),
                "severity": str(severity or "資訊"),
                "note": str(note or ""),
                "previous_hash": previous_hash,
            }
            digest_source = previous_hash + AuditLogService._canonical_payload(record)
            record["hash"] = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()
            try:
                with open(AuditLogService.LOG_FILE, "a", encoding="utf-8", newline="\n") as f:
                    f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            except Exception:
                get_logger().error("寫入稽核紀錄失敗：%s / %s", module, action, exc_info=True)
                raise
            return record

    @staticmethod
    def _load_all_logs(limit=None, newest_first=True):
        AuditLogService._ensure()
        if not os.path.isfile(AuditLogService.LOG_FILE):
            return []
        rows = []
        try:
            with open(AuditLogService.LOG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        rows.append({
                            "timestamp": "", "module": "稽核", "action": "無法解析的紀錄",
                            "result": "異常", "note": line[:300], "hash": "",
                            "previous_hash": "", "actor": {},
                        })
        except Exception:
            get_logger().error("讀取稽核紀錄失敗。", exc_info=True)
            return []
        if newest_first:
            rows.reverse()
        if limit is not None:
            rows = rows[:max(0, int(limit))]
        return rows

    @staticmethod
    def _scope_rows(rows):
        """service 層依角色限制可讀稽核紀錄，避免繞過 UI 直接讀到不該看的紀錄。"""
        try:
            from services import role_rules
            from services.user_auth_service import UserAuthService
            role = role_rules.current_role()
            user = UserAuthService.current_user() or {}
            username = str(user.get("username", ""))
        except Exception:
            return []
        if role in {"系統管理員", "主管"}:
            return rows
        if role == "採購管理者":
            allowed = {"採購建議", "供應商", "客戶需求", "庫存", "跨倉調撥", "財務", "登入", "匯出", "智慧掃碼", "Mapping Center"}
            return [x for x in rows if str(x.get("module", "")) in allowed]
        if role == "倉管":
            allowed = {"庫存", "跨倉調撥", "客戶需求", "登入", "智慧掃碼"}
            return [x for x in rows if str(x.get("module", "")) in allowed]
        if role == "財務人員":
            allowed = {"財務", "供應商", "登入", "匯出", "智慧掃碼", "Mapping Center"}
            return [x for x in rows if str(x.get("module", "")) in allowed]
        return [x for x in rows if str((x.get("actor") or {}).get("username", "")) == username]

    @staticmethod
    def load_logs(limit=None, newest_first=True):
        rows = AuditLogService._scope_rows(AuditLogService._load_all_logs(newest_first=newest_first))
        if limit is not None:
            rows = rows[:max(0, int(limit))]
        return rows

    @staticmethod
    def query_logs(keyword="", module="全部", action="全部", username="全部",
                   severity="全部", date_from="", date_to=""):
        keyword = str(keyword or "").strip().lower()
        result = []
        for row in AuditLogService.load_logs(newest_first=True):
            actor = row.get("actor") or {}
            if module != "全部" and str(row.get("module", "")) != module:
                continue
            if action != "全部" and str(row.get("action", "")) != action:
                continue
            if username != "全部" and str(actor.get("username", "")) != username:
                continue
            if severity != "全部" and str(row.get("severity", "資訊")) != severity:
                continue
            ts = str(row.get("timestamp", ""))
            if date_from and ts[:10] < date_from:
                continue
            if date_to and ts[:10] > date_to:
                continue
            if keyword:
                blob = json.dumps(row, ensure_ascii=False).lower()
                if keyword not in blob:
                    continue
            result.append(row)
        return result

    @staticmethod
    def verify_integrity():
        """以檔案原始順序驗證 hash chain。"""
        rows = AuditLogService._load_all_logs(newest_first=False)
        previous = ""
        checked = 0
        for index, row in enumerate(rows, start=1):
            if row.get("action") == "無法解析的紀錄":
                return {"ok": False, "checked": checked, "broken_at": index, "reason": "紀錄 JSON 無法解析"}
            expected_prev = str(row.get("previous_hash", ""))
            if expected_prev != previous:
                return {"ok": False, "checked": checked, "broken_at": index, "reason": "previous_hash 不連續"}
            actual_hash = str(row.get("hash", ""))
            payload = dict(row)
            payload.pop("hash", None)
            expected_hash = hashlib.sha256((previous + AuditLogService._canonical_payload(payload)).encode("utf-8")).hexdigest()
            if actual_hash != expected_hash:
                return {"ok": False, "checked": checked, "broken_at": index, "reason": "hash 驗證失敗"}
            previous = actual_hash
            checked += 1
        return {"ok": True, "checked": checked, "broken_at": None, "reason": "完整"}

    @staticmethod
    def distinct_values():
        logs = AuditLogService.load_logs(newest_first=False)
        return {
            "modules": sorted({str(x.get("module", "")) for x in logs if str(x.get("module", ""))}),
            "actions": sorted({str(x.get("action", "")) for x in logs if str(x.get("action", ""))}),
            "users": sorted({str((x.get("actor") or {}).get("username", "")) for x in logs if str((x.get("actor") or {}).get("username", ""))}),
            "severities": sorted({str(x.get("severity", "資訊")) for x in logs}),
        }

    @staticmethod
    def stats():
        logs = AuditLogService.load_logs(newest_first=True)
        today = datetime.now().strftime("%Y-%m-%d")
        return {
            "total": len(logs),
            "today": sum(1 for x in logs if str(x.get("timestamp", "")).startswith(today)),
            "errors": sum(1 for x in logs if str(x.get("result", "")) not in ("成功", "完成", "")),
            "last_at": str(logs[0].get("timestamp", "")) if logs else "",
        }
