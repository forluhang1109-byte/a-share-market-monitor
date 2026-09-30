import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from a_share_monitor.analytics import build_breadth, volume_compare, analyze_portfolio


def test_breadth():
    stocks = [
        {"pct": 1, "amount": 100},
        {"pct": -1, "amount": 200},
        {"pct": 0, "amount": 300},
    ]
    out = build_breadth(stocks)
    assert out["up"] == 1
    assert out["down"] == 1
    assert out["flat"] == 1


def test_volume_compare():
    out = volume_compare(110, 100, 1.05, 0.95)
    assert out["label"] == "放量"
    assert round(out["change_pct"], 1) == 10.0


def test_portfolio_rule():
    pf = [{"name": "X", "themes": ["半导体"], "cost_return_pct": -2}]
    industry = [{"name": "半导体", "pct": 2.0, "main_net": 1e9}]
    out = analyze_portfolio(
        pf, industry, [], [{"pct": 0.6}], {"ratio": 1.1}, -15
    )
    assert out[0]["strength"] == "偏强"
    assert "主力资金" in "；".join(out[0]["reasons"])


if __name__ == "__main__":
    test_breadth()
    test_volume_compare()
    test_portfolio_rule()
    print("tests passed")
