from __future__ import annotations

import argparse
import sys
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from a_share_monitor.main import run
from a_share_monitor.collection import session_collection_window


def wait_until(hhmm: str, max_wait_minutes: int):
    tz = ZoneInfo("Asia/Shanghai")
    now = datetime.now(tz)
    hh, mm = [int(x) for x in hhmm.split(":")]
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if now >= target:
        return
    wait_seconds = (target - now).total_seconds()
    max_seconds = max_wait_minutes * 60
    if wait_seconds > max_seconds:
        raise RuntimeError(
            f"target {hhmm} is {wait_seconds/60:.1f} minutes away, "
            f"exceeds max_wait_minutes={max_wait_minutes}"
        )
    print(f"[wait] Beijing time now={now:%H:%M:%S}; waiting until {hhmm}, {wait_seconds:.0f}s")
    time.sleep(wait_seconds)


def _window_guard(session: str):
    """Fail visibly rather than backfilling a snapshot after market hours."""
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    deadline = {"noon": "11:41", "close": "14:48"}[session]
    if now.strftime("%H:%M") >= deadline:
        print(f"[expired] {session} collection deadline passed at {now:%H:%M:%S}; no overwrite")
        sys.exit(4)


def _already_collected(session: str) -> bool:
    """Skip redundant cron attempts only after a valid, complete collection."""
    path = ROOT / "data" / "history" / f"{datetime.now(ZoneInfo('Asia/Shanghai')):%Y-%m-%d}_{session}.json"
    if not path.exists():
        return False
    try:
        meta = json.loads(path.read_text(encoding="utf-8")).get("meta", {})
        return meta.get("status") == "ok" and session_collection_window(meta, session)
    except (OSError, ValueError, TypeError):
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", choices=["noon", "close"], required=True)
    ap.add_argument("--not-before", default=None, help="Beijing HH:MM")
    ap.add_argument("--max-wait-minutes", type=int, default=15)
    ap.add_argument("--skip-wait", action="store_true")
    args = ap.parse_args()

    if not args.skip_wait:
        if _already_collected(args.session):
            print(f"[already_done] {args.session}: valid snapshot already present")
            return
        _window_guard(args.session)
    if args.not_before and not args.skip_wait:
        wait_until(args.not_before, args.max_wait_minutes)
    if not args.skip_wait:
        _window_guard(args.session)
        if _already_collected(args.session):
            print(f"[already_done] {args.session}: valid snapshot already present")
            return

    snap = run(args.session, require_window=not args.skip_wait)
    if snap.get("meta", {}).get("status") == "invalid_collection_window":
        print(f"[expired] {args.session} collection finished outside its window; historical files unchanged")
        sys.exit(4)
    print(
        f"[done] session={args.session} "
        f"status={snap.get('meta',{}).get('status')} "
        f"generated_at={snap.get('meta',{}).get('generated_at')}"
    )
    if snap.get("meta", {}).get("errors"):
        print("[partial errors]")
        for e in snap["meta"]["errors"]:
            print(" -", e)


if __name__ == "__main__":
    main()

