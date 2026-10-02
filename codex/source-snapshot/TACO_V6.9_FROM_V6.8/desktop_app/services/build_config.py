import os
import sys


class BuildConfig:
    """集中管理開發版/正式版差異。

    - 原始碼執行預設 DEV，方便既有開發流程。
    - PyInstaller frozen 執行預設 PROD。
    - 可用 TACO_BUILD_MODE=dev|prod 明確覆寫（測試/封裝時使用）。
    """

    APP_ID = "taco_smart_procurement"
    PRODUCT_NAME = "TACO 智慧採購助理"
    VERSION = "6.9.0"
    SCHEMA_VERSION = 2

    @staticmethod
    def mode():
        forced = str(os.environ.get("TACO_BUILD_MODE", "")).strip().lower()
        if forced in {"dev", "prod"}:
            return forced
        return "prod" if bool(getattr(sys, "frozen", False)) else "dev"

    @staticmethod
    def is_production():
        return BuildConfig.mode() == "prod"

    @staticmethod
    def is_development():
        return not BuildConfig.is_production()
