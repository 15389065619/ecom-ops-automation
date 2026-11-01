"""FastAPI 接口：把日报管道包装成 HTTP 服务，供 n8n 等外部系统调用。

启动：python -m ops_automation.api   （默认 8000 端口）
调用：POST /run-report?days=30      返回当日概览 + 告警 JSON
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import uvicorn
from fastapi import FastAPI, Query

from .config import Settings
from .db import Database
from .pipeline import (
    build_alerts,
    clean_orders,
    daily_metrics,
    enrich,
    group_metrics,
    normalize_costs,
    summarize,
)
from .report import build_report
from .sources import AD_COLUMNS, INVENTORY_COLUMNS, build_source

app = FastAPI(title="ops-automation", version="1.0.0")


@app.post("/run-report")
def run_report(
    days: int = Query(default=30, ge=1, le=365),
    report_date: str | None = Query(default=None, description="截止日期 YYYY-MM-DD，默认今天"),
    source: str = Query(default="mock", pattern="^(mock|spapi)$"),
) -> dict:
    """跑一遍日报管道，返回概览指标和告警列表。"""
    settings = Settings.from_env(None)
    end = pd.Timestamp(report_date) if report_date else pd.Timestamp(date.today())
    start = end - timedelta(days=days - 1)
    start_s, end_s = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    bundle = build_source(source, settings).load(start_s, end_s)

    db = Database(settings.db_path)
    db.upsert("orders", clean_orders(bundle["orders"]), ["order_id", "sku"])
    db.upsert("costs", normalize_costs(bundle["costs"]), ["sku"])

    ads = bundle["ads"].copy()
    ads["date"] = pd.to_datetime(ads["date"]).dt.strftime("%Y-%m-%d")
    ads["sku"] = ads["sku"].astype(str).str.strip().str.upper()
    ads["marketplace"] = ads["marketplace"].astype(str).str.strip().str.upper()
    ads["ad_spend"] = pd.to_numeric(ads["ad_spend"], errors="coerce").fillna(0.0)
    db.upsert("ad_spend", ads[AD_COLUMNS], ["date", "marketplace", "sku"])

    inventory = bundle["inventory"].copy()
    inventory["sku"] = inventory["sku"].astype(str).str.strip().str.upper()
    inventory["marketplace"] = inventory["marketplace"].astype(str).str.strip().str.upper()
    for col in ["available_qty", "inbound_qty", "safety_stock"]:
        inventory[col] = pd.to_numeric(inventory[col], errors="coerce").fillna(0).astype(int)
    db.upsert("inventory", inventory[INVENTORY_COLUMNS], ["sku", "marketplace"])

    stored = db.read_orders(start_s, end_s)
    enriched = enrich(clean_orders(stored), db.read_table("costs"), db.read_table("ad_spend"))

    overview = summarize(enriched)
    by_sku = group_metrics(enriched, ["sku"])
    by_marketplace = group_metrics(enriched, ["marketplace"])
    daily = daily_metrics(enriched)
    alerts = build_alerts(by_sku, enriched, db.read_table("inventory"), days=days)

    path = build_report(
        Path(settings.reports_dir), end_s, start_s, end_s,
        overview, by_sku, by_marketplace, daily, enriched, alerts,
    )
    db.record_run(end_s, str(path), overview["net_profit"], overview["margin"])

    return {
        "date": end_s,
        "window_days": days,
        "orders": int(overview["orders"]),
        "revenue": round(float(overview["revenue"]), 2),
        "net_profit": round(float(overview["net_profit"]), 2),
        "margin": round(float(overview["margin"]), 4),
        "return_rate": round(float(overview["return_rate"]), 4),
        "alert_count": len(alerts),
        "p1_count": int((alerts["level"] == "P1").sum()) if not alerts.empty else 0,
        "alerts": alerts.to_dict("records") if not alerts.empty else [],
        "report_path": str(path),
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("ops_automation.api:app", host="0.0.0.0", port=8000, reload=False)
