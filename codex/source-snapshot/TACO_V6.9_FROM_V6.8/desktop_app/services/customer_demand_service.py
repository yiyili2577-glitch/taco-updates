import os
import re

import pandas as pd
import pymupdf

from services.product_alias_service import ProductAliasService
from services.product_master_service import ProductMasterService


class CustomerDemandService:

    # =========================================================
    # 基本設定
    # =========================================================

    TABLE_COLUMNS = [
        "品名規格",
        "數量",
        "單位",
        "到貨日期",
        "配送地址",
        "客戶訂號",
    ]

    VALID_UNITS = {
        "盒",
        "箱",
        "捲",
        "卷",
        "雙",
        "包",
        "本",
        "打",
        "條",
        "KG",
        "kg",
        "Kg",
        "公斤",
        "片",
        "支",
        "個",
        "套",
        "組",
        "瓶",
        "桶",
        "台",
        "袋",
        "顆",
        "粒",
        "只",
        "件",
        "把",
        "罐",
        "張",
    }

    ADDRESS_KEYWORDS = [
        "台北市",
        "新北市",
        "桃園市",
        "台中市",
        "台南市",
        "高雄市",
        "基隆市",
        "新竹市",
        "嘉義市",
        "縣",
        "市",
        "區",
        "鄉",
        "鎮",
        "村",
        "里",
        "路",
        "街",
        "巷",
        "弄",
        "號",
        "樓",
        "醫院",
        "診所",
        "公司",
        "倉庫",
        "藥局",
        "院區",
        "中心",
        "衛材",
        "資材",
        "保管",
        "供應",
        "收發",
    ]

    NOTE_KEYWORDS = [
        "隨貨附",
        "附訂單",
        "出貨明細",
        "急件",
        "指定",
        "新竹物流",
        "大榮貨運",
        "貨運",
        "黑貓",
        "不良品",
        "備註",
        "請附",
        "隨貨",
        "出貨單",
        "收貨",
        "樣品",
    ]

    SPEC_PATTERNS = [
        r"^[SMLX]{1,4}\d{1,4}$",
        r"^[SMLX]{1,4}\d{1,4}\s*[（(].+?[）)]$",
        r"^\d+(?:\.\d+)?[gG]$",
        r"^\d+[\"吋]$",
        r"^[A-Za-z0-9\-/#]+$",
        r"^\d+[xX*×]\d+.*$",
    ]

    # =========================================================
    # 基本文字
    # =========================================================

    @staticmethod
    def clean_text(value):

        if value is None:
            return ""

        try:
            if pd.isna(value):
                return ""
        except Exception:
            pass

        text = str(value)

        text = (
            text
            .replace("\r", " ")
            .replace("\n", " ")
            .replace("\u3000", " ")
            .strip()
        )

        text = re.sub(
            r"\s+",
            " ",
            text
        )

        return text.strip()

    @staticmethod
    def compact_text(value):

        return (
            CustomerDemandService
            .clean_text(value)
            .replace(" ", "")
        )

    # =========================================================
    # 數量
    # =========================================================

    @staticmethod
    def parse_number(value):

        text = (
            CustomerDemandService
            .clean_text(value)
            .replace(",", "")
        )

        if not text:
            return None

        if re.fullmatch(
            r"-?\d+(?:\.\d+)?",
            text
        ):

            try:
                return float(text)
            except Exception:
                return None

        return None

    # =========================================================
    # 日期
    # =========================================================

    @staticmethod
    def extract_roc_date(value):

        text = (
            CustomerDemandService
            .clean_text(value)
        )

        match = re.search(
            r"\b(1\d{2}/\d{1,2}/\d{1,2})\b",
            text
        )

        if match:
            return match.group(1)

        return ""

    @staticmethod
    def is_date(value):

        return bool(
            CustomerDemandService
            .extract_roc_date(
                value
            )
        )

    # =========================================================
    # 單位
    # =========================================================

    @staticmethod
    def normalize_unit(value):

        text = (
            CustomerDemandService
            .clean_text(value)
        )

        if not text:
            return ""

        compact = (
            text.replace(
                " ",
                ""
            )
        )

        # 日期不可能是單位
        if (
            CustomerDemandService
            .is_date(
                compact
            )
        ):
            return ""

        # 完全符合
        if (
            compact
            in CustomerDemandService
            .VALID_UNITS
        ):

            return compact

        # 例如：
        # 盒(20盒)
        # 包/箱
        # KG/包
        pattern = (
            r"^("
            +
            "|".join(
                re.escape(unit)
                for unit
                in sorted(
                    CustomerDemandService
                    .VALID_UNITS,
                    key=len,
                    reverse=True
                )
            )
            +
            r")"
            r"(?:[(/／].*)?$"
        )

        match = re.match(
            pattern,
            compact,
            flags=re.IGNORECASE
        )

        if match:
            return compact

        return ""

    @staticmethod
    def is_unit(value):

        return bool(
            CustomerDemandService
            .normalize_unit(
                value
            )
        )

    # =========================================================
    # 地址
    # =========================================================

    @staticmethod
    def looks_like_address(value):

        text = (
            CustomerDemandService
            .clean_text(value)
        )

        if not text:
            return False

        if any(
            keyword in text
            for keyword
            in CustomerDemandService
            .ADDRESS_KEYWORDS
        ):
            return True

        # 電話也算配送相關資訊
        if re.search(
            r"0\d{1,3}[-－]\d{6,10}",
            text
        ):
            return True

        return False

    # =========================================================
    # 備註
    # =========================================================

    @staticmethod
    def looks_like_note(value):

        text = (
            CustomerDemandService
            .clean_text(value)
        )

        if not text:
            return False

        return any(
            keyword in text
            for keyword
            in CustomerDemandService
            .NOTE_KEYWORDS
        )

    # =========================================================
    # 客戶訂號
    #
    # 包含：
    # O115040027
    # B1576438
    # A0278195
    # P202607310
    # 2150807003
    # 20260803004
    # D150803012-01
    # =========================================================

    @staticmethod
    def looks_like_customer_order_no(
        value
    ):

        text = (
            CustomerDemandService
            .clean_text(value)
            .replace(" ", "")
        )

        if not text:
            return False

        if (
            CustomerDemandService
            .is_date(text)
        ):
            return False

        if (
            CustomerDemandService
            .looks_like_address(text)
        ):
            return False

        if (
            CustomerDemandService
            .looks_like_note(text)
        ):
            return False

        # 純數字訂號
        if re.fullmatch(
            r"\d{7,16}",
            text
        ):
            return True

        # 英數混合
        if re.fullmatch(
            r"[A-Za-z#][A-Za-z0-9#\-]{4,24}",
            text
        ):
            return True

        # 英文數字混合但不是英文起頭
        if (
            re.fullmatch(
                r"[A-Za-z0-9#\-]{6,25}",
                text
            )
            and
            re.search(
                r"[A-Za-z]",
                text
            )
            and
            re.search(
                r"\d",
                text
            )
        ):
            return True

        return False

    # =========================================================
    # 規格續行
    # =========================================================

    @staticmethod
    def looks_like_spec_fragment(
        value
    ):

        text = (
            CustomerDemandService
            .clean_text(value)
        )

        if not text:
            return False

        # 太長通常不是單純規格
        if len(text) > 35:
            return False

        if (
            CustomerDemandService
            .is_date(text)
            or
            CustomerDemandService
            .is_unit(text)
            or
            CustomerDemandService
            .looks_like_address(text)
            or
            CustomerDemandService
            .looks_like_customer_order_no(text)
            or
            CustomerDemandService
            .looks_like_note(text)
        ):
            return False

        for pattern in (
            CustomerDemandService
            .SPEC_PATTERNS
        ):

            if re.fullmatch(
                pattern,
                text,
                flags=re.IGNORECASE
            ):
                return True

        # 常見：
        # M100（合約）
        # S100（合約）
        # 無粉
        # 藍
        # 白色
        if any(
            keyword in text
            for keyword
            in [
                "合約",
                "無粉",
                "有粉",
                "藍",
                "白色",
                "綠色",
                "橘色",
                "黑色",
            ]
        ):
            return True

        return False

    # =========================================================
    # 採購單資料
    # =========================================================

    @staticmethod
    def extract_order_no(text):

        text = (
            CustomerDemandService
            .clean_text(text)
        )

        match = re.search(
            r"採購單號\s*[:：]?\s*([A-Za-z0-9\-]+)",
            text
        )

        if match:
            return match.group(1).strip()

        return ""

    @staticmethod
    def extract_purchase_date(text):

        text = (
            CustomerDemandService
            .clean_text(text)
        )

        match = re.search(
            r"採購日期\s*[:：]?\s*"
            r"(1\d{2}/\d{1,2}/\d{1,2})",
            text
        )

        if match:
            return match.group(1)

        return ""

    @staticmethod
    def extract_vendor(text):

        lines = [
            CustomerDemandService
            .clean_text(line)

            for line
            in str(text).splitlines()

            if CustomerDemandService
            .clean_text(line)
        ]

        for line in lines:

            if "廠商名稱" not in line:
                continue

            value = re.sub(
                r"^.*?廠商名稱\s*[:：]?\s*",
                "",
                line
            )

            stop_labels = [
                "聯絡電話",
                "電話",
                "傳真",
                "廠商地址",
                "採購日期",
                "採購人員",
            ]

            for stop in stop_labels:

                if stop in value:

                    value = (
                        value.split(
                            stop,
                            1
                        )[0]
                    )

            value = re.sub(
                r"\s+0\d{1,3}"
                r"[-－]\d{6,10}"
                r"(?:#\d+)?"
                r".*$",
                "",
                value
            )

            return value.strip()

        return ""

    # =========================================================
    # PDF words
    # =========================================================

    @staticmethod
    def normalize_words(
        raw_words
    ):

        result = []

        for word in raw_words:

            if len(word) < 5:
                continue

            text = (
                CustomerDemandService
                .clean_text(
                    word[4]
                )
            )

            if not text:
                continue

            x0 = float(
                word[0]
            )

            y0 = float(
                word[1]
            )

            x1 = float(
                word[2]
            )

            y1 = float(
                word[3]
            )

            result.append(
                {
                    "x0":
                        x0,

                    "y0":
                        y0,

                    "x1":
                        x1,

                    "y1":
                        y1,

                    "cx":
                        (
                            x0 + x1
                        ) / 2,

                    "cy":
                        (
                            y0 + y1
                        ) / 2,

                    "text":
                        text,
                }
            )

        return result

    # =========================================================
    # 視覺行
    # =========================================================

    @staticmethod
    def group_words_by_line(
        words,
        tolerance=3.0
    ):

        words = sorted(
            words,
            key=lambda item:
            (
                item["cy"],
                item["x0"]
            )
        )

        lines = []

        current = []
        current_y = None

        for word in words:

            if current_y is None:

                current = [
                    word
                ]

                current_y = word[
                    "cy"
                ]

                continue

            if (
                abs(
                    word["cy"]
                    -
                    current_y
                )
                <=
                tolerance
            ):

                current.append(
                    word
                )

                current_y = (
                    sum(
                        item["cy"]
                        for item
                        in current
                    )
                    /
                    len(current)
                )

            else:

                current.sort(
                    key=lambda item:
                    item["x0"]
                )

                lines.append(
                    current
                )

                current = [
                    word
                ]

                current_y = word[
                    "cy"
                ]

        if current:

            current.sort(
                key=lambda item:
                item["x0"]
            )

            lines.append(
                current
            )

        return lines

    # =========================================================
    # 找表頭
    # =========================================================

    @staticmethod
    def find_header_line(
        words
    ):

        lines = (
            CustomerDemandService
            .group_words_by_line(
                words,
                tolerance=4.0
            )
        )

        best = None
        best_score = 0

        for line in lines:

            joined = "".join(
                CustomerDemandService
                .compact_text(
                    item["text"]
                )
                for item
                in line
            )

            score = 0

            if "品名規格" in joined:
                score += 5

            if "數量" in joined:
                score += 4

            if "單位" in joined:
                score += 3

            if "到貨日期" in joined:
                score += 5

            if "配送地址" in joined:
                score += 4

            if "客戶訂號" in joined:
                score += 4

            if score > best_score:

                best_score = score
                best = line

        if best_score < 12:
            return None

        return best

    # =========================================================
    # 找表頭中心
    # =========================================================

    @staticmethod
    def find_header_centers(
        header_line,
        page_width
    ):

        items = sorted(
            header_line,
            key=lambda item:
            item["x0"]
        )

        def find_target(
            target
        ):

            # 單 word
            for item in items:

                compact = (
                    CustomerDemandService
                    .compact_text(
                        item["text"]
                    )
                )

                if target in compact:

                    return item[
                        "cx"
                    ]

            # 合併相鄰
            for start in range(
                len(items)
            ):

                text = ""
                selected = []

                for end in range(
                    start,
                    min(
                        len(items),
                        start + 6
                    )
                ):

                    text += (
                        CustomerDemandService
                        .compact_text(
                            items[end]["text"]
                        )
                    )

                    selected.append(
                        items[end]
                    )

                    if target in text:

                        left = min(
                            item["x0"]
                            for item
                            in selected
                        )

                        right = max(
                            item["x1"]
                            for item
                            in selected
                        )

                        return (
                            left + right
                        ) / 2

            return None

        centers = {
            "品名規格":
                find_target(
                    "品名規格"
                ),

            "數量":
                find_target(
                    "數量"
                ),

            "單位":
                find_target(
                    "單位"
                ),

            "到貨日期":
                find_target(
                    "到貨日期"
                ),

            "配送地址":
                find_target(
                    "配送地址"
                ),

            "客戶訂號":
                find_target(
                    "客戶訂號"
                ),
        }

        fallback = {
            "品名規格":
                page_width * 0.20,

            "數量":
                page_width * 0.41,

            "單位":
                page_width * 0.48,

            "到貨日期":
                page_width * 0.57,

            "配送地址":
                page_width * 0.73,

            "客戶訂號":
                page_width * 0.92,
        }

        for column in (
            CustomerDemandService
            .TABLE_COLUMNS
        ):

            if centers[
                column
            ] is None:

                centers[
                    column
                ] = fallback[
                    column
                ]

        return centers

    # =========================================================
    # 欄位邊界
    # =========================================================

    @staticmethod
    def build_column_boundaries(
        centers,
        page_width
    ):

        columns = (
            CustomerDemandService
            .TABLE_COLUMNS
        )

        boundaries = {}

        for index, column in enumerate(
            columns
        ):

            if index == 0:

                left = 0

            else:

                previous = (
                    columns[
                        index - 1
                    ]
                )

                left = (
                    centers[
                        previous
                    ]
                    +
                    centers[
                        column
                    ]
                ) / 2

            if (
                index
                ==
                len(columns) - 1
            ):

                right = (
                    page_width
                    +
                    10
                )

            else:

                next_column = (
                    columns[
                        index + 1
                    ]
                )

                right = (
                    centers[
                        column
                    ]
                    +
                    centers[
                        next_column
                    ]
                ) / 2

            boundaries[
                column
            ] = (
                left,
                right
            )

        return boundaries

    # =========================================================
    # 真實 lines 表格
    # =========================================================

    @staticmethod
    def find_line_table(
        page
    ):

        try:

            finder = (
                page.find_tables(
                    strategy="lines",

                    snap_tolerance=4,
                    join_tolerance=5,
                    intersection_tolerance=5,
                    edge_min_length=2,
                )
            )

        except Exception:
            return None

        try:
            tables = finder.tables
        except Exception:
            return None

        if not tables:
            return None

        best_table = None
        best_score = -1

        for table in tables:

            try:

                bbox = (
                    table.bbox
                )

                rows = (
                    table.extract()
                )

            except Exception:
                continue

            width = (
                float(
                    bbox[2]
                )
                -
                float(
                    bbox[0]
                )
            )

            width_ratio = (
                width
                /
                page.rect.width
            )

            row_count = (
                len(rows)
            )

            score = (
                row_count
                +
                width_ratio * 30
            )

            if score > best_score:

                best_score = score
                best_table = table

        return best_table

    # =========================================================
    # Rows Y
    # =========================================================

    @staticmethod
    def get_table_row_boundaries(
        table
    ):

        try:

            cells = (
                table.cells
            )

        except Exception:

            cells = []

        y_values = []

        for cell in cells:

            if not cell:
                continue

            try:

                x0, y0, x1, y1 = cell

            except Exception:
                continue

            y_values.extend(
                [
                    float(y0),
                    float(y1),
                ]
            )

        if not y_values:
            return []

        y_values.sort()

        merged = []

        for value in y_values:

            if not merged:

                merged.append(
                    value
                )

                continue

            if (
                abs(
                    value
                    -
                    merged[-1]
                )
                <=
                2.0
            ):

                merged[-1] = (
                    merged[-1]
                    +
                    value
                ) / 2

            else:

                merged.append(
                    value
                )

        ranges = []

        for index in range(
            len(merged) - 1
        ):

            top = merged[
                index
            ]

            bottom = merged[
                index + 1
            ]

            if (
                bottom - top
                >=
                3
            ):

                ranges.append(
                    (
                        top,
                        bottom
                    )
                )

        return ranges

    # =========================================================
    # 取 Cell words
    # =========================================================

    @staticmethod
    def get_cell_text_from_words(
        words,
        row_top,
        row_bottom,
        col_left,
        col_right
    ):

        selected = []

        for word in words:

            if not (
                row_top
                <=
                word["cy"]
                <
                row_bottom
            ):
                continue

            if not (
                col_left
                <=
                word["cx"]
                <
                col_right
            ):
                continue

            selected.append(
                word
            )

        if not selected:
            return ""

        lines = (
            CustomerDemandService
            .group_words_by_line(
                selected,
                tolerance=3.0
            )
        )

        text_lines = []

        for line in lines:

            text = (
                " ".join(
                    item["text"]
                    for item
                    in line
                )
            )

            text = (
                CustomerDemandService
                .clean_text(
                    text
                )
            )

            if text:

                text_lines.append(
                    text
                )

        return (
            " ".join(
                text_lines
            )
            .strip()
        )

    # =========================================================
    # 初步 Row
    # =========================================================

    @staticmethod
    def read_raw_rows(
        page
    ):

        raw_words = (
            page.get_text(
                "words"
            )
        )

        words = (
            CustomerDemandService
            .normalize_words(
                raw_words
            )
        )

        if not words:
            return []

        header_line = (
            CustomerDemandService
            .find_header_line(
                words
            )
        )

        if header_line is None:
            return []

        centers = (
            CustomerDemandService
            .find_header_centers(
                header_line,
                page.rect.width
            )
        )

        boundaries = (
            CustomerDemandService
            .build_column_boundaries(
                centers,
                page.rect.width
            )
        )

        header_bottom = max(
            word["y1"]
            for word
            in header_line
        )

        table = (
            CustomerDemandService
            .find_line_table(
                page
            )
        )

        if table is None:
            return []

        row_ranges = (
            CustomerDemandService
            .get_table_row_boundaries(
                table
            )
        )

        raw_rows = []

        for row_index, (
            row_top,
            row_bottom
        ) in enumerate(
            row_ranges,
            start=1
        ):

            if (
                row_bottom
                <=
                header_bottom + 1
            ):
                continue

            row = {
                "_row_index":
                    row_index
            }

            for column in (
                CustomerDemandService
                .TABLE_COLUMNS
            ):

                left, right = (
                    boundaries[
                        column
                    ]
                )

                row[
                    column
                ] = (
                    CustomerDemandService
                    .get_cell_text_from_words(
                        words,
                        row_top,
                        row_bottom,
                        left,
                        right
                    )
                )

            combined = (
                " ".join(
                    str(value)
                    for key, value
                    in row.items()

                    if key
                    !=
                    "_row_index"
                )
            )

            if any(
                marker in combined
                for marker
                in [
                    "備註",
                    "合計",
                    "總計",
                    "請款單於隔月",
                    "無法如期交貨",
                ]
            ):
                continue

            if not any(
                CustomerDemandService
                .clean_text(
                    value
                )
                for key, value
                in row.items()

                if key
                !=
                "_row_index"
            ):
                continue

            raw_rows.append(
                row
            )

        return raw_rows

    # =========================================================
    # 把 Row 裡所有 Cell 拆成 token
    #
    # 不是死守原來欄位
    # =========================================================

    @staticmethod
    def row_tokens(
        row
    ):

        result = []

        for column in (
            CustomerDemandService
            .TABLE_COLUMNS
        ):

            value = (
                CustomerDemandService
                .clean_text(
                    row.get(
                        column,
                        ""
                    )
                )
            )

            if not value:
                continue

            # 保留整格
            result.append(
                {
                    "source_column":
                        column,

                    "text":
                        value,
                }
            )

        return result

    # =========================================================
    # 語意重新分類
    # =========================================================

    @staticmethod
    def semantic_repair_row(
        row
    ):

        tokens = (
            CustomerDemandService
            .row_tokens(
                row
            )
        )

        repaired = {
            "品名規格":
                "",

            "數量":
                None,

            "單位":
                "",

            "到貨日期":
                "",

            "配送地址":
                "",

            "客戶訂號":
                "",

            "出貨備註":
                "",

            "_row_index":
                row.get(
                    "_row_index"
                ),

            "_auto_fixed":
                [],
        }

        leftovers = []

        # =====================================================
        # 第一輪：
        # 高可信度欄位優先
        # =====================================================

        for token in tokens:

            text = (
                token[
                    "text"
                ]
            )

            source = (
                token[
                    "source_column"
                ]
            )

            # 日期
            date = (
                CustomerDemandService
                .extract_roc_date(
                    text
                )
            )

            if date:

                repaired[
                    "到貨日期"
                ] = date

                if source != "到貨日期":

                    repaired[
                        "_auto_fixed"
                    ].append(
                        f"{source}→到貨日期"
                    )

                remaining = (
                    text.replace(
                        date,
                        " "
                    )
                )

                remaining = (
                    CustomerDemandService
                    .clean_text(
                        remaining
                    )
                )

                if remaining:

                    leftovers.append(
                        {
                            "source_column":
                                source,

                            "text":
                                remaining,
                        }
                    )

                continue

            # 單位
            unit = (
                CustomerDemandService
                .normalize_unit(
                    text
                )
            )

            if unit:

                repaired[
                    "單位"
                ] = unit

                if source != "單位":

                    repaired[
                        "_auto_fixed"
                    ].append(
                        f"{source}→單位"
                    )

                continue

            # 純數字
            number = (
                CustomerDemandService
                .parse_number(
                    text
                )
            )

            if number is not None:

                # 客戶訂號欄若是長數字，
                # 更可能是訂號
                compact = (
                    text.replace(
                        " ",
                        ""
                    )
                )

                if (
                    source
                    ==
                    "客戶訂號"
                    and
                    len(compact)
                    >=
                    7
                ):

                    repaired[
                        "客戶訂號"
                    ] = compact

                    continue

                # 其他情況先當數量
                if (
                    repaired[
                        "數量"
                    ]
                    is None
                ):

                    repaired[
                        "數量"
                    ] = number

                    if source != "數量":

                        repaired[
                            "_auto_fixed"
                        ].append(
                            f"{source}→數量"
                        )

                    continue

            # 客戶訂號
            if (
                CustomerDemandService
                .looks_like_customer_order_no(
                    text
                )
            ):

                repaired[
                    "客戶訂號"
                ] = (
                    text.replace(
                        " ",
                        ""
                    )
                )

                if source != "客戶訂號":

                    repaired[
                        "_auto_fixed"
                    ].append(
                        f"{source}→客戶訂號"
                    )

                continue

            # 備註
            if (
                CustomerDemandService
                .looks_like_note(
                    text
                )
            ):

                if repaired[
                    "出貨備註"
                ]:

                    repaired[
                        "出貨備註"
                    ] += (
                        " "
                        +
                        text
                    )

                else:

                    repaired[
                        "出貨備註"
                    ] = text

                continue

            # 地址
            if (
                CustomerDemandService
                .looks_like_address(
                    text
                )
            ):

                if repaired[
                    "配送地址"
                ]:

                    repaired[
                        "配送地址"
                    ] += (
                        " "
                        +
                        text
                    )

                else:

                    repaired[
                        "配送地址"
                    ] = text

                if source != "配送地址":

                    repaired[
                        "_auto_fixed"
                    ].append(
                        f"{source}→配送地址"
                    )

                continue

            leftovers.append(
                {
                    "source_column":
                        source,

                    "text":
                        text,
                }
            )

        # =====================================================
        # 第二輪：
        # 剩下內容
        # =====================================================

        product_parts = []

        for token in leftovers:

            text = token[
                "text"
            ]

            source = token[
                "source_column"
            ]

            # 如果仍然很像地址
            if (
                CustomerDemandService
                .looks_like_address(
                    text
                )
            ):

                if repaired[
                    "配送地址"
                ]:

                    repaired[
                        "配送地址"
                    ] += (
                        " "
                        +
                        text
                    )

                else:

                    repaired[
                        "配送地址"
                    ] = text

                continue

            # 訂號與備註可能同格
            if (
                source
                ==
                "客戶訂號"
            ):

                pieces = (
                    CustomerDemandService
                    .split_order_and_note(
                        text
                    )
                )

                if (
                    pieces[
                        "order_no"
                    ]
                ):

                    repaired[
                        "客戶訂號"
                    ] = pieces[
                        "order_no"
                    ]

                if (
                    pieces[
                        "note"
                    ]
                ):

                    repaired[
                        "出貨備註"
                    ] = (
                        (
                            repaired[
                                "出貨備註"
                            ]
                            +
                            " "
                        )
                        if repaired[
                            "出貨備註"
                        ]
                        else ""
                    ) + pieces[
                        "note"
                    ]

                if (
                    pieces[
                        "rest"
                    ]
                ):

                    product_parts.append(
                        pieces[
                            "rest"
                        ]
                    )

                continue

            product_parts.append(
                text
            )

        repaired[
            "品名規格"
        ] = (
            ProductAliasService
            .normalize_name(
                " ".join(
                    product_parts
                )
            )
        )

        if (
            repaired[
                "數量"
            ]
            is None
        ):

            repaired[
                "數量"
            ] = 0.0

        return repaired

    # =========================================================
    # 客戶訂號 + 中文備註拆開
    # =========================================================

    @staticmethod
    def split_order_and_note(
        value
    ):

        text = (
            CustomerDemandService
            .clean_text(
                value
            )
        )

        result = {
            "order_no":
                "",

            "note":
                "",

            "rest":
                "",
        }

        if not text:
            return result

        # 找訂號 token
        tokens = (
            text.split()
        )

        other = []

        for token in tokens:

            compact = (
                token.replace(
                    " ",
                    ""
                )
            )

            if (
                not result[
                    "order_no"
                ]
                and
                CustomerDemandService
                .looks_like_customer_order_no(
                    compact
                )
            ):

                result[
                    "order_no"
                ] = compact

            else:

                other.append(
                    token
                )

        remaining = (
            " ".join(
                other
            )
        )

        if (
            CustomerDemandService
            .looks_like_note(
                remaining
            )
        ):

            result[
                "note"
            ] = remaining

        else:

            result[
                "rest"
            ] = remaining

        return result

    # =========================================================
    # 跨列合併
    # =========================================================

    @staticmethod
    def merge_continuation_rows(
        rows
    ):

        if not rows:
            return []

        result = []

        index = 0

        while index < len(
            rows
        ):

            current = rows[
                index
            ]

            # -------------------------------------------------
            # 純規格續行：
            #
            # 數量=0
            # 沒日期
            # 沒單位
            # 沒地址
            # 品名很像規格
            # -------------------------------------------------

            is_spec_only = (
                float(
                    current.get(
                        "數量",
                        0
                    )
                    or
                    0
                )
                ==
                0
                and
                not current.get(
                    "到貨日期"
                )
                and
                not current.get(
                    "單位"
                )
                and
                not current.get(
                    "配送地址"
                )
                and
                not current.get(
                    "客戶訂號"
                )
                and
                CustomerDemandService
                .looks_like_spec_fragment(
                    current.get(
                        "品名規格",
                        ""
                    )
                )
            )

            if is_spec_only:

                # -----------------------------------------
                # 優先併到上一列
                # -----------------------------------------

                if result:

                    previous = (
                        result[-1]
                    )

                    # 如果上一列已有完整數量
                    if (
                        float(
                            previous.get(
                                "數量",
                                0
                            )
                            or
                            0
                        )
                        >
                        0
                    ):

                        previous_name = (
                            previous.get(
                                "品名規格",
                                ""
                            )
                        )

                        spec = (
                            current.get(
                                "品名規格",
                                ""
                            )
                        )

                        previous[
                            "品名規格"
                        ] = (
                            ProductAliasService
                            .normalize_name(
                                (
                                    previous_name
                                    +
                                    " "
                                    +
                                    spec
                                )
                            )
                        )

                        previous[
                            "_auto_fixed"
                        ].append(
                            "跨列規格合併"
                        )

                        index += 1
                        continue

                # -----------------------------------------
                # 若無上一列，嘗試併下一列
                # -----------------------------------------

                if (
                    index + 1
                    <
                    len(rows)
                ):

                    next_row = (
                        rows[
                            index + 1
                        ]
                    )

                    if (
                        float(
                            next_row.get(
                                "數量",
                                0
                            )
                            or
                            0
                        )
                        >
                        0
                    ):

                        spec = (
                            current.get(
                                "品名規格",
                                ""
                            )
                        )

                        next_name = (
                            next_row.get(
                                "品名規格",
                                ""
                            )
                        )

                        next_row[
                            "品名規格"
                        ] = (
                            ProductAliasService
                            .normalize_name(
                                (
                                    spec
                                    +
                                    " "
                                    +
                                    next_name
                                )
                            )
                        )

                        next_row[
                            "_auto_fixed"
                        ].append(
                            "跨列規格合併"
                        )

                        index += 1
                        continue

            result.append(
                current
            )

            index += 1

        # =====================================================
        # 再清除真正無效列
        # =====================================================

        final_rows = []

        for row in result:

            quantity = float(
                row.get(
                    "數量",
                    0
                )
                or
                0
            )

            if (
                quantity
                <=
                0
            ):

                # 沒數量不能作為正式需求
                continue

            if not row.get(
                "品名規格"
            ):
                continue

            final_rows.append(
                row
            )

        return final_rows

    # =========================================================
    # 客戶 + 地址
    # =========================================================

    @staticmethod
    def parse_customer_from_delivery(
        delivery
    ):

        delivery = (
            CustomerDemandService
            .clean_text(
                delivery
            )
        )

        if not delivery:
            return "", ""

        # 客戶：地址
        match = re.match(
            r"^(.{1,60}?)[：:]\s*(.+)$",
            delivery
        )

        if match:

            return (
                match.group(1).strip(),
                match.group(2).strip(),
            )

        # XX醫院 台北市...
        match = re.match(
            r"^(.{1,40}?"
            r"(?:醫院|診所|公司|倉庫|藥局|中心|院區|機構)"
            r")\s+(.+)$",
            delivery
        )

        if match:

            return (
                match.group(1).strip(),
                match.group(2).strip(),
            )

        return "", delivery

    # =========================================================
    # 配送類型
    # =========================================================

    @staticmethod
    def determine_delivery_type(
        delivery
    ):

        text = (
            CustomerDemandService
            .clean_text(
                delivery
            )
        )

        if any(
            keyword in text
            for keyword
            in [
                "蓓莉雅公司",
                "蓓莉雅股份有限公司",
                "蓓莉雅：",
                "蓓莉雅:",
            ]
        ):

            return "公司入庫"

        return "客戶直送"

    # =========================================================
    # 驗證
    # =========================================================

    @staticmethod
    def validate_repaired_row(
        row
    ):

        serious = []
        auto_fixed = (
            row.get(
                "_auto_fixed",
                []
            )
        )

        product_name = (
            ProductAliasService
            .normalize_name(
                row.get(
                    "品名規格",
                    ""
                )
            )
        )

        quantity = float(
            row.get(
                "數量",
                0
            )
            or
            0
        )

        unit = (
            CustomerDemandService
            .normalize_unit(
                row.get(
                    "單位",
                    ""
                )
            )
        )

        arrival_date = (
            CustomerDemandService
            .extract_roc_date(
                row.get(
                    "到貨日期",
                    ""
                )
            )
        )

        delivery = (
            CustomerDemandService
            .clean_text(
                row.get(
                    "配送地址",
                    ""
                )
            )
        )

        customer_order_no = (
            CustomerDemandService
            .clean_text(
                row.get(
                    "客戶訂號",
                    ""
                )
            )
        )

        note = (
            CustomerDemandService
            .clean_text(
                row.get(
                    "出貨備註",
                    ""
                )
            )
        )

        if not product_name:

            serious.append(
                "缺少品名規格"
            )

        if quantity <= 0:

            serious.append(
                "數量異常"
            )

        if not arrival_date:

            serious.append(
                "缺少或無法辨識到貨日期"
            )

        if not delivery:

            serious.append(
                "缺少配送資料"
            )

        if (
            customer_order_no
            and
            CustomerDemandService
            .looks_like_address(
                customer_order_no
            )
        ):

            serious.append(
                "客戶訂號疑似為地址"
            )

        if serious:

            status = (
                "🔴 需要人工確認"
            )

        elif auto_fixed:

            status = (
                "🟡 自動修正"
            )

        else:

            status = (
                "🟢 正常"
            )

        return {
            "驗證狀態":
                status,

            "驗證問題":
                "；".join(
                    serious
                ),

            "自動修正":
                "；".join(
                    auto_fixed
                ),

            "品名規格":
                product_name,

            "數量":
                quantity,

            "單位":
                unit,

            "到貨日期":
                arrival_date,

            "配送地址":
                delivery,

            "客戶訂號":
                customer_order_no,

            "出貨備註":
                note,
        }

    # =========================================================
    # 單頁
    # =========================================================

    @staticmethod
    def parse_page(
        page,
        page_number
    ):

        page_text = (
            page.get_text(
                "text",
                sort=True
            )
            or
            ""
        )

        order_no = (
            CustomerDemandService
            .extract_order_no(
                page_text
            )
        )

        purchase_date = (
            CustomerDemandService
            .extract_purchase_date(
                page_text
            )
        )

        vendor = (
            CustomerDemandService
            .extract_vendor(
                page_text
            )
        )

        raw_rows = (
            CustomerDemandService
            .read_raw_rows(
                page
            )
        )

        if not raw_rows:

            return {
                "rows":
                    [],

                "reason":
                    "本頁沒有可解析的需求表格",
            }

        repaired_rows = []

        for raw_row in raw_rows:

            repaired = (
                CustomerDemandService
                .semantic_repair_row(
                    raw_row
                )
            )

            repaired_rows.append(
                repaired
            )

        repaired_rows = (
            CustomerDemandService
            .merge_continuation_rows(
                repaired_rows
            )
        )

        result = []

        for repaired in repaired_rows:

            validated = (
                CustomerDemandService
                .validate_repaired_row(
                    repaired
                )
            )

            customer, address = (
                CustomerDemandService
                .parse_customer_from_delivery(
                    validated[
                        "配送地址"
                    ]
                )
            )

            delivery_type = (
                CustomerDemandService
                .determine_delivery_type(
                    validated[
                        "配送地址"
                    ]
                )
            )

            result.append(
                {
                    "驗證狀態":
                        validated[
                            "驗證狀態"
                        ],

                    "驗證問題":
                        validated[
                            "驗證問題"
                        ],

                    "自動修正":
                        validated[
                            "自動修正"
                        ],

                    "PDF頁碼":
                        page_number,

                    "PDF表格列":
                        repaired.get(
                            "_row_index",
                            ""
                        ),

                    "採購單號":
                        order_no,

                    "採購日期":
                        purchase_date,

                    "採購廠商":
                        vendor,

                    "客戶":
                        customer,

                    "客戶訂號":
                        validated[
                            "客戶訂號"
                        ],

                    "出貨備註":
                        validated[
                            "出貨備註"
                        ],

                    "PDF品名規格":
                        validated[
                            "品名規格"
                        ],

                    "數量":
                        validated[
                            "數量"
                        ],

                    "單位":
                        validated[
                            "單位"
                        ],

                    "到貨日期":
                        validated[
                            "到貨日期"
                        ],

                    "配送類型":
                        delivery_type,

                    "配送地址":
                        address,

                    "配送內容":
                        validated[
                            "配送地址"
                        ],

                    "表格解析策略":
                        "lines + semantic_repair",
                }
            )

        return {
            "rows":
                result,

            "reason":
                "",
        }

    # =========================================================
    # PDF 全檔
    # =========================================================

    @staticmethod
    def read_pdf(
        file_path
    ):

        try:

            document = (
                pymupdf.open(
                    file_path
                )
            )

        except Exception as e:

            raise Exception(
                f"PDF 無法開啟：{str(e)}"
            )

        all_rows = []

        page_errors = []

        skipped_pages = []

        total_pages = len(
            document
        )

        try:

            for page_index in range(
                total_pages
            ):

                page_number = (
                    page_index + 1
                )

                try:

                    page = (
                        document[
                            page_index
                        ]
                    )

                    parsed = (
                        CustomerDemandService
                        .parse_page(
                            page,
                            page_number
                        )
                    )

                    rows = (
                        parsed[
                            "rows"
                        ]
                    )

                    if rows:

                        all_rows.extend(
                            rows
                        )

                    else:

                        skipped_pages.append(
                            {
                                "page":
                                    page_number,

                                "reason":
                                    parsed[
                                        "reason"
                                    ],
                            }
                        )

                except Exception as e:

                    page_errors.append(
                        {
                            "page":
                                page_number,

                            "error":
                                str(e),
                        }
                    )

        finally:

            document.close()

        if not all_rows:

            raise Exception(
                "PDF 已成功開啟，但經過"
                "格線＋語意修復後仍沒有解析到需求資料。"
            )

        df = (
            pd.DataFrame(
                all_rows
            )
        )

        # =====================================================
        # 去重
        # =====================================================

        dedupe_columns = [
            "PDF頁碼",
            "採購單號",
            "PDF品名規格",
            "數量",
            "到貨日期",
            "配送內容",
            "客戶訂號",
        ]

        dedupe_columns = [
            column
            for column
            in dedupe_columns
            if column in df.columns
        ]

        if dedupe_columns:

            df = (
                df
                .drop_duplicates(
                    subset=dedupe_columns
                )
                .reset_index(
                    drop=True
                )
            )

        # =====================================================
        # Alias
        # =====================================================

        df = (
            ProductAliasService
            .apply_aliases(
                df
            )
        )

        # =====================================================
        # Product master
        # =====================================================

        df = (
            CustomerDemandService
            .attach_product_master(
                df
            )
        )

        return {
            "detail_df":
                df,

            "pages":
                total_pages,

            "page_errors":
                page_errors,

            "no_table_pages":
                skipped_pages,

            "source_file":
                os.path.basename(
                    file_path
                ),
        }

    # =========================================================
    # Product master
    # =========================================================

    @staticmethod
    def attach_product_master(
        df
    ):

        if df is None:
            return df

        if df.empty:
            return df

        df = df.copy()

        products = (
            ProductMasterService
            .load_products()
        )

        product_map = {}

        for product in products:

            product_no = (
                str(
                    product.get(
                        "產品編號",
                        ""
                    )
                )
                .strip()
            )

            if product_no:

                product_map[
                    product_no
                ] = product

        product_names = []
        categories = []
        mapping_statuses = []

        for _, row in (
            df.iterrows()
        ):

            product_no = (
                str(
                    row.get(
                        "產品編號",
                        ""
                    )
                )
                .strip()
            )

            product = (
                product_map.get(
                    product_no
                )
            )

            if (
                product_no
                and
                product
            ):

                product_names.append(
                    product.get(
                        "產品名稱",
                        ""
                    )
                )

                categories.append(
                    product.get(
                        "品項分類",
                        ""
                    )
                )

                mapping_statuses.append(
                    "🟢 已對應"
                )

            else:

                product_names.append(
                    ""
                )

                categories.append(
                    ""
                )

                mapping_statuses.append(
                    "🔴 未對應"
                )

        df[
            "產品名稱"
        ] = product_names

        df[
            "品項分類"
        ] = categories

        df[
            "對應狀態"
        ] = mapping_statuses

        preferred = [
            "驗證狀態",
            "驗證問題",
            "自動修正",
            "對應狀態",
            "PDF頁碼",
            "採購單號",
            "採購日期",
            "採購廠商",
            "客戶",
            "客戶訂號",
            "出貨備註",
            "PDF品名規格",
            "產品編號",
            "產品名稱",
            "品項分類",
            "數量",
            "單位",
            "到貨日期",
            "配送類型",
            "配送地址",
            "配送內容",
        ]

        columns = []

        for column in preferred:

            if (
                column in df.columns
                and
                column not in columns
            ):

                columns.append(
                    column
                )

        for column in df.columns:

            if column not in columns:

                columns.append(
                    column
                )

        return (
            df[
                columns
            ]
            .reset_index(
                drop=True
            )
        )

    # =========================================================
    # 未對應
    #
    # 正常＋自動修正都可以進
    # 紅色人工確認不能進
    # =========================================================

    @staticmethod
    def get_unmapped_products(
        detail_df
    ):

        empty = pd.DataFrame(
            columns=[
                "PDF品名規格",
                "出現次數",
                "需求總量",
            ]
        )

        if (
            detail_df is None
            or
            detail_df.empty
        ):

            return empty

        df = (
            detail_df.copy()
        )

        df = df[
            df[
                "產品編號"
            ]
            .fillna("")
            .astype(str)
            .str.strip()
            ==
            ""
        ]

        if (
            "驗證狀態"
            in df.columns
        ):

            df = df[
                df[
                    "驗證狀態"
                ]
                .isin(
                    [
                        "🟢 正常",
                        "🟡 自動修正",
                    ]
                )
            ]

        if df.empty:

            return empty

        df[
            "數量"
        ] = pd.to_numeric(
            df[
                "數量"
            ],
            errors="coerce"
        ).fillna(0)

        return (
            df.groupby(
                "PDF品名規格",
                dropna=False
            )
            .agg(
                出現次數=(
                    "PDF品名規格",
                    "size"
                ),

                需求總量=(
                    "數量",
                    "sum"
                ),
            )
            .reset_index()
        )

    # =========================================================
    # 民國日期
    # =========================================================

    @staticmethod
    def roc_date_to_timestamp(
        value
    ):

        date = (
            CustomerDemandService
            .extract_roc_date(
                value
            )
        )

        if not date:
            return pd.NaT

        try:

            year_text, month_text, day_text = (
                date.split("/")
            )

            return pd.Timestamp(
                year=(
                    int(year_text)
                    +
                    1911
                ),
                month=int(
                    month_text
                ),
                day=int(
                    day_text
                ),
            )

        except Exception:

            return pd.NaT

    # =========================================================
    # 需求彙總
    # =========================================================

    @staticmethod
    def summarize_demand(
        detail_df
    ):

        if (
            detail_df is None
            or
            detail_df.empty
        ):

            return pd.DataFrame()

        df = (
            detail_df.copy()
        )

        df = df[
            df[
                "產品編號"
            ]
            .fillna("")
            .astype(str)
            .str.strip()
            !=
            ""
        ]

        if (
            "驗證狀態"
            in df.columns
        ):

            df = df[
                df[
                    "驗證狀態"
                ]
                .isin(
                    [
                        "🟢 正常",
                        "🟡 自動修正",
                    ]
                )
            ]

        if df.empty:

            return pd.DataFrame()

        df[
            "數量"
        ] = pd.to_numeric(
            df[
                "數量"
            ],
            errors="coerce"
        ).fillna(0)

        df[
            "客戶直送量"
        ] = df.apply(
            lambda row:
            row["數量"]
            if row.get(
                "配送類型"
            )
            ==
            "客戶直送"
            else 0,
            axis=1
        )

        df[
            "公司入庫量"
        ] = df.apply(
            lambda row:
            row["數量"]
            if row.get(
                "配送類型"
            )
            ==
            "公司入庫"
            else 0,
            axis=1
        )

        df[
            "_日期"
        ] = df[
            "到貨日期"
        ].apply(
            CustomerDemandService
            .roc_date_to_timestamp
        )

        result_rows = []

        grouped = (
            df.groupby(
                [
                    "產品編號",
                    "產品名稱",
                    "品項分類",
                ],
                dropna=False
            )
        )

        for (
            product_no,
            product_name,
            category
        ), group in grouped:

            dates = (
                group[
                    "_日期"
                ]
                .dropna()
            )

            earliest = ""

            if not dates.empty:

                earliest_index = (
                    dates.idxmin()
                )

                earliest = (
                    group.loc[
                        earliest_index,
                        "到貨日期"
                    ]
                )

            customers = sorted(
                {
                    str(value).strip()

                    for value
                    in group[
                        "客戶"
                    ].fillna("")

                    if str(value).strip()
                }
            )

            result_rows.append(
                {
                    "產品編號":
                        product_no,

                    "產品名稱":
                        product_name,

                    "品項分類":
                        category,

                    "總需求量":
                        round(
                            group[
                                "數量"
                            ].sum(),
                            2
                        ),

                    "客戶直送量":
                        round(
                            group[
                                "客戶直送量"
                            ].sum(),
                            2
                        ),

                    "公司入庫量":
                        round(
                            group[
                                "公司入庫量"
                            ].sum(),
                            2
                        ),

                    "需求筆數":
                        len(
                            group
                        ),

                    "客戶數":
                        len(
                            customers
                        ),

                    "最早到貨日":
                        earliest,

                    "客戶":
                        "、".join(
                            customers
                        ),
                }
            )

        result = (
            pd.DataFrame(
                result_rows
            )
        )

        if not result.empty:

            result = (
                result
                .sort_values(
                    by=[
                        "品項分類",
                        "產品編號",
                    ],
                    na_position="last"
                )
                .reset_index(
                    drop=True
                )
            )

        return result