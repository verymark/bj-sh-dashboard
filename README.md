# 京沪统计指标每日对比仪表盘

该项目会每天自动从上海市统计局与北京市统计局网站抓取公开页面数据，抽取关键经济指标，生成对比仪表盘并提交到 GitHub。

## 功能

- 每天自动抓取两地统计网站公开页面
- 自动识别并提取关键指标（GDP、工业、消费、投资、CPI、进出口）
- 生成历史数据 `data/history.csv`
- 生成仪表盘页面 `docs/index.html`
- 通过 GitHub Actions 每日自动更新并提交

## 项目结构

- `config/sources.json`: 数据源与指标关键词配置
- `scripts/collect_data.py`: 采集与清洗脚本
- `scripts/build_dashboard.py`: 仪表盘 HTML 生成脚本
- `.github/workflows/daily_dashboard.yml`: 每日自动任务
- `data/`: 采集结果与历史数据
- `docs/index.html`: GitHub 可直接展示的仪表盘

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/collect_data.py
python scripts/build_dashboard.py
```

## GitHub 展示

1. 将仓库推送到 GitHub。
2. 在仓库 Settings -> Pages 中，将 Source 设置为 `Deploy from a branch`。
3. Branch 选择默认分支（如 `main`），目录选择 `/docs`。
4. 仪表盘会在 Pages URL 下展示。

## 调度时间

GitHub Actions 使用 `cron: 0 1 * * *`，对应北京时间每天 `09:00`。

## 可调参数

修改 `config/sources.json`：

- `seed_urls`: 各地入口页面
- `link_keywords`: 用于定位统计数据页面的关键词
- `indicator_keywords`: 关键指标匹配关键词

> 说明：两地统计局页面结构可能调整，建议定期检查关键词配置以保证采集精度。
