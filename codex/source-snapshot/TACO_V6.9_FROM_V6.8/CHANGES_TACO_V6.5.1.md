# TACO V6.5.1 變更摘要

基底：TACO V6.5 Hotfix 1。

## 正式桌面封裝基底

- `services/build_config.py`：DEV / PROD 分離；frozen EXE 預設 PROD。
- `services/app_paths.py`：正式可變資料全部移到 `%PROGRAMDATA%\TACO`。
- `services/bootstrap_service.py`：首次 EXE 啟動偵測舊 Desktop `Erp_app\data`，先 ZIP 備份再搬遷。
- `services/data_migration_service.py`：新增 schema migration framework 與 migration 前資料備份。
- `build_tools/TACO.spec`：PyInstaller OneDir 正式 build。
- `build_tools/TACOUpdater.spec`：獨立 Updater build。
- `installer/TACO_V651.iss`：Inno Setup 安裝程式；卸載不刪 ProgramData 公司資料。

## License Server 2.0

- 延續 Claude 版 SQLite + 高熵 Token + SHA-256 token hash。
- 舊 `licenses.db` 自動補新欄位，既有 token_hash 不變。
- Ed25519 簽章 License Receipt。
- Desktop 只含 Public Key；Private Key 只在 License Server。
- 裝置啟用 / max devices / revoke device。
- 離線授權收據，預設 7 天。
- maintenance_until / update_channel / min_version。
- 嚴格 app ID 檢查。
- 日期格式錯誤改為 fail closed。
- 基本 rate limit。
- License DB backup CLI。

## Secret 安全

- 正式 License Token 不再寫進 `system_settings.json`。
- Windows 使用 DPAPI LOCAL_MACHINE scope 存放裝置授權 Token。
- 舊版 JSON 若還有 `license_key`，正式首次啟動會搬入 DPAPI 並清空 JSON 欄位。
- 正式版 `development_mode` 無法靠修改 JSON 開啟。
- 正式 tier 只信任有效的 Ed25519 Receipt。

## 安全更新架構

- `services/update_service.py`：驗證簽章 Manifest、下載、SHA-256 驗證。
- `update_server/`：獨立 Update Ed25519 signing key、更新 ZIP 封裝與 manifest 產生工具。
- `desktop_app/updater.py`：獨立更新器基底；更新前備份 Program Files 程式、失敗回滾、不碰 ProgramData Data。
- 系統設定「版本更新」改為 signed manifest 檢查，不再直接相信任意文字回應。

## Claude 正式套件整合

- 不使用舊 `erp_app` 覆蓋新版。
- 保留並升級 License Server 思路。
- 將 `erp_sql_connector_service.py`、`sql_import_dialog.py` 安全地保留在新完整 source 中，供後續正式正航 SQL 整合；目前不強行改變既有 UI 工作流。

## 回歸測試

- Desktop：95 tests OK。
- License Server 2.0：5 tests OK。
