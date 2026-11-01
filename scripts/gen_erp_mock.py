"""生成模拟 ERP API 响应（data/mock/erp_response.json）。

把现有 orders.csv 转成 ERP 风格的字段名，模拟领星/积加开放 API 的返回结构。
真实 ERP API 返回字段名与 SP-API 不同，这里演示字段映射过程。
"""

import json
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "mock"
orders = pd.read_csv(DATA_DIR / "orders.csv", dtype={"sku": str, "order_id": str})

# ERP 风格字段名（与统一结构不同，需要映射）
erp_orders = orders.rename(
    columns={
        "order_id": "order_no",
        "marketplace": "site",
        "quantity": "qty",
        "item_price": "price",
        "shipping_credit": "shipping",
        "promo_discount": "discount",
        "referral_fee": "commission",
        "refund_amount": "refund",
    }
).to_dict(orient="records")

payload = {
    "code": 0,
    "message": "success",
    "data": erp_orders,
    "total": len(erp_orders),
    "total_pages": 1,
}

out = DATA_DIR / "erp_response.json"
out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"written: {out} ({len(erp_orders)} orders)")
