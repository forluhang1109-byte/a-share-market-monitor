from __future__ import annotations

from typing import Any
import os
import pandas as pd

from .utils import retry_call, safe_float, pick, compact_error


def _code6(value: Any) -> str:
    s = str(value or "").strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits[-6:].zfill(6) if digits else s


def normalize_stock_spot(df: pd.DataFrame, source: str) -> list[dict]:
    """
    Normalize realtime A-share quotes to yuan / shares / percentage points.

    Tencent's 2026 rank API uses:
      zxj      = latest price
      zdf      = change percentage
      turnover =成交额, unit 10k CNY
      volume   =成交量, unit 100 shares (lot)
      zljlr    =主力净流入, unit 10k CNY
    """
    out = []
    for _, r in df.iterrows():
        row = r.to_dict()
        code = _code6(pick(row, ["代码", "code", "symbol", "股票代码"]))
        name = str(pick(row, ["名称", "name", "股票名称"], "") or "")

        if source == "tencent":
            price = safe_float(pick(row, ["zxj"]))
            pct = safe_float(pick(row, ["zdf"]))
            raw_amount = safe_float(pick(row, ["turnover"]), 0.0) or 0.0
            raw_volume = safe_float(pick(row, ["volume"]), 0.0) or 0.0
            raw_main = safe_float(pick(row, ["zljlr"]))
            amount = raw_amount * 10000.0
            volume = raw_volume * 100.0
            main_net = raw_main * 10000.0 if raw_main is not None else None
        else:
            price = safe_float(pick(row, ["最新价", "trade", "price", "现价"]))
            pct = safe_float(pick(row, ["涨跌幅", "changepercent", "change_pct", "pct_chg"]))
            amount = safe_float(pick(row, ["成交额", "amount", "成交金额"]), 0.0) or 0.0
            volume = safe_float(pick(row, ["成交量", "volume"]), 0.0) or 0.0
            main_net = safe_float(pick(row, ["主力净流入-净额", "主力净流入", "main_net"]))

        if code and name:
            out.append({
                "code": code,
                "name": name,
                "price": price,
                "pct": pct,
                "amount": amount,
                "volume": volume,
                "main_net": main_net,
            })
    return out


def _tencent_parallel_frame():
    """Same documented AKShare Tencent endpoint, bounded four-page concurrency."""
    import math
    import time
    import requests
    from concurrent.futures import ThreadPoolExecutor
    url = "https://proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList"
    def page(offset):
        params = {"_appver": "11.17.0", "board_code": "aStock", "sort_type": "price",
                  "direct": "down", "offset": str(offset), "count": "500"}
        # One slow/flaky page must not kill the whole spot fetch (2026-11-05:
        # a single 8s read timeout on one page cascaded into
        # core_data_missing for the entire close snapshot). Retry each page,
        # but timebox the first page hard: if the endpoint is down today,
        # fail fast so the sina fallback still fits the collection budget.
        tries, timeout = (2, (3, 8)) if offset == 0 else (3, (3, 12))
        last_exc = None
        for attempt in range(tries):
            try:
                response = requests.get(url, params=params, timeout=timeout)
                response.raise_for_status()
                return response.json()["data"]
            except Exception as exc:
                last_exc = exc
                if attempt < tries - 1:
                    time.sleep(0.6 * (attempt + 1))
        raise last_exc
    first = page(0)
    total = int(first["total"])
    if total < 1000 or total > 20000:
        raise ValueError("Unexpected Tencent market size")
    rows = list(first["rank_list"])
    with ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(page, range(500, total, 500)):
            if int(result["total"]) != total:
                raise ValueError("Tencent market size changed during collection")
            rows.extend(result["rank_list"])
    frame = pd.DataFrame(rows).drop_duplicates(subset=["code"])
    if len(frame) < total * 0.98:
        raise ValueError("Incomplete Tencent page coverage")
    return frame


def _spot_source_frame(source: str) -> tuple[pd.DataFrame, str]:
    import akshare as ak

    if source == "eastmoney":
        return ak.stock_zh_a_spot_em(), "eastmoney"
    if source == "tencent":
        if os.environ.get("ASH_FAST_MODE") == "1":
            return _tencent_parallel_frame(), "tencent"
        return ak.stock_zh_a_spot_tx(), "tencent"
    return ak.stock_zh_a_spot(), "sina"


def _spot_worker(source: str, output) -> None:
    try:
        df, name = _spot_source_frame(source)
        output.put(("ok", normalize_stock_spot(df, name)))
    except Exception as exc:
        output.put(("err", f"{type(exc).__name__}: {str(exc)[:200]}"))


def fetch_a_share_spot() -> tuple[list[dict], dict]:
    # 2026-11-09: the sequential in-process chain died again — a slow first
    # source (tencent worst case ~70s with per-page retries, sina ~70s)
    # starved every fallback inside the 90s collection budget and the
    # worker was killed with no per-source error at all. In-process HTTP
    # calls cannot be hard-killed, so each source now runs in its own
    # child process with a hard wall-clock slice (same isolation pattern
    # collection.py uses one level up). Slices sum to ~170s, inside the
    # 185s collection budget (start moved to 14:36 on 2026-11-09) with
    # headroom for spawn overhead and result transfer.
    import multiprocessing as mp

    order = ["eastmoney", "tencent", "sina"]
    slices = {"tencent": 45, "eastmoney": 45, "sina": 80}
    if os.environ.get("ASH_FAST_MODE") == "1":
        order = ["tencent", "eastmoney", "sina"]
    ctx = mp.get_context("spawn")
    errors = []
    for name in order:
        q = ctx.Queue()
        p = ctx.Process(target=_spot_worker, args=(name, q))
        p.start()
        p.join(slices[name])
        if p.is_alive():
            p.terminate()
            p.join(timeout=1)
            if p.is_alive():
                p.kill()
                p.join(timeout=1)
            errors.append(f"{name}: exceeded {slices[name]}s slice")
            continue
        try:
            kind, payload = q.get(timeout=5)
        except Exception:
            errors.append(f"{name}: worker exited without result")
            continue
        if kind == "err":
            errors.append(f"{name}: {payload}")
            continue
        rows = payload
        valid_pct = sum(1 for x in rows if x.get("pct") is not None)
        valid_amount = sum(1 for x in rows if (x.get("amount") or 0) > 0)
        if len(rows) < 1000:
            errors.append(f"{name}: normalized rows too few: {len(rows)}")
            continue
        if valid_pct < 1000:
            errors.append(f"{name}: valid pct rows too few: {valid_pct}")
            continue
        if valid_amount < 1000:
            errors.append(f"{name}: valid amount rows too few: {valid_amount}")
            continue
        return rows, {
            "source": name,
            "ok": True,
            "rows": len(rows),
            "valid_pct_rows": valid_pct,
            "valid_amount_rows": valid_amount,
            "errors": errors,
        }
    raise RuntimeError("all A-share realtime providers failed | " + " | ".join(errors))


def _normalize_indices(df: pd.DataFrame, wanted: dict[str, str]) -> list[dict]:
    results = []
    for _, r in df.iterrows():
        row = r.to_dict()
        code = _code6(pick(row, ["代码", "code", "symbol"]))
        raw_symbol = str(pick(row, ["symbol"], "") or "")
        for wanted_code, wanted_name in wanted.items():
            if code == wanted_code or raw_symbol.endswith(wanted_code):
                results.append({
                    "code": wanted_code,
                    "name": wanted_name,
                    "price": safe_float(pick(row, ["最新价", "trade", "price"])),
                    "pct": safe_float(pick(row, ["涨跌幅", "changepercent", "pct_chg"])),
                    "amount": safe_float(pick(row, ["成交额", "amount"]), 0.0),
                    "volume": safe_float(pick(row, ["成交量", "volume"]), 0.0),
                    "high": safe_float(pick(row, ["最高", "high"])),
                    "low": safe_float(pick(row, ["最低", "low"])),
                    "open": safe_float(pick(row, ["今开", "open"])),
                    "prev_close": safe_float(pick(row, ["昨收", "settlement", "pre_close"])),
                })
    dedup = {x["code"]: x for x in results}
    return [dedup[k] for k in wanted if k in dedup]


def _tencent_indices(wanted: dict[str, str]) -> list[dict]:
    import requests
    symbols = [("sh" if code.startswith("000") else "sz") + code for code in wanted]
    response = requests.get("https://qt.gtimg.cn/q=" + ",".join(symbols), timeout=(3, 8))
    response.raise_for_status()
    rows = {}
    for line in response.text.split(";"):
        if '="' not in line:
            continue
        fields = line.split('="', 1)[1].strip().strip('"').split("~")
        if len(fields) <= 32 or fields[2] not in wanted:
            continue
        code = fields[2]
        price, pct = safe_float(fields[3]), safe_float(fields[32])
        if price is not None and price > 0 and pct is not None:
            rows[code] = {"code": code, "name": wanted[code], "price": price, "pct": pct,
                          "provider_quote_time": fields[30]}
    if set(rows) != set(wanted):
        raise RuntimeError(f"incomplete Tencent indices: {sorted(rows)}")
    return [rows[code] for code in wanted]


def fetch_indices(wanted: dict[str, str]) -> tuple[list[dict], dict]:
    import akshare as ak
    errors = []
    # One bounded batch request before AKShare's potentially long paginated
    # index endpoints; a hung first source must not starve every fallback.
    try:
        rows = _tencent_indices(wanted)
        return rows, {"source": "tencent", "ok": True, "rows": len(rows), "errors": []}
    except Exception as exc:
        errors.append(f"tencent: {compact_error(exc)}")
    attempts = [
        ("eastmoney", lambda: ak.stock_zh_index_spot_em(symbol="沪深重要指数")),
        ("sina", lambda: ak.stock_zh_index_spot_sina()),
    ]
    if os.environ.get("ASH_FAST_MODE") == "1":
        attempts.reverse()
    for name, fn in attempts:
        try:
            df = retry_call(fn, attempts=2, delay=1.2)
            rows = _normalize_indices(df, wanted)
            if len(rows) != len(wanted) or not all(
                r.get("price") is not None and r["price"] > 0 and r.get("pct") is not None
                for r in rows
            ):
                raise RuntimeError(f"wanted indices found: {len(rows)}")
            return rows, {"source": name, "ok": True, "rows": len(rows), "errors": errors}
        except Exception as exc:
            errors.append(f"{name}: {compact_error(exc)}")
    return [], {"source": None, "ok": False, "rows": 0, "errors": errors}


def _sector_rows(df: pd.DataFrame, net_multiplier: float = 1.0) -> list[dict]:
    rows = []
    for _, r in df.iterrows():
        row = r.to_dict()
        raw_net = safe_float(pick(row, ["主力净流入-净额", "净额"]))
        rows.append({
            "name": str(pick(row, ["名称", "行业", "概念"], "") or ""),
            "pct": safe_float(pick(row, ["今日涨跌幅", "行业-涨跌幅", "涨跌幅"])),
            "main_net": raw_net * net_multiplier if raw_net is not None else None,
            "main_ratio": safe_float(pick(row, ["主力净流入-净占比"])),
            "leader": str(pick(row, ["主力净流入最大股", "领涨股"], "") or ""),
        })
    return [x for x in rows if x["name"]]


def fetch_sector_flow(sector_type: str) -> tuple[list[dict], dict]:
    import akshare as ak

    errors = []

    # Primary: Eastmoney sector fund-flow rank.
    try:
        df = retry_call(
            lambda: ak.stock_sector_fund_flow_rank(indicator="今日", sector_type=sector_type),
            attempts=2,
            delay=1.5,
        )
        rows = _sector_rows(df, net_multiplier=1.0)
        if rows:
            return rows, {"source": "eastmoney", "ok": True, "rows": len(rows), "errors": errors}
        raise RuntimeError("empty Eastmoney sector rows")
    except Exception as exc:
        errors.append(f"eastmoney: {compact_error(exc)}")

    # Fallback: THS fund-flow tables. THS '净额' is in 1e8 CNY.
    try:
        if "概念" in sector_type:
            df = retry_call(lambda: ak.stock_fund_flow_concept(symbol="即时"), attempts=2, delay=1.5)
        else:
            df = retry_call(lambda: ak.stock_fund_flow_industry(symbol="即时"), attempts=2, delay=1.5)
        rows = _sector_rows(df, net_multiplier=1e8)
        if not rows:
            raise RuntimeError("empty THS sector rows")
        return rows, {"source": "ths", "ok": True, "rows": len(rows), "errors": errors}
    except Exception as exc:
        errors.append(f"ths: {compact_error(exc)}")

    return [], {"source": None, "ok": False, "rows": 0, "errors": errors}


def validate_market_flow_date(row: dict, expected_date: str) -> bool:
    """Historical daily endpoints must not masquerade as today's intraday flow."""
    value = row.get("日期") or row.get("date")
    if value is None:
        return False
    try:
        return pd.Timestamp(value).date().isoformat() == expected_date
    except (ValueError, TypeError):
        return False


def fetch_market_fund_flow() -> tuple[dict | None, dict]:
    import akshare as ak
    try:
        df = retry_call(lambda: ak.stock_market_fund_flow(), attempts=2, delay=1.5)
        if df is None or df.empty:
            return None, {"source": "eastmoney", "ok": False, "errors": ["empty dataframe"]}
        row = df.iloc[-1].to_dict()
        cleaned = {}
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                v = v.isoformat()
            elif pd.isna(v):
                v = None
            elif hasattr(v, "item"):
                v = v.item()
            cleaned[str(k)] = v
        from .utils import now_cn
        expected_date = now_cn().date().isoformat()
        if not validate_market_flow_date(cleaned, expected_date):
            return None, {"source": "eastmoney", "ok": False,
                          "data_date": cleaned.get("日期"),
                          "errors": ["stale or missing market flow date; expected " + expected_date]}
        return cleaned, {"source": "eastmoney", "ok": True, "data_date": expected_date, "errors": []}
    except Exception as exc:
        return None, {"source": "eastmoney", "ok": False, "errors": [compact_error(exc)]}


def aggregate_tencent_market_main_flow(stocks: list[dict]) -> dict | None:
    vals = [x.get("main_net") for x in stocks if x.get("main_net") is not None]
    if len(vals) < 1000:
        return None
    return {
        "source": "tencent_stock_aggregate",
        "主力净流入-净额": float(sum(vals)),
        "覆盖股票数": len(vals),
        "说明": "由腾讯个股实时主力净流入字段聚合，作为东财大盘资金流接口失败时的备用参考",
    }


def fetch_limit_stats(date_yyyymmdd: str) -> tuple[dict, dict]:
    import akshare as ak
    stats = {"limit_up": None, "limit_down": None, "broken": None}
    errors = []
    calls = [
        ("limit_up", lambda: ak.stock_zt_pool_em(date=date_yyyymmdd)),
        ("limit_down", lambda: ak.stock_zt_pool_dtgc_em(date=date_yyyymmdd)),
        ("broken", lambda: ak.stock_zt_pool_zbgc_em(date=date_yyyymmdd)),
    ]
    for key, fn in calls:
        try:
            df = retry_call(fn, attempts=2, delay=1.0)
            stats[key] = int(len(df))
        except Exception as exc:
            errors.append(f"{key}: {compact_error(exc)}")
    return stats, {"source": "eastmoney", "ok": any(v is not None for v in stats.values()), "errors": errors}


