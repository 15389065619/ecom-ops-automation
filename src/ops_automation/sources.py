"""数据源适配层：mock CSV 与 Amazon SP-API 返回同一种表格结构。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ORDER_COLUMNS = [
    "order_id",
    "marketplace",
    "sku",
    "order_date",
    "quantity",
    "item_price",
    "shipping_credit",
    "promo_discount",
    "referral_fee",
    "fba_fee",
    "refund_amount",
    "status",
]
COST_COLUMNS = ["sku", "product_cost", "first_leg_cost", "packaging_cost"]
AD_COLUMNS = ["date", "marketplace", "sku", "ad_spend"]
INVENTORY_COLUMNS = ["sku", "marketplace", "available_qty", "inbound_qty", "safety_stock"]

DataBundle = dict[str, pd.DataFrame]


class MockSource:
    """离线数据源：读取 data/mock 下的 CSV，便于本地复现与测试。"""

    name = "mock"

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)

    def load(self, start: str, end: str) -> DataBundle:
        orders = pd.read_csv(self.data_dir / "orders.csv", dtype={"sku": str, "order_id": str})
        orders["order_date"] = pd.to_datetime(orders["order_date"]).dt.normalize()
        in_range = (orders["order_date"] >= pd.Timestamp(start)) & (orders["order_date"] <= pd.Timestamp(end))
        return {
            "orders": orders.loc[in_range, ORDER_COLUMNS].reset_index(drop=True),
            "costs": pd.read_csv(self.data_dir / "costs.csv"),
            "ads": pd.read_csv(self.data_dir / "ads.csv"),
            "inventory": pd.read_csv(self.data_dir / "inventory.csv"),
        }


class SpApiSource:
    """真实数据源：用 python-amazon-sp-api 拉订单/财务报告，映射成统一表格。

    需要有 SP-API 凭证（LWA refresh token + APP ID/Secret）。未安装依赖或缺凭证时
    直接给出明确错误，不做静默降级。
    """

    name = "spapi"

    def __init__(self, settings):
        self.settings = settings

    def _client(self):
        try:
            from sp_api.api import Orders, Reports
            from sp_api.base import Marketplaces
            from sp_api.base.credential_provider import Credentials
        except ImportError as exc:  # 依赖是可选安装项
            raise RuntimeError('真实取数需要先执行: pip install "python-amazon-sp-api"') from exc

        s = self.settings
        if not (s.spapi_refresh_token and s.spapi_lwa_app_id and s.spapi_lwa_client_secret):
            raise RuntimeError("缺少 SP-API 凭证：SPAPI_REFRESH_TOKEN / SPAPI_LWA_APP_ID / SPAPI_LWA_CLIENT_SECRET")

        creds = Credentials(
            refresh_token=s.spapi_refresh_token,
            lwa_app_id=s.spapi_lwa_app_id,
            lwa_client_secret=s.spapi_lwa_client_secret,
        )
        marketplace = getattr(Marketplaces, s.spapi_region, Marketplaces.US)
        return Orders(credentials=creds, marketplace=marketplace), Reports(credentials=creds, marketplace=marketplace)

    def load(self, start: str, end: str) -> DataBundle:
        """只拉订单主表；成本、广告、库存仍由公司内部数据（CSV/ERP）补齐。

        真实环境里广告数据走 Advertising API、库存走 FBA Inventory API，
        本 demo 保留同一接口，方便替换实现而不动管道。
        """
        orders_api, _ = self._client()
        rows: list[dict] = []
        next_token = None
        while True:
            resp = orders_api.get_orders(
                CreatedAfter=f"{start}T00:00:00Z",
                CreatedBefore=f"{end}T23:59:59Z",
                NextToken=next_token,
            )
            for order in resp.payload.get("Orders", []):
                for item in order.get("OrderItems", []) or [{"OrderItemId": "", "SellerSKU": "", "QuantityOrdered": 0}]:
                    rows.append(
                        {
                            "order_id": order.get("AmazonOrderId", ""),
                            "marketplace": order.get("MarketplaceId", ""),
                            "sku": item.get("SellerSKU") or item.get("ASIN", ""),
                            "order_date": order.get("PurchaseDate", "")[:10],
                            "quantity": item.get("QuantityOrdered", 0),
                            "item_price": float(item.get("ItemPrice", {}).get("Amount", 0) or 0),
                            "shipping_credit": float(item.get("ShippingPrice", {}).get("Amount", 0) or 0),
                            "promo_discount": float(item.get("ItemPromotionDiscount", {}).get("Amount", 0) or 0),
                            "referral_fee": 0.0,
                            "fba_fee": 0.0,
                            "refund_amount": 0.0,
                            "status": order.get("OrderStatus", ""),
                        }
                    )
            next_token = resp.payload.get("NextToken")
            if not next_token:
                break

        orders = pd.DataFrame(rows, columns=ORDER_COLUMNS)
        return {
            "orders": orders,
            "costs": pd.read_csv(self.settings.data_dir / "costs.csv"),
            "ads": pd.read_csv(self.settings.data_dir / "ads.csv"),
            "inventory": pd.read_csv(self.settings.data_dir / "inventory.csv"),
        }


def build_source(name: str, settings) -> MockSource | SpApiSource:
    if name == "mock":
        return MockSource(settings.data_dir)
    if name == "spapi":
        return SpApiSource(settings)
    raise ValueError(f"未知数据源: {name}")
