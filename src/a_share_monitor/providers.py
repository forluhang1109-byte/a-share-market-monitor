from __future__ import annotations

from typing import Any
import pandas as pd

from .utils import retry_call, safe_float, safe_int, pick, compact_error


def _code6(value: Any) -> str:
    s = str(value or "").strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits[-6:].zfill(6) if digits else s


def normalize_stock_spot(df: pd.DataFrame) -> list[dict]:
    out = []
    for _, r in df.iterrows():
        row = r.to_dict()
        code = _code6(pick(row, ["代码", "code", "symbol", "股票代码"]))
        name = str(pick(row, ["名称", "name", "股票名称"], "") or "")
        price = safe_float(pick(row, ["最新价", "trade", "price", "现价"]))
        pct = safe_float(pick(row, ["涨跌幅", "changepercent", "change_pct", "pct_chg"]))
        amount = safe_float(pick(row, ["成交额", "amount", "成交金额"]), 0.0) or 0.0
        volume = safe_float(pick(row, ["成交量", "volume"]), 0.0) or 0.0
        if code and name:
            out.append({
                "code": code,
                "name": name,
                "price": price,
                "pct": pct,
                "amount": amount,
                "volume": volume,
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
            rows = normalize_stock_spot(df)
            if len(rows) < 1000:
                raise RuntimeError(f"normalized rows too few: {len(rows)}")
            return rows, {"source": name, "ok": True, "rows": len(rows), "errors": errors}
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


def _sector_rows(df: pd.DataFrame) -> list[dict]:
    rows = []
    for _, r in df.iterrows():
        row = r.to_dict()
        rows.append({
            "name": str(pick(row, ["名称", "行业", "概念"], "") or ""),
            "pct": safe_float(pick(row, ["今日涨跌幅", "行业-涨跌幅", "涨跌幅"])),
            "main_net": safe_float(pick(row, ["主力净流入-净额", "净额"])),
            "main_ratio": safe_float(pick(row, ["主力净流入-净占比"])),
            "leader": str(pick(row, ["主力净流入最大股", "领涨股"], "") or ""),
        })
    return [x for x in rows if x["name"]]


def fetch_sector_flow(sector_type: str) -> tuple[list[dict], dict]:
    import akshare as ak
    try:
        df = retry_call(
            lambda: ak.stock_sector_fund_flow_rank(indicator="今日", sector_type=sector_type),
            attempts=2,
            delay=1.5,
        )
        rows = _sector_rows(df)
        return rows, {"source": "eastmoney", "ok": True, "rows": len(rows), "errors": []}
    except Exception as exc:
        return [], {"source": "eastmoney", "ok": False, "rows": 0, "errors": [compact_error(exc)]}


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
