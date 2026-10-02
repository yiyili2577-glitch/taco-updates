import re
import uuid
from copy import deepcopy

from services import security
from services.audit_log_service import AuditLogService
from services.integration_db_service import IntegrationDbService
from services.scanner_service import ScannerService
from services.warehouse_service import WarehouseService


class ScanReceiptError(ValueError): pass


class ScanReceiptSession:
    ORDER='order'; ITEMS='items'; REVIEW='review'; COMMITTED='committed'; CANCELLED='cancelled'

    def __init__(self,session_id=None):
        self.session_id=session_id or str(uuid.uuid4()); self.stage=self.ORDER; self.order_no=''; self.items={}; self.destination=None; self.allocations=[]; self.receipt_id=''

    @property
    def total_quantity(self): return sum(float(x['quantity']) for x in self.items.values())

    def snapshot(self):
        return {'session_id':self.session_id,'stage':self.stage,'order_no':self.order_no,'items':list(self.items.values()),'destination':self.destination,'allocations':self.allocations,'total_quantity':self.total_quantity}


class ScanReceiptService:
    """V6.9 收貨狀態機：掃碼只建立意圖，commit 才能修改庫存。"""
    def __init__(self,session=None): self.session=session or ScanReceiptSession()

    def scan(self,code,default_warehouse=''):
        code=str(code or '').strip()
        if not code or any(ord(ch)<32 for ch in code): raise ScanReceiptError('條碼不可空白或包含控制字元。')
        if self.session.stage==ScanReceiptSession.ORDER: return self._order(code)
        if self.session.stage!=ScanReceiptSession.ITEMS: raise ScanReceiptError('此批次已進入覆核或結案，請先確認、取消或建立下一批。')
        resolved=ScannerService.resolve(code)
        if resolved.get('found'): return self._item(code,resolved)
        destination=IntegrationDbService.resolve_destination(code,default_warehouse)
        if destination: return self._destination(code,destination)
        self._audit('掃碼拒絕',code,'找不到貨品、容器或儲位 Mapping','失敗')
        raise ScanReceiptError('找不到貨品、容器或儲位 Mapping。')

    def _order(self,code):
        value=re.sub(r'^(ORDER|PO|單號)[:：]', '', code, flags=re.I).strip()
        if not 2<=len(value)<=80: raise ScanReceiptError('單號長度必須為 2～80 字元。')
        self.session.order_no=value; self.session.stage=ScanReceiptSession.ITEMS; self._audit('掃描單號',code,value); return self.session

    def _item(self,barcode,resolved):
        binding=resolved.get('binding') or {}; qty=float(binding.get('qty_per_scan',1) or 1)
        if qty<=0: raise ScanReceiptError('條碼每掃數量必須大於 0。')
        pno=str(resolved['product_no']); current=self.session.items.get(pno)
        if current: current['quantity']+=qty; current['scan_count']+=1
        else:
            product=resolved.get('product') or {}; group=str(product.get('產品分類') or product.get('分類') or product.get('品類') or '')
            self.session.items[pno]={'product_no':pno,'product_name':str(resolved.get('product_name','')),'product_group':group,'quantity':qty,'scan_count':1,'last_barcode':barcode}
        self._audit('掃描貨品',barcode,f'{pno} +{qty:g}'); return self.session

    def _destination(self,barcode,destination):
        if not self.session.items: raise ScanReceiptError('至少需要掃描一個貨品後才能指定容器／儲位。')
        names=WarehouseService.load_names(); allocations=[]
        for item in self.session.items.values():
            rule=IntegrationDbService.resolve_storage_rule(item['product_no'],item.get('product_group',''),destination) or {}
            warehouse=str(rule.get('warehouse') or destination.get('warehouse') or '').strip()
            if warehouse not in names: raise ScanReceiptError(f"品項 {item['product_no']} 的分配倉庫不存在：{warehouse or '空白'}")
            allocations.append({'product_no':item['product_no'],'product_name':item['product_name'],'quantity':item['quantity'],'container':destination['code'] if destination['kind']=='container' else '', 'location':str(rule.get('location') or destination.get('location') or ''),'zone':str(rule.get('zone') or destination.get('zone') or '待上架區'),'warehouse':warehouse,'rule_id':str(rule.get('rule_id') or 'destination-default')})
        self.session.destination=dict(destination); self.session.allocations=allocations; self.session.stage=ScanReceiptSession.REVIEW
        self._audit('掃描容器／儲位',barcode,f'完成 {len(allocations)} 品項分配'); return self.session

    def commit(self):
        if self.session.stage!=ScanReceiptSession.REVIEW: raise ScanReceiptError('尚未完成單號、貨品與目的地掃描。')
        security.require_tier('intermediate','智慧掃碼批次入庫'); security.require_write_access('智慧掃碼批次入庫')
        if not self.session.order_no or not self.session.items or len(self.session.allocations)!=len(self.session.items): raise ScanReceiptError('收貨批次資料不完整。')
        names=WarehouseService.load_names(); payload=self.session.snapshot(); row,created=IntegrationDbService.begin_receipt(self.session.session_id,self.session.order_no,payload)
        if not created:
            if row.get('status')=='committed': self.session.stage=ScanReceiptSession.COMMITTED; self.session.receipt_id=row['receipt_id']; return row['receipt_id']
            raise ScanReceiptError('此批次正在處理或曾失敗，為避免重複入庫，請由管理員檢查後處理。')
        before=WarehouseService.load_inventory(); after=deepcopy(before)
        try:
            for allocation in self.session.allocations:
                pno=allocation['product_no']; index=str(names.index(allocation['warehouse'])); record=dict(after.get(pno,{}) or {})
                record[index]=float(record.get(index,0) or 0)+float(allocation['quantity']); after[pno]=record
            WarehouseService.save_inventory(after)
            IntegrationDbService.finish_receipt(self.session.session_id,'committed')
            for item in self.session.items.values():
                IntegrationDbService.record_scan(barcode=item['last_barcode'],product_no=item['product_no'],product_name=item['product_name'],action='批次入庫',warehouse_to=next(a['warehouse'] for a in self.session.allocations if a['product_no']==item['product_no']),quantity=item['quantity'],status='completed',message=f"單號 {self.session.order_no}",idempotency_key=f"receipt:{self.session.session_id}:{item['product_no']}")
            IntegrationDbService.enqueue('receipt_batch',row['receipt_id'],'upsert',payload,'receipt:'+self.session.session_id)
        except Exception as exc:
            try: IntegrationDbService.finish_receipt(self.session.session_id,'failed',type(exc).__name__)
            except Exception: pass
            self._audit('批次入庫失敗',row['receipt_id'],type(exc).__name__,'失敗'); raise
        self.session.stage=ScanReceiptSession.COMMITTED; self.session.receipt_id=row['receipt_id']
        AuditLogService.log_event('智慧掃碼','批次入庫',record_id=row['receipt_id'],before={'order_no':self.session.order_no},after=payload,note=f"{len(self.session.items)} 品項／{self.session.total_quantity:g}")
        return row['receipt_id']

    def cancel(self,reason='使用者取消'):
        if self.session.stage==ScanReceiptSession.COMMITTED: raise ScanReceiptError('已入庫批次不可取消，請走沖銷流程。')
        self.session.stage=ScanReceiptSession.CANCELLED; self._audit('取消批次',self.session.session_id,str(reason)); return self.session

    def new_session(self): self.session=ScanReceiptSession(); return self.session

    def _audit(self,action,record_id,note,result='成功'):
        IntegrationDbService.record_scan(barcode=str(record_id),action=action,status='completed' if result=='成功' else 'rejected',message=str(note),idempotency_key=f"workflow:{self.session.session_id}:{uuid.uuid4()}")
        AuditLogService.log_event('智慧掃碼',action,record_id=str(record_id),after={'session_id':self.session.session_id,'stage':self.session.stage,'order_no':self.session.order_no},result=result,note=str(note))
