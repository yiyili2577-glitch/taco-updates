from datetime import date

import pandas as pd
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QDialog,
    QFormLayout, QDoubleSpinBox, QLineEdit, QDialogButtonBox, QComboBox,
    QGroupBox, QGridLayout, QAbstractItemView, QSpinBox
)

from services.financial_service import FinancialService
from services.table_export_service import TableExportService
from ui.responsive_action_bar import FlowLayout, compact_button
from ui.two_row_tab_widget import TwoRowTabWidget



class PaymentDialog(QDialog):
    def __init__(self, payable, parent=None):
        super().__init__(parent)
        self.payable = payable
        self.setWindowTitle("記錄供應商付款")
        self.setMinimumWidth(460)
        layout = QFormLayout(self)
        remaining = FinancialService._open_payable(payable)
        layout.addRow("應付", QLabel(f"{payable.get('supplier','')}｜{payable.get('product_no','')} {payable.get('product_name','')}"))
        layout.addRow("未付", QLabel(f"{payable.get('currency','')} {remaining:,.2f}"))
        self.amount = QDoubleSpinBox(); self.amount.setDecimals(6); self.amount.setMaximum(max(remaining, 0)); self.amount.setValue(remaining)
        self.payment_date = QLineEdit(date.today().isoformat())
        self.fx = QDoubleSpinBox(); self.fx.setDecimals(6); self.fx.setMaximum(9999); self.fx.setValue(FinancialService.get_rate(payable.get("currency","")))
        self.fee = QDoubleSpinBox(); self.fee.setDecimals(2); self.fee.setMaximum(999999999)
        self.note = QLineEdit()
        layout.addRow("付款金額（原幣）", self.amount); layout.addRow("付款日期", self.payment_date)
        layout.addRow("付款匯率 → TWD", self.fx); layout.addRow("銀行手續費 TWD", self.fee); layout.addRow("備註", self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addRow(buttons)


class ReceiptDialog(QDialog):
    def __init__(self, receivable, parent=None):
        super().__init__(parent)
        self.receivable = receivable
        self.setWindowTitle("記錄客戶收款")
        self.setMinimumWidth(460)
        layout = QFormLayout(self)
        remaining = FinancialService._open_receivable(receivable)
        layout.addRow("應收", QLabel(f"{receivable.get('customer','')}｜{receivable.get('product_no','')} {receivable.get('product_name','')}"))
        layout.addRow("未收", QLabel(f"{receivable.get('currency','')} {remaining:,.2f}"))
        self.amount = QDoubleSpinBox(); self.amount.setDecimals(6); self.amount.setMaximum(max(remaining, 0)); self.amount.setValue(remaining)
        self.receipt_date = QLineEdit(date.today().isoformat())
        self.fx = QDoubleSpinBox(); self.fx.setDecimals(6); self.fx.setMaximum(9999); self.fx.setValue(FinancialService.get_rate(receivable.get("currency","")))
        self.fee = QDoubleSpinBox(); self.fee.setDecimals(2); self.fee.setMaximum(999999999)
        self.note = QLineEdit()
        layout.addRow("收款金額（原幣）", self.amount); layout.addRow("收款日期", self.receipt_date)
        layout.addRow("收款匯率 → TWD", self.fx); layout.addRow("銀行手續費 TWD", self.fee); layout.addRow("備註", self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addRow(buttons)


class ReceivableDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("新增客戶應收"); self.setMinimumWidth(520)
        layout = QFormLayout(self)
        self.customer = QLineEdit(); self.order_no = QLineEdit(); self.product_no = QLineEdit(); self.product_name = QLineEdit()
        self.qty = QDoubleSpinBox(); self.qty.setDecimals(4); self.qty.setMaximum(999999999)
        self.qty_unit = QLineEdit(); self.currency = QComboBox(); self.currency.setEditable(True); self.currency.addItems(["TWD","USD","CNY","JPY","EUR"])
        self.unit_price = QDoubleSpinBox(); self.unit_price.setDecimals(6); self.unit_price.setMaximum(999999999)
        self.total = QDoubleSpinBox(); self.total.setDecimals(2); self.total.setMaximum(999999999999)
        self.invoice_date = QLineEdit(date.today().isoformat()); self.due_date = QLineEdit(); self.note = QLineEdit()
        layout.addRow("客戶 *", self.customer); layout.addRow("客戶訂號", self.order_no); layout.addRow("產品編號", self.product_no)
        layout.addRow("產品名稱", self.product_name); layout.addRow("數量", self.qty); layout.addRow("數量單位", self.qty_unit)
        layout.addRow("幣別", self.currency); layout.addRow("單價", self.unit_price); layout.addRow("總額（填 0 則用數量×單價）", self.total)
        layout.addRow("開立日期", self.invoice_date); layout.addRow("到期日", self.due_date); layout.addRow("備註", self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addRow(buttons)


class ExpenseDialog(QDialog):
    CATEGORIES = ["運費", "報關費", "倉儲費", "辦公費", "薪資", "租金", "水電", "銀行手續費", "差旅", "其他"]
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("新增費用"); self.setMinimumWidth(500)
        layout = QFormLayout(self)
        self.expense_date = QLineEdit(date.today().isoformat())
        self.category = QComboBox(); self.category.setEditable(True); self.category.addItems(self.CATEGORIES)
        self.vendor = QLineEdit(); self.reference = QLineEdit(); self.currency = QComboBox(); self.currency.setEditable(True); self.currency.addItems(["TWD","USD","CNY","JPY","EUR"])
        self.amount = QDoubleSpinBox(); self.amount.setDecimals(2); self.amount.setMaximum(999999999999)
        self.fx = QDoubleSpinBox(); self.fx.setDecimals(6); self.fx.setMaximum(9999); self.fx.setValue(1.0)
        self.note = QLineEdit()
        layout.addRow("日期", self.expense_date); layout.addRow("費用類別", self.category); layout.addRow("對象 / 廠商", self.vendor)
        layout.addRow("憑證 / 單號", self.reference); layout.addRow("幣別", self.currency); layout.addRow("金額", self.amount)
        layout.addRow("匯率 → TWD", self.fx); layout.addRow("備註", self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addRow(buttons)


class ShipmentCostDialog(QDialog):
    COST_LABELS = {
        "ocean_freight":"海運費", "customs":"報關費", "tariff":"關稅", "import_tax":"進口營業稅",
        "trucking":"拖車費", "storage":"倉儲費", "document_fee":"文件費", "bank_fee":"銀行手續費", "other":"其他費用",
    }
    def __init__(self, shipment, parent=None):
        super().__init__(parent); self.shipment=shipment; self.inputs={}; self.setWindowTitle("進口共同成本"); self.setMinimumWidth(480)
        layout=QFormLayout(self); layout.addRow("批次", QLabel(str(shipment.get("id","")))); layout.addRow("總 CBM", QLabel(f"{FinancialService._num(shipment.get('total_cbm')):,.2f}"))
        costs=shipment.get("costs_twd",{})
        for key,label in self.COST_LABELS.items():
            spin=QDoubleSpinBox(); spin.setDecimals(2); spin.setMaximum(999999999); spin.setValue(FinancialService._num(costs.get(key,0))); self.inputs[key]=spin; layout.addRow(f"{label} TWD", spin)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addRow(buttons)
    def costs(self): return {k:w.value() for k,w in self.inputs.items()}


class CustomerTermsDialog(QDialog):
    TERM_CODES = ["CASH", "NET7", "NET15", "NET30", "NET45", "NET60", "NET90", "EOM", "EOM30", "EOM60"]
    def __init__(self, record=None, parent=None):
        super().__init__(parent); self.record=record or {}; self.setWindowTitle("客戶信用 / 帳款條件"); self.setMinimumWidth(520)
        f=QFormLayout(self)
        self.customer=QLineEdit(str(self.record.get("customer","")))
        self.credit=QDoubleSpinBox(); self.credit.setDecimals(2); self.credit.setMaximum(999999999999); self.credit.setValue(FinancialService._num(self.record.get("credit_limit_twd",0)))
        self.term=QComboBox(); self.term.setEditable(True); self.term.addItems(self.TERM_CODES); self.term.setCurrentText(str(self.record.get("term_code","NET30")))
        self.currency=QComboBox(); self.currency.setEditable(True); self.currency.addItems(["TWD","USD","CNY","JPY","EUR"]); self.currency.setCurrentText(str(self.record.get("default_currency","TWD")))
        self.warning=QDoubleSpinBox(); self.warning.setRange(1,100); self.warning.setDecimals(0); self.warning.setValue(FinancialService._num(self.record.get("warning_pct",80)) or 80)
        self.policy=QComboBox(); self.policy.addItems(["警示","禁止超額"]); self.policy.setCurrentText(str(self.record.get("credit_policy","警示")))
        self.note=QLineEdit(str(self.record.get("note","")))
        f.addRow("客戶 *",self.customer); f.addRow("信用額度 TWD",self.credit); f.addRow("帳款條件",self.term); f.addRow("預設幣別",self.currency); f.addRow("額度警示 %",self.warning); f.addRow("超額政策",self.policy); f.addRow("備註",self.note)
        hint=QLabel("帳款條件：NET30=發票日+30天；EOM30=發票當月底+30天；CASH=發票日到期。信用額度 0 代表尚未設定額度。")
        hint.setWordWrap(True); f.addRow(hint)
        b=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel); b.accepted.connect(self.accept); b.rejected.connect(self.reject); f.addRow(b)


class InvoiceIssueDialog(QDialog):
    def __init__(self, receivables, parent=None):
        super().__init__(parent); self.setWindowTitle("正式開立銷售發票"); self.setMinimumWidth(600); f=QFormLayout(self)
        self.receivable=QComboBox()
        for r in receivables:
            if FinancialService._text(r.get("invoice_no")): continue
            remain=FinancialService._open_receivable(r)
            self.receivable.addItem(f"{r.get('id','')}｜{r.get('customer','')}｜{r.get('currency','')} {remain:,.2f}｜{r.get('product_name','')}", r.get("id"))
        self.invoice_no=QLineEdit(); self.invoice_date=QLineEdit(date.today().isoformat())
        self.tax_rate=QDoubleSpinBox(); self.tax_rate.setRange(0,100); self.tax_rate.setDecimals(2); self.tax_rate.setValue(5.0)
        self.term=QComboBox(); self.term.setEditable(True); self.term.addItems(CustomerTermsDialog.TERM_CODES); self.term.setCurrentText("")
        f.addRow("待開票應收",self.receivable); f.addRow("發票號碼 *",self.invoice_no); f.addRow("發票日期",self.invoice_date); f.addRow("營業稅率 %",self.tax_rate); f.addRow("帳款條件（空白=客戶設定）",self.term)
        hint=QLabel("此功能不會重複建立應收，而是把既有應收正式轉成『已開票』，並依客戶帳款條件自動計算到期日。")
        hint.setWordWrap(True); f.addRow(hint)
        b=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel); b.accepted.connect(self.accept); b.rejected.connect(self.reject); f.addRow(b)


class ExpectedPaymentDialog(QDialog):
    def __init__(self, payable, parent=None):
        super().__init__(parent); self.setWindowTitle("設定預計付款日"); self.setMinimumWidth(430); f=QFormLayout(self)
        self.expected=QLineEdit(str(payable.get("expected_payment_date","") or date.today().isoformat()))
        f.addRow("供應商",QLabel(str(payable.get("supplier","")))); f.addRow("應付編號",QLabel(str(payable.get("id","")))); f.addRow("預計付款日",self.expected)
        b=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel); b.accepted.connect(self.accept); b.rejected.connect(self.reject); f.addRow(b)


class CashPlanDialog(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent); self.setWindowTitle("新增預計現金流"); self.setMinimumWidth(500); f=QFormLayout(self)
        self.plan_date=QLineEdit(date.today().isoformat()); self.direction=QComboBox(); self.direction.addItems(["流入","流出"]); self.category=QComboBox(); self.category.setEditable(True); self.category.addItems(["預計收款","預計付款","薪資","租金","稅費","其他"]); self.counterparty=QLineEdit(); self.currency=QComboBox(); self.currency.setEditable(True); self.currency.addItems(["TWD","USD","CNY","JPY","EUR"]); self.amount=QDoubleSpinBox(); self.amount.setDecimals(2); self.amount.setMaximum(999999999999); self.note=QLineEdit()
        f.addRow("日期",self.plan_date); f.addRow("方向",self.direction); f.addRow("類別",self.category); f.addRow("對象",self.counterparty); f.addRow("幣別",self.currency); f.addRow("金額",self.amount); f.addRow("備註",self.note)
        b=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel); b.accepted.connect(self.accept); b.rejected.connect(self.reject); f.addRow(b)



class SalesOrderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("新增正式銷售訂單"); self.setMinimumWidth(540); f=QFormLayout(self)
        self.customer=QLineEdit(); self.order_no=QLineEdit(); self.order_date=QLineEdit(date.today().isoformat()); self.promised=QLineEdit()
        self.product_no=QLineEdit(); self.product_name=QLineEdit(); self.qty=QDoubleSpinBox(); self.qty.setDecimals(4); self.qty.setMaximum(999999999)
        self.qty_unit=QLineEdit(); self.currency=QComboBox(); self.currency.setEditable(True); self.currency.addItems(["TWD","USD","CNY","JPY","EUR"])
        self.unit_price=QDoubleSpinBox(); self.unit_price.setDecimals(6); self.unit_price.setMaximum(999999999); self.note=QLineEdit()
        for label, widget in [("客戶 *",self.customer),("客戶訂號",self.order_no),("訂單日期",self.order_date),("預計交貨日",self.promised),("產品編號 *",self.product_no),("產品名稱",self.product_name),("訂購數量 *",self.qty),("數量單位",self.qty_unit),("幣別",self.currency),("單價",self.unit_price),("備註",self.note)]: f.addRow(label,widget)
        hint=QLabel("單價可留 0；系統會優先查找『客戶＋產品』銷售價格主檔。沒有價格時仍可建立訂單，但出貨後建立應收前必須補齊售價。")
        hint.setWordWrap(True); f.addRow(hint)
        b=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel); b.accepted.connect(self.accept); b.rejected.connect(self.reject); f.addRow(b)


class DeliveryDialog(QDialog):
    def __init__(self, order, parent=None):
        super().__init__(parent); self.order=order; self.setWindowTitle("記錄銷售出貨"); self.setMinimumWidth(500); f=QFormLayout(self)
        remain=max(0.0,FinancialService._num(order.get("order_qty"))-FinancialService._num(order.get("delivered_qty")))
        f.addRow("銷售訂單",QLabel(str(order.get("id","")))); f.addRow("客戶",QLabel(str(order.get("customer","")))); f.addRow("未出貨",QLabel(f"{remain:,.2f} {order.get('qty_unit','')}"))
        self.qty=QDoubleSpinBox(); self.qty.setDecimals(4); self.qty.setMaximum(remain); self.qty.setValue(remain)
        self.delivery_date=QLineEdit(date.today().isoformat()); self.delivery_no=QLineEdit(); self.warehouse=QLineEdit(); self.carrier=QLineEdit(); self.note=QLineEdit()
        for label,widget in [("本次出貨數量",self.qty),("出貨日期",self.delivery_date),("出貨單號",self.delivery_no),("出貨倉",self.warehouse),("承運商",self.carrier),("備註",self.note)]: f.addRow(label,widget)
        b=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel); b.accepted.connect(self.accept); b.rejected.connect(self.reject); f.addRow(b)


class CollectionActionDialog(QDialog):
    def __init__(self, record, parent=None):
        super().__init__(parent); self.setWindowTitle("新增應收催收紀錄"); self.setMinimumWidth(500); f=QFormLayout(self)
        f.addRow("客戶",QLabel(str(record.get("客戶","")))); f.addRow("發票",QLabel(str(record.get("發票號碼","")))); f.addRow("未收",QLabel(f"{record.get('幣別','')} {FinancialService._num(record.get('未收金額')):,.2f}"))
        self.action_date=QLineEdit(date.today().isoformat()); self.method=QComboBox(); self.method.setEditable(True); self.method.addItems(["電話","Email","LINE","簡訊","對帳單","業務聯繫","其他"])
        self.result=QLineEdit(); self.next_followup=QLineEdit(); self.note=QLineEdit()
        for label,widget in [("催收日期",self.action_date),("方式",self.method),("結果",self.result),("下次追蹤日",self.next_followup),("備註",self.note)]: f.addRow(label,widget)
        b=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel); b.accepted.connect(self.accept); b.rejected.connect(self.reject); f.addRow(b)


class SalesAdjustmentDialog(QDialog):
    def __init__(self, receivables, mode="退貨", parent=None):
        super().__init__(parent); self.mode=mode; self.setWindowTitle("銷售退貨" if mode=="退貨" else "發票折讓"); self.setMinimumWidth(600); f=QFormLayout(self)
        self.target=QComboBox()
        for r in receivables:
            open_amt=FinancialService._open_receivable(r)
            if open_amt>1e-9 or FinancialService._num(r.get("total_amount"))>0:
                self.target.addItem(f"{r.get('customer','')}｜{r.get('invoice_no') or r.get('id')}｜{r.get('currency','')} {open_amt:,.2f}",r.get('id'))
        self.biz_date=QLineEdit(date.today().isoformat()); self.qty=QDoubleSpinBox(); self.qty.setDecimals(4); self.qty.setMaximum(999999999)
        self.amount=QDoubleSpinBox(); self.amount.setDecimals(6); self.amount.setMaximum(999999999999); self.reason=QLineEdit(); self.note=QLineEdit()
        self.allowance_no=QLineEdit(); self.restock=QComboBox(); self.restock.addItems(["是","否"])
        f.addRow("應收 / 發票",self.target); f.addRow("日期",self.biz_date)
        if mode=="退貨": f.addRow("退貨數量（可 0）",self.qty); f.addRow("退回庫存",self.restock)
        else: f.addRow("折讓單號 *",self.allowance_no)
        f.addRow("金額 *",self.amount); f.addRow("原因",self.reason); f.addRow("備註",self.note)
        hint=QLabel("退貨／折讓先建立憑證，再按『沖帳』才會真正減少應收餘額；這樣可以保留完整追蹤歷程。" if mode=="退貨" else "發票折讓必須對應已開立的正式發票；建立後仍需沖帳。")
        hint.setWordWrap(True); f.addRow(hint)
        b=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel); b.accepted.connect(self.accept); b.rejected.connect(self.reject); f.addRow(b)

class PurchaseReturnDialog(QDialog):
    def __init__(self, payables, parent=None):
        super().__init__(parent); self.setWindowTitle("進貨退貨"); self.setMinimumWidth(600); f=QFormLayout(self); self.target=QComboBox()
        for p in payables:
            self.target.addItem(f"{p.get('supplier','')}｜{p.get('id','')}｜{p.get('currency','')} {FinancialService._open_payable(p):,.2f}",p.get('id'))
        self.biz_date=QLineEdit(date.today().isoformat()); self.qty=QDoubleSpinBox(); self.qty.setDecimals(4); self.qty.setMaximum(999999999); self.amount=QDoubleSpinBox(); self.amount.setDecimals(6); self.amount.setMaximum(999999999999); self.reason=QLineEdit(); self.note=QLineEdit()
        for label,w in [("應付",self.target),("退貨日期",self.biz_date),("退貨數量（可 0）",self.qty),("退貨金額 *",self.amount),("原因",self.reason),("備註",self.note)]: f.addRow(label,w)
        hint=QLabel("進貨退貨先建立退貨憑證，再沖帳至原始應付；現金付款紀錄不會被改寫。" ); hint.setWordWrap(True); f.addRow(hint)
        b=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel); b.accepted.connect(self.accept); b.rejected.connect(self.reject); f.addRow(b)

class SettlementDialog(QDialog):
    def __init__(self, record, parent=None):
        super().__init__(parent); self.setWindowTitle("沖帳"); self.setMinimumWidth(460); f=QFormLayout(self); remain=max(0.0,FinancialService._num(record.get("amount"))-FinancialService._num(record.get("settled_amount")))
        f.addRow("調整單",QLabel(str(record.get("id","")))); f.addRow("待沖金額",QLabel(f"{record.get('currency','')} {remain:,.2f}")); self.amount=QDoubleSpinBox(); self.amount.setDecimals(6); self.amount.setMaximum(remain); self.amount.setValue(remain); self.biz_date=QLineEdit(date.today().isoformat()); f.addRow("本次沖帳金額",self.amount); f.addRow("沖帳日期",self.biz_date)
        b=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel); b.accepted.connect(self.accept); b.rejected.connect(self.reject); f.addRow(b)

class FinancePage(QWidget):
    def __init__(self):
        super().__init__(); self.setObjectName("financePage"); self.build_ui(); self.refresh_all()

    def _flow_bar(self):
        holder = QWidget(); flow = FlowLayout(holder, margin=0, h_spacing=8, v_spacing=7); return holder, flow

    def build_ui(self):
        root=QVBoxLayout(self); root.setContentsMargins(20,18,20,20); root.setSpacing(12)
        title=QLabel("財務中心"); title.setObjectName("pageTitle")
        subtitle=QLabel("V6.8：升級為雙排流程頁籤與更清楚的 ERP 工作視圖。保留 V6.5～V6.6 全部財務能力，並將常用作業依實際順手度集中呈現。")
        subtitle.setWordWrap(True); subtitle.setObjectName("pageSubtitle"); root.addWidget(title); root.addWidget(subtitle)
        self.tabs=TwoRowTabWidget(columns=11); root.addWidget(self.tabs,1)
        self.tabs.addTab(self._dashboard_tab(), "① 財務儀表板")
        self.tabs.addTab(self._payable_tab(), "② 採購應付")
        self.tabs.addTab(self._payment_tab(), "③ 供應商付款")
        self.tabs.addTab(self._receivable_tab(), "④ 客戶應收")
        self.tabs.addTab(self._receipt_tab(), "⑤ 客戶收款")
        self.tabs.addTab(self._expense_tab(), "⑥ 費用管理")
        self.tabs.addTab(self._shipment_tab(), "⑦ 進口成本")
        self.tabs.addTab(self._rate_tab(), "⑧ 匯率管理")
        self.tabs.addTab(self._margin_tab(), "⑨ 毛利分析")
        self.tabs.addTab(self._sales_price_tab(), "⑩ 銷售價格主檔")
        self.tabs.addTab(self._aging_tab(), "⑪ 應收帳齡 / 逾期")
        self.tabs.addTab(self._management_tab(), "⑫ 現金流 / 管理排行")
        self.tabs.addTab(self._credit_tab(), "⑬ 客戶信用 / 帳款條件")
        self.tabs.addTab(self._invoice_tab(), "⑭ 正式發票 / 應收")
        self.tabs.addTab(self._forecast_tab(), "⑮ 現金流預測")
        self.tabs.addTab(self._sales_order_tab(), "⑯ 銷售訂單")
        self.tabs.addTab(self._delivery_tab(), "⑰ 出貨 / 發票整合")
        self.tabs.addTab(self._statement_collection_tab(), "⑱ 對帳單 / 催收")
        self.tabs.addTab(self._payment_schedule_tab(), "⑲ 付款排程")
        self.tabs.addTab(self._sales_adjustment_tab(), "⑳ 銷售退貨 / 發票折讓")
        self.tabs.addTab(self._purchase_return_tab(), "㉑ 進貨退貨 / 沖帳")
        self.tabs.addTab(self._month_close_tab(), "㉒ 月結作業")

    def _dashboard_tab(self):
        w=QWidget(); l=QVBoxLayout(w); box=QGroupBox("財務摘要"); grid=QGridLayout(box); self.sum_labels={}
        keys=["未付原幣","未收原幣","已付款TWD","已收款TWD","費用TWD","估算毛利TWD","毛利率","缺成本品項","信用超額客戶","30天期末現金","待出貨訂單","30天付款排程"]
        for i,key in enumerate(keys):
            card=QGroupBox(key); cl=QVBoxLayout(card); value=QLabel("0"); value.setStyleSheet("font-size:22px;font-weight:900;"); value.setWordWrap(True); cl.addWidget(value); self.sum_labels[key]=value; grid.addWidget(card,i//4,i%4)
        l.addWidget(box)
        hint=QLabel("提示：毛利屬管理估算。V6.3 另加入正式發票、客戶信用與未來現金流；外幣資料若尚未設定匯率，會標示為缺少匯率並排除該筆預測，避免把金額誤算成 0。")
        hint.setWordWrap(True); l.addWidget(hint); l.addStretch(); return w

    def _payable_tab(self):
        w=QWidget(); l=QVBoxLayout(w); holder,tools=self._flow_bar()
        self.btn_sync=compact_button(QPushButton("🔄 同步目前採購建議"), primary=True); self.btn_sync.clicked.connect(self.sync_payables)
        self.btn_pay=compact_button(QPushButton("💳 記錄付款")); self.btn_pay.clicked.connect(self.record_payment)
        self.btn_expected=compact_button(QPushButton("📅 預計付款日")); self.btn_expected.clicked.connect(self.set_expected_payment_date)
        b1=compact_button(QPushButton("📊 匯出 Excel")); b1.clicked.connect(lambda: self.export_table(self.payable_table,"採購應付","xlsx"))
        b2=compact_button(QPushButton("📄 匯出 PDF")); b2.clicked.connect(lambda: self.export_table(self.payable_table,"採購應付","pdf"))
        for b in [self.btn_sync,self.btn_pay,self.btn_expected,b1,b2]: tools.addWidget(b)
        l.addWidget(holder); self.payable_table=self._table(); l.addWidget(self.payable_table,1); return w

    def _payment_tab(self):
        w=QWidget(); l=QVBoxLayout(w); self.payment_table=self._table(); l.addWidget(self.payment_table,1); return w

    def _receivable_tab(self):
        w=QWidget(); l=QVBoxLayout(w); holder,tools=self._flow_bar()
        sync=compact_button(QPushButton("🔄 從客戶需求同步應收"), primary=True); sync.clicked.connect(self.sync_receivables)
        add=compact_button(QPushButton("＋ 新增應收")); add.clicked.connect(self.add_receivable)
        receipt=compact_button(QPushButton("💰 記錄收款")); receipt.clicked.connect(self.record_receipt)
        x=compact_button(QPushButton("📊 匯出 Excel")); x.clicked.connect(lambda: self.export_table(self.receivable_table,"客戶應收","xlsx"))
        p=compact_button(QPushButton("📄 匯出 PDF")); p.clicked.connect(lambda: self.export_table(self.receivable_table,"客戶應收","pdf"))
        for b in [sync,add,receipt,x,p]: tools.addWidget(b)
        l.addWidget(holder)
        note=QLabel("正式流程：客戶需求 → 同步成待開票應收 → 開立正式發票 → 自動計算帳款到期日 → 收款 / 帳齡 / 信用額度 / 現金流預測。客戶需求若沒有銷售價格，會優先使用『銷售價格主檔』；仍沒有價格時才跳過，不會自動猜價。")
        note.setWordWrap(True); l.addWidget(note); self.receivable_table=self._table(); l.addWidget(self.receivable_table,1); return w

    def _receipt_tab(self):
        w=QWidget(); l=QVBoxLayout(w); self.receipt_table=self._table(); l.addWidget(self.receipt_table,1); return w

    def _expense_tab(self):
        w=QWidget(); l=QVBoxLayout(w); holder,tools=self._flow_bar(); add=compact_button(QPushButton("＋ 新增費用"), primary=True); add.clicked.connect(self.add_expense)
        x=compact_button(QPushButton("📊 匯出 Excel")); x.clicked.connect(lambda:self.export_table(self.expense_table,"費用管理","xlsx"))
        p=compact_button(QPushButton("📄 匯出 PDF")); p.clicked.connect(lambda:self.export_table(self.expense_table,"費用管理","pdf"))
        for b in [add,x,p]: tools.addWidget(b)
        l.addWidget(holder); self.expense_table=self._table(); l.addWidget(self.expense_table,1); return w

    def _shipment_tab(self):
        w=QWidget(); l=QVBoxLayout(w); holder,tools=self._flow_bar(); self.btn_cost=compact_button(QPushButton("✏ 編輯共同成本")); self.btn_cost.clicked.connect(self.edit_shipment_cost)
        refresh=compact_button(QPushButton("重新整理")); refresh.clicked.connect(self.refresh_all); tools.addWidget(self.btn_cost); tools.addWidget(refresh); l.addWidget(holder)
        note=QLabel("進口批次由『採購建議 → 混櫃規劃 → 建立進口成本批次』產生。下方選取批次後會同步顯示該批次落地成本。")
        note.setWordWrap(True); l.addWidget(note); self.shipment_table=self._table(); l.addWidget(self.shipment_table,1)
        line=QHBoxLayout(); self.cost_shipment=QComboBox(); self.cost_shipment.currentIndexChanged.connect(self.refresh_cost_analysis); line.addWidget(QLabel("成本分析批次")); line.addWidget(self.cost_shipment); line.addStretch(); l.addLayout(line)
        self.cost_summary=QLabel(""); self.cost_summary.setStyleSheet("font-weight:800;"); l.addWidget(self.cost_summary); self.cost_table=self._table(); l.addWidget(self.cost_table,1); return w

    def _rate_tab(self):
        w=QWidget(); l=QVBoxLayout(w); holder,tools=self._flow_bar(); self.rate_currency=QComboBox(); self.rate_currency.setEditable(True); self.rate_currency.addItems(["USD","CNY","JPY","EUR","TWD"])
        self.rate_value=QDoubleSpinBox(); self.rate_value.setDecimals(6); self.rate_value.setMaximum(9999); self.rate_date=QLineEdit(date.today().isoformat()); self.rate_note=QLineEdit(); self.rate_note.setPlaceholderText("例如：付款日銀行牌告／人工設定")
        save=compact_button(QPushButton("💾 儲存匯率"), primary=True); save.clicked.connect(self.save_rate)
        for x in [QLabel("幣別"),self.rate_currency,QLabel("1 原幣 = TWD"),self.rate_value,QLabel("日期"),self.rate_date,self.rate_note,save]: tools.addWidget(x)
        l.addWidget(holder); self.rate_table=self._table(); l.addWidget(self.rate_table,1); return w

    def _margin_tab(self):
        w=QWidget(); l=QVBoxLayout(w); holder,tools=self._flow_bar(); refresh=compact_button(QPushButton("🔄 重新計算毛利"), primary=True); refresh.clicked.connect(self.refresh_margin)
        x=compact_button(QPushButton("📊 匯出 Excel")); x.clicked.connect(lambda:self.export_table(self.margin_table,"毛利分析","xlsx")); p=compact_button(QPushButton("📄 匯出 PDF")); p.clicked.connect(lambda:self.export_table(self.margin_table,"毛利分析","pdf"))
        for b in [refresh,x,p]: tools.addWidget(b)
        l.addWidget(holder); self.margin_summary=QLabel(""); self.margin_summary.setStyleSheet("font-weight:800;"); self.margin_summary.setWordWrap(True); l.addWidget(self.margin_summary); self.margin_table=self._table(); l.addWidget(self.margin_table,1); return w

    def _sales_price_tab(self):
        w=QWidget(); l=QVBoxLayout(w)
        holder,tools=self._flow_bar()
        self.sp_customer=QLineEdit(); self.sp_customer.setPlaceholderText("客戶名稱"); self.sp_customer.setMaximumWidth(220)
        self.sp_product=QLineEdit(); self.sp_product.setPlaceholderText("產品編號"); self.sp_product.setMaximumWidth(180)
        self.sp_price=QDoubleSpinBox(); self.sp_price.setDecimals(6); self.sp_price.setMaximum(999999999); self.sp_price.setPrefix("單價 ")
        self.sp_currency=QComboBox(); self.sp_currency.setEditable(True); self.sp_currency.addItems(["TWD","USD","CNY","JPY","EUR"])
        self.sp_unit=QLineEdit(); self.sp_unit.setPlaceholderText("數量單位，例如 包 / 箱"); self.sp_unit.setMaximumWidth(170)
        self.sp_note=QLineEdit(); self.sp_note.setPlaceholderText("備註"); self.sp_note.setMaximumWidth(220)
        save=compact_button(QPushButton("💾 儲存價格"), primary=True); save.clicked.connect(self.save_sales_price)
        delete=compact_button(QPushButton("🗑 刪除所選")); delete.clicked.connect(self.delete_sales_price)
        ex=compact_button(QPushButton("📊 匯出 Excel")); ex.clicked.connect(lambda:self.export_table(self.sales_price_table,"客戶銷售價格主檔","xlsx"))
        for widget in [QLabel("客戶"),self.sp_customer,QLabel("產品"),self.sp_product,self.sp_price,self.sp_currency,self.sp_unit,self.sp_note,save,delete,ex]: tools.addWidget(widget)
        l.addWidget(holder)
        hint=QLabel("同一個『客戶＋產品編號』只保留一組目前銷售價格。客戶需求沒有單價時，應收同步會優先使用這裡的價格。")
        hint.setWordWrap(True); l.addWidget(hint)
        self.sales_price_table=self._table(); self.sales_price_table.itemSelectionChanged.connect(self.load_selected_sales_price); l.addWidget(self.sales_price_table,1)
        return w

    def _aging_tab(self):
        w=QWidget(); l=QVBoxLayout(w); holder,tools=self._flow_bar()
        refresh=compact_button(QPushButton("⟳ 重新計算帳齡"), primary=True); refresh.clicked.connect(self.refresh_aging)
        ex=compact_button(QPushButton("📊 匯出 Excel")); ex.clicked.connect(lambda:self.export_table(self.aging_table,"應收帳齡","xlsx"))
        pdf=compact_button(QPushButton("📄 匯出 PDF")); pdf.clicked.connect(lambda:self.export_table(self.aging_table,"應收帳齡","pdf"))
        for b in [refresh,ex,pdf]: tools.addWidget(b)
        l.addWidget(holder); self.aging_summary=QLabel(""); self.aging_summary.setStyleSheet("font-weight:800;"); self.aging_summary.setWordWrap(True); l.addWidget(self.aging_summary)
        self.aging_table=self._table(); l.addWidget(self.aging_table,1); return w

    def _management_tab(self):
        w=QWidget(); l=QVBoxLayout(w); holder,tools=self._flow_bar()
        refresh=compact_button(QPushButton("⟳ 重新計算管理分析"), primary=True); refresh.clicked.connect(self.refresh_management)
        ex=compact_button(QPushButton("📊 匯出現金流 Excel")); ex.clicked.connect(lambda:self.export_table(self.cashflow_table,"現金流明細","xlsx"))
        for b in [refresh,ex]: tools.addWidget(b)
        l.addWidget(holder); self.cashflow_summary=QLabel(""); self.cashflow_summary.setStyleSheet("font-weight:800;"); self.cashflow_summary.setWordWrap(True); l.addWidget(self.cashflow_summary)
        sub=QTabWidget(); l.addWidget(sub,1)
        cash=QWidget(); cl=QVBoxLayout(cash); self.cashflow_table=self._table(); cl.addWidget(self.cashflow_table); sub.addTab(cash,"現金流明細")
        prod=QWidget(); pl=QVBoxLayout(prod); self.product_margin_table=self._table(); pl.addWidget(self.product_margin_table); sub.addTab(prod,"產品毛利排行")
        cust=QWidget(); cul=QVBoxLayout(cust); self.customer_margin_table=self._table(); cul.addWidget(self.customer_margin_table); sub.addTab(cust,"客戶毛利排行")
        supp=QWidget(); sl=QVBoxLayout(supp); self.supplier_margin_table=self._table(); sl.addWidget(self.supplier_margin_table); sub.addTab(supp,"供應商毛利排行")
        return w

    def save_sales_price(self):
        try:
            FinancialService.upsert_sales_price(self.sp_customer.text(), self.sp_product.text(), self.sp_price.value(), self.sp_currency.currentText(), self.sp_unit.text(), self.sp_note.text())
            self.refresh_all(); QMessageBox.information(self,"完成","客戶銷售價格已保存。")
        except Exception as e: QMessageBox.critical(self,"儲存失敗",str(e))

    def load_selected_sales_price(self):
        row=self.sales_price_table.currentRow()
        if row < 0 or self.sales_price_table.columnCount() == 0: return
        headers=[self.sales_price_table.horizontalHeaderItem(i).text() for i in range(self.sales_price_table.columnCount())]
        values={h:(self.sales_price_table.item(row,i).text() if self.sales_price_table.item(row,i) else "") for i,h in enumerate(headers)}
        self.sp_customer.setText(values.get("customer","")); self.sp_product.setText(values.get("product_no",""))
        try:self.sp_price.setValue(float(values.get("unit_price",0) or 0))
        except Exception:pass
        self.sp_currency.setCurrentText(values.get("currency","TWD")); self.sp_unit.setText(values.get("qty_unit","")); self.sp_note.setText(values.get("note",""))

    def delete_sales_price(self):
        row=self.sales_price_table.currentRow()
        if row < 0: QMessageBox.information(self,"請選擇","請先選取一筆銷售價格。"); return
        item=self.sales_price_table.item(row,0); rid=item.text() if item else ""
        if QMessageBox.question(self,"確認刪除","確定刪除所選客戶銷售價格？") != QMessageBox.StandardButton.Yes: return
        try: FinancialService.delete_sales_price(rid); self.refresh_all()
        except Exception as e: QMessageBox.critical(self,"刪除失敗",str(e))

    def refresh_aging(self):
        df,s=FinancialService.receivable_aging(); self._show_df(self.aging_table,df)
        b=s.get("buckets",{}); self.aging_summary.setText(
            f"逾期 {s.get('overdue_count',0)} 筆｜逾期未收 TWD {s.get('overdue_twd',0):,.0f}｜"
            f"未到期 {b.get('未到期',0):,.0f}｜1-30天 {b.get('逾期1-30天',0):,.0f}｜31-60天 {b.get('逾期31-60天',0):,.0f}｜61-90天 {b.get('逾期61-90天',0):,.0f}｜90天以上 {b.get('逾期90天以上',0):,.0f}")

    def refresh_management(self):
        cdf,cs=FinancialService.cashflow_analysis(); self._show_df(self.cashflow_table,cdf)
        self.cashflow_summary.setText(f"現金流入 TWD {cs.get('inflow_twd',0):,.0f}｜現金流出 TWD {cs.get('outflow_twd',0):,.0f}｜淨現金流 TWD {cs.get('net_twd',0):,.0f}")
        ranks=FinancialService.margin_rankings(); self._show_df(self.product_margin_table,ranks.get("product")); self._show_df(self.customer_margin_table,ranks.get("customer")); self._show_df(self.supplier_margin_table,ranks.get("supplier"))

    def _credit_tab(self):
        w=QWidget(); l=QVBoxLayout(w); holder,tools=self._flow_bar()
        b1=compact_button(QPushButton("＋ 新增客戶條件")); b2=compact_button(QPushButton("✏ 編輯所選")); b3=compact_button(QPushButton("🗑 刪除所選")); b4=compact_button(QPushButton("📊 匯出 Excel")); b5=compact_button(QPushButton("📄 匯出 PDF"))
        b1.clicked.connect(self.add_customer_terms); b2.clicked.connect(self.edit_customer_terms); b3.clicked.connect(self.delete_customer_terms); b4.clicked.connect(lambda:self.export_table(self.credit_table,"客戶信用與帳款條件","xlsx")); b5.clicked.connect(lambda:self.export_table(self.credit_table,"客戶信用與帳款條件","pdf"))
        for b in [b1,b2,b3,b4,b5]: tools.addWidget(b)
        l.addWidget(holder); self.credit_summary=QLabel(""); self.credit_summary.setWordWrap(True); l.addWidget(self.credit_summary); self.credit_table=self._table(); l.addWidget(self.credit_table,1); return w

    def _invoice_tab(self):
        w=QWidget(); l=QVBoxLayout(w); holder,tools=self._flow_bar()
        b1=compact_button(QPushButton("🧾 從待開票應收開立發票")); b2=compact_button(QPushButton("⟳ 重新整理")); b3=compact_button(QPushButton("📊 匯出 Excel")); b4=compact_button(QPushButton("📄 匯出 PDF"))
        b1.clicked.connect(self.issue_invoice); b2.clicked.connect(self.refresh_all); b3.clicked.connect(lambda:self.export_table(self.invoice_table,"正式銷售發票","xlsx")); b4.clicked.connect(lambda:self.export_table(self.invoice_table,"正式銷售發票","pdf"))
        for b in [b1,b2,b3,b4]: tools.addWidget(b)
        l.addWidget(holder); hint=QLabel("流程：客戶需求 → 應收（待開票）→ 開立發票 → 自動套用客戶帳款條件 → 計算到期日 → 收款 / 帳齡 / 信用額度 / 現金流預測。發票金額以目前應收的『含稅總額』為基礎，營業稅率用於拆算未稅額與稅額。")
        hint.setWordWrap(True); l.addWidget(hint); self.invoice_table=self._table(); l.addWidget(self.invoice_table,1); return w

    def _forecast_tab(self):
        w=QWidget(); l=QVBoxLayout(w); holder,tools=self._flow_bar()
        tools.addWidget(QLabel("預測區間")); self.forecast_days=QComboBox(); self.forecast_days.addItem("30天",30); self.forecast_days.addItem("60天",60); self.forecast_days.addItem("90天",90); self.forecast_days.addItem("180天",180); self.forecast_days.setCurrentIndex(2); tools.addWidget(self.forecast_days)
        tools.addWidget(QLabel("期初可用現金TWD")); self.opening_cash=QDoubleSpinBox(); self.opening_cash.setDecimals(2); self.opening_cash.setMaximum(999999999999); tools.addWidget(self.opening_cash)
        b0=compact_button(QPushButton("💾 儲存期初現金")); b1=compact_button(QPushButton("＋ 新增預計現金流")); b2=compact_button(QPushButton("🗑 刪除所選計畫")); b3=compact_button(QPushButton("⟳ 重新計算")); b4=compact_button(QPushButton("📊 匯出 Excel")); b5=compact_button(QPushButton("📄 匯出 PDF"))
        b0.clicked.connect(self.save_opening_cash); b1.clicked.connect(self.add_cash_plan); b2.clicked.connect(self.delete_cash_plan); b3.clicked.connect(self.refresh_forecast); b4.clicked.connect(lambda:self.export_table(self.forecast_table,"現金流預測","xlsx")); b5.clicked.connect(lambda:self.export_table(self.forecast_table,"現金流預測","pdf"))
        for b in [b0,b1,b2,b3,b4,b5]: tools.addWidget(b)
        l.addWidget(holder); self.forecast_summary=QLabel(""); self.forecast_summary.setWordWrap(True); l.addWidget(self.forecast_summary); self.forecast_table=self._table(); l.addWidget(self.forecast_table,2); l.addWidget(QLabel("人工預計項目")); self.cashplan_table=self._table(); l.addWidget(self.cashplan_table,1); self.forecast_days.currentIndexChanged.connect(self.refresh_forecast); return w

    def _sales_order_tab(self):
        w=QWidget(); l=QVBoxLayout(w); holder,tools=self._flow_bar()
        b1=compact_button(QPushButton("🔄 從客戶需求同步訂單"), primary=True); b2=compact_button(QPushButton("＋ 新增銷售訂單")); b3=compact_button(QPushButton("🚚 記錄出貨")); b4=compact_button(QPushButton("📊 匯出 Excel")); b5=compact_button(QPushButton("📄 匯出 PDF"))
        b1.clicked.connect(self.sync_sales_orders); b2.clicked.connect(self.add_sales_order); b3.clicked.connect(self.record_sales_delivery); b4.clicked.connect(lambda:self.export_table(self.sales_order_table,"正式銷售訂單","xlsx")); b5.clicked.connect(lambda:self.export_table(self.sales_order_table,"正式銷售訂單","pdf"))
        for b in [b1,b2,b3,b4,b5]: tools.addWidget(b)
        l.addWidget(holder); hint=QLabel("建議正式流程：客戶需求 → 銷售訂單 → 出貨 → 建立應收 / 發票 → 收款。此頁只管理訂單與出貨進度，不會在同步訂單時直接產生應收，避免重複認列。")
        hint.setWordWrap(True); l.addWidget(hint); self.sales_order_summary=QLabel(""); self.sales_order_summary.setWordWrap(True); l.addWidget(self.sales_order_summary); self.sales_order_table=self._table(); l.addWidget(self.sales_order_table,1); return w

    def _delivery_tab(self):
        w=QWidget(); l=QVBoxLayout(w); holder,tools=self._flow_bar()
        b1=compact_button(QPushButton("💵 由出貨建立應收"), primary=True); b2=compact_button(QPushButton("🧾 由出貨開立發票")); b3=compact_button(QPushButton("⟳ 重新整理")); b4=compact_button(QPushButton("📊 匯出 Excel")); b5=compact_button(QPushButton("📄 匯出 PDF"))
        b1.clicked.connect(self.delivery_to_receivable); b2.clicked.connect(self.invoice_selected_delivery); b3.clicked.connect(self.refresh_all); b4.clicked.connect(lambda:self.export_table(self.delivery_table,"銷售出貨明細","xlsx")); b5.clicked.connect(lambda:self.export_table(self.delivery_table,"銷售出貨明細","pdf"))
        for b in [b1,b2,b3,b4,b5]: tools.addWidget(b)
        l.addWidget(holder); hint=QLabel("出貨後才建立應收可避免尚未履約就提早認列。若要開票，可直接選取出貨紀錄後『由出貨開立發票』；系統會先建立對應應收，再沿用客戶帳款條件計算到期日。")
        hint.setWordWrap(True); l.addWidget(hint); self.delivery_table=self._table(); l.addWidget(self.delivery_table,1); return w

    def _statement_collection_tab(self):
        w=QWidget(); l=QVBoxLayout(w); top,flow=self._flow_bar()
        flow.addWidget(QLabel("客戶")); self.statement_customer=QComboBox(); self.statement_customer.setEditable(True); self.statement_customer.setMinimumWidth(180); flow.addWidget(self.statement_customer)
        flow.addWidget(QLabel("起日")); self.statement_start=QLineEdit(); self.statement_start.setPlaceholderText("YYYY-MM-DD"); self.statement_start.setMaximumWidth(125); flow.addWidget(self.statement_start)
        flow.addWidget(QLabel("迄日")); self.statement_end=QLineEdit(); self.statement_end.setPlaceholderText("YYYY-MM-DD"); self.statement_end.setMaximumWidth(125); flow.addWidget(self.statement_end)
        b1=compact_button(QPushButton("📋 產生對帳單"), primary=True); b2=compact_button(QPushButton("📊 匯出對帳 Excel")); b3=compact_button(QPushButton("📄 匯出對帳 PDF")); b1.clicked.connect(self.refresh_statement); b2.clicked.connect(lambda:self.export_table(self.statement_table,"客戶對帳單","xlsx")); b3.clicked.connect(lambda:self.export_table(self.statement_table,"客戶對帳單","pdf"))
        for b in [b1,b2,b3]: flow.addWidget(b)
        l.addWidget(top); self.statement_summary=QLabel("請先選擇客戶並產生對帳單。"); self.statement_summary.setWordWrap(True); l.addWidget(self.statement_summary); self.statement_table=self._table(); l.addWidget(self.statement_table,1)
        l.addWidget(QLabel("應收催收管理")); cbar,cflow=self._flow_bar(); c1=compact_button(QPushButton("📞 新增催收紀錄"), primary=True); c2=compact_button(QPushButton("⟳ 重新整理催收")); c3=compact_button(QPushButton("📊 匯出催收 Excel")); c1.clicked.connect(self.add_collection_action); c2.clicked.connect(self.refresh_collection); c3.clicked.connect(lambda:self.export_table(self.collection_table,"應收催收管理","xlsx")); [cflow.addWidget(x) for x in [c1,c2,c3]]; l.addWidget(cbar); self.collection_table=self._table(); l.addWidget(self.collection_table,1); return w

    def _payment_schedule_tab(self):
        w=QWidget(); l=QVBoxLayout(w); holder,tools=self._flow_bar(); tools.addWidget(QLabel("排程區間")); self.payment_schedule_days=QComboBox(); self.payment_schedule_days.addItem("30天",30); self.payment_schedule_days.addItem("60天",60); self.payment_schedule_days.addItem("90天",90); self.payment_schedule_days.addItem("180天",180); self.payment_schedule_days.setCurrentIndex(2); tools.addWidget(self.payment_schedule_days)
        b1=compact_button(QPushButton("📅 設定所選付款日"), primary=True); b2=compact_button(QPushButton("⟳ 重新計算")); b3=compact_button(QPushButton("📊 匯出 Excel")); b4=compact_button(QPushButton("📄 匯出 PDF")); b1.clicked.connect(self.schedule_selected_payable); b2.clicked.connect(self.refresh_payment_schedule); b3.clicked.connect(lambda:self.export_table(self.payment_schedule_table,"供應商付款排程","xlsx")); b4.clicked.connect(lambda:self.export_table(self.payment_schedule_table,"供應商付款排程","pdf")); [tools.addWidget(x) for x in [b1,b2,b3,b4]]
        l.addWidget(holder); self.payment_schedule_summary=QLabel(""); self.payment_schedule_summary.setWordWrap(True); l.addWidget(self.payment_schedule_summary); self.payment_schedule_table=self._table(); l.addWidget(self.payment_schedule_table,1); self.payment_schedule_days.currentIndexChanged.connect(self.refresh_payment_schedule); return w

    def _sales_adjustment_tab(self):
        w=QWidget(); l=QVBoxLayout(w); holder,tools=self._flow_bar(); b1=compact_button(QPushButton("↩ 新增銷售退貨"),primary=True); b2=compact_button(QPushButton("🧾 新增發票折讓")); b3=compact_button(QPushButton("🔗 沖帳所選")); b4=compact_button(QPushButton("⟳ 重新整理")); b1.clicked.connect(self.add_sales_return); b2.clicked.connect(self.add_invoice_allowance); b3.clicked.connect(self.settle_selected_sales_adjustment); b4.clicked.connect(self.refresh_all); [tools.addWidget(x) for x in [b1,b2,b3,b4]]; l.addWidget(holder)
        hint=QLabel("正式流程：退貨／折讓先建立調整憑證，不直接刪改原發票；確認後再沖帳。銷售退貨可記錄是否退回庫存，本版先保留財務與稽核紀錄，實際庫存入庫仍需由庫存作業確認。" ); hint.setWordWrap(True); l.addWidget(hint)
        self.sales_adjust_tabs=QTabWidget(); a=QWidget(); al=QVBoxLayout(a); self.sales_return_table=self._table(); al.addWidget(self.sales_return_table); b=QWidget(); bl=QVBoxLayout(b); self.allowance_table=self._table(); bl.addWidget(self.allowance_table); self.sales_adjust_tabs.addTab(a,"銷售退貨"); self.sales_adjust_tabs.addTab(b,"發票折讓"); l.addWidget(self.sales_adjust_tabs,1); return w

    def _purchase_return_tab(self):
        w=QWidget(); l=QVBoxLayout(w); holder,tools=self._flow_bar(); b1=compact_button(QPushButton("↩ 新增進貨退貨"),primary=True); b2=compact_button(QPushButton("🔗 沖帳所選")); b3=compact_button(QPushButton("📊 匯出 Excel")); b1.clicked.connect(self.add_purchase_return); b2.clicked.connect(self.settle_selected_purchase_return); b3.clicked.connect(lambda:self.export_table(self.purchase_return_table,"進貨退貨","xlsx")); [tools.addWidget(x) for x in [b1,b2,b3]]; l.addWidget(holder)
        hint=QLabel("進貨退貨不會刪除原始採購應付，也不會改寫已付款紀錄；退貨憑證沖帳後才減少應付餘額。下方同時顯示歷次沖帳紀錄。" ); hint.setWordWrap(True); l.addWidget(hint); self.purchase_return_table=self._table(); l.addWidget(self.purchase_return_table,1); l.addWidget(QLabel("沖帳紀錄")); self.settlement_table=self._table(); l.addWidget(self.settlement_table,1); return w

    def _month_close_tab(self):
        w=QWidget(); l=QVBoxLayout(w); holder,tools=self._flow_bar(); self.close_period=QLineEdit(date.today().strftime("%Y-%m")); self.close_period.setMaximumWidth(110); self.close_note=QLineEdit(); self.close_note.setPlaceholderText("月結備註／重開原因"); self.close_note.setMaximumWidth(280); preview=compact_button(QPushButton("🔎 月結預覽"),primary=True); close=compact_button(QPushButton("🔒 執行月結")); reopen=compact_button(QPushButton("🔓 重開月份")); preview.clicked.connect(self.preview_month_close); close.clicked.connect(self.close_month); reopen.clicked.connect(self.reopen_month); [tools.addWidget(x) for x in [QLabel("月份"),self.close_period,self.close_note,preview,close,reopen]]; l.addWidget(holder)
        hint=QLabel("月結後，該月份的發票、收款、付款、費用、退貨、折讓與沖帳將被 service 層鎖定，不能再補登或倒填。重開月份只有系統管理員可執行，而且必須填原因。月結前若有外幣缺匯率，系統會拒絕結帳。" ); hint.setWordWrap(True); l.addWidget(hint); self.close_summary=QLabel("請先選月份做月結預覽。"); self.close_summary.setWordWrap(True); l.addWidget(self.close_summary); self.close_preview_table=self._table(); l.addWidget(self.close_preview_table,1); l.addWidget(QLabel("月結 / 重開歷程")); self.close_history_table=self._table(); l.addWidget(self.close_history_table,1); return w

    def _table(self):
        t=QTableWidget(); t.setAlternatingRowColors(True); t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection); t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers); t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive); return t

    def _show_df(self, table, df, columns=None):
        table.clear()
        if df is None or df.empty: table.setRowCount(0); table.setColumnCount(0); return
        if columns: df=df[[c for c in columns if c in df.columns]].copy()
        table.setRowCount(len(df)); table.setColumnCount(len(df.columns)); table.setHorizontalHeaderLabels([str(c) for c in df.columns])
        for r,(_,row) in enumerate(df.iterrows()):
            for c,col in enumerate(df.columns): table.setItem(r,c,QTableWidgetItem(str(row.get(col,""))))
        table.resizeColumnsToContents()

    def refresh_all(self):
        data=FinancialService.load(); s=FinancialService.summary()
        self.sum_labels["未付原幣"].setText(" / ".join(f"{k} {v:,.2f}" for k,v in s["unpaid_by_currency"].items() if v>0) or "0")
        self.sum_labels["未收原幣"].setText(" / ".join(f"{k} {v:,.2f}" for k,v in s["uncollected_by_currency"].items() if v>0) or "0")
        self.sum_labels["已付款TWD"].setText(f"{s['paid_twd']:,.0f}"); self.sum_labels["已收款TWD"].setText(f"{s['received_twd']:,.0f}")
        self.sum_labels["費用TWD"].setText(f"{s['expense_twd']:,.0f}"); self.sum_labels["估算毛利TWD"].setText(f"{s['gross_profit_twd']:,.0f}")
        self.sum_labels["毛利率"].setText(f"{s['gross_margin_pct']:.1f}%"); self.sum_labels["缺成本品項"].setText(str(s['missing_cost_count']))
        self.sum_labels["信用超額客戶"].setText(str(s.get("over_credit_count",0)))
        self.sum_labels["30天期末現金"].setText(f"TWD {s.get('forecast_30d_ending_cash_twd',0):,.0f}")
        self.sum_labels["待出貨訂單"].setText(str(s.get("pending_sales_order_count",0)))
        self.sum_labels["30天付款排程"].setText(f"TWD {s.get('payment_schedule_30d_twd',0):,.0f}")

        pay=pd.DataFrame(data["payables"])
        if not pay.empty: pay["沖帳金額"]=FinancialService._numeric_series(pay,"adjustment_amount"); pay["未付款金額"]=FinancialService._numeric_series(pay,"total_amount")-FinancialService._numeric_series(pay,"paid_amount")-pay["沖帳金額"]
        self._show_df(self.payable_table,pay,["id","status","supplier","product_no","product_name","qty","purchase_qty_unit","currency","unit_price","price_unit","total_amount","paid_amount","沖帳金額","未付款金額","expected_payment_date","source_updated_at"])
        self._show_df(self.payment_table,pd.DataFrame(data["payments"]),["id","payment_date","supplier","currency","amount","fx_rate","amount_twd","bank_fee_twd","payable_id","note"])

        ar=pd.DataFrame(data.get("receivables",[]))
        if not ar.empty: ar["沖帳金額"]=FinancialService._numeric_series(ar,"adjustment_amount"); ar["未收款金額"]=FinancialService._numeric_series(ar,"total_amount")-FinancialService._numeric_series(ar,"received_amount")-ar["沖帳金額"]
        self._show_df(self.receivable_table,ar,["id","status","customer","customer_order_no","product_no","product_name","qty","qty_unit","currency","unit_price","total_amount","received_amount","沖帳金額","未收款金額","invoice_no","invoice_date","due_date","term_code","note"])
        self._show_df(self.receipt_table,pd.DataFrame(data.get("receipts",[])),["id","receipt_date","customer","currency","amount","fx_rate","amount_twd","bank_fee_twd","receivable_id","note"])
        self._show_df(self.expense_table,pd.DataFrame(data.get("expenses",[])),["id","expense_date","category","vendor","reference_no","currency","amount","fx_rate","amount_twd","note"])

        ships=[]
        for x in data["shipments"]:
            shared=sum(FinancialService._num(v) for v in x.get("costs_twd",{}).values()); ships.append({"id":x.get("id"),"created_at":x.get("created_at"),"總CBM":x.get("total_cbm"),"櫃數":x.get("container_count"),"品項":len(x.get("rows",[])),"共同成本TWD":round(shared,2),"備註":x.get("note","")})
        self._show_df(self.shipment_table,pd.DataFrame(ships)); self._show_df(self.rate_table,pd.DataFrame(data["exchange_rates"]),["currency","rate_to_twd","date","note","updated_at"])
        current=self.cost_shipment.currentText(); self.cost_shipment.blockSignals(True); self.cost_shipment.clear(); self.cost_shipment.addItems([str(x.get("id")) for x in data["shipments"]]);
        if current: self.cost_shipment.setCurrentText(current)
        self.cost_shipment.blockSignals(False); self.refresh_cost_analysis(); self.refresh_margin()
        self._show_df(self.sales_price_table,pd.DataFrame(data.get("sales_prices",[])),["id","customer","product_no","currency","unit_price","qty_unit","note","updated_at"])
        self.refresh_aging(); self.refresh_management(); self.refresh_credit(); self._show_df(self.invoice_table,FinancialService.invoice_dataframe()); self.refresh_forecast()
        if hasattr(self,"sales_order_table"):
            sodf=FinancialService.sales_order_dataframe(); self._show_df(self.sales_order_table,sodf)
            pending=int((sodf["未出貨"]>0).sum()) if sodf is not None and not sodf.empty else 0; qty=float(pd.to_numeric(sodf["未出貨"],errors="coerce").fillna(0).sum()) if sodf is not None and not sodf.empty else 0
            self.sales_order_summary.setText(f"銷售訂單 {len(sodf) if sodf is not None else 0} 筆｜待出貨 {pending} 筆｜未出貨總量 {qty:,.2f}")
        if hasattr(self,"delivery_table"): self._show_df(self.delivery_table,FinancialService.delivery_dataframe())
        if hasattr(self,"collection_table"): self.refresh_collection()
        if hasattr(self,"payment_schedule_table"): self.refresh_payment_schedule()
        if hasattr(self,"sales_return_table"):
            sr,ia=FinancialService.sales_adjustment_dataframes(); self._show_df(self.sales_return_table,sr,["id","status","return_date","customer","invoice_no","product_no","product_name","qty","qty_unit","currency","amount","settled_amount","restock","inventory_status","reason","note"]); self._show_df(self.allowance_table,ia,["id","status","allowance_no","allowance_date","customer","invoice_no","currency","amount","settled_amount","reason","note"])
        if hasattr(self,"purchase_return_table"):
            self._show_df(self.purchase_return_table,FinancialService.purchase_return_dataframe(),["id","status","return_date","supplier","payable_id","product_no","product_name","qty","qty_unit","currency","amount","settled_amount","inventory_status","reason","note"]); self._show_df(self.settlement_table,FinancialService.settlement_dataframe())
        if hasattr(self,"close_history_table"): self._show_df(self.close_history_table,FinancialService.month_close_history_dataframe())
        if hasattr(self,"statement_customer"):
            current=self.statement_customer.currentText(); customers=sorted({FinancialService._text(x.get("customer")) for x in data.get("sales_orders",[])+data.get("receivables",[]) if FinancialService._text(x.get("customer"))}); self.statement_customer.blockSignals(True); self.statement_customer.clear(); self.statement_customer.addItems(customers); self.statement_customer.setCurrentText(current); self.statement_customer.blockSignals(False)

    def sync_payables(self):
        try:
            result=FinancialService.sync_payables_from_purchase(); self.refresh_all(); QMessageBox.information(self,"同步完成",f"新增 {result['created']} 筆、更新 {result['updated']} 筆。\n已付款而未覆蓋：{result['skipped_paid']} 筆。\n來源採購快照：{result['source_updated_at'] or '尚無時間'}")
        except Exception as e: QMessageBox.critical(self,"同步失敗",str(e))

    def sync_receivables(self):
        try:
            r=FinancialService.sync_receivables_from_customer_demand(); self.refresh_all(); QMessageBox.information(self,"應收同步完成",f"新增 {r['created']} 筆、更新 {r['updated']} 筆。\n已有收款未覆蓋：{r['skipped_received']} 筆。\n缺少銷售金額且價格主檔也無資料：{r['skipped_no_amount']} 筆。\n缺少客戶或正式產品編號：{r['skipped_no_product']} 筆。")
        except Exception as e: QMessageBox.critical(self,"同步失敗",str(e))

    def add_receivable(self):
        d=ReceivableDialog(self)
        if d.exec()!=QDialog.DialogCode.Accepted: return
        try:
            FinancialService.create_receivable(d.customer.text(),d.product_no.text(),d.product_name.text(),d.qty.value(),d.qty_unit.text(),d.currency.currentText(),d.unit_price.value(),d.total.value(),d.invoice_date.text(),d.due_date.text(),d.order_no.text(),d.note.text()); self.refresh_all(); QMessageBox.information(self,"完成","客戶應收已新增。")
        except Exception as e: QMessageBox.critical(self,"新增失敗",str(e))

    def _selected_record(self, table, key):
        row=table.currentRow();
        if row<0: return None
        item=table.item(row,0); rid=item.text() if item else ""; return next((x for x in FinancialService.load().get(key,[]) if x.get("id")==rid),None)

    def record_payment(self):
        p=self._selected_record(self.payable_table,"payables")
        if not p: QMessageBox.information(self,"請選擇","請先選取一筆採購應付。"); return
        d=PaymentDialog(p,self)
        if d.exec()!=QDialog.DialogCode.Accepted: return
        try: FinancialService.record_payment(p["id"],d.amount.value(),d.payment_date.text().strip(),d.fx.value(),d.fee.value(),d.note.text().strip()); self.refresh_all(); QMessageBox.information(self,"完成","付款紀錄已保存。")
        except Exception as e: QMessageBox.critical(self,"付款失敗",str(e))

    def record_receipt(self):
        r=self._selected_record(self.receivable_table,"receivables")
        if not r: QMessageBox.information(self,"請選擇","請先選取一筆客戶應收。"); return
        d=ReceiptDialog(r,self)
        if d.exec()!=QDialog.DialogCode.Accepted: return
        try: FinancialService.record_receipt(r["id"],d.amount.value(),d.receipt_date.text().strip(),d.fx.value(),d.fee.value(),d.note.text().strip()); self.refresh_all(); QMessageBox.information(self,"完成","收款紀錄已保存。")
        except Exception as e: QMessageBox.critical(self,"收款失敗",str(e))

    def add_expense(self):
        d=ExpenseDialog(self)
        if d.exec()!=QDialog.DialogCode.Accepted: return
        try: FinancialService.create_expense(d.expense_date.text(),d.category.currentText(),d.amount.value(),d.currency.currentText(),d.fx.value(),d.vendor.text(),d.reference.text(),d.note.text()); self.refresh_all(); QMessageBox.information(self,"完成","費用已新增。")
        except Exception as e: QMessageBox.critical(self,"費用新增失敗",str(e))

    def save_rate(self):
        try: FinancialService.upsert_rate(self.rate_currency.currentText(),self.rate_value.value(),self.rate_date.text().strip(),self.rate_note.text().strip()); self.refresh_all(); QMessageBox.information(self,"完成","匯率已保存。")
        except Exception as e: QMessageBox.critical(self,"匯率錯誤",str(e))

    def _selected_shipment(self):
        return self._selected_record(self.shipment_table,"shipments")

    def edit_shipment_cost(self):
        s=self._selected_shipment()
        if not s: QMessageBox.information(self,"請選擇","請先選取一個進口批次。"); return
        d=ShipmentCostDialog(s,self)
        if d.exec()!=QDialog.DialogCode.Accepted: return
        try: FinancialService.update_shipment_costs(s["id"],d.costs()); self.refresh_all(); QMessageBox.information(self,"完成","進口共同成本已更新，成本分析已重新計算。")
        except Exception as e: QMessageBox.critical(self,"更新失敗",str(e))

    def refresh_cost_analysis(self):
        sid=self.cost_shipment.currentText().strip(); shipment=next((x for x in FinancialService.load()["shipments"] if x.get("id")==sid),None)
        if not shipment: self._show_df(self.cost_table,pd.DataFrame()); self.cost_summary.setText("尚未建立進口成本批次。"); return
        df,s=FinancialService.shipment_analysis(shipment); self._show_df(self.cost_table,df); self.cost_summary.setText(f"商品台幣 {s.get('merchandise_twd',0):,.2f}｜共同成本 {s.get('shared_cost_twd',0):,.2f}｜落地總成本 {s.get('landed_total_twd',0):,.2f}")

    def refresh_margin(self):
        df,s=FinancialService.gross_margin_analysis(); self._show_df(self.margin_table,df); self.margin_summary.setText(f"收入 TWD {s.get('revenue_twd',0):,.2f}｜可比較成本 TWD {s.get('cost_twd',0):,.2f}｜估算毛利 TWD {s.get('gross_profit_twd',0):,.2f}｜估算毛利率 {s.get('margin_pct',0):.2f}%｜缺少落地成本 {s.get('missing_cost_count',0)} 筆")

    def refresh_credit(self):
        df=FinancialService.customer_credit_status(); self._show_df(self.credit_table,df)
        if df.empty: self.credit_summary.setText("尚未建立客戶信用 / 帳款條件。")
        else:
            over=int((df["狀態"]=="超額").sum()); near=int((df["狀態"]=="接近額度").sum()); overdue=float(pd.to_numeric(df["逾期未收TWD"],errors="coerce").fillna(0).sum())
            self.credit_summary.setText(f"客戶 {len(df)} 家｜超額 {over} 家｜接近額度 {near} 家｜逾期未收 TWD {overdue:,.0f}")

    def _selected_credit_record(self):
        row=self.credit_table.currentRow()
        if row<0: return None
        headers=[self.credit_table.horizontalHeaderItem(i).text() for i in range(self.credit_table.columnCount())]
        try: idx=headers.index("設定ID")
        except ValueError: return None
        item=self.credit_table.item(row,idx); rid=item.text() if item else ""
        return next((x for x in FinancialService.load().get("customer_terms",[]) if x.get("id")==rid),None)

    def add_customer_terms(self):
        d=CustomerTermsDialog(parent=self)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        try: FinancialService.upsert_customer_terms(d.customer.text(),d.credit.value(),d.term.currentText(),d.currency.currentText(),d.warning.value(),d.policy.currentText(),d.note.text()); self.refresh_all()
        except Exception as e: QMessageBox.critical(self,"保存失敗",str(e))

    def edit_customer_terms(self):
        rec=self._selected_credit_record()
        if not rec: QMessageBox.information(self,"請選擇","請先選取一筆客戶信用設定。"); return
        d=CustomerTermsDialog(rec,self)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        try: FinancialService.upsert_customer_terms(d.customer.text(),d.credit.value(),d.term.currentText(),d.currency.currentText(),d.warning.value(),d.policy.currentText(),d.note.text()); self.refresh_all()
        except Exception as e: QMessageBox.critical(self,"保存失敗",str(e))

    def delete_customer_terms(self):
        rec=self._selected_credit_record()
        if not rec: QMessageBox.information(self,"請選擇","請先選取一筆客戶信用設定。"); return
        if QMessageBox.question(self,"確認刪除",f"確定刪除 {rec.get('customer','')} 的信用 / 帳款條件？")!=QMessageBox.StandardButton.Yes:return
        try: FinancialService.delete_customer_terms(rec.get("id")); self.refresh_all()
        except Exception as e: QMessageBox.critical(self,"刪除失敗",str(e))

    def issue_invoice(self):
        rows=FinancialService.load().get("receivables",[])
        pending=[x for x in rows if not FinancialService._text(x.get("invoice_no")) and FinancialService._num(x.get("total_amount"))>0]
        if not pending: QMessageBox.information(self,"沒有待開票資料","目前沒有可以開立發票的應收。"); return
        d=InvoiceIssueDialog(pending,self)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        rid=d.receivable.currentData()
        if not rid: return
        try:
            inv=FinancialService.issue_invoice_from_receivable(rid,d.invoice_no.text(),d.invoice_date.text(),d.tax_rate.value(),d.term.currentText())
            self.refresh_all(); QMessageBox.information(
                self, "發票完成",
                f"發票 {inv.get('invoice_no')} 已開立。\n到期日：{inv.get('due_date')}\n帳款條件：{inv.get('term_code')}"
            )
        except Exception as e: QMessageBox.critical(self,"開票失敗",str(e))

    def set_expected_payment_date(self):
        p=self._selected_record(self.payable_table,"payables")
        if not p: QMessageBox.information(self,"請選擇","請先選取一筆採購應付。"); return
        d=ExpectedPaymentDialog(p,self)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        try: FinancialService.set_payable_expected_date(p.get("id"),d.expected.text()); self.refresh_all()
        except Exception as e: QMessageBox.critical(self,"保存失敗",str(e))

    def save_opening_cash(self):
        try: FinancialService.set_opening_cash(self.opening_cash.value()); self.refresh_forecast(); QMessageBox.information(self,"完成","期初可用現金已保存。")
        except Exception as e: QMessageBox.critical(self,"保存失敗",str(e))

    def add_cash_plan(self):
        d=CashPlanDialog(self)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        try: FinancialService.add_cashflow_plan(d.plan_date.text(),d.direction.currentText(),d.amount.value(),d.currency.currentText(),d.category.currentText(),d.counterparty.text(),d.note.text()); self.refresh_all()
        except Exception as e: QMessageBox.critical(self,"新增失敗",str(e))

    def delete_cash_plan(self):
        row=self.cashplan_table.currentRow()
        if row<0: QMessageBox.information(self,"請選擇","請先選取一筆人工預計現金流。"); return
        item=self.cashplan_table.item(row,0); pid=item.text() if item else ""
        if not pid:return
        if QMessageBox.question(self,"確認刪除","確定刪除這筆預計現金流？")!=QMessageBox.StandardButton.Yes:return
        try: FinancialService.delete_cashflow_plan(pid); self.refresh_all()
        except Exception as e: QMessageBox.critical(self,"刪除失敗",str(e))

    def refresh_forecast(self):
        if not hasattr(self,"forecast_table"): return
        days=self.forecast_days.currentData() or 90
        df,s=FinancialService.cashflow_forecast(days); self._show_df(self.forecast_table,df)
        self.forecast_summary.setText(f"期初現金 TWD {s.get('opening_cash_twd',0):,.0f}｜預計流入 {s.get('forecast_inflow_twd',0):,.0f}｜預計流出 {s.get('forecast_outflow_twd',0):,.0f}｜期末預估 {s.get('ending_cash_twd',0):,.0f}｜最低日終餘額 {s.get('min_cash_twd',0):,.0f}" + (f"｜⚠ 預估 {s.get('negative_date')} 出現負現金" if s.get('negative_date') else "") + (f"｜⚠ {s.get('missing_fx_count',0)} 筆缺少匯率未納入" if s.get('missing_fx_count',0) else ""))
        data=FinancialService.load(); self.opening_cash.blockSignals(True); self.opening_cash.setValue(FinancialService._num(data.get("cash_settings",{}).get("opening_cash_twd",0))); self.opening_cash.blockSignals(False)
        self._show_df(self.cashplan_table,pd.DataFrame(data.get("cashflow_plans",[])),["id","plan_date","direction","category","counterparty","currency","amount","fx_rate","amount_twd","note"])

    def sync_sales_orders(self):
        try:
            r=FinancialService.sync_sales_orders_from_customer_demand(); self.refresh_all(); QMessageBox.information(self,"同步完成",f"新增 {r['created']} 筆、更新 {r['updated']} 筆、略過 {r['skipped']} 筆。")
        except Exception as e: QMessageBox.critical(self,"同步失敗",str(e))

    def add_sales_order(self):
        d=SalesOrderDialog(self)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        try:
            FinancialService.create_sales_order(d.customer.text(),d.order_no.text(),d.product_no.text(),d.product_name.text(),d.qty.value(),d.qty_unit.text(),d.currency.currentText(),d.unit_price.value(),d.order_date.text(),d.promised.text(),d.note.text()); self.refresh_all()
        except Exception as e: QMessageBox.critical(self,"新增失敗",str(e))

    def _selected_sales_order(self):
        row=self.sales_order_table.currentRow()
        if row<0:return None
        headers=[self.sales_order_table.horizontalHeaderItem(i).text() for i in range(self.sales_order_table.columnCount())]
        try: col=headers.index("銷售訂單")
        except ValueError:return None
        item=self.sales_order_table.item(row,col); rid=item.text() if item else ""
        return next((x for x in FinancialService.load().get("sales_orders",[]) if x.get("id")==rid),None)

    def record_sales_delivery(self):
        o=self._selected_sales_order()
        if not o: QMessageBox.information(self,"請選擇","請先選取一筆銷售訂單。") ; return
        d=DeliveryDialog(o,self)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        try: FinancialService.record_delivery(o["id"],d.qty.value(),d.delivery_date.text(),d.delivery_no.text(),d.warehouse.text(),d.carrier.text(),d.note.text()); self.refresh_all()
        except Exception as e: QMessageBox.critical(self,"出貨失敗",str(e))

    def _selected_delivery(self):
        row=self.delivery_table.currentRow()
        if row<0:return None
        headers=[self.delivery_table.horizontalHeaderItem(i).text() for i in range(self.delivery_table.columnCount())]
        try: col=headers.index("出貨編號")
        except ValueError:return None
        item=self.delivery_table.item(row,col); rid=item.text() if item else ""
        return next((x for x in FinancialService.load().get("deliveries",[]) if x.get("id")==rid),None)

    def delivery_to_receivable(self):
        d=self._selected_delivery()
        if not d: QMessageBox.information(self,"請選擇","請先選取一筆出貨資料。") ; return
        try:
            ar=FinancialService.create_receivable_from_delivery(d["id"]); self.refresh_all(); QMessageBox.information(self,"完成",f"已建立/取得應收：{ar.get('id')}")
        except Exception as e: QMessageBox.critical(self,"建立應收失敗",str(e))

    def invoice_selected_delivery(self):
        d=self._selected_delivery()
        if not d: QMessageBox.information(self,"請選擇","請先選取一筆出貨資料。\n") ; return
        try: ar=FinancialService.create_receivable_from_delivery(d["id"])
        except Exception as e: QMessageBox.critical(self,"無法建立應收",str(e)); return
        if FinancialService._text(ar.get("invoice_no")): QMessageBox.information(self,"已開票",f"此出貨已對應發票 {ar.get('invoice_no')}"); return
        dlg=InvoiceIssueDialog([ar],self)
        if dlg.exec()!=QDialog.DialogCode.Accepted:return
        try:
            inv=FinancialService.issue_invoice_from_delivery(d["id"],dlg.invoice_no.text(),dlg.invoice_date.text(),dlg.tax_rate.value(),dlg.term.currentText()); self.refresh_all(); QMessageBox.information(self,"完成",f"已開立發票 {inv.get('invoice_no')}，到期日 {inv.get('due_date')}。")
        except Exception as e: QMessageBox.critical(self,"開票失敗",str(e))

    def refresh_statement(self):
        customer=self.statement_customer.currentText().strip()
        df,s=FinancialService.customer_statement(customer,self.statement_start.text().strip(),self.statement_end.text().strip()); self._show_df(self.statement_table,df)
        self.statement_summary.setText(f"{customer or '未選客戶'}｜幣別：{s.get('currency') or '-'}｜期初 {s.get('opening',0):,.2f}｜本期應收 {s.get('debit',0):,.2f}｜本期收款 {s.get('credit',0):,.2f}｜期末 {s.get('closing',0):,.2f}" + ("｜⚠ 多幣別資料請分幣別檢視，不宜直接相加" if s.get('currency')=='多幣別' else ""))

    def refresh_collection(self):
        self._show_df(self.collection_table,FinancialService.collection_queue())

    def _selected_collection_row(self):
        row=self.collection_table.currentRow()
        if row<0:return None
        headers=[self.collection_table.horizontalHeaderItem(i).text() for i in range(self.collection_table.columnCount())]
        return {h:(self.collection_table.item(row,i).text() if self.collection_table.item(row,i) else "") for i,h in enumerate(headers)}

    def add_collection_action(self):
        rec=self._selected_collection_row()
        if not rec: QMessageBox.information(self,"請選擇","請先選取一筆應收催收資料。") ; return
        d=CollectionActionDialog(rec,self)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        try: FinancialService.add_collection_action(rec.get("應收編號",""),d.action_date.text(),d.method.currentText(),d.result.text(),d.next_followup.text(),d.note.text()); self.refresh_all()
        except Exception as e: QMessageBox.critical(self,"保存失敗",str(e))

    def refresh_payment_schedule(self):
        if not hasattr(self,"payment_schedule_table"):return
        days=self.payment_schedule_days.currentData() or 90; df,s=FinancialService.payment_schedule(days); self._show_df(self.payment_schedule_table,df); self.payment_schedule_summary.setText(f"{days} 天內待付款 {s.get('count',0)} 筆｜換算 TWD {s.get('total_twd',0):,.0f}" + (f"｜⚠ {s.get('missing_fx_count',0)} 筆缺少匯率" if s.get('missing_fx_count',0) else ""))

    def schedule_selected_payable(self):
        row=self.payment_schedule_table.currentRow()
        if row<0: QMessageBox.information(self,"請選擇","請先選取一筆付款排程。") ; return
        headers=[self.payment_schedule_table.horizontalHeaderItem(i).text() for i in range(self.payment_schedule_table.columnCount())]
        try: col=headers.index("應付編號")
        except ValueError:return
        item=self.payment_schedule_table.item(row,col); pid=item.text() if item else ""; p=next((x for x in FinancialService.load().get("payables",[]) if x.get("id")==pid),None)
        if not p:return
        d=ExpectedPaymentDialog(p,self)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        try: FinancialService.set_payable_expected_date(pid,d.expected.text()); self.refresh_all()
        except Exception as e: QMessageBox.critical(self,"保存失敗",str(e))

    def add_sales_return(self):
        data=FinancialService.load(); d=SalesAdjustmentDialog(data.get("receivables",[]),"退貨",self)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        try: FinancialService.create_sales_return(d.target.currentData(),d.biz_date.text(),d.qty.value(),d.amount.value(),d.reason.text(),d.restock.currentText()=="是",d.note.text()); self.refresh_all()
        except Exception as e: QMessageBox.critical(self,"新增失敗",str(e))

    def add_invoice_allowance(self):
        data=FinancialService.load(); rows=[x for x in data.get("receivables",[]) if FinancialService._text(x.get("invoice_no"))]; d=SalesAdjustmentDialog(rows,"折讓",self)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        try: FinancialService.create_invoice_allowance(d.target.currentData(),d.allowance_no.text(),d.biz_date.text(),d.amount.value(),d.reason.text(),d.note.text()); self.refresh_all()
        except Exception as e: QMessageBox.critical(self,"新增失敗",str(e))

    def _selected_id_from_table(self,table):
        row=table.currentRow()
        if row<0:return ""
        headers=[table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]
        if "id" not in headers:return ""
        item=table.item(row,headers.index("id")); return item.text() if item else ""

    def settle_selected_sales_adjustment(self):
        if self.sales_adjust_tabs.currentIndex()==0: table=self.sales_return_table; kind="銷售退貨"; key="sales_returns"
        else: table=self.allowance_table; kind="發票折讓"; key="invoice_allowances"
        rid=self._selected_id_from_table(table)
        if not rid: QMessageBox.information(self,"請選擇","請先選取一筆待沖帳資料。"); return
        rec=next((x for x in FinancialService.load().get(key,[]) if x.get("id")==rid),None)
        if not rec:return
        d=SettlementDialog(rec,self)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        try: FinancialService.settle_adjustment(kind,rid,d.amount.value(),d.biz_date.text()); self.refresh_all()
        except Exception as e: QMessageBox.critical(self,"沖帳失敗",str(e))

    def add_purchase_return(self):
        data=FinancialService.load(); d=PurchaseReturnDialog(data.get("payables",[]),self)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        try: FinancialService.create_purchase_return(d.target.currentData(),d.biz_date.text(),d.qty.value(),d.amount.value(),d.reason.text(),d.note.text()); self.refresh_all()
        except Exception as e: QMessageBox.critical(self,"新增失敗",str(e))

    def settle_selected_purchase_return(self):
        rid=self._selected_id_from_table(self.purchase_return_table)
        if not rid: QMessageBox.information(self,"請選擇","請先選取一筆進貨退貨資料。"); return
        rec=next((x for x in FinancialService.load().get("purchase_returns",[]) if x.get("id")==rid),None)
        if not rec:return
        d=SettlementDialog(rec,self)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        try: FinancialService.settle_adjustment("進貨退貨",rid,d.amount.value(),d.biz_date.text()); self.refresh_all()
        except Exception as e: QMessageBox.critical(self,"沖帳失敗",str(e))

    def preview_month_close(self):
        try:
            df,s=FinancialService.month_close_preview(self.close_period.text().strip()); self._show_df(self.close_preview_table,df); self.close_summary.setText(f"{s.get('period')}｜銷售 TWD {s.get('sales_twd',0):,.0f}｜收款 {s.get('receipts_twd',0):,.0f}｜付款 {s.get('payments_twd',0):,.0f}｜費用 {s.get('expenses_twd',0):,.0f}｜期末未收 {s.get('open_ar_twd',0):,.0f}｜期末未付 {s.get('open_ap_twd',0):,.0f}"+(f"｜⚠ 缺匯率 {s.get('missing_fx_count')} 筆" if s.get('missing_fx_count') else ""))
        except Exception as e: QMessageBox.critical(self,"預覽失敗",str(e))

    def close_month(self):
        period=self.close_period.text().strip()
        if QMessageBox.question(self,"確認月結",f"確定要鎖定 {period}？\n月結後該月份不得再補登發票、收付款、費用、退貨、折讓與沖帳。")!=QMessageBox.StandardButton.Yes:return
        try: FinancialService.close_month(period,self.close_note.text()); self.refresh_all(); self.preview_month_close(); QMessageBox.information(self,"月結完成",f"{period} 已鎖帳。")
        except Exception as e: QMessageBox.critical(self,"月結失敗",str(e))

    def reopen_month(self):
        period=self.close_period.text().strip(); reason=self.close_note.text().strip()
        if not reason: QMessageBox.warning(self,"需要原因","重開月份請先在備註欄輸入原因。"); return
        if QMessageBox.question(self,"確認重開",f"確定重開 {period}？此動作會留下稽核紀錄。")!=QMessageBox.StandardButton.Yes:return
        try: FinancialService.reopen_month(period,reason); self.refresh_all(); QMessageBox.information(self,"已重開",f"{period} 已解除鎖帳。")
        except Exception as e: QMessageBox.critical(self,"重開失敗",str(e))

    def export_table(self, table, title, kind):
        try:
            if kind=="xlsx": TableExportService.export_tables_excel(self,[(title,table)],default_name=f"{title}.xlsx")
            else: TableExportService.export_tables_pdf(self,[(title,table)],title=title,default_name=f"{title}.pdf")
        except Exception as e: QMessageBox.critical(self,"匯出失敗",str(e))
