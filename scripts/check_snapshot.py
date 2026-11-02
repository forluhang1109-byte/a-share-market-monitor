"""Consumer-side check: persisted delivery_eligible is not a live freshness check."""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from a_share_monitor.collection import session_collection_window, delivery_gate


def check(snapshot, session, now, live=False):
    meta = snapshot.get("meta", {})
    if meta.get("date") != now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat():
        return False, "wrong_date"
    if meta.get("session") != session or not session_collection_window(meta, session):
        return False, "invalid_collection_window"
    if meta.get("status") not in ("ok", "partial") or not meta.get("is_trading_day"):
        return False, "invalid_status"
    if not all(meta.get("source_status", {}).get(k, {}).get("ok") for k in ("a_share_spot", "indices")):
        return False, "core_data_missing"
    if live:
        if session != "close":
            return False, "live_delivery_requires_close"
        return delivery_gate(meta, now)
    return True, "same_day_historical_sample_not_live_quote"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", choices=["noon", "close"], required=True)
    ap.add_argument("--live", action="store_true", help="Enforce pre-15:00 delivery freshness")
    args = ap.parse_args()
    path = ROOT / "data" / f"latest_{args.session}.json"
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        ok, reason = check(snapshot, args.session, datetime.now(ZoneInfo("Asia/Shanghai")), args.live)
    except (OSError, ValueError, TypeError) as exc:
        ok, reason = False, f"unreadable_snapshot:{type(exc).__name__}"
    print(json.dumps({"ok": ok, "reason": reason, "path": str(path)}, ensure_ascii=False))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
