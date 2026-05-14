#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gold (XAUUSD) Trading Enhancements Module
==========================================
Optimizations specific to XAUUSD trading:
1. Session/Killzone Filter (London + NY sessions)
2. Spread Protection (real-time spread check)
3. Multi-Timeframe (MTF) Trend Alignment (H1/H4)
4. RSI Divergence Filter (anti-fakeout)
5. Trailing Stop & Partial Close
6. Fast-path tick polling for WINDOW_OPEN state

All functions are designed to be called from advanced_mt5_monitor_gui.py
without modifying the core state machine structure.
"""

import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

# Lazy imports for MT5 and numpy (may not be available in all environments)
try:
    import MetaTrader5 as mt5
    import numpy as np
    import pandas as pd
except ImportError:
    mt5 = None
    np = None
    pd = None


# ==========================================================================
# GOLD-SPECIFIC CONSTANTS
# ==========================================================================

# 24/5 Trading Session (All day, every day the market is open)
# Market is natively closed on Saturday/Sunday by MT5 server.
GOLD_KILLZONES_VN = [
    {'name': '24/5 Session', 'start_h': 0, 'start_m': 0, 'end_h': 23, 'end_m': 59},
]

# Maximum allowed spread for XAUUSD (in points, i.e. $0.01 units)
# Normal spread: 20-50 points ($0.20-$0.50)
# News spike: can exceed 300 points ($3.00)
MAX_ALLOWED_SPREAD_GOLD_POINTS = 80  # $0.80 max spread

# RSI settings for divergence detection
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

# ==========================================================================
# TP SPLITTING CONFIG (per trading_strategy.md spec)
# ==========================================================================
# Split TP into 4 levels. At each level, close a percentage of volume.
# After TP1+TP2 hit (50% of volume closed), move SL to entry (breakeven).
#
# TP Level | Distance (% of total TP) | Volume to close (% of original)
# ---------|--------------------------|----------------------------------
# TP1      | 30%                      | 30%
# TP2      | 50%                      | 20%
# TP3      | 80%                      | 30%
# TP4      | 100%                     | 20% (remaining, handled by broker TP)
#
# Example: Entry=2000, TP=2020 (TP distance = 20)
#   TP1 = 2000 + 20*0.30 = 2006 → close 30% volume
#   TP2 = 2000 + 20*0.50 = 2010 → close 20% volume, move SL→entry
#   TP3 = 2000 + 20*0.80 = 2016 → close 30% volume
#   TP4 = 2000 + 20*1.00 = 2020 → remaining 20% hits broker TP
# ==========================================================================

TP_LEVELS = [
    {'name': 'TP1', 'distance_pct': 0.30, 'close_pct': 0.30},
    {'name': 'TP2', 'distance_pct': 0.50, 'close_pct': 0.20},
    {'name': 'TP3', 'distance_pct': 0.80, 'close_pct': 0.30},
    # TP4 is handled by the broker's native TP order (remaining 20%)
]

# Move SL to entry (breakeven) after this many TP levels are hit
SL_MOVE_AFTER_TP_LEVEL = 2  # Move SL to entry after TP2 hit (50% closed)

# ==========================================================================
# SCALING (NHỒI LỆNH) CONFIG (per trading_strategy.md spec)
# ==========================================================================
# Conditions:
#   1. TP1 + TP2 hit (>= 50% TP profit taken)
#   2. 75% H1 candle body confirmation (strong trend, no reversal)
# Max orders: 1 base + 3 scaling orders
# SL rule: Move SL of ALL previous orders to their entry price after scaling
# Flow:
#   Base → TP2 hit → Scale 1 → move SL base → entry
#   Scale 1 hits 50% TP → Scale 2 → move SL Scale1 → entry
#   Scale 2 hits 50% TP → Scale 3 → move SL Scale2 → entry
# ==========================================================================

MAX_SCALING_ORDERS = 3           # Maximum add-on orders
SCALING_TRIGGER_TP_LEVEL = 2     # Trigger scaling after this many TP levels hit (TP2)
SCALING_TRIGGER_TP_PCT = 0.50    # Scaling order triggers at 50% of its own TP
H1_CANDLE_BODY_MIN_PCT = 0.75   # H1 candle body must be >= 75% of range
SCALING_RISK_PERCENT = 0.01      # Same 1% risk per scaling order

# Fast polling interval when WINDOW_OPEN (milliseconds equivalent)
FAST_POLL_INTERVAL_SEC = 0.5  # 500ms tick polling

# Position monitoring interval
POSITION_MONITOR_INTERVAL_SEC = 2.0


# ==========================================================================
# 1. SESSION / KILLZONE FILTER
# ==========================================================================

def validate_gold_session(current_dt: datetime, broker_utc_offset: int = 1) -> Tuple[bool, str]:
    """Check if current time falls within Gold killzones (London/NY sessions).
    
    Gold is most tradeable during London and NY sessions. Asian session
    produces choppy, low-volume price action that generates false signals.
    
    Args:
        current_dt: Broker time (from MT5 data)
        broker_utc_offset: Broker's UTC offset (1 for UTC+1, 2 for UTC+2, etc.)
    
    Returns:
        (is_allowed, session_name): Tuple of bool and active session name
    """
    # Convert broker time to Vietnam time (UTC+7)
    utc_time = current_dt - timedelta(hours=broker_utc_offset)
    vn_time = utc_time + timedelta(hours=7)
    
    current_minutes = vn_time.hour * 60 + vn_time.minute
    
    for zone in GOLD_KILLZONES_VN:
        start_min = zone['start_h'] * 60 + zone['start_m']
        end_min = zone['end_h'] * 60 + zone['end_m']
        
        if start_min <= end_min:
            if start_min <= current_minutes <= end_min:
                return True, zone['name']
        else:
            # Overnight wrap
            if current_minutes >= start_min or current_minutes <= end_min:
                return True, zone['name']
    
    vn_time_str = vn_time.strftime('%H:%M')
    return False, f"Outside killzones (VN time: {vn_time_str})"


# ==========================================================================
# 2. SPREAD PROTECTION
# ==========================================================================

def check_gold_spread(symbol: str = "XAUUSD", max_spread_points: int = MAX_ALLOWED_SPREAD_GOLD_POINTS) -> Tuple[bool, float]:
    """Check if current spread is within acceptable range for XAUUSD.
    
    During high-impact news (NFP, CPI, FOMC), Gold spread can spike
    from 20 points to 300+ points. Trading during spread spikes
    results in immediate unrealized loss equal to the spread.
    
    Args:
        symbol: Trading symbol (default XAUUSD)
        max_spread_points: Maximum allowed spread in points
    
    Returns:
        (is_safe, current_spread_points): Tuple of bool and spread value
    """
    if mt5 is None:
        return True, 0.0
    
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return False, 999.0  # Can't get tick = unsafe
    
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return False, 999.0
    
    # Calculate spread in points
    spread_price = tick.ask - tick.bid
    spread_points = spread_price / symbol_info.point
    
    is_safe = spread_points <= max_spread_points
    return is_safe, spread_points


# ==========================================================================
# 3. MULTI-TIMEFRAME (MTF) TREND ALIGNMENT
# ==========================================================================

def check_higher_tf_trend(symbol: str = "XAUUSD", direction: str = "LONG") -> Tuple[bool, Dict]:
    """Check if H1 and H4 timeframes align with the intended trade direction.
    
    Gold follows strong multi-timeframe structure. Trading M5 signals
    against H1/H4 trend results in ~50% more false signals.
    
    Logic:
    - Calculate EMA(20) slope on H1 and H4
    - LONG: Both H1 and H4 EMA slopes must be positive (uptrend)
    - SHORT: Both H1 and H4 EMA slopes must be negative (downtrend)
    
    Args:
        symbol: Trading symbol
        direction: 'LONG' or 'SHORT'
    
    Returns:
        (is_aligned, details): Tuple of bool and diagnostic info
    """
    if mt5 is None or pd is None or np is None:
        return True, {'error': 'Dependencies not available'}
    
    details = {}
    ema_period = 20  # EMA period for trend detection
    slope_bars = 3   # Number of bars to measure slope
    
    for tf_name, tf_const in [('H1', mt5.TIMEFRAME_H1), ('H4', mt5.TIMEFRAME_H4)]:
        rates = mt5.copy_rates_from_pos(symbol, tf_const, 0, ema_period + slope_bars + 5)
        if rates is None or len(rates) < ema_period + slope_bars:
            details[tf_name] = {'error': 'Insufficient data'}
            return True, details  # Fail-safe: allow trade if data unavailable
        
        df = pd.DataFrame(rates)
        df['ema'] = df['close'].ewm(span=ema_period, adjust=False).mean()
        
        # Calculate slope: compare current EMA vs N bars ago
        current_ema = df['ema'].iloc[-1]
        prev_ema = df['ema'].iloc[-1 - slope_bars]
        slope = current_ema - prev_ema
        
        # Check 75% candle body confirmation on H1 (as per spec)
        last_candle = df.iloc[-2]  # Last closed candle
        body = abs(last_candle['close'] - last_candle['open'])
        total_range = last_candle['high'] - last_candle['low']
        body_ratio = body / total_range if total_range > 0 else 0
        
        is_bullish_body = last_candle['close'] > last_candle['open']
        
        details[tf_name] = {
            'ema': round(current_ema, 2),
            'slope': round(slope, 4),
            'body_ratio': round(body_ratio, 2),
            'is_bullish': is_bullish_body,
            'trend': 'UP' if slope > 0 else 'DOWN'
        }
    
    # Alignment check
    if direction == 'LONG':
        h1_ok = details.get('H1', {}).get('slope', 0) > 0
        h4_ok = details.get('H4', {}).get('slope', 0) > 0
        is_aligned = h1_ok and h4_ok
    else:  # SHORT
        h1_ok = details.get('H1', {}).get('slope', 0) < 0
        h4_ok = details.get('H4', {}).get('slope', 0) < 0
        is_aligned = h1_ok and h4_ok
    
    details['aligned'] = is_aligned
    details['h1_ok'] = h1_ok
    details['h4_ok'] = h4_ok
    
    return is_aligned, details


# ==========================================================================
# 4. RSI DIVERGENCE FILTER (Anti-Fakeout / Turtle Soup)
# ==========================================================================

def calculate_rsi(closes, period: int = RSI_PERIOD):
    """Calculate RSI from a series of close prices."""
    if np is None or pd is None:
        return None
    
    if len(closes) < period + 1:
        return None
    
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = pd.Series(gains).rolling(window=period).mean().iloc[-1]
    avg_loss = pd.Series(losses).rolling(window=period).mean().iloc[-1]
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def check_rsi_divergence(symbol: str = "XAUUSD", direction: str = "LONG", lookback: int = 20) -> Tuple[bool, Dict]:
    """Check for RSI divergence that would indicate a fakeout/bull trap.
    
    Fakeout detection:
    - LONG: If price makes new high but RSI makes lower high → bearish divergence → BLOCK
    - SHORT: If price makes new low but RSI makes higher low → bullish divergence → BLOCK
    
    Args:
        symbol: Trading symbol
        direction: 'LONG' or 'SHORT'
        lookback: Number of M15 bars to check for divergence
    
    Returns:
        (is_safe, details): True if NO divergence detected (safe to trade)
    """
    if mt5 is None or np is None or pd is None:
        return True, {'error': 'Dependencies not available'}
    
    # Use M15 for divergence (more reliable than M5)
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, lookback + RSI_PERIOD + 5)
    if rates is None or len(rates) < lookback + RSI_PERIOD:
        return True, {'error': 'Insufficient M15 data'}
    
    df = pd.DataFrame(rates)
    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    
    # Calculate RSI for each bar in lookback window
    rsi_values = []
    for i in range(RSI_PERIOD + 1, len(closes) + 1):
        rsi = calculate_rsi(closes[:i], RSI_PERIOD)
        rsi_values.append(rsi)
    
    if len(rsi_values) < lookback:
        return True, {'error': 'Insufficient RSI data'}
    
    rsi_recent = rsi_values[-lookback:]
    price_recent_high = highs[-lookback:]
    price_recent_low = lows[-lookback:]
    
    details = {
        'current_rsi': round(rsi_recent[-1], 1) if rsi_recent[-1] else 0,
        'divergence_detected': False
    }
    
    if direction == 'LONG':
        # Check bearish divergence: price higher high + RSI lower high
        price_max_idx = np.argmax(price_recent_high[-10:])  # Recent 10 bars
        price_prev_max_idx = np.argmax(price_recent_high[-20:-10]) if lookback >= 20 else 0
        
        if price_recent_high[-10:][price_max_idx] > price_recent_high[-20:-10][price_prev_max_idx] if lookback >= 20 else False:
            # Price made higher high, check RSI
            rsi_at_max = rsi_recent[-10:][price_max_idx] if price_max_idx < len(rsi_recent[-10:]) else None
            rsi_at_prev = rsi_recent[-20:-10][price_prev_max_idx] if price_prev_max_idx < len(rsi_recent[-20:-10]) else None
            
            if rsi_at_max is not None and rsi_at_prev is not None:
                if rsi_at_max < rsi_at_prev:
                    details['divergence_detected'] = True
                    details['type'] = 'BEARISH_DIVERGENCE'
                    details['msg'] = f'Price higher high but RSI lower ({rsi_at_max:.0f} < {rsi_at_prev:.0f})'
                    return False, details
    
    elif direction == 'SHORT':
        # Check bullish divergence: price lower low + RSI higher low
        price_min_idx = np.argmin(price_recent_low[-10:])
        price_prev_min_idx = np.argmin(price_recent_low[-20:-10]) if lookback >= 20 else 0
        
        if lookback >= 20 and price_recent_low[-10:][price_min_idx] < price_recent_low[-20:-10][price_prev_min_idx]:
            rsi_at_min = rsi_recent[-10:][price_min_idx] if price_min_idx < len(rsi_recent[-10:]) else None
            rsi_at_prev = rsi_recent[-20:-10][price_prev_min_idx] if price_prev_min_idx < len(rsi_recent[-20:-10]) else None
            
            if rsi_at_min is not None and rsi_at_prev is not None:
                if rsi_at_min > rsi_at_prev:
                    details['divergence_detected'] = True
                    details['type'] = 'BULLISH_DIVERGENCE'
                    details['msg'] = f'Price lower low but RSI higher ({rsi_at_min:.0f} > {rsi_at_prev:.0f})'
                    return False, details
    
    return True, details


# ==========================================================================
# 4B. H1 CANDLE BODY CONFIRMATION (Scaling Pre-condition)
# ==========================================================================

def check_h1_candle_confirmation(symbol: str, direction: str) -> Tuple[bool, Dict]:
    """Check if the current H1 candle confirms strong trend (no reversal).
    
    Per trading_strategy.md spec:
    - "75% H1 candle confirmation (no reversal)"
    - The H1 candle body must be >= 75% of the total range (high-low)
    - Body direction must match the trade direction
    
    Why H1?
    - H1 filters out M5 noise during scaling decisions
    - A 75% body means strong institutional conviction
    - Small body / large wicks = indecision / reversal risk
    
    Args:
        symbol: Trading symbol (e.g., 'XAUUSD')
        direction: 'LONG' or 'SHORT'
    
    Returns:
        (confirmed, details): True if H1 candle confirms trend
    """
    details = {
        'check': 'H1_CANDLE_BODY',
        'direction': direction,
        'confirmed': False,
        'body_pct': 0.0,
        'candle_direction': 'NONE',
    }
    
    if mt5 is None:
        return False, details
    
    try:
        # Fetch last 2 H1 candles (current forming + last closed)
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 2)
        if rates is None or len(rates) < 2:
            details['msg'] = 'Failed to fetch H1 data'
            return False, details
        
        # Use the LAST CLOSED H1 candle (index 0), not the forming one (index 1)
        candle = rates[0]
        c_open = candle['open']
        c_high = candle['high']
        c_low = candle['low']
        c_close = candle['close']
        
        total_range = c_high - c_low
        if total_range <= 0:
            details['msg'] = 'H1 candle has zero range (doji)'
            return False, details
        
        body = abs(c_close - c_open)
        body_pct = body / total_range
        is_bullish = c_close > c_open
        is_bearish = c_close < c_open
        
        details['body_pct'] = body_pct
        details['candle_direction'] = 'BULL' if is_bullish else ('BEAR' if is_bearish else 'DOJI')
        details['h1_open'] = c_open
        details['h1_close'] = c_close
        details['h1_high'] = c_high
        details['h1_low'] = c_low
        
        # CHECK 1: Body must be >= 75% of range
        if body_pct < H1_CANDLE_BODY_MIN_PCT:
            details['msg'] = (f'H1 body too small: {body_pct*100:.0f}% < {H1_CANDLE_BODY_MIN_PCT*100:.0f}% '
                            f'(indecision/reversal risk)')
            return False, details
        
        # CHECK 2: Candle direction must match trade direction
        if direction == 'LONG' and not is_bullish:
            details['msg'] = f'H1 candle is {details["candle_direction"]} (need BULL for LONG scaling)'
            return False, details
        
        if direction == 'SHORT' and not is_bearish:
            details['msg'] = f'H1 candle is {details["candle_direction"]} (need BEAR for SHORT scaling)'
            return False, details
        
        # ALL CHECKS PASSED
        details['confirmed'] = True
        details['msg'] = (f'H1 confirmed: {details["candle_direction"]} body={body_pct*100:.0f}% '
                         f'(>= {H1_CANDLE_BODY_MIN_PCT*100:.0f}%)')
        return True, details
        
    except Exception as e:
        details['msg'] = f'H1 check error: {str(e)}'
        return False, details


# ==========================================================================
# 5. TRAILING STOP & 4-LEVEL TP SPLITTING MANAGER
# ==========================================================================

class GoldPositionManager:
    """Manages 4-level TP splitting and trailing stop for positions.
    
    Per trading_strategy.md spec:
    - TP1 (30% distance): Close 30% volume
    - TP2 (50% distance): Close 20% volume → Move SL to entry (breakeven)
    - TP3 (80% distance): Close 30% volume
    - TP4 (100% distance): Remaining 20% hits broker's native TP order
    
    This runs in a separate thread monitoring positions every 2 seconds,
    independent of the main candle-based polling loop.
    
    Thread Safety:
    - _tracked_positions dict protected by RLock
    - Only this thread modifies position state
    - MT5 order_send is thread-safe (serialized by MT5 terminal)
    """
    
    def __init__(self, logger_func=None):
        self._running = False
        self._thread = None
        self._lock = threading.RLock()
        self._tracked_positions = {}  # {ticket: position_info}
        self._log = logger_func or print
    
    def start(self):
        """Start the position monitoring thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="GoldPositionManager")
        self._thread.start()
        self._log("[GOLD] Position Manager started (4-level TP splitting active)")
    
    def stop(self):
        """Stop the position monitoring thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._log("[GOLD] Position Manager stopped")
    
    def track_position(self, ticket: int, entry_price: float, sl_price: float, 
                       tp_price: float, direction: str, volume: float):
        """Register a new position for 4-level TP monitoring.
        
        Calculates TP price levels from entry and TP distance:
        - TP1 = entry + (tp_distance * 0.30)
        - TP2 = entry + (tp_distance * 0.50)  
        - TP3 = entry + (tp_distance * 0.80)
        - TP4 = tp_price (handled by broker's native TP order)
        
        Args:
            ticket: MT5 position ticket number
            entry_price: Position entry price
            sl_price: Initial stop loss price
            tp_price: Final take profit price (TP4 level)
            direction: 'LONG' or 'SHORT'
            volume: Position volume in lots
        """
        # Calculate TP distance
        if direction == 'LONG':
            tp_distance = tp_price - entry_price
        else:
            tp_distance = entry_price - tp_price
        
        if tp_distance <= 0:
            self._log(f"[GOLD] ⚠ #{ticket}: Invalid TP distance ({tp_distance:.2f}) - skipping TP splitting")
            return
        
        # Build TP level price targets
        tp_level_prices = []
        for level in TP_LEVELS:
            if direction == 'LONG':
                level_price = entry_price + (tp_distance * level['distance_pct'])
            else:
                level_price = entry_price - (tp_distance * level['distance_pct'])
            tp_level_prices.append({
                'name': level['name'],
                'price': level_price,
                'close_pct': level['close_pct'],
                'hit': False,
            })
        
        with self._lock:
            self._tracked_positions[ticket] = {
                'entry_price': entry_price,
                'sl_price': sl_price,
                'tp_price': tp_price,  # TP4 = broker's native TP
                'tp_distance': tp_distance,
                'direction': direction,
                'volume': volume,
                'original_volume': volume,
                'tp_levels': tp_level_prices,
                'tp_levels_hit': 0,
                'sl_moved_to_entry': False,
                # Scaling state
                'scaling_orders': [],     # List of {ticket, entry, sl, tp, volume}
                'scaling_count': 0,       # Number of scaling orders placed
                'scaling_eligible': False, # True after TP2 hit
                'is_scaling_order': False, # True if THIS is a scaling order (not base)
                'parent_ticket': None,     # Parent ticket if scaling order
                'tracked_at': datetime.now()
            }
        
        # Log all TP levels
        self._log(f"[GOLD] 📊 Tracking position #{ticket} | {direction} | Vol={volume:.2f} lots")
        self._log(f"[GOLD]   Entry={entry_price:.2f} | SL={sl_price:.2f} | TP_distance={tp_distance:.2f}")
        for lv in tp_level_prices:
            self._log(f"[GOLD]   {lv['name']}: Price={lv['price']:.2f} ({lv['close_pct']*100:.0f}% close)")
        self._log(f"[GOLD]   TP4: Price={tp_price:.2f} (remaining 20% - broker TP)")
        self._log(f"[GOLD]   Scaling: Max {MAX_SCALING_ORDERS} add-on orders (after TP2 + H1 confirm)")
    
    def _monitor_loop(self):
        """Main monitoring loop - runs every 2 seconds."""
        while self._running:
            try:
                self._check_positions()
            except Exception as e:
                self._log(f"[GOLD] Monitor error: {str(e)}")
            time.sleep(POSITION_MONITOR_INTERVAL_SEC)
    
    def _check_positions(self):
        """Check all tracked positions for TP level hits and execute partial closes."""
        if mt5 is None:
            return
        
        with self._lock:
            tickets_to_remove = []
            
            # ORACLE3 LIFO UNWINDING: Sort tracked positions by ticket ID descending (newest first)
            # This ensures that newest positions are checked and closed first, freeing up margin 
            # and reducing short-term exposure during high volatility.
            lifo_tickets = sorted(self._tracked_positions.keys(), reverse=True)
            
            for ticket in lifo_tickets:
                info = self._tracked_positions[ticket]
                # Check if position still exists in MT5
                positions = mt5.positions_get(ticket=ticket)
                if positions is None or len(positions) == 0:
                    tickets_to_remove.append(ticket)
                    hits = info['tp_levels_hit']
                    self._log(f"[GOLD] Position #{ticket} closed (by SL/TP) | TP levels hit: {hits}/3")
                    continue
                
                pos = positions[0]
                tick = mt5.symbol_info_tick(pos.symbol)
                if tick is None:
                    continue
                
                current_price = tick.bid if info['direction'] == 'LONG' else tick.ask
                
                # Check each TP level (sequential, must hit TP1 before TP2, etc.)
                for i, level in enumerate(info['tp_levels']):
                    if level['hit']:
                        continue  # Already hit this level
                    
                    # Check if price has reached this TP level
                    level_hit = False
                    if info['direction'] == 'LONG':
                        level_hit = current_price >= level['price']
                    else:  # SHORT
                        level_hit = current_price <= level['price']
                    
                    if not level_hit:
                        break  # Must hit levels in order; stop checking higher levels
                    
                    # TP LEVEL HIT! Execute partial close
                    self._log(f"[GOLD] 🎯 #{ticket}: {level['name']} HIT! | "
                              f"Price={current_price:.2f} >= Target={level['price']:.2f}")
                    
                    # Calculate close volume based on ORIGINAL volume
                    close_volume = info['original_volume'] * level['close_pct']
                    
                    success = self._partial_close_at_level(pos, info, close_volume, level['name'])
                    if success:
                        level['hit'] = True
                        info['tp_levels_hit'] += 1
                        
                        closed_pct = sum(lv['close_pct'] for lv in info['tp_levels'] if lv['hit'])
                        self._log(f"[GOLD] ✅ #{ticket}: {level['name']} closed {level['close_pct']*100:.0f}% "
                                  f"({close_volume:.2f} lots) | Total closed: {closed_pct*100:.0f}%")
                        
                        # CHECK: Move SL to entry after TP2 hit (per spec)
                        if info['tp_levels_hit'] >= SL_MOVE_AFTER_TP_LEVEL and not info['sl_moved_to_entry']:
                            sl_success = self._move_sl_to_entry(pos, info)
                            if sl_success:
                                info['sl_moved_to_entry'] = True
                                self._log(f"[GOLD] 🔒 #{ticket}: SL moved to ENTRY (breakeven) "
                                          f"after {info['tp_levels_hit']} TP levels hit | "
                                          f"New SL={info['entry_price']:.2f}")
                        
                        # SCALING TRIGGER: After TP2 hit, check if we can scale
                        if info['tp_levels_hit'] >= SCALING_TRIGGER_TP_LEVEL:
                            info['scaling_eligible'] = True
                            if info['scaling_count'] < MAX_SCALING_ORDERS:
                                self._check_and_execute_scaling(pos, info, ticket)
                    else:
                        self._log(f"[GOLD] ❌ #{ticket}: {level['name']} partial close FAILED")
                    
                    # Only process one TP level per check cycle
                    # (give MT5 time to update position volume)
                    break
                
                # CHECK SCALING ORDER PROGRESS
                # For scaling orders that are already running, check their 50% TP trigger
                if info.get('scaling_orders') and not info.get('is_scaling_order'):
                    self._check_scaling_order_progress(info, ticket)
            
            # Clean up closed positions
            for ticket in tickets_to_remove:
                del self._tracked_positions[ticket]
    
    def _move_sl_to_entry(self, position, info: Dict) -> bool:
        """Move stop loss to entry price (breakeven).
        
        Called after TP1+TP2 are hit (50% of position closed).
        Per trading_strategy.md: "Move SL to entry after scaling"
        """
        if mt5 is None:
            return False
        
        try:
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": position.symbol,
                "position": position.ticket,
                "sl": info['entry_price'],
                "tp": position.tp,  # Keep original TP4
                "magic": 234000,
            }
            result = mt5.order_send(request)
            return result is not None and result.retcode == mt5.TRADE_RETCODE_DONE
        except Exception as e:
            self._log(f"[GOLD] Move SL error: {str(e)}")
            return False
    
    def _partial_close_at_level(self, position, info: Dict, 
                                close_volume: float, level_name: str) -> bool:
        """Close a specific volume at a TP level.
        
        Args:
            position: MT5 position object
            info: Tracked position info dict
            close_volume: Volume to close (in lots)
            level_name: TP level name for logging (e.g., 'TP1')
        
        Returns:
            True if partial close succeeded
        """
        if mt5 is None:
            return False
        
        try:
            symbol_info = mt5.symbol_info(position.symbol)
            if symbol_info is None:
                return False
            
            # Round to valid lot step
            lot_step = symbol_info.volume_step
            close_volume = round(close_volume / lot_step) * lot_step
            close_volume = max(symbol_info.volume_min, close_volume)
            
            # Safety check: don't close more than current position volume
            if close_volume > position.volume:
                close_volume = position.volume
            
            # Safety check: remaining volume must be >= minimum (unless closing all)
            remaining = position.volume - close_volume
            if remaining > 0 and remaining < symbol_info.volume_min:
                # Adjust close_volume to leave at least min volume
                close_volume = position.volume - symbol_info.volume_min
                close_volume = round(close_volume / lot_step) * lot_step
                if close_volume < symbol_info.volume_min:
                    self._log(f"[GOLD] #{position.ticket}: {level_name} skip - volume too small "
                              f"(current={position.volume:.2f}, close={close_volume:.2f})")
                    return False
            
            tick = mt5.symbol_info_tick(position.symbol)
            if tick is None:
                return False
            
            # Determine close order type (opposite direction)
            if info['direction'] == 'LONG':
                order_type = mt5.ORDER_TYPE_SELL
                price = tick.bid
            else:
                order_type = mt5.ORDER_TYPE_BUY
                price = tick.ask
            
            # Detect filling mode
            filling_type = mt5.ORDER_FILLING_IOC
            if symbol_info.filling_mode & 2:
                filling_type = mt5.ORDER_FILLING_IOC
            elif symbol_info.filling_mode & 1:
                filling_type = mt5.ORDER_FILLING_FOK
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": position.symbol,
                "volume": close_volume,
                "type": order_type,
                "position": position.ticket,
                "price": price,
                "deviation": 20,
                "magic": 234000,
                "comment": f"Sunrise_{level_name}_{info['direction']}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling_type,
            }
            
            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                info['volume'] = position.volume - close_volume
                self._log(f"[GOLD] #{position.ticket}: {level_name} CLOSED {close_volume:.2f} lots @ {price:.2f} | "
                          f"Remaining: {info['volume']:.2f} lots")
                return True
            else:
                retcode = result.retcode if result else 'N/A'
                comment = result.comment if result else 'No response'
                self._log(f"[GOLD] #{position.ticket}: {level_name} order failed - code={retcode}: {comment}")
                return False
            
        except Exception as e:
            self._log(f"[GOLD] Partial close error ({level_name}): {str(e)}")
            return False
    
    # ==================================================================
    # SCALING ENGINE (Step 4)
    # ==================================================================
    
    def _check_and_execute_scaling(self, position, info: Dict, base_ticket: int):
        """Check H1 confirmation and execute scaling order if conditions met.
        
        Per trading_strategy.md:
        1. TP1+TP2 must be hit (50% closed) - already verified by caller
        2. H1 candle body >= 75% confirming trend
        3. Max 3 scaling orders
        4. Move SL of previous orders to entry after scaling
        """
        if info['scaling_count'] >= MAX_SCALING_ORDERS:
            return  # Max scaling reached
        
        symbol = position.symbol
        direction = info['direction']
        
        # CHECK H1 CANDLE CONFIRMATION (Step 5)
        h1_confirmed, h1_details = check_h1_candle_confirmation(symbol, direction)
        
        if not h1_confirmed:
            self._log(f"[SCALE] #{base_ticket}: H1 not confirmed - {h1_details.get('msg', 'unknown')}")
            return
        
        self._log(f"[SCALE] ✅ #{base_ticket}: H1 CONFIRMED - {h1_details.get('msg', '')}")
        
        # CHECK SPREAD before placing scaling order
        spread_ok, spread_points = check_gold_spread(symbol)
        if not spread_ok:
            self._log(f"[SCALE] #{base_ticket}: Spread too wide for scaling ({spread_points:.0f} pts)")
            return
        
        # EXECUTE SCALING ORDER
        scaling_number = info['scaling_count'] + 1
        success = self._place_scaling_order(position, info, base_ticket, scaling_number)
        
        if success:
            info['scaling_count'] = scaling_number
            self._log(f"[SCALE] 🚀 #{base_ticket}: Scaling order #{scaling_number}/{MAX_SCALING_ORDERS} PLACED!")
    
    def _place_scaling_order(self, position, info: Dict, 
                             base_ticket: int, scaling_number: int) -> bool:
        """Place a scaling (add-on) order.
        
        Scaling order specs:
        - Entry: Current market price (where TP2 was hit)
        - SL: Base order's entry price (breakeven level)
        - TP: Same TP distance as base order from new entry
        - Volume: Same risk-based calculation as base order
        """
        if mt5 is None:
            return False
        
        try:
            symbol = position.symbol
            direction = info['direction']
            tp_distance = info.get('tp_distance', 0)
            
            if tp_distance <= 0:
                self._log(f"[SCALE] #{base_ticket}: Cannot scale - invalid TP distance")
                return False
            
            # Get current tick for entry price
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return False
            
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                return False
            
            # Entry price = current market
            if direction == 'LONG':
                entry_price = tick.ask
                sl_price = info['entry_price']  # SL = base entry (breakeven)
                tp_price = entry_price + tp_distance  # Same TP distance
                order_type = mt5.ORDER_TYPE_BUY
            else:
                entry_price = tick.bid
                sl_price = info['entry_price']  # SL = base entry (breakeven)
                tp_price = entry_price - tp_distance  # Same TP distance
                order_type = mt5.ORDER_TYPE_SELL
            
            # Calculate lot size: 1% risk of account balance
            account_info = mt5.account_info()
            if account_info is None:
                return False
            
            balance = account_info.balance
            risk_amount = balance * SCALING_RISK_PERCENT
            
            sl_distance_price = abs(entry_price - sl_price)
            if sl_distance_price <= 0:
                self._log(f"[SCALE] #{base_ticket}: SL distance is zero - cannot calculate lot size")
                return False
            
            point = symbol_info.point
            tick_value = symbol_info.trade_tick_value
            tick_size = symbol_info.trade_tick_size
            
            if tick_size > 0 and point > 0:
                value_per_point = tick_value * (point / tick_size)
            else:
                value_per_point = tick_value if tick_value > 0 else 0.01
            
            sl_points = sl_distance_price / point
            
            if value_per_point > 0 and sl_points > 0:
                lot_size = risk_amount / (sl_points * value_per_point)
            else:
                self._log(f"[SCALE] #{base_ticket}: Invalid calculation values")
                return False
            
            # Round to lot step and apply limits
            lot_step = symbol_info.volume_step
            lot_size = round(lot_size / lot_step) * lot_step
            lot_size = max(symbol_info.volume_min, min(lot_size, symbol_info.volume_max))
            
            # Round prices
            digits = symbol_info.digits
            sl_price = round(sl_price, digits)
            tp_price = round(tp_price, digits)
            
            # Detect filling mode
            filling_type = mt5.ORDER_FILLING_IOC
            if symbol_info.filling_mode & 2:
                filling_type = mt5.ORDER_FILLING_IOC
            elif symbol_info.filling_mode & 1:
                filling_type = mt5.ORDER_FILLING_FOK
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": lot_size,
                "type": order_type,
                "price": entry_price,
                "sl": sl_price,
                "tp": tp_price,
                "deviation": 20,
                "magic": 234000,
                "comment": f"Sunrise_SCALE{scaling_number}_{direction}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling_type,
            }
            
            self._log(f"[SCALE] #{base_ticket}: Placing Scale#{scaling_number} {direction} | "
                      f"Entry={entry_price:.2f} SL={sl_price:.2f} TP={tp_price:.2f} | "
                      f"Vol={lot_size:.2f} lots | Risk=${risk_amount:.2f}")
            
            result = mt5.order_send(request)
            
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                # Track the scaling order
                scaling_info = {
                    'ticket': result.order,
                    'entry': result.price if result.price > 0 else entry_price,
                    'sl': sl_price,
                    'tp': tp_price,
                    'volume': result.volume,
                    'tp_distance': tp_distance,
                    'half_tp_reached': False,
                    'sl_moved': False,
                }
                info['scaling_orders'].append(scaling_info)
                
                self._log(f"[SCALE] ✅ #{base_ticket}: Scale#{scaling_number} FILLED! "
                          f"Ticket=#{result.order} | Vol={result.volume:.2f} lots @ {result.price:.2f}")
                return True
            else:
                retcode = result.retcode if result else 'N/A'
                comment = result.comment if result else 'No response'
                self._log(f"[SCALE] ❌ #{base_ticket}: Scale#{scaling_number} FAILED - {retcode}: {comment}")
                return False
        
        except Exception as e:
            self._log(f"[SCALE] Error placing scaling order: {str(e)}")
            return False
    
    def _check_scaling_order_progress(self, info: Dict, base_ticket: int):
        """Monitor scaling orders for their 50% TP trigger.
        
        Per trading_strategy.md:
        - When scaling order reaches 50% of its TP, move its SL to entry
        - If it also passes 50% TP, allow the next scaling order
        """
        if mt5 is None:
            return
        
        for scale_info in info['scaling_orders']:
            scale_ticket = scale_info['ticket']
            
            # Check if scaling position still exists
            positions = mt5.positions_get(ticket=scale_ticket)
            if positions is None or len(positions) == 0:
                continue  # Closed by SL/TP
            
            pos = positions[0]
            tick = mt5.symbol_info_tick(pos.symbol)
            if tick is None:
                continue
            
            current_price = tick.bid if info['direction'] == 'LONG' else tick.ask
            scale_entry = scale_info['entry']
            scale_tp_distance = scale_info['tp_distance']
            
            # Calculate progress toward TP
            if info['direction'] == 'LONG':
                progress = (current_price - scale_entry) / scale_tp_distance if scale_tp_distance > 0 else 0
            else:
                progress = (scale_entry - current_price) / scale_tp_distance if scale_tp_distance > 0 else 0
            
            # CHECK: Has this scaling order reached 50% of its TP?
            if progress >= SCALING_TRIGGER_TP_PCT and not scale_info['half_tp_reached']:
                scale_info['half_tp_reached'] = True
                self._log(f"[SCALE] 🎯 #{scale_ticket} (child of #{base_ticket}): "
                          f"Reached {progress*100:.0f}% of TP!")
                
                # Move SL of this scaling order to its entry
                if not scale_info['sl_moved']:
                    try:
                        request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "symbol": pos.symbol,
                            "position": scale_ticket,
                            "sl": scale_entry,
                            "tp": pos.tp,
                            "magic": 234000,
                        }
                        result = mt5.order_send(request)
                        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                            scale_info['sl_moved'] = True
                            self._log(f"[SCALE] 🔒 #{scale_ticket}: SL moved to entry {scale_entry:.2f}")
                    except Exception as e:
                        self._log(f"[SCALE] Error moving SL for #{scale_ticket}: {str(e)}")
                
                # TRIGGER NEXT SCALING ORDER (if available)
                if info['scaling_count'] < MAX_SCALING_ORDERS:
                    self._log(f"[SCALE] #{base_ticket}: Scale order #{scale_ticket} at 50% TP - "
                              f"checking for next scaling opportunity...")
                    # Re-fetch base position to pass to scaling check
                    base_positions = mt5.positions_get(ticket=base_ticket)
                    if base_positions and len(base_positions) > 0:
                        self._check_and_execute_scaling(base_positions[0], info, base_ticket)


# ==========================================================================
# 6. FAST-PATH TICK POLLING FOR WINDOW_OPEN (Async Thread)
# ==========================================================================

class GoldFastPollThread:
    """Dedicated thread for ultra-fast tick-level breakout detection.
    
    Architecture:
    - When XAUUSD transitions to WINDOW_OPEN, the main loop calls start().
    - This spawns a daemon thread that polls mt5.symbol_info_tick() every 500ms.
    - When a breakout boundary is hit, the result is placed into a thread-safe queue.
    - The main monitoring loop reads from the queue instead of calling _phase4_monitor_window().
    - When breakout is detected or window expires, main loop calls stop().
    
    Why a separate thread?
    - The main loop sleeps 5 seconds between iterations.
    - Gold can move $5/second during London/NY volatility.
    - 5-second polling = potential $25 slippage on entry.
    - 500ms polling = max $2.50 slippage (10x improvement).
    
    Thread Safety:
    - Result queue is thread-safe (queue.Queue).
    - Only ONE fast-poll thread runs at a time per symbol (enforced by _running flag).
    - Thread is daemon: auto-killed when main process exits.
    """
    
    def __init__(self, logger_func=None):
        self._running = False
        self._thread = None
        self._result_queue = None  # Will be created per-session
        self._lock = threading.RLock()
        self._log = logger_func or print
        self._symbol = None
        self._direction = None
        self._window_top = None
        self._window_bottom = None
        self._window_expiry_bar = None
        self._poll_count = 0
        self._started_at = None
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    def start(self, symbol: str, direction: str, window_top: float, 
              window_bottom: float, window_expiry_bar: int,
              result_queue) -> bool:
        """Start fast tick polling for breakout detection.
        
        Args:
            symbol: Trading symbol (e.g., 'XAUUSD')
            direction: 'LONG' or 'SHORT'
            window_top: Upper breakout boundary price
            window_bottom: Lower breakout boundary price
            window_expiry_bar: Bar count at which window expires
            result_queue: queue.Queue to put results into
        
        Returns:
            True if started successfully, False if already running
        """
        with self._lock:
            if self._running:
                self._log(f"[FASTPOLL] Already running for {self._symbol} - ignoring start request")
                return False
            
            self._symbol = symbol
            self._direction = direction
            self._window_top = window_top
            self._window_bottom = window_bottom
            self._window_expiry_bar = window_expiry_bar
            self._result_queue = result_queue
            self._poll_count = 0
            self._started_at = time.time()
            self._running = True
            
            self._thread = threading.Thread(
                target=self._poll_loop, 
                daemon=True, 
                name=f"GoldFastPoll_{symbol}"
            )
            self._thread.start()
            
            self._log(f"[FASTPOLL] ⚡ Started for {symbol} {direction} | "
                      f"Top={window_top:.2f} Bottom={window_bottom:.2f} | "
                      f"Polling every {FAST_POLL_INTERVAL_SEC}s")
            return True
    
    def stop(self):
        """Stop the fast polling thread."""
        with self._lock:
            if not self._running:
                return
            self._running = False
            elapsed = time.time() - self._started_at if self._started_at else 0
            self._log(f"[FASTPOLL] Stopped for {self._symbol} | "
                      f"Polls={self._poll_count} | Duration={elapsed:.1f}s")
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
    
    def update_expiry(self, new_expiry_bar: int):
        """Update the window expiry bar (called when main loop increments bar count)."""
        with self._lock:
            self._window_expiry_bar = new_expiry_bar
    
    def _poll_loop(self):
        """Core polling loop - runs every 500ms checking tick prices."""
        if mt5 is None:
            self._log("[FASTPOLL] MT5 not available - exiting")
            self._running = False
            return
        
        last_log_time = 0
        
        while self._running:
            try:
                tick = mt5.symbol_info_tick(self._symbol)
                if tick is None:
                    time.sleep(FAST_POLL_INTERVAL_SEC)
                    continue
                
                self._poll_count += 1
                current_bid = tick.bid
                current_ask = tick.ask
                current_mid = (current_bid + current_ask) / 2
                
                # Log tick every 5 seconds (not every 500ms to avoid spam)
                now = time.time()
                if now - last_log_time >= 5.0:
                    elapsed = now - self._started_at if self._started_at else 0
                    self._log(f"[FASTPOLL] {self._symbol} {self._direction} | "
                              f"Bid={current_bid:.2f} Ask={current_ask:.2f} | "
                              f"Window [{self._window_bottom:.2f} - {self._window_top:.2f}] | "
                              f"Polls={self._poll_count} ({elapsed:.0f}s)")
                    last_log_time = now
                
                # CHECK BREAKOUT BOUNDARIES
                result = None
                
                if self._direction == 'LONG':
                    # SUCCESS: Price breaks above top limit
                    if current_ask >= self._window_top:
                        result = {
                            'status': 'SUCCESS',
                            'price': current_ask,
                            'bid': current_bid,
                            'ask': current_ask,
                            'polls': self._poll_count,
                            'latency_ms': (now - self._started_at) * 1000 if self._started_at else 0,
                            'direction': self._direction,
                            'symbol': self._symbol,
                        }
                        self._log(f"[FASTPOLL] ✅ BREAKOUT! {self._symbol} LONG | "
                                  f"Ask={current_ask:.2f} >= Top={self._window_top:.2f} | "
                                  f"Detected in {self._poll_count} polls")
                    
                    # FAILURE: Price breaks below bottom limit
                    elif current_bid <= self._window_bottom:
                        result = {
                            'status': 'FAILURE',
                            'price': current_bid,
                            'bid': current_bid,
                            'ask': current_ask,
                            'polls': self._poll_count,
                            'latency_ms': (now - self._started_at) * 1000 if self._started_at else 0,
                            'direction': self._direction,
                            'symbol': self._symbol,
                        }
                        self._log(f"[FASTPOLL] ❌ FAILURE! {self._symbol} LONG | "
                                  f"Bid={current_bid:.2f} <= Bottom={self._window_bottom:.2f}")
                
                else:  # SHORT
                    # SUCCESS: Price breaks below bottom limit
                    if current_bid <= self._window_bottom:
                        result = {
                            'status': 'SUCCESS',
                            'price': current_bid,
                            'bid': current_bid,
                            'ask': current_ask,
                            'polls': self._poll_count,
                            'latency_ms': (now - self._started_at) * 1000 if self._started_at else 0,
                            'direction': self._direction,
                            'symbol': self._symbol,
                        }
                        self._log(f"[FASTPOLL] ✅ BREAKOUT! {self._symbol} SHORT | "
                                  f"Bid={current_bid:.2f} <= Bottom={self._window_bottom:.2f} | "
                                  f"Detected in {self._poll_count} polls")
                    
                    # FAILURE: Price breaks above top limit
                    elif current_ask >= self._window_top:
                        result = {
                            'status': 'FAILURE',
                            'price': current_ask,
                            'bid': current_bid,
                            'ask': current_ask,
                            'polls': self._poll_count,
                            'latency_ms': (now - self._started_at) * 1000 if self._started_at else 0,
                            'direction': self._direction,
                            'symbol': self._symbol,
                        }
                        self._log(f"[FASTPOLL] ❌ FAILURE! {self._symbol} SHORT | "
                                  f"Ask={current_ask:.2f} >= Top={self._window_top:.2f}")
                
                # If breakout detected, push to queue and stop
                if result:
                    self._result_queue.put(result)
                    self._running = False
                    return
                
                time.sleep(FAST_POLL_INTERVAL_SEC)
                
            except Exception as e:
                self._log(f"[FASTPOLL] Error in poll loop: {str(e)}")
                time.sleep(FAST_POLL_INTERVAL_SEC * 2)  # Back off on error
        
        # Thread stopped externally (window expired in main loop)
        self._log(f"[FASTPOLL] Thread stopped (external) for {self._symbol}")


# ==========================================================================
# 7. GOLD LOT SIZE CALCULATOR (Correct for 100oz contract)
# ==========================================================================

def calculate_gold_lot_size(balance: float, risk_percent: float, sl_distance_price: float,
                            use_dalio: bool = False, dalio_allocation: float = 0.15) -> Tuple[float, Dict]:
    """Calculate correct lot size for XAUUSD with proper contract size handling.
    
    XAUUSD contract: 1 lot = 100 oz
    Point value: 1 point ($0.01) = $0.01 per oz = $1.00 per lot
    
    Args:
        balance: Account balance
        risk_percent: Risk as decimal (0.01 = 1%)
        sl_distance_price: Stop loss distance in price units (e.g., $12.50)
        use_dalio: If True, use Dalio allocation; if False, use full balance
        dalio_allocation: Dalio allocation percentage for XAUUSD (default 15%)
    
    Returns:
        (lot_size, calculation_details): Lot size and breakdown
    """
    if mt5 is None:
        return 0.01, {'error': 'MT5 not available'}
    
    # Calculate risk amount
    if use_dalio:
        allocated_capital = balance * dalio_allocation
        risk_amount = allocated_capital * risk_percent
    else:
        # Risk-first spec: 1% of total balance
        risk_amount = balance * risk_percent
    
    # Get symbol info from MT5
    symbol_info = mt5.symbol_info("XAUUSD")
    if symbol_info is None:
        return 0.01, {'error': 'Symbol info unavailable'}
    
    point = symbol_info.point           # Usually 0.01 for XAUUSD
    tick_value = symbol_info.trade_tick_value   # Value per tick in account currency
    tick_size = symbol_info.trade_tick_size     # Minimum price change
    
    # Value per point
    if tick_size > 0 and point > 0:
        value_per_point = tick_value * (point / tick_size)
    else:
        value_per_point = tick_value if tick_value > 0 else 1.0
    
    # SL distance in points
    sl_points = sl_distance_price / point if point > 0 else sl_distance_price * 100
    
    # Lot size formula
    if value_per_point > 0 and sl_points > 0:
        lot_size = risk_amount / (sl_points * value_per_point)
    else:
        lot_size = 0.01
    
    # Apply broker limits
    lot_min = symbol_info.volume_min
    lot_max = symbol_info.volume_max
    lot_step = symbol_info.volume_step
    
    lot_size = round(lot_size / lot_step) * lot_step
    lot_size = max(lot_min, min(lot_size, lot_max))
    
    # Safety cap: Never risk more than 2% regardless of calculation
    max_safe_lot = (balance * 0.02) / (sl_points * value_per_point) if (sl_points * value_per_point) > 0 else lot_max
    max_safe_lot = round(max_safe_lot / lot_step) * lot_step
    lot_size = min(lot_size, max_safe_lot)
    
    details = {
        'balance': balance,
        'risk_percent': risk_percent,
        'risk_amount': risk_amount,
        'sl_distance_price': sl_distance_price,
        'sl_points': sl_points,
        'value_per_point': value_per_point,
        'lot_size_raw': risk_amount / (sl_points * value_per_point) if (sl_points * value_per_point) > 0 else 0,
        'lot_size_final': lot_size,
        'use_dalio': use_dalio,
        'safety_cap_applied': lot_size == max_safe_lot,
    }
    
    return lot_size, details
