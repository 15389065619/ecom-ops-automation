"""飞书自定义机器人推送：支持签名校验，未配置 Webhook 时只打印预览。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import requests

MAX_ALERTS = 8


def _sign(secret: str, timestamp: str) -> str:
    payload = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(payload, b"", digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def build_card(title: str, overview: dict, alerts_rows: list[dict]) -> dict:
    has_p1 = any(row["level"] == "P1" for row in alerts_rows)
    summary = (
        f"**销售额**：{overview['revenue']:,.2f}　**净利**：{overview['net_profit']:,.2f}　"
        f"**净利率**：{overview['margin']:.2%}　**退货率**：{overview['return_rate']:.2%}"
    )
    elements = [{"tag": "div", "text": {"tag": "lark_md", "content": summary}}]
    if alerts_rows:
        lines = [f"- **{r['level']} {r['type']}**｜{r['message']}" for r in alerts_rows[:MAX_ALERTS]]
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}})
    else:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "今日无异常，继续保持。"}})

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "red" if has_p1 else "green",
                "title": {"tag": "plain_text", "content": title},
            },
            "elements": elements,
        },
    }


def send_report(
    webhook: str,
    secret: str,
    title: str,
    overview: dict,
    alerts_rows: list[dict],
    dry_run: bool = False,
) -> dict:
    payload = build_card(title, overview, alerts_rows)

    if dry_run or not webhook:
        print("[dry-run] 未配置 FEISHU_WEBHOOK，以下为将要发送的消息：")
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:1200])
        return {"code": 200, "dry_run": True}

    body: dict = dict(payload)
    if secret:
        timestamp = str(int(time.time()))
        body["timestamp"] = timestamp
        body["sign"] = _sign(secret, timestamp)

    resp = requests.post(webhook, json=body, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") not in (0, 200):
        raise RuntimeError(f"飞书返回异常: {data}")
    return data
