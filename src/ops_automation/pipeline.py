"""数据管道：清洗 -> 关联成本/广告 -> 算利润 -> 聚合 -> 告警。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import MARGIN_ALERT_THRESHOLD, RETURN_RATE_ALERT_THRESHOLD, STOCK_COVER_ALERT_DAYS

NUMERIC_COLS = [
    "quantity",
    "item_price",
    "shipping_credit",
    "promo_discount",
    "referral_fee",
    "fba_fee",
    "refund_amount",
]
COST_COLS = ["product_cost", "first_leg_cost", "packaging_cost"]


def clean_orders(df: pd.DataFrame) -> pd.DataFrame:
    """统一类型与口径：去空格、去重、剔除取消单。"""
    orders = df.copy()
    for col in NUMERIC_COLS:
        orders[col] = pd.to_numeric(orders[col], errors="coerce").fillna(0.0)
    orders["order_date"] = pd.to_datetime(orders["order_date"]).dt.normalize()
    orders["order_id"] = orders["order_id"].astype(str).str.strip()
    orders["sku"] = orders["sku"].astype(str).str.strip().str.upper()
    orders["marketplace"] = orders["marketplace"].astype(str).str.strip().str.upper()
    orders["status"] = orders["status"].astype(str).str.strip().str.lower()
    orders["quantity"] = orders["quantity"].astype(int)
    orders = orders[orders["quantity"] > 0]
    orders = orders[~orders["status"].isin(["cancelled", "canceled", "pending"])]
    orders = orders.drop_duplicates(subset=["order_id", "sku"], keep="last")
    return orders.reset_index(drop=True)


def normalize_costs(costs: pd.DataFrame) -> pd.DataFrame:
    costs = costs.copy()
    costs["sku"] = costs["sku"].astype(str).str.strip().str.upper()
    for col in COST_COLS:
        costs[col] = pd.to_numeric(costs[col], errors="coerce").fillna(0.0)
    return costs


def enrich(orders: pd.DataFrame, costs: pd.DataFrame, ads: pd.DataFrame) -> pd.DataFrame:
    """把成本、广告费摊到订单行，并计算毛利/净利。"""
    result = orders.copy()
    if result.empty:
        for col in COST_COLS + ["ad_allocated", "gross_revenue", "amazon_fees", "cogs", "net_profit", "margin"]:
            result[col] = 0.0
        return result

    result = result.merge(normalize_costs(costs), on="sku", how="left")
    for col in COST_COLS:
        result[col] = result[col].fillna(0.0)

    ads = ads.copy()
    ads["date"] = pd.to_datetime(ads["date"]).dt.normalize()
    ads["sku"] = ads["sku"].astype(str).str.strip().str.upper()
    ads["marketplace"] = ads["marketplace"].astype(str).str.strip().str.upper()
    ads["ad_spend"] = pd.to_numeric(ads["ad_spend"], errors="coerce").fillna(0.0)
    ads = ads.groupby(["date", "marketplace", "sku"], as_index=False)["ad_spend"].sum()

    result = result.merge(
        ads,
        how="left",
        left_on=["order_date", "marketplace", "sku"],
        right_on=["date", "marketplace", "sku"],
    )
    result["ad_spend_sku_day"] = result["ad_spend"].fillna(0.0)
    result = result.drop(columns=["date", "ad_spend"])

    # 同一天同 SKU 可能有多个订单，按件数比例摊广告费
    units = result.groupby(["order_date", "marketplace", "sku"])["quantity"].transform("sum").replace(0, np.nan)
    result["ad_allocated"] = (result["ad_spend_sku_day"] * result["quantity"] / units).fillna(0.0)

    result["gross_revenue"] = (
        result["item_price"] * result["quantity"] + result["shipping_credit"] - result["promo_discount"]
    )
    result["amazon_fees"] = result["referral_fee"] + result["fba_fee"]
    result["cogs"] = (result["product_cost"] + result["first_leg_cost"] + result["packaging_cost"]) * result["quantity"]
    result["net_profit"] = (
        result["gross_revenue"] - result["amazon_fees"] - result["cogs"] - result["ad_allocated"] - result["refund_amount"]
    )
    result["margin"] = np.where(
        result["gross_revenue"] > 0, result["net_profit"] / result["gross_revenue"], np.nan
    )
    return result.reset_index(drop=True)


def summarize(orders: pd.DataFrame) -> dict:
    """总览 KPI。"""
    if orders.empty:
        return {
            "orders": 0, "units": 0, "revenue": 0.0, "amazon_fees": 0.0, "cogs": 0.0,
            "ad_spend": 0.0, "refunds": 0.0, "net_profit": 0.0, "margin": 0.0,
            "return_rate": 0.0, "sku_count": 0, "refund_orders": 0,
        }
    revenue = float(orders["gross_revenue"].sum())
    net_profit = float(orders["net_profit"].sum())
    refund_orders = int((orders["refund_amount"] > 0).sum())
    return {
        "orders": int(len(orders)),
        "units": int(orders["quantity"].sum()),
        "revenue": round(revenue, 2),
        "amazon_fees": round(float(orders["amazon_fees"].sum()), 2),
        "cogs": round(float(orders["cogs"].sum()), 2),
        "ad_spend": round(float(orders["ad_allocated"].sum()), 2),
        "refunds": round(float(orders["refund_amount"].sum()), 2),
        "net_profit": round(net_profit, 2),
        "margin": round(net_profit / revenue, 4) if revenue else 0.0,
        "return_rate": round(refund_orders / len(orders), 4),
        "refund_orders": refund_orders,
        "sku_count": int(orders["sku"].nunique()),
    }


def group_metrics(orders: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """按维度聚合，附带退货率。"""
    if orders.empty:
        return pd.DataFrame(columns=[*by, "orders", "units", "revenue", "net_profit", "margin", "ad_spend", "return_rate"])
    grouped = orders.groupby(by, as_index=False).agg(
        orders=("order_id", "count"),
        units=("quantity", "sum"),
        revenue=("gross_revenue", "sum"),
        net_profit=("net_profit", "sum"),
        ad_spend=("ad_allocated", "sum"),
        refund_orders=("refund_amount", lambda s: int((s > 0).sum())),
    )
    grouped["margin"] = np.where(grouped["revenue"] > 0, grouped["net_profit"] / grouped["revenue"], 0.0)
    grouped["return_rate"] = grouped["refund_orders"] / grouped["orders"]
    for col in ["revenue", "net_profit", "margin", "ad_spend", "return_rate"]:
        grouped[col] = grouped[col].round(4)
    return grouped.drop(columns=["refund_orders"]).sort_values("revenue", ascending=False).reset_index(drop=True)


def daily_metrics(orders: pd.DataFrame) -> pd.DataFrame:
    if orders.empty:
        return pd.DataFrame(columns=["order_date", "orders", "units", "revenue", "net_profit", "margin"])
    daily = orders.groupby("order_date", as_index=False).agg(
        orders=("order_id", "count"),
        units=("quantity", "sum"),
        revenue=("gross_revenue", "sum"),
        net_profit=("net_profit", "sum"),
    )
    daily["margin"] = np.where(daily["revenue"] > 0, daily["net_profit"] / daily["revenue"], 0.0)
    daily["order_date"] = daily["order_date"].dt.strftime("%Y-%m-%d")
    for col in ["revenue", "net_profit", "margin"]:
        daily[col] = daily[col].round(4)
    return daily


def build_alerts(by_sku: pd.DataFrame, orders: pd.DataFrame, inventory: pd.DataFrame, days: int) -> pd.DataFrame:
    """利润 / 退货 / 库存三类告警，输出给报表和飞书复用。"""
    alerts: list[dict] = []
    if not by_sku.empty:
        for row in by_sku.itertuples(index=False):
            if row.revenue > 0 and row.margin < MARGIN_ALERT_THRESHOLD:
                alerts.append({
                    "level": "P1" if row.margin < 0 else "P2",
                    "type": "利润预警",
                    "target": row.sku,
                    "message": f"{row.sku} 净利率 {row.margin:.2%}，低于 {MARGIN_ALERT_THRESHOLD:.0%} 红线（净利 {row.net_profit:.2f}）",
                })
            if row.return_rate > RETURN_RATE_ALERT_THRESHOLD:
                alerts.append({
                    "level": "P1" if row.return_rate > RETURN_RATE_ALERT_THRESHOLD * 2 else "P2",
                    "type": "退货预警",
                    "target": row.sku,
                    "message": f"{row.sku} 退货率 {row.return_rate:.2%}，高于 {RETURN_RATE_ALERT_THRESHOLD:.0%}",
                })

    if not inventory.empty and not orders.empty:
        inv = inventory.copy()
        inv["available_qty"] = pd.to_numeric(inv["available_qty"], errors="coerce").fillna(0)
        inv["safety_stock"] = pd.to_numeric(inv["safety_stock"], errors="coerce").fillna(0)
        total_inv = inv.groupby("sku", as_index=False).agg(
            available_qty=("available_qty", "sum"), safety_stock=("safety_stock", "sum")
        )
        sold = orders.groupby("sku", as_index=False)["quantity"].sum().rename(columns={"quantity": "units"})
        merged = total_inv.merge(sold, on="sku", how="left").fillna({"units": 0})
        avg_daily = merged["units"] / max(days, 1)
        merged["cover_days"] = np.where(avg_daily > 0, merged["available_qty"] / avg_daily.replace(0, np.nan), np.inf)
        for row in merged.itertuples(index=False):
            cover = row.cover_days
            if np.isfinite(cover) and cover < STOCK_COVER_ALERT_DAYS:
                alerts.append({
                    "level": "P1",
                    "type": "断货预警",
                    "target": row.sku,
                    "message": f"{row.sku} 可售 {int(row.available_qty)} 件，库存可支撑 {cover:.1f} 天（<{STOCK_COVER_ALERT_DAYS} 天）",
                })
            if row.available_qty < row.safety_stock:
                alerts.append({
                    "level": "P2",
                    "type": "库存预警",
                    "target": row.sku,
                    "message": f"{row.sku} 可用库存 {int(row.available_qty)} 件，低于安全库存 {int(row.safety_stock)} 件",
                })

    columns = ["level", "type", "target", "message"]
    return pd.DataFrame(alerts, columns=columns).sort_values(["level", "type"]).reset_index(drop=True)
