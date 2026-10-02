import os
import sys
from pathlib import Path

from services.build_config import BuildConfig


class AppPaths:
    """TACO 執行路徑唯一來源。

    開發版：沿用專案資料夾 data/、logs/、exports/。
    正式 EXE：所有可變資料移至 %PROGRAMDATA%\\TACO，程式本體留在 Program Files。
    """

    @staticmethod
    def install_dir():
        if bool(getattr(sys, "frozen", False)):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parents[1]

    @staticmethod
    def resource_dir():
        base = getattr(sys, "_MEIPASS", None)
        return Path(base).resolve() if base else AppPaths.install_dir()

    @staticmethod
    def root_dir():
        override = str(os.environ.get("TACO_RUNTIME_ROOT", "")).strip()
        if override:
            return Path(override).expanduser().resolve()
        if BuildConfig.is_production():
            program_data = os.environ.get("PROGRAMDATA") or r"C:\ProgramData"
            return (Path(program_data) / "TACO").resolve()
        return AppPaths.install_dir()

    @staticmethod
    def data_dir():
        override = str(os.environ.get("TACO_DATA_DIR", "")).strip()
        if override:
            return Path(override).expanduser().resolve()
        return AppPaths.root_dir() / ("Data" if BuildConfig.is_production() else "data")

    @staticmethod
    def backups_dir():
        return AppPaths.root_dir() / ("Backups" if BuildConfig.is_production() else "backups")

    @staticmethod
    def logs_dir():
        return AppPaths.root_dir() / ("Logs" if BuildConfig.is_production() else "logs")

    @staticmethod
    def audit_dir():
        if BuildConfig.is_production():
            return AppPaths.root_dir() / "AuditLogs"
        return AppPaths.data_dir() / "audit_logs"

    @staticmethod
    def config_dir():
        return AppPaths.root_dir() / ("Config" if BuildConfig.is_production() else "config")

    @staticmethod
    def exports_dir():
        return AppPaths.root_dir() / ("Exports" if BuildConfig.is_production() else "exports")

    @staticmethod
    def update_dir():
        return AppPaths.root_dir() / ("Updates" if BuildConfig.is_production() else "updates")

    @staticmethod
    def ensure_runtime_dirs():
        for path in [
            AppPaths.root_dir(), AppPaths.data_dir(), AppPaths.backups_dir(),
            AppPaths.logs_dir(), AppPaths.audit_dir(), AppPaths.config_dir(),
            AppPaths.exports_dir(), AppPaths.update_dir(),
        ]:
            Path(path).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def legacy_data_candidates():
        result = []
        env_path = str(os.environ.get("TACO_LEGACY_DATA_DIR", "")).strip()
        if env_path:
            result.append(Path(env_path).expanduser())
        # 舊版最常見位置
        home = Path.home()
        result.append(home / "Desktop" / "Erp_app" / "data")
        # 若 EXE 同層或上一層曾留 data，也一起偵測
        result.append(AppPaths.install_dir() / "data")
        result.append(AppPaths.install_dir().parent / "data")
        # 去重
        seen = set(); unique = []
        for p in result:
            try:
                key = str(p.resolve())
            except Exception:
                key = str(p)
            if key not in seen:
                seen.add(key); unique.append(p)
        return unique
