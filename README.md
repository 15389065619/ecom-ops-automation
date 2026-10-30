# ecom-ops-automation

跨境电商运营效率工程 demo：**取数 → 清洗算利 → Excel 日报 → 飞书告警**，对应 JD 里"独立完成工具开发与落地"的一条完整链路。

## 一条命令跑通（离线可复现）

```powershell
cd ecom-ops-automation
$env:PYTHONPATH="src"
python scripts/gen_mock_data.py                      # 生成 30 天 mock 数据
python -m ops_automation --date 2026-10-29 --days 30 --dry-run
```

输出：

- `reports/ops-report-2026-10-29.xlsx`：总览 / 按SKU / 按站点 / 每日趋势 / 告警 / 订单明细 六个 Sheet
- `reports/by-sku-*.csv`、`reports/alerts-*.csv`
- 控制台 + 飞书卡片预览（`--dry-run` 不真正发送）

真实推送只需配置环境变量（见 `.env.example`）：

```powershell
$env:FEISHU_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
$env:FEISHU_SECRET="xxx"        # 机器人开启签名校验时填
python -m ops_automation --date 2026-10-29
```

## 可视化看板（docs/）

```powershell
python scripts/build_dashboard.py      # 从 SQLite 导出 docs/assets/data.js
```

浏览器直接打开 `docs/index.html` 即可看到 KPI、日度走势、SKU 净利排行、站点占比与告警清单（ECharts 已本地化，无 CDN 依赖）。

发布到 GitHub Pages：仓库 `Settings → Pages → Source: main / docs`，或：

```powershell
gh repo create <仓库名> --public --source . --remote origin --push
```

## 接真实 Amazon 数据

```powershell
pip install "python-amazon-sp-api"
$env:SPAPI_REFRESH_TOKEN="..."
$env:SPAPI_LWA_APP_ID="..."
$env:SPAPI_LWA_CLIENT_SECRET="..."
$env:SPAPI_REGION="NA"
python -m ops_automation --source spapi --days 7
```

`SpApiSource` 只负责把订单拉成统一表结构，成本/广告/库存仍从内部 CSV（可替换成 ERP 导出、Advertising API、FBA Inventory API），管道代码不用改。

## 口径说明

| 指标 | 公式 |
|---|---|
| 销售额 | 单价 × 件数 + 运费收入 − 促销折扣 |
| 平台佣金 | referral_fee + fba_fee |
| 商品成本 | (采购 + 头程 + 包装) × 件数 |
| 广告费 | 按"同日期、同站点、同 SKU"的件数占比分摊 |
| 净利润 | 销售额 − 平台佣金 − 商品成本 − 广告费 − 退款 |
| 净利率 | 净利润 / 销售额 |

告警阈值集中在 `src/ops_automation/config.py`：净利率 < 8%、退货率 > 6%、可售天数 < 14 天、可用库存 < 安全库存。

## 目录

```
src/ops_automation/
  sources.py   数据源适配（mock CSV / SP-API）
  pipeline.py  清洗、成本与广告关联、利润计算、聚合、告警
  db.py        SQLite 幂等 upsert，重复跑不重复计账
  report.py    openpyxl 多 Sheet 报表 + CSV
  notify.py    飞书自定义机器人（支持加签）
  cli.py       命令行入口
tests/         8 个用例覆盖利润口径、告警、报表、幂等
```

## 测试

```powershell
$env:PYTHONPATH="src"; python -m pytest -q
```

## 与 JD 能力点对应

| JD 要求 | 落在哪 |
|---|---|
| Python 独立编写数据处理/自动化脚本 | 全部管道代码，分层清晰、无魔法 |
| pandas / openpyxl 处理 Excel、CSV | `pipeline.py` + `report.py` |
| HTTP API / JSON / JWT 认证 | `sources.py` 走 SP-API LWA OAuth，`notify.py` 走 Webhook + HMAC 签名 |
| 用 AI 工具辅助开发并检查生成代码 | 代码由 Codex 类工具生成后补测试与口径校验，`tests/` 即验收入口 |
| SQL / Git | SQLite upsert 去重、报表留痕表 `report_runs` |
| 对接 ERP / 平台 API / 飞书 | `sources.py` 可插拔数据源 + `notify.py` 飞书卡片 |
| 异常处理、使用说明、非技术同事可用 | `--dry-run` 预览、报表即产物、README 即操作手册 |
