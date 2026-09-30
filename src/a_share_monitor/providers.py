from __future__ import annotations

from typing import Any
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


def fetch_a_share_spot() -> tuple[list[dict], dict]:
    import akshare as ak

    candidates = [
        ("eastmoney", lambda: ak.stock_zh_a_spot_em()),
        ("tencent", lambda: ak.stock_zh_a_spot_tx()),
        ("sina", lambda: ak.stock_zh_a_spot()),
    ]
    errors = []
    for name, fn in candidates:
        try:
            df = retry_call(fn, attempts=2, delay=1.5)
            rows = normalize_stock_spot(df, name)
            valid_pct = sum(1 for x in rows if x.get("pct") is not None)
            valid_amount = sum(1 for x in rows if (x.get("amount") or 0) > 0)
            if len(rows) < 1000:
                raise RuntimeError(f"normalized rows too few: {len(rows)}")
            if valid_pct < 1000:
                raise RuntimeError(f"valid pct rows too few: {valid_pct}")
            if valid_amount < 1000:
                raise RuntimeError(f"valid amount rows too few: {valid_amount}")
            return rows, {
                "source": name,
                "ok": True,
                "rows": len(rows),
                "valid_pct_rows": valid_pct,
                "valid_amount_rows": valid_amount,
                "errors": errors,
            }
        except Exception as exc:
            errors.append(f"{name}: {compact_error(exc)}")
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


def fetch_indices(wanted: dict[str, str]) -> tuple[list[dict], dict]:
    import akshare as ak
    attempts = [
        ("eastmoney", lambda: ak.stock_zh_index_spot_em(symbol="沪深重要指数")),
        ("sina", lambda: ak.stock_zh_index_spot_sina()),
    ]
    errors = []
    for name, fn in attempts:
        try:
            df = retry_call(fn, attempts=2, delay=1.2)
            rows = _normalize_indices(df, wanted)
            if len(rows) < 3:
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
        return cleaned, {"source": "eastmoney", "ok": True, "errors": []}
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
