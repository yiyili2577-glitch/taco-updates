# TACO V6.5.1 安全層級

## Layer 1：商業授權

License Server 2.0 發出 Ed25519 簽章 Receipt。TACO.exe 只有 Public Key。

- general
- intermediate
- advanced
- expiry
- maintenance_until
- max_devices
- update_channel
- offline receipt expiry

## Layer 2：公司內部帳號角色

- 系統管理員
- 財務人員
- 採購管理者
- 採購人員
- 倉管
- 主管

商業授權與使用者角色是兩件事；功能必須同時通過兩層。

## Layer 3：Service Permission

高風險寫入不只靠 UI disabled。`services/security.py` 在底層再次檢查角色與 tier。

## Layer 4：Business Rules

包含月結鎖帳、沖帳限制、信用額度、資料還原限制、正式發票限制等。

## Layer 5：OS / Data Security

- Windows DPAPI Secret Store
- SafeStorage atomic write + fsync + file backup
- Audit hash chain
- Data savepoint / restore
- Program Files / ProgramData 分離
- Signed License Receipt
- Signed Update Manifest + SHA-256
- Schema Migration + pre-migration backup
- Updater rollback foundation

## Private Key 信任邊界

License private key 與 Update private key 只存在你的伺服器/安全 build 環境，不存在客戶安裝包。
