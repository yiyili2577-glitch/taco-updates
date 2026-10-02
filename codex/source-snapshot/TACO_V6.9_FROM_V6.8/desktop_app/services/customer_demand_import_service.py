import os
import re

import pandas as pd


class CustomerDemandImportService:
    """客戶需求 Excel 匯入、欄位拆解與 ERP 產品直接對應。"""

    MATERIAL_KEYWORDS = [
        "不織布", "PVC", "NBR", "乳膠", "矽膠", "聚酯纖維", "聚丙烯",
        "PP", "PE", "木漿", "竹纖維", "棉線", "紙", "尼龍",
    ]

    PRODUCT_KEYWORDS = [
        "抗過敏檢診手套", "檢診手套", "手術手套", "彈性繃帶", "織邊繃帶",
        "雙折邊紗布塊", "阻力線紗布塊", "紗布塊", "紗布", "石膏襪套",
        "酒精棉片", "棉棒", "棉球", "口罩", "尿袋", "抽痰包", "隔離衣",
        "女帽", "手術衣", "消毒袋", "膠帶", "敷料", "手套",
    ]

    COLUMN_ALIASES = {
        "採購單號": ["採購單號", "訂單號碼", "訂單號", "單號"],
        "採購日期": ["採購日期", "訂購日期", "訂購日", "日期"],
        "採購廠商": ["採購廠商", "供應商", "廠商", "賣方"],
        "客戶": ["客戶", "客戶名稱", "收貨客戶", "送貨客戶"],
        "客戶訂號": ["客戶訂號", "客戶訂單", "客戶訂單號", "訂號"],
        "PDF品名規格": ["PDF品名規格", "品名規格", "品名/規格", "品名／規格", "品名", "產品名稱", "商品名稱", "商品", "品項", "貨品名稱", "貨品"],
        "數量": ["數量", "數", "需求數量", "訂購數量", "採購數量", "需求量", "訂單數量", "出貨數量", "QTY", "Qty", "qty", "Quantity", "quantity"],
        "單位": ["單位", "數量單位", "計量單位", "UOM", "Unit", "unit"],
        "到貨日期": ["到貨日期", "到貨日", "約交日期", "約交日", "交貨日期", "交期", "需求日期", "預計到貨日"],
        "配送地址": ["配送地址", "送貨地址", "地址", "收貨地址"],
        "原始產品編號": ["原始產品編號", "客戶產品編號", "客戶品號", "產品編號", "料號", "品號"],
        "規格": ["規格", "產品規格"],
        "材質": ["材質", "材料"],
        "包裝方式": ["包裝方式", "包裝"],
        "單價": ["單價", "單價USD", "單價US$", "UnitPrice", "Unit Price"],
        "總價": ["總價", "總價USD", "總價US$", "Amount"],
        "紙箱規格": ["紙箱規格(CM)", "紙箱規格", "外箱規格CM", "外箱規格", "箱規"],
        "體積CBM": ["體積立方", "體積", "CBM", "體積CBM"],
    }

    @staticmethod
    def clean(value):
        if value is None:
            return ""
        try:
            if pd.isna(value):
                return ""
        except Exception:
            pass
        return re.sub(r"\s+", " ", str(value).replace("\u3000", " ")).strip()

    @staticmethod
    def normalize_col(value):
        text = CustomerDemandImportService.clean(value)
        return (
            text.replace(" ", "")
            .replace("\n", "")
            .replace("\r", "")
            .replace("（", "(")
            .replace("）", ")")
        )

    @staticmethod
    def normalize_product_no(value):
        return (
            CustomerDemandImportService.clean(value)
            .upper()
            .replace(" ", "")
            .replace("－", "-")
        )

    @staticmethod
    def find_header_row(file_path, max_rows=80):
        raw = pd.read_excel(file_path, header=None, nrows=max_rows)
        best = None
        best_score = -1

        for idx, row in raw.iterrows():
            cells = [CustomerDemandImportService.normalize_col(v) for v in row.tolist()]
            score = 0

            for canonical, aliases in CustomerDemandImportService.COLUMN_ALIASES.items():
                if canonical in {"採購單號", "採購日期", "採購廠商", "客戶", "配送地址"}:
                    continue
                for alias in aliases:
                    a = CustomerDemandImportService.normalize_col(alias)
                    if any(a and (c == a or a in c) for c in cells):
                        score += 1
                        break

            has_name = any(
                any(CustomerDemandImportService.normalize_col(a) in c
                    for a in CustomerDemandImportService.COLUMN_ALIASES["PDF品名規格"])
                for c in cells
            )
            has_qty = any(
                any(CustomerDemandImportService.normalize_col(a) == c
                    for a in CustomerDemandImportService.COLUMN_ALIASES["數量"])
                for c in cells
            )
            has_product_no = any(
                any(CustomerDemandImportService.normalize_col(a) in c
                    for a in CustomerDemandImportService.COLUMN_ALIASES["原始產品編號"])
                for c in cells
            )

            if has_name and (has_qty or has_product_no):
                score += 10

            if score > best_score:
                best_score = score
                best = idx

        if best is None or best_score < 10:
            return 0
        return int(best)

    @staticmethod
    def normalize_columns(df):
        df = df.copy()
        normalized_existing = {
            CustomerDemandImportService.normalize_col(c): c
            for c in df.columns
        }
        rename_map = {}

        for canonical, aliases in CustomerDemandImportService.COLUMN_ALIASES.items():
            for alias in [canonical] + aliases:
                key = CustomerDemandImportService.normalize_col(alias)
                if key in normalized_existing:
                    rename_map[normalized_existing[key]] = canonical
                    break

        df = df.rename(columns=rename_map)

        # 特殊但常見的訂購單表頭：分成「數」與「量」兩欄。
        # 在這類表格中「數」是真正數量，而「量」其實放的是
        # 「包(60箱) / 包(150箱)」等需求單位與箱數資訊。
        # 若已有「數量」但尚未有「單位」，將剩下的「量」欄改為「單位」。
        if "數量" in df.columns and "單位" not in df.columns:
            for col in list(df.columns):
                if CustomerDemandImportService.normalize_col(col) == "量":
                    df = df.rename(columns={col: "單位"})
                    break

        return df

    @staticmethod
    def extract_metadata(file_path):
        try:
            preview = pd.read_excel(file_path, header=None, nrows=15)
            text = "\n".join(
                CustomerDemandImportService.clean(v)
                for v in preview.to_numpy().flatten()
                if CustomerDemandImportService.clean(v)
            )
        except Exception:
            text = ""

        order_no = ""
        purchase_date = ""
        arrival_date = ""
        vendor = ""

        m = re.search(r"(?:訂單號碼|訂單號|採購單號)\s*[:：]?\s*([A-Za-z0-9\-]+)", text)
        if m:
            order_no = m.group(1)

        m = re.search(
            r"(?:訂購日期|訂購日|採購日期)\s*[:：]?\s*((?:20\d{2}|1\d{2})[/-]\d{1,2}[/-]\d{1,2})",
            text,
        )
        if m:
            purchase_date = m.group(1)

        m = re.search(
            r"(?:約交日期|約交日|到貨日期|到貨日|交貨日期)\s*[:：]?\s*((?:20\d{2}|1\d{2})[/-]\d{1,2}[/-]\d{1,2})",
            text,
        )
        if m:
            arrival_date = m.group(1)

        # 元資料在 Excel 常被攤平成單行，因此以已知標籤截斷。
        m = re.search(r"(?:賣方|廠商名稱|供應商)\s*[:：]?\s*([^\n]+)", text)
        if m:
            vendor = re.split(r"電話|傳真|地址|訂單號碼|訂購日期|約交", m.group(1))[0].strip()

        return {
            "採購單號": order_no,
            "採購日期": purchase_date,
            "採購廠商": vendor,
            "到貨日期": arrival_date,
        }

    @staticmethod
    def extract_box_info(quantity, unit_text, packing_text=""):
        qty = pd.to_numeric(quantity, errors="coerce")
        if pd.isna(qty):
            qty = 0.0
        qty = float(qty)

        unit_text = CustomerDemandImportService.clean(unit_text)
        packing_text = CustomerDemandImportService.clean(packing_text)

        boxes = 0.0
        units_per_box = 0.0
        demand_unit = unit_text

        # 例如：包(100箱)、包（150箱）
        m = re.search(r"^([^()（）]+)\s*[（(]\s*([\d,.]+)\s*箱\s*[）)]", unit_text)
        if m:
            demand_unit = CustomerDemandImportService.clean(m.group(1))
            try:
                boxes = float(m.group(2).replace(",", ""))
            except Exception:
                boxes = 0.0

        if boxes > 0 and qty > 0:
            units_per_box = qty / boxes

        # 若單位沒有箱數，從包裝方式抓「1200包/箱」。
        if units_per_box <= 0 and packing_text:
            m = re.search(r"([\d,.]+)\s*[^\s/]+\s*/\s*箱", packing_text)
            if m:
                try:
                    units_per_box = float(m.group(1).replace(",", ""))
                except Exception:
                    units_per_box = 0.0
            if units_per_box > 0 and qty > 0:
                boxes = qty / units_per_box

        return {
            "需求單位": demand_unit,
            "箱數": round(boxes, 4),
            "每箱數量": round(units_per_box, 4),
        }

    @staticmethod
    def split_product_fields(text, existing_code="", existing_spec="", existing_material=""):
        raw = CustomerDemandImportService.clean(text)
        code = CustomerDemandImportService.clean(existing_code)
        spec = CustomerDemandImportService.clean(existing_spec)
        material = CustomerDemandImportService.clean(existing_material)

        if not code:
            candidates = re.findall(
                r"(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9\-/#.]*\d[A-Za-z0-9\-/#.]*)",
                raw,
            )
            if candidates:
                code = candidates[0]

        if not material:
            for keyword in sorted(CustomerDemandImportService.MATERIAL_KEYWORDS, key=len, reverse=True):
                if keyword.upper() in raw.upper():
                    material = keyword
                    break

        # 規格優先使用 Excel 原本的「規格」欄，例如滅菌4支裝、滅菌5片包。
        if not spec:
            patterns = [
                r"滅菌\s*\d+\s*(?:支|片|個|入|包)(?:裝|包|束)?",
                r"(?:無粉|有粉)(?:\s*[A-Za-z0-9]+)?",
                r"\d+\s*(?:支|片|個|入)(?:裝|包|束)",
            ]
            for pattern in patterns:
                m = re.search(pattern, raw, flags=re.IGNORECASE)
                if m:
                    spec = CustomerDemandImportService.clean(m.group(0))
                    break

        size = ""
        size_patterns = [
            r"\d+(?:\.\d+)?[\"吋]?\s*[xX×*]\s*\d+(?:\.\d+)?(?:\s*[xX×*]\s*\d+(?:\.\d+)?)?\s*(?:CM|MM)?",
            r"\d+(?:\.\d+)?\s*(?:CM|MM|吋|\")",
        ]
        for pattern in size_patterns:
            m = re.search(pattern, raw, flags=re.IGNORECASE)
            if m:
                size = CustomerDemandImportService.clean(m.group(0))
                break

        base_weight = ""
        m = re.search(r"\b\d+(?:\.\d+)?\s*G\b", raw, flags=re.IGNORECASE)
        if m:
            base_weight = CustomerDemandImportService.clean(m.group(0)).upper()

        product = ""
        for keyword in sorted(CustomerDemandImportService.PRODUCT_KEYWORDS, key=len, reverse=True):
            if keyword in raw:
                product = keyword
                break

        if not product:
            cleaned = raw
            for part in [code, spec, material, size, base_weight]:
                if part:
                    cleaned = cleaned.replace(part, " ")
            cleaned = re.sub(r"\([^)]*\)", " ", cleaned)
            cleaned = re.sub(r"\b\d+[Pp]\b", " ", cleaned)
            cleaned = re.sub(r"\b\d+['’]?[Ss](?:/\d+)?\b", " ", cleaned)
            cleaned = re.sub(r"[/_]+", " ", cleaned)
            cleaned = re.sub(r"[\"\'`~!@#$%^&*+=|\\:;,.<>?，。；：]+", " ", cleaned)
            cleaned = CustomerDemandImportService.clean(cleaned)
            product = cleaned if re.search(r"[A-Za-z0-9\u4e00-\u9fff]", cleaned) else ""

        return {
            "原始產品編號": code,
            "需求產品名稱": product,
            "規格": spec,
            "材質": material,
            "尺寸": size,
            "基重": base_weight,
        }

    @staticmethod
    def enrich_detail_df(df):
        if df is None or df.empty:
            return df

        df = df.copy()
        if "PDF品名規格" not in df.columns:
            return df

        parsed_rows = []
        for _, row in df.iterrows():
            parsed_rows.append(
                CustomerDemandImportService.split_product_fields(
                    row.get("PDF品名規格", ""),
                    row.get("原始產品編號", ""),
                    row.get("規格", ""),
                    row.get("材質", ""),
                )
            )

        parsed = pd.DataFrame(parsed_rows, index=df.index)
        for col in ["原始產品編號", "需求產品名稱", "規格", "材質", "尺寸", "基重"]:
            if col not in df.columns:
                df[col] = parsed[col]
            else:
                existing = df[col].fillna("").astype(str).str.strip()
                df[col] = df[col].where(existing != "", parsed[col])

        # 箱數與每箱數量。Excel 訂單常用「包(100箱)」。
        box_rows = []
        for _, row in df.iterrows():
            box_rows.append(
                CustomerDemandImportService.extract_box_info(
                    row.get("數量", 0),
                    row.get("單位", ""),
                    row.get("包裝方式", ""),
                )
            )
        box_df = pd.DataFrame(box_rows, index=df.index)
        for col in ["需求單位", "箱數", "每箱數量"]:
            df[col] = box_df[col]

        return df

    @staticmethod
    def apply_product_master_mapping(df, products=None):
        """Excel 有產品編號時，直接用 ERP 產品主檔對應，不再要求 Alias。"""
        if df is None or df.empty:
            return df

        if products is None:
            try:
                from services.product_master_service import ProductMasterService
                products = ProductMasterService.load_products()
            except Exception:
                products = []

        products = products or []
        master_map = {}
        for product in products:
            key = CustomerDemandImportService.normalize_product_no(
                product.get("產品編號", "")
            )
            if key:
                master_map[key] = product

        df = df.copy()
        if "產品編號" not in df.columns:
            df["產品編號"] = ""

        direct_flags = []
        direct_notes = []

        for idx, row in df.iterrows():
            current = CustomerDemandImportService.clean(row.get("產品編號", ""))
            source_code = CustomerDemandImportService.clean(row.get("原始產品編號", ""))
            source_type = CustomerDemandImportService.clean(row.get("來源類型", ""))
            direct = False
            note = ""

            # PDF 已由 Alias 對應的 current 保留；Excel 原始代碼若可命中主檔則優先直接對應。
            if source_type == "Excel" and source_code:
                key = CustomerDemandImportService.normalize_product_no(source_code)
                product = master_map.get(key)
                if product is not None:
                    official_no = CustomerDemandImportService.clean(product.get("產品編號", ""))
                    df.at[idx, "產品編號"] = official_no
                    direct = True
                    note = "Excel產品編號直接對應產品主檔"

                    # 拆解用的產品名稱若空白，可由主檔補足。
                    parsed_name = CustomerDemandImportService.clean(row.get("需求產品名稱", ""))
                    if (
                        not parsed_name
                        or not re.search(r"[A-Za-z0-9\u4e00-\u9fff]", parsed_name)
                    ):
                        df.at[idx, "需求產品名稱"] = CustomerDemandImportService.clean(
                            product.get("產品名稱", "")
                        )
                    if not CustomerDemandImportService.clean(row.get("材質", "")):
                        master_material = CustomerDemandImportService.clean(product.get("材質", ""))
                        if master_material:
                            df.at[idx, "材質"] = master_material
                elif not current:
                    df.at[idx, "產品編號"] = ""

            direct_flags.append(direct)
            direct_notes.append(note)

        df["Excel直接對應"] = direct_flags
        df["Excel對應說明"] = direct_notes
        return df

    # =========================================================
    # V4.2：Excel 三層讀取
    # 1. 標準欄名
    # 2. 自動尋找真正表頭（跨工作表）
    # 3. 無可靠表頭時，依欄內容語意推測
    # =========================================================

    @staticmethod
    def _read_sheet_raw(file_path, sheet_name):
        return pd.read_excel(file_path, sheet_name=sheet_name, header=None)

    @staticmethod
    def _header_score(row_values):
        cells = [CustomerDemandImportService.normalize_col(v) for v in row_values]
        score = 0
        hits = set()
        for canonical, aliases in CustomerDemandImportService.COLUMN_ALIASES.items():
            candidates = [canonical] + list(aliases)
            found = False
            for alias in candidates:
                a = CustomerDemandImportService.normalize_col(alias)
                if not a:
                    continue
                if any(c == a or (len(a) >= 2 and a in c) for c in cells if c):
                    found = True
                    break
            if found:
                hits.add(canonical)
                score += 2

        if "PDF品名規格" in hits:
            score += 6
        if "數量" in hits:
            score += 6
        if "原始產品編號" in hits:
            score += 4
        if "單位" in hits:
            score += 2
        if "到貨日期" in hits:
            score += 2
        return score, hits

    @staticmethod
    def _detect_header_in_raw(raw, max_rows=120):
        if raw is None or raw.empty:
            return None, 0, set()
        best_idx = None
        best_score = -1
        best_hits = set()
        for idx in range(min(len(raw), max_rows)):
            score, hits = CustomerDemandImportService._header_score(raw.iloc[idx].tolist())
            if score > best_score:
                best_idx = idx
                best_score = score
                best_hits = hits
        # 只要品名+數量，或產品編號+數量，就接受。
        valid = (
            ("PDF品名規格" in best_hits and "數量" in best_hits)
            or ("原始產品編號" in best_hits and "數量" in best_hits)
        )
        if not valid:
            return None, best_score, best_hits
        return int(best_idx), best_score, best_hits

    @staticmethod
    def _is_product_code(value):
        text = CustomerDemandImportService.clean(value).upper().replace(" ", "")
        if not text or len(text) < 3:
            return False
        if CustomerDemandImportService.extract_roc_like_date(text):
            return False
        return bool(re.fullmatch(r"(?=.*[A-Z])(?=.*\d)[A-Z0-9][A-Z0-9\-/#.()]{2,30}", text))

    @staticmethod
    def extract_roc_like_date(value):
        text = CustomerDemandImportService.clean(value)
        m = re.search(r"(?:20\d{2}|1\d{2})[/-]\d{1,2}[/-]\d{1,2}", text)
        return m.group(0) if m else ""

    @staticmethod
    def _is_unit_text(value):
        text = CustomerDemandImportService.clean(value)
        if not text:
            return False
        units = ["包", "盒", "箱", "雙", "支", "片", "捲", "卷", "條", "本", "打", "KG", "公斤", "瓶", "袋", "套", "個", "組", "桶", "台"]
        if any(text.upper() == u.upper() for u in units):
            return True
        return bool(re.match(r"^(?:包|盒|箱|雙|支|片|捲|卷|條|本|打|KG|公斤|瓶|袋|套|個|組)(?:\s*[（(].*箱.*[）)])?$", text, re.I))

    @staticmethod
    def _semantic_column_scores(raw):
        scores = {}
        if raw is None or raw.empty:
            return scores
        for col in raw.columns:
            values = [CustomerDemandImportService.clean(v) for v in raw[col].tolist()]
            values = [v for v in values if v and v.lower() not in {"nan", "none"}]
            sample = values[:200]
            if not sample:
                continue
            n = len(sample)
            numeric = 0
            code = 0
            unit = 0
            date = 0
            textish = 0
            productish = 0
            for v in sample:
                try:
                    num = pd.to_numeric(str(v).replace(",", ""), errors="coerce")
                    if not pd.isna(num):
                        numeric += 1
                except Exception:
                    pass
                if CustomerDemandImportService._is_product_code(v):
                    code += 1
                if CustomerDemandImportService._is_unit_text(v):
                    unit += 1
                if CustomerDemandImportService.extract_roc_like_date(v):
                    date += 1
                if re.search(r"[A-Za-z\u4e00-\u9fff]", v):
                    textish += 1
                if any(k in v for k in CustomerDemandImportService.PRODUCT_KEYWORDS + CustomerDemandImportService.MATERIAL_KEYWORDS):
                    productish += 1
            scores[col] = {
                "numeric": numeric / n,
                "code": code / n,
                "unit": unit / n,
                "date": date / n,
                "text": textish / n,
                "product": productish / n,
                "count": n,
            }
        return scores

    @staticmethod
    def _semantic_table(raw):
        """沒有可靠表頭時，以欄內容建立最小可用需求表。"""
        if raw is None or raw.empty:
            return None, ""

        # 先移除完全空白列/欄。
        work = raw.copy().dropna(how="all").dropna(axis=1, how="all")
        if work.empty or len(work.columns) < 2:
            return None, ""

        scores = CustomerDemandImportService._semantic_column_scores(work)
        if not scores:
            return None, ""

        cols = list(work.columns)
        code_col = max(cols, key=lambda c: scores.get(c, {}).get("code", 0))
        unit_col = max(cols, key=lambda c: scores.get(c, {}).get("unit", 0))
        date_col = max(cols, key=lambda c: scores.get(c, {}).get("date", 0))

        # 數量：偏好高 numeric ratio，但排除日期欄；若多欄都是數值，選中位數較大的欄作需求量。
        numeric_candidates = []
        for c in cols:
            sc = scores.get(c, {})
            if c == date_col or sc.get("numeric", 0) < 0.35:
                continue
            nums = pd.to_numeric(work[c].astype(str).str.replace(",", "", regex=False), errors="coerce").dropna()
            median = float(nums.median()) if not nums.empty else 0.0
            numeric_candidates.append((sc.get("numeric", 0), median, c))
        qty_col = None
        if numeric_candidates:
            # 數量通常比單價/序號大；先看比例，再看中位數。
            numeric_candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
            qty_col = numeric_candidates[0][2]

        # 品名：排除已選欄位，偏好含產品詞、文字比例高的欄。
        excluded = {code_col, unit_col, date_col, qty_col}
        name_candidates = []
        for c in cols:
            if c in excluded:
                continue
            sc = scores.get(c, {})
            name_candidates.append((sc.get("product", 0) * 3 + sc.get("text", 0), c))
        name_col = max(name_candidates, default=(0, None))[1]

        # 若產品代碼比例非常低，視為不存在。
        if scores.get(code_col, {}).get("code", 0) < 0.15:
            code_col = None
        if scores.get(unit_col, {}).get("unit", 0) < 0.15:
            unit_col = None
        if scores.get(date_col, {}).get("date", 0) < 0.10:
            date_col = None

        # 最少要有數量，以及品名或產品編號之一。
        if qty_col is None or (name_col is None and code_col is None):
            return None, ""

        out = pd.DataFrame(index=work.index)
        if code_col is not None:
            out["原始產品編號"] = work[code_col]
        if name_col is not None:
            out["PDF品名規格"] = work[name_col]
        elif code_col is not None:
            out["PDF品名規格"] = work[code_col]
        out["數量"] = work[qty_col]
        if unit_col is not None:
            out["單位"] = work[unit_col]
        if date_col is not None:
            out["到貨日期"] = work[date_col]

        # 過濾表頭/合計/空列。
        out["PDF品名規格"] = out["PDF品名規格"].apply(CustomerDemandImportService.clean)
        out = out[out["PDF品名規格"] != ""].copy()
        out["數量"] = pd.to_numeric(out["數量"].astype(str).str.replace(",", "", regex=False), errors="coerce")
        out = out[out["數量"].notna() & (out["數量"] > 0)].copy()
        bad = out["PDF品名規格"].astype(str).str.contains("合計|總計|小計|品名|產品名稱", regex=True, na=False)
        out = out[~bad].copy()

        if out.empty:
            return None, ""
        return out, "內容語意判定"

    @staticmethod
    def _load_best_excel_table(file_path):
        """回傳 (df, 讀取方式, sheet_name, header_row)。"""
        xls = pd.ExcelFile(file_path)
        diagnostics = []

        # 第一、二層：每個工作表找真正表頭。
        for sheet in xls.sheet_names:
            try:
                raw = CustomerDemandImportService._read_sheet_raw(file_path, sheet)
            except Exception as e:
                diagnostics.append(f"{sheet}: 無法讀取({e})")
                continue
            header_row, score, hits = CustomerDemandImportService._detect_header_in_raw(raw)
            if header_row is not None:
                try:
                    df = pd.read_excel(file_path, sheet_name=sheet, header=header_row)
                    df = CustomerDemandImportService.normalize_columns(df)
                    # 若有正式產品代碼但沒有品名，仍可先用代碼當品名候選。
                    if "PDF品名規格" not in df.columns and "原始產品編號" in df.columns:
                        df["PDF品名規格"] = df["原始產品編號"]
                    if "數量" in df.columns and "PDF品名規格" in df.columns:
                        method = "標準欄名" if header_row == 0 else "自動表頭偵測"
                        return df, method, sheet, header_row
                except Exception as e:
                    diagnostics.append(f"{sheet}: 表頭{header_row}重讀失敗({e})")

        # 第三層：內容語意推測。
        best = None
        best_count = 0
        for sheet in xls.sheet_names:
            try:
                raw = CustomerDemandImportService._read_sheet_raw(file_path, sheet)
                inferred, method = CustomerDemandImportService._semantic_table(raw)
                if inferred is not None and len(inferred) > best_count:
                    best = (inferred, method, sheet, None)
                    best_count = len(inferred)
            except Exception as e:
                diagnostics.append(f"{sheet}: 語意判定失敗({e})")
        if best is not None:
            return best

        detail = "\n".join(diagnostics[-8:])
        raise Exception(
            "Excel 已嘗試三種方式仍無法建立客戶需求表：\n"
            "① 標準欄名 ② 自動表頭偵測 ③ 內容語意判定。\n"
            + ("\n診斷：\n" + detail if detail else "")
        )

    @staticmethod
    def read_excel(file_path):
        df, read_method, sheet_name, header_row = CustomerDemandImportService._load_best_excel_table(file_path)
        df = CustomerDemandImportService.normalize_columns(df)
        metadata = CustomerDemandImportService.extract_metadata(file_path)

        if "PDF品名規格" not in df.columns and "原始產品編號" in df.columns:
            df["PDF品名規格"] = df["原始產品編號"]

        if "PDF品名規格" not in df.columns:
            raise Exception(
                "Excel 三層讀取已完成，但仍找不到品名/品名規格欄位。\n"
                f"讀取方式：{read_method}\n工作表：{sheet_name}\n目前欄位：{list(df.columns)}"
            )

        if "數量" not in df.columns:
            raise Exception(
                "Excel 三層讀取已完成，但仍沒有可辨識的需求數量欄位。\n"
                f"讀取方式：{read_method}\n工作表：{sheet_name}\n目前欄位：{list(df.columns)}"
            )

        df = df[df["PDF品名規格"].notna()].copy()
        df["PDF品名規格"] = df["PDF品名規格"].apply(CustomerDemandImportService.clean)
        df = df[df["PDF品名規格"] != ""].copy()

        if "原始產品編號" not in df.columns:
            df["原始產品編號"] = ""

        defaults = {
            "驗證狀態": "🟢 正常",
            "驗證問題": "",
            "自動修正": f"Excel匯入/{read_method}",
            "採購單號": metadata.get("採購單號", ""),
            "採購日期": metadata.get("採購日期", ""),
            "採購廠商": metadata.get("採購廠商", ""),
            "客戶": "",
            "客戶訂號": "",
            "出貨備註": "",
            "單位": "",
            "到貨日期": metadata.get("到貨日期", ""),
            "配送類型": "客戶直送",
            "配送地址": "",
            "配送內容": "",
        }
        for col, default in defaults.items():
            if col not in df.columns:
                df[col] = default
            else:
                df[col] = df[col].fillna(default)
                if default and col in {"採購單號", "採購日期", "採購廠商", "到貨日期"}:
                    empty_mask = df[col].astype(str).str.strip() == ""
                    df.loc[empty_mask, col] = default

        # 數量支援千分位與 Excel 數值。
        df["數量"] = pd.to_numeric(
            df["數量"].astype(str).str.replace(",", "", regex=False),
            errors="coerce"
        ).fillna(0)
        df = df[df["數量"] > 0].copy()

        for numeric_col in ["單價", "總價", "體積CBM"]:
            if numeric_col in df.columns:
                df[numeric_col] = pd.to_numeric(
                    df[numeric_col].astype(str).str.replace(",", "", regex=False),
                    errors="coerce"
                ).fillna(0)

        # 偵測幣別，不再重新用錯誤 header 讀一次。
        header_text = " ".join(str(c) for c in df.columns)
        default_currency = "USD" if "USD" in header_text.upper() else ""
        if "幣別" not in df.columns:
            df["幣別"] = default_currency

        df["來源類型"] = "Excel"
        df["來源檔案"] = os.path.basename(file_path)
        df["Excel讀取方式"] = read_method
        df["Excel工作表"] = str(sheet_name)
        df["Excel表頭列"] = "" if header_row is None else int(header_row) + 1

        df = CustomerDemandImportService.enrich_detail_df(df)
        df = CustomerDemandImportService.apply_product_master_mapping(df)

        if df.empty:
            raise Exception(
                f"Excel 已讀取成功（{read_method}），但過濾後沒有大於 0 的需求資料。"
            )

        return {
            "detail_df": df.reset_index(drop=True),
            "pages": 0,
            "page_errors": [],
            "no_table_pages": [],
            "source_file": os.path.basename(file_path),
            "read_method": read_method,
            "sheet_name": str(sheet_name),
            "header_row": header_row,
        }

