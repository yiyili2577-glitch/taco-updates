import os

import pandas as pd

from services.excel_service import ExcelService
from services.app_paths import AppPaths
from services.safe_storage import SafeStorage


class ProductMasterService:

    BASE_DIR = str(AppPaths.install_dir())

    DATA_DIR = str(AppPaths.data_dir())

    DATA_FILE = os.path.join(
        DATA_DIR,
        "product_master.json"
    )

    # =====================================================
    # Folder
    # =====================================================

    @staticmethod
    def ensure_data_folder():

        os.makedirs(
            ProductMasterService.DATA_DIR,
            exist_ok=True
        )

    # =====================================================
    # Clean
    # =====================================================

    @staticmethod
    def clean_text(value):

        if value is None:
            return ""

        try:

            if pd.isna(value):
                return ""

        except Exception:
            pass

        return (
            str(value)
            .replace("\u3000", " ")
            .strip()
        )

    # =====================================================
    # Normalize columns
    # =====================================================

    @staticmethod
    def normalize_columns(df):

        if df is None:

            return pd.DataFrame()

        df = df.copy()

        clean_columns = []

        for column in df.columns:

            clean_columns.append(
                str(column)
                .replace("\n", "")
                .replace("\r", "")
                .replace("\u3000", "")
                .strip()
            )

        df.columns = (
            clean_columns
        )

        aliases = {
            "料號":
                "產品編號",

            "產品編碼":
                "產品編號",

            "品號":
                "產品編號",

            "品名":
                "產品名稱",

            "產品名":
                "產品名稱",

            "包裝":
                "包裝方式",

            "材料":
                "材質",
        }

        rename_map = {}

        for old_name, new_name in (
            aliases.items()
        ):

            if (
                old_name in df.columns
                and
                new_name not in df.columns
            ):

                rename_map[
                    old_name
                ] = new_name

        if rename_map:

            df = df.rename(
                columns=rename_map
            )

        return df

    # =====================================================
    # Load
    # =====================================================

    @staticmethod
    def load_products():

        ProductMasterService.ensure_data_folder()

        data = SafeStorage.safe_read_json(
            ProductMasterService.DATA_FILE,
            default=[]
        )

        if isinstance(
            data,
            list
        ):

            return data

        return []

    # =====================================================
    # Save
    # =====================================================

    @staticmethod
    def save_products(products):
        from services import security
        security.require_write_access("儲存產品主檔")

        ProductMasterService.ensure_data_folder()

        product_map = {}

        for product in products:

            product_no = (
                ProductMasterService
                .clean_text(
                    product.get(
                        "產品編號",
                        ""
                    )
                )
            )

            if not product_no:
                continue

            product_map[
                product_no
            ] = {
                "產品編號":
                    product_no,

                "產品名稱":
                    ProductMasterService
                    .clean_text(
                        product.get(
                            "產品名稱",
                            ""
                        )
                    ),

                "品項分類":
                    ProductMasterService
                    .clean_text(
                        product.get(
                            "品項分類",
                            ""
                        )
                    ),

                "規格":
                    ProductMasterService
                    .clean_text(
                        product.get(
                            "規格",
                            ""
                        )
                    ),

                "材質":
                    ProductMasterService
                    .clean_text(
                        product.get(
                            "材質",
                            ""
                        )
                    ),

                "包裝方式":
                    ProductMasterService
                    .clean_text(
                        product.get(
                            "包裝方式",
                            ""
                        )
                    ),
            }

        products = list(
            product_map.values()
        )

        products.sort(
            key=lambda x:
            x.get(
                "產品編號",
                ""
            )
        )

        SafeStorage.atomic_write_json(
            ProductMasterService.DATA_FILE,
            products,
            indent=4
        )

        try:
            from services.audit_log_service import AuditLogService
            AuditLogService.log_event("產品主檔", "儲存產品主檔", after={"產品數": len(products) if isinstance(products, list) else 0}, result="成功")
        except Exception:
            from services.safe_storage import get_logger
            get_logger().warning("產品主檔已儲存，但稽核紀錄寫入失敗。", exc_info=True)

    # =====================================================
    # 判斷是不是正常產品編號
    # =====================================================

    @staticmethod
    def is_valid_product_no(
        value
    ):

        value = (
            ProductMasterService
            .clean_text(
                value
            )
        )

        if not value:
            return False

        bad_values = [
            "產品編號",
            "料號",
            "合計",
            "共",
            "總計",
            "nan",
            "None",
        ]

        if value in bad_values:
            return False

        # 訂單的正常產品編號通常至少包含
        # 英文、數字或 -
        if len(value) < 2:
            return False

        return True

    # =====================================================
    # DataFrame → products
    # =====================================================

    @staticmethod
    def dataframe_to_products(
        df,
        default_category=""
    ):

        df = (
            ProductMasterService
            .normalize_columns(
                df
            )
        )

        if (
            "產品編號"
            not in df.columns
        ):

            raise Exception(
                "找不到「產品編號」欄位。\n"
                f"目前欄位：{list(df.columns)}"
            )

        if (
            "產品名稱"
            not in df.columns
        ):

            df[
                "產品名稱"
            ] = ""

        products = []

        for _, row in df.iterrows():

            product_no = (
                ProductMasterService
                .clean_text(
                    row.get(
                        "產品編號",
                        ""
                    )
                )
            )

            if not (
                ProductMasterService
                .is_valid_product_no(
                    product_no
                )
            ):

                continue

            product_name = (
                ProductMasterService
                .clean_text(
                    row.get(
                        "產品名稱",
                        ""
                    )
                )
            )

            specification = (
                ProductMasterService
                .clean_text(
                    row.get(
                        "規格",
                        ""
                    )
                )
            )

            material = (
                ProductMasterService
                .clean_text(
                    row.get(
                        "材質",
                        ""
                    )
                )
            )

            packing = (
                ProductMasterService
                .clean_text(
                    row.get(
                        "包裝方式",
                        ""
                    )
                )
            )

            products.append(
                {
                    "產品編號":
                        product_no,

                    "產品名稱":
                        product_name,

                    "品項分類":
                        default_category,

                    "規格":
                        specification,

                    "材質":
                        material,

                    "包裝方式":
                        packing,
                }
            )

        return products

    # =====================================================
    # Merge products
    # =====================================================

    @staticmethod
    def merge_products(
        new_products
    ):

        old_products = (
            ProductMasterService
            .load_products()
        )

        product_map = {
            product.get(
                "產品編號",
                ""
            ):
            product.copy()

            for product
            in old_products

            if product.get(
                "產品編號"
            )
        }

        for new_product in new_products:

            product_no = (
                new_product.get(
                    "產品編號",
                    ""
                )
            )

            if not product_no:
                continue

            old = product_map.get(
                product_no,
                {}
            )

            # 保留原本人工分類
            category = (
                old.get(
                    "品項分類",
                    ""
                )
                or
                new_product.get(
                    "品項分類",
                    ""
                )
            )

            product_map[
                product_no
            ] = {
                "產品編號":
                    product_no,

                "產品名稱":
                    (
                        new_product.get(
                            "產品名稱",
                            ""
                        )
                        or
                        old.get(
                            "產品名稱",
                            ""
                        )
                    ),

                "品項分類":
                    category,

                "規格":
                    (
                        new_product.get(
                            "規格",
                            ""
                        )
                        or
                        old.get(
                            "規格",
                            ""
                        )
                    ),

                "材質":
                    (
                        new_product.get(
                            "材質",
                            ""
                        )
                        or
                        old.get(
                            "材質",
                            ""
                        )
                    ),

                "包裝方式":
                    (
                        new_product.get(
                            "包裝方式",
                            ""
                        )
                        or
                        old.get(
                            "包裝方式",
                            ""
                        )
                    ),
            }

        final_products = list(
            product_map.values()
        )

        ProductMasterService.save_products(
            final_products
        )

        return (
            ProductMasterService
            .load_products()
        )

    # =====================================================
    # 單份 Excel
    # =====================================================

    @staticmethod
    def import_from_excel(
        file_path,
        default_category=""
    ):

        df = (
            ExcelService
            .read_product_excel(
                file_path
            )
        )

        products = (
            ProductMasterService
            .dataframe_to_products(
                df,
                default_category
            )
        )

        return (
            ProductMasterService
            .merge_products(
                products
            )
        )

    # =====================================================
    # 多份 Excel
    # =====================================================

    @staticmethod
    def import_from_excels(
        file_paths,
        default_category=""
    ):

        all_products = []

        successful_files = []

        errors = []

        for file_path in file_paths:

            try:

                df = (
                    ExcelService
                    .read_product_excel(
                        file_path
                    )
                )

                products = (
                    ProductMasterService
                    .dataframe_to_products(
                        df,
                        default_category
                    )
                )

                all_products.extend(
                    products
                )

                successful_files.append(
                    file_path
                )

            except Exception as e:

                errors.append(
                    (
                        file_path,
                        str(e)
                    )
                )

        if not all_products:

            raise Exception(
                "沒有任何 Excel 成功讀取產品。"
            )

        final_products = (
            ProductMasterService
            .merge_products(
                all_products
            )
        )

        return {
            "products":
                final_products,

            "imported_count":
                len(
                    {
                        product[
                            "產品編號"
                        ]
                        for product
                        in all_products
                    }
                ),

            "successful_files":
                successful_files,

            "errors":
                errors,
        }

    # =====================================================
    # DataFrame import
    # =====================================================

    @staticmethod
    def import_from_dataframe(
        df,
        default_category=""
    ):

        products = (
            ProductMasterService
            .dataframe_to_products(
                df,
                default_category
            )
        )

        return (
            ProductMasterService
            .merge_products(
                products
            )
        )

    # =====================================================
    # Upsert
    # =====================================================

    @staticmethod
    def upsert_product(
        product_no,
        product_name,
        category="",
        specification="",
        packing="",
        material=""
    ):

        product_no = (
            ProductMasterService
            .clean_text(
                product_no
            )
        )

        if not product_no:

            raise Exception(
                "產品編號不可空白。"
            )

        products = (
            ProductMasterService
            .load_products()
        )

        found = False

        for product in products:

            if (
                product.get(
                    "產品編號"
                )
                == product_no
            ):

                product[
                    "產品名稱"
                ] = (
                    product_name
                )

                product[
                    "品項分類"
                ] = (
                    category
                )

                product[
                    "規格"
                ] = (
                    specification
                )

                product[
                    "材質"
                ] = (
                    material
                )

                product[
                    "包裝方式"
                ] = (
                    packing
                )

                found = True

                break

        if not found:

            products.append(
                {
                    "產品編號":
                        product_no,

                    "產品名稱":
                        product_name,

                    "品項分類":
                        category,

                    "規格":
                        specification,

                    "材質":
                        material,

                    "包裝方式":
                        packing,
                }
            )

        ProductMasterService.save_products(
            products
        )

        return (
            ProductMasterService
            .load_products()
        )

    # =====================================================
    # Delete
    # =====================================================

    @staticmethod
    def delete_product(
        product_no
    ):

        products = [
            product
            for product
            in ProductMasterService
            .load_products()

            if product.get(
                "產品編號"
            )
            != product_no
        ]

        ProductMasterService.save_products(
            products
        )

    # =====================================================
    # Category products
    # =====================================================

    @staticmethod
    def get_products_by_category(
        category
    ):

        return [
            product
            for product
            in ProductMasterService
            .load_products()

            if str(
                product.get(
                    "品項分類",
                    ""
                )
            ).strip()
            == str(
                category
            ).strip()
        ]