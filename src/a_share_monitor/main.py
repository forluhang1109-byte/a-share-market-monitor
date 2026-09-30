from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from .utils import now_cn, load_json, dump_json
from .calendar import is_trading_day
from .providers import (
    fetch_a_share_spot,
    fetch_indices,
    fetch_sector_flow,
    fetch_market_fund_flow,
    fetch_limit_stats,
)
from .analytics import (
    build_breadth,
    total_turnover,
    volume_compare,
    rank_sector_rows,
    analyze_portfolio,
)
from .report import make_markdown


ROOT = Path(__file__).resolve().parents[2]


def _previous_snapshot(session: str, current_date: str) -> dict | None:
    hist = ROOT / "data" / "history"
    if not hist.exists():
        return None
    files = sorted(hist.glob(f"*_{session}.json"), reverse=True)
    for path in files:
        if path.name.startswith(current_date):
            continue
        try:
            snap = load_json(path, None)
            if snap and snap.get("meta", {}).get("is_trading_day"):
                return snap
        except Exception:
            continue
    return None


def run(session: str = "noon") -> dict:
    now = now_cn()
    day = now.date()
    date_str = day.isoformat()
    date_yyyymmdd = day.strftime("%Y%m%d")

    settings = load_json(ROOT / "config" / "settings.json", {})
    portfolio = load_json(ROOT / "config" / "portfolio.json", [])
    trading, calendar_source = is_trading_day(day)

    snapshot: dict[str, Any] = {
        "meta": {
            "generated_at": now.isoformat(),
            "session": session,
            "date": date_str,
            "is_trading_day": trading,
            "calendar_source": calendar_source,
            "source_status": {},
            "errors": [],
        },
        "market": {},
        "sectors": {},
        "portfolio": [],
    }

    if not trading:
        snapshot["meta"]["status"] = "skipped_non_trading_day"
        _write_outputs(snapshot, session, date_str)
        return snapshot

    # A-share realtime spot is the core dependency.
    try:
        stocks, status = fetch_a_share_spot()
        snapshot["meta"]["source_status"]["a_share_spot"] = status
        breadth = build_breadth(stocks)
        turnover_current = total_turnover(stocks)
    except Exception as exc:
        stocks = []
        breadth = {}
        turnover_current = 0.0
        snapshot["meta"]["errors"].append(f"A股实时行情失败: {type(exc).__name__}: {str(exc)[:300]}")

    try:
        indices, status = fetch_indices(settings.get("index_codes", {}))
        snapshot["meta"]["source_status"]["indices"] = status
    except Exception as exc:
        indices = []
        snapshot["meta"]["errors"].append(f"指数行情失败: {type(exc).__name__}: {str(exc)[:300]}")

    industry_rows, status = fetch_sector_flow("行业资金流")
    snapshot["meta"]["source_status"]["industry_flow"] = status
    if not status.get("ok"):
        snapshot["meta"]["errors"].extend([f"行业资金流: {e}" for e in status.get("errors", [])])

    concept_rows, status = fetch_sector_flow("概念资金流")
    snapshot["meta"]["source_status"]["concept_flow"] = status
    if not status.get("ok"):
        snapshot["meta"]["errors"].extend([f"概念资金流: {e}" for e in status.get("errors", [])])

    market_flow, status = fetch_market_fund_flow()
    snapshot["meta"]["source_status"]["market_fund_flow"] = status
    if not status.get("ok"):
        snapshot["meta"]["errors"].extend([f"大盘资金流: {e}" for e in status.get("errors", [])])

    limit_stats, status = fetch_limit_stats(date_yyyymmdd)
    snapshot["meta"]["source_status"]["limit_pool"] = status
    if status.get("errors"):
        snapshot["meta"]["errors"].extend([f"涨跌停池: {e}" for e in status.get("errors", [])])

    previous = _previous_snapshot(session, date_str)
    prev_turnover = None
    if previous:
        prev_turnover = previous.get("market", {}).get("turnover", {}).get("current")

    volume_cfg = settings.get("volume", {})
    turnover = volume_compare(
        turnover_current,
        prev_turnover,
        float(volume_cfg.get("expand_threshold", 1.05)),
        float(volume_cfg.get("shrink_threshold", 0.95)),
    )

    top_n = int(settings.get("report", {}).get("top_n", 10))
    industry_ranked = rank_sector_rows(industry_rows, top_n=top_n)
    concept_ranked = rank_sector_rows(concept_rows, top_n=top_n)

    snapshot["market"] = {
        "indices": indices,
        "breadth": breadth,
        "turnover": turnover,
        "limit_stats": limit_stats,
        "market_fund_flow": market_flow,
    }
    snapshot["sectors"] = {
        "industry": industry_ranked,
        "concept": concept_ranked,
    }

    snapshot["portfolio"] = analyze_portfolio(
        portfolio=portfolio,
        industry_rows=industry_rows,
        concept_rows=concept_rows,
        indices=indices,
        turnover=turnover,
        stop_loss_pct=float(settings.get("risk", {}).get("stop_loss_pct", -15)),
    )

    snapshot["meta"]["status"] = "ok" if not snapshot["meta"]["errors"] else "partial"
    _write_outputs(snapshot, session, date_str)
    return snapshot


def _write_outputs(snapshot: dict, session: str, date_str: str):
    data_dir = ROOT / "data"
    report_dir = ROOT / "reports"
    hist_dir = data_dir / "history"
    data_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    hist_dir.mkdir(parents=True, exist_ok=True)

    latest_json = data_dir / f"latest_{session}.json"
    history_json = hist_dir / f"{date_str}_{session}.json"
    latest_md = report_dir / f"latest_{session}.md"
    history_md = report_dir / f"{date_str}_{session}.md"

    dump_json(latest_json, snapshot)
    dump_json(history_json, snapshot)
    md = make_markdown(snapshot)
    latest_md.write_text(md, encoding="utf-8")
    history_md.write_text(md, encoding="utf-8")
