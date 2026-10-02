# TACO Update Server（靜態 HTTPS 即可）

這個資料夾不需要對外開管理 API。正式流程：

1. `generate_update_keys.py` 只執行一次；private key 留在伺服器，public key 進桌面程式 build。
2. Windows build 完後用 `package_app_update.py` 產生 `TACO_Update_x.x.x_win-x64.zip`。
3. 用 `build_signed_manifest.py` 產生 Ed25519 簽章的 `update.json`；manifest 裡含套件 SHA-256。
4. 把 `update.json` 與 ZIP 放到 HTTPS 靜態網站/CDN。
5. TACO 先驗證 manifest 簽章，再下載 ZIP、驗證 SHA-256；失敗即拒絕更新。

**private key 絕對不能進 TACO.exe 或交付給客戶。**
