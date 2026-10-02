from services.dashboard_data_service import DashboardDataService
from services.financial_service import FinancialService


class NotificationService:
    @staticmethod
    def build_notifications():
        d = DashboardDataService.summary()
        items = []

        def add(level, title, message, target):
            items.append({"level": level, "title": title, "message": message, "target": target})

        if d.get("urgent_purchase_count", 0) > 0:
            add("urgent", "急需採購", f"有 {d['urgent_purchase_count']} 個品項需要優先處理。", "urgent")
        if d.get("unmapped_count", 0) > 0:
            add("warning", "客戶需求尚未對應", f"仍有 {d['unmapped_count']} 筆需求需要產品對應。", "unmapped")
        if d.get("transfer_count", 0) > 0:
            add("info", "可跨倉調撥", f"目前有 {d['transfer_count']} 筆跨倉調撥建議。", "transfer")
        if d.get("transfer_remaining_shortage", 0) > 0:
            add("urgent", "調撥後仍有缺口", f"有 {d['transfer_remaining_shortage']} 個品項調撥後仍缺貨。", "shortage")
        if d.get("low_stock_count", 0) > 0:
            add("warning", "低庫存", f"有 {d['low_stock_count']} 個品項需要注意庫存。", "shortage")
        if d.get("container_count", 0) > 0 and 0 < d.get("last_container_usage", 0) < 70:
            add("info", "貨櫃尚有空間", f"最後一櫃目前約使用 {d['last_container_usage']:.0f}% ，可再評估併櫃。", "container")
        try:
            f = FinancialService.summary()
            if f.get("overdue_count", 0) > 0:
                add("urgent", "應收帳款逾期", f"目前有 {f['overdue_count']} 筆逾期應收，約 TWD {f.get('overdue_twd',0):,.0f}。", "finance")
            if f.get("over_credit_count", 0) > 0:
                add("urgent", "客戶信用額度超限", f"目前有 {f.get('over_credit_count',0)} 家客戶超過信用額度。", "finance")
            elif f.get("near_credit_count", 0) > 0:
                add("warning", "客戶信用額度接近上限", f"目前有 {f.get('near_credit_count',0)} 家客戶已接近信用額度警示線。", "finance")
            if f.get("forecast_30d_negative_date"):
                add("urgent", "30天現金流預警", f"依目前應收、應付與預計項目，預估 {f.get('forecast_30d_negative_date')} 可用現金可能低於 0。", "finance")
            if f.get("forecast_30d_missing_fx_count", 0) > 0:
                add("warning", "現金流預測缺少匯率", f"有 {f.get('forecast_30d_missing_fx_count',0)} 筆外幣應收 / 應付因缺少匯率未納入 30 天現金流預測。", "finance")
            if f.get("pending_sales_order_count", 0) > 0:
                add("info", "銷售訂單待出貨", f"目前有 {f.get('pending_sales_order_count',0)} 筆銷售訂單尚未完全出貨。", "finance")
            if f.get("payment_schedule_30d_count", 0) > 0:
                add("warning", "30天內供應商付款", f"未來30天有 {f.get('payment_schedule_30d_count',0)} 筆待付款，約 TWD {f.get('payment_schedule_30d_twd',0):,.0f}。", "finance")
        except Exception:
            pass
        if not items:
            add("ok", "目前沒有重大待辦", "尚未發現急需採購、未對應需求或調撥後缺口。", "dashboard")
        return items
