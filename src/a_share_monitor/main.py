from __future__ import annotations

from pathlib import Path
from typing import Any

from .utils import now_cn, load_json, dump_json
from .calendar import is_trading_day
from .providers import (
    fetch_a_share_spot,
    fetch_indices,
    fetch_sector_flow,
    fetch_market_fund_flow,
    aggregate_tencent_market_main_flow,
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
from .collection import collect, delivery_gate
import time


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

    started = time.monotonic()
    snapshot["meta"]["collection_started_at"] = now_cn().isoformat()
    results = collect(settings, date_yyyymmdd)
    mapping = {
        "a_share_spot": "fetch_a_share_spot", "indices": "fetch_indices",
        "industry_flow": "fetch_sector_flow:industry", "concept_flow": "fetch_sector_flow:concept",
        "market_fund_flow": "fetch_market_fund_flow", "limit_pool": "fetch_limit_stats",
    }
    for label, key in mapping.items():
        status = results[key][1]
        snapshot["meta"]["source_status"][label] = status
        if not status.get("ok"):
            snapshot["meta"]["errors"].extend(f"{label}: {e}" for e in status.get("errors", []))
    stocks = results["fetch_a_share_spot"][0] or []
    indices = results["fetch_indices"][0] or []
    industry_rows = results["fetch_sector_flow:industry"][0] or []
    concept_rows = results["fetch_sector_flow:concept"][0] or []
    market_flow = results["fetch_market_fund_flow"][0]
    if market_flow is None:
        market_flow = aggregate_tencent_market_main_flow(stocks)
        if market_flow is not None:
            snapshot["meta"]["source_status"]["market_fund_flow"].update(ok=True, source="tencent_stock_aggregate")
    limit_stats = results["fetch_limit_stats"][0] or {"limit_up": None, "limit_down": None, "broken": None}
    breadth = build_breadth(stocks) if stocks else {}
    turnover_current = total_turnover(stocks) if stocks else None
    snapshot["meta"]["collection_completed_at"] = now_cn().isoformat()
    snapshot["meta"]["collection_elapsed_seconds"] = round(time.monotonic() - started, 2)
    snapshot["meta"]["quote_timestamp_verified"] = False

    previous = _previous_snapshot(session, date_str)
    prev_turnover = None
    if previous:
        prev_turnover = previous.get("market", {}).get("turnover", {}).get("current")

    comparable_time = False
    if previous:
        try:
            from datetime import datetime
            old = datetime.fromisoformat(previous["meta"]["collection_started_at"])
            current = datetime.fromisoformat(snapshot["meta"]["collection_started_at"])
            comparable_time = abs((old.hour * 3600 + old.minute * 60 + old.second) -
                                  (current.hour * 3600 + current.minute * 60 + current.second)) <= 120
            old_source = previous["meta"]["source_status"]["a_share_spot"]
            new_source = snapshot["meta"]["source_status"]["a_share_spot"]
            comparable_time = comparable_time and old_source.get("source") == new_source.get("source")
        except (KeyError, ValueError, TypeError):
            pass
    if not comparable_time:
        prev_turnover = None

    volume_cfg = settings.get("volume", {})
    turnover = volume_compare(
        turnover_current,
        prev_turnover,
        float(volume_cfg.get("expand_threshold", 1.05)),
        float(volume_cfg.get("shrink_threshold", 0.95)),
    )

    if turnover_current is None:
        turnover.update(current=None, ratio=None, change_pct=None, label="行情缺失，不能判断量能")
    turnover["same_collection_time_and_source"] = comparable_time

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

    # 'partial' only when a material data component is unavailable. Provider
    # fallback warnings live inside source_status.errors and do not downgrade
    # an otherwise usable snapshot.
    critical_missing = (
        not stocks
        or not indices
        or not industry_rows
        or not concept_rows
    )
    snapshot["meta"]["status"] = "partial" if critical_missing else "ok"

    snapshot["meta"]["generated_at"] = now_cn().isoformat()
    eligible, reason = delivery_gate(snapshot["meta"], now_cn())
    snapshot["meta"]["delivery_eligible"] = eligible if session == "close" else False
    snapshot["meta"]["delivery_reason"] = reason
    snapshot["meta"]["portfolio_status"] = "stored_configuration_not_reconfirmed"
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

