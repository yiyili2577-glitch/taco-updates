"""正航 ERP SQL Server 唯讀連線服務。

取代「手動匯出 Excel 再匯入」的步驟：直接用唯讀 SQL 帳號查詢正航資料庫，
轉換成 TACO 既有的欄位格式，然後餵給既有的 WarehouseService /
CustomerDemandStoreService，讓後續的採購建議、儀表板等功能完全不用改，
跟現在 Excel 匯入的結果是同一條資料管線。

=====================================================================
安全設計（務必先讀）
=====================================================================
1. **一定要用唯讀帳號**：這裡的每一個查詢都會先檢查是不是「純 SELECT」，
   不是的話會直接拒絕執行（_assert_select_only）。但這只是應用程式層的
   最後一道防線，真正的保護還是要靠資料庫那邊只給這個帳號 SELECT 權限，
   不要給 INSERT / UPDATE / DELETE。
2. **密碼不落地**：這個模組完全不會把密碼寫進任何檔案。密碼只在呼叫當下
   當作參數傳進來，用完即丟（Python 變數離開作用域後由記憶體回收）。
3. **SQL 查詢文字放在設定檔，不寫死在程式碼裡**：因為每家公司的正航資料庫
   結構不一樣，這裡不猜測實際的資料表 / 欄位名稱。實際的查詢語法和欄位對照
   由 data/sql_import_mapping.json 設定，出貨前你們的 IT 或熟悉正航資料庫
   結構的人需要自行填入。預設值是「永遠回傳 0 筆」的安全查詢，不會誤匯入
   垃圾資料。

=====================================================================
使用方式
=====================================================================
    from services.erp_sql_connector_service import ErpSqlConnectorService as SqlConn

    # 1) 匯入前先預覽，確認欄位、資料看起來對
    preview = SqlConn.preview("inventory", password="...", limit=20)

    # 2) 確認沒問題後正式匯入（等同於原本「選擇 Excel」+「儲存三倉庫存」兩步）
    result = SqlConn.import_inventory_from_sql(password="...")

    # 客戶需求同理
    preview = SqlConn.preview("customer_demand", password="...", limit=20)
    result = SqlConn.import_customer_demand_from_sql(password="...")
"""
import os
import re
from copy import deepcopy

import pandas as pd

from services.app_paths import AppPaths
from services.safe_storage import SafeStorage, get_logger
from services.system_settings_service import SystemSettingsService
from services.warehouse_service import WarehouseService
from services.dashboard_data_service import DashboardDataService
from services.customer_demand_store_service import CustomerDemandStoreService
from services.fulfillment_service import FulfillmentService


class SqlImportNotConfiguredError(Exception):
    """data/sql_import_mapping.json 裡的查詢還是預設的 TODO 佔位內容，尚未設定。"""


class UnsafeSqlError(Exception):
    """偵測到查詢文字不是單一的 SELECT 陳述式，為安全起見拒絕執行。"""


# 出現這些關鍵字一律視為不安全（不分大小寫）。即使資料庫帳號本身已經是唯讀，
# 這裡還是要擋，因為帳號權限設定錯誤、或未來有人不小心改用了有寫入權限的
# 帳號時，這一層還能防止程式意外寫壞正航的正式資料。
_FORBIDDEN_KEYWORDS = [
    "insert", "update", "delete", "drop", "alter", "truncate", "merge",
    "exec", "execute", "create", "grant", "revoke", "sp_", "xp_",
]

_TODO_MARKER = "TODO"


class ErpSqlConnectorService:
    BASE_DIR = str(AppPaths.install_dir())
    DATA_DIR = str(AppPaths.data_dir())
    MAPPING_FILE = os.path.join(DATA_DIR, "sql_import_mapping.json")

    # 兩種用途各自的目標欄位（匯入完成後的 DataFrame 必須至少有這些欄位，
    # 對應到 WarehouseService / CustomerDemandService 既有邏輯所需要的格式）。
    TARGET_COLUMNS = {
        "inventory": ["產品編號", "產品名稱", "平均月耗用量", "目前庫存", "預計到貨"],
        "customer_demand": [
            "產品編號", "產品名稱", "品項分類", "數量", "配送類型", "到貨日期",
            "客戶", "客戶訂號", "採購單號", "採購日期", "來源檔案",
        ],
    }

    DEFAULT_MAPPING = {
        "_說明": (
            "這個檔案設定「怎麼從正航 SQL Server 查詢資料、查出來的欄位怎麼對應到 "
            "TACO 需要的欄位」。出貨前請依實際的正航資料庫結構修改 inventory 和 "
            "customer_demand 這兩段的 sql 與 column_map，修改前系統會拒絕真正匯入"
            "（只允許預覽），避免誤用尚未設定好的查詢。"
        ),
        "inventory": {
            "_說明": (
                "TODO：請改成能查出目前庫存的 SQL。column_map 的 key 是你 SQL "
                "查詢結果的欄位名稱，value 是 TACO 需要的欄位名稱，兩者不同名"
                "才需要寫在這裡；同名的欄位可以省略。"
            ),
            "sql": "SELECT NULL AS 產品編號 WHERE 1 = 0  -- TODO: 換成實際查詢正航庫存的 SQL",
            "column_map": {
                "產品編號": "產品編號",
                "產品名稱": "產品名稱",
                "平均月耗用量": "平均月耗用量",
                "目前庫存": "目前庫存",
                "預計到貨": "預計到貨",
            },
        },
        "customer_demand": {
            "_說明": "TODO：請改成能查出客戶需求明細的 SQL（一筆訂單明細一列）。",
            "sql": "SELECT NULL AS 產品編號 WHERE 1 = 0  -- TODO: 換成實際查詢正航客戶需求的 SQL",
            "column_map": {
                "產品編號": "產品編號",
                "產品名稱": "產品名稱",
                "品項分類": "品項分類",
                "數量": "數量",
                "配送類型": "配送類型",
                "到貨日期": "到貨日期",
                "客戶": "客戶",
                "客戶訂號": "客戶訂號",
                "採購單號": "採購單號",
                "採購日期": "採購日期",
            },
        },
    }

    # =====================================================
    # 設定檔（SQL 查詢文字 + 欄位對照）
    # =====================================================

    @staticmethod
    def _ensure():
        os.makedirs(ErpSqlConnectorService.DATA_DIR, exist_ok=True)

    @staticmethod
    def load_mapping():
        ErpSqlConnectorService._ensure()
        if not os.path.exists(ErpSqlConnectorService.MAPPING_FILE):
            SafeStorage.atomic_write_json(ErpSqlConnectorService.MAPPING_FILE, ErpSqlConnectorService.DEFAULT_MAPPING)
            return deepcopy(ErpSqlConnectorService.DEFAULT_MAPPING)
        data = SafeStorage.safe_read_json(ErpSqlConnectorService.MAPPING_FILE, default=None)
        if not isinstance(data, dict):
            return deepcopy(ErpSqlConnectorService.DEFAULT_MAPPING)
        return data

    @staticmethod
    def save_mapping(mapping):
        ErpSqlConnectorService._ensure()
        SafeStorage.atomic_write_json(ErpSqlConnectorService.MAPPING_FILE, mapping)

    @staticmethod
    def _purpose_config(purpose):
        mapping = ErpSqlConnectorService.load_mapping()
        config = mapping.get(purpose)
        if not isinstance(config, dict):
            raise ValueError(f"data/sql_import_mapping.json 裡找不到「{purpose}」這個設定區塊。")
        return config

    # =====================================================
    # 安全檢查
    # =====================================================

    @staticmethod
    def _assert_select_only(sql_text):
        # 先把 -- 單行註解拿掉，只留下真正的 SQL 內容來檢查，避免有人把
        # 危險關鍵字藏在註解裡誤導這個檢查（雖然目前只是防呆，不是防駭）。
        without_comments = re.sub(r"--.*", "", sql_text)
        stripped = without_comments.strip().rstrip(";").strip()
        if not stripped:
            raise UnsafeSqlError("SQL 查詢是空的。")
        if not re.match(r"(?is)^\s*(with\b.+)?select\b", stripped):
            raise UnsafeSqlError("只允許 SELECT 查詢（可以是 WITH ... SELECT 的 CTE），偵測到其他語法。")
        if ";" in stripped:
            raise UnsafeSqlError("不允許一次執行多個 SQL 陳述式（偵測到分號）。")
        lowered = stripped.lower()
        for keyword in _FORBIDDEN_KEYWORDS:
            if re.search(r"\b" + re.escape(keyword) + r"\b", lowered):
                raise UnsafeSqlError(f"偵測到不允許的關鍵字「{keyword}」，為安全起見拒絕執行。")

    @staticmethod
    def _assert_configured(config, purpose):
        sql_text = str(config.get("sql", ""))
        if _TODO_MARKER in sql_text:
            raise SqlImportNotConfiguredError(
                f"「{purpose}」的 SQL 查詢還沒有設定（data/sql_import_mapping.json 裡還是預設的 TODO），"
                "請先請 IT 或熟悉正航資料庫的人填入實際查詢語法。"
            )

    # =====================================================
    # 連線字串
    # =====================================================

    @staticmethod
    def build_connection_string(conn_settings, password):
        driver = str(conn_settings.get("driver", "ODBC Driver 18 for SQL Server")).strip()
        server = str(conn_settings.get("server", "")).strip()
        database = str(conn_settings.get("database", "")).strip()
        auth_type = str(conn_settings.get("auth_type", "SQL Server 驗證")).strip()
        if not server or not database:
            raise ValueError("尚未設定 SQL Server 位址或 Database 名稱，請先到系統設定的連線資料分頁填寫。")
        base = f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};TrustServerCertificate=yes;"
        # ApplicationIntent=ReadOnly 在連到 Always On 可讀取的次要節點時會生效；
        # 對一般單機 SQL Server 沒有實質作用，但加上去無害，也是一個明確的意圖標記。
        base += "ApplicationIntent=ReadOnly;"
        if auth_type == "Windows 驗證":
            return base + "Trusted_Connection=yes;"
        username = str(conn_settings.get("username", "")).strip()
        return base + f"UID={username};PWD={password};"

    # =====================================================
    # 執行查詢
    # =====================================================

    @staticmethod
    def _connect(password, timeout=None):
        try:
            import pyodbc  # 延遲匯入：只有真的要用 SQL Server 模式時才需要安裝這個套件。
        except ImportError as exc:
            raise RuntimeError(
                "找不到 pyodbc 套件，請先安裝（pip install pyodbc）並確認已安裝對應版本的 "
                "ODBC Driver for SQL Server。"
            ) from exc
        settings = SystemSettingsService.load().get("connection", {})
        conn_str = ErpSqlConnectorService.build_connection_string(settings, password)
        conn_timeout = int(timeout if timeout is not None else settings.get("timeout", 5) or 5)
        return pyodbc.connect(conn_str, timeout=conn_timeout)

    @staticmethod
    def _run_select(sql_text, password, row_limit=None):
        ErpSqlConnectorService._assert_select_only(sql_text)
        query = sql_text
        if row_limit:
            # 用子查詢包一層 TOP N，不修改原始查詢的邏輯，只限制回傳筆數，用於預覽。
            query = f"SELECT TOP {int(row_limit)} * FROM ({sql_text.rstrip(';')}) AS _taco_preview"
        conn = ErpSqlConnectorService._connect(password)
        try:
            cursor = conn.cursor()
            cursor.execute(query)
            columns = [d[0] for d in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            data = [dict(zip(columns, row)) for row in rows]
            return columns, data
        finally:
            conn.close()

    @staticmethod
    def _apply_column_map(records, column_map, target_columns):
        """把 SQL 查出來的欄位名稱改成 TACO 需要的欄位名稱，缺少的目標欄位補空值。"""
        renamed = []
        for record in records:
            mapped = {}
            for source_col, value in record.items():
                target_col = column_map.get(source_col, source_col)
                mapped[target_col] = value
            renamed.append(mapped)
        df = pd.DataFrame(renamed)
        for col in target_columns:
            if col not in df.columns:
                df[col] = ""
        return df

    # =====================================================
    # 對外主要功能
    # =====================================================

    @staticmethod
    def preview(purpose, password, limit=20):
        """預覽查詢結果，不會寫入任何 TACO 資料，只是給使用者確認用的。"""
        config = ErpSqlConnectorService._purpose_config(purpose)
        ErpSqlConnectorService._assert_configured(config, purpose)
        sql_text = str(config.get("sql", ""))
        columns, rows = ErpSqlConnectorService._run_select(sql_text, password, row_limit=limit)
        return {"columns": columns, "rows": rows, "row_count": len(rows)}

    @staticmethod
    def fetch_mapped_dataframe(purpose, password):
        config = ErpSqlConnectorService._purpose_config(purpose)
        ErpSqlConnectorService._assert_configured(config, purpose)
        sql_text = str(config.get("sql", ""))
        column_map = config.get("column_map", {}) or {}
        target_columns = ErpSqlConnectorService.TARGET_COLUMNS.get(purpose, [])
        _, rows = ErpSqlConnectorService._run_select(sql_text, password)
        return ErpSqlConnectorService._apply_column_map(rows, column_map, target_columns)

    @staticmethod
    def import_inventory_from_sql(password):
        """等同於原本「選擇正航 Excel」+「儲存三倉庫存」兩個步驟，資料來源換成 SQL。"""
        df = ErpSqlConnectorService.fetch_mapped_dataframe("inventory", password)
        if df is None or df.empty:
            return {"count": 0, "df": df}
        if "產品編號" not in df.columns:
            raise ValueError("SQL 查詢結果沒有「產品編號」欄位，請檢查 column_map 設定。")
        df = df[df["產品編號"].astype(str).str.strip() != ""].copy()
        for numeric_col in ["平均月耗用量", "目前庫存", "預計到貨"]:
            df[numeric_col] = pd.to_numeric(df[numeric_col], errors="coerce").fillna(0)

        df = WarehouseService.enrich_dataframe(df, initialize_from_current=True)
        # 跟既有 Excel 匯入流程一致：三倉庫存合計才是後續採購建議真正採用的「目前庫存」。
        df["目前庫存"] = df["三倉庫存合計"]
        count = WarehouseService.save_from_dataframe(df)
        DashboardDataService.save_inventory_snapshot(df, source_file="SQL Server 直接匯入")
        get_logger().info("SQL 匯入庫存完成，共 %d 個產品。", count)
        return {"count": count, "df": df}

    @staticmethod
    def import_customer_demand_from_sql(password):
        """等同於原本 PDF / Excel 匯入客戶需求的最後一步，資料來源換成 SQL。"""
        detail_df = ErpSqlConnectorService.fetch_mapped_dataframe("customer_demand", password)
        if detail_df is None or detail_df.empty:
            return {"count": 0, "summary_df": pd.DataFrame(), "detail_df": detail_df}
        if "產品編號" not in detail_df.columns:
            raise ValueError("SQL 查詢結果沒有「產品編號」欄位，請檢查 column_map 設定。")

        detail_df["數量"] = pd.to_numeric(detail_df.get("數量", 0), errors="coerce").fillna(0)
        detail_df["來源類型"] = "SQL"
        detail_df["來源檔案"] = "SQL Server 直接匯入"

        # 從這裡開始完全比照 ui/customer_demand_page.py 既有流程（rebuild_all 的最後幾步），
        # 確保 SQL 匯入跟 PDF / Excel 匯入產生完全一致的彙總與履約分流結果。
        summary_df = CustomerDemandServiceProxy.summarize_demand(detail_df)
        fulfillment_summary = FulfillmentService.summarize(detail_df)
        if summary_df is not None and not summary_df.empty and fulfillment_summary is not None and not fulfillment_summary.empty:
            summary_df = summary_df.merge(fulfillment_summary, on="產品編號", how="left")
            for col in fulfillment_summary.columns:
                if col != "產品編號" and col in summary_df.columns:
                    summary_df[col] = pd.to_numeric(summary_df[col], errors="coerce").fillna(0)

        CustomerDemandStoreService.save_snapshot(summary_df, detail_df, source_file="SQL Server 直接匯入")
        get_logger().info("SQL 匯入客戶需求完成，共 %d 筆明細。", len(detail_df))
        return {"count": len(detail_df), "summary_df": summary_df, "detail_df": detail_df}


class CustomerDemandServiceProxy:
    """延遲匯入 CustomerDemandService（3500+ 行的大檔案），避免這個連線模組
    一被 import 就強制載入整個客戶需求模組，減少不必要的耦合與載入時間。"""

    @staticmethod
    def summarize_demand(detail_df):
        from services.customer_demand_service import CustomerDemandService
        return CustomerDemandService.summarize_demand(detail_df)
