"""运行配置：全部从环境变量读取，不落盘任何密钥。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    project_dir: Path
    data_dir: Path
    reports_dir: Path
    db_path: Path
    feishu_webhook: str
    feishu_secret: str
    spapi_refresh_token: str
    spapi_lwa_app_id: str
    spapi_lwa_client_secret: str
    spapi_region: str
    erp_api_base_url: str
    erp_api_token: str

    @classmethod
    def from_env(cls, project_dir: Path | None = None) -> "Settings":
        root = Path(project_dir or Path(__file__).resolve().parents[2])
        return cls(
            project_dir=root,
            data_dir=root / "data" / "mock",
            reports_dir=root / "reports",
            db_path=root / "data" / "ops.db",
            feishu_webhook=os.getenv("FEISHU_WEBHOOK", ""),
            feishu_secret=os.getenv("FEISHU_SECRET", ""),
            spapi_refresh_token=os.getenv("SPAPI_REFRESH_TOKEN", ""),
            spapi_lwa_app_id=os.getenv("SPAPI_LWA_APP_ID", ""),
            spapi_lwa_client_secret=os.getenv("SPAPI_LWA_CLIENT_SECRET", ""),
            spapi_region=os.getenv("SPAPI_REGION", "NA"),
            erp_api_base_url=os.getenv("ERP_API_BASE_URL", ""),
            erp_api_token=os.getenv("ERP_API_TOKEN", ""),
        )


# 利润与告警阈值，集中管理便于按业务调整
MARGIN_ALERT_THRESHOLD = 0.08
RETURN_RATE_ALERT_THRESHOLD = 0.06
STOCK_COVER_ALERT_DAYS = 14
