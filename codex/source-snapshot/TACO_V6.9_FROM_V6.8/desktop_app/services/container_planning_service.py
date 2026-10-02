import math
from collections import defaultdict

import pandas as pd

from services.import_profile_service import ImportProfileService
from services.system_settings_service import SystemSettingsService


class ContainerPlanningService:
    """把採購建議轉為可裝櫃資料，並明確列出不能計算的原因。"""

    REQUIRED_PROFILE_FIELDS = (
        "purchase_qty_unit", "units_per_carton",
        "carton_length_cm", "carton_width_cm", "carton_height_cm",
    )

    @staticmethod
    def _num(value):
        try:
            if value is None or pd.isna(value):
                return 0.0
            if isinstance(value, str):
                value = value.replace(",", "").strip()
            return float(value or 0)
        except Exception:
            return 0.0

    @staticmethod
    def validate_row(row):
        pno = str(row.get("產品編號", "")).strip()
        pname = str(row.get("產品名稱", "")).strip()
        supplier = str(row.get("本次採購供應商", "")).strip()
        qty = ContainerPlanningService._num(row.get("實際採購量", row.get("建議採購量", 0)))
        issues = []
        if qty <= 0:
            issues.append("實際採購量為 0")
        if not supplier:
            issues.append("尚未選擇本次採購供應商")

        profile = ImportProfileService.get_profile(pno, supplier)
        if not ImportProfileService.has_profile(pno, supplier):
            issues.append("尚未建立包裝／進口設定")
        else:
            purchase_unit = str(profile.get("purchase_qty_unit", "")).strip()
            units_per_carton = ContainerPlanningService._num(profile.get("units_per_carton", 0))
            L = ContainerPlanningService._num(profile.get("carton_length_cm", 0))
            W = ContainerPlanningService._num(profile.get("carton_width_cm", 0))
            H = ContainerPlanningService._num(profile.get("carton_height_cm", 0))
            if not purchase_unit:
                issues.append("缺少採購數量單位")
            if purchase_unit != "箱" and units_per_carton <= 0:
                issues.append("缺少每箱數量")
            if L <= 0 or W <= 0 or H <= 0:
                issues.append("缺少紙箱長／寬／高")

        return {
            "產品編號": pno,
            "產品名稱": pname,
            "供應商": supplier,
            "實際採購量": qty,
            "問題": "；".join(issues),
            "可計算": not issues,
            "profile": profile,
        }

    @staticmethod
    def build_plan(purchase_df, supplier_name=""):
        if purchase_df is None or purchase_df.empty:
            return {
                "valid_df": pd.DataFrame(), "issues_df": pd.DataFrame(),
                "summary": ContainerPlanningService.empty_summary(),
            }

        valid_rows, issue_rows = [], []
        skipped_zero = 0
        for _, row in purchase_df.iterrows():
            result = ContainerPlanningService.validate_row(row)
            if supplier_name and supplier_name != "全部供應商" and result["供應商"] != supplier_name:
                continue
            if result["實際採購量"] <= 0:
                skipped_zero += 1
                continue
            if not result["可計算"]:
                issue_rows.append({k: v for k, v in result.items() if k != "profile"})
                continue

            metrics = ImportProfileService.calculate(result["實際採購量"], result["profile"])
            valid_rows.append({
                "產品編號": result["產品編號"],
                "產品名稱": result["產品名稱"],
                "本次採購供應商": result["供應商"],
                "實際採購量": result["實際採購量"],
                **metrics,
            })

        valid_df = pd.DataFrame(valid_rows)
        issues_df = pd.DataFrame(issue_rows)
        capacity = float(SystemSettingsService.load().get("warehouse", {}).get("container_cbm", 66.5) or 66.5)
        total_cbm = float(pd.to_numeric(valid_df.get("本次CBM", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not valid_df.empty else 0.0
        container_count = int(math.ceil(total_cbm / capacity)) if total_cbm > 0 and capacity > 0 else 0
        last_cbm = (total_cbm - capacity * (container_count - 1)) if container_count > 0 else 0.0
        last_usage = (last_cbm / capacity * 100) if capacity > 0 and container_count > 0 else 0.0
        remaining_last = max(0.0, capacity - last_cbm) if container_count > 0 else capacity
        by_currency = defaultdict(float)
        if not valid_df.empty:
            for _, r in valid_df.iterrows():
                by_currency[str(r.get("幣別", "")).strip()] += ContainerPlanningService._num(r.get("商品總價", 0))

        summary = {
            "valid_count": len(valid_df),
            "issue_count": len(issues_df),
            "skipped_zero_count": skipped_zero,
            "capacity_cbm": capacity,
            "total_cbm": round(total_cbm, 4),
            "container_count": container_count,
            "last_container_cbm": round(last_cbm, 4),
            "last_container_usage_pct": round(last_usage, 2),
            "remaining_last_cbm": round(remaining_last, 4),
            "amounts_by_currency": dict(by_currency),
        }
        return {"valid_df": valid_df, "issues_df": issues_df, "summary": summary}

    @staticmethod
    def empty_summary():
        return {
            "valid_count": 0, "issue_count": 0, "skipped_zero_count": 0,
            "capacity_cbm": 66.5, "total_cbm": 0.0, "container_count": 0,
            "last_container_cbm": 0.0, "last_container_usage_pct": 0.0,
            "remaining_last_cbm": 66.5, "amounts_by_currency": {},
        }
