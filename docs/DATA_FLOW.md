# 🌊 DATA FLOW — From MT5 Tick to Order

> **Mục đích:** Visualize đường đi của dữ liệu qua từng bước, kèm shape/type/sample.

---

## 1. SƠ ĐỒ TỔNG QUAN

```
┌────────────────────┐        ┌────────────────────┐        ┌─────────────────┐
│  MT5 TERMINAL      │  IPC   │  Python Bot        │  TCP   │  BROKER SERVER  │
│  (running locally) │ ─────► │  (bot logic)       │ ─────► │  (live market)  │
└─────────▲──────────┘        └─────────┬──────────┘        └─────────────────┘
          │                              │
          │ mt5.copy_rates_from_pos()    │ mt5.order_send()
          │                              │
          └──────────────────────────────┘
              (Bidirectional via Python API)
```

---

## 2. INPUT — Market Data Pipeline

### 2.1 `mt5.copy_rates_from_pos(symbol, TIMEFRAME_M5, 0, 151)`

**Output:** `numpy.ndarray` of structured records

```python
# Sample row (tuple-like)
(
    1731420600,           # time   (Unix epoch seconds)
    1.08234,              # open
    1.08267,              # high
    1.08221,              # low
    1.08245,              # close
    142,                  # tick_volume
    0,                    # spread (in points)
    0                     # real_volume
)
```

**Shape:** `(151,)` — 151 nến liên tiếp (150 closed + 1 forming)

### 2.2 Convert → Pandas DataFrame

```python
df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')
```

**DataFrame schema sau convert:**

| Column | Type | Sample |
|--------|------|--------|
| `time` | datetime64[ns] | `2025-11-12 14:30:00` |
| `open` | float64 | 1.08234 |
| `high` | float64 | 1.08267 |
| `low` | float64 | 1.08221 |
| `close` | float64 | 1.08245 |
| `tick_volume` | int64 | 142 |
| `spread` | int64 | 0 |
| `real_volume` | int64 | 0 |

### 2.3 Remove forming candle ⚡ CRITICAL

```python
df = df.iloc[:-1].copy()   # Bỏ nến đang hình thành
```
**Lý do:** EMA/ATR phải tính trên closed candles (match MT5 + Backtrader).

**Final DataFrame:** 150 rows.

---

## 3. INDICATOR COMPUTATION

### 3.1 EMA (Exponential Moving Average)

```python
df['close'].ewm(span=N, adjust=False).mean()
```

**Quan trọng:** `adjust=False` đảm bảo dùng công thức đệ quy chuẩn:
```
EMA[t] = α × Price[t] + (1-α) × EMA[t-1]
α = 2 / (N + 1)
```
Match với MT5 và Backtrader. `adjust=True` (mặc định pandas) sẽ KHÁC.

### 3.2 4 EMAs được tính (LONG default params):

| Name | Period | Mục đích |
|------|--------|----------|
| `ema_fast` | 18 | Trend nhanh |
| `ema_medium` | 18 | Trend trung |
| `ema_slow` | 24 | Trend chậm |
| `ema_filter` | 100 | Filter trend lớn |
| `ema_confirm` | 1 | = close price (cho crossover detect) |

### 3.3 ATR (Average True Range)

```python
high_low   = df['high'] - df['low']
high_close = abs(df['high'] - df['close'].shift())
low_close  = abs(df['low']  - df['close'].shift())

ranges     = pd.concat([high_low, high_close, low_close], axis=1)
true_range = np.max(ranges, axis=1)
atr        = true_range.rolling(atr_period).mean().iloc[-1]
```

**Kết quả:** float scalar (ATR cuối cùng)

### 3.4 `indicators` dict (output của `calculate_indicators`):
```python
{
    'ema_fast':           1.08220,
    'ema_medium':         1.08220,
    'ema_slow':           1.08198,
    'ema_filter':         1.08087,
    'ema_confirm':        1.08245,
    'ema_fast_period':    18,
    'ema_medium_period':  18,
    'ema_slow_period':    24,
    'ema_filter_period':  100,
    'atr':                0.00045,
    'atr_period':         10,
    'current_price':      1.08245,
    'sl_level':           1.08178,
    'tp_level':           1.08695,
    'sl_multiplier':      4.5,
    'tp_multiplier':      6.5,
    'trend':              'BULLISH',
    'ema_fast_array':     pd.Series(...),    # cho chart
    'ema_medium_array':   pd.Series(...),
    'ema_slow_array':     pd.Series(...),
    'ema_filter_array':   pd.Series(...),
}
```

---

## 4. CROSSOVER DETECTION FLOW

```
indicators DataFrame (150 rows, EMA series tính sẵn)
         │
         ▼
detect_ema_crossovers()
         │
         ├── Lấy current vs prev (iloc[-1] vs iloc[-2])
         │
         ├── BULLISH check:
         │     confirm > fast  AND  prev_confirm <= prev_fast    (3 đường)
         │
         ├── BEARISH check (mirror)
         │
         ├── Stale check (candle_time vs bot_startup_time)
         │
         └── 6-LAYER FILTER VALIDATION ▼

      ┌────────────────────────────────────────┐
      │ ATR Filter      → True/False           │
      │ Angle Filter    → True/False           │
      │ Price Filter    → True/False           │
      │ Candle Filter   → True/False           │
      │ EMA Ordering    → True/False           │
      │ EMA Position    → True/False           │
      └─────────────┬──────────────────────────┘
                    │
            ALL PASS?
            ┌──────┴──────┐
           YES            NO
            │              │
       ┌────▼────┐    ┌────▼────┐
       │ Cross   │    │ Discard │
       │ STORED  │    │  Cross  │
       └────┬────┘    └─────────┘
            ▼
    strategy_states[symbol]['crossover_data'] = {
        'bullish_crossover': True/False,
        'bearish_crossover': True/False,
        'candle_time':       datetime
    }
```

---

## 5. STATE FLOW

### 5.1 strategy_states[symbol] mutation timeline

| Phase Transition | Field changes |
|------------------|---------------|
| Init | `entry_state='SCANNING'`, `current_bar=0`, `pullback_count=0` |
| **SCANNING → ARMED_LONG** | `entry_state='ARMED_LONG'`, `armed_direction='LONG'`, `signal_detection_atr=X`, `signal_trigger_candle={OHLC}`, `last_pullback_check_candle=time` |
| Pullback detected (n/MAX) | `pullback_candle_count++`, `last_pullback_check_candle=time` |
| **ARMED → WINDOW_OPEN** | `entry_state='WINDOW_OPEN'`, `last_pullback_candle_high/low=X`, `window_bar_start=N`, `window_expiry_bar=N+M`, `window_top_limit=X`, `window_bottom_limit=Y`, `window_active=True` |
| **WINDOW_OPEN → IN_TRADE** | `entry_state='IN_TRADE'`, `phase='TRADE_ACTIVE'` |
| Position closed | Reset all → `entry_state='SCANNING'` |
| Window EXPIRED/FAILURE | `entry_state='ARMED_{direction}'`, `pullback_count=0`, window vars=None |

### 5.2 Persistence: state → JSON

```
strategy_states (in-memory)
         │
         │  save_strategy_state()
         │  - deepcopy
         │  - remove non-serializable (DataFrames)
         │  - convert datetime → ISO string
         │  - atomic write (.tmp + rename)
         ▼
mt5_strategy_state.json
{
    "EURUSD": {
        "entry_state": "ARMED_LONG",
        "armed_direction": "LONG",
        "pullback_candle_count": 1,
        "last_update": "2025-11-12T14:35:00",
        ...
    },
    "GBPUSD": {...},
    ...
}
```

---

## 6. ORDER EXECUTION FLOW (DATA TRANSFORMATION)

### 6.1 Inputs
```python
symbol     = 'EURUSD'
direction  = 'LONG'
price      = 1.08245   # current close
config     = {...}      # from strategy file
```

### 6.2 Pipeline transformation

```
Step 1: Get broker info
  symbol_info = mt5.symbol_info(symbol)
  └─ Returns: SymbolInfo struct
     - point: 0.00001
     - trade_contract_size: 100000
     - trade_tick_value: 1.0       (USD per tick for 1 lot)
     - trade_tick_size: 0.00001
     - volume_min: 0.01
     - volume_max: 100.0
     - volume_step: 0.01
     - digits: 5
     - filling_mode: 1|2|4

Step 2: Account info
  account_info = mt5.account_info()
  └─ balance: 10000.00 USD

Step 3: Dalio sizing
  allocation_percent  = ASSET_ALLOCATIONS['EURUSD']  = 0.12
  allocated_capital   = 10000 × 0.12  = 1200.00
  risk_amount         = 1200 × 0.01   = 12.00 USD

Step 4: ATR-based SL/TP distances
  atr               = indicators['atr'] = 0.00045
  sl_distance       = 0.00045 × 4.5 = 0.002025  (price units)
  tp_distance       = 0.00045 × 6.5 = 0.002925

Step 5: Broker-specific lot calc
  value_per_point        = tick_value × (point/tick_size) = 1.0 × 1 = 1.0
  sl_distance_in_points  = 0.002025 / 0.00001 = 202.5

  lot_size = risk_amount / (sl_distance_in_points × value_per_point)
           = 12.00 / (202.5 × 1.0)
           = 0.0593

Step 6: Apply broker limits
  lot_size = round(0.0593 / 0.01) × 0.01 = 0.06
  lot_size = max(0.01, min(0.06, 100.0)) = 0.06

Step 7: SL/TP prices
  sl_price = round(1.08245 - 0.002025, 5) = 1.08043
  tp_price = round(1.08245 + 0.002925, 5) = 1.08538

Step 8: Build order request
  request = {
    "action":       TRADE_ACTION_DEAL,
    "symbol":       "EURUSD",
    "volume":       0.06,
    "type":         ORDER_TYPE_BUY,
    "price":        1.08245,
    "sl":           1.08043,
    "tp":           1.08538,
    "deviation":    20,
    "magic":        234000,
    "comment":      "Sunrise_LONG",
    "type_time":    ORDER_TIME_GTC,
    "type_filling": ORDER_FILLING_IOC
  }

Step 9: Send order
  result = mt5.order_send(request)

  result schema:
    .retcode:  10009 (TRADE_RETCODE_DONE) means success
    .deal:     12345678
    .order:    87654321
    .volume:   0.06
    .price:    1.08245
    .comment:  "Request executed"
```

---

## 7. CHART RENDERING DATA FLOW

```
chart_data[symbol] (per monitor cycle)
       │
       │  refresh_chart() called by GUI
       │
       ▼
plot_candlesticks(ax, df.tail(100))
       │
       ├── Vẽ OHLC candles
       ├── Overlay 4 EMAs (fast/medium/slow/filter)
       ├── Overlay window markers (nếu WINDOW_OPEN)
       │     - Top limit (green dashed)
       │     - Bottom limit (red dashed)
       └── Update tab "Charts"
```

---

## 8. LOG/EVENT DATA FLOW

```
                    ┌───────────────────────┐
                    │  monitor_thread       │
                    │  (background)         │
                    └──────┬────────────────┘
                           │ terminal_log(msg, level, critical)
                           │
                           ▼
              ┌───────────────────────────────┐
              │  Filter by level + critical   │
              │  (NORMAL/INFO/SUCCESS/ERROR…) │
              └──────┬────────────────────────┘
                     │
        ┌────────────┼─────────────┐
        ▼            ▼             ▼
  ┌──────────┐ ┌──────────┐  ┌─────────────┐
  │ stdout   │ │  Log file│  │ GUI Terminal│
  │ console  │ │ (UTF-8)  │  │ Tab         │
  └──────────┘ └──────────┘  └─────────────┘
                                     │
                                     │ via phase_update_queue
                                     ▼
                              Main Thread (Tkinter)
                              update text widget
```

---

## 9. CONFIG FLOW (Read-only)

```
strategies/sunrise_ogle_eurusd.py
         │
         │  parse_strategy_config(file_path, "EURUSD")
         │  - Read file UTF-8
         │  - Regex: param = value
         │  - Strip quotes/comments
         │
         ▼
strategy_configs["EURUSD"] = {
    "ema_fast_length":            "18",
    "ema_medium_length":          "18",
    "ema_slow_length":            "24",
    "long_atr_sl_multiplier":     "4.5",
    "long_atr_tp_multiplier":     "6.5",
    "LONG_USE_PULLBACK_ENTRY":    "True",
    "LONG_PULLBACK_MAX_CANDLES":  "2",
    "LONG_ENTRY_WINDOW_PERIODS":  "10",
    "USE_WINDOW_TIME_OFFSET":     "False",
    "USE_TIME_RANGE_FILTER":      "True",
    "ENTRY_START_HOUR":           "8",
    "ENTRY_END_HOUR":             "16",
    ...
    "_config_valid":              True,
    "_symbol":                    "EURUSD"
}
         │
         ▼
validate_critical_params() → đảm bảo có đủ 8-12 params bắt buộc
```

---

## 10. TIME/TIMEZONE FLOW

```
MT5 Broker Time (e.g., UTC+1 winter, UTC+2 summer)
         │
         ▼
df['time'] (datetime, "naive", broker timezone)
         │
         ▼ _validate_time_filter()
         │
strategy_time_utc = broker_time - timedelta(hours=broker_utc_offset)
         │
         ▼
Compare against:
  ENTRY_START_HOUR / ENTRY_END_HOUR  (UTC values from strategy)
```

**Sources cho `broker_utc_offset`:**
1. GUI dropdown (UTC+1/+2/+3)
2. `config/broker_timezone.json`
3. Default: 1 (UTC+1)

---

## 11. THREADING DATA SAFETY

| Resource | Thread Access | Safe? |
|----------|--------------|-------|
| `strategy_states` | Monitor thread (W/R), Main thread (R) | ⚠️ No lock — relies on GIL + atomic dict ops |
| `chart_data` | Monitor thread (W), Main thread (R) | ⚠️ Same |
| GUI widgets | Main thread ONLY | ✅ Use `root.after(0, fn)` cross-thread |
| `phase_update_queue` | Multi-thread | ✅ `queue.Queue` is thread-safe |
| `mt5.*` API | Monitor thread | ✅ MT5 lib handles internal locking |
| State JSON file | Monitor thread | ✅ Atomic write (.tmp + rename) |
| `terminal_log` | Multi-thread | ⚠️ Uses queue for GUI updates |

**Note:** Hệ thống không dùng explicit `threading.Lock`, dựa vào:
- Python GIL cho dict operations
- Atomic file rename cho persistence
- `queue.Queue` cho GUI updates
- `root.after(0, ...)` cho thread-safe Tkinter calls
