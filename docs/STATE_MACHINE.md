# 🔄 STATE MACHINE — 4-Phase Detailed Reference

> **Mục đích:** Mô tả chi tiết state transitions, conditions và edge cases.

---

## 1. STATE DIAGRAM

```
                                                  ┌────────────────────┐
                                                  │ Stale Crossover    │
                                                  │ → Skip processing  │
                                                  └────────────────────┘

         ┌─────────────────┐
         │   Bot Startup   │
         └────────┬────────┘
                  │
                  ▼
         ┌────────────────┐
         │   SCANNING     │ ◄─────────────────────────────────────────────┐
         │ (Default state)│                                               │
         └────────┬───────┘                                               │
                  │                                                       │
        Bullish/Bearish                                                   │
        Crossover detected                                                │
                  │                                                       │
                  ▼                                                       │
         ┌──────────────────┐                                             │
         │ 6-Layer Filter   │                                             │
         │ Cascade          │                                             │
         └────────┬─────────┘                                             │
                  │                                                       │
                  ▼                                                       │
              ALL PASS?                                                   │
              ┌──┴──┐                                                     │
             NO    YES                                                    │
              │     │                                                     │
       Discard│     │USE_PULLBACK_ENTRY?                                  │
       crossover    │                                                     │
              │     ├────────┬────────┐                                   │
              │    YES       │       NO                                   │
              │     │        │        │                                   │
              │     ▼        │        ▼                                   │
              │ ┌─────────┐  │  ┌─────────────────┐                       │
              │ │ ARMED_  │  │  │ Direct Entry    │                       │
              │ │ {LONG/  │  │  │ (STANDARD MODE) │                       │
              │ │ SHORT}  │  │  │ → IN_TRADE      │                       │
              │ └────┬────┘  │  └─────────┬───────┘                       │
              │      │       │            │                               │
              │      │       │            │ position                      │
              │      │       │            │ closed                        │
              │      │       │            ▼                               │
              │      │       │     ┌─────────────┐                        │
              │      │       │     │  SCANNING   │ ──────────────────────►┘
              │      │       │     └─────────────┘
              │      │       │
              │      ▼       │
              │ ┌─────────────────────┐
              │ │ Wait for Pullback   │ ◄─────────────────────────────┐
              │ │ Candle (loop)       │                                │
              │ └──────────┬──────────┘                                │
              │            │                                           │
              │            ▼                                           │
              │  Right color candle?                                   │
              │      ┌─────┴─────┐                                     │
              │     YES          NO                                    │
              │      │            │                                    │
              │      │  ┌─────────▼──────────┐                         │
              │      │  │ Wrong color → RESET│                         │
              │      │  │ → SCANNING         │ ────────────────────────┤
              │      │  └────────────────────┘                         │
              │      │                                                 │
              │ pullback_count++                                       │
              │      │                                                 │
              │  count >= MAX_PULLBACK_CANDLES?                        │
              │      │                                                 │
              │      ├──── NO ──────────────────────────────────────────┤
              │      │                                                 │
              │     YES                                                │
              │      │                                                 │
              │      ▼                                                 │
              │ ┌──────────────────────┐                               │
              │ │ Open Breakout Window │                               │
              │ │ (Phase 3)            │                               │
              │ └──────────┬───────────┘                               │
              │            │                                           │
              │            ▼                                           │
              │ ┌──────────────────────┐                               │
              │ │   WINDOW_OPEN        │ ◄─────┐                       │
              │ └──────────┬───────────┘       │                       │
              │            │                   │                       │
              │     ┌──────┴──────┐            │                       │
              │     │ Phase 4     │            │                       │
              │     │ Monitor     │            │                       │
              │     └──────┬──────┘            │                       │
              │            │                   │                       │
              │  ┌─────────┴─────────┐         │                       │
              │  │                   │         │                       │
              │ SUCCESS    EXPIRED/FAILURE     │                       │
              │  │                   │         │                       │
              │  ▼                   ▼         │                       │
              │ Validate     ARMED_{direction} ┘  (search new pullback)│
              │ all filters                                            │
              │ + Time check                                           │
              │  │                                                     │
              │  │  ALL PASS?                                          │
              │  │  ┌─────┴─────┐                                      │
              │  │ YES          NO                                     │
              │  │  │            │                                     │
              │  │  ▼            ▼                                     │
              │  │ ┌─────────┐  ┌──────────┐                           │
              │  │ │ EXECUTE │  │ ABORT    │                           │
              │  │ │ ORDER   │  │ → SCAN   │ ────────────────────────► ┤
              │  │ └────┬────┘  └──────────┘                           │
              │  │      │                                              │
              │  │      ▼                                              │
              │  │ ┌──────────────────┐                                │
              │  │ │   IN_TRADE       │                                │
              │  │ │ (Locked state)   │                                │
              │  │ └────────┬─────────┘                                │
              │  │          │                                          │
              │  │ position closed? (SL/TP hit)                        │
              │  │          │                                          │
              │  │          ▼                                          │
              │  │ ┌──────────────────┐                                │
              │  │ │ unlock → SCAN    │ ──────────────────────────────►┤
              │  │ └──────────────────┘                                │
              │  │                                                     │
              │  └──────────────── reset ARMED ──────────────────────► │
              │                                                        │
              │   ┌────────────── GLOBAL INVALIDATION ─────────────────┤
              │   │ ARMED_LONG  + bearish_cross + RED candle  → RESET  │
              │   │ ARMED_SHORT + bullish_cross + GREEN candle → RESET │
              │   └────────────────────────────────────────────────────┘
              │
              └────────────────► SCANNING (loop)
```

---

## 2. STATES — DEFINITION & FIELDS

| State | `entry_state` value | `phase` value | Khi nào |
|-------|---------------------|---------------|---------|
| **SCANNING** | `'SCANNING'` | `'NORMAL'` | Default, đang tìm crossover |
| **ARMED_LONG** | `'ARMED_LONG'` | `'WAITING_PULLBACK'` | Bullish crossover đã pass filters, chờ pullback |
| **ARMED_SHORT** | `'ARMED_SHORT'` | `'WAITING_PULLBACK'` | (Disabled by default) |
| **WINDOW_OPEN** | `'WINDOW_OPEN'` | `'WAITING_BREAKOUT'` | Pullback đủ, đang chờ breakout |
| **IN_TRADE** | `'IN_TRADE'` | `'TRADE_ACTIVE'` | Position đang mở, lock state |

---

## 3. STATE DICTIONARY (per symbol)

```python
strategy_states[symbol] = {
    # Core state
    'entry_state':                'SCANNING',          # Main FSM state
    'phase':                      'NORMAL',            # Display label
    'armed_direction':            None,                # 'LONG'|'SHORT'|None
    
    # Pullback tracking
    'pullback_candle_count':      0,                   # Đếm 1, 2, 3... (đến MAX)
    'signal_trigger_candle':      None,                # OHLC dict của Bar -1 khi armed
    'last_pullback_candle_high':  None,                # Cho window calc
    'last_pullback_candle_low':   None,
    'last_pullback_check_candle': None,                # Timestamp đã check
    'candle_sequence_counter':    0,                   # Total candles since ARMED
    'armed_at_candle_time':       None,                # Khi vào ARMED
    
    # Window
    'window_active':              False,
    'window_bar_start':           None,                # Bar index khi window mở
    'window_expiry_bar':          None,                # Bar index hết hạn
    'window_top_limit':           None,                # Price boundary trên
    'window_bottom_limit':        None,                # Price boundary dưới
    
    # Timing
    'current_bar':                0,                   # Increment per new candle
    'last_candle_time':           None,                # Latest closed timestamp
    'last_crossover_check_candle': None,               # Anti-duplicate
    
    # Data
    'crossover_data': {
        'bullish_crossover':      False,
        'bearish_crossover':      False,
        'candle_time':            datetime
    },
    'indicators':                 {},                  # Dict từ calculate_indicators
    'signals':                    [],                  # History
    'signal_detection_atr':       None,                # Cho ATR change filter
    
    # Display
    'breakout_level':             None,
    'last_update':                datetime.now(),
    'digits':                     5,                   # Symbol precision
}
```

---

## 4. TRANSITION TABLE

| Current State | Trigger | Conditions | Next State | Side Effects |
|---------------|---------|------------|------------|--------------|
| **SCANNING** | Bullish crossover | All 6 filters PASS + USE_PULLBACK=True | **ARMED_LONG** | Store signal_atr, trigger_candle, init counters |
| **SCANNING** | Bullish crossover | All 6 filters PASS + USE_PULLBACK=False | (direct) | `_execute_entry()` → IN_TRADE or SCAN |
| **SCANNING** | Bearish crossover | + SHORT enabled + filters pass | **ARMED_SHORT** | (rare — usually disabled) |
| **SCANNING** | Filter fail | - | SCANNING | Discard crossover |
| **SCANNING** | Stale crossover | candle < startup_time | SCANNING | Skip |
| **ARMED_LONG** | Bearish cross + RED | (Global Invalidation) | SCANNING | Reset, log |
| **ARMED_LONG** | Pullback candle (BEARISH) | count < MAX | ARMED_LONG | count++ |
| **ARMED_LONG** | Pullback candle (BEARISH) | count == MAX | **WINDOW_OPEN** | Open window, store boundaries |
| **ARMED_LONG** | Wrong color (BULLISH) | - | SCANNING | Reset |
| **ARMED_SHORT** | Mirror of ARMED_LONG | (BULLISH pullback expected) | WINDOW_OPEN | - |
| **WINDOW_OPEN** | bar < window_start | (PENDING) | WINDOW_OPEN | Wait |
| **WINDOW_OPEN** | bar > window_expiry | (EXPIRED) | **ARMED_{dir}** | Reset pullback_count, search new |
| **WINDOW_OPEN** | LONG: high >= top_limit | (SUCCESS) | (validate) | Re-check filters + time |
| **WINDOW_OPEN** | LONG: low <= bottom_limit | (FAILURE) | **ARMED_LONG** | Reset, search new pullback |
| **WINDOW_OPEN** | SUCCESS + filters pass + time OK | execute_trade() OK | **IN_TRADE** | Lock state |
| **WINDOW_OPEN** | SUCCESS + filters fail | - | SCANNING | Abort, reset |
| **WINDOW_OPEN** | SUCCESS + time fail | - | SCANNING | Abort, reset |
| **WINDOW_OPEN** | execute_trade fail | - | SCANNING | Reset |
| **IN_TRADE** | positions = [] | (closed by SL/TP) | SCANNING | Unlock |
| **IN_TRADE** | positions exist | - | IN_TRADE | Skip |
| **(Any)** | Orphan position detected | position exists, state ≠ IN_TRADE | **IN_TRADE** | Sync state |

---

## 5. PHASE 1 DETAIL — SCANNING → ARMED

### 5.1 Trigger
- `crossover_data['bullish_crossover'] == True`
- HOẶC `crossover_data['bearish_crossover'] == True AND short_enabled == True`

### 5.2 Logic flow
```python
if entry_state == 'SCANNING':
    signal_direction = None
    
    if bullish_cross:
        signal_direction = 'LONG'
    elif bearish_cross and short_enabled:
        signal_direction = 'SHORT'
    
    if signal_direction:
        # CRITICAL: Clear flags trước để tránh re-arming
        crossover_data['bullish_crossover'] = False
        crossover_data['bearish_crossover'] = False
        
        # Decide mode
        use_pullback = config['LONG_USE_PULLBACK_ENTRY']
        
        if use_pullback:
            # PULLBACK MODE
            entry_state = f'ARMED_{signal_direction}'
            phase = 'WAITING_PULLBACK'
            armed_direction = signal_direction
            pullback_candle_count = 0
            signal_detection_atr = indicators['atr']
            
            # Trigger candle = Bar -1 (previous closed)
            signal_trigger_candle = {
                'open':  df['open'].iloc[-2],
                'high':  df['high'].iloc[-2],
                'low':   df['low'].iloc[-2],
                'close': df['close'].iloc[-2],
                'datetime': df['time'].iloc[-2],
                'is_bullish': close > open,
                'is_bearish': close < open
            }
            
            # Mark current candle as processed
            last_pullback_check_candle = df['time'].iloc[-1]
            candle_sequence_counter = 0
            armed_at_candle_time = df['time'].iloc[-1]
        else:
            # STANDARD MODE — direct entry
            _execute_entry(symbol, signal_direction, df, current_dt, config)
            _reset_entry_state(symbol)
```

### 5.3 Tại sao trigger candle = Bar -1?
Match logic Backtrader gốc — `data.close[-1]` trong `next()` ám chỉ candle đã đóng trước hiện tại. Khi crossover detect ở Bar 0 (vừa đóng), trigger thực tế là từ Bar -1 (penultimate).

---

## 6. PHASE 2 DETAIL — ARMED → WINDOW_OPEN (Pullback)

### 6.1 Pullback definition
| Direction | Pullback candle = |
|-----------|---------------------|
| LONG | BEARISH (close < open) — giá điều chỉnh xuống tạm thời |
| SHORT | BULLISH (close > open) — giá điều chỉnh lên tạm thời |

### 6.2 Bulletproof gap detection
```python
# Mỗi cycle, lấy ALL candles AFTER last_pullback_check_candle
unprocessed = df[df['time'] > last_pullback_check_candle]

if len(unprocessed) == 0:
    # Đã xử lý hết, chờ candle mới
    pass
elif len(unprocessed) == 1:
    # Normal: chỉ 1 candle mới
    process(unprocessed)
else:
    # GAP! Multiple candles bị skip (network issue?)
    # Process TẤT CẢ theo thứ tự
    for candle in unprocessed:
        process(candle)
```

### 6.3 Per-candle processing
```python
for candle in unprocessed:
    seq_counter += 1
    log(f"CHECKING CANDLE #{seq_counter}")
    
    # Global Invalidation tại candle này
    bullish, bearish = check_crossover_at_candle(idx)
    if armed_LONG and bearish and current_red:
        return SCANNING  # INVALIDATE
    
    # Pullback color check
    is_pullback = (close < open) if armed_LONG else (close > open)
    
    last_pullback_check_candle = candle['time']
    
    if is_pullback:
        pullback_count += 1
        if pullback_count >= MAX_PULLBACK_CANDLES:
            last_pullback_high = candle['high']
            last_pullback_low  = candle['low']
            _phase3_open_breakout_window()
            entry_state = 'WINDOW_OPEN'
            break
    else:
        # Wrong color → IMMEDIATE RESET
        _reset_entry_state()
        return SCANNING
```

### 6.4 Pullback yêu cầu phải LIÊN TIẾP
Sai 1 candle (wrong color) = **reset toàn bộ** về SCANNING. Không có "tolerance".

---

## 7. PHASE 3 DETAIL — Window Construction

### 7.1 Inputs
- `last_pullback_candle_high/low` — high/low của nến pullback CUỐI
- `pullback_candle_count` — số nến pullback đã có
- Config: `USE_WINDOW_TIME_OFFSET`, `WINDOW_OFFSET_MULTIPLIER`, `WINDOW_PRICE_OFFSET_MULTIPLIER`, `LONG_ENTRY_WINDOW_PERIODS`

### 7.2 Time offset (optional)
```python
if USE_WINDOW_TIME_OFFSET:
    offset = pullback_count * WINDOW_OFFSET_MULTIPLIER
    window_start_bar = current_bar + int(offset)
else:
    window_start_bar = current_bar  # Window active immediately
```

### 7.3 Two-sided price channel
```python
candle_range = last_pullback_high - last_pullback_low
price_offset = candle_range * WINDOW_PRICE_OFFSET_MULTIPLIER

window_top_limit    = last_pullback_high + price_offset
window_bottom_limit = last_pullback_low  - price_offset
```

### 7.4 Window duration
```python
window_expiry_bar = window_start_bar + LONG_ENTRY_WINDOW_PERIODS  # 1-20 bars
```

### 7.5 Visual minh hoạ:
```
        Pullback candle (last)
                  │
       ┌──────────┴──────────┐
       │ Top    ▲ window_top │ ──────  high + price_offset  ── SUCCESS for LONG
       │        │            │
       │        ▼            │ ──────  high                  ── pullback high
       │   ┌────────────┐    │
       │   │  Pullback  │    │
       │   │   Candle   │    │  ◄── window_active từ here
       │   └────────────┘    │
       │        ▲            │ ──────  low                   ── pullback low
       │        │            │
       │ Bottom ▼ window_bot │ ──────  low - price_offset    ── FAILURE for LONG
       └─────────────────────┘
       │←─── window_periods ─→│ (1-20 bars)
```

---

## 8. PHASE 4 DETAIL — Window Monitoring

### 8.1 Status codes
```python
def _phase4_monitor_window():
    if current_bar < window_bar_start:
        return 'PENDING'    # Time offset chưa qua
    
    if current_bar > window_expiry_bar:
        return 'EXPIRED'    # Hết hạn
    
    if direction == 'LONG':
        if current_high >= window_top_limit:
            if time_filter_pass:
                return 'SUCCESS'    # ✅ Breakout
            else:
                return 'EXPIRED'    # Out of hours
        if current_low <= window_bottom_limit:
            return 'FAILURE'        # ❌ Wrong direction
    
    else:  # SHORT (mirror)
        if current_low <= window_bottom_limit:
            return 'SUCCESS'
        if current_high >= window_top_limit:
            return 'FAILURE'
    
    return None  # Still monitoring
```

### 8.2 Re-validation tại SUCCESS

**Quan trọng:** Filters re-check với **indicators MỚI** (không dùng cache):

```python
# 1. Re-calculate indicators
fresh_indicators = calculate_indicators(df, symbol)

# 2. Add ATR vào df cho validators
df_validation = df.copy()
df_validation['atr'] = fresh_indicators['atr']

# 3. Re-validate (4 filter chính):
filters_to_check = [
    _validate_ema_ordering(symbol, fresh_confirm, fresh_fast, fresh_medium, fresh_slow, dir),
    _validate_price_filter(symbol, df_validation, dir),
    _validate_ema_position_filter(symbol, df_validation, fresh_fast, fresh_medium, fresh_slow, dir),
    _validate_angle_filter(symbol, df_validation, dir)
]

# 4. Trigger candle direction (LONG = trigger phải bullish, etc.)
if signal_trigger_candle:
    if direction == 'LONG' and not trigger_candle['is_bullish']:
        all_filters_passed = False

# 5. Time filter (final check)
if not _validate_time_filter(symbol, current_dt, direction):
    return SCANNING

# 6. Execute trade
if all_filters_passed:
    execute_trade(symbol, direction, current_close, config)
    entry_state = 'IN_TRADE'
else:
    _reset_entry_state()
```

---

## 9. EDGE CASES & DEFENSIVE LOGIC

### 9.1 Orphan Position Detection (line 2787)
**Vấn đề:** Bot crash khi đang IN_TRADE → restart, position vẫn ở MT5 nhưng state về SCANNING → có thể vào lệnh trùng.

**Giải pháp:**
```python
if entry_state != 'IN_TRADE':
    positions = mt5.positions_get(symbol=symbol)
    if positions and len(positions) > 0:
        # Sync state
        entry_state = 'IN_TRADE'
        armed_direction = 'LONG' if pos.type == 0 else 'SHORT'
        return 'IN_TRADE'
```

### 9.2 ARMED_SHORT Emergency Reset (line 2802)
**Vấn đề:** State machine có code SHORT nhưng default disabled toàn cục.

**Giải pháp:** Nếu somehow ARMED_SHORT xuất hiện → emergency reset.

### 9.3 IN_TRADE → SCANNING Auto-unlock
**Vấn đề:** Bot không quản lý exit (SL/TP đặt ở MT5).

**Giải pháp:** Mỗi cycle check `positions_get()`. Nếu empty → position đã đóng → reset.

### 9.4 Stale Crossover (line 2179)
**Vấn đề:** Bot khởi động lại lúc giữa nến → crossover từ trước startup vẫn được detect.

**Giải pháp:** So với `bot_startup_time`, bỏ qua nếu candle cũ hơn.

### 9.5 Saved State Stale Check
**Vấn đề:** Bot tắt 1 ngày, state cũ không còn relevant.

**Giải pháp:** Trong `load_strategy_state()`:
- Check `STATE_MAX_AGE_MINUTES = 30` → discard nếu cũ hơn
- Validate `entry_state in VALID_ENTRY_STATES` → reset nếu invalid
- (Note: IN_TRADE không nằm trong VALID_ENTRY_STATES — luôn reset về SCANNING)

### 9.6 Re-arming Prevention (line 2953)
**Vấn đề:** Cùng 1 crossover bị process 2 lần → ARM 2 lần.

**Giải pháp:** Sau khi consume crossover, **clear flags ngay**:
```python
crossover_data['bullish_crossover'] = False
crossover_data['bearish_crossover'] = False
```

### 9.7 Forming candle bug (CRITICAL FIX)
**Vấn đề trước fix:** Tính EMA trên forming candle → giá trị thay đổi liên tục → crossover phantom.

**Giải pháp:** `df = df.iloc[:-1].copy()` ngay sau fetch.

---

## 10. INVALIDATION RULES — TỔNG HỢP

| Rule | Trigger | Result |
|------|---------|--------|
| **Global Invalidation** | ARMED + opposing crossover + matching color candle | RESET → SCANNING |
| **Wrong Pullback Color** | Pullback candle sai màu | RESET → SCANNING |
| **Window EXPIRED** | bar > window_expiry_bar | → ARMED (search new pullback) |
| **Window FAILURE** | Price breaks fail boundary | → ARMED (search new pullback) |
| **Filter Fail at Breakout** | Re-validate fail tại SUCCESS | RESET → SCANNING |
| **Time Filter Fail** | Outside trading hours tại breakout | RESET → SCANNING |
| **Stale Crossover** | Candle < bot_startup_time | Skip (no state change) |
| **Trigger Candle Direction Invalid** | Bar -1 candle wrong color tại breakout | RESET → SCANNING |
| **Order Send Fail** | mt5.order_send() returns error | RESET → SCANNING |
| **SHORT Disabled** | ARMED_SHORT + global SHORT off | Emergency RESET |
| **IPC Failure** | mt5.last_error() == -10001 | attempt_reconnect() (no state change) |

---

## 11. EXAMPLE TIMELINE — FULL CYCLE

```
14:30:00  M5 close → SCANNING
          - Calculate EMA + ATR
          - No crossover
          - State unchanged

14:35:00  M5 close → SCANNING
          - BULLISH CROSSOVER detected (Confirm > Fast)
          - 6 Filters: ALL PASS ✅
          - USE_PULLBACK = True
          - State: SCANNING → ARMED_LONG
          - signal_trigger_candle = OHLC at 14:30 (Bar -1)
          - signal_detection_atr = 0.00045
          - pullback_count = 0
          - last_pullback_check_candle = 14:35

14:40:00  M5 close → ARMED_LONG
          - Candle 14:40: BEARISH (close < open) ✅ pullback
          - pullback_count = 1
          - MAX = 2, need 1 more

14:45:00  M5 close → ARMED_LONG
          - Candle 14:45: BEARISH ✅ pullback
          - pullback_count = 2 == MAX
          - last_pullback_high = 1.08267
          - last_pullback_low  = 1.08221
          - candle_range = 0.00046
          - price_offset = 0.00046 * 0.5 = 0.00023
          - window_top_limit = 1.08267 + 0.00023 = 1.08290
          - window_bottom_limit = 1.08221 - 0.00023 = 1.08198
          - window_start_bar = current_bar
          - window_expiry_bar = current_bar + 10
          - State: ARMED_LONG → WINDOW_OPEN

14:50:00  M5 close → WINDOW_OPEN
          - high = 1.08280 < 1.08290 (top)
          - low  = 1.08240 > 1.08198 (bottom)
          - No breakout, monitoring continues

14:55:00  M5 close → WINDOW_OPEN
          - high = 1.08295 >= 1.08290 ✅ SUCCESS
          - Time filter: current_time = 14:55 (broker UTC+1) → 13:55 UTC
            - Allowed range: 08:00-16:00 UTC ✅
          - Re-validate filters (with fresh indicators):
            - EMA Ordering: PASS
            - Price Filter: PASS
            - EMA Position: PASS
            - Angle: PASS
            - Trigger Candle (Bar -1 at 14:30): bullish ✅
          - All pass → execute_trade()
            - balance = $10,000
            - allocation = 12% = $1,200
            - risk = 1% × $1,200 = $12
            - atr = 0.00050 (fresh)
            - sl_distance = 0.00050 × 4.5 = 0.00225
            - lot = $12 / (225 points × $1.0/point) = 0.053 → round to 0.05
            - sl_price = 1.08295 - 0.00225 = 1.08070
            - tp_price = 1.08295 + 0.00325 = 1.08620
          - order_send() → SUCCESS (Order #87654321)
          - State: WINDOW_OPEN → IN_TRADE

15:00:00 — 18:00:00  M5 close → IN_TRADE
          - positions_get() returns [position]
          - Skip processing

18:05:00  M5 close
          - positions_get() returns []  (TP hit)
          - Position closed by broker (TP at 1.08620)
          - State: IN_TRADE → SCANNING
          - Ready for new signals
```
