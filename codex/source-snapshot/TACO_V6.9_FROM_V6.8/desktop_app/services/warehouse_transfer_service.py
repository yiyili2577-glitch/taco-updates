import pandas as pd

from services.warehouse_service import WarehouseService


class WarehouseTransferService:
    """V4.4 三倉需求分配與跨倉調撥建議。

    原則：
    1. 每筆客戶需求先由「履約／出貨分流」指定出貨倉。
    2. 各倉先用自己的現有庫存支應指定需求。
    3. 有剩餘庫存的倉，可調撥給缺貨倉。
    4. 調撥仍不足的部分才標記為「調撥後缺口」。

    此處只規劃「目前三倉現貨」的內部調撥，不把預計到貨視為可立即調撥庫存。
    """

    @staticmethod
    def to_number(value):
        try:
            if value is None or pd.isna(value):
                return 0.0
            if isinstance(value, str):
                value = value.replace(",", "").strip()
                if not value:
                    return 0.0
            return float(value)
        except Exception:
            return 0.0

    @staticmethod
    def _demand_map(demand_df):
        result = {}
        if demand_df is None or demand_df.empty or "產品編號" not in demand_df.columns:
            return result
        for _, row in demand_df.iterrows():
            pno = str(row.get("產品編號", "")).strip()
            if not pno:
                continue
            result[pno] = row.to_dict()
        return result

    @staticmethod
    def calculate(inventory_df, demand_df=None):
        names = WarehouseService.load_names()
        summary_rows = []
        transfer_rows = []

        if inventory_df is None or inventory_df.empty or "產品編號" not in inventory_df.columns:
            return {
                "summary_df": pd.DataFrame(),
                "transfer_df": pd.DataFrame(),
            }

        demand_map = WarehouseTransferService._demand_map(demand_df)

        for _, row in inventory_df.iterrows():
            pno = str(row.get("產品編號", "")).strip()
            if not pno:
                continue
            pname = str(row.get("產品名稱", row.get("品名", ""))).strip()
            demand = demand_map.get(pno, {})

            stocks = {
                name: WarehouseTransferService.to_number(row.get(name, 0))
                for name in names
            }
            demands = {
                name: WarehouseTransferService.to_number(demand.get(f"{name}出貨需求", 0))
                for name in names
            }

            before = {name: stocks[name] - demands[name] for name in names}
            after = dict(before)

            # 缺貨倉與可供調出倉；每次都優先處理最大缺口、最大餘量。
            receivers = sorted(
                [name for name in names if after[name] < 0],
                key=lambda n: after[n]
            )
            donors = sorted(
                [name for name in names if after[name] > 0],
                key=lambda n: after[n],
                reverse=True
            )

            product_transfers = []
            for receiver in receivers:
                need = max(0.0, -after[receiver])
                if need <= 0:
                    continue
                # 每次重新依可用餘量排序，避免前一筆調撥後順序失真。
                donors = sorted(
                    [name for name in names if after[name] > 0],
                    key=lambda n: after[n],
                    reverse=True
                )
                for donor in donors:
                    if need <= 0:
                        break
                    available = max(0.0, after[donor])
                    if available <= 0:
                        continue
                    qty = min(available, need)
                    if qty <= 0:
                        continue
                    after[donor] -= qty
                    after[receiver] += qty
                    need -= qty
                    record = {
                        "產品編號": pno,
                        "產品名稱": pname,
                        "調出倉": donor,
                        "調入倉": receiver,
                        "建議調撥量": round(qty, 2),
                    }
                    transfer_rows.append(record)
                    product_transfers.append(record)

            before_gap = sum(max(0.0, -v) for v in before.values())
            transferable = sum(x["建議調撥量"] for x in product_transfers)
            after_gap = sum(max(0.0, -v) for v in after.values())

            suggestions = [
                f"{x['調出倉']}→{x['調入倉']} {x['建議調撥量']:g}"
                for x in product_transfers
            ]
            if after_gap > 0:
                suggestions.append(f"調撥後仍缺 {after_gap:g}")
            if not suggestions:
                suggestions.append("不需跨倉調撥")

            out = {
                "產品編號": pno,
                "產品名稱": pname,
                "三倉現有庫存": round(sum(stocks.values()), 2),
                "三倉指定出貨需求": round(sum(demands.values()), 2),
                "調撥前缺口": round(before_gap, 2),
                "可由他倉調撥": round(transferable, 2),
                "調撥後缺口": round(after_gap, 2),
                "調撥建議": "；".join(suggestions),
            }
            for name in names:
                out[f"{name}庫存"] = round(stocks[name], 2)
                out[f"{name}出貨需求"] = round(demands[name], 2)
                out[f"{name}需求後庫存"] = round(before[name], 2)
                out[f"{name}調撥後庫存"] = round(after[name], 2)

            summary_rows.append(out)

        summary_df = pd.DataFrame(summary_rows)
        transfer_df = pd.DataFrame(transfer_rows)

        # 優先顯示真正需要調撥或仍有缺口的品項。
        if not summary_df.empty:
            summary_df["_priority"] = (
                (pd.to_numeric(summary_df["調撥後缺口"], errors="coerce").fillna(0) > 0).astype(int) * 2
                + (pd.to_numeric(summary_df["可由他倉調撥"], errors="coerce").fillna(0) > 0).astype(int)
            )
            summary_df = summary_df.sort_values(
                by=["_priority", "調撥後缺口", "可由他倉調撥"],
                ascending=[False, False, False]
            ).drop(columns=["_priority"]).reset_index(drop=True)

        return {
            "summary_df": summary_df,
            "transfer_df": transfer_df,
        }

    @staticmethod
    def enrich_dataframe(df, demand_df=None):
        if df is None or df.empty:
            return df
        result = WarehouseTransferService.calculate(df, demand_df)
        summary = result["summary_df"]
        if summary.empty:
            return df

        # 不重複帶入產品名稱與原本倉庫庫存欄；只補分析欄位。
        keep = ["產品編號"]
        for col in summary.columns:
            if col in {"產品編號", "產品名稱", "三倉現有庫存"}:
                continue
            keep.append(col)

        base = df.copy()
        drop_existing = [c for c in keep if c != "產品編號" and c in base.columns]
        if drop_existing:
            base = base.drop(columns=drop_existing)
        return base.merge(summary[keep], on="產品編號", how="left")
