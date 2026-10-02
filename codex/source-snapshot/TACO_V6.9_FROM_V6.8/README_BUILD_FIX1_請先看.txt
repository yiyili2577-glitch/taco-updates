TACO V6.5.1 - Windows Build Fix 1
=================================

這個修正版針對第一次 build_windows.bat 執行後視窗直接消失、dist 空白的問題。

已修正：
1. TACO.spec / TACOUpdater.spec 專案根目錄計算錯一層。
   原版使用 Path(SPECPATH).resolve().parent.parent，會把根目錄指到 taco_v651_pkg 的上一層，
   因此找不到 desktop_app/main.py，PyInstaller 在建立 EXE 前就失敗。
2. build_windows.bat 失敗後不再直接關閉視窗，會保留畫面等待按鍵。
3. 新增 build_logs/build_windows_latest.log，失敗時會顯示最後 80 行。
4. 新增獨立 .build_venv，避免依賴舊 Erp_app/.venv 或全域 Python 套件狀態。
5. PyInstaller 完成後會確認 TACO.exe 與 TACOUpdater.exe 真的存在。
6. 安全金鑰腳本改用同一個 build Python，並避免已有私鑰但 public key 不見時自動重建造成 key pair 不一致。

使用：
1. 將本 ZIP 解壓成全新的資料夾，例如：
   C:\TACO_RELEASE\V6.5.1_buildfix1\taco_v651_pkg
2. 不要覆蓋 C:\Users\User\Desktop\Erp_app，也不要搬舊 data 進來。
3. 雙擊：build_tools\build_windows.bat
4. 第一次會建立 .build_venv 並安裝套件，可能需要數分鐘。
5. 成功後應有：
   dist\TACO\TACO.exe
   dist\TACO\TACOUpdater.exe
6. 如果失敗，視窗不會消失；請截圖最後錯誤，或傳：
   build_logs\build_windows_latest.log
