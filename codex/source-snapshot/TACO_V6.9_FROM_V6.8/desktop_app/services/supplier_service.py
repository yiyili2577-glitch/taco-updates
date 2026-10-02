import os

from services.app_paths import AppPaths
from services.safe_storage import SafeStorage


class SupplierService:

    # =====================================================
    # JSON 資料儲存位置
    # =====================================================

    BASE_DIR = str(AppPaths.install_dir())

    DATA_DIR = str(AppPaths.data_dir())

    DATA_FILE = os.path.join(
        DATA_DIR,
        "suppliers.json"
    )

    # =====================================================
    # 確保 data 資料夾存在
    # =====================================================

    @staticmethod
    def ensure_data_folder():

        if not os.path.exists(
            SupplierService.DATA_DIR
        ):

            os.makedirs(
                SupplierService.DATA_DIR
            )

    # =====================================================
    # 讀取供應商設定
    # =====================================================

    @staticmethod
    def load_suppliers():

        SupplierService.ensure_data_folder()

        data = SafeStorage.safe_read_json(
            SupplierService.DATA_FILE,
            default=[]
        )

        if isinstance(data, list):
            return data

        return []

    # =====================================================
    # 儲存供應商設定
    # =====================================================

    @staticmethod
    def save_suppliers(suppliers):
        from services import security
        security.require_write_access("儲存供應商資料")

        SupplierService.ensure_data_folder()

        SafeStorage.atomic_write_json(
            SupplierService.DATA_FILE,
            suppliers,
            indent=4
        )