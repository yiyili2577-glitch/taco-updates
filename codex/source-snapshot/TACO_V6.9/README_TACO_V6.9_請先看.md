# TACO V6.9｜安全自動更新與智慧掃碼整合版

版本 `6.9.0`；Integration Schema `2`；設計基底為 TACO V6.6／V6.8 的安全契約。

## 先說明交付邊界

本工作區的 `sources/` 是空的，沒有先前 V6.8 的 136 項測試原始專案或 Windows Build。因此這份 ZIP 是**完整、可執行、可測試的 V6.9 更新／掃碼整合套件**，不是已合併財務 22 頁籤與所有舊模組的客戶端 Setup.exe。不得把它直接覆蓋正式客戶端。

取得 V6.8 原始專案後，依 `INTEGRATION_GUIDE_V6.8.md` 將本套件的 service 與 UI 元件併入，再跑 V6.8 原有 136 項＋本版 35 項測試，才能標記為正式安裝版。

## 已完成範圍

- 安全更新：嚴格 canonical manifest、Ed25519、SHA-256、HTTPS-only、大小限制、版本／通道／維護權檢查。
- 安全解壓：阻擋 Zip Slip、Windows 反斜線逸出、絕對路徑、磁碟機路徑、大小寫重複檔、符號連結與解壓炸彈。
- 離線更新器：staging、版本標記、安裝目錄備份、原子替換、健康檢查與失敗回復；禁止 ProgramData 與安裝目錄互相包含。
- 版本發佈工具：由外部 Ed25519 私鑰產生 `manifest.json` 與 `manifest.sig`；私鑰不能位於輸出目錄。
- 智慧掃碼：大型 30pt 輸入區、24px 垂直留白、固定焦點、四步驟導引、大型可捲動多品項表格。
- 流程：`掃單號 → 連續掃多個貨品 → 掃容器／儲位 → 安全覆核 → 入庫`。
- 多品項：重複 SKU 累加；每個 SKU 可依 Mapping、品項群組、容器與儲位規則分到不同 Location／Zone。
- 安全提交：掃碼只建立 intent 與 audit event，不直接改庫存；提交依序經 RBAC／readonly、業務規則、outbox、冪等 InventoryService、稽核。
- 相容契約：License 2.0、72h offline grace、clock rollback、readonly、ProgramData、SafeStorage、`integration.db`、Mapping profiles。

## 本機驗證

```powershell
& "C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest discover -s tests -v
& "C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m desktop_app.main
```

示範條碼：`PO-1001`、`SKU-A`、`SKU-COLD`、`BOX-01` 或 `BIN-A01`。示範 InventoryService 只存在記憶體；正式併版必須替換為 V6.8 既有庫存服務。

## 正式更新發佈

客戶端不下載 Python 原始碼。每次發佈必須先建立完整 Windows one-folder Build，再建立內容如下的更新包：

```text
TACO_Update_6.9.1.zip
└─ app/
   ├─ TACO.exe
   ├─ TACOUpdater.exe
   ├─ BUILD_VERSION.txt
   └─ 其餘已 Build 程式檔
```

接著以 `build_tools/release.py` 產生 canonical manifest 與簽章，並把 ZIP、manifest、signature 上傳 GitHub Releases 或自有 HTTPS 儲存空間。傳輸來源不是信任根；內建 Ed25519 公鑰才是。

完整步驟請看 `UPDATE_SYSTEM_V6.9.md` 與 `RELEASE_CHECKLIST_V6.9.md`。
