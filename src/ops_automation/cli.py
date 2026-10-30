"""命令行入口：取数 -> 落库 -> 算利 -> 出报表 -> 推飞书。"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from .config import Settings
from .db import Database
from .notify import send_report
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ops-report", description="跨境电商运营日报自动化")
    parser.add_argument("--source", choices=["mock", "spapi"], default="mock", help="数据源，默认 mock 离线数据")
    parser.add_argument("--date", default=None, help="报表截止日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--days", type=int, default=30, help="统计窗口天数，默认 30")
    parser.add_argument("--base-dir", default=None, help="项目根目录，默认自动定位")
    parser.add_argument("--report-dir", default=None, help="报表输出目录，默认 reports/")
    parser.add_argument("--no-notify", action="store_true", help="不推送飞书")
    parser.add_argument("--dry-run", action="store_true", help="只打印待发送消息，不真正推送")
    return parser


def run(args: argparse.Namespace) -> int:
    settings = Settings.from_env(Path(args.base_dir).resolve() if args.base_dir else None)
    end = pd.Timestamp(args.date) if args.date else pd.Timestamp(date.today())
    start = end - timedelta(days=max(args.days, 1) - 1)
    start_s, end_s = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    source = build_source(args.source, settings)
    bundle = source.load(start_s, end_s)

    db = Database(settings.db_path)
    orders = clean_orders(bundle["orders"])
    db.upsert("orders", orders, ["order_id", "sku"])
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

    # 从库里回读，保证报表口径与落库数据一致，重复跑也不会重复计账
    stored = db.read_orders(start_s, end_s)
    enriched = enrich(clean_orders(stored), db.read_table("costs"), db.read_table("ad_spend"))

    overview = summarize(enriched)
    by_sku = group_metrics(enriched, ["sku"])
    by_marketplace = group_metrics(enriched, ["marketplace"])
    daily = daily_metrics(enriched)
    alerts = build_alerts(by_sku, enriched, db.read_table("inventory"), days=max(args.days, 1))

    report_dir = Path(args.report_dir) if args.report_dir else settings.reports_dir
    path = build_report(
        report_dir, end_s, start_s, end_s, overview, by_sku, by_marketplace, daily, enriched, alerts
    )
    db.record_run(end_s, str(path), overview["net_profit"], overview["margin"])

    print(f"报表已生成：{path}")
    print(
        f"订单 {overview['orders']}｜销售额 {overview['revenue']:,.2f}｜净利 {overview['net_profit']:,.2f}"
        f"｜净利率 {overview['margin']:.2%}｜退货率 {overview['return_rate']:.2%}"
    )
    print(f"告警 {len(alerts)} 条：P1 {int((alerts['level'] == 'P1').sum()) if not alerts.empty else 0} 条")

    if not args.no_notify:
        send_report(
            settings.feishu_webhook,
            settings.feishu_secret,
            title=f"运营日报 {end_s}",
            overview=overview,
            alerts_rows=alerts.to_dict("records") if not alerts.empty else [],
            dry_run=args.dry_run,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))
