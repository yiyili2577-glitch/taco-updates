# TACO 6.9.0 版本說明

## 安全自動更新中心

- 新增 Stable／Beta／Internal 通道與 License 維護更新權檢查。
- 新增 canonical manifest、Ed25519 發佈簽章、SHA-256 與檔案大小雙重驗證。
- 更新下載限定 HTTPS，任何格式、簽章、雜湊或資格錯誤皆 fail-closed。
- 新增惡意 ZIP 防護、staging、備份、原子替換、健康檢查與回復核心。
- 新增獨立發佈工具；更新私鑰永不進入客戶包。

## 智慧掃碼中心

- 條碼輸入欄放大為 30pt，增加 24px 垂直留白並固定掃碼焦點。
- 新增四階段工作導引、批次摘要與六欄大型多品項清單。
- 明確流程為「單號 → 多品項 → 容器／儲位 → 安全覆核」。
- 重複品項累加數量；不同品項可依 Mapping／群組規則分流到不同儲位與區域。
- 掃碼不修改庫存；只有通過權限、readonly、單據／數量規則、outbox 與冪等服務後才入庫。

## 相容與安全

- 保留 License 2.0、72h offline grace、clock rollback、readonly mode。
- 保留 `C:\ProgramData\TACO`、SafeStorage、`integration.db` WAL、Mapping profiles 與 sync queue。
- Integration Schema 維持 2；V6.9 僅做 additive table／column migration。

## 已知邊界

因本工作區沒有 V6.8 原始專案，本包尚未合併財務中心等既有業務畫面，也沒有產生正式 Setup.exe。正式客戶端必須完成 V6.8 併版與全回歸後另行 Build。
