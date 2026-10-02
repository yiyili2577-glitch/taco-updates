import json
import logging
import os
import shutil
import tempfile
import uuid
from datetime import datetime
from logging.handlers import RotatingFileHandler

from services.app_paths import AppPaths

_LOGGER_NAME = "taco_erp"
_logger = None


def get_logger():
    """回傳全域共用的 logger。

    第一次呼叫時會在專案根目錄建立 logs/app.log（自動輪替，最多保留 5 份、
    每份 2MB），之後所有模組都可以用同一個 logger 記錄警告或錯誤，
    取代原本大量「except Exception: pass」完全不留痕跡的寫法。
    """
    global _logger
    if _logger is not None:
        return _logger

    base_dir = str(AppPaths.root_dir())
    log_dir = str(AppPaths.logs_dir())
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        log_dir = base_dir  # 萬一連 logs 目錄都建立不了，退回程式根目錄，至少不會整個炸掉。

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        log_file = os.path.join(log_dir, "app.log")
        handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
    _logger = logger
    return _logger


class SafeStorage:
    """所有 JSON 資料檔的統一讀寫工具。

    取代原本各個 service 各自寫的「open(path,'w') + json.dump」。原本的寫法有
    兩個風險：
      1. 直接覆寫正式檔案，如果存檔中途當機、斷電或磁碟空間不足，檔案有可能
         寫到一半就壞掉，而且沒有任何備份可以救回來。
      2. 讀取時如果檔案損毀，大多數 service 是直接 except Exception: pass，
         悄悄回傳空資料，使用者完全不會知道資料其實不見了。

    這裡的做法：
      1. atomic_write_json：新資料先寫到同一個資料夾底下的暫存檔，flush +
         fsync 確保真的落盤後，才用 os.replace 換掉正式檔案（os.replace 在
         同一個檔案系統內是原子操作，不會有寫到一半的中間狀態）。覆寫前會先
         把「舊版本」複製一份到 _file_backups/ 子資料夾，預設保留最近 5 份。
      2. safe_read_json：主檔案讀取失敗時，會自動改用最新一份備份，並記一筆
         警告到 log，而不是悄悄回傳空資料或讓程式crash。
    """

    DEFAULT_KEEP_BACKUPS = 5

    @staticmethod
    def _backup_dir_for(path):
        return os.path.join(os.path.dirname(os.path.abspath(path)), "_file_backups")

    @staticmethod
    def _list_backups(path):
        backup_dir = SafeStorage._backup_dir_for(path)
        name = os.path.basename(path)
        try:
            entries = [f for f in os.listdir(backup_dir) if f.startswith(name + ".") and f.endswith(".bak")]
        except FileNotFoundError:
            return []
        entries.sort()  # 檔名帶時間戳（年月日時分秒微秒），字串排序即時間排序
        return entries

    @staticmethod
    def _rotate_backups(path, keep):
        backup_dir = SafeStorage._backup_dir_for(path)
        entries = SafeStorage._list_backups(path)
        excess = len(entries) - keep
        for old in entries[:max(0, excess)]:
            try:
                os.remove(os.path.join(backup_dir, old))
            except Exception:
                get_logger().warning("清除舊備份失敗：%s", old, exc_info=True)

    @staticmethod
    def atomic_write_json(path, data, keep_backups=DEFAULT_KEEP_BACKUPS, indent=2):
        """原子寫入 JSON，並在覆寫前保留一份備份。失敗時會拋出例外（不吞掉），
        讓呼叫端知道存檔真的失敗了，而不是誤以為存成功。"""
        path = os.path.abspath(path)
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)

        if os.path.exists(path):
            backup_dir = SafeStorage._backup_dir_for(path)
            try:
                os.makedirs(backup_dir, exist_ok=True)
                # 極高速連續寫入時 datetime 在部分 Windows 時鐘上可能回傳同一微秒；
                # UUID 後綴避免備份被同名覆蓋，前方時間戳仍維持可排序性。
                stamp = datetime.now().strftime("%Y%m%d%H%M%S%f") + "_" + uuid.uuid4().hex
                backup_path = os.path.join(backup_dir, f"{os.path.basename(path)}.{stamp}.bak")
                shutil.copy2(path, backup_path)
                SafeStorage._rotate_backups(path, keep_backups)
            except Exception:
                # 備份失敗不擋主要流程，但要留紀錄——不然使用者不會知道其實沒有備份可用。
                get_logger().warning("備份 %s 失敗，仍會繼續寫入新資料。", path, exc_info=True)

        fd, tmp_path = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=indent)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        except Exception:
            get_logger().error("寫入 %s 失敗。", path, exc_info=True)
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            raise

    @staticmethod
    def safe_read_json(path, default=None):
        """讀取 JSON；主檔案損毀時自動改讀最新備份，最後才回退到 default。"""
        path = os.path.abspath(path)
        if not os.path.exists(path):
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            get_logger().warning("讀取 %s 失敗，嘗試改用備份。", path, exc_info=True)

        for candidate in reversed(SafeStorage._list_backups(path)):
            candidate_path = os.path.join(SafeStorage._backup_dir_for(path), candidate)
            try:
                with open(candidate_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                get_logger().warning("已改用備份還原 %s（來源：%s）。", path, candidate)
                return data
            except Exception:
                continue

        get_logger().error("%s 及所有備份都無法讀取，改用預設值。", path)
        return default
