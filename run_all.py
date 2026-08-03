#!/usr/bin/env python3
"""Batch Xuanlong ice-poison analysis: all domestic futures varieties x 5 periods.

Uses the indicator pipeline from scripts/analyze_xuanlong_ice.py and the Sina
domestic futures adapter. The TongDaXin question-answering MCP returns no
usable futures OHLC bars, so this is the documented fallback provider.
"""

import csv
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = (ROOT.parent / "玄龙期货冰毒" / "scripts").resolve()
sys.path.insert(0, str(SCRIPTS))

import analyze_xuanlong_ice as ax  # noqa: E402


REQUESTED_START_DAILY = "2026-01-05"
REQUESTED_END_DAILY = "2026-07-31"
REQUESTED_START_MIN = "2026-01-05 09:00"
REQUESTED_END_MIN = "2026-07-31 23:59:59"
INTERVALS = ["daily", "30", "60", "90", "120"]
INTERVAL_LABELS = {
    "daily": "日线",
    "30": "30分钟",
    "60": "60分钟",
    "90": "90分钟",
    "120": "120分钟",
}

# Sina main-continuous codes for every currently listed domestic futures variety.
SYMBOLS = [
    # 上海期货交易所
    ("CU0", "沪铜", "上期所"), ("AL0", "沪铝", "上期所"), ("ZN0", "沪锌", "上期所"),
    ("PB0", "沪铅", "上期所"), ("NI0", "沪镍", "上期所"), ("SN0", "沪锡", "上期所"),
    ("AU0", "黄金", "上期所"), ("AG0", "白银", "上期所"), ("RB0", "螺纹钢", "上期所"),
    ("HC0", "热轧卷板", "上期所"), ("FU0", "燃油", "上期所"), ("BU0", "沥青", "上期所"),
    ("RU0", "橡胶", "上期所"), ("SP0", "纸浆", "上期所"), ("SS0", "不锈钢", "上期所"),
    ("AO0", "氧化铝", "上期所"), ("BR0", "丁二烯橡胶", "上期所"),
    ("AD0", "铸造铝合金", "上期所"), ("WR0", "线材", "上期所"),
    # 大连商品交易所
    ("A0", "豆一", "大商所"), ("B0", "豆二", "大商所"), ("M0", "豆粕", "大商所"),
    ("Y0", "豆油", "大商所"), ("P0", "棕榈", "大商所"), ("C0", "玉米", "大商所"),
    ("CS0", "玉米淀粉", "大商所"), ("JD0", "鸡蛋", "大商所"), ("LH0", "生猪", "大商所"),
    ("L0", "塑料", "大商所"), ("V0", "PVC", "大商所"), ("PP0", "聚丙烯", "大商所"),
    ("EG0", "乙二醇", "大商所"), ("EB0", "苯乙烯", "大商所"),
    ("PG0", "液化石油气", "大商所"), ("RR0", "粳米", "大商所"),
    ("FB0", "纤维板", "大商所"), ("BB0", "胶合板", "大商所"), ("LG0", "原木", "大商所"),
    ("J0", "焦炭", "大商所"), ("JM0", "焦煤", "大商所"), ("I0", "铁矿石", "大商所"),
    # 郑州商品交易所
    ("SR0", "白糖", "郑商所"), ("CF0", "棉花", "郑商所"), ("TA0", "PTA", "郑商所"),
    ("OI0", "菜油", "郑商所"), ("MA0", "甲醇", "郑商所"), ("FG0", "玻璃", "郑商所"),
    ("RM0", "菜粕", "郑商所"), ("AP0", "苹果", "郑商所"), ("CJ0", "红枣", "郑商所"),
    ("UR0", "尿素", "郑商所"), ("SA0", "纯碱", "郑商所"), ("PF0", "短纤", "郑商所"),
    ("PK0", "花生", "郑商所"), ("SH0", "烧碱", "郑商所"), ("PX0", "对二甲苯", "郑商所"),
    ("PR0", "瓶片", "郑商所"), ("SF0", "硅铁", "郑商所"), ("SM0", "锰硅", "郑商所"),
    ("CY0", "棉纱", "郑商所"), ("RS0", "菜籽", "郑商所"), ("PL0", "丙烯", "郑商所"),
    # 中国金融期货交易所
    ("IF0", "沪深300", "中金所"), ("IH0", "上证50", "中金所"),
    ("IC0", "中证500", "中金所"), ("IM0", "中证1000", "中金所"),
    ("T0", "10年期国债", "中金所"), ("TF0", "5年期国债", "中金所"),
    ("TS0", "2年期国债", "中金所"), ("TL0", "30年期国债", "中金所"),
    # 上海国际能源交易中心
    ("SC0", "原油", "能源中心"), ("LU0", "低硫燃料油", "能源中心"),
    ("NR0", "20号胶", "能源中心"), ("BC0", "国际铜", "能源中心"),
    ("EC0", "集运欧线", "能源中心"),
    # 广州期货交易所
    ("SI0", "工业硅", "广期所"), ("LC0", "碳酸锂", "广期所"),
    ("PS0", "多晶硅", "广期所"), ("PT0", "铂", "广期所"),
]

CACHE_DIR = ROOT / ".cache"
OUT_DIR = ROOT / "outputs"
_CACHE_LOCK = threading.Lock()


def fetch_rows(symbol, interval):
    """Fetch Sina bars with a small on-disk cache and retry logic."""
    cache_path = CACHE_DIR / f"{symbol.lower()}_{interval}.json"
    if cache_path.exists():
        with cache_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    last_error = None
    for attempt in range(4):
        try:
            rows = ax.fetch_sina(symbol, interval)
            if not rows:
                raise RuntimeError("provider returned no bars")
            with _CACHE_LOCK:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                with cache_path.open("w", encoding="utf-8") as handle:
                    json.dump(rows, handle, ensure_ascii=False)
            return rows
        except Exception as error:  # noqa: BLE001
            last_error = error
            time.sleep(1.0 + 1.5 * attempt)
    raise RuntimeError(f"fetch {symbol}/{interval} failed: {last_error}")


def sanitize_rows(rows):
    """Drop provider-invalid historical bars before validation.

    Sina's long daily history occasionally contains a bar with high < open/close
    or duplicate timestamps (all observed outside 2026). Removing those bars keeps
    the requested window and indicator pipeline intact while making the number of
    dropped rows auditable.
    """
    seen = {}
    dropped_duplicates = 0
    for row in rows:
        stamp = row["datetime"]
        if stamp in seen:
            dropped_duplicates += 1
            seen[stamp] = row
        else:
            seen[stamp] = row
    deduped = list(seen.values())

    valid = []
    dropped_invalid = 0
    for row in deduped:
        try:
            open_ = float(row["open"])
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])
        except (TypeError, ValueError):
            dropped_invalid += 1
            continue
        if (
            min(open_, close) <= 0
            or low > min(open_, close)
            or high < max(open_, close)
        ):
            dropped_invalid += 1
            continue
        valid.append(row)
    return valid, dropped_duplicates, dropped_invalid


def analyze_symbol_interval(symbol, variety, exchange, interval):
    """Run the full Xuanlong pipeline for one symbol/interval and persist files."""
    safe_interval = "daily" if interval == "daily" else f"{interval}m"
    csv_path = OUT_DIR / f"{symbol.lower()}_{safe_interval}.csv"
    json_path = OUT_DIR / f"{symbol.lower()}_{safe_interval}.json"
    requested_start = (
        REQUESTED_START_DAILY if interval == "daily" else REQUESTED_START_MIN
    )
    requested_end = REQUESTED_END_DAILY if interval == "daily" else REQUESTED_END_MIN

    try:
        rows = fetch_rows(symbol, interval)
        rows, dropped_duplicates, dropped_invalid = sanitize_rows(rows)
        rows = ax.calculate(ax.validate_rows(rows), 20, 2.0, 3)
        rows = ax.calculate_xuanlong(rows, 25, 1)
    except Exception as error:  # noqa: BLE001
        summary = {
            "symbol": symbol,
            "variety": variety,
            "exchange": exchange,
            "interval": safe_interval,
            "status": "error",
            "error": str(error),
            "sanitized_dropped_duplicates": 0,
            "sanitized_dropped_invalid": 0,
            "requested_start": requested_start,
            "requested_end": requested_end,
        }
        json_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return summary

    start = ax.parse_time(requested_start)
    end = ax.parse_time(requested_end, end=True)
    provider_start = datetime.fromisoformat(rows[0]["datetime"])
    provider_end = datetime.fromisoformat(rows[-1]["datetime"])
    selected = [
        row
        for row in rows
        if start <= datetime.fromisoformat(row["datetime"]) <= end
    ]
    if not selected:
        summary = {
            "symbol": symbol,
            "variety": variety,
            "exchange": exchange,
            "interval": safe_interval,
            "status": "no_overlap",
            "requested_start": requested_start,
            "requested_end": requested_end,
            "provider_start": rows[0]["datetime"],
            "provider_end": rows[-1]["datetime"],
        }
        json_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return summary

    coverage_start = provider_start <= start
    coverage_end = provider_end.date() >= end.date()
    coverage_full = bool(coverage_start and coverage_end)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ax.write_csv(selected, csv_path)

    summary = {
        "symbol": symbol,
        "variety": variety,
        "exchange": exchange,
        "interval": safe_interval,
        "interval_label": INTERVAL_LABELS[interval],
        "status": "ok",
        "source": "sina",
        "requested_start": requested_start,
        "requested_end": requested_end,
        "provider_start": rows[0]["datetime"],
        "provider_end": rows[-1]["datetime"],
        "actual_start": selected[0]["datetime"],
        "actual_end": selected[-1]["datetime"],
        "coverage_start": coverage_start,
        "coverage_end": coverage_end,
        "coverage_full": coverage_full,
        "sanitized_dropped_duplicates": dropped_duplicates,
        "sanitized_dropped_invalid": dropped_invalid,
        "bar_count": len(selected),
        "ma_period": 20,
        "std_multiplier": 2.0,
        "ice_window_bars": 3,
        "channel_period": 25,
        "macd_rule": "DIFF=EMA(CLOSE,12)-EMA(CLOSE,26); DEA=EMA(DIFF,9)",
        "resonance_window_bars": 1,
        "golden_crosses": [
            row["datetime"] for row in selected if row["cross"] == "golden"
        ],
        "death_crosses": [
            row["datetime"] for row in selected if row["cross"] == "death"
        ],
        "ice_points": [
            {
                "death_cross": row["datetime"],
                "source_golden_cross": row["source_golden_cross"],
                "bar_gap": row["bar_gap"],
                "close": row["close"],
                "mid": row["mid"],
            }
            for row in selected
            if row["ice_point"]
        ],
        "xuanlong_long_signals": [
            row["datetime"] for row in selected if row["sig_long"]
        ],
        "xuanlong_short_signals": [
            row["datetime"] for row in selected if row["sig_short"]
        ],
        "resonance_long_points": [
            {
                "datetime": row["datetime"],
                "close": row["close"],
                "zd": row["zd"],
                "bk": row["bk"],
            }
            for row in selected
            if row["resonance_long"]
        ],
        "resonance_short_points": [
            {
                "datetime": row["datetime"],
                "close": row["close"],
                "zk": row["zk"],
                "bk": row["bk"],
            }
            for row in selected
            if row["resonance_short"]
        ],
    }
    json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def run_batch():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    started = time.time()
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = []
        for symbol, variety, exchange in SYMBOLS:
            for interval in INTERVALS:
                futures.append(
                    pool.submit(
                        analyze_symbol_interval, symbol, variety, exchange, interval
                    )
                )
        for index, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            results.append(result)
            status = result.get("status", "?")
            print(
                f"[{index}/{len(futures)}] {result.get('symbol')} "
                f"{result.get('interval')} {status}",
                flush=True,
            )
    with (ROOT / "run_log.txt").open("w", encoding="utf-8") as handle:
        handle.write(
            f"batch finished in {time.time() - started:.1f}s\n"
            f"ok={sum(1 for r in results if r.get('status') == 'ok')} "
            f"error={sum(1 for r in results if r.get('status') == 'error')} "
            f"no_overlap={sum(1 for r in results if r.get('status') == 'no_overlap')}\n"
        )


def aggregate():
    summaries = []
    for json_path in sorted(OUT_DIR.glob("*.json")):
        with json_path.open("r", encoding="utf-8") as handle:
            summaries.append(json.load(handle))

    summary_rows = []
    ice_rows = []
    resonance_rows = []
    for item in summaries:
        if item.get("status") != "ok":
            summary_rows.append(
                {
                    "symbol": item.get("symbol"),
                    "variety": item.get("variety"),
                    "exchange": item.get("exchange"),
                    "interval": item.get("interval"),
                    "status": item.get("status"),
                    "error": item.get("error", ""),
                }
            )
            continue
        row = {
            "symbol": item["symbol"],
            "variety": item["variety"],
            "exchange": item["exchange"],
            "interval": item["interval"],
            "interval_label": item["interval_label"],
            "status": "ok",
            "coverage_full": item["coverage_full"],
            "coverage_start": item["coverage_start"],
            "coverage_end": item["coverage_end"],
            "provider_start": item["provider_start"],
            "provider_end": item["provider_end"],
            "actual_start": item["actual_start"],
            "actual_end": item["actual_end"],
            "bar_count": item["bar_count"],
            "golden_crosses": len(item["golden_crosses"]),
            "death_crosses": len(item["death_crosses"]),
            "ice_points": len(item["ice_points"]),
            "sig_long": len(item["xuanlong_long_signals"]),
            "sig_short": len(item["xuanlong_short_signals"]),
            "resonance_long": len(item["resonance_long_points"]),
            "resonance_short": len(item["resonance_short_points"]),
        }
        summary_rows.append(row)
        for point in item["ice_points"]:
            ice_rows.append(
                {
                    "symbol": item["symbol"],
                    "variety": item["variety"],
                    "exchange": item["exchange"],
                    "interval": item["interval"],
                    **point,
                }
            )
        for point in item["resonance_long_points"]:
            resonance_rows.append(
                {
                    "symbol": item["symbol"],
                    "variety": item["variety"],
                    "exchange": item["exchange"],
                    "interval": item["interval"],
                    "direction": "long",
                    **point,
                }
            )
        for point in item["resonance_short_points"]:
            resonance_rows.append(
                {
                    "symbol": item["symbol"],
                    "variety": item["variety"],
                    "exchange": item["exchange"],
                    "interval": item["interval"],
                    "direction": "short",
                    **point,
                }
            )

    def write_csv_rows(path, rows, fieldnames):
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    summary_fields = [
        "symbol", "variety", "exchange", "interval", "interval_label", "status",
        "coverage_full", "coverage_start", "coverage_end", "provider_start",
        "provider_end", "actual_start", "actual_end", "bar_count",
        "golden_crosses", "death_crosses", "ice_points", "sig_long", "sig_short",
        "resonance_long", "resonance_short",
    ]
    ok_rows = [row for row in summary_rows if row.get("status") == "ok"]
    write_csv_rows(ROOT / "汇总_五周期.csv", ok_rows, summary_fields)

    ice_fields = [
        "symbol", "variety", "exchange", "interval", "death_cross",
        "source_golden_cross", "bar_gap", "close", "mid",
    ]
    write_csv_rows(ROOT / "冰毒点_明细.csv", ice_rows, ice_fields)

    resonance_fields = [
        "symbol", "variety", "exchange", "interval", "direction", "datetime",
        "close", "zk", "zd", "bk",
    ]
    write_csv_rows(ROOT / "共振_明细.csv", resonance_rows, resonance_fields)

    coverage_fields = [
        "interval", "interval_label", "ok", "full", "partial", "no_data",
    ]
    coverage_rows = []
    for interval in ["daily", "30m", "60m", "90m", "120m"]:
        interval_rows = [
            row for row in ok_rows if row["interval"] == interval
        ]
        coverage_rows.append(
            {
                "interval": interval,
                "interval_label": INTERVAL_LABELS.get(
                    interval.replace("m", ""), interval
                ),
                "ok": len(interval_rows),
                "full": sum(1 for row in interval_rows if row["coverage_full"]),
                "partial": sum(
                    1 for row in interval_rows if not row["coverage_full"]
                ),
                "no_data": sum(
                    1
                    for item in summaries
                    if item.get("interval") == interval
                    and item.get("status") != "ok"
                ),
            }
        )
    write_csv_rows(ROOT / "覆盖情况.csv", coverage_rows, coverage_fields)

    by_interval = {}
    for interval in ["daily", "30m", "60m", "90m", "120m"]:
        interval_rows = [row for row in ok_rows if row["interval"] == interval]
        by_interval[interval] = {
            "ok": len(interval_rows),
            "full_coverage": sum(1 for r in interval_rows if r["coverage_full"]),
            "partial_coverage": sum(
                1 for r in interval_rows if not r["coverage_full"]
            ),
            "ice_points": sum(r["ice_points"] for r in interval_rows),
            "golden_crosses": sum(r["golden_crosses"] for r in interval_rows),
            "death_crosses": sum(r["death_crosses"] for r in interval_rows),
            "sig_long": sum(r["sig_long"] for r in interval_rows),
            "sig_short": sum(r["sig_short"] for r in interval_rows),
            "resonance_long": sum(r["resonance_long"] for r in interval_rows),
            "resonance_short": sum(r["resonance_short"] for r in interval_rows),
            "symbols_with_ice": sum(1 for r in interval_rows if r["ice_points"] > 0),
            "top_symbols": sorted(
                [dict(r) for r in interval_rows if r["ice_points"] > 0],
                key=lambda r: r["ice_points"],
                reverse=True,
            )[:10],
        }

    result = {
        "requested": {
            "start": REQUESTED_START_DAILY,
            "end": REQUESTED_END_DAILY,
        },
        "rule": {
            "mid": "MA(CLOSE,20)",
            "ice_window_bars": 3,
            "channel_period": 25,
            "resonance_window_bars": 1,
        },
        "symbol_count": len(SYMBOLS),
        "interval_count": len(INTERVALS),
        "ok_analyses": sum(1 for r in ok_rows for _ in [0]) if ok_rows else 0,
        "total_ice_points": len(ice_rows),
        "total_resonance": len(resonance_rows),
        "by_interval": by_interval,
        "summaries": ok_rows,
        "ice_points": ice_rows,
        "resonance_points": resonance_rows,
    }
    (ROOT / "汇总_五周期.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(
        {
            "ok": result["ok_analyses"],
            "total_ice_points": result["total_ice_points"],
            "total_resonance": result["total_resonance"],
            "by_interval": {
                k: {kk: vv for kk, vv in v.items() if kk != "top_symbols"}
                for k, v in by_interval.items()
            },
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    run_batch()
    aggregate()
