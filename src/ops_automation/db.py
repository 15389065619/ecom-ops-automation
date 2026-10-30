"""SQLite 落库：幂等 upsert，避免重复拉数造成重复计账。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

DDL = """
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT NOT NULL,
    sku TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    order_date TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    item_price REAL NOT NULL,
    shipping_credit REAL NOT NULL,
    promo_discount REAL NOT NULL,
    referral_fee REAL NOT NULL,
    fba_fee REAL NOT NULL,
    refund_amount REAL NOT NULL,
    status TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id, sku)
);
CREATE TABLE IF NOT EXISTS costs (
    sku TEXT PRIMARY KEY,
    product_cost REAL NOT NULL,
    first_leg_cost REAL NOT NULL,
    packaging_cost REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ad_spend (
    date TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    sku TEXT NOT NULL,
    ad_spend REAL NOT NULL,
    PRIMARY KEY (date, marketplace, sku)
);
CREATE TABLE IF NOT EXISTS inventory (
    sku TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    available_qty INTEGER NOT NULL,
    inbound_qty INTEGER NOT NULL,
    safety_stock INTEGER NOT NULL,
    PRIMARY KEY (sku, marketplace)
);
CREATE TABLE IF NOT EXISTS report_runs (
    run_at TEXT DEFAULT CURRENT_TIMESTAMP,
    report_date TEXT NOT NULL,
    path TEXT NOT NULL,
    net_profit REAL NOT NULL,
    margin REAL NOT NULL
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.executescript(DDL)
        return conn

    def upsert(self, table: str, df: pd.DataFrame, keys: list[str]) -> int:
        if df.empty:
            return 0
        frame = df.copy()
        for col in frame.columns:
            if pd.api.types.is_datetime64_any_dtype(frame[col]):
                frame[col] = frame[col].dt.strftime("%Y-%m-%d")
        cols = list(frame.columns)
        placeholders = ",".join("?" * len(cols))
        updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in keys)
        sql = (
            f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT ({','.join(keys)}) DO UPDATE SET {updates}"
        )
        # 转成纯 Python 类型，避免 numpy 标量无法被 sqlite3 绑定
        rows = frame[cols].astype(object).where(frame[cols].notna(), None).values.tolist()
        with self.connect() as conn:
            conn.executemany(sql, rows)
        return len(rows)

    def read_orders(self, start: str, end: str) -> pd.DataFrame:
        with self.connect() as conn:
            return pd.read_sql_query(
                "SELECT * FROM orders WHERE order_date BETWEEN ? AND ? ORDER BY order_date, order_id",
                conn,
                params=(start, end),
            )

    def read_table(self, table: str) -> pd.DataFrame:
        with self.connect() as conn:
            return pd.read_sql_query(f"SELECT * FROM {table}", conn)

    def record_run(self, report_date: str, path: str, net_profit: float, margin: float) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO report_runs (report_date, path, net_profit, margin) VALUES (?,?,?,?)",
                (report_date, path, net_profit, margin),
            )
