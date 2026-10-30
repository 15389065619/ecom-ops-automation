"""把最新一期运营数据导出成仪表盘数据文件（docs/assets/data.js）。

先跑一次日报（python -m ops_automation），再执行本脚本。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from ops_automation.config import Settings  # noqa: E402
from ops_automation.db import Database  # noqa: E402
from ops_automation.pipeline import (  # noqa: E402
    build_alerts,
    clean_orders,
    daily_metrics,
    enrich,
    group_metrics,
    summarize,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="导出仪表盘数据")
    parser.add_argument("--date", default=None, help="报表截止日 YYYY-MM-DD，默认库里最新一天")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    settings = Settings.from_env(PROJECT_DIR)
    db = Database(settings.db_path)
    all_orders = db.read_table("orders")
    if all_orders.empty:
        raise SystemExit("库里没有订单，先执行: python -m ops_automation --days 30")

    end = pd.Timestamp(args.date) if args.date else pd.to_datetime(all_orders["order_date"]).max()
    start = end - timedelta(days=max(args.days, 1) - 1)
    start_s, end_s = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    stored = db.read_orders(start_s, end_s)
    enriched = enrich(clean_orders(stored), db.read_table("costs"), db.read_table("ad_spend"))

    overview = summarize(enriched)
    by_sku = group_metrics(enriched, ["sku"])
    by_marketplace = group_metrics(enriched, ["marketplace"])
    daily = daily_metrics(enriched)
    alerts = build_alerts(by_sku, enriched, db.read_table("inventory"), days=max(args.days, 1))

    data = {
        "period": {"start": start_s, "end": end_s, "days": args.days},
        "generated_at": date.today().isoformat(),
        "overview": overview,
        "daily": daily.to_dict("records"),
        "by_sku": by_sku.to_dict("records"),
        "by_marketplace": by_marketplace.to_dict("records"),
        "alerts": alerts.to_dict("records"),
    }

    out_dir = PROJECT_DIR / "docs" / "assets"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "data.js"
    target.write_text(
        "window.DASHBOARD_DATA = " + json.dumps(data, ensure_ascii=False, default=str, indent=2) + ";\n",
        encoding="utf-8",
    )
    print(f"仪表盘数据已写入: {target}（{start_s} ~ {end_s}，告警 {len(alerts)} 条）")


if __name__ == "__main__":
    main()
