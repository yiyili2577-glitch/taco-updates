import json
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,QLineEdit,QComboBox,QDoubleSpinBox,QTabWidget,QTableWidget,QTableWidgetItem,QHeaderView,QMessageBox,QPlainTextEdit,QGroupBox,QFormLayout
from PyQt6.QtCore import Qt,QTimer
from PyQt6.QtGui import QFont
from services.integration_db_service import IntegrationDbService
from services.scanner_service import ScannerService
from services.mapping_service import MappingService
from services.product_master_service import ProductMasterService
from services.warehouse_service import WarehouseService
from services.audit_log_service import AuditLogService
from services.scan_receipt_service import ScanReceiptService,ScanReceiptSession
from ui.page_header import add_page_header

class IntegrationCenterPage(QWidget):
    def __init__(self):
        super().__init__(); self.receipt_workflow=ScanReceiptService(); self.build_ui(); self.refresh_all()
    def build_ui(self):
        root=QVBoxLayout(self); root.setContentsMargins(20,18,20,20); root.setSpacing(12)
        add_page_header(root,'智慧掃碼中心 / Mapping Center','USB 掃碼槍（鍵盤模擬）、產品條碼、欄位 Mapping 與 Local Integration Queue 集中作業；所有異動仍通過版本、角色、唯讀、業務規則與稽核安全層。')
        self.tabs=QTabWidget(); root.addWidget(self.tabs,1)
        self.scan_tab=QWidget(); self.bar_tab=QWidget(); self.map_tab=QWidget(); self.queue_tab=QWidget()
        for w,n in [(self.scan_tab,'📷 掃碼作業'),(self.bar_tab,'🏷 產品條碼'),(self.map_tab,'🔀 Mapping Center'),(self.queue_tab,'🔄 Local Integration')]: self.tabs.addTab(w,n)
        self._scan_ui(); self._bar_ui(); self._map_ui(); self._queue_ui()
    def _scan_ui(self):
        l=QVBoxLayout(self.scan_tab); l.setContentsMargins(16,16,16,16); l.setSpacing(12)
        flow=QHBoxLayout()
        self.scan_steps=[]
        for text in ('① 掃單號','② 連續掃多品項','③ 掃容器／儲位','④ 安全覆核入庫'):
            label=QLabel(text); label.setAlignment(Qt.AlignmentFlag.AlignCenter); label.setMinimumHeight(42); label.setStyleSheet('border:1px solid #bdd0df;border-radius:7px;background:#eaf2f8;color:#174c6e;font-size:14px;font-weight:700;padding:8px;'); flow.addWidget(label,1); self.scan_steps.append(label)
        l.addLayout(flow)
        box=QGroupBox('大型條碼輸入區（掃碼焦點固定，掃碼槍送出 Enter 即處理）'); box.setMinimumHeight(175); grid=QGridLayout(box); grid.setContentsMargins(20,22,20,18); grid.setHorizontalSpacing(14); grid.setVerticalSpacing(10)
        self.scan_code=QLineEdit(); self.scan_code.setObjectName('largeScannerInput'); self.scan_code.setPlaceholderText('等待掃描單號…'); self.scan_code.setMinimumHeight(78); font=QFont(); font.setPointSize(24); font.setBold(True); self.scan_code.setFont(font); self.scan_code.setAlignment(Qt.AlignmentFlag.AlignCenter); self.scan_code.returnPressed.connect(self.do_scan)
        self.scan_to=QComboBox(); self.scan_to.setMinimumHeight(42); self.scan_to.setToolTip('未建立容器 Mapping 時，BIN-/BOX- 條碼會使用此倉庫作為預設目的倉。')
        grid.addWidget(QLabel('條碼'),0,0); grid.addWidget(self.scan_code,0,1,1,5); grid.addWidget(QLabel('預設目的倉'),1,0); grid.addWidget(self.scan_to,1,1); self.scan_status=QLabel('1／4　等待掃描單號'); self.scan_status.setStyleSheet('font-size:16px;font-weight:700;color:#176b4d;padding:4px;'); grid.addWidget(self.scan_status,1,2,1,4)
        l.addWidget(box)
        summary=QHBoxLayout(); self.scan_summary=QLabel('品項 0 種｜總數量 0｜尚未指定容器／儲位'); self.scan_summary.setStyleSheet('font-size:14px;font-weight:600;color:#334e68;'); summary.addWidget(self.scan_summary,1)
        self.scan_commit=QPushButton('✅ 權限與規則檢查後確認入庫'); self.scan_commit.setMinimumHeight(46); self.scan_commit.clicked.connect(self.commit_receipt); self.scan_commit.setEnabled(False)
        cancel=QPushButton('取消本批'); cancel.clicked.connect(self.cancel_receipt); new=QPushButton('建立下一批'); new.clicked.connect(self.new_receipt)
        summary.addWidget(cancel); summary.addWidget(new); summary.addWidget(self.scan_commit); l.addLayout(summary)
        self.scan_alloc_table=QTableWidget(0,7); self.scan_alloc_table.setHorizontalHeaderLabels(['品項','名稱','數量','容器','儲位','區域','目的倉']); self.scan_alloc_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); self.scan_alloc_table.verticalHeader().setDefaultSectionSize(34); self.scan_alloc_table.setMinimumHeight(270); l.addWidget(self.scan_alloc_table,1)
        history=QGroupBox('最近掃碼／稽核事件'); history_l=QVBoxLayout(history); self.scan_table=QTableWidget(0,8); self.scan_table.setHorizontalHeaderLabels(['時間','條碼','產品編號','產品名稱','動作','數量','狀態','訊息']); self.scan_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); self.scan_table.setMaximumHeight(185); history_l.addWidget(self.scan_table); l.addWidget(history)
    def _bar_ui(self):
        l=QVBoxLayout(self.bar_tab); row=QHBoxLayout(); self.bar_code=QLineEdit(); self.bar_code.setPlaceholderText('條碼'); self.bar_product=QComboBox(); self.bar_qty=QDoubleSpinBox(); self.bar_qty.setRange(.0001,999999); self.bar_qty.setValue(1); self.bar_unit=QLineEdit(); self.bar_unit.setPlaceholderText('單位'); save=QPushButton('💾 儲存條碼'); save.clicked.connect(self.save_barcode); delete=QPushButton('🗑 刪除條碼'); delete.clicked.connect(self.delete_barcode)
        for w in (QLabel('條碼'),self.bar_code,QLabel('產品'),self.bar_product,QLabel('每掃數量'),self.bar_qty,self.bar_unit,save,delete): row.addWidget(w)
        l.addLayout(row); self.bar_table=QTableWidget(0,6); self.bar_table.setHorizontalHeaderLabels(['條碼','產品編號','產品名稱','單位','每掃數量','更新時間']); self.bar_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); l.addWidget(self.bar_table)
    def _map_ui(self):
        l=QVBoxLayout(self.map_tab); top=QHBoxLayout(); self.map_name=QLineEdit(); self.map_name.setPlaceholderText('例如：正航產品匯入 / A客戶訂單'); self.map_type=QComboBox(); self.map_type.addItems(['Excel','PDF','SQL Server','API','CSV','其他']); self.map_tenant=QLineEdit('local'); save=QPushButton('💾 儲存 Mapping Profile'); save.clicked.connect(self.save_mapping)
        for w in (QLabel('名稱'),self.map_name,QLabel('來源'),self.map_type,QLabel('Tenant'),self.map_tenant,save): top.addWidget(w)
        l.addLayout(top); hint=QLabel('每行格式：來源欄位 = TACO canonical 欄位。例：貨號 = product_no、貨品名稱 = product_name、數 = quantity'); hint.setWordWrap(True); l.addWidget(hint)
        self.map_editor=QPlainTextEdit(); self.map_editor.setPlaceholderText('貨號 = product_no\n貨品名稱 = product_name\n數 = quantity\n量 = unit'); l.addWidget(self.map_editor,1)
        self.map_table=QTableWidget(0,5); self.map_table.setHorizontalHeaderLabels(['Profile','來源','Tenant','欄位數','更新時間']); self.map_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); l.addWidget(self.map_table,1)
    def _queue_ui(self):
        l=QVBoxLayout(self.queue_tab); row=QHBoxLayout(); self.health_label=QLabel(); h=QPushButton('🩺 驗證 integration.db'); h.clicked.connect(self.show_health); rr=QPushButton('↻ 重新整理 Queue'); rr.clicked.connect(self.refresh_queue); row.addWidget(h); row.addWidget(rr); row.addWidget(self.health_label,1); l.addLayout(row)
        n=QLabel('V6.6 僅建立 Local Outbox/Queue，不會直接把公司資料傳上雲。V7.0 才接 HTTPS Cloud Sync。'); n.setWordWrap(True); l.addWidget(n)
        self.queue_table=QTableWidget(0,7); self.queue_table.setHorizontalHeaderLabels(['時間','類型','資料ID','操作','狀態','重試','最後錯誤']); self.queue_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch); l.addWidget(self.queue_table)
    def update_scan_fields(self):
        pass
    def refresh_all(self):
        IntegrationDbService.initialize(); names=WarehouseService.load_names(); current=self.scan_to.currentText(); self.scan_to.clear(); self.scan_to.addItems(names); index=self.scan_to.findText(current); self.scan_to.setCurrentIndex(index if index>=0 else 0)
        self.products=ProductMasterService.load_products(); self.bar_product.clear()
        for p in self.products: self.bar_product.addItem(f"{p.get('產品編號','')}｜{p.get('產品名稱','')}",str(p.get('產品編號','')))
        self.refresh_scans(); self.refresh_barcodes(); self.refresh_maps(); self.refresh_queue(); self.refresh_receipt_ui(); QTimer.singleShot(0,self.scan_code.setFocus)
    def do_scan(self):
        code=self.scan_code.text().strip()
        if not code:return
        try:
            self.receipt_workflow.scan(code,self.scan_to.currentText()); self.scan_code.clear()
        except Exception as e: self.scan_status.setText('⚠ '+str(e)); self.scan_status.setStyleSheet('font-size:16px;font-weight:700;color:#b42318;padding:4px;')
        self.refresh_receipt_ui(); self.refresh_scans(); self.refresh_queue(); self.scan_code.setFocus()

    def refresh_receipt_ui(self):
        s=self.receipt_workflow.session; labels={ScanReceiptSession.ORDER:'1／4　等待掃描單號',ScanReceiptSession.ITEMS:f'2／4　單號 {s.order_no}｜請連續掃貨品，完成後掃容器／儲位',ScanReceiptSession.REVIEW:'3／4　分配完成，等待安全覆核',ScanReceiptSession.COMMITTED:f'4／4　安全入庫完成：{s.receipt_id}',ScanReceiptSession.CANCELLED:'本批次已取消'}
        self.scan_status.setText(labels.get(s.stage,s.stage)); self.scan_status.setStyleSheet('font-size:16px;font-weight:700;color:#176b4d;padding:4px;')
        self.scan_code.setPlaceholderText('等待掃描單號…' if s.stage==ScanReceiptSession.ORDER else '連續掃描貨品；完成後掃 BOX-/BIN- 容器或儲位…')
        alloc={x['product_no']:x for x in s.allocations}; self.scan_alloc_table.setRowCount(len(s.items))
        for i,item in enumerate(s.items.values()):
            a=alloc.get(item['product_no'],{}); vals=[item['product_no'],item['product_name'],f"{item['quantity']:g}",a.get('container','—'),a.get('location','—'),a.get('zone','—'),a.get('warehouse','等待目的地')]
            for j,v in enumerate(vals): self.scan_alloc_table.setItem(i,j,QTableWidgetItem(str(v)))
        destination=(s.destination or {}).get('code','尚未指定容器／儲位'); self.scan_summary.setText(f'品項 {len(s.items)} 種｜總數量 {s.total_quantity:g}｜{destination}'); self.scan_commit.setEnabled(s.stage==ScanReceiptSession.REVIEW)

    def commit_receipt(self):
        answer=QMessageBox.question(self,'確認安全入庫',f"單號：{self.receipt_workflow.session.order_no}\n品項：{len(self.receipt_workflow.session.items)} 種\n總數量：{self.receipt_workflow.session.total_quantity:g}\n\n確認後才會經權限、唯讀、業務規則、事件與稽核層修改庫存。")
        if answer!=QMessageBox.StandardButton.Yes: self.scan_code.setFocus(); return
        try:
            receipt=self.receipt_workflow.commit(); QMessageBox.information(self,'入庫完成',f'收貨批次：{receipt}\n已安全寫入庫存並建立稽核與同步事件。')
        except Exception as e: QMessageBox.warning(self,'入庫失敗',str(e))
        self.refresh_receipt_ui(); self.refresh_scans(); self.refresh_queue(); self.scan_code.setFocus()

    def cancel_receipt(self):
        try: self.receipt_workflow.cancel(); self.refresh_receipt_ui()
        except Exception as e: QMessageBox.warning(self,'無法取消',str(e))
        self.scan_code.setFocus()

    def new_receipt(self):
        self.receipt_workflow.new_session(); self.refresh_receipt_ui(); self.scan_code.clear(); self.scan_code.setFocus()
    def refresh_scans(self):
        rows=IntegrationDbService.list_scans(); self.scan_table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            for j,v in enumerate([r['scanned_at'],r['barcode'],r['product_no'],r['product_name'],r['action'],f"{r['quantity']:g}",r['status'],r['message']]): self.scan_table.setItem(i,j,QTableWidgetItem(str(v)))
    def save_barcode(self):
        try:
            pno=self.bar_product.currentData(); IntegrationDbService.upsert_barcode(self.bar_code.text(),pno,self.bar_unit.text(),self.bar_qty.value()); AuditLogService.log_event('智慧掃碼','條碼設定',record_id=self.bar_code.text(),after={'產品編號':pno}); self.refresh_barcodes()
        except Exception as e: QMessageBox.warning(self,'儲存失敗',str(e))
    def delete_barcode(self):
        try: IntegrationDbService.delete_barcode(self.bar_code.text()); AuditLogService.log_event('智慧掃碼','刪除條碼',record_id=self.bar_code.text()); self.refresh_barcodes()
        except Exception as e: QMessageBox.warning(self,'刪除失敗',str(e))
    def refresh_barcodes(self):
        rows=IntegrationDbService.list_barcodes(); pmap={str(p.get('產品編號','')):str(p.get('產品名稱','')) for p in self.products}; self.bar_table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            for j,v in enumerate([r['barcode'],r['product_no'],pmap.get(r['product_no'],''),r['unit'],f"{r['qty_per_scan']:g}",r['updated_at']]): self.bar_table.setItem(i,j,QTableWidgetItem(str(v)))
    def save_mapping(self):
        mappings={}
        for line in self.map_editor.toPlainText().splitlines():
            if '=' in line:
                a,b=line.split('=',1); mappings[a.strip()]=b.strip()
        errs=MappingService.validate_mapping(mappings)
        if errs: QMessageBox.warning(self,'Mapping 錯誤','\n'.join(errs)); return
        try:
            pid=IntegrationDbService.save_mapping_profile(self.map_name.text(),self.map_type.currentText(),mappings,self.map_tenant.text()); AuditLogService.log_event('Mapping Center','儲存 Profile',record_id=pid,after={'name':self.map_name.text(),'mappings':mappings}); self.refresh_maps()
        except Exception as e: QMessageBox.warning(self,'儲存失敗',str(e))
    def refresh_maps(self):
        rows=IntegrationDbService.list_mapping_profiles(); self.map_table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            for j,v in enumerate([r['name'],r['source_type'],r['tenant_id'],len(r['mappings']),r['updated_at']]): self.map_table.setItem(i,j,QTableWidgetItem(str(v)))
    def refresh_queue(self):
        rows=IntegrationDbService.list_queue(); self.queue_table.setRowCount(len(rows))
        for i,r in enumerate(rows):
            for j,v in enumerate([r['created_at'],r['entity_type'],r['entity_id'],r['operation'],r['status'],r['retry_count'],r['last_error']]): self.queue_table.setItem(i,j,QTableWidgetItem(str(v)))
        h=IntegrationDbService.health(); self.health_label.setText(f"DB：{'✅' if h.get('ok') else '❌'}｜WAL：{h.get('journal_mode','')}｜Queue：{h.get('counts',{}).get('sync_queue',0)}")
    def show_health(self): QMessageBox.information(self,'integration.db 驗證',json.dumps(IntegrationDbService.health(),ensure_ascii=False,indent=2))
