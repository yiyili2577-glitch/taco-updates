import json, sqlite3, threading, uuid
from datetime import datetime, timezone
from pathlib import Path
from services.app_paths import AppPaths
from services.safe_storage import get_logger

class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None: self.commit()
            else: self.rollback()
        finally:
            self.close()
        return False

class IntegrationDbService:
    _lock = threading.RLock()
    @staticmethod
    def db_path(): return Path(AppPaths.data_dir()) / 'integration.db'
    @staticmethod
    def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
    @classmethod
    def connect(cls):
        p=cls.db_path(); p.parent.mkdir(parents=True,exist_ok=True)
        c=sqlite3.connect(str(p),timeout=10,factory=_ClosingConnection); c.row_factory=sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON'); c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA synchronous=FULL'); c.execute('PRAGMA busy_timeout=10000')
        return c
    @classmethod
    def initialize(cls):
        with cls._lock, cls.connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS barcode_bindings(barcode TEXT PRIMARY KEY,product_no TEXT NOT NULL,unit TEXT NOT NULL DEFAULT '',qty_per_scan REAL NOT NULL DEFAULT 1,note TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS scan_events(event_id TEXT PRIMARY KEY,scanned_at TEXT NOT NULL,barcode TEXT NOT NULL,product_no TEXT NOT NULL DEFAULT '',product_name TEXT NOT NULL DEFAULT '',action TEXT NOT NULL,warehouse_from TEXT NOT NULL DEFAULT '',warehouse_to TEXT NOT NULL DEFAULT '',quantity REAL NOT NULL DEFAULT 0,status TEXT NOT NULL,message TEXT NOT NULL DEFAULT '',actor TEXT NOT NULL DEFAULT '',idempotency_key TEXT NOT NULL UNIQUE);
            CREATE TABLE IF NOT EXISTS mapping_profiles(profile_id TEXT PRIMARY KEY,name TEXT NOT NULL UNIQUE,source_type TEXT NOT NULL,tenant_id TEXT NOT NULL DEFAULT 'local',mappings_json TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sync_queue(queue_id TEXT PRIMARY KEY,entity_type TEXT NOT NULL,entity_id TEXT NOT NULL,operation TEXT NOT NULL,payload_json TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',retry_count INTEGER NOT NULL DEFAULT 0,next_retry_at TEXT NOT NULL DEFAULT '',last_error TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,idempotency_key TEXT NOT NULL UNIQUE);
            CREATE TABLE IF NOT EXISTS storage_destinations(code TEXT PRIMARY KEY,kind TEXT NOT NULL CHECK(kind IN ('container','location')),warehouse TEXT NOT NULL,location TEXT NOT NULL DEFAULT '',zone TEXT NOT NULL DEFAULT '',enabled INTEGER NOT NULL DEFAULT 1,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS storage_rules(rule_id TEXT PRIMARY KEY,product_no TEXT NOT NULL DEFAULT '*',product_group TEXT NOT NULL DEFAULT '',container_code TEXT NOT NULL DEFAULT '',warehouse TEXT NOT NULL DEFAULT '',location TEXT NOT NULL DEFAULT '',zone TEXT NOT NULL DEFAULT '',priority INTEGER NOT NULL DEFAULT 100,enabled INTEGER NOT NULL DEFAULT 1,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS receipt_batches(receipt_id TEXT PRIMARY KEY,session_id TEXT NOT NULL UNIQUE,order_no TEXT NOT NULL,payload_json TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('applying','committed','failed')),failure_code TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_scan_product ON scan_events(product_no, scanned_at);
            CREATE INDEX IF NOT EXISTS idx_queue_status ON sync_queue(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_storage_rule_match ON storage_rules(product_no,product_group,container_code,priority);
            """)
        return str(cls.db_path())
    @classmethod
    def upsert_barcode(cls,barcode,product_no,unit='',qty_per_scan=1,note=''):
        from services import security; security.require_write_access('設定產品條碼')
        barcode=str(barcode or '').strip(); product_no=str(product_no or '').strip(); qty=float(qty_per_scan or 1)
        if not barcode or not product_no: raise ValueError('條碼與產品編號不可空白。')
        if qty<=0: raise ValueError('每掃數量必須大於 0。')
        cls.initialize()
        with cls._lock, cls.connect() as c:
            c.execute("INSERT INTO barcode_bindings VALUES(?,?,?,?,?,?) ON CONFLICT(barcode) DO UPDATE SET product_no=excluded.product_no,unit=excluded.unit,qty_per_scan=excluded.qty_per_scan,note=excluded.note,updated_at=excluded.updated_at",(barcode,product_no,str(unit or ''),qty,str(note or ''),cls.now()))
        return True
    @classmethod
    def delete_barcode(cls,barcode):
        from services import security; security.require_write_access('刪除產品條碼'); cls.initialize()
        with cls._lock, cls.connect() as c: c.execute('DELETE FROM barcode_bindings WHERE barcode=?',(str(barcode),))
    @classmethod
    def barcode(cls,code):
        cls.initialize()
        with cls.connect() as c: r=c.execute('SELECT * FROM barcode_bindings WHERE barcode=?',(str(code or '').strip(),)).fetchone()
        return dict(r) if r else None
    @classmethod
    def list_barcodes(cls):
        cls.initialize()
        with cls.connect() as c: rows=c.execute('SELECT * FROM barcode_bindings ORDER BY product_no,barcode').fetchall()
        return [dict(x) for x in rows]
    @classmethod
    def record_scan(cls,**e):
        cls.initialize(); eid=e.get('event_id') or str(uuid.uuid4()); idem=e.get('idempotency_key') or str(uuid.uuid4())
        vals=(eid,e.get('scanned_at') or cls.now(),str(e.get('barcode','')),str(e.get('product_no','')),str(e.get('product_name','')),str(e.get('action','查詢')),str(e.get('warehouse_from','')),str(e.get('warehouse_to','')),float(e.get('quantity',0) or 0),str(e.get('status','completed')),str(e.get('message','')),str(e.get('actor','')),idem)
        with cls._lock, cls.connect() as c: c.execute('INSERT OR IGNORE INTO scan_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',vals)
        return eid
    @classmethod
    def list_scans(cls,limit=300):
        cls.initialize()
        with cls.connect() as c: rows=c.execute('SELECT * FROM scan_events ORDER BY scanned_at DESC LIMIT ?',(int(limit),)).fetchall()
        return [dict(x) for x in rows]
    @classmethod
    def save_mapping_profile(cls,name,source_type,mappings,tenant_id='local',profile_id=None):
        from services import security; security.require_write_access('儲存 Mapping Profile')
        name=str(name or '').strip(); source_type=str(source_type or '').strip(); clean={str(k).strip():str(v).strip() for k,v in dict(mappings or {}).items() if str(k).strip() and str(v).strip()}
        if not name or not source_type: raise ValueError('Profile 名稱與來源類型不可空白。')
        if not clean: raise ValueError('至少需要一個欄位對應。')
        cls.initialize(); pid=profile_id or str(uuid.uuid4()); now=cls.now()
        with cls._lock, cls.connect() as c:
            old=c.execute('SELECT profile_id FROM mapping_profiles WHERE name=?',(name,)).fetchone(); pid=old['profile_id'] if old else pid
            c.execute("INSERT INTO mapping_profiles VALUES(?,?,?,?,?,1,?) ON CONFLICT(profile_id) DO UPDATE SET name=excluded.name,source_type=excluded.source_type,tenant_id=excluded.tenant_id,mappings_json=excluded.mappings_json,enabled=1,updated_at=excluded.updated_at",(pid,name,source_type,str(tenant_id or 'local'),json.dumps(clean,ensure_ascii=False),now))
        return pid
    @classmethod
    def list_mapping_profiles(cls):
        cls.initialize()
        with cls.connect() as c: rows=c.execute('SELECT * FROM mapping_profiles ORDER BY name').fetchall()
        out=[]
        for r in rows:
            d=dict(r)
            try: d['mappings']=json.loads(d.pop('mappings_json'))
            except Exception: d['mappings']={}
            out.append(d)
        return out
    @classmethod
    def get_mapping_profile(cls,pid): return next((x for x in cls.list_mapping_profiles() if x['profile_id']==pid),None)
    @classmethod
    def enqueue(cls,entity_type,entity_id,operation,payload,idempotency_key=None):
        from services import security; security.require_write_access('建立本機同步佇列')
        cls.initialize(); qid=str(uuid.uuid4()); idem=idempotency_key or f'{entity_type}:{entity_id}:{operation}:{uuid.uuid4()}'; now=cls.now()
        with cls._lock, cls.connect() as c: c.execute("INSERT OR IGNORE INTO sync_queue VALUES(?,?,?,?,?,'pending',0,'','',?,?,?)",(qid,str(entity_type),str(entity_id),str(operation),json.dumps(payload,ensure_ascii=False),now,now,idem))
        return qid
    @classmethod
    def list_queue(cls,status=None,limit=300):
        cls.initialize(); sql='SELECT * FROM sync_queue'; args=[]
        if status: sql+=' WHERE status=?'; args.append(status)
        sql+=' ORDER BY created_at DESC LIMIT ?'; args.append(int(limit))
        with cls.connect() as c: rows=c.execute(sql,args).fetchall()
        return [dict(x) for x in rows]
    @classmethod
    def health(cls):
        try:
            p=cls.initialize()
            with cls.connect() as c:
                mode=c.execute('PRAGMA journal_mode').fetchone()[0]; integ=c.execute('PRAGMA quick_check').fetchone()[0]
                counts={t:c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ('barcode_bindings','scan_events','mapping_profiles','sync_queue','storage_destinations','storage_rules','receipt_batches')}
            return {'ok':integ=='ok','db':p,'journal_mode':mode,'integrity':integ,'counts':counts}
        except Exception as e:
            get_logger().error('integration.db health failed',exc_info=True); return {'ok':False,'error':str(e)}

    @classmethod
    def upsert_destination(cls,code,kind,warehouse,location='',zone=''):
        from services import security; security.require_write_access('設定容器／儲位 Mapping')
        code=str(code or '').strip(); kind=str(kind or '').strip().lower(); warehouse=str(warehouse or '').strip()
        if not code or kind not in ('container','location') or not warehouse: raise ValueError('目的地代碼、類型與倉庫不可空白。')
        cls.initialize()
        with cls._lock, cls.connect() as c:
            c.execute("INSERT INTO storage_destinations VALUES(?,?,?,?,?,1,?) ON CONFLICT(code) DO UPDATE SET kind=excluded.kind,warehouse=excluded.warehouse,location=excluded.location,zone=excluded.zone,enabled=1,updated_at=excluded.updated_at",(code,kind,warehouse,str(location or ''),str(zone or ''),cls.now()))
        return code

    @classmethod
    def resolve_destination(cls,code,default_warehouse=''):
        cls.initialize(); code=str(code or '').strip()
        with cls.connect() as c: row=c.execute('SELECT * FROM storage_destinations WHERE code=? AND enabled=1',(code,)).fetchone()
        if row: return dict(row)
        upper=code.upper()
        if upper.startswith(('BOX-','BOX:','CTN-','CTN:')): kind='container'
        elif upper.startswith(('BIN-','BIN:','LOC-','LOC:')): kind='location'
        else: return None
        warehouse=str(default_warehouse or '').strip()
        if not warehouse: return None
        return {'code':code,'kind':kind,'warehouse':warehouse,'location':code if kind=='location' else '','zone':'待上架區','enabled':1}

    @classmethod
    def upsert_storage_rule(cls,product_no='*',product_group='',container_code='',warehouse='',location='',zone='',priority=100,rule_id=None):
        from services import security; security.require_write_access('設定品項存放規則')
        if not any(str(x or '').strip() for x in (warehouse,location,zone)): raise ValueError('存放規則至少要指定倉庫、儲位或區域。')
        cls.initialize(); rid=rule_id or str(uuid.uuid4())
        with cls._lock, cls.connect() as c:
            c.execute("INSERT INTO storage_rules VALUES(?,?,?,?,?,?,?,?,1,?) ON CONFLICT(rule_id) DO UPDATE SET product_no=excluded.product_no,product_group=excluded.product_group,container_code=excluded.container_code,warehouse=excluded.warehouse,location=excluded.location,zone=excluded.zone,priority=excluded.priority,enabled=1,updated_at=excluded.updated_at",(rid,str(product_no or '*'),str(product_group or ''),str(container_code or ''),str(warehouse or ''),str(location or ''),str(zone or ''),int(priority),cls.now()))
        return rid

    @classmethod
    def resolve_storage_rule(cls,product_no,product_group,destination):
        cls.initialize(); container=str((destination or {}).get('code','')) if str((destination or {}).get('kind',''))=='container' else ''
        with cls.connect() as c:
            rows=c.execute("SELECT * FROM storage_rules WHERE enabled=1 AND product_no IN (?, '*') AND product_group IN (?, '') AND container_code IN (?, '') ORDER BY CASE WHEN product_no=? THEN 0 ELSE 1 END,CASE WHEN product_group<>'' THEN 0 ELSE 1 END,CASE WHEN container_code<>'' THEN 0 ELSE 1 END,priority ASC",(str(product_no),str(product_group or ''),container,str(product_no))).fetchall()
        return dict(rows[0]) if rows else None

    @classmethod
    def begin_receipt(cls,session_id,order_no,payload):
        cls.initialize(); session_id=str(session_id); now=cls.now(); receipt_id='RCV-'+uuid.uuid4().hex[:12].upper()
        with cls._lock, cls.connect() as c:
            old=c.execute('SELECT * FROM receipt_batches WHERE session_id=?',(session_id,)).fetchone()
            if old: return dict(old),False
            c.execute("INSERT INTO receipt_batches VALUES(?,?,?,?,'applying','',?,?)",(receipt_id,session_id,str(order_no),json.dumps(payload,ensure_ascii=False,sort_keys=True),now,now))
        return {'receipt_id':receipt_id,'session_id':session_id,'status':'applying'},True

    @classmethod
    def finish_receipt(cls,session_id,status,failure_code=''):
        if status not in ('committed','failed'): raise ValueError('receipt status 無效。')
        cls.initialize()
        with cls._lock, cls.connect() as c:
            cur=c.execute('UPDATE receipt_batches SET status=?,failure_code=?,updated_at=? WHERE session_id=?',(status,str(failure_code or '')[:200],cls.now(),str(session_id)))
            if cur.rowcount!=1: raise ValueError('找不到收貨批次。')

    @classmethod
    def list_receipts(cls,limit=100):
        cls.initialize()
        with cls.connect() as c: rows=c.execute('SELECT * FROM receipt_batches ORDER BY created_at DESC LIMIT ?',(int(limit),)).fetchall()
        return [dict(x) for x in rows]
