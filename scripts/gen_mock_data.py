"""生成离线 mock 数据，便于任何机器上复现整条管道。

用法：python scripts/gen_mock_data.py
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

SEED = 20261029
END_DATE = date(2026, 10, 29)
DAYS = 30
MARKETPLACES = ["US", "UK", "DE"]
SKUS = {
    "SKU-A001": 24.99,
    "SKU-A002": 39.99,
    "SKU-A003": 15.49,
    "SKU-B001": 59.99,
    "SKU-B002": 89.99,
    "SKU-C001": 12.99,
    "SKU-C002": 34.50,
    "SKU-D001": 109.00,
    "SKU-D002": 19.90,
}


def main() -> None:
    random.seed(SEED)
    out_dir = Path(__file__).resolve().parents[1] / "data" / "mock"
    out_dir.mkdir(parents=True, exist_ok=True)

    orders = []
    refund_skus = {"SKU-C001", "SKU-D002"}
    for offset in range(DAYS):
        day = END_DATE - timedelta(days=DAYS - 1 - offset)
        for marketplace in MARKETPLACES:
            for sku, price in SKUS.items():
                for _ in range(random.randint(0, 3)):
                    qty = random.choice([1, 1, 1, 2, 3])
                    status = "shipped"
                    refund = 0.0
                    if random.random() < 0.04 or (sku in refund_skus and random.random() < 0.06):
                        status, refund = "refunded", round(price * qty, 2)
                    price_now = round(price * random.uniform(0.85, 1.05), 2)
                    orders.append(
                        {
                            "order_id": f"{marketplace}-{day.strftime('%Y%m%d')}-{len(orders):05d}",
                            "marketplace": marketplace,
                            "sku": sku,
                            "order_date": day.isoformat(),
                            "quantity": qty,
                            "item_price": price_now,
                            "shipping_credit": round(random.uniform(0, 4.99), 2) if random.random() < 0.15 else 0.0,
                            "promo_discount": round(price_now * qty * 0.1, 2) if random.random() < 0.1 else 0.0,
                            "referral_fee": round(price_now * qty * 0.15, 2),
                            "fba_fee": round(random.uniform(2.8, 6.5) * qty, 2),
                            "refund_amount": refund,
                            "status": status,
                        }
                    )

    pd.DataFrame(orders).to_csv(out_dir / "orders.csv", index=False)

    costs = []
    for sku, price in SKUS.items():
        costs.append(
            {
                "sku": sku,
                "product_cost": round(price * random.uniform(0.28, 0.42), 2),
                "first_leg_cost": round(price * random.uniform(0.05, 0.12), 2),
                "packaging_cost": round(random.uniform(0.15, 0.6), 2),
            }
        )
    pd.DataFrame(costs).to_csv(out_dir / "costs.csv", index=False)

    ads = []
    for offset in range(DAYS):
        day = END_DATE - timedelta(days=DAYS - 1 - offset)
        for marketplace in MARKETPLACES:
            for sku in SKUS:
                spend = round(random.uniform(1.5, 8), 2) if random.random() < 0.4 else 0.0
                ads.append({"date": day.isoformat(), "marketplace": marketplace, "sku": sku, "ad_spend": spend})
    pd.DataFrame(ads).to_csv(out_dir / "ads.csv", index=False)

    inventory = []
    for marketplace in MARKETPLACES:
        for sku in SKUS:
            safety = random.choice([50, 80, 120])
            available = random.randint(0, 400)
            if sku in {"SKU-D001", "SKU-C002"}:
                available = random.randint(0, 30)  # 制造断货告警
            inventory.append(
                {
                    "sku": sku,
                    "marketplace": marketplace,
                    "available_qty": available,
                    "inbound_qty": random.randint(0, 200),
                    "safety_stock": safety,
                }
            )
    pd.DataFrame(inventory).to_csv(out_dir / "inventory.csv", index=False)

    print(f"已生成 {len(orders)} 条订单、{len(costs)} 条成本、{len(ads)} 条广告、{len(inventory)} 条库存 -> {out_dir}")


if __name__ == "__main__":
    main()
