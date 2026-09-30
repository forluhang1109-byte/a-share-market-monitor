from __future__ import annotations

import json
import math
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any, Callable


def now_cn() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def safe_float(value: Any, default=None):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace(",", "").replace("%", "").strip()
            if value in {"", "-", "--", "None", "nan"}:
                return default
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except Exception:
        return default


def safe_int(value: Any, default=0):
    f = safe_float(value, None)
    return int(f) if f is not None else default


def pick(row, candidates, default=None):
    for key in candidates:
        if key in row and row[key] is not None:
            return row[key]
    return default


def retry_call(fn: Callable, attempts: int = 3, delay: float = 2.0):
    last_error = None
    for idx in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last_error = exc
            if idx < attempts - 1:
                time.sleep(delay * (idx + 1))
    raise last_error


def load_json(path: Path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def compact_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc)[:260]}"
