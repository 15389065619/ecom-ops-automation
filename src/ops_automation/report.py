"""报表输出：单个 Excel 多 Sheet + CSV，方便业务直接发群。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

MONEY_COLS = {"revenue", "net_profit", "ad_spend", "amazon_fees", "cogs", "refunds", "gross_revenue", "amazon_fees"}
PCT_COLS = {"margin", "return_rate"}

HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
TITLE_FONT = Font(bold=True, size=14)
THIN = Side(style="thin", color="D9D9D9")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

HEADERS = {
    "sku": "SKU",
    "marketplace": "站点",
    "orders": "订单数",
    "units": "件数",
    "revenue": "销售额",
    "net_profit": "净利",
    "margin": "净利率",
    "ad_spend": "广告费",
    "return_rate": "退货率",
    "order_date": "日期",
    "level": "级别",
    "type": "类型",
    "target": "对象",
    "message": "说明",
    "order_id": "订单号",
    "quantity": "数量",
    "item_price": "单价",
    "gross_revenue": "销售额",
    "amazon_fees": "平台佣金",
    "cogs": "商品成本",
    "ad_allocated": "广告费",
    "refund_amount": "退款",
    "status": "状态",
}


def _display_name(col: str) -> str:
    return HEADERS.get(col, col)


def _write_table(ws, df: pd.DataFrame, start_row: int = 1) -> int:
    if df.empty:
        ws.cell(row=start_row, column=1, value="暂无数据")
        return start_row + 2

    for idx, col in enumerate(df.columns, start=1):
        cell = ws.cell(row=start_row, column=idx, value=_display_name(col))
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for r, row in enumerate(df.itertuples(index=False), start=start_row + 1):
        for c, (col, value) in enumerate(zip(df.columns, row), start=1):
            if isinstance(value, float) and pd.isna(value):
                value = None
            cell = ws.cell(row=r, column=c, value=value)
            cell.border = BORDER
            if col in MONEY_COLS:
                cell.number_format = "#,##0.00"
            elif col in PCT_COLS:
                cell.number_format = "0.00%"
            if col in {"sku", "order_id", "message"}:
                cell.alignment = Alignment(horizontal="left")

    for idx, col in enumerate(df.columns, start=1):
        width = max(len(_display_name(col)) * 2, *(len(str(v)) * 1.4 for v in df[col].head(20)))
        ws.column_dimensions[get_column_letter(idx)].width = min(max(width, 10), 42)

    ws.freeze_panes = ws.cell(row=start_row + 1, column=1)
    return start_row + len(df) + 3


def _write_overview(ws, overview: dict, start: str, end: str) -> None:
    ws["A1"] = f"跨境电商运营日报（{start} ~ {end}）"
    ws["A1"].font = TITLE_FONT

    rows = [
        ("订单数", overview["orders"], "0"),
        ("件数", overview["units"], "0"),
        ("销售额", overview["revenue"], "#,##0.00"),
        ("平台佣金", overview["amazon_fees"], "#,##0.00"),
        ("商品成本", overview["cogs"], "#,##0.00"),
        ("广告费", overview["ad_spend"], "#,##0.00"),
        ("退款金额", overview["refunds"], "#,##0.00"),
        ("净利润", overview["net_profit"], "#,##0.00"),
        ("净利率", overview["margin"], "0.00%"),
        ("退货率", overview["return_rate"], "0.00%"),
        ("在售 SKU 数", overview["sku_count"], "0"),
    ]
    for r, (label, value, fmt) in enumerate(rows, start=3):
        ws.cell(row=r, column=1, value=label).font = Font(bold=True)
        cell = ws.cell(row=r, column=2, value=value)
        cell.number_format = fmt
        cell.alignment = Alignment(horizontal="right")
        cell.border = BORDER
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 18


def build_report(
    out_dir: Path,
    report_date: str,
    start: str,
    end: str,
    overview: dict,
    by_sku: pd.DataFrame,
    by_marketplace: pd.DataFrame,
    daily: pd.DataFrame,
    details: pd.DataFrame,
    alerts: pd.DataFrame,
) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"ops-report-{report_date}.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "总览"
    _write_overview(ws, overview, start, end)

    detail_cols = [
        "order_date", "order_id", "marketplace", "sku", "quantity", "item_price",
        "gross_revenue", "amazon_fees", "cogs", "ad_allocated", "refund_amount",
        "net_profit", "margin", "status",
    ]

    for sheet_name, frame in [
        ("按SKU", by_sku),
        ("按站点", by_marketplace),
        ("每日趋势", daily),
        ("告警", alerts),
        ("订单明细", details[detail_cols] if not details.empty else details),
    ]:
        sheet = wb.create_sheet(sheet_name)
        _write_table(sheet, frame)

    wb.save(path)

    by_sku.to_csv(out_dir / f"by-sku-{report_date}.csv", index=False)
    alerts.to_csv(out_dir / f"alerts-{report_date}.csv", index=False)
    return path
