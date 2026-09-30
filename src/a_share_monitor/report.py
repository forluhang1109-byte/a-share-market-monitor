from __future__ import annotations

from typing import Any


def _pct(x):
    return "—" if x is None else f"{x:+.2f}%"


def _yi(x):
    if x is None:
        return "—"
    return f"{x / 1e8:+.2f}亿"


def _money(x):
    if x is None:
        return "—"
    if abs(x) >= 1e12:
        return f"{x/1e12:.2f}万亿"
    return f"{x/1e8:.0f}亿"


def make_markdown(snapshot: dict) -> str:
    meta = snapshot["meta"]
    market = snapshot["market"]
    sectors = snapshot["sectors"]
    lines = [
        f"# A股{'午盘' if meta['session']=='noon' else '14:40前'}报告",
        "",
        f"- 生成时间：{meta['generated_at']}",
        f"- Session：`{meta['session']}`",
        f"- 交易日判断来源：{meta.get('calendar_source')}",
        "",
        "## 1. 主要指数",
        "",
        "| 指数 | 点位 | 涨跌幅 |",
        "|---|---:|---:|",
    ]
    for x in market.get("indices", []):
        price = "—" if x.get("price") is None else f"{x['price']:.2f}"
        lines.append(f"| {x['name']} | {price} | {_pct(x.get('pct'))} |")

    b = market.get("breadth", {})
    t = market.get("turnover", {})
    lines += [
        "",
        "## 2. 市场广度与量能",
        "",
        f"- 上涨：**{b.get('up','—')}** 家；下跌：**{b.get('down','—')}** 家；平盘：{b.get('flat','—')} 家",
        f"- 全A累计成交额：**{_money(t.get('current'))}**",
        f"- 上一交易日同周期：{_money(t.get('previous_same_session'))}",
        f"- 同比变化：{_pct(t.get('change_pct')) if t.get('change_pct') is not None else '—'}",
        f"- 量能判断：**{t.get('label','—')}**",
    ]

    ls = market.get("limit_stats", {})
    lines += [
        f"- 涨停：{ls.get('limit_up','—')}；跌停：{ls.get('limit_down','—')}；炸板：{ls.get('broken','—')}",
        "",
        "## 3. 行业资金/涨跌 TOP",
        "",
    ]
    for title, key in [("涨幅前列", "top_gain"), ("主力净流入前列", "top_main_inflow")]:
        lines.append(f"### {title}")
        rows = sectors.get("industry", {}).get(key, [])[:8]
        if not rows:
            lines.append("- 数据暂缺")
        for r in rows:
            lines.append(f"- {r['name']}：涨跌 {_pct(r.get('pct'))}；主力 {_yi(r.get('main_net'))}")

    lines += ["", "## 4. 概念资金/涨跌 TOP", ""]
    for title, key in [("涨幅前列", "top_gain"), ("主力净流入前列", "top_main_inflow")]:
        lines.append(f"### {title}")
        rows = sectors.get("concept", {}).get(key, [])[:8]
        if not rows:
            lines.append("- 数据暂缺")
        for r in rows:
            lines.append(f"- {r['name']}：涨跌 {_pct(r.get('pct'))}；主力 {_yi(r.get('main_net'))}")

    lines += ["", "## 5. 持仓分析", ""]
    pf = snapshot.get("portfolio", [])
    if not pf:
        lines.append("> `config/portfolio.json` 目前为空。把最新持仓填进去后，这里会自动按你的持仓输出。")
    for x in pf:
        lines += [
            f"### {x.get('name')}",
            f"- 强弱：**{x.get('strength')}**（规则分 {x.get('score')}）",
            f"- 对应主题均值：{_pct(x.get('theme_avg_pct'))}",
            f"- 匹配板块主力资金合计：{_yi(x.get('matched_main_flow_sum'))}",
        ]
        if x.get("risk_alert"):
            lines.append(f"- 风控：**{x['risk_alert']}**")
        if x.get("reasons"):
            lines.append("- 依据：" + "；".join(x["reasons"]))
        lines.append(f"- 条件化参考：{x.get('action_reference')}")

    errors = meta.get("errors") or []
    if errors:
        lines += ["", "## 6. 数据异常记录", ""]
        for e in errors:
            lines.append(f"- {e}")

    lines += [
        "",
        "---",
        "素材仅为个人学习成长，不构成投资建议。",
    ]
    return "\n".join(lines) + "\n"
