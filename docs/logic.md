# LOGIC CỐT LÕI — PHÂN TÍCH TÍN HIỆU & VÀO LỆNH

> **Codebase:** MT5 Live Trading Bot — Sunrise Ogle Strategy
> **File chính:** `advanced_mt5_monitor_gui.py` (~3,500 dòng) + `strategies/sunrise_ogle_*.py`
> **Timeframe:** M5 (5 phút) | **8 Assets:** EURUSD, GBPUSD, XAUUSD, AUDUSD, XAGUSD, USDCHF, EURJPY, USDJPY

---

## 1. TỔNG QUAN PIPELINE

```
┌──────────────────────────────────────────────────────────────────┐
│ advanced_monitoring_loop()                  [line 1303]          │
│   └── monitor_strategy_phase(symbol)        [line 1358]          │
│        ├── Fetch M5 data → remove forming candle                 │
│        ├── calculate_indicators()           [line 2343]          │
│        │    └── detect_ema_crossovers()     [line 2074]          │
│        │         └── 6-LAYER FILTER CASCADE [line 2255-2305]     │
│        │              ├── _validate_atr_filter()         [1577]  │
│        │              ├── _validate_angle_filter()       [1678]  │
│        │              ├── _validate_price_filter()       [1739]  │
│        │              ├── _validate_candle_direction()   [1795]  │
│        │              ├── _validate_ema_ordering()       [1843]  │
│        │              └── _validate_ema_position_filter()[1890]  │
│        └── determine_strategy_phase()       [line 2768]          │
│             ├── PHASE 1: SCANNING → ARMED                        │
│             ├── PHASE 2: ARMED → WINDOW_OPEN (pullback)          │
│             ├── PHASE 3: WINDOW_OPEN (open breakout window)[2599]│
│             ├── PHASE 4: WINDOW_OPEN → ENTRY (breakout)   [2675] │
│             └── _execute_entry() / execute_trade() [4210/4259]   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. NGUYÊN TẮC TRỌNG YẾU CỦA TOÀN BỘ HỆ THỐNG

| # | Nguyên tắc | Lý do |
|---|------------|-------|
| 1 | **Chỉ xử lý nến đã đóng** (forming candle removed) | Match Backtrader: `next()` chạy 1 lần/closed candle |
| 2 | **EMA dùng `adjust=False`** | Khớp công thức EMA chuẩn (MT5/Backtrader) |
| 3 | **`Confirm EMA` = EMA(1) = giá close** | Dùng để phát hiện crossover |
| 4 | **Filter trên lỗi (Exception) → BLOCK trade** | An toàn: nếu validate lỗi thì không vào lệnh |
| 5 | **Stale crossover (trước startup) → bỏ qua** | Tránh trigger tín hiệu cũ khi bot khởi động lại |
| 6 | **Time filter CHỈ check tại Phase 4 (breakout)** | State progression chạy 24/7, chỉ chặn execution |
| 7 | **Duplicate position check** trước mỗi entry | Không mở lệnh trùng trên cùng 1 symbol |

---

## 3. TÍNH INDICATORS (`calculate_indicators` — line 2343)

### Các indicator được tính trên DataFrame đã loại forming candle:

| Indicator | Công thức | Mục đích |
|-----------|-----------|----------|
| `ema_fast` | `df['close'].ewm(span=fast_period, adjust=False).mean()` | EMA nhanh (default 18) |
| `ema_medium` | EMA(medium_period) | EMA trung bình (default 18) |
| `ema_slow` | EMA(slow_period) | EMA chậm (default 24-50) |
| `ema_filter` | EMA(filter_period) | EMA lọc trend (default 70-100) |
| `ema_confirm` | EMA(1) ≈ close price | Phát hiện crossover |
| `atr` | True Range rolling mean (period 10) | Volatility — dùng cho SL/TP/filter |

### True Range:
```python
high_low   = high - low
high_close = abs(high - close.shift())
low_close  = abs(low - close.shift())
true_range = max(high_low, high_close, low_close)
atr = true_range.rolling(atr_period).mean()
```

### Trend label (dùng cho hiển thị):
- `BULLISH`: fast > medium > slow
- `BEARISH`: fast < medium < slow
- `SIDEWAYS`: còn lại

---

## 4. PHÁT HIỆN CROSSOVER (`detect_ema_crossovers` — line 2074)

### Điều kiện CỐT LÕI:
- **Chỉ chạy 1 lần mỗi closed candle** (track qua `last_crossover_check_candle`)
- Cần ≥ 20 bars để tính EMA

### Bullish Crossover:
```
confirm_ema > fast_ema   AND  prev_confirm <= prev_fast    → bullish
confirm_ema > medium_ema AND  prev_confirm <= prev_medium  → bullish
confirm_ema > slow_ema   AND  prev_confirm <= prev_slow    → bullish
```
Đếm có thể được 1, 2 hoặc 3 crossover trong cùng 1 nến.

### Bearish Crossover (mirror):
```
confirm_ema < fast_ema   AND  prev_confirm >= prev_fast    → bearish
... (tương tự cho medium, slow)
```

### Stale check:
Nếu candle thời gian < `bot_startup_time` → set `crossover_is_stale = True` → bỏ qua signal.

---

## 5. 6-LAYER ENTRY FILTER CASCADE (CHẶNG 1 — TẠI CROSSOVER)

Mọi crossover phải pass **TẤT CẢ** filter mới chuyển sang ARMED. Nếu enable=False thì filter auto-pass.

### Filter 1 — ATR Filter (`_validate_atr_filter` — line 1577)
```python
# 1.1 ATR range
if not (ATR_MIN <= current_atr <= ATR_MAX):  return False

# 1.2 ATR increment filter (positive change)
atr_change = current_atr - signal_detection_atr  # KHÔNG dùng prev_atr
if atr_change >= 0 and USE_INCREMENT_FILTER:
    if not (incr_min <= atr_change <= incr_max):  return False

# 1.3 ATR decrement filter (negative change)
if atr_change < 0 and USE_DECREMENT_FILTER:
    if not (decr_min <= atr_change <= decr_max):  return False
```
**Lưu ý:** ATR change tính từ thời điểm signal detect, không phải bar trước đó.

### Filter 2 — Angle Filter (`_validate_angle_filter` — line 1678)
```python
ema_confirm  = df['close'].ewm(span=1, adjust=False).mean()
rise  = (ema_confirm[-1] - ema_confirm[-2]) * scale_factor   # 1 bar back
angle = atan(rise) * 180/pi
if not (MIN_ANGLE <= angle <= MAX_ANGLE):  return False
```
**Scale factor:** Forex = 10000, Metals = 10.

### Filter 3 — Price vs Filter EMA (`_validate_price_filter` — line 1739)
```
LONG:  current_close >  filter_EMA  (price above trend)
SHORT: current_close <  filter_EMA  (price below trend)
```

### Filter 4 — Candle Direction (`_validate_candle_direction` — line 1795)
```
LONG:  previous closed candle BULLISH  (close > open)
SHORT: previous closed candle BEARISH  (close < open)
```

### Filter 5 — EMA Ordering (`_validate_ema_ordering` — line 1843)
```
LONG:  confirm > fast  AND  confirm > medium  AND  confirm > slow
SHORT: confirm < fast  AND  confirm < medium  AND  confirm < slow
```
**KHÔNG** ép thứ tự `fast > medium > slow` — chỉ cần `confirm` cao/thấp hơn cả 3.

### Filter 6 — EMA Position vs Price (`_validate_ema_position_filter` — line 1890)
```
LONG:  current_close > fast_EMA, medium_EMA, slow_EMA  (all EMAs below price)
SHORT: current_close < fast_EMA, medium_EMA, slow_EMA  (all EMAs above price)
```

### Filter 7 — Time Filter (`_validate_time_filter` — line 1946) — CHỈ TẠI ENTRY
```python
strategy_time_utc = broker_time - broker_utc_offset
# Compare với Entry Start/End Hour (UTC) trong config
# Hỗ trợ overnight range (e.g. 22:00-02:00)
```

---

## 6. STATE MACHINE 4-PHASE (`determine_strategy_phase` — line 2768)

### Pre-checks (chạy trước mọi phase):
1. **Orphan position detection:** Nếu có position mở mà state ≠ `IN_TRADE` → sync về `IN_TRADE`
2. **SHORT emergency disable:** Nếu `ARMED_SHORT` → reset (global LONG-only)
3. **IN_TRADE check:** Nếu position đã đóng → reset về `SCANNING`
4. **Bar counter:** Tăng `current_bar` mỗi khi candle timestamp mới
5. **GLOBAL INVALIDATION:** ARMED_LONG + bearish_cross + RED candle → reset SCANNING

### PHASE 1 — SCANNING → ARMED (line 2927)
```
IF bullish_crossover:                    signal_direction = LONG
ELIF bearish_crossover AND short_enabled: signal_direction = SHORT

IF signal_direction:
    Clear crossover flags  # tránh re-arming
    Store signal_detection_atr  # cho ATR increment filter

    IF USE_PULLBACK_ENTRY:
        # PULLBACK MODE
        state = ARMED_{direction}
        phase = WAITING_PULLBACK
        pullback_candle_count = 0
        Store signal_trigger_candle (Bar -1, không phải Bar 0)
    ELSE:
        # STANDARD MODE
        Execute entry ngay → _execute_entry()
        Reset → SCANNING
```

### PHASE 2 — ARMED → WINDOW_OPEN (line 3042)
Mỗi closed candle mới, check pullback:

```
LONG pullback  = bearish candle (close < open)
SHORT pullback = bullish candle (close > open)

# Bulletproof gap detection
unprocessed_candles = df[df['time'] > last_pullback_check_candle]
FOR each unprocessed candle:
    # Global invalidation check tại candle này
    bullish_cross, bearish_cross = check_crossover_at_candle(candle_idx)
    IF armed_LONG AND bearish_cross AND current_red:   RESET
    IF armed_SHORT AND bullish_cross AND current_green: RESET

    IF candle là pullback đúng màu:
        pullback_count += 1
        IF pullback_count >= MAX_PULLBACK_CANDLES:
            Store last_pullback_candle_high/low
            → _phase3_open_breakout_window()
            entry_state = WINDOW_OPEN
            BREAK
    ELSE:
        # Wrong color → RESET to SCANNING
```

**Pullback rule:** Yêu cầu `MAX_CANDLES` nến pullback **LIÊN TIẾP** đúng màu. Sai màu = invalidate.

### PHASE 3 — Open Breakout Window (`_phase3_open_breakout_window` — line 2599)
Sau khi đủ pullback, mở **2-sided channel**:

```python
# 1. Time offset (optional)
IF USE_WINDOW_TIME_OFFSET:
    window_start_bar = current_bar + (pullback_count * WINDOW_OFFSET_MULTIPLIER)
ELSE:
    window_start_bar = current_bar

# 2. Duration
window_expiry_bar = window_start_bar + ENTRY_WINDOW_PERIODS  # 1-20 bars

# 3. Two-sided price channel
candle_range = last_pullback_high - last_pullback_low
price_offset = candle_range * WINDOW_PRICE_OFFSET_MULTIPLIER

window_top_limit    = last_pullback_high + price_offset
window_bottom_limit = last_pullback_low  - price_offset

entry_state = WINDOW_OPEN
```

### PHASE 4 — Monitor Window (`_phase4_monitor_window` — line 2675)
Mỗi candle mới khi `WINDOW_OPEN`, check breakout:

```
IF current_bar < window_bar_start:  return 'PENDING'    # chưa active
IF current_bar > window_expiry_bar: return 'EXPIRED'    # quá hạn

# LONG direction
IF current_high >= window_top_limit:
    IF time_filter_passed:  return 'SUCCESS'   # ✅ Breakout vào lệnh
    ELSE:                   return 'EXPIRED'   # ngoài giờ trade
IF current_low <= window_bottom_limit:
    return 'FAILURE'                            # ❌ Breakout ngược

# SHORT direction (mirror)
IF current_low <= window_bottom_limit:  → SUCCESS
IF current_high >= window_top_limit:    → FAILURE
```

### Xử lý kết quả Window:
| Status | Hành động |
|--------|-----------|
| `SUCCESS` | Re-validate filters → execute_trade() → `IN_TRADE` |
| `EXPIRED` | Quay lại `ARMED_{direction}`, reset pullback_count, tìm pullback mới |
| `FAILURE` | Quay lại `ARMED_{direction}`, reset pullback_count, tìm pullback mới |
| `PENDING` | Tiếp tục chờ |
| `None` | Vẫn trong boundaries, monitor tiếp |

---

## 7. 6-LAYER ENTRY FILTER CASCADE (CHẶNG 2 — TẠI BREAKOUT, line 3315)

Khi breakout `SUCCESS`, **re-validate** với indicator MỚI:
```
1. EMA Ordering           (_validate_ema_ordering)
2. Price Filter           (_validate_price_filter)
3. EMA Position           (_validate_ema_position_filter)
4. Angle Filter           (_validate_angle_filter)
5. Trigger Candle valid   (kiểm tra candle gốc còn đúng direction)
6. Time Filter            (_validate_time_filter)  ← CHỈ ở đây
```
Nếu fail bất kỳ → ABORT ENTRY, reset SCANNING.

---

## 8. THỰC THI LỆNH (`execute_trade` — line 4259)

### Bước 1 — Duplicate check:
```python
positions = mt5.positions_get(symbol=symbol)
IF positions exists: return False  # Không vào trùng
```

### Bước 2 — Ray Dalio Position Sizing:
```python
balance              = account_info.balance
allocation_percent   = ASSET_ALLOCATIONS[symbol]  # e.g. XAUUSD=18%
allocated_capital    = balance * allocation_percent
risk_percent         = config.get('RISK_PER_TRADE', 0.01)  # 1% default
risk_amount          = allocated_capital * risk_percent
```

### Asset Allocations (Ray Dalio):
| Asset | % | Vai trò |
|-------|---|---------|
| XAUUSD | 18% | Inflation hedge |
| USDCHF | 15% | Deflation hedge |
| AUDUSD | 15% | Commodity currency |
| GBPUSD | 13% | Balanced growth |
| EURUSD | 12% | Balanced growth |
| XAGUSD | 12% | Commodity exposure |
| USDJPY | 8% | JPY carry trade |
| EURJPY | 7% | JPY cross |

### Bước 3 — Tính SL/TP từ ATR:
```python
sl_distance = atr * ATR_SL_MULTIPLIER   # default 4.5
tp_distance = atr * ATR_TP_MULTIPLIER   # default 6.5

LONG:  sl_price = entry_price - sl_distance,  tp_price = entry_price + tp_distance
SHORT: sl_price = entry_price + sl_distance,  tp_price = entry_price - tp_distance
```

### Bước 4 — Tính lot size theo broker thật:
```python
# Lấy spec từ MT5 (KHÔNG hardcode pip value!)
point         = symbol_info.point
contract_size = symbol_info.trade_contract_size
tick_value    = symbol_info.trade_tick_value    # value/tick (account currency)
tick_size     = symbol_info.trade_tick_size

# Value per point
value_per_point      = tick_value * (point / tick_size)
sl_distance_in_points = sl_distance / point

# Final formula
lot_size = risk_amount / (sl_distance_in_points * value_per_point)

# Apply broker limits
lot_size = round(lot_size / lot_step) * lot_step
lot_size = max(lot_min, min(lot_size, lot_max))
```

### Bước 5 — Detect filling mode:
```python
IF symbol_info.filling_mode & 2: filling = IOC
ELIF symbol_info.filling_mode & 1: filling = FOK
ELIF symbol_info.filling_mode & 4: filling = RETURN
ELSE: filling = FOK  # fallback
```

### Bước 6 — Gửi order:
```python
request = {
    "action":       mt5.TRADE_ACTION_DEAL,
    "symbol":       symbol,
    "volume":       lot_size,
    "type":         BUY/SELL,
    "price":        entry_price,
    "sl":           sl_price,
    "tp":           tp_price,
    "deviation":    20,
    "magic":        234000,
    "comment":      f"Sunrise_{direction}",
    "type_time":    GTC,
    "type_filling": filling,
}
result = mt5.order_send(request)
IF result.retcode != TRADE_RETCODE_DONE: return False
```

---

## 9. CÁC RULE INVALIDATION (RESET VỀ SCANNING)

| Rule | Khi nào trigger | Vị trí |
|------|----------------|--------|
| **Global Invalidation** | ARMED_LONG + bearish_cross + RED candle | line 2886, 3194 |
| **Wrong Pullback Color** | Pullback candle sai màu | line 3258 |
| **Window EXPIRED** | Bar > window_expiry_bar | → quay lại ARMED |
| **Window FAILURE** | Price breaks fail boundary | → quay lại ARMED |
| **Filter Fail at Breakout** | Re-validate filter fail tại SUCCESS | line 3375 |
| **Outside Trading Hours** | Time filter fail tại breakout | line 3388 |
| **Stale Crossover** | Crossover < bot_startup_time | line 2179 |
| **SHORT Disabled** | ARMED_SHORT khi SHORT off | line 2802 |

---

## 10. CÁC BIẾN STATE QUAN TRỌNG (`strategy_states[symbol]`)

```python
{
    'entry_state':                'SCANNING'|'ARMED_LONG'|'ARMED_SHORT'|'WINDOW_OPEN'|'IN_TRADE',
    'phase':                      'NORMAL'|'WAITING_PULLBACK'|'WAITING_BREAKOUT'|'TRADE_ACTIVE',
    'armed_direction':            'LONG'|'SHORT'|None,
    'pullback_candle_count':      int,
    'signal_detection_atr':       float,        # ATR tại lúc detect signal
    'signal_trigger_candle':      dict,         # OHLC của Bar -1 khi armed
    'last_pullback_candle_high':  float,
    'last_pullback_candle_low':   float,
    'last_pullback_check_candle': timestamp,
    'window_bar_start':           int,
    'window_expiry_bar':          int,
    'window_top_limit':           float,
    'window_bottom_limit':        float,
    'window_active':              bool,
    'current_bar':                int,          # Increment per new candle
    'last_candle_time':           timestamp,
    'crossover_data':             {bullish, bearish, candle_time},
    'indicators':                 dict,
    'digits':                     int,          # 5 forex, 3 JPY, 2 XAUUSD, 3 XAGUSD
}
```

---

## 11. LƯỢC ĐỒ FLOW HOÀN CHỈNH

```
                        ┌──────────────┐
                        │   SCANNING   │ ◄────────────────────┐
                        └──────┬───────┘                      │
                               │                              │
                  Crossover detected                          │
                               │                              │
                  ┌────────────▼────────────┐                 │
                  │  6-LAYER FILTER CHECK   │                 │
                  │ (ATR/Angle/Price/Candle │                 │
                  │  /EMA Order/EMA Pos)    │                 │
                  └────────────┬────────────┘                 │
                               │                              │
                          ALL PASS?                           │
                          ┌────┴────┐                         │
                         NO         YES                       │
                          │          │                        │
                          └──────────┼────────────────────────┤
                                     │                        │
                              USE_PULLBACK?                   │
                              ┌──────┴──────┐                 │
                             NO            YES                │
                              │             │                 │
                     ┌────────▼─────┐  ┌────▼──────┐          │
                     │ STANDARD     │  │   ARMED   │          │
                     │ ENTRY (now)  │  └────┬──────┘          │
                     └──────┬───────┘       │                 │
                            │      Wait pullback candles      │
                            │               │                 │
                            │      ┌────────▼─────────┐       │
                            │      │ Right color?     │       │
                            │      └────────┬─────────┘       │
                            │       ┌───────┴───────┐         │
                            │      NO              YES        │
                            │       │               │         │
                            │       │      count >= MAX?      │
                            │       │       ┌───────┴───┐     │
                            │       │      NO          YES    │
                            │       │       │           │     │
                            │       │       └───────────┤     │
                            │       └───────────────────┼─────┤
                            │                           │     │
                            │                  ┌────────▼──────────┐
                            │                  │   WINDOW_OPEN     │
                            │                  │ (2-sided channel) │
                            │                  └────────┬──────────┘
                            │                           │
                            │                  ┌────────▼─────────┐
                            │                  │ Monitor breakout │
                            │                  └────────┬─────────┘
                            │                           │
                            │              ┌────────────┼────────────┐
                            │           SUCCESS      EXPIRED      FAILURE
                            │              │            │            │
                            │              │            └─→ ARMED ──┤
                            │              │            └─→ ARMED ──┤
                            │   Re-validate 6 filters + Time         │
                            │              │                         │
                            │           PASS?                        │
                            │       ┌──────┴──────┐                  │
                            │      NO            YES                 │
                            │       │             │                  │
                            │       └─────────────┼──────────────────┤
                            │                     │                  │
                            └─────────────────────▼                  │
                                     ┌────────────────┐              │
                                     │ execute_trade()│              │
                                     │ Dalio sizing   │              │
                                     │ ATR SL/TP      │              │
                                     │ Send to MT5    │              │
                                     └───────┬────────┘              │
                                             │                       │
                                        Order OK?                    │
                                       ┌─────┴─────┐                 │
                                      NO          YES                │
                                       │           │                 │
                                       └───────────┼─────────────────┤
                                                   │                 │
                                          ┌────────▼─────────┐       │
                                          │    IN_TRADE      │       │
                                          │  (locked until   │       │
                                          │  position close) │       │
                                          └────────┬─────────┘       │
                                                   │                 │
                                          Position closed?           │
                                                   │                 │
                                                   └─────────────────┘
```

---

## 12. THAM SỐ CONFIG QUAN TRỌNG (từ `strategies/sunrise_ogle_*.py`)

| Param | Mô tả |
|-------|-------|
| `ema_fast_length`, `ema_medium_length`, `ema_slow_length` | EMA periods |
| `ema_filter_price_length` | Filter EMA period (default 70-100) |
| `atr_length` | ATR period (default 10) |
| `long_atr_sl_multiplier` | SL multiplier (default 4.5) |
| `long_atr_tp_multiplier` | TP multiplier (default 6.5) |
| `LONG_USE_PULLBACK_ENTRY` | Bật/tắt pullback mode |
| `LONG_PULLBACK_MAX_CANDLES` | Số nến pullback cần (1-3) |
| `LONG_ENTRY_WINDOW_PERIODS` | Số bar window (1-20) |
| `USE_WINDOW_TIME_OFFSET` | Time offset window |
| `WINDOW_OFFSET_MULTIPLIER` | Multiplier offset |
| `WINDOW_PRICE_OFFSET_MULTIPLIER` | Price channel offset |
| `LONG_USE_ATR_FILTER`, `LONG_ATR_MIN/MAX_THRESHOLD` | ATR filter |
| `LONG_USE_ANGLE_FILTER`, `LONG_MIN/MAX_ANGLE`, `LONG_ANGLE_SCALE_FACTOR` | Angle filter |
| `LONG_USE_PRICE_FILTER_EMA` | Price vs filter EMA |
| `LONG_USE_CANDLE_DIRECTION_FILTER` | Candle direction filter |
| `LONG_USE_EMA_ORDER_CONDITION` | EMA ordering filter |
| `LONG_USE_EMA_BELOW_PRICE_FILTER` | EMA position filter |
| `Use Time Range Filter`, `Entry Start/End Hour (UTC)` | Time filter |
| `ENABLE_SHORT_TRADES` | Global SHORT toggle (default False) |
| `RISK_PER_TRADE` | % risk allocated capital (default 0.01) |

---

## 13. KEY FILES & LINES — QUICK REFERENCE

| Chức năng | File:Line |
|-----------|-----------|
| Main monitoring loop | `advanced_mt5_monitor_gui.py:1303` |
| Per-symbol orchestrator | `advanced_mt5_monitor_gui.py:1358` |
| State machine | `advanced_mt5_monitor_gui.py:2768` |
| Indicators calc | `advanced_mt5_monitor_gui.py:2343` |
| Crossover detection | `advanced_mt5_monitor_gui.py:2074` |
| Crossover at specific candle | `advanced_mt5_monitor_gui.py:2002` |
| ATR Filter | `advanced_mt5_monitor_gui.py:1577` |
| Angle Filter | `advanced_mt5_monitor_gui.py:1678` |
| Price Filter | `advanced_mt5_monitor_gui.py:1739` |
| Candle Direction Filter | `advanced_mt5_monitor_gui.py:1795` |
| EMA Ordering Filter | `advanced_mt5_monitor_gui.py:1843` |
| EMA Position Filter | `advanced_mt5_monitor_gui.py:1890` |
| Time Filter | `advanced_mt5_monitor_gui.py:1946` |
| Open breakout window | `advanced_mt5_monitor_gui.py:2599` |
| Monitor window | `advanced_mt5_monitor_gui.py:2675` |
| Reset state | `advanced_mt5_monitor_gui.py:2583` |
| Standard entry | `advanced_mt5_monitor_gui.py:4210` |
| Execute trade (MT5 send) | `advanced_mt5_monitor_gui.py:4259` |
| Backtrader source-of-truth | `strategies/sunrise_ogle_*.py` (READ-ONLY) |

---

> **⚠️ Lưu ý:** `src/sunrise_signal_adapter.py` là **placeholder cũ KHÔNG dùng** trong live bot. Toàn bộ logic phân tích & vào lệnh thực tế nằm trong `advanced_mt5_monitor_gui.py`.
