TACO V6.5.1｜Windows 正式桌面版基底＋License Server 2.0＋安全更新架構
====================================================================

這一版是「封裝/上線基底」，不是再新增一堆財務按鈕。
主程式基底：TACO V6.5 Hotfix 1（含 V6.5 財務啟動相容修正）。
同時把 Claude 正式上線套件中的 License Server 優點重新整合成 2.0，而不是用舊 V5 程式覆蓋 V6.5。

【最重要的架構改變】

正式 EXE：
  C:\Program Files\TACO\TACO.exe

正式公司資料：
  C:\ProgramData\TACO\Data

其他可變資料：
  C:\ProgramData\TACO\Backups
  C:\ProgramData\TACO\AuditLogs
  C:\ProgramData\TACO\Logs
  C:\ProgramData\TACO\Config
  C:\ProgramData\TACO\Exports
  C:\ProgramData\TACO\Updates

未來更新只換 Program Files 裡的程式；ProgramData 公司資料不覆蓋。
解除安裝也刻意保留 ProgramData\TACO，避免資料跟著軟體被刪除。

【第一次從舊 Erp_app 移轉】

正式 EXE 第一次啟動時，如果新 Data 還沒有公司資料，會偵測：
  %USERPROFILE%\Desktop\Erp_app\data

找到後會先建立：
  MIGRATION_PRE_V651_*.zip

再複製到 ProgramData\TACO。新資料區已存在資料時，不會自動覆蓋。

【DEV / PROD 分離】

原始碼執行預設 DEV：保留開發測試模式，可測一般/中階/高級版。
PyInstaller EXE 預設 PROD：
  - development_mode 永遠 False
  - 修改 system_settings.json 不能自己變 advanced
  - 正式 tier 只相信 Ed25519 簽章 License Receipt
  - 正式授權 Token 不寫 system_settings.json

【Token 安全】

正式 Windows 使用 DPAPI 保存 License Token：
  C:\ProgramData\TACO\Config\secrets.dpapi.json

裡面是 Windows DPAPI 密文，不是 Token 明碼。
Public metadata（公司、tier、到期日等）可以保存在設定中。

【License Server 2.0】

保留 Claude 原本：
  - SQLite
  - secrets.token_urlsafe(32)
  - DB 只存 Token SHA-256
  - revoke / expiry
  - 不開授權管理 Web API

新增：
  - Ed25519 簽章
  - Device Activation / Max Devices
  - Offline Receipt（預設 7 天）
  - maintenance_until
  - stable / beta channel
  - min_version
  - app ID 嚴格驗證
  - 異常日期 fail closed
  - rate limit
  - 舊 licenses.db schema 自動升級

【更新安全】

更新 Manifest 必須有 Ed25519 簽章。
更新 ZIP 必須符合 Manifest 裡的 SHA-256。
流程：
  signed update.json
       ↓
  TACO 驗證 Public Key
       ↓
  下載 ZIP
       ↓
  SHA-256 驗證
       ↓
  pending_update.json
       ↓
  TACOUpdater.exe（獨立更新器基底）
       ↓
  更新前 APP_UPDATE_PRE_*.zip
       ↓
  只替換程式，不碰 ProgramData\TACO\Data
       ↓
  失敗可 rollback

【Data Schema Migration】

新增 services/data_migration_service.py。
現在 schema_version=1；未來 V6.6/V7.0 要改資料格式時，必須透過 migration 逐版升級，不能要求刪掉舊資料重來。

【Windows 第一次正式 Build】

1. 請保留目前 Erp_app 完整備份。
2. 把這個 ZIP 解壓到一個新的資料夾，例如：
     C:\TACO_RELEASE\V6.5.1
3. 開啟 CMD / PowerShell 到這個資料夾。
4. 執行：
     build_tools\build_windows.bat
5. 完成後：
     dist\TACO\TACO.exe
     dist\TACO\TACOUpdater.exe

如果要產生正式安裝程式，先安裝 Inno Setup 6，然後：
     build_tools\build_setup.bat

完成後：
     installer\Output\TACO_Setup_6.5.1.exe

注意：PyInstaller 的 Windows EXE 必須在 Windows 上 build。本套件已包含 spec/build script，但這裡提供的 ZIP 本身不是已編譯 EXE。

【金鑰】

build_windows.bat 第一次會建立：
  license_server\secret\license_private_key.pem
  update_server\secret\update_private_key.pem

並把兩把 Public Key 複製到 desktop_app\resources 後才 Build。

PRIVATE KEY 禁止寄給客戶、禁止塞進 EXE、禁止公開上傳。

【測試】

Desktop source：95 tests OK
License Server 2.0：5 tests OK

建議 Windows build 前再跑：
  cd desktop_app
  python -m unittest discover -s tests -v

【資料不要這樣做】

不要把舊 data 手動塞進 Program Files\TACO。
不要把 license_server 整個資料夾發給客戶。
不要把 update_server\secret 發給客戶。
不要用舊 Claude erp_app 覆蓋 V6.5。
不要在正式 EXE 用 development_mode 解鎖 advanced。
