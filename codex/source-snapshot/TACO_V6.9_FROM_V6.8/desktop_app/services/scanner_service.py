import hashlib
from services.integration_db_service import IntegrationDbService
from services.product_master_service import ProductMasterService
from services.warehouse_service import WarehouseService
from services.audit_log_service import AuditLogService
from services import security
class ScannerService:
    ACTIONS=('查詢','入庫','出庫','盤點','移倉')
    @staticmethod
    def resolve(code):
        code=str(code or '').strip(); binding=IntegrationDbService.barcode(code); pno=(binding or {}).get('product_no',''); products=ProductMasterService.load_products()
        if not pno:
            for p in products:
                if code==str(p.get('產品編號','')).strip() or code in {str(p.get('條碼','')).strip(),str(p.get('Barcode','')).strip()}: pno=str(p.get('產品編號','')).strip(); break
        prod=next((p for p in products if str(p.get('產品編號','')).strip()==pno),None)
        return {'barcode':code,'product_no':pno,'product_name':str((prod or {}).get('產品名稱','')),'binding':binding,'product':prod,'found':bool(prod)}
    @staticmethod
    def process_scan(code,action='查詢',quantity=None,warehouse_from='',warehouse_to='',idempotency_key=''):
        if action not in ScannerService.ACTIONS: raise ValueError('不支援的掃碼動作。')
        r=ScannerService.resolve(code)
        if not r.get('found'):
            eid=IntegrationDbService.record_scan(barcode=code,action=action,status='rejected',message='找不到條碼對應產品',idempotency_key=idempotency_key or None); AuditLogService.log_event('智慧掃碼','掃碼拒絕',record_id=eid,result='失敗',severity='警告',note='找不到條碼對應產品'); return {'ok':False,'message':'找不到條碼對應產品。請先建立產品條碼。','event_id':eid}
        bind=r.get('binding') or {}; qty=float(quantity if quantity not in (None,'') else bind.get('qty_per_scan',1) or 1)
        if qty<=0: raise ValueError('數量必須大於 0。')
        pno=r['product_no']; names=WarehouseService.load_names(); data=WarehouseService.load_inventory(); rec=dict(data.get(pno,{}) or {}); before=dict(rec); msg='僅查詢，未修改庫存'
        if action!='查詢':
            security.require_tier('intermediate','智慧掃碼庫存異動'); security.require_write_access('智慧掃碼庫存異動')
            def idx(n):
                if n not in names: raise ValueError(f'找不到倉庫：{n}')
                return str(names.index(n))
            if action=='入庫':
                n=warehouse_to or names[0]; k=idx(n); rec[k]=float(rec.get(k,0) or 0)+qty; msg=f'{n} 入庫 +{qty:g}'
            elif action=='出庫':
                n=warehouse_from or names[0]; k=idx(n); cur=float(rec.get(k,0) or 0)
                if cur<qty: raise ValueError(f'庫存不足：目前 {cur:g}，欲出庫 {qty:g}')
                rec[k]=cur-qty; msg=f'{n} 出庫 -{qty:g}'
            elif action=='盤點':
                n=warehouse_to or warehouse_from or names[0]; k=idx(n); rec[k]=qty; msg=f'{n} 盤點設為 {qty:g}'
            else:
                kf=idx(warehouse_from); kt=idx(warehouse_to)
                if kf==kt: raise ValueError('來源與目的倉不可相同。')
                cur=float(rec.get(kf,0) or 0)
                if cur<qty: raise ValueError(f'來源倉庫存不足：目前 {cur:g}，欲移倉 {qty:g}')
                rec[kf]=cur-qty; rec[kt]=float(rec.get(kt,0) or 0)+qty; msg=f'{warehouse_from} → {warehouse_to} {qty:g}'
            data[pno]=rec; WarehouseService.save_inventory(data)
        key=idempotency_key or hashlib.sha256(f'{code}|{action}|{pno}|{qty}|{warehouse_from}|{warehouse_to}|{IntegrationDbService.now()}'.encode()).hexdigest()
        eid=IntegrationDbService.record_scan(barcode=code,product_no=pno,product_name=r['product_name'],action=action,warehouse_from=warehouse_from,warehouse_to=warehouse_to,quantity=qty,status='completed',message=msg,idempotency_key=key)
        IntegrationDbService.enqueue('scan_event',eid,'upsert',{'barcode':code,'product_no':pno,'action':action,'quantity':qty,'warehouse_from':warehouse_from,'warehouse_to':warehouse_to},'scan:'+eid)
        AuditLogService.log_event('智慧掃碼',action,record_id=pno,before=before if action!='查詢' else None,after=rec if action!='查詢' else r,result='成功',note=msg)
        return {'ok':True,'message':msg,'event_id':eid,'resolved':r,'quantity':qty}
