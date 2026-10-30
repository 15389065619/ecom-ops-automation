"""飞书消息构造测试：不依赖网络。"""

from __future__ import annotations

import pytest

from ops_automation.notify import build_card, send_report

OVERVIEW = {"revenue": 1000.0, "net_profit": 120.0, "margin": 0.12, "return_rate": 0.03, "orders": 10, "units": 12,
            "amazon_fees": 150.0, "cogs": 500.0, "ad_spend": 80.0, "refunds": 0.0, "sku_count": 3, "refund_orders": 0}


def test_card_marks_p1_red():
    card = build_card("日报", OVERVIEW, [{"level": "P1", "type": "断货预警", "message": "SKU-A001 断货"}])
    assert card["card"]["header"]["template"] == "red"
    assert "断货预警" in card["card"]["elements"][1]["text"]["content"]


def test_card_green_when_no_alert():
    card = build_card("日报", OVERVIEW, [])
    assert card["card"]["header"]["template"] == "green"


def test_dry_run_does_not_need_webhook():
    result = send_report("", "", "日报", OVERVIEW, [], dry_run=True)
    assert result["dry_run"] is True
    assert result["code"] == 200
