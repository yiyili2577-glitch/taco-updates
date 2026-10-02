# TACO License Server 2.0

這是從原先 Claude 版 License Server 升級而來的正式授權基底。保留「SQLite + 高熵 Token SHA-256 雜湊 + 只暴露 verify API」的簡潔設計，新增：

- Ed25519 非對稱簽章授權收據（Desktop 只有 Public Key，Private Key 永不進 EXE）
- `app=taco_smart_procurement` 嚴格檢查
- 授權到期日格式異常採 **fail closed**
- 公司、方案層級、維護更新期限
- 裝置數上限與裝置啟用 / 停用
- 7 天離線授權 Receipt（可用 `OFFLINE_RECEIPT_DAYS` 調整 1~30 天）
- stable / beta update channel
- 最低允許版本
- 驗證端點簡易 Rate Limit
- 舊版 `licenses.db` 自動補欄位，不改 token_hash，舊 Token 可延續
- License DB 備份 CLI

## 1. 第一次部署只做一次：產生簽章金鑰

在**伺服器主機或安全的管理電腦**執行：

```bash
python generate_signing_keys.py --desktop-resources ../desktop_app/resources
```

會產生：

- `license_server/secret/license_private_key.pem`：**只留伺服器，禁止外流**
- `desktop_app/resources/license_public_key.pem`：可以放進 TACO.exe

不要反覆重新產生。換 Private Key 等於換授權信任根，既有 Desktop 也要同步更新 Public Key。

## 2. 安裝依賴 / 測試

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

## 3. 核發授權

```bash
python issue_license_cli.py issue \
  --company "客戶公司" \
  --tier advanced \
  --expires 2027-12-31 \
  --maintenance-until 2027-12-31 \
  --max-devices 10 \
  --channel stable \
  --min-version 6.5.1
```

Token 只顯示一次，DB 只保存 SHA-256 雜湊。

查看授權：

```bash
python issue_license_cli.py list
```

查看某授權已啟用電腦：

```bash
python issue_license_cli.py devices --license-id LIC-2026-000001
```

停用特定電腦：

```bash
python issue_license_cli.py revoke-device --license-id LIC-2026-000001 --device-id <DEVICE_ID>
```

停用整組授權：

```bash
python issue_license_cli.py revoke --token <TOKEN>
```

備份 DB：

```bash
python issue_license_cli.py backup --to /secure/backup/path
```

## 4. API

正式只需對外：

- `GET /health`
- `POST /verify`

Verify Request：

```json
{
  "token": "...",
  "app": "taco_smart_procurement",
  "version": "6.5.1",
  "device_id": "...",
  "device_name": "FINANCE-PC01"
}
```

成功回應含 `receipt` + `signature`。Desktop 必須先驗 Ed25519 signature 才相信 tier。

## 5. 正式部署

建議：

```text
Internet -> HTTPS (Caddy/Nginx) -> Gunicorn -> Flask -> SQLite
```

Linux 範例：

```bash
export LICENSE_DB_PATH=/srv/taco-license/data/licenses.db
export LICENSE_PRIVATE_KEY_PATH=/srv/taco-license/secret/license_private_key.pem
export OFFLINE_RECEIPT_DAYS=7
export VERIFY_LIMIT_PER_MINUTE=60

gunicorn --workers 2 --bind 127.0.0.1:8000 app:app
```

對外只開 443。`issue_license_cli.py` 不需要做網路管理 API，建議 SSH 到伺服器執行。

## 安全底線

**絕對不可交付給客戶：**

- `license_server/secret/`
- `license_private_key.pem`
- `licenses.db`
- 伺服器備份

客戶安裝包只需要 Public Key。
