"""Unit tests for Kelly Criterion Position Sizing (Oracle3 adaptation).

Tests cover:
- Basic Kelly formula: K = W - (1-W)/R
- Fractional Kelly (quarter, half, full)
- Edge cases: no trades, all wins, all losses
- Min/max caps
- Per-symbol vs global statistics
- Persistence (save/load)
- Integration helper function

Run: python -m pytest testing/test_kelly_sizing.py -v
  Or: python testing/test_kelly_sizing.py
"""

import os
import sys
import json
import tempfile

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.oracle3_kelly import (
    KellySizer,
    KellyStats,
    TradeRecord,
    calculate_kelly_risk_amount,
)


def test_kelly_formula_basic():
    """Test: W=0.55, R=1.5 -> kelly = 0.55 - 0.45/1.5 = 0.25"""
    sizer = KellySizer(
        fraction=1.0,  # Full Kelly for formula verification
        min_trades=5,
        max_risk_percent=1.0,  # No cap for test
        min_risk_percent=0.0,
        lookback_trades=200,  # Large enough to hold all trades
        enable_persistence=False,
    )

    # Record 55% win rate with 1.5 R:R — interleaved to avoid lookback issues
    import random
    random.seed(42)
    trades = [True] * 55 + [False] * 45
    random.shuffle(trades)
    for is_win in trades:
        if is_win:
            sizer.record_trade(pnl=150.0, risk_amount=100.0, symbol='TEST')
        else:
            sizer.record_trade(pnl=-100.0, risk_amount=100.0, symbol='TEST')

    stats = sizer.compute_stats()

    assert abs(stats.win_rate - 0.55) < 0.02, f"Expected WR~0.55, got {stats.win_rate}"
    assert abs(stats.rr_ratio - 1.5) < 0.05, f"Expected R:R~1.5, got {stats.rr_ratio}"
    # Kelly = 0.55 - 0.45/1.5 = 0.55 - 0.30 = 0.25
    assert abs(stats.raw_kelly - 0.25) < 0.05, f"Expected Kelly~0.25, got {stats.raw_kelly}"
    assert stats.has_edge is True
    print(f"[OK] Basic Kelly formula: W={stats.win_rate:.2f}, R:R={stats.rr_ratio:.2f}, K={stats.raw_kelly:.3f}")


def test_kelly_formula_negative_edge():
    """Test: W=0.40, R=0.8 -> kelly = 0.40 - 0.60/0.8 = -0.35 (no edge)"""
    sizer = KellySizer(
        fraction=1.0,
        min_trades=5,
        lookback_trades=200,
        enable_persistence=False,
    )

    import random
    random.seed(99)
    trades = [True] * 40 + [False] * 60
    random.shuffle(trades)
    for is_win in trades:
        if is_win:
            sizer.record_trade(pnl=80.0, risk_amount=100.0, symbol='TEST')
        else:
            sizer.record_trade(pnl=-100.0, risk_amount=100.0, symbol='TEST')

    stats = sizer.compute_stats()

    assert stats.raw_kelly < 0, f"Expected negative Kelly, got {stats.raw_kelly}"
    assert stats.has_edge is False
    # Should use minimum risk when no edge
    assert stats.final_risk_pct == sizer.min_risk_percent
    print(f"[OK] Negative edge: K={stats.raw_kelly:.3f}, using min risk={stats.final_risk_pct*100:.1f}%")


def test_fractional_kelly():
    """Test quarter-Kelly reduces risk by 75%."""
    # Full Kelly sizer
    full = KellySizer(fraction=1.0, min_trades=5, max_risk_percent=1.0,
                      min_risk_percent=0.0, enable_persistence=False)
    # Quarter Kelly sizer
    quarter = KellySizer(fraction=0.25, min_trades=5, max_risk_percent=1.0,
                         min_risk_percent=0.0, enable_persistence=False)

    # Same trade data
    for s in [full, quarter]:
        for _ in range(60):
            s.record_trade(pnl=200.0, risk_amount=100.0)
        for _ in range(40):
            s.record_trade(pnl=-100.0, risk_amount=100.0)

    full_stats = full.compute_stats()
    quarter_stats = quarter.compute_stats()

    assert abs(quarter_stats.fractional_kelly - full_stats.raw_kelly * 0.25) < 0.001
    print(f"[OK] Fractional Kelly: Full={full_stats.raw_kelly*100:.1f}%, "
          f"Quarter={quarter_stats.fractional_kelly*100:.2f}%")


def test_max_cap():
    """Test that risk never exceeds max_risk_percent."""
    sizer = KellySizer(
        fraction=0.5,
        min_trades=5,
        max_risk_percent=0.03,  # 3% cap
        enable_persistence=False,
    )

    # Very high win rate → large Kelly
    for _ in range(90):
        sizer.record_trade(pnl=300.0, risk_amount=100.0)
    for _ in range(10):
        sizer.record_trade(pnl=-100.0, risk_amount=100.0)

    stats = sizer.compute_stats()

    assert stats.raw_kelly > 0.03, "Raw Kelly should exceed 3% for this test"
    assert stats.final_risk_pct <= 0.03, f"Final risk {stats.final_risk_pct} exceeds cap 0.03"
    print(f"[OK] Max cap: Raw Kelly={stats.raw_kelly*100:.1f}%, capped at {stats.final_risk_pct*100:.1f}%")


def test_min_floor():
    """Test that risk never goes below min_risk_percent."""
    sizer = KellySizer(
        fraction=0.25,
        min_trades=5,
        min_risk_percent=0.005,  # 0.5% floor
        enable_persistence=False,
    )

    # Barely positive edge → very small Kelly
    for _ in range(52):
        sizer.record_trade(pnl=105.0, risk_amount=100.0)
    for _ in range(48):
        sizer.record_trade(pnl=-100.0, risk_amount=100.0)

    stats = sizer.compute_stats()

    assert stats.final_risk_pct >= 0.005, f"Final risk {stats.final_risk_pct} below floor 0.005"
    print(f"[OK] Min floor: Kelly={stats.raw_kelly*100:.2f}%, "
          f"quarter={stats.fractional_kelly*100:.3f}%, floor at {stats.final_risk_pct*100:.2f}%")


def test_fallback_mode():
    """Test fallback to fixed risk when not enough trades."""
    sizer = KellySizer(
        min_trades=20,
        fallback_risk=0.01,
        enable_persistence=False,
    )

    # Only 5 trades (below min_trades=20)
    for _ in range(5):
        sizer.record_trade(pnl=200.0, risk_amount=100.0)

    stats = sizer.compute_stats()

    assert stats.using_fallback is True
    assert stats.final_risk_pct == 0.01
    assert stats.confidence == 'low'
    print(f"[OK] Fallback mode: {stats.total_trades} trades < {sizer.min_trades} -> "
          f"fixed {stats.final_risk_pct*100:.1f}%")


def test_per_symbol_stats():
    """Test per-symbol differentiated sizing."""
    sizer = KellySizer(min_trades=5, fraction=0.5, max_risk_percent=1.0,
                       min_risk_percent=0.0, enable_persistence=False)

    # XAUUSD: high win rate
    for _ in range(70):
        sizer.record_trade(pnl=200.0, risk_amount=100.0, symbol='XAUUSD')
    for _ in range(30):
        sizer.record_trade(pnl=-100.0, risk_amount=100.0, symbol='XAUUSD')

    # EURUSD: low win rate
    for _ in range(40):
        sizer.record_trade(pnl=120.0, risk_amount=100.0, symbol='EURUSD')
    for _ in range(60):
        sizer.record_trade(pnl=-100.0, risk_amount=100.0, symbol='EURUSD')

    gold_risk = sizer.get_risk_percent(symbol='XAUUSD')
    euro_risk = sizer.get_risk_percent(symbol='EURUSD')

    assert gold_risk > euro_risk, \
        f"XAUUSD ({gold_risk:.3f}) should have higher risk than EURUSD ({euro_risk:.3f})"
    print(f"[OK] Per-symbol: XAUUSD risk={gold_risk*100:.2f}%, EURUSD risk={euro_risk*100:.2f}%")


def test_persistence():
    """Test save/load trade history."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        tmp_path = f.name

    try:
        # Create sizer and record trades
        sizer1 = KellySizer(
            min_trades=5,
            history_file=tmp_path,
            enable_persistence=True,
        )
        for _ in range(10):
            sizer1.record_trade(pnl=150.0, risk_amount=100.0, symbol='TEST')
        for _ in range(5):
            sizer1.record_trade(pnl=-80.0, risk_amount=80.0, symbol='TEST')

        stats1 = sizer1.compute_stats()

        # Create new sizer loading from same file
        sizer2 = KellySizer(
            min_trades=5,
            history_file=tmp_path,
            enable_persistence=True,
        )

        stats2 = sizer2.compute_stats()

        assert stats2.total_trades == stats1.total_trades, \
            f"Loaded {stats2.total_trades} trades, expected {stats1.total_trades}"
        assert abs(stats2.win_rate - stats1.win_rate) < 0.001

        print(f"[OK] Persistence: Saved {stats1.total_trades} trades, "
              f"loaded {stats2.total_trades} with WR={stats2.win_rate:.2f}")

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def test_empty_history():
    """Test behavior with zero trades."""
    sizer = KellySizer(enable_persistence=False)
    stats = sizer.compute_stats()

    assert stats.total_trades == 0
    assert stats.using_fallback is True
    assert stats.final_risk_pct == sizer.fallback_risk
    print(f"[OK] Empty history: fallback to {stats.final_risk_pct*100:.1f}%")


def test_all_wins():
    """Test behavior when ALL trades are winners."""
    sizer = KellySizer(min_trades=5, fraction=0.25, max_risk_percent=0.03,
                       enable_persistence=False)

    for _ in range(20):
        sizer.record_trade(pnl=200.0, risk_amount=100.0)

    stats = sizer.compute_stats()

    assert stats.win_rate == 1.0
    # When WR=1.0 and no losses, avg_loss defaults to 1.0
    # Kelly = 1.0 - 0.0/R = 1.0 (always bet everything)
    # But capped at max_risk_percent
    assert stats.final_risk_pct <= sizer.max_risk_percent
    print(f"[OK] All wins: Kelly={stats.raw_kelly*100:.1f}%, capped at {stats.final_risk_pct*100:.1f}%")


def test_all_losses():
    """Test behavior when ALL trades are losers."""
    sizer = KellySizer(min_trades=5, enable_persistence=False)

    for _ in range(20):
        sizer.record_trade(pnl=-100.0, risk_amount=100.0)

    stats = sizer.compute_stats()

    assert stats.win_rate == 0.0
    assert stats.has_edge is False
    assert stats.final_risk_pct == sizer.min_risk_percent
    print(f"[OK] All losses: Kelly={stats.raw_kelly*100:.1f}%, using min risk={stats.final_risk_pct*100:.1f}%")


def test_calculate_kelly_risk_amount():
    """Test the GUI integration helper function."""
    sizer = KellySizer(
        min_trades=5,
        fraction=0.25,
        max_risk_percent=0.03,
        enable_persistence=False,
    )

    # Record some trades to get past fallback mode
    for _ in range(30):
        sizer.record_trade(pnl=150.0, risk_amount=100.0, symbol='XAUUSD')
    for _ in range(20):
        sizer.record_trade(pnl=-100.0, risk_amount=100.0, symbol='XAUUSD')

    # Calculate risk for $50,000 balance, 15% XAUUSD allocation
    risk_amount, risk_percent, summary = calculate_kelly_risk_amount(
        kelly_sizer=sizer,
        balance=50000.0,
        allocation_percent=0.15,
        symbol='XAUUSD',
    )

    allocated = 50000.0 * 0.15  # $7,500
    expected_risk = allocated * risk_percent

    assert abs(risk_amount - expected_risk) < 0.01
    assert risk_percent > 0
    assert len(summary) > 0
    print(f"[OK] Integration: Balance=$50K, XAUUSD 15% allocation -> "
          f"risk_pct={risk_percent*100:.2f}%, risk_amount=${risk_amount:.2f}")
    print(f"   Summary: {summary}")


def test_confidence_levels():
    """Test confidence level calculation."""
    sizer = KellySizer(min_trades=5, enable_persistence=False)

    # 10 trades → low confidence
    for _ in range(10):
        sizer.record_trade(pnl=100.0, risk_amount=100.0)
    assert sizer.compute_stats().confidence == 'low'

    # 35 trades → medium confidence
    for _ in range(25):
        sizer.record_trade(pnl=100.0, risk_amount=100.0)
    assert sizer.compute_stats().confidence == 'medium'

    # 55 trades → high confidence
    for _ in range(20):
        sizer.record_trade(pnl=100.0, risk_amount=100.0)
    assert sizer.compute_stats().confidence == 'high'

    print("[OK] Confidence levels: low -> medium -> high progression verified")


def test_reset():
    """Test reset functionality."""
    sizer = KellySizer(min_trades=5, enable_persistence=False)

    for _ in range(10):
        sizer.record_trade(pnl=100.0, risk_amount=100.0, symbol='XAUUSD')
    for _ in range(5):
        sizer.record_trade(pnl=100.0, risk_amount=100.0, symbol='EURUSD')

    # Reset single symbol
    sizer.reset(symbol='XAUUSD')
    assert sizer.get_trade_count(symbol='XAUUSD') == 0
    assert sizer.get_trade_count(symbol='EURUSD') == 5

    # Reset all
    sizer.reset()
    assert sizer.get_trade_count() == 0
    print("[OK] Reset: per-symbol and global reset working")


def test_summary_output():
    """Test that get_summary returns readable strings."""
    sizer = KellySizer(min_trades=5, enable_persistence=False)

    # Fallback mode
    summary = sizer.get_summary()
    assert 'FALLBACK' in summary

    # After enough trades
    for _ in range(30):
        sizer.record_trade(pnl=150.0, risk_amount=100.0)
    for _ in range(20):
        sizer.record_trade(pnl=-100.0, risk_amount=100.0)

    summary = sizer.get_summary()
    assert 'EDGE' in summary
    assert 'WinRate' in summary
    assert 'R:R' in summary
    print(f"[OK] Summary output:")
    print(f"   Fallback: Kelly [ALL]: FALLBACK MODE...")
    print(f"   Active:   {summary}")


# =============================================================
# Main runner
# =============================================================

if __name__ == '__main__':
    print("=" * 70)
    print("  KELLY CRITERION POSITION SIZING - UNIT TESTS")
    print("  Adapted from Oracle3 greeks.py -> Forex MT5")
    print("=" * 70)
    print()

    tests = [
        test_kelly_formula_basic,
        test_kelly_formula_negative_edge,
        test_fractional_kelly,
        test_max_cap,
        test_min_floor,
        test_fallback_mode,
        test_per_symbol_stats,
        test_persistence,
        test_empty_history,
        test_all_wins,
        test_all_losses,
        test_calculate_kelly_risk_amount,
        test_confidence_levels,
        test_reset,
        test_summary_output,
    ]

    passed = 0
    failed = 0

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"[FAIL] {test_fn.__name__}: {e}")

    print()
    print("=" * 70)
    print(f"  RESULTS: {passed} passed, {failed} failed, {len(tests)} total")
    print("=" * 70)

    if failed > 0:
        sys.exit(1)
