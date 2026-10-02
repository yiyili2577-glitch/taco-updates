import pandas as pd

from services.product_master_service import ProductMasterService


class InventoryService:

    @staticmethod
    def to_number(value):

        try:

            if value is None:
                return 0.0

            if pd.isna(value):
                return 0.0

            if isinstance(
                value,
                str
            ):

                value = (
                    value
                    .replace(",", "")
                    .strip()
                )

                if not value:
                    return 0.0

            return float(
                value
            )

        except Exception:

            return 0.0

    # =====================================================
    # 找欄位
    # =====================================================

    @staticmethod
    def find_column(
        df,
        keywords
    ):

        for column in df.columns:

            column_text = str(
                column
            ).strip()

            for keyword in keywords:

                if (
                    keyword
                    == column_text
                    or
                    keyword in column_text
                ):

                    return column

        return None

    # =====================================================
    # clean inventory
    # =====================================================

    @staticmethod
    def clean_inventory_data(df):

        if df is None:

            return pd.DataFrame()

        if df.empty:

            return pd.DataFrame()

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
                "庫存 Excel 找不到「產品編號」欄位。\n"
                f"目前讀到：{list(df.columns)}"
            )

        if (
            "產品名稱"
            not in df.columns
        ):

            df[
                "產品名稱"
            ] = ""

        # 移除無產品編號
        df = df[
            df[
                "產品編號"
            ].notna()
        ].copy()

        df[
            "產品編號"
        ] = (
            df[
                "產品編號"
            ]
            .astype(str)
            .str.strip()
        )

        df = df[
            (
                df[
                    "產品編號"
                ] != ""
            )
            &
            (
                df[
                    "產品編號"
                ].str.lower()
                != "nan"
            )
        ].copy()

        # =================================================
        # 月用量
        # =================================================

        usage_column = (
            InventoryService
            .find_column(
                df,
                [
                    "平均月耗用量",
                    "月用量",
                    "月耗用量",
                    "月耗用",
                ]
            )
        )

        if usage_column:

            df[
                "平均月耗用量"
            ] = pd.to_numeric(
                df[
                    usage_column
                ],
                errors="coerce"
            ).fillna(0)

        else:

            df[
                "平均月耗用量"
            ] = 0.0

        # =================================================
        # 庫存
        # =================================================

        stock_column = (
            InventoryService
            .find_column(
                df,
                [
                    "目前庫存",
                    "庫存(箱)",
                    "庫存量",
                    "庫存",
                ]
            )
        )

        if stock_column:

            df[
                "目前庫存"
            ] = pd.to_numeric(
                df[
                    stock_column
                ],
                errors="coerce"
            ).fillna(0)

        else:

            df[
                "目前庫存"
            ] = 0.0

        # =================================================
        # 預計到貨
        # =================================================

        incoming_column = (
            InventoryService
            .find_column(
                df,
                [
                    "預計到貨",
                    "預計到貨量",
                    "在途量",
                    "在途",
                ]
            )
        )

        if incoming_column:

            df[
                "預計到貨"
            ] = pd.to_numeric(
                df[
                    incoming_column
                ],
                errors="coerce"
            ).fillna(0)

        else:

            df[
                "預計到貨"
            ] = 0.0

        # =================================================
        # 可撐月數
        # =================================================

        def calculate_months(row):

            usage = (
                InventoryService
                .to_number(
                    row.get(
                        "平均月耗用量",
                        0
                    )
                )
            )

            stock = (
                InventoryService
                .to_number(
                    row.get(
                        "目前庫存",
                        0
                    )
                )
            )

            incoming = (
                InventoryService
                .to_number(
                    row.get(
                        "預計到貨",
                        0
                    )
                )
            )

            if usage <= 0:
                return 0

            return round(
                (
                    stock
                    +
                    incoming
                )
                /
                usage,
                2
            )

        df[
            "現有可撐月數"
        ] = df.apply(
            calculate_months,
            axis=1
        )

        # =================================================
        # 狀態
        # =================================================

        def calculate_status(row):

            usage = (
                InventoryService
                .to_number(
                    row.get(
                        "平均月耗用量",
                        0
                    )
                )
            )

            months = (
                InventoryService
                .to_number(
                    row.get(
                        "現有可撐月數",
                        0
                    )
                )
            )

            if usage <= 0:

                return (
                    "⚪ 無耗用資料"
                )

            if months <= 1:

                return (
                    "🔴 急需採購"
                )

            if months <= 3:

                return (
                    "🟡 注意"
                )

            return (
                "🟢 正常"
            )

        df[
            "狀態"
        ] = df.apply(
            calculate_status,
            axis=1
        )

        # 同步產品主檔
        ProductMasterService.import_from_dataframe(
            df
        )

        return df.reset_index(
            drop=True
        )