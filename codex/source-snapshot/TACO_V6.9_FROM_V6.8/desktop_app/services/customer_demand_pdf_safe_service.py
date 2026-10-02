import os

import pandas as pd
import pymupdf

from services.product_alias_service import ProductAliasService
from services.customer_demand_service import CustomerDemandService


class CustomerDemandPdfSafeService:
    """V4.2 PDF 安全讀取器。

    正常 read_pdf() 若因單頁特殊內容中斷，改逐頁呼叫 parse_page()；
    單頁錯誤只記錄，不讓整份 PDF 失敗。
    """

    @staticmethod
    def read_pdf(file_path):
        document = pymupdf.open(file_path)
        all_rows = []
        page_errors = []
        skipped_pages = []
        total_pages = len(document)

        try:
            for page_index in range(total_pages):
                page_number = page_index + 1
                try:
                    page = document[page_index]
                    parsed = CustomerDemandService.parse_page(page, page_number)
                    if isinstance(parsed, dict):
                        rows = parsed.get("rows", []) or []
                        reason = parsed.get("reason", "")
                    elif isinstance(parsed, list):
                        rows = parsed
                        reason = ""
                    else:
                        rows = []
                        reason = "未知解析結果"

                    if rows:
                        all_rows.extend(rows)
                    else:
                        skipped_pages.append({"page": page_number, "reason": reason or "本頁無需求資料"})
                except Exception as exc:
                    page_errors.append({"page": page_number, "error": str(exc)})
        finally:
            document.close()

        if not all_rows:
            detail = "\n".join(
                f"第 {item['page']} 頁：{item['error']}" for item in page_errors[:10]
            )
            raise Exception(
                "PDF 安全模式已逐頁嘗試，但仍沒有解析到需求資料。"
                + ("\n\n頁面錯誤：\n" + detail if detail else "")
            )

        df = pd.DataFrame(all_rows)

        dedupe_columns = [
            "PDF頁碼", "採購單號", "PDF品名規格", "數量", "到貨日期", "配送內容", "客戶訂號"
        ]
        dedupe_columns = [c for c in dedupe_columns if c in df.columns]
        if dedupe_columns:
            df = df.drop_duplicates(subset=dedupe_columns).reset_index(drop=True)

        try:
            df = ProductAliasService.apply_aliases(df)
        except Exception:
            pass

        try:
            if hasattr(CustomerDemandService, "attach_product_master"):
                df = CustomerDemandService.attach_product_master(df)
        except Exception:
            pass

        return {
            "detail_df": df,
            "pages": total_pages,
            "page_errors": page_errors,
            "no_table_pages": skipped_pages,
            "source_file": os.path.basename(file_path),
            "safe_mode": True,
        }
