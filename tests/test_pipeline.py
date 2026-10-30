"""管道与报表的关键口径测试。"""

from __future__ import annotations

import pandas as pd
import pytest
from openpyxl import load_workbook

from ops_automation.db import Database
from ops_automation.pipeline import build_alerts, clean_orders, enrich, group_metrics, summarize
from ops_automation.report import build_report


@pytest.fixture()
def raw_orders() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"order_id": "A-1", "marketplace": "US", "sku": "SKU-A001", "order_date": "2026-10-27",
             "quantity": 2, "item_price": 25.0, "shipping_credit": 0.0, "promo_discount": 0.0,
             "referral_fee": 7.5, "fba_fee": 6.0, "refund_amount": 0.0, "status": "Shipped"},
            {"order_id": "A-2", "marketplace": "US", "sku": "SKU-A001", "order_date": "2026-10-27",
             "quantity": 1, "item_price": 25.0, "shipping_credit": 0.0, "promo_discount": 0.0,
             "referral_fee": 3.75, "fba_fee": 3.0, "refund_amount": 0.0, "status": "shipped"},
            {"order_id": "A-3", "marketplace": "US", "sku": "SKU-A001", "order_date": "2026-10-27",
             "quantity": 1, "item_price": 25.0, "shipping_credit": 0.0, "promo_discount": 0.0,
             "referral_fee": 3.75, "fba_fee": 3.0, "refund_amount": 25.0, "status": "refunded"},
            {"order_id": "A-4", "marketplace": "US", "sku": "SKU-A001", "order_date": "2026-10-27",
             "quantity": 1, "item_price": 25.0, "shipping_credit": 0.0, "promo_discount": 0.0,
             "referral_fee": 3.75, "fba_fee": 3.0, "refund_amount": 0.0, "status": "Cancelled"},
        ]
    )


@pytest.fixture()
def costs() -> pd.DataFrame:
    return pd.DataFrame([{"sku": "SKU-A001", "product_cost": 8.0, "first_leg_cost": 1.5, "packaging_cost": 0.5}])


@pytest.fixture()
def ads() -> pd.DataFrame:
    return pd.DataFrame([{"date": "2026-10-27", "marketplace": "US", "sku": "SKU-A001", "ad_spend": 9.0}])


def test_clean_orders_drops_cancelled_and_duplicates(raw_orders):
    cleaned = clean_orders(raw_orders)
    assert set(cleaned["order_id"]) == {"A-1", "A-2", "A-3"}
    assert (cleaned["status"] == "cancelled").sum() == 0


def test_profit_math(raw_orders, costs, ads):
    enriched = enrich(clean_orders(raw_orders), costs, ads)
    by_id = enriched.set_index("order_id")
    # 订单 A-1：收入 50，佣金 7.5，FBA 6，成本 (8+1.5+0.5)*2=20，广告按件数摊 9*2/4=4.5
    a1 = by_id.loc["A-1"]
    assert a1["gross_revenue"] == pytest.approx(50.0)
    assert a1["cogs"] == pytest.approx(20.0)
    assert a1["ad_allocated"] == pytest.approx(4.5)
    assert a1["net_profit"] == pytest.approx(50 - 13.5 - 20 - 4.5)

    # 广告费全部分摊完，不应凭空多出或少算
    assert enriched["ad_allocated"].sum() == pytest.approx(9.0)
    assert summarize(enriched)["net_profit"] == pytest.approx(enriched["net_profit"].sum())


def test_alerts_low_margin_and_stockout(raw_orders, costs, ads):
    enriched = enrich(clean_orders(raw_orders), costs, ads)
    by_sku = group_metrics(enriched, ["sku"])
    inventory = pd.DataFrame(
        [{"sku": "SKU-A001", "marketplace": "US", "available_qty": 6, "inbound_qty": 0, "safety_stock": 20}]
    )
    alerts = build_alerts(by_sku, enriched, inventory, days=1)
    types = set(alerts["type"])
    assert "断货预警" in types
    assert "库存预警" in types
    assert "退货预警" in types


def test_report_contains_expected_sheets(tmp_path, raw_orders, costs, ads):
    enriched = enrich(clean_orders(raw_orders), costs, ads)
    overview = summarize(enriched)
    by_sku = group_metrics(enriched, ["sku"])
    path = build_report(
        tmp_path, "2026-10-27", "2026-10-27", "2026-10-27",
        overview, by_sku, group_metrics(enriched, ["marketplace"]),
        pd.DataFrame(), enriched, pd.DataFrame(),
    )
    assert path.exists()
    wb = load_workbook(path)
    assert wb.sheetnames == ["总览", "按SKU", "按站点", "每日趋势", "告警", "订单明细"]
    assert wb["总览"]["B10"].value == pytest.approx(overview["net_profit"], abs=0.01)


def test_db_upsert_is_idempotent(tmp_path, raw_orders):
    db = Database(tmp_path / "ops.db")
    cleaned = clean_orders(raw_orders)
    db.upsert("orders", cleaned, ["order_id", "sku"])
    db.upsert("orders", cleaned, ["order_id", "sku"])
    stored = db.read_orders("2026-10-27", "2026-10-27")
    assert len(stored) == len(cleaned)
