import hashlib
import os
import secrets
import shutil
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from signing import sign_payload

VALID_TIERS = {"general", "intermediate", "advanced"}
VALID_CHANNELS = {"stable", "beta"}
STATUS_ACTIVE = "active"
STATUS_REVOKED = "revoked"
APP_ID = "taco_smart_procurement"


def _hash_token(raw_token):
    return hashlib.sha256(str(raw_token).encode("utf-8")).hexdigest()


def generate_token():
    return secrets.token_urlsafe(32)


def _columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_column(conn, table, name, definition):
    if name not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def init_db(db_path):
    os.makedirs(os.path.dirname(os.path.abspath(db_path)) or ".", exist_ok=True)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS licenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT UNIQUE NOT NULL,
                company TEXT NOT NULL DEFAULT '',
                tier TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                expires_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                last_verified_at TEXT NOT NULL DEFAULT ''
            )
        """)
        for name, definition in [
            ("license_id", "TEXT NOT NULL DEFAULT ''"),
            ("maintenance_until", "TEXT NOT NULL DEFAULT ''"),
            ("max_devices", "INTEGER NOT NULL DEFAULT 1"),
            ("update_channel", "TEXT NOT NULL DEFAULT 'stable'"),
            ("min_version", "TEXT NOT NULL DEFAULT ''"),
            ("latest_version", "TEXT NOT NULL DEFAULT ''"),
            ("offline_grace_hours", "INTEGER NOT NULL DEFAULT 72"),
        ]:
            _ensure_column(conn, "licenses", name, definition)
        # 舊 License Server 1.x 資料庫升級：補上 license_id，不改 token_hash，因此既有授權碼仍可繼續使用。
        legacy_rows = conn.execute("SELECT id, created_at, license_id FROM licenses").fetchall()
        for row_id, created_at, license_id in legacy_rows:
            if str(license_id or "").strip():
                continue
            year = str(created_at or "")[:4]
            if not year.isdigit():
                year = str(datetime.now().year)
            conn.execute("UPDATE licenses SET license_id=? WHERE id=?", (f"LIC-{year}-{int(row_id):06d}", row_id))

        conn.execute("""
            CREATE TABLE IF NOT EXISTS activations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                license_id INTEGER NOT NULL,
                device_id TEXT NOT NULL,
                device_name TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                UNIQUE(license_id, device_id),
                FOREIGN KEY(license_id) REFERENCES licenses(id)
            )
        """)
        conn.commit()


def _version_tuple(v):
    nums=[]
    for part in str(v or "").split("."):
        try: nums.append(int(''.join(ch for ch in part if ch.isdigit()) or 0))
        except Exception: nums.append(0)
    return tuple((nums+[0,0,0,0])[:4])


def issue_license(db_path, company, tier, expires_at="", raw_token=None, maintenance_until="",
                  max_devices=1, update_channel="stable", min_version="", latest_version="",
                  offline_grace_hours=72):
    if tier not in VALID_TIERS: raise ValueError(f"tier 必須是 {sorted(VALID_TIERS)} 其中之一。")
    if update_channel not in VALID_CHANNELS: raise ValueError("update_channel 只支援 stable / beta。")
    max_devices=max(1,int(max_devices))
    offline_grace_hours=max(1,min(720,int(offline_grace_hours or 72)))
    for label,value in [("expires_at",expires_at),("maintenance_until",maintenance_until)]:
        if value:
            try: date.fromisoformat(value)
            except ValueError as exc: raise ValueError(f"{label} 必須是 YYYY-MM-DD。") from exc
    raw_token=raw_token or generate_token(); init_db(db_path)
    created=datetime.now(timezone.utc).isoformat(timespec="seconds")
    with closing(sqlite3.connect(db_path)) as conn:
        cur=conn.execute(
            "INSERT INTO licenses (token_hash,company,tier,status,expires_at,created_at,license_id,maintenance_until,max_devices,update_channel,min_version,latest_version,offline_grace_hours) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (_hash_token(raw_token),str(company),tier,STATUS_ACTIVE,expires_at,created,"",maintenance_until,max_devices,update_channel,min_version,latest_version,offline_grace_hours),
        )
        row_id=cur.lastrowid
        license_id=f"LIC-{datetime.now().year}-{row_id:06d}"
        conn.execute("UPDATE licenses SET license_id=? WHERE id=?",(license_id,row_id)); conn.commit()
    return raw_token


def revoke_license(db_path, raw_token):
    init_db(db_path)
    with closing(sqlite3.connect(db_path)) as conn:
        cur=conn.execute("UPDATE licenses SET status=? WHERE token_hash=?",(STATUS_REVOKED,_hash_token(raw_token))); conn.commit(); return cur.rowcount>0


def revoke_device(db_path, license_id, device_id):
    init_db(db_path)
    with closing(sqlite3.connect(db_path)) as conn:
        cur=conn.execute("UPDATE activations SET status='revoked' WHERE license_id=(SELECT id FROM licenses WHERE license_id=?) AND device_id=?",(license_id,device_id)); conn.commit(); return cur.rowcount>0


def list_licenses(db_path):
    init_db(db_path)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory=sqlite3.Row
        rows=conn.execute("SELECT id,license_id,company,tier,status,expires_at,maintenance_until,max_devices,update_channel,min_version,latest_version,offline_grace_hours,created_at,last_verified_at FROM licenses ORDER BY id").fetchall()
        out=[]
        for row in rows:
            d=dict(row)
            d['active_devices']=conn.execute("SELECT COUNT(*) FROM activations WHERE license_id=? AND status='active'",(row['id'],)).fetchone()[0]
            out.append(d)
        return out


def list_devices(db_path, license_id):
    init_db(db_path)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory=sqlite3.Row
        rows=conn.execute("SELECT a.device_id,a.device_name,a.status,a.first_seen_at,a.last_seen_at FROM activations a JOIN licenses l ON l.id=a.license_id WHERE l.license_id=? ORDER BY a.last_seen_at DESC",(license_id,)).fetchall()
        return [dict(x) for x in rows]


def backup_db(db_path, backup_dir):
    init_db(db_path); Path(backup_dir).mkdir(parents=True,exist_ok=True)
    target=Path(backup_dir)/f"licenses_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(db_path,target); return str(target)


def _invalid(message, code="invalid", **extra):
    out={"valid":False,"code":code,"message":message}
    for key,value in extra.items():
        if value not in (None, ""):
            out[key]=value
    return out


def verify_token(db_path, raw_token, app, version, device_id, device_name="", default_offline_grace_hours=72):
    if not raw_token: return _invalid("缺少授權碼。","missing_token")
    if str(app)!=(APP_ID): return _invalid("應用程式識別不正確。","wrong_app")
    device_id=str(device_id or '').strip()
    if not device_id: return _invalid("缺少裝置識別。","missing_device")
    init_db(db_path)
    now=datetime.now(timezone.utc); now_iso=now.isoformat(timespec="seconds")
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory=sqlite3.Row
        row=conn.execute("SELECT * FROM licenses WHERE token_hash=?",(_hash_token(raw_token),)).fetchone()
        if row is None: return _invalid("授權碼不存在或不正確。","not_found")
        if row['status']!=STATUS_ACTIVE: return _invalid("這組授權碼已被停用。","revoked",license_id=str(row['license_id']))
        exp=str(row['expires_at'] or '').strip()
        if exp:
            try:
                if date.fromisoformat(exp)<date.today(): return _invalid(f"授權已於 {exp} 到期，請聯絡續約。","expired",license_id=str(row['license_id']))
            except ValueError:
                return _invalid("授權資料的到期日期格式異常，已拒絕驗證。","bad_expiry",license_id=str(row['license_id']))
        maint=str(row['maintenance_until'] or '').strip()
        if maint:
            try: date.fromisoformat(maint)
            except ValueError: return _invalid("授權資料的維護期限格式異常，已拒絕驗證。","bad_maintenance",license_id=str(row['license_id']))
        min_version=str(row['min_version'] or '').strip()
        if min_version and _version_tuple(version)<_version_tuple(min_version):
            return _invalid(f"目前 TACO {version} 低於最低允許版本 {min_version}，請先更新。","version_too_old",license_id=str(row['license_id']))

        activation=conn.execute("SELECT * FROM activations WHERE license_id=? AND device_id=?",(row['id'],device_id)).fetchone()
        if activation and activation['status']=='revoked': return _invalid("此裝置已被停用。","device_revoked",license_id=str(row['license_id']))
        if activation is None:
            count=conn.execute("SELECT COUNT(*) FROM activations WHERE license_id=? AND status='active'",(row['id'],)).fetchone()[0]
            if count>=int(row['max_devices'] or 1): return _invalid("已達授權裝置數上限，請先停用舊電腦。","device_limit",license_id=str(row['license_id']))
            conn.execute("INSERT INTO activations (license_id,device_id,device_name,status,first_seen_at,last_seen_at) VALUES (?,?,?,?,?,?)",(row['id'],device_id,str(device_name),STATUS_ACTIVE,now_iso,now_iso))
        else:
            conn.execute("UPDATE activations SET device_name=?,last_seen_at=?,status='active' WHERE id=?",(str(device_name),now_iso,activation['id']))
        conn.execute("UPDATE licenses SET last_verified_at=? WHERE id=?",(now_iso,row['id'])); conn.commit()

        grace_hours = int(row["offline_grace_hours"] or default_offline_grace_hours or 72)
        grace_hours = max(1, min(720, grace_hours))
        receipt={
            "app":APP_ID,
            "license_id":str(row['license_id']),
            "company":str(row['company']),
            "tier":str(row['tier']),
            "expires_at":exp,
            "maintenance_until":maint,
            "max_devices":int(row['max_devices'] or 1),
            "update_channel":str(row['update_channel'] or 'stable'),
            "min_version":min_version,
            "latest_version":str(row['latest_version'] or ''),
            "device_id":device_id,
            "server_time":now_iso.replace('+00:00','Z'),
            "issued_at":now_iso.replace('+00:00','Z'),
            "offline_grace_hours":grace_hours,
            "receipt_expires_at":(now+timedelta(hours=grace_hours)).isoformat(timespec='seconds').replace('+00:00','Z'),
        }
        return {"valid":True,"receipt":receipt,"signature":sign_payload(receipt),"message":""}
