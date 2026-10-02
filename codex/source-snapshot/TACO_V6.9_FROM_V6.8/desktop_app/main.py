import sys

from services.bootstrap_service import BootstrapService
from services.data_migration_service import DataMigrationService


# 必須在載入各 service / UI 前先決定正式資料路徑與完成舊 data 搬遷。
_bootstrap_result = BootstrapService.prepare_runtime()
DataMigrationService.migrate_to_latest()

from PyQt6.QtWidgets import QApplication, QMessageBox
from ui.main_window import MainWindow
from services.build_config import BuildConfig
from services.app_paths import AppPaths


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(BuildConfig.PRODUCT_NAME)
    app.setApplicationVersion(BuildConfig.VERSION)
    window = MainWindow()
    window.show()
    if _bootstrap_result.get("migrated"):
        QMessageBox.information(
            window,
            "舊版資料已安全移轉",
            "TACO 已將舊 Erp_app\\data 搬到正式資料區。\n\n"
            f"新資料位置：\n{AppPaths.data_dir()}\n\n"
            f"移轉前備份：\n{_bootstrap_result.get('backup','')}",
        )
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
