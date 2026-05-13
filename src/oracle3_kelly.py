"""Kelly Criterion Position Sizing — Adapted from Oracle3 greeks.py

Replaces fixed 1% risk per trade with mathematically optimal position sizing
based on actual trading performance (win rate and risk-reward ratio).

Oracle3 Origin:
    oracle3/pricing/greeks.py → kelly_fraction()
    Adapted from binary prediction markets to continuous Forex markets.

Key Differences from Oracle3:
    - Oracle3 uses binary outcomes (p_star vs p_market) for prediction markets.
    - This module uses empirical win rate + R:R ratio from trade history.
    - Same fractional Kelly concept (quarter/half Kelly for safety).

Usage:
    from src.oracle3_kelly import KellySizer

    sizer = KellySizer(fraction=0.25, min_trades=20)
    sizer.record_trade(pnl=150.0, risk=100.0)   # Won $150 risking $100
    sizer.record_trade(pnl=-80.0, risk=80.0)     # Lost $80 risking $80

    risk_pct = sizer.get_risk_percent()  # Dynamic risk% based on edge
"""

from __future__ import annotations

import json
import logging
import os
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# =============================================================
# CONFIGURATION
# =============================================================

# Default Kelly parameters
DEFAULT_KELLY_FRACTION = 0.25        # Quarter-Kelly (very conservative)
DEFAULT_MIN_TRADES = 20              # Minimum trades before switching to Kelly
DEFAULT_MAX_RISK_PERCENT = 0.03      # Maximum 3% risk per trade (hard cap)
DEFAULT_MIN_RISK_PERCENT = 0.005     # Minimum 0.5% risk per trade (floor)
DEFAULT_FALLBACK_RISK = 0.01         # Fixed 1% while insufficient data
DEFAULT_LOOKBACK_TRADES = 50         # Rolling window for statistics
DEFAULT_TRADE_HISTORY_FILE = 'kelly_trade_history.json'


# =============================================================
# DATA STRUCTURES
# =============================================================

@dataclass
class TradeRecord:
    """Record of a completed trade for Kelly calculation."""
    symbol: str
    direction: str              # 'LONG' or 'SHORT'
    pnl: float                  # Profit/loss in account currency
    risk_amount: float          # Amount risked (in account currency)
    entry_price: float = 0.0
    exit_price: float = 0.0
    timestamp: str = ''
    is_win: bool = False

    def __post_init__(self):
        self.is_win = self.pnl > 0
        if not self.timestamp:
            self.timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')


@dataclass
class KellyStats:
    """Computed Kelly statistics."""
    win_rate: float = 0.0           # W: probability of winning (0.0 → 1.0)
    avg_win: float = 0.0           # Average winning trade ($)
    avg_loss: float = 0.0          # Average losing trade ($, positive)
    rr_ratio: float = 0.0          # R:R = avg_win / avg_loss
    raw_kelly: float = 0.0         # Full Kelly percentage
    fractional_kelly: float = 0.0  # After applying fraction
    final_risk_pct: float = 0.01   # After applying min/max caps
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    has_edge: bool = False         # True if Kelly > 0 (positive expectancy)
    using_fallback: bool = True    # True if not enough data for Kelly
    confidence: str = 'low'        # 'low', 'medium', 'high'


# =============================================================
# KELLY SIZER — MAIN CLASS
# =============================================================

class KellySizer:
    """Kelly Criterion position sizer adapted from Oracle3.

    Calculates optimal risk percentage based on empirical trading performance.

    Formula:
        kelly% = W - (1 - W) / R

        W = win rate (0.0 → 1.0)
        R = avg_win / avg_loss (reward-to-risk ratio)

    Safety features:
        - Fractional Kelly (default 25%) to reduce variance
        - Min/Max risk caps to prevent extreme sizing
        - Fallback to fixed 1% when insufficient trade history
        - Per-symbol statistics for differentiated sizing
        - Persistent trade history (JSON file)

    Example:
        W = 0.55 (55% win rate), R = 1.5 (avg win 1.5x avg loss)
        kelly = 0.55 - 0.45/1.5 = 0.55 - 0.30 = 0.25 (25%)
        quarter_kelly = 0.25 * 0.25 = 0.0625 (6.25%)
        capped = min(0.0625, 0.03) = 0.03 (3% — hit max cap)
    """

    def __init__(
        self,
        fraction: float = DEFAULT_KELLY_FRACTION,
        min_trades: int = DEFAULT_MIN_TRADES,
        max_risk_percent: float = DEFAULT_MAX_RISK_PERCENT,
        min_risk_percent: float = DEFAULT_MIN_RISK_PERCENT,
        fallback_risk: float = DEFAULT_FALLBACK_RISK,
        lookback_trades: int = DEFAULT_LOOKBACK_TRADES,
        history_file: str = DEFAULT_TRADE_HISTORY_FILE,
        enable_persistence: bool = True,
    ):
        """
        Parameters
        ----------
        fraction:
            Fractional Kelly multiplier. 0.25 = quarter-Kelly (safest),
            0.5 = half-Kelly, 1.0 = full Kelly (dangerous).
        min_trades:
            Minimum number of completed trades before switching from
            fallback to Kelly-based sizing.
        max_risk_percent:
            Hard cap on risk percentage (0.03 = 3%).
        min_risk_percent:
            Floor for risk percentage (0.005 = 0.5%).
        fallback_risk:
            Fixed risk percentage used when trade count < min_trades.
        lookback_trades:
            Number of most recent trades to use for statistics.
        history_file:
            Path to JSON file for persisting trade history.
        enable_persistence:
            If True, save/load trade history to/from disk.
        """
        self.fraction = fraction
        self.min_trades = min_trades
        self.max_risk_percent = max_risk_percent
        self.min_risk_percent = min_risk_percent
        self.fallback_risk = fallback_risk
        self.lookback_trades = lookback_trades
        self.history_file = history_file
        self.enable_persistence = enable_persistence

        # Trade history — deque for efficient rolling window
        self._trades: deque[TradeRecord] = deque(maxlen=lookback_trades * 2)

        # Per-symbol trade history for differentiated sizing
        self._symbol_trades: dict[str, deque[TradeRecord]] = {}

        # Load persisted history
        if enable_persistence:
            self._load_history()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_trade(
        self,
        pnl: float,
        risk_amount: float,
        symbol: str = 'ALL',
        direction: str = 'LONG',
        entry_price: float = 0.0,
        exit_price: float = 0.0,
    ) -> TradeRecord:
        """Record a completed trade for Kelly statistics.

        Call this after every trade closes (win or loss).

        Args:
            pnl: Profit/loss in account currency (positive=win, negative=loss)
            risk_amount: Amount that was risked on this trade
            symbol: Trading symbol (e.g., 'XAUUSD')
            direction: 'LONG' or 'SHORT'
            entry_price: Entry price (for logging)
            exit_price: Exit price (for logging)

        Returns:
            The created TradeRecord.
        """
        record = TradeRecord(
            symbol=symbol,
            direction=direction,
            pnl=pnl,
            risk_amount=risk_amount,
            entry_price=entry_price,
            exit_price=exit_price,
        )

        # Add to global history
        self._trades.append(record)

        # Add to per-symbol history
        if symbol not in self._symbol_trades:
            self._symbol_trades[symbol] = deque(maxlen=self.lookback_trades)
        self._symbol_trades[symbol].append(record)

        # Persist
        if self.enable_persistence:
            self._save_history()

        logger.info(
            'Kelly: Recorded %s trade on %s | PnL=$%.2f | Risk=$%.2f | %s',
            direction, symbol, pnl, risk_amount,
            'WIN' if record.is_win else 'LOSS',
        )

        return record

    def get_risk_percent(self, symbol: Optional[str] = None) -> float:
        """Get the optimal risk percentage for the next trade.

        Args:
            symbol: If provided, uses per-symbol statistics.
                    If None, uses global (all symbols) statistics.

        Returns:
            Risk percentage as a decimal (e.g., 0.015 = 1.5%).
        """
        stats = self.compute_stats(symbol)
        return stats.final_risk_pct

    def compute_stats(self, symbol: Optional[str] = None) -> KellyStats:
        """Compute full Kelly statistics.

        Args:
            symbol: If provided, compute for specific symbol only.

        Returns:
            KellyStats with all computed values.
        """
        # Select trade pool
        if symbol and symbol in self._symbol_trades:
            trades = list(self._symbol_trades[symbol])[-self.lookback_trades:]
        else:
            trades = list(self._trades)[-self.lookback_trades:]

        stats = KellyStats()
        stats.total_trades = len(trades)

        # Not enough data → fallback
        if stats.total_trades < self.min_trades:
            stats.using_fallback = True
            stats.final_risk_pct = self.fallback_risk
            stats.confidence = 'low'
            return stats

        # Separate wins and losses
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]

        stats.winning_trades = len(wins)
        stats.losing_trades = len(losses)
        stats.win_rate = len(wins) / len(trades) if trades else 0.0

        # Calculate averages
        stats.avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0.0
        stats.avg_loss = abs(sum(t.pnl for t in losses) / len(losses)) if losses else 1.0

        # Risk-Reward ratio
        stats.rr_ratio = stats.avg_win / stats.avg_loss if stats.avg_loss > 0 else 0.0

        # Kelly formula: K = W - (1-W)/R
        if stats.rr_ratio > 0:
            stats.raw_kelly = stats.win_rate - (1.0 - stats.win_rate) / stats.rr_ratio
        else:
            stats.raw_kelly = 0.0

        stats.has_edge = stats.raw_kelly > 0

        # Fractional Kelly
        stats.fractional_kelly = stats.raw_kelly * self.fraction

        # Apply min/max caps
        if stats.has_edge:
            stats.final_risk_pct = max(
                self.min_risk_percent,
                min(stats.fractional_kelly, self.max_risk_percent),
            )
        else:
            # Negative Kelly → use minimum risk (still trade but small)
            stats.final_risk_pct = self.min_risk_percent

        stats.using_fallback = False

        # Confidence level based on sample size
        if stats.total_trades >= 50:
            stats.confidence = 'high'
        elif stats.total_trades >= 30:
            stats.confidence = 'medium'
        else:
            stats.confidence = 'low'

        return stats

    def get_summary(self, symbol: Optional[str] = None) -> str:
        """Get a human-readable summary of Kelly statistics.

        Useful for GUI terminal display.
        """
        stats = self.compute_stats(symbol)
        label = f'[{symbol}]' if symbol else '[ALL]'

        if stats.using_fallback:
            return (
                f'Kelly {label}: FALLBACK MODE | '
                f'Trades: {stats.total_trades}/{self.min_trades} needed | '
                f'Using fixed {stats.final_risk_pct*100:.1f}% risk'
            )

        edge_status = 'POSITIVE' if stats.has_edge else 'NEGATIVE'
        return (
            f'Kelly {label}: {edge_status} EDGE | '
            f'WinRate: {stats.win_rate*100:.1f}% | '
            f'R:R: {stats.rr_ratio:.2f} | '
            f'Raw Kelly: {stats.raw_kelly*100:.1f}% | '
            f'{self.fraction:.0%} Kelly: {stats.fractional_kelly*100:.2f}% | '
            f'Final Risk: {stats.final_risk_pct*100:.2f}% | '
            f'Trades: {stats.total_trades} ({stats.confidence} confidence)'
        )

    def get_trade_count(self, symbol: Optional[str] = None) -> int:
        """Get number of recorded trades."""
        if symbol and symbol in self._symbol_trades:
            return len(self._symbol_trades[symbol])
        return len(self._trades)

    def reset(self, symbol: Optional[str] = None) -> None:
        """Reset trade history.

        Args:
            symbol: If provided, reset only that symbol's history.
                    If None, reset all history.
        """
        if symbol:
            if symbol in self._symbol_trades:
                self._symbol_trades[symbol].clear()
            logger.info('Kelly: Reset history for %s', symbol)
        else:
            self._trades.clear()
            self._symbol_trades.clear()
            logger.info('Kelly: Reset ALL trade history')

        if self.enable_persistence:
            self._save_history()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_history(self) -> None:
        """Save trade history to JSON file."""
        try:
            data = {
                'version': '1.0',
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'config': {
                    'fraction': self.fraction,
                    'min_trades': self.min_trades,
                    'max_risk_percent': self.max_risk_percent,
                    'min_risk_percent': self.min_risk_percent,
                    'fallback_risk': self.fallback_risk,
                    'lookback_trades': self.lookback_trades,
                },
                'trades': [
                    {
                        'symbol': t.symbol,
                        'direction': t.direction,
                        'pnl': t.pnl,
                        'risk_amount': t.risk_amount,
                        'entry_price': t.entry_price,
                        'exit_price': t.exit_price,
                        'timestamp': t.timestamp,
                        'is_win': t.is_win,
                    }
                    for t in self._trades
                ],
            }

            # Atomic write (temp + rename)
            tmp_file = self.history_file + '.tmp'
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_file, self.history_file)

        except Exception as e:
            logger.warning('Kelly: Failed to save history: %s', e)

    def _load_history(self) -> None:
        """Load trade history from JSON file."""
        if not os.path.exists(self.history_file):
            return

        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            trades_data = data.get('trades', [])
            for td in trades_data:
                record = TradeRecord(
                    symbol=td.get('symbol', 'UNKNOWN'),
                    direction=td.get('direction', 'LONG'),
                    pnl=td.get('pnl', 0.0),
                    risk_amount=td.get('risk_amount', 0.0),
                    entry_price=td.get('entry_price', 0.0),
                    exit_price=td.get('exit_price', 0.0),
                    timestamp=td.get('timestamp', ''),
                )
                self._trades.append(record)

                # Rebuild per-symbol history
                sym = record.symbol
                if sym not in self._symbol_trades:
                    self._symbol_trades[sym] = deque(maxlen=self.lookback_trades)
                self._symbol_trades[sym].append(record)

            logger.info(
                'Kelly: Loaded %d trades from %s', len(trades_data), self.history_file
            )

        except Exception as e:
            logger.warning('Kelly: Failed to load history: %s', e)


# =============================================================
# CONVENIENCE FUNCTION FOR GUI INTEGRATION
# =============================================================

def calculate_kelly_risk_amount(
    kelly_sizer: KellySizer,
    balance: float,
    allocation_percent: float,
    symbol: str,
    default_risk_percent: float = 0.01,
) -> tuple[float, float, str]:
    """Calculate risk amount using Kelly Criterion.

    Drop-in replacement for the fixed risk calculation in execute_trade().

    Args:
        kelly_sizer: KellySizer instance
        balance: Account balance
        allocation_percent: Dalio allocation for this symbol (0.0 → 1.0)
        symbol: Trading symbol
        default_risk_percent: Fallback risk if Kelly not available

    Returns:
        (risk_amount, risk_percent, summary_text)
    """
    allocated_capital = balance * allocation_percent

    # Get Kelly-optimal risk percentage
    risk_percent = kelly_sizer.get_risk_percent(symbol=symbol)
    risk_amount = allocated_capital * risk_percent

    # Generate summary for terminal logging
    summary = kelly_sizer.get_summary(symbol=symbol)

    return risk_amount, risk_percent, summary
