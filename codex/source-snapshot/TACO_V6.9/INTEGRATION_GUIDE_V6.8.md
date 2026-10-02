# V6.8 → V6.9 正式併版指南

1. 從已驗證的 V6.8 原始專案建立新分支；不要由本參考包反向重建財務／庫存模組。
2. 將 `domain.py` 的 ScanWorkflow、AllocationPolicy、ReceiptBusinessRules 接到 V6.8 Barcode Resolver 與 Mapping Center。
3. 將 V6.8 原有 InventoryService 實作為 `commit_receipt(idempotency_key, session_id, order_no, allocations, actor_id)`；資料庫需對 idempotency key 建唯一約束。
4. 將 `IntegrationEventStore` 接至既有 `C:\ProgramData\TACO\integration.db`。初始化只允許 additive migration，先備份後驗證 Mapping profiles 與 sync queue 筆數不變。
5. 把 ScannerCenter 嵌入原智慧掃碼頁，不另開第二套庫存資料；保留 V6.8 共用 Page Header 與 Theme，再套用大型掃碼區尺寸。
6. 將 `UpdateClient` 接到系統設定的版本更新頁。Ed25519 公鑰編入客戶端；manifest URL 只能由受保護設定切換，Stable 客戶不可任意輸入。
7. TACO 主程式只下載與驗證；實際 Program Files 替換必須由獨立 `TACOUpdater.exe` 在主程式關閉後執行。
8. 更新包來源必須是原 Windows Build 的完整 `dist/TACO`，不可下載或覆蓋單一 `.py`。
9. 合併後先跑 V6.8 原 136 項，再跑本版 35 項，最後做兩台乾淨 Windows VM：正常升級與故障回復。
10. Build 產物版本、`desktop_app/VERSION`、`BUILD_VERSION.txt`、PyInstaller version info、Inno Setup AppVersion 與檔名必須全部為 `6.9.0`。

## 不可破壞項目

- License 2.0 驗章、撤銷、裝置限制、72h offline grace、clock rollback、readonly。
- `C:\ProgramData\TACO` 與 SafeStorage 原子寫入。
- `integration.db` WAL、Mapping、sync queue、scan events 與 UUID／冪等語意。
- 原 Service Permission、Business Rule、Audit、Backup、財務與庫存資料契約。
- Server 私鑰、更新私鑰、License DB 永不進入桌面 ZIP 或 Setup。
