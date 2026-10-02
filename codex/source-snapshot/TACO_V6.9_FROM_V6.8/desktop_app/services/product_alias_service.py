import os
import re
from difflib import SequenceMatcher

from services.app_paths import AppPaths
from services.safe_storage import SafeStorage


class ProductAliasService:

    BASE_DIR = str(AppPaths.install_dir())

    DATA_DIR = str(AppPaths.data_dir())

    DATA_FILE = os.path.join(
        DATA_DIR,
        "product_aliases.json"
    )

    # =========================================================
    # 建立 data 資料夾
    # =========================================================

    @staticmethod
    def ensure_data_folder():

        os.makedirs(
            ProductAliasService.DATA_DIR,
            exist_ok=True
        )

    # =========================================================
    # 正規化文字
    # =========================================================

    @staticmethod
    def normalize_name(value):

        if value is None:
            return ""

        text = str(value)

        text = (
            text
            .replace("\r", " ")
            .replace("\n", " ")
            .replace("\u3000", " ")
            .replace("（", "(")
            .replace("）", ")")
            .replace("＊", "*")
            .replace("Ｘ", "X")
            .replace("ｘ", "x")
            .replace("／", "/")
            .strip()
        )

        text = re.sub(
            r"\s+",
            " ",
            text
        )

        return text.strip()

    # =========================================================
    # 搜尋比較時使用的文字
    # =========================================================

    @staticmethod
    def normalize_for_match(value):

        text = (
            ProductAliasService
            .normalize_name(
                value
            )
            .upper()
        )

        # 常見同義寫法統一
        replacements = {
            "吋": '"',
            "＂": '"',
            "×": "X",
            "*": "X",
            "CM": "CM",
            "公分": "CM",
            "無粉": "無粉",
            "有粉": "有粉",
        }

        for old, new in replacements.items():

            text = text.replace(
                old,
                new
            )

        # 移除不影響比對的符號
        text = re.sub(
            r"[\s\-_/,，。:：;；]+",
            "",
            text
        )

        return text

    # =========================================================
    # 讀取 Alias
    # =========================================================

    @staticmethod
    def load_aliases():

        ProductAliasService.ensure_data_folder()

        data = SafeStorage.safe_read_json(
            ProductAliasService.DATA_FILE,
            default={}
        )

        if isinstance(
            data,
            dict
        ):

            return data

        return {}

    # =========================================================
    # 儲存 Alias
    # =========================================================

    @staticmethod
    def save_aliases(
        aliases
    ):

        from services import security
        security.require_write_access("儲存產品對應")
        ProductAliasService.ensure_data_folder()

        SafeStorage.atomic_write_json(
            ProductAliasService.DATA_FILE,
            aliases,
            indent=4
        )

    # =========================================================
    # 單筆儲存
    # =========================================================

    @staticmethod
    def set_alias(
        pdf_product_name,
        product_no
    ):

        pdf_product_name = (
            ProductAliasService
            .normalize_name(
                pdf_product_name
            )
        )

        product_no = str(
            product_no
        ).strip()

        if not pdf_product_name:

            raise Exception(
                "PDF 品名不可空白。"
            )

        if not product_no:

            raise Exception(
                "產品編號不可空白。"
            )

        aliases = (
            ProductAliasService
            .load_aliases()
        )

        aliases[
            pdf_product_name
        ] = product_no

        ProductAliasService.save_aliases(
            aliases
        )

    # =========================================================
    # 批次儲存
    #
    # mappings:
    #
    # {
    #     "PDF品名A": "A01-01",
    #     "PDF品名B": "B02-03"
    # }
    # =========================================================

    @staticmethod
    def set_aliases_bulk(
        mappings
    ):

        if not isinstance(
            mappings,
            dict
        ):

            raise Exception(
                "批次產品對應資料格式錯誤。"
            )

        aliases = (
            ProductAliasService
            .load_aliases()
        )

        saved_count = 0

        for pdf_name, product_no in (
            mappings.items()
        ):

            pdf_name = (
                ProductAliasService
                .normalize_name(
                    pdf_name
                )
            )

            product_no = str(
                product_no
            ).strip()

            if (
                not pdf_name
                or
                not product_no
            ):

                continue

            aliases[
                pdf_name
            ] = product_no

            saved_count += 1

        ProductAliasService.save_aliases(
            aliases
        )

        return saved_count

    # =========================================================
    # 刪除 Alias
    # =========================================================

    @staticmethod
    def delete_alias(
        pdf_product_name
    ):

        pdf_product_name = (
            ProductAliasService
            .normalize_name(
                pdf_product_name
            )
        )

        aliases = (
            ProductAliasService
            .load_aliases()
        )

        if pdf_product_name in aliases:

            del aliases[
                pdf_product_name
            ]

            ProductAliasService.save_aliases(
                aliases
            )

    # =========================================================
    # 查詢產品編號
    # =========================================================

    @staticmethod
    def get_product_no(
        pdf_product_name
    ):

        pdf_product_name = (
            ProductAliasService
            .normalize_name(
                pdf_product_name
            )
        )

        aliases = (
            ProductAliasService
            .load_aliases()
        )

        return str(
            aliases.get(
                pdf_product_name,
                ""
            )
        ).strip()

    # =========================================================
    # 套用 Alias 到 dataframe
    # =========================================================

    @staticmethod
    def apply_aliases(
        df
    ):

        if df is None:
            return df

        if df.empty:
            return df

        if (
            "PDF品名規格"
            not in df.columns
        ):

            return df

        df = df.copy()

        aliases = (
            ProductAliasService
            .load_aliases()
        )

        def lookup(
            value
        ):

            key = (
                ProductAliasService
                .normalize_name(
                    value
                )
            )

            return str(
                aliases.get(
                    key,
                    ""
                )
            ).strip()

        df[
            "產品編號"
        ] = df[
            "PDF品名規格"
        ].apply(
            lookup
        )

        return df

    # =========================================================
    # 取得產品文字
    # =========================================================

    @staticmethod
    def build_product_search_text(
        product
    ):

        fields = [
            "產品編號",
            "產品名稱",
            "品名",
            "品項分類",
            "規格",
            "包裝方式",
        ]

        parts = []

        for field in fields:

            value = str(
                product.get(
                    field,
                    ""
                )
            ).strip()

            if value:

                parts.append(
                    value
                )

        return " ".join(
            parts
        )

    # =========================================================
    # 規格 token
    #
    # M100
    # S100
    # L100
    # XL100
    # 4X4
    # 6X5Y
    # 100支
    # =========================================================

    @staticmethod
    def extract_tokens(
        value
    ):

        text = (
            ProductAliasService
            .normalize_for_match(
                value
            )
        )

        tokens = set()

        patterns = [
            r"[XSML]{1,3}\d{1,4}",
            r"\d+(?:\.\d+)?G",
            r"\d+(?:\.\d+)?X\d+(?:\.\d+)?",
            r"\d+X\d+[A-Z]?",
            r"\d+CM",
            r"\d+支",
            r"\d+片",
            r"\d+盒",
            r"\d+包",
            r"\d+雙",
        ]

        for pattern in patterns:

            found = re.findall(
                pattern,
                text
            )

            tokens.update(
                found
            )

        keywords = [
            "無粉",
            "有粉",
            "抗過敏",
            "檢診手套",
            "PVC",
            "NBR",
            "乳膠",
            "彈性繃帶",
            "織邊繃帶",
            "石膏襪套",
            "酒精棉片",
            "棉棒",
            "棉球",
            "消毒袋",
            "口罩",
            "尿袋",
            "抽痰包",
            "隔離衣",
            "女帽",
            "紗布",
            "不織布",
        ]

        raw = (
            ProductAliasService
            .normalize_name(
                value
            )
            .upper()
        )

        for keyword in keywords:

            if (
                keyword.upper()
                in raw
            ):

                tokens.add(
                    keyword.upper()
                )

        return tokens

    # =========================================================
    # 計算兩個產品名稱相似度
    #
    # 0 ~ 100
    # =========================================================

    @staticmethod
    def calculate_similarity(
        pdf_name,
        product
    ):

        pdf_name_clean = (
            ProductAliasService
            .normalize_for_match(
                pdf_name
            )
        )

        product_text = (
            ProductAliasService
            .build_product_search_text(
                product
            )
        )

        product_clean = (
            ProductAliasService
            .normalize_for_match(
                product_text
            )
        )

        if (
            not pdf_name_clean
            or
            not product_clean
        ):

            return 0

        # =====================================================
        # 基礎字串相似度
        # =====================================================

        sequence_score = (
            SequenceMatcher(
                None,
                pdf_name_clean,
                product_clean
            )
            .ratio()
            *
            100
        )

        # =====================================================
        # 若其中一方包含另一方
        # =====================================================

        contain_bonus = 0

        if (
            pdf_name_clean
            in product_clean
            or
            product_clean
            in pdf_name_clean
        ):

            contain_bonus = 18

        # =====================================================
        # 規格 / 關鍵詞 Token
        # =====================================================

        pdf_tokens = (
            ProductAliasService
            .extract_tokens(
                pdf_name
            )
        )

        product_tokens = (
            ProductAliasService
            .extract_tokens(
                product_text
            )
        )

        token_score = 0

        if pdf_tokens:

            common = (
                pdf_tokens
                &
                product_tokens
            )

            token_score = (
                len(common)
                /
                len(pdf_tokens)
                *
                100
            )

        # =====================================================
        # 最重要：規格衝突扣分
        #
        # M100 不要推薦 S100
        # L100 不要推薦 XL100
        # =====================================================

        size_pattern = (
            r"\b("
            r"XXL\d*|XL\d*|L\d*|M\d*|S\d*|XS\d*"
            r")\b"
        )

        pdf_sizes = set(
            re.findall(
                size_pattern,
                ProductAliasService
                .normalize_name(
                    pdf_name
                )
                .upper()
            )
        )

        product_sizes = set(
            re.findall(
                size_pattern,
                ProductAliasService
                .normalize_name(
                    product_text
                )
                .upper()
            )
        )

        conflict_penalty = 0

        if (
            pdf_sizes
            and
            product_sizes
            and
            pdf_sizes.isdisjoint(
                product_sizes
            )
        ):

            conflict_penalty = 35

        # =====================================================
        # 綜合
        # =====================================================

        final_score = (
            sequence_score
            *
            0.55
            +
            token_score
            *
            0.45
            +
            contain_bonus
            -
            conflict_penalty
        )

        final_score = max(
            0,
            min(
                100,
                final_score
            )
        )

        return round(
            final_score,
            1
        )

    # =========================================================
    # 找最佳產品
    # =========================================================

    @staticmethod
    def suggest_product(
        pdf_name,
        products
    ):

        if not products:

            return {
                "產品編號":
                    "",

                "產品名稱":
                    "",

                "分數":
                    0,
            }

        best_product = None
        best_score = -1

        for product in products:

            product_no = str(
                product.get(
                    "產品編號",
                    ""
                )
            ).strip()

            if not product_no:
                continue

            score = (
                ProductAliasService
                .calculate_similarity(
                    pdf_name,
                    product
                )
            )

            if score > best_score:

                best_score = score
                best_product = product

        if best_product is None:

            return {
                "產品編號":
                    "",

                "產品名稱":
                    "",

                "分數":
                    0,
            }

        return {
            "產品編號":
                str(
                    best_product.get(
                        "產品編號",
                        ""
                    )
                ).strip(),

            "產品名稱":
                str(
                    best_product.get(
                        "產品名稱",
                        ""
                    )
                ).strip(),

            "分數":
                best_score,
        }