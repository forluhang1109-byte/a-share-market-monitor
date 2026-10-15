"""Parallel, killable collection with a hard wall-clock budget (no thread leaks)."""
from __future__ import annotations

import multiprocessing as mp
import queue
import time
from datetime import datetime
from zoneinfo import ZoneInfo


def _task(name, args, output):
    started = time.monotonic()
    try:
        from . import providers
        fn = getattr(providers, name)
        data, status = fn(*args)
        status.update(collected_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
                      elapsed_seconds=round(time.monotonic() - started, 2),
                      quote_timestamp_verified=False)
        output.put((name, data, status))
    except Exception as exc:
        output.put((name, None, {"ok": False, "errors": [f"{type(exc).__name__}: {str(exc)[:240]}"]}))


def collect(settings, day, budget_seconds=75, task_target=None):
    specs = {
        "fetch_a_share_spot": (),
        "fetch_indices": (settings.get("index_codes", {}),),
        "fetch_sector_flow:industry": ("行业资金流",),
        "fetch_sector_flow:concept": ("概念资金流",),
        "fetch_market_fund_flow": (),
        "fetch_limit_stats": (day,),
    }
    ctx = mp.get_context("spawn")
    processes, outputs, results = {}, {}, {}
    started = time.monotonic()
    try:
        for key, args in specs.items():
            q = ctx.Queue()
            p = ctx.Process(target=task_target or _task, args=(key.split(":")[0], args, q))
            p.start()
            processes[key], outputs[key] = p, q
        while len(results) < len(specs) and time.monotonic() - started < budget_seconds:
            for key, q in outputs.items():
                if key not in results:
                    try:
                        _, data, status = q.get_nowait()
                        results[key] = (data, status)
                    except queue.Empty:
                        pass
            if len(results) < len(specs):
                time.sleep(0.02)
    finally:
        for p in processes.values():
            if p.is_alive():
                p.terminate()
            p.join(timeout=0.5)
            if p.is_alive():
                p.kill()
                p.join(timeout=0.5)
        for q in outputs.values():
            q.close()
    for key in specs:
        results.setdefault(key, (None, {"ok": False, "errors": ["collection deadline exceeded or worker exited"],
                                       "timed_out": True}))
    return results


def delivery_gate(meta, now):
    """Collection time is not an exchange quote timestamp; never hide this distinction."""
    if meta.get("calendar_source") != "exchange_calendars:XSHG":
        return False, "trading_calendar_unverified"
    if not meta.get("is_trading_day"):
        return False, "non_trading_day"
    try:
        start = datetime.fromisoformat(meta["collection_started_at"])
        end = datetime.fromisoformat(meta["collection_completed_at"])
        if any(t.tzinfo is None for t in (start, end, now)):
            return False, "missing_timezone"
    except (KeyError, ValueError, TypeError):
        return False, "missing_collection_timestamps"
    cn = ZoneInfo("Asia/Shanghai")
    start, end, now = (t.astimezone(cn) for t in (start, end, now))
    if start.date() != now.date() or end.date() != now.date():
        return False, "wrong_date"
    if not ("14:40" <= start.strftime("%H:%M") <= "14:48"):
        return False, "outside_collection_window"
    if end.strftime("%H:%M") > "14:48" or now.strftime("%H:%M") > "14:49":
        return False, "past_delivery_deadline"
    if not (0 <= (end-start).total_seconds() <= 100 and 0 <= (now-end).total_seconds() <= 300):
        return False, "stale_or_invalid_collection"
    statuses = meta.get("source_status", {})
    if not all(statuses.get(k, {}).get("ok") for k in ("a_share_spot", "indices")):
        return False, "core_data_missing"
    return True, "collection_fresh_quote_timestamps_unverified"
