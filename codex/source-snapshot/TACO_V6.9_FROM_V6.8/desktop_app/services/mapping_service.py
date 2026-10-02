from services.integration_db_service import IntegrationDbService
class MappingService:
    CANONICAL_FIELDS={'產品編號':'product_no','產品名稱':'product_name','數量':'quantity','單位':'unit','客戶':'customer','供應商':'supplier','倉庫':'warehouse','條碼':'barcode','單價':'unit_price','幣別':'currency','日期':'date','客戶訂號':'customer_order_no','採購單號':'purchase_order_no','規格':'specification'}
    @staticmethod
    def standardize_row(row,mappings): return {str(t):dict(row or {}).get(s) for s,t in dict(mappings or {}).items() if s in dict(row or {})}
    @staticmethod
    def validate_mapping(mappings):
        errors=[]; seen=set()
        for s,t in dict(mappings or {}).items():
            if not str(s).strip() or not str(t).strip(): errors.append('來源與 TACO 欄位不可空白')
            if t in seen: errors.append(f'TACO 欄位重複對應：{t}')
            seen.add(t)
        return errors
