# TACO V6.9 安全更新系統

## 信任模型

GitHub Releases、自有 CDN 或物件儲存只負責傳輸。客戶端唯一信任根是隨 TACO 發佈、不可由伺服器替換的 Ed25519 公鑰。對應私鑰必須離線保存，禁止進入 Git、CI log、客戶 ZIP 或 Setup。

Windows 正式檔另應使用 Authenticode 簽署；它解決 Windows 發行者信任，Ed25519 則解決 TACO 內部更新信任，兩者不能互相取代。

## 客戶端順序

1. 透過 HTTPS 下載 `manifest.json` 與 `manifest.sig`。
2. 先用內建 Ed25519 公鑰驗證原始 manifest bytes，再解析內容。
3. 檢查 Stable／Beta／Internal、SemVer、最低橋接版本、License 維護期限與 Schema 禁止降級。
4. 下載已 Build 的 Windows ZIP，限制 Content-Length 與實際接收大小。
5. 驗證 package size 與 SHA-256。
6. 解壓至獨立 staging，阻擋路徑逸出、符號連結、重複檔與解壓炸彈。
7. 確認 `app/BUILD_VERSION.txt`，建立安裝目錄備份與 ProgramData 資料儲存點。
8. 關閉 TACO，由獨立 `TACOUpdater.exe` 進行 Program Files 原子替換。
9. 只有具版本號、可重入且可回復的 migration 能修改 ProgramData。
10. 執行 migration、啟動健康檢查；任一步失敗即回復程式與資料。
11. 成功後記錄 update history 並重啟 TACO。

## Manifest 欄位

```json
{
  "channel": "stable",
  "min_version": "6.9.0",
  "package_sha256": "64-lowercase-hex",
  "package_size": 123456,
  "package_url": "https://updates.example/TACO_Update_6.9.1.zip",
  "published_at": "2026-08-14T00:00:00Z",
  "release_notes": "修正內容",
  "schema_version": 2,
  "version": "6.9.1"
}
```

JSON 必須以 UTF-8、key 排序、無額外空白的 canonical 形式簽署。客戶端採嚴格欄位白名單，新增欄位時需提升 manifest 規格版本，不可靜默接受。

## ProgramData 規則

- 一般更新包只能替換 Program Files，不能包含或覆蓋 `C:\ProgramData\TACO`。
- `integration.db` 使用 WAL；備份要走 SQLite backup／checkpoint 協調，不可在寫入中只複製 `.db`。
- Migration 必須先建立 `UPDATE_PRE_<version>` 儲存點，再執行可重入 migration。
- Migration 失敗必須把程式與資料一起回復，不能留下新程式搭配舊 Schema。

## 發佈工具範例

```powershell
python build_tools\release.py TACO_Update_6.9.1.zip `
  --private-key D:\TACO_OFFLINE_KEYS\update_private_key.pem `
  --version 6.9.1 --channel stable `
  --url https://updates.example/TACO_Update_6.9.1.zip `
  --min-version 6.9.0 --schema-version 2 `
  --published-at 2026-08-14T00:00:00Z `
  --release-notes "修正內容" --output release\6.9.1
```

私鑰路徑必須位於發佈輸出目錄之外。
