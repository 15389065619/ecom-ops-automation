"""数据源适配层：mock / ERP / SP-API 返回同一种表格结构。

企业实际选型：不直接接 Amazon SP-API（资质审核慢、PII 合规成本高），
而是通过已完成 SP-API 对接的 ERP（领星/积加等）开放 API 间接获取数据。
ERP 已处理 SigV4 签名、PII 脱敏、限流，调用方只需 Bearer token 认证。
"""

from __future__ import annotations

import json
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


def build_source(name: str, settings) -> MockSource | ErpSource | SpApiSource:
    if name == "mock":
        return MockSource(settings.data_dir)
    if name == "erp":
        return ErpSource(settings)
    if name == "spapi":
        return SpApiSource(settings)
    raise ValueError(f"未知数据源: {name}")


class ErpSource:
    """通过 ERP 开放 API 间接获取亚马逊数据（领星/积加模式）。

    为什么不直接接 SP-API：
    - SP-API 开发者审核需 1-2 周，PII 数据需额外数据安全评估
    - SigV4 签名 + LWA 双重认证，维护成本高
    - ERP 已封装这些，调用方只需 Bearer token + RESTful JSON

    需要配置 ERP_API_BASE_URL 和 ERP_API_TOKEN。
    未配置时降级读取 data/mock/erp_response.json（模拟 API 响应），保证可演示。
    """

    name = "erp"

    def __init__(self, settings):
        self.settings = settings
        self.base_url = settings.erp_api_base_url.rstrip("/")
        self.token = settings.erp_api_token
        self._mock_path = Path(settings.data_dir) / "erp_response.json"

    def _request(self, path: str, params: dict | None = None) -> dict:
        """带 token 的 GET 请求，失败抛明确异常。"""
        try:
            import requests
        except ImportError as exc:
            raise RuntimeError("ERP 取数需要: pip install requests") from exc

        headers = {"Authorization": f"Bearer {self.token}"}
        resp = requests.get(f"{self.base_url}{path}", headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _fetch_orders(self, start: str, end: str) -> list[dict]:
        """分页拉取订单，演示真实 API 调用。"""
        orders: list[dict] = []
        page = 1
        while True:
            payload = self._request(
                "/api/v1/orders",
                params={"start_date": start, "end_date": end, "page": page, "page_size": 100},
            )
            orders.extend(payload.get("data", []))
            if page >= payload.get("total_pages", 1):
                break
            page += 1
        return orders

    def _mock_response(self) -> dict:
        """无 ERP 凭证时读取本地模拟响应，保证流程可演示。"""
        if not self._mock_path.exists():
            raise RuntimeError(
                "未配置 ERP_API_BASE_URL/ERP_API_TOKEN，且缺少模拟响应文件 "
                f"{self._mock_path}。请配置凭证或生成 mock 数据。"
            )
        return json.loads(self._mock_path.read_text(encoding="utf-8"))

    def load(self, start: str, end: str) -> DataBundle:
        if not (self.base_url and self.token):
            # 演示模式：用本地模拟响应替代真实 API 调用
            payload = self._mock_response()
        else:
            payload = {
                "orders": self._fetch_orders(start, end),
                # 真实环境还会调 /api/v1/ads、/api/v1/inventory 等
            }

        # ERP 字段名与 SP-API 不同，统一映射成管道认识的结构
        orders = pd.DataFrame(payload.get("orders", []))
        if not orders.empty:
            orders = orders.rename(
                columns={
                    "order_no": "order_id",
                    "site": "marketplace",
                    "sku": "sku",
                    "order_date": "order_date",
                    "qty": "quantity",
                    "price": "item_price",
                    "shipping": "shipping_credit",
                    "discount": "promo_discount",
                    "commission": "referral_fee",
                    "fba_fee": "fba_fee",
                    "refund": "refund_amount",
                    "status": "status",
                }
            )
            orders["order_date"] = pd.to_datetime(orders["order_date"]).dt.normalize()
        orders = orders.reindex(columns=ORDER_COLUMNS)

        return {
            "orders": orders,
            "costs": pd.read_csv(self.settings.data_dir / "costs.csv"),
            "ads": pd.read_csv(self.settings.data_dir / "ads.csv"),
            "inventory": pd.read_csv(self.settings.data_dir / "inventory.csv"),
        }
