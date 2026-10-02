# TACO V6.9 驗證報告

驗證日期：2026-08-14（Asia/Taipei）

## 結果

- Python compileall：PASS
- V6.9 單元／安全回歸：35／35 PASS
- ZIP 封裝與 SHA-256：PASS（最終值見 `artifacts/PACKAGE_SHA256_V6.9.txt`）
- 私鑰／資料庫／bytecode 排除檢查：由封裝腳本自動執行

## 覆蓋範圍

- 掃描順序、空條碼、單號優先、多品項、重複品項數量累加。
- 容器 Mapping、缺少 Mapping、逐品項／群組分流、不同 Location／Zone。
- 掃描不改庫存、RBAC、readonly、超收規則、冪等 key、取消與結案限制。
- scan audit、inventory outbox committed／failed 狀態與 Windows SQLite 連線釋放。
- License 2.0、72h offline grace、clock rollback、revoke、到期與維護權。
- SafeStorage 原子寫入、絕對／相對路徑逸出阻擋。
- `integration.db` WAL、additive migration、Mapping profiles 資料保留。
- Manifest 嚴格欄位、SemVer、通道、HTTPS、日期、雜湊與大小限制。
- Ed25519 正確／竄改簽章、SHA-256、package size。
- Zip Slip、Windows 反斜線、絕對／磁碟機路徑、重複路徑、符號連結。
- 更新資格、ProgramData 邊界、版本標記、原子替換成功與健康檢查失敗回復。

## 未驗證／不能宣稱完成的範圍

- `sources/` 為空，因此未取得 V6.8 原始專案，無法重跑先前 136 項完整回歸。
- 未合併 V6.8 財務 22 頁籤及其他既有業務頁面。
- 未建立 PyInstaller／Inno Setup 的正式 `TACO_Setup_6.9.0.exe`。
- 未對真實 License Server、正式 InventoryService、GitHub Release 或正式 HTTPS Server 做端到端測試。
- 未做 Windows Authenticode，因工作區沒有正式簽章憑證。

上述項目需在取得 V6.8 原始專案、正式公鑰／URL 與 Build 憑證後，依 `RELEASE_CHECKLIST_V6.9.md` 完成。
