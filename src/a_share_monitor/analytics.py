from __future__ import annotations

from statistics import mean
from typing import Any

from .utils import safe_float


def build_breadth(stocks: list[dict]) -> dict:
    pcts = [x["pct"] for x in stocks if x.get("pct") is not None]
    up = sum(1 for x in pcts if x > 0)
    down = sum(1 for x in pcts if x < 0)
    flat = sum(1 for x in pcts if x == 0)
    return {
        "total_valid": len(pcts),
        "up": up,
        "down": down,
        "flat": flat,
        "median_pct": sorted(pcts)[len(pcts)//2] if pcts else None,
        "avg_pct": mean(pcts) if pcts else None,
        "up_down_ratio": (up / down) if down else None,
    }


def total_turnover(stocks: list[dict]) -> float:
    return float(sum((x.get("amount") or 0.0) for x in stocks))


def volume_compare(current: float, previous: float | None, expand_threshold: float, shrink_threshold: float) -> dict:
    if not previous or previous <= 0:
        return {
            "current": current,
            "previous_same_session": previous,
            "ratio": None,
            "change_pct": None,
            "label": "暂无同周期基准",
        }
    ratio = current / previous
    change_pct = (ratio - 1) * 100
    if ratio >= expand_threshold:
        label = "放量"
    elif ratio <= shrink_threshold:
        label = "缩量"
    else:
        label = "量能接近"
    return {
        "current": current,
        "previous_same_session": previous,
        "ratio": ratio,
        "change_pct": change_pct,
        "label": label,
    }


def rank_sector_rows(rows: list[dict], top_n: int = 10) -> dict:
    with_pct = [x for x in rows if x.get("pct") is not None]
    with_flow = [x for x in rows if x.get("main_net") is not None]
    return {
        "top_gain": sorted(with_pct, key=lambda x: x["pct"], reverse=True)[:top_n],
        "bottom_gain": sorted(with_pct, key=lambda x: x["pct"])[:top_n],
        "top_main_inflow": sorted(with_flow, key=lambda x: x["main_net"], reverse=True)[:top_n],
        "top_main_outflow": sorted(with_flow, key=lambda x: x["main_net"])[:top_n],
        "all": rows,
    }


def _theme_matches(theme: str, sector_rows: list[dict]) -> list[dict]:
    t = theme.strip().lower()
    if not t:
        return []
    exact = [x for x in sector_rows if str(x.get("name", "")).strip().lower() == t]
    if exact:
        return exact[:3]
    fuzzy = [
        x for x in sector_rows
        if t in str(x.get("name", "")).lower() or str(x.get("name", "")).lower() in t
    ]
    return fuzzy[:3]


def analyze_portfolio(
    portfolio: list[dict],
    industry_rows: list[dict],
    concept_rows: list[dict],
    indices: list[dict],
    turnover: dict,
    stop_loss_pct: float = -15,
) -> list[dict]:
    all_sectors = industry_rows + concept_rows
    market_index_pcts = [x.get("pct") for x in indices if x.get("pct") is not None]
    market_avg = mean(market_index_pcts) if market_index_pcts else 0.0

    results = []
    for item in portfolio:
        themes = item.get("themes") or []
        matches = []
        seen = set()
        for theme in themes:
            for row in _theme_matches(str(theme), all_sectors):
                key = row.get("name")
                if key not in seen:
                    seen.add(key)
                    matches.append(row)

        pcts = [x["pct"] for x in matches if x.get("pct") is not None]
        flows = [x["main_net"] for x in matches if x.get("main_net") is not None]
        theme_avg_pct = mean(pcts) if pcts else None
        flow_sum = sum(flows) if flows else None

        score = 0.0
        reasons = []
        if theme_avg_pct is not None:
            if theme_avg_pct >= 1.5:
                score += 2
                reasons.append("对应主题平均涨幅较强")
            elif theme_avg_pct >= 0.3:
                score += 1
                reasons.append("对应主题偏强")
            elif theme_avg_pct <= -1.5:
                score -= 2
                reasons.append("对应主题平均跌幅较大")
            elif theme_avg_pct <= -0.3:
                score -= 1
                reasons.append("对应主题偏弱")

        if flow_sum is not None:
            if flow_sum > 0:
                score += 0.8
                reasons.append("匹配板块主力资金合计为净流入")
            elif flow_sum < 0:
                score -= 0.8
                reasons.append("匹配板块主力资金合计为净流出")

        if market_avg > 0.3:
            score += 0.4
            reasons.append("主要指数整体偏强")
        elif market_avg < -0.3:
            score -= 0.4
            reasons.append("主要指数整体偏弱")

        vr = turnover.get("ratio")
        if vr is not None and vr >= 1.05:
            score += 0.3 if score > 0 else 0
            reasons.append("市场较上一同周期放量")
        elif vr is not None and vr <= 0.95:
            reasons.append("市场较上一同周期缩量")

        if score >= 1.8:
            strength = "偏强"
            action = "继续持有观察；若尾盘仍放量且对应板块资金未转负，再评估是否分批加仓。"
        elif score <= -1.8:
            strength = "偏弱"
            action = "暂不加仓；观察是否止跌、资金回流。若已触及个人风控线，优先执行既定风控。"
        else:
            strength = "中性"
            action = "以持有观察为主；等待方向、成交量和资金流进一步确认，不追涨。"

        cost_return_pct = safe_float(item.get("cost_return_pct"))
        risk_alert = None
        if cost_return_pct is not None and cost_return_pct <= stop_loss_pct:
            risk_alert = f"当前持仓收益率 {cost_return_pct:.2f}% 已触及设定风控线 {stop_loss_pct:.2f}%"
            action = "已触及设定风控线：优先复核仓位与止损纪律，不用短线反弹预期替代风控。"

        results.append({
            "name": item.get("name"),
            "fund_code": item.get("fund_code"),
            "amount": item.get("amount"),
            "cost_return_pct": cost_return_pct,
            "themes": themes,
            "matched_sectors": matches,
            "theme_avg_pct": theme_avg_pct,
            "matched_main_flow_sum": flow_sum,
            "score": round(score, 2),
            "strength": strength,
            "reasons": reasons,
            "risk_alert": risk_alert,
            "action_reference": action,
        })
    return results
