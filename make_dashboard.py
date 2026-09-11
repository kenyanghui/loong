#!/usr/bin/env python3
"""Build annotated Plotly charts and a self-contained summary dashboard."""

import csv
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "outputs"
CHART_DIR = ROOT / "charts"

INTERVAL_LABEL = {
    "daily": "日线",
    "30m": "30分钟",
    "60m": "60分钟",
    "90m": "90分钟",
    "120m": "120分钟",
}

PLOTLY_HEAD = """
<html>
<head><meta charset="utf-8" /></head>
<body>
<div style="height:860px; width:100%;">
<script src="https://cdn.plot.ly/plotly-3.7.0.min.js"></script>
<div id="chart" class="plotly-graph-div" style="height:100%; width:100%;"></div>
<script>
const data = %DATA%;
const layout = %LAYOUT%;
Plotly.newPlot("chart", data, layout, {responsive: true});
</script>
</div>
</body>
</html>
"""


def number_or_none(value):
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def fmt_ts(value):
    try:
        return value.replace(" ", "T")
    except AttributeError:
        return value


def marker_trace(rows, predicate, label, color, symbol, size=11, text=None):
    points = [row for row in rows if predicate(row)]
    return {
        "type": "scatter",
        "mode": "markers+text",
        "name": label,
        "x": [fmt_ts(row["datetime"]) for row in points],
        "y": [number_or_none(row["close"]) for row in points],
        "text": [text or label] * len(points),
        "textposition": "top center",
        "textfont": {"color": color, "size": 11},
        "marker": {
            "color": color,
            "line": {"color": "white", "width": 1},
            "size": size,
            "symbol": symbol,
        },
        "hovertemplate": f"<b>{label}</b> %{{x|%Y-%m-%d %H:%M}}<extra></extra>",
        "xaxis": "x",
        "yaxis": "y",
    }


def build_chart(symbol, variety, interval_label, rows):
    x = [fmt_ts(row["datetime"]) for row in rows]
    opens = [number_or_none(row["open"]) for row in rows]
    highs = [number_or_none(row["high"]) for row in rows]
    lows = [number_or_none(row["low"]) for row in rows]
    closes = [number_or_none(row["close"]) for row in rows]
    volumes = [int(number_or_none(row["volume"]) or 0) for row in rows]
    vol_colors = [
        "#e74c3c" if (close or 0) >= (open_ or 0) else "#2ecc71"
        for open_, close in zip(opens, closes)
    ]

    customdata = []
    for row in rows:
        cross = row.get("cross") or "-"
        ice = "是" if row.get("ice_point") else "否"
        source = row.get("source_golden_cross") or "-"
        resonance = row.get("resonance") or "-"
        customdata.append(
            [
                f"开 {row['open']}",
                f"高 {row['high']}",
                f"低 {row['low']}",
                f"收 {row['close']}",
                f"MID {row.get('mid') or '-'}",
                f"UPPER {row.get('upper') or '-'}",
                f"LOWER {row.get('lower') or '-'}",
                f"ZK {row.get('zk') or '-'}",
                f"ZD {row.get('zd') or '-'}",
                f"ZD2 {row.get('zd2') or '-'}",
                f"BK {row.get('bk') or '-'}",
                f"DIFF {row.get('diff') or '-'}",
                f"DEA {row.get('dea') or '-'}",
                f"交叉 {cross}",
                f"冰毒点 {ice}",
                f"前置金叉 {source}",
                f"共振 {resonance}",
            ]
        )

    line = lambda key, color, dash=None: {  # noqa: E731
        "type": "scatter",
        "mode": "lines",
        "name": key.upper(),
        "x": x,
        "y": [number_or_none(row.get(key.lower())) for row in rows],
        "line": {"color": color, "width": 1, **({"dash": dash} if dash else {})},
        "hovertemplate": f"<b>{key.upper()}</b> %{{y:,.2f}}<extra></extra>",
        "xaxis": "x",
        "yaxis": "y",
    }

    traces = [
        {
            "type": "candlestick",
            "name": "K线",
            "x": x,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "customdata": customdata,
            "hovertemplate": "%{customdata}<extra></extra>",
            "increasing": {"line": {"color": "#e74c3c"}},
            "decreasing": {"line": {"color": "#2ecc71"}},
            "xaxis": "x",
            "yaxis": "y",
        },
        {
            "type": "bar",
            "name": "成交量",
            "x": x,
            "y": volumes,
            "marker": {"color": vol_colors},
            "hovertemplate": "%{y:,.0f}<extra></extra>",
            "xaxis": "x2",
            "yaxis": "y2",
        },
        line("mid", "#f39c12"),
        line("upper", "#7f8c8d", "dot"),
        line("lower", "#7f8c8d", "dot"),
        line("zk", "#2980b9"),
        line("zd", "#e74c3c"),
        line("zd2", "#8e44ad"),
    ]
    traces.append(marker_trace(rows, lambda r: r.get("cross") == "golden", "金叉", "#f39c12", "triangle-up"))
    traces.append(marker_trace(rows, lambda r: r.get("cross") == "death", "死叉", "#8e44ad", "triangle-down"))
    traces.append(marker_trace(rows, lambda r: r.get("ice_point"), "冰毒点", "#e67e22", "diamond", 13))
    traces.append(marker_trace(rows, lambda r: r.get("sig_long"), "做多", "#2980b9", "triangle-up", 14))
    traces.append(marker_trace(rows, lambda r: r.get("sig_short"), "做空", "#16a085", "triangle-down", 14))
    traces.append(marker_trace(rows, lambda r: r.get("resonance") == "long", "共振做多", "#2980b9", "diamond-open", 20))
    traces.append(marker_trace(rows, lambda r: r.get("resonance") == "short", "共振做空", "#16a085", "diamond-open", 20))

    layout = {
        "title": {
            "text": f"{variety} {symbol} {interval_label} · 玄龙期货冰毒 · 2026",
            "x": 0.01,
        },
        "height": 860,
        "hovermode": "closest",
        "xaxis": {
            "anchor": "y",
            "domain": [0, 1],
            "rangeslider": {"visible": False},
            "showticklabels": False,
        },
        "yaxis": {"anchor": "x", "domain": [0.25, 1], "title": {"text": "价格"}},
        "xaxis2": {"anchor": "y2", "domain": [0, 1]},
        "yaxis2": {"anchor": "x2", "domain": [0, 0.21], "title": {"text": "成交量"}},
        "legend": {"orientation": "h", "y": 1.02, "x": 0},
        "margin": {"l": 60, "r": 20, "t": 80, "b": 40},
    }
    return json.dumps(traces, ensure_ascii=False), json.dumps(layout, ensure_ascii=False)


def read_rows(path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def chart_targets(summary):
    targets = set()
    for row in summary["summaries"]:
        if row["interval"] == "daily":
            targets.add((row["symbol"], row["interval"]))
        if row["resonance_long"] or row["resonance_short"]:
            targets.add((row["symbol"], row["interval"]))
    return targets


def make_charts(summary):
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    targets = chart_targets(summary)
    created = []
    for symbol, interval in sorted(targets):
        csv_path = OUT_DIR / f"{symbol.lower()}_{interval}.csv"
        if not csv_path.exists():
            continue
        rows = read_rows(csv_path)
        meta = next(
            (r for r in summary["summaries"] if r["symbol"] == symbol and r["interval"] == interval),
            {},
        )
        variety = meta.get("variety", symbol)
        interval_label = INTERVAL_LABEL.get(interval, interval)
        data_json, layout_json = build_chart(symbol, variety, interval_label, rows)
        html = (
            PLOTLY_HEAD.replace("%DATA%", data_json)
            .replace("%LAYOUT%", layout_json)
        )
        out_path = CHART_DIR / f"{symbol.lower()}_{interval}_chart.html"
        out_path.write_text(html, encoding="utf-8")
        created.append(out_path.name)
    return created


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>全期货品种·五周期 玄龙冰毒点完整汇总 2026-01-05 ~ 2026-07-31</title>
<style>
:root { --bg:#f5f6f8; --card:#fff; --ink:#1f2430; --muted:#6b7280; --line:#e3e6eb; --accent:#2563eb; --ok:#16a34a; --warn:#d97706; --bad:#dc2626; }
* { box-sizing:border-box; }
body { margin:0; font:14px/1.5 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif; background:var(--bg); color:var(--ink); }
header { background:#fff; border-bottom:1px solid var(--line); padding:22px 28px 16px; }
h1 { margin:0 0 6px; font-size:22px; }
.sub { color:var(--muted); font-size:13px; }
.wrap { max-width:1500px; margin:0 auto; padding:20px 24px 60px; }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; margin:18px 0; }
.card { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:14px 16px; }
.card b { display:block; font-size:26px; margin-top:2px; }
.card span { color:var(--muted); font-size:12px; }
.notice { background:#fffbeb; border:1px solid #fcd34d; border-radius:8px; padding:10px 14px; margin:14px 0; font-size:13px; color:#92400e; }
.filters { position:sticky; top:0; z-index:5; background:rgba(255,255,255,.96); border-bottom:1px solid var(--line); padding:10px 24px; display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
.filters select,.filters input { height:32px; border:1px solid var(--line); border-radius:6px; padding:0 10px; font-size:13px; background:#fff; }
.filters input { width:220px; }
table { width:100%; border-collapse:collapse; background:#fff; margin:16px 0 8px; font-size:13px; }
th { background:#f0f2f5; text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); position:sticky; top:54px; white-space:nowrap; }
td { padding:7px 10px; border-bottom:1px solid var(--line); white-space:nowrap; }
tr:hover td { background:#f8fafc; }
.num { text-align:right; font-variant-numeric:tabular-nums; }
.full { color:var(--ok); font-weight:600; }
.partial { color:var(--warn); font-weight:600; }
.no { color:var(--bad); }
a.chart { color:var(--accent); text-decoration:none; }
a.chart:hover { text-decoration:underline; }
.pill { display:inline-block; padding:1px 8px; border-radius:10px; font-size:12px; }
.pill.long { background:#dbeafe; color:#1d4ed8; }
.pill.short { background:#d1fae5; color:#047857; }
.section { background:#fff; border:1px solid var(--line); border-radius:8px; padding:14px 18px; margin-top:18px; }
.section h2 { margin:0 0 4px; font-size:16px; }
.foot { color:var(--muted); font-size:12px; margin-top:22px; }
</style>
</head>
<body>
<header>
<h1>全期货品种 · 五周期玄龙冰毒点完整汇总</h1>
<div class="sub">区间 2026-01-05 ~ 2026-07-31 ｜ MID=MA(CLOSE,20) ｜ 冰毒窗口 3 根 ｜ 共振窗口 1 根 ｜ 数据：新浪期货（通达信问小达MCP对期货返回为空，按技能回退）</div>
<div style="margin-top:9px;font-size:13px"><a href="./wanfeng-agent-gap.html" style="color:#2563eb;text-decoration:none;font-weight:600">→ 万丰大模型｜金融Agent操作系统 — 代码与目标差距分析</a></div>
</header>
<div class="wrap">
<div class="cards" id="cards"></div>
<div class="notice" id="coverageNote"></div>
<div class="filters">
  <select id="intervalFilter"><option value="">全部周期</option></select>
  <select id="exchangeFilter"><option value="">全部交易所</option></select>
  <select id="signalFilter"><option value="">全部信号</option><option value="ice">有冰毒点</option><option value="res">有共振</option><option value="full">完整覆盖</option><option value="partial">部分覆盖</option></select>
  <input id="search" placeholder="搜索品种/代码" />
</div>
<div class="section">
<h2>品种 × 周期汇总（79 品种 × 5 周期 = 395 项）</h2>
<div style="max-height:560px;overflow:auto"><table id="summaryTable"><thead><tr>
<th>品种</th><th>代码</th><th>交易所</th><th>周期</th><th>覆盖</th><th>实际起点</th><th>实际终点</th><th>K线数</th><th class="num">金叉</th><th class="num">死叉</th><th class="num">冰毒点</th><th class="num">做多</th><th class="num">做空</th><th class="num">共振多</th><th class="num">共振空</th><th>图表</th>
</tr></thead><tbody></tbody></table></div>
</div>
<div class="section">
<h2>冰毒点明细（%ICE_COUNT% 条）</h2>
<div style="max-height:520px;overflow:auto"><table id="iceTable"><thead><tr>
<th>品种</th><th>代码</th><th>交易所</th><th>周期</th><th>死叉时间</th><th>前置金叉</th><th class="num">间隔K线</th><th class="num">收盘</th><th class="num">MID</th>
</tr></thead><tbody></tbody></table></div>
</div>
<div class="section">
<h2>玄龙共振明细（%RES_COUNT% 条）</h2>
<div style="max-height:520px;overflow:auto"><table id="resTable"><thead><tr>
<th>品种</th><th>代码</th><th>交易所</th><th>周期</th><th>方向</th><th>时间</th><th class="num">收盘</th><th class="num">ZK</th><th class="num">ZD</th><th class="num">BK</th>
</tr></thead><tbody></tbody></table></div>
</div>
<div class="foot" id="foot"></div>
</div>
<script id="data" type="application/json">%DATA%</script>
<script>
const data = JSON.parse(document.getElementById("data").textContent);
const summaries = data.summaries;
const iceRows = data.ice_points;
const resRows = data.resonance_points;
const charts = data.charts;
const byInterval = data.by_interval;

function esc(v){ return String(v==null?"":v).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }
function badge(v){ return v ? '<span class="full">完整</span>' : '<span class="partial">部分</span>'; }

document.getElementById("cards").innerHTML = [
  ["品种", data.symbol_count], ["分析项", data.ok_analyses], ["总冰毒点", data.total_ice_points],
  ["总共振", data.total_resonance], ["日线冰毒点", byInterval.daily.ice_points],
  ["30m冰毒点", byInterval["30m"].ice_points], ["60m冰毒点", byInterval["60m"].ice_points],
  ["90m冰毒点", byInterval["90m"].ice_points], ["120m冰毒点", byInterval["120m"].ice_points]
].map(([k,v]) => '<div class="card"><span>'+k+'</span><b>'+v+'</b></div>').join("");

const note = [];
for (const [iv, info] of Object.entries(byInterval)) {
  const label = {daily:"日线","30m":"30分钟","60m":"60分钟","90m":"90分钟","120m":"120分钟"}[iv];
  note.push(label+"："+info.full_coverage+" 项完整覆盖 / "+info.partial_coverage+" 项部分覆盖");
}
document.getElementById("coverageNote").textContent = "覆盖说明：新浪分钟K线为约1023根滚动窗口，30分钟大多只能覆盖最近约2-3个月，故 2026-01-05 起点下大部分为部分覆盖；60/90/120分钟及日线基本完整。线材 WR0 2026-04-22 后无成交。" + note.join("；");

const intervalSel = document.getElementById("intervalFilter");
["daily","30m","60m","90m","120m"].forEach(iv => {
  const o = document.createElement("option"); o.value = iv; o.textContent = {daily:"日线","30m":"30分钟","60m":"60分钟","90m":"90分钟","120m":"120分钟"}[iv]; intervalSel.appendChild(o);
});
const exchangeSel = document.getElementById("exchangeFilter");
[...new Set(summaries.map(r=>r.exchange))].sort().forEach(ex => { const o=document.createElement("option"); o.value=ex; o.textContent=ex; exchangeSel.appendChild(o); });

function chartLink(symbol, interval) {
  const name = symbol.toLowerCase()+"_"+interval+"_chart.html";
  return charts.includes(name) ? '<a class="chart" href="charts/'+name+'">打开</a>' : "-";
}
function renderSummaries(){
  const iv = intervalSel.value, ex = exchangeSel.value, sig = signalFilter.value, q = search.value.trim().toLowerCase();
  const rows = summaries.filter(r =>
    (!iv || r.interval===iv) && (!ex || r.exchange===ex) &&
    (!q || (r.variety+" "+r.symbol).toLowerCase().includes(q)) &&
    (sig==="" || (sig==="ice"&&r.ice_points>0) || (sig==="res"&&(r.resonance_long+r.resonance_short)>0) ||
     (sig==="full"&&r.coverage_full) || (sig==="partial"&&!r.coverage_full))
  );
  document.querySelector("#summaryTable tbody").innerHTML = rows.map(r =>
    "<tr><td>"+esc(r.variety)+"</td><td>"+esc(r.symbol)+"</td><td>"+esc(r.exchange)+"</td><td>"+esc(r.interval_label)+"</td><td>"+badge(r.coverage_full)+"</td><td>"+esc(r.actual_start)+"</td><td>"+esc(r.actual_end)+"</td><td class=num>"+r.bar_count+"</td><td class=num>"+r.golden_crosses+"</td><td class=num>"+r.death_crosses+"</td><td class=num><b>"+r.ice_points+"</b></td><td class=num>"+r.sig_long+"</td><td class=num>"+r.sig_short+"</td><td class=num>"+r.resonance_long+"</td><td class=num>"+r.resonance_short+"</td><td>"+chartLink(r.symbol,r.interval)+"</td></tr>"
  ).join("");
}
function renderIce(){
  const iv = intervalSel.value, q = search.value.trim().toLowerCase();
  const rows = iceRows.filter(r => (!iv || r.interval===iv) && (!q || (r.variety+" "+r.symbol).toLowerCase().includes(q)));
  document.querySelector("#iceTable tbody").innerHTML = rows.map(r =>
    "<tr><td>"+esc(r.variety)+"</td><td>"+esc(r.symbol)+"</td><td>"+esc(r.exchange)+"</td><td>"+esc(r.interval)+"</td><td>"+esc(r.death_cross)+"</td><td>"+esc(r.source_golden_cross)+"</td><td class=num>"+r.bar_gap+"</td><td class=num>"+r.close+"</td><td class=num>"+r.mid+"</td></tr>"
  ).join("");
}
function renderRes(){
  const iv = intervalSel.value, q = search.value.trim().toLowerCase();
  const rows = resRows.filter(r => (!iv || r.interval===iv) && (!q || (r.variety+" "+r.symbol).toLowerCase().includes(q)));
  document.querySelector("#resTable tbody").innerHTML = rows.map(r =>
    "<tr><td>"+esc(r.variety)+"</td><td>"+esc(r.symbol)+"</td><td>"+esc(r.exchange)+"</td><td>"+esc(r.interval)+"</td><td><span class='pill "+(r.direction==="long"?"long":"short")+"'>"+(r.direction==="long"?"做多":"做空")+"</span></td><td>"+esc(r.datetime)+"</td><td class=num>"+r.close+"</td><td class=num>"+(r.zk==null?"-":r.zk)+"</td><td class=num>"+(r.zd==null?"-":r.zd)+"</td><td class=num>"+r.bk+"</td></tr>"
  ).join("");
}
[intervalSel, exchangeSel, signalFilter, document.getElementById("search")].forEach(el => el.addEventListener("change", ()=>{renderSummaries();renderIce();renderRes();}));
document.getElementById("search").addEventListener("input", ()=>{renderSummaries();renderIce();renderRes();});
renderSummaries(); renderIce(); renderRes();
document.getElementById("foot").innerHTML = "XMA 为居中均值，序列右端约 12 根为暂定值并会随新K线重绘；本汇总覆盖的 2026 历史区间已闭合，近期信号以标注为准。图表为日线全部 + 出现共振的周期组合。";
</script>
</body>
</html>
"""


def make_dashboard(summary, chart_files):
    summary["charts"] = sorted(chart_files)
    payload = json.dumps(summary, ensure_ascii=False)
    html = (
        DASHBOARD_HTML.replace("%ICE_COUNT%", str(len(summary["ice_points"])))
        .replace("%RES_COUNT%", str(len(summary["resonance_points"])))
        .replace("%DATA%", payload)
    )
    (ROOT / "index.html").write_text(html, encoding="utf-8")


def main():
    with (ROOT / "汇总_五周期.json").open("r", encoding="utf-8") as handle:
        summary = json.load(handle)
    chart_files = make_charts(summary)
    make_dashboard(summary, chart_files)
    print(f"charts={len(chart_files)} dashboard=index.html")


if __name__ == "__main__":
    main()
