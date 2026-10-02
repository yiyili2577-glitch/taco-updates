# TACO V6.9 正式發佈檢查表

## Build 前

- [ ] V6.8 原始專案已完整併版，沒有用本參考包取代舊業務模組。
- [ ] V6.8 原 136 項＋V6.9 35 項測試全部通過。
- [ ] Schema migration 已做實際 V6.6／V6.8 資料副本升級與回復測試。
- [ ] Stable manifest URL、內建 Ed25519 公鑰、License maintenance 欄位已設定。

## Build 與簽署

- [ ] 所有版本標記一致為目標版本；舊 dist 版本不符時強制重建。
- [ ] PyInstaller one-folder Build 成功，`BUILD_VERSION.txt` 正確。
- [ ] TACO.exe、TACOUpdater.exe、DLL 與 Setup 已做 Authenticode。
- [ ] 更新 ZIP 只有 `app/` Build 成品，不包含 ProgramData、私鑰、`.db`、測試資料。
- [ ] 離線 Ed25519 私鑰產生 manifest.sig；私鑰沒有進 CI artifact／log。

## 發佈前驗證

- [ ] 乾淨 Windows VM 安裝 V6.8，再由 Stable 通道升級到目標版本。
- [ ] 模擬下載中斷、SHA-256 錯誤、簽章錯誤、ZIP 路徑攻擊，皆 fail-closed。
- [ ] 模擬程式替換後健康檢查失敗，程式與資料均成功回復。
- [ ] 72 小時離線、時間回撥、撤銷與 readonly 行為未改變。
- [ ] 多品項、冷藏／一般分流、容器 Mapping、超收、無權限與重複提交實機測試完成。
- [ ] `C:\ProgramData\TACO` 資料、Mapping 與 integration queue 升級後完整。

## 發佈後

- [ ] Stable release assets、manifest、signature 與 release notes 已上傳。
- [ ] 先以 Internal／Beta 小範圍更新，再逐步開 Stable。
- [ ] 保留前一版程式與 migration 回復包，監看 update history 與錯誤率。
