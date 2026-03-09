#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = ROOT / "data" / "history.csv"
OUT_PATH = ROOT / "docs" / "index.html"


def format_value(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}"


def build_html(history) -> str:
    import pandas as pd

    history["capture_date"] = pd.to_datetime(history["capture_date"])
    history = history.sort_values("capture_date")

    latest = history.groupby(["city", "indicator"], as_index=False).tail(1)
    dates = sorted(history["capture_date"].dt.strftime("%Y-%m-%d").unique().tolist())

    indicators = sorted(history["indicator"].unique().tolist())
    cities = sorted(history["city"].unique().tolist())

    cards = []
    for indicator in indicators:
        rows = latest[latest["indicator"] == indicator]
        parts = []
        for city in cities:
            row = rows[rows["city"] == city]
            if row.empty:
                parts.append(f"<li>{city}: 暂无</li>")
                continue
            value = float(row.iloc[0]["value"])
            unit = str(row.iloc[0].get("unit", "") or "")
            parts.append(f"<li>{city}: {format_value(value)} {unit}</li>")
        cards.append(
            f"""
            <div class=\"card\">
              <h3>{indicator}</h3>
              <ul>{''.join(parts)}</ul>
            </div>
            """
        )

    trend_payload = {}
    for indicator in indicators:
        trend_payload[indicator] = {}
        subset = history[history["indicator"] == indicator]
        for city in cities:
            city_rows = subset[subset["city"] == city]
            trend_payload[indicator][city] = [None if pd.isna(v) else float(v) for v in city_rows["value"].tolist()]

    source_table = (
        latest[["capture_date", "city", "indicator", "value", "unit", "source_url"]]
        .sort_values(["indicator", "city"])
        .copy()
    )
    source_table["capture_date"] = source_table["capture_date"].dt.strftime("%Y-%m-%d")

    source_rows = "\n".join(
        f"<tr><td>{r.capture_date}</td><td>{r.city}</td><td>{r.indicator}</td><td>{format_value(float(r.value))}</td><td>{r.unit or ''}</td><td><a href='{r.source_url}' target='_blank'>来源</a></td></tr>"
        for r in source_table.itertuples()
    )

    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>京沪关键指标对比仪表盘</title>
  <script src=\"https://cdn.jsdelivr.net/npm/chart.js\"></script>
  <style>
    :root {{
      --bg: #f4f7fb;
      --surface: #ffffff;
      --ink: #1a2a3a;
      --muted: #65717e;
      --accent-a: #0055a6;
      --accent-b: #d63c2f;
      --ring: #d8e4f4;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Noto Sans SC", "PingFang SC", sans-serif; background: radial-gradient(circle at top right, #eaf2ff, var(--bg)); color: var(--ink); }}
    .wrap {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px 36px; }}
    h1 {{ margin: 0 0 8px; }}
    .meta {{ color: var(--muted); margin-bottom: 20px; }}
    .grid {{ display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }}
    .card {{ background: var(--surface); border: 1px solid var(--ring); border-radius: 12px; padding: 14px; box-shadow: 0 8px 20px rgba(35,55,80,0.05); }}
    .card h3 {{ margin: 0 0 6px; font-size: 16px; }}
    .card ul {{ margin: 0; padding-left: 18px; }}
    .panel {{ margin-top: 18px; padding: 14px; background: var(--surface); border: 1px solid var(--ring); border-radius: 12px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ border-bottom: 1px solid #eef2f7; padding: 8px; text-align: left; }}
    th {{ background: #f7fafd; }}
    canvas {{ width: 100% !important; height: 420px !important; }}
    a {{ color: var(--accent-a); }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <h1>京沪关键指标对比仪表盘</h1>
    <div class=\"meta\">按日自动抓取上海市统计局与北京市统计局网站公开信息。更新时间: {dates[-1] if dates else 'N/A'}</div>

    <div class=\"grid\">{''.join(cards)}</div>

    <div class=\"panel\">
      <h2>趋势对比</h2>
      <canvas id=\"trend\"></canvas>
    </div>

    <div class=\"panel\">
      <h2>最新采集明细</h2>
      <table>
        <thead>
          <tr><th>日期</th><th>城市</th><th>指标</th><th>数值</th><th>单位</th><th>来源</th></tr>
        </thead>
        <tbody>
          {source_rows}
        </tbody>
      </table>
    </div>
  </div>

  <script>
    const labels = {json.dumps(dates, ensure_ascii=False)};
    const trendPayload = {json.dumps(trend_payload, ensure_ascii=False)};
    const indicatorOrder = {json.dumps(indicators, ensure_ascii=False)};
    const cityColors = {{"上海": "#0055a6", "北京": "#d63c2f"}};

    function datasetsFor(indicator) {{
      const cityMap = trendPayload[indicator] || {{}};
      return Object.keys(cityMap).map(city => ({{
        label: `${{indicator}} - ${{city}}`,
        data: cityMap[city],
        borderColor: cityColors[city] || '#333',
        backgroundColor: cityColors[city] || '#333',
        tension: 0.2,
        borderWidth: 2
      }}));
    }}

    const allDatasets = indicatorOrder.flatMap(datasetsFor);
    const ctx = document.getElementById('trend').getContext('2d');
    new Chart(ctx, {{
      type: 'line',
      data: {{ labels, datasets: allDatasets }},
      options: {{
        responsive: true,
        interaction: {{ mode: 'nearest', axis: 'x', intersect: false }},
        plugins: {{ legend: {{ position: 'bottom' }} }},
        scales: {{ y: {{ beginAtZero: false }} }}
      }}
    }});
  </script>
</body>
</html>
"""


def main() -> None:
    if not HISTORY_PATH.exists():
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(
            "<!doctype html><html lang='zh-CN'><meta charset='utf-8' /><title>京沪关键指标对比仪表盘</title><body><h1>京沪关键指标对比仪表盘</h1><p>暂无可展示数据，请等待首次成功采集后自动更新。</p></body></html>",
            encoding="utf-8",
        )
        return

    import pandas as pd

    history = pd.read_csv(HISTORY_PATH)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(build_html(history), encoding="utf-8")


if __name__ == "__main__":
    main()
