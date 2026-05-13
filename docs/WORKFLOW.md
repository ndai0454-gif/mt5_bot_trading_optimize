# 🔄 WORKFLOW — Step-by-Step Operation

> **Mục đích:** Mô tả tuần tự mọi bước từ khi user khởi động bot đến khi đóng lệnh.

---

## 🚀 PHẦN A: KHỞI ĐỘNG (BOOT SEQUENCE)

### STEP A1 — User chạy bot
```bash
python advanced_mt5_monitor_gui.py
# hoặc
dist/MT5_Trading_Bot.exe
```

### STEP A2 — `main()` function (line 4576)
```
1. In banner version
2. Check DEPENDENCIES_AVAILABLE (MT5, pandas, numpy)
   ├─ Thiếu → in error, exit
3. Check MATPLOTLIB_AVAILABLE (optional)
   ├─ Thiếu → warning, tiếp tục không có chart
4. Tạo tk.Tk() root window
5. Khởi tạo AdvancedMT5TradingMonitorGUI(root)
6. root.mainloop()
```

### STEP A3 — `__init__()` (line 200)

```
1. Set title, geometry "1600x1000"
2. Khởi tạo state dicts:
   ├─ strategy_states = {}
   ├─ strategy_configs = {}
   ├─ chart_data = {}
   ├─ window_markers = {}
   ├─ config_errors = {}
3. Set bot_startup_time = datetime.now()
4. load_utc_offset_from_config()
   └─ Đọc config/broker_timezone.json (default UTC+1)
5. Khởi tạo threading: stop_event, phase_update_queue
6. setup_logging() → console + mt5_advanced_monitor.log (UTF-8)
7. setup_gui() → Left/Right panel + status bar
8. initialize_mt5_connection()
9. load_strategy_configurations()
10. Bind WM_DELETE_WINDOW → on_closing()
11. process_phase_updates() → schedule queue poll
```

### STEP A4 — `initialize_mt5_connection()` (line 957)
```
1. mt5.initialize()
   ├─ Fail → return False
2. account_info = mt5.account_info()
   ├─ None → shutdown + fail
3. Set mt5_connected = True
4. Update GUI: "Connected" + green
5. initialize_signal_processing() (legacy, ít dùng)
```

### STEP A5 — `load_strategy_configurations()` (line 605)
Cho mỗi symbol trong `["EURUSD", "GBPUSD", "XAUUSD", "AUDUSD", "XAGUSD", "USDCHF", "EURJPY", "USDJPY"]`:

```
1. digits = mt5.symbol_info(symbol).digits  (5/3/2 tùy asset)
2. Init strategy_states[symbol] = {entry_state='SCANNING', current_bar=0, ...}
3. Đường dẫn: strategies/sunrise_ogle_{symbol_lower}.py
4. parse_strategy_config(file_path, symbol)
   ├─ Đọc file → regex match 60+ params (line 756-838)
   ├─ Store cả key dạng `Fast EMA Period` và `ema_fast_length`
5. validate_critical_params()
   ├─ Check CRITICAL_PARAMS_CORE (8 params)
   ├─ Nếu ENABLE_SHORT_TRADES → check CRITICAL_PARAMS_SHORT (4 params)
   ├─ Missing → _config_valid=False, schedule retry sau 5min
6. Update symbol_combo dropdown
```

### STEP A6 — User click "Start Monitoring"
→ `start_monitoring()` (line 1245)
```
1. Check mt5_connected → fail nếu chưa connect
2. load_strategy_state()
   ├─ Đọc mt5_strategy_state.json (nếu có)
   ├─ Check age > 30min → discard (stale)
   ├─ Validate entry_state nằm trong VALID_ENTRY_STATES
   ├─ Restore các scalar fields + datetimes
3. monitoring_active = True
4. Tạo daemon thread: advanced_monitoring_loop()
5. In startup summary với version, pairs, timeframe
```

---

## 🔁 PHẦN B: MONITORING LOOP (HEARTBEAT)

### STEP B1 — `advanced_monitoring_loop()` (line 1303, chạy trong thread)

```python
while monitoring_active and not stop_event.is_set():
    current_minute = datetime.now().minute
    current_second = datetime.now().second
    
    # SMART POLL: Chỉ check khi M5 candle close
    is_candle_close_time = (current_minute % 5 == 0) and (current_second <= 10)
    
    if is_candle_close_time:
        check_key = "YYYY-MM-DD HH:MM"
        
        # Log 1 lần / 5 phút
        if last_candle_check.get('last_candle_log') != check_key:
            log("CANDLE CLOSE DETECTED")
        
        # Process từng symbol
        for symbol in strategy_states.keys():
            if last_candle_check.get(symbol) != check_key:
                monitor_strategy_phase(symbol)   # ← MAIN WORK
                last_candle_check[symbol] = check_key
        
        save_strategy_state()           # JSON snapshot
        root.after(0, update_strategy_displays)   # GUI refresh
        
    # Hourly summary
    if time.time() - last_summary >= 3600:
        log_hourly_summary()
        last_summary = time.time()
    
    time.sleep(CANDLE_CHECK_SLEEP_SECONDS)   # = 5 giây
```

### STEP B2 — `monitor_strategy_phase(symbol)` (line 1358)

```
[1] Config validity check
    ├─ Invalid → check retry timer (5min)
    │  └─ Retry → retry_load_config(symbol)
    └─ Vẫn invalid → SKIP symbol này

[2] Fast Path (chỉ khi WINDOW_OPEN)
    ├─ Fetch 101 bars (ít hơn full path)
    ├─ Remove forming candle
    ├─ Increment current_bar nếu candle timestamp mới
    ├─ Reuse cached indicators
    ├─ Call determine_strategy_phase() → check breakout
    └─ Update chart_data + return EARLY

[3] Full Path (SCANNING / ARMED states)
    ├─ Fetch BARS_TO_FETCH=151 bars
    ├─ IPC fail → attempt_reconnect() với exponential backoff
    ├─ Remove forming candle (df.iloc[:-1])
    ├─ Verify len(df) >= MIN_BARS_REQUIRED=100
    ├─ calculate_indicators(df, symbol)
    │   └─ Trong đó gọi detect_ema_crossovers() ← phát hiện signal
    ├─ determine_strategy_phase(symbol, df, indicators) ← state machine
    ├─ Update strategy_states[symbol]
    │   ├─ Log phase transition (NORMAL → WAITING_PULLBACK etc.)
    │   └─ log_phase_summary()
    └─ Update chart_data với df.tail(100)
```

---

## 🧮 PHẦN C: SIGNAL DETECTION (PER CANDLE)

### STEP C1 — `calculate_indicators(df, symbol)` (line 2343)
```
1. Lấy params từ strategy_configs[symbol]:
   ├─ ema_fast_length (default 18)
   ├─ ema_medium_length (default 18)
   ├─ ema_slow_length (default 24)
   ├─ ema_filter_price_length (default 100)
   └─ atr_length (default 10)

2. Verify len(df) >= max(periods)

3. Tính EMA (adjust=False — match MT5/Backtrader):
   ├─ ema_fast = df['close'].ewm(span=fast, adjust=False).mean()[-1]
   ├─ ema_medium
   ├─ ema_slow
   ├─ ema_filter
   └─ ema_confirm = EMA(1) ≈ close price

4. Tính ATR (True Range rolling mean):
   ├─ high_low = high - low
   ├─ high_close = abs(high - close.shift())
   ├─ low_close = abs(low - close.shift())
   ├─ true_range = max(high_low, high_close, low_close)
   └─ atr = true_range.rolling(atr_period).mean()[-1]

5. Trend label:
   ├─ BULLISH:  ema_fast > ema_medium > ema_slow
   ├─ BEARISH:  ema_fast < ema_medium < ema_slow
   └─ SIDEWAYS: otherwise

6. → detect_ema_crossovers(symbol, indicators, df)
```

### STEP C2 — `detect_ema_crossovers()` (line 2074)
```
1. Anti-duplicate: Check current_closed_candle_time != last_processed
   └─ Đã process → SKIP

2. Mark candle as processed

3. Compute 4 EMA series trên df (closed candles)

4. Phát hiện BULLISH crossover (đếm 1-3 đường):
   ├─ confirm > fast  AND  prev_confirm <= prev_fast
   ├─ confirm > medium AND prev_confirm <= prev_medium
   └─ confirm > slow  AND  prev_confirm <= prev_slow

5. Phát hiện BEARISH crossover (mirror)

6. Stale check: candle_time < bot_startup_time → discard

7. ▼ 6-LAYER FILTER CASCADE (chỉ cho LONG/BULLISH):
   
   Filter 1: _validate_atr_filter
       └─ ATR range + increment + decrement
   
   Filter 2: _validate_angle_filter
       └─ EMA slope angle (atan)
   
   Filter 3: _validate_price_filter
       └─ close > filter_EMA (LONG)
   
   Filter 4: _validate_candle_direction
       └─ Previous candle bullish (close > open)
   
   Filter 5: _validate_ema_ordering
       └─ confirm > fast, medium, slow (all)
   
   Filter 6: _validate_ema_position_filter
       └─ close > all EMAs

   IF ANY filter fails → bullish_crossover = False, REJECT

8. Bearish crossover được PRESERVE cho Global Invalidation
   (dù SHORT disabled, vẫn cần để reset ARMED_LONG)

9. Lưu crossover_data vào strategy_states[symbol]
```

---

## 🎯 PHẦN D: STATE MACHINE PROCESSING

### STEP D1 — `determine_strategy_phase()` (line 2768)

#### Pre-checks (chạy trước mọi phase):
```
A. Orphan detection
   └─ Nếu position mở mà state ≠ IN_TRADE → sync IN_TRADE

B. ARMED_SHORT emergency reset
   └─ Tất cả assets LONG-only theo default

C. IN_TRADE check
   ├─ positions = []  → position đã đóng → reset SCANNING
   └─ positions exist → SKIP (lock until close)

D. Bar counter increment
   └─ Nếu df['time'][-1] != last_candle_time → current_bar++

E. Global Invalidation (ARMED states)
   ├─ ARMED_LONG + bearish_cross + RED candle → RESET
   └─ ARMED_SHORT + bullish_cross + GREEN candle → RESET
```

#### PHASE 1 — SCANNING → ARMED (line 2927)
```
IF bullish_crossover:    signal_direction = 'LONG'
ELIF bearish_crossover AND short_enabled: signal_direction = 'SHORT'

IF signal_direction:
    Clear crossover flags (tránh re-arming)
    Store signal_detection_atr (cho filter sau)
    
    use_pullback = config['LONG_USE_PULLBACK_ENTRY']
    
    IF use_pullback == True:
        entry_state = 'ARMED_LONG'
        phase = 'WAITING_PULLBACK'
        pullback_candle_count = 0
        Store signal_trigger_candle = OHLC của Bar -1
        Initialize candle_sequence_counter = 0
        ── go to PHASE 2 next candle
    ELSE:
        Log "STANDARD MODE - Enter immediately"
        _execute_entry(symbol, direction, df, current_dt, config)
        Reset → SCANNING
```

#### PHASE 2 — ARMED → WINDOW_OPEN (line 3042)
```
1. DataFrame Integrity Check:
   └─ time.diff() phát hiện gap > 5 phút → warning

2. Bulletproof Gap Detection:
   ├─ unprocessed = df[df['time'] > last_pullback_check_candle]
   ├─ 0 candles → đã xử lý hết, chờ candle mới
   ├─ 1 candle  → normal flow
   └─ >1 candles → GAP! Process all consecutively

3. FOR each unprocessed candle:
   3.1 Global Invalidation per-candle:
       ├─ check_crossover_at_candle() tại idx này
       ├─ ARMED_LONG + bearish + red → INVALIDATE return SCANNING
       └─ ARMED_SHORT + bullish + green → INVALIDATE
   
   3.2 Pullback check:
       ├─ LONG pullback = bearish candle (close < open)
       ├─ SHORT pullback = bullish candle (close > open)
       
       IF correct color:
           pullback_candle_count++
           IF count >= MAX_PULLBACK_CANDLES:
               Store last_pullback_candle_high/low
               → _phase3_open_breakout_window() ★
               entry_state = 'WINDOW_OPEN'
               BREAK
       ELSE:
           Log "Wrong color - RESET"
           reset → SCANNING
           return
```

#### PHASE 3 — Open Breakout Window (line 2599) — gọi 1 lần duy nhất
```
1. window_start_bar = current_bar
   IF USE_WINDOW_TIME_OFFSET:
       offset = pullback_count * WINDOW_OFFSET_MULTIPLIER
       window_start_bar += int(offset)

2. window_expiry_bar = window_start_bar + ENTRY_WINDOW_PERIODS  (1-20)

3. Two-sided channel:
   candle_range = last_pullback_high - last_pullback_low
   price_offset = candle_range * WINDOW_PRICE_OFFSET_MULTIPLIER
   
   window_top_limit    = last_pullback_high + price_offset
   window_bottom_limit = last_pullback_low  - price_offset

4. State: entry_state = 'WINDOW_OPEN', phase = 'WAITING_BREAKOUT'
```

#### PHASE 4 — Monitor Window (line 3284 + 2675)
```
breakout_status = _phase4_monitor_window(symbol, df, direction, bar, dt, config)

Cases:
  PENDING  → current_bar < window_bar_start (chưa active)
  EXPIRED  → current_bar > window_expiry_bar
  None     → trong boundary, monitor tiếp
  
  SUCCESS  (LONG: high >= top_limit  /  SHORT: low <= bottom_limit):
      ├─ Time filter check
      │   ├─ Fail → reset SCANNING
      │   └─ Pass → continue
      │
      ├─ Re-validate filters với indicator MỚI (line 3315):
      │   1. EMA Ordering
      │   2. Price Filter
      │   3. EMA Position
      │   4. Angle Filter
      │   5. Trigger Candle Direction
      │   6. Time Filter (final check)
      │
      ├─ Bất kỳ fail → ABORT, reset SCANNING
      │
      └─ All pass → execute_trade() ★★★
  
  FAILURE  (price ngược boundary):
      ├─ entry_state = 'ARMED_{direction}'
      ├─ pullback_candle_count = 0
      └─ Quay lại Phase 2 tìm pullback mới
  
  EXPIRED:
      ├─ entry_state = 'ARMED_{direction}'
      ├─ pullback_candle_count = 0
      └─ Tương tự FAILURE
```

---

## 💰 PHẦN E: ORDER EXECUTION

### STEP E1 — `_execute_entry()` (line 4210) — STANDARD MODE (không pullback)
```
1. Verify df có data
2. entry_price = df['close'].iloc[-1]
3. _is_in_trading_time_range() check
4. Call execute_trade()
5. IF success:
   ├─ entry_state = 'IN_TRADE'
   ├─ phase = 'TRADE_ACTIVE'
   └─ Lock until position closes
```

### STEP E2 — `execute_trade()` (line 4259) — CORE ORDER LOGIC
```
1. mt5.symbol_info(symbol) → get specs
   IF not symbol_info.visible → mt5.symbol_select()

2. mt5.account_info() → get balance

3. DUPLICATE CHECK:
   positions = mt5.positions_get(symbol=symbol)
   IF positions exist → SKIP (return False)

4. RAY DALIO POSITION SIZING:
   balance              = account_info.balance
   allocation_percent   = ASSET_ALLOCATIONS[symbol]   # e.g. 0.18
   allocated_capital    = balance * allocation_percent
   risk_percent         = config['RISK_PER_TRADE']    # 0.01 default
   risk_amount          = allocated_capital * risk_percent

5. GET ATR (từ indicators cache):
   atr = strategy_states[symbol]['indicators']['atr']
   IF invalid → ERROR, return False

6. ATR-based SL/TP:
   sl_distance = atr * 4.5    (default LONG)
   tp_distance = atr * 6.5    (default LONG)

7. BROKER-SPECIFIC LOT CALC (KHÔNG hardcode!):
   point         = symbol_info.point
   tick_value    = symbol_info.trade_tick_value
   tick_size     = symbol_info.trade_tick_size
   
   value_per_point = tick_value * (point / tick_size)
   sl_distance_in_points = sl_distance / point
   
   lot_size = risk_amount / (sl_distance_in_points * value_per_point)

8. Apply broker limits:
   lot_size = round(lot_size / lot_step) * lot_step
   lot_size = max(lot_min, min(lot_size, lot_max))

9. Compute SL/TP prices:
   LONG:  sl = entry - sl_distance,  tp = entry + tp_distance
   SHORT: sl = entry + sl_distance,  tp = entry - tp_distance
   
   sl_price = round(sl_price, digits)
   tp_price = round(tp_price, digits)

10. DETECT FILLING MODE:
    IF filling_mode & 2: IOC
    ELIF filling_mode & 1: FOK
    ELIF filling_mode & 4: RETURN
    ELSE: FOK (fallback)

11. BUILD ORDER REQUEST:
    {
        "action":       TRADE_ACTION_DEAL,
        "symbol":       symbol,
        "volume":       lot_size,
        "type":         ORDER_TYPE_BUY/SELL,
        "price":        entry_price,
        "sl":           sl_price,
        "tp":           tp_price,
        "deviation":    20,
        "magic":        234000,
        "comment":      f"Sunrise_{direction}",
        "type_time":    ORDER_TIME_GTC,
        "type_filling": filling_type,
    }

12. result = mt5.order_send(request)
    IF result is None → ERROR
    IF result.retcode != TRADE_RETCODE_DONE → ERROR
    
13. SUCCESS:
    ├─ Log Order#, Deal#, Volume, Price
    └─ State updated bởi caller (entry_state = IN_TRADE)
```

---

## 🔚 PHẦN F: POSITION LIFECYCLE & SHUTDOWN

### STEP F1 — Position Open → Monitoring
- Bot không quản lý exit logic (SL/TP đặt sẵn ở MT5)
- `determine_strategy_phase()` mỗi candle check `positions_get()`
- Nếu position đã đóng (SL/TP hit) → reset → SCANNING

### STEP F2 — `stop_monitoring()` (line 1288)
```
1. monitoring_active = False
2. stop_event.set()  → thread thoát loop
3. save_strategy_state() → JSON snapshot
4. Update GUI buttons
```

### STEP F3 — `on_closing()` (line 4559)
```
1. Confirm dialog
2. stop_monitoring()
3. disconnect_mt5() → mt5.shutdown()
4. root.destroy()
```

---

## 📊 LỊCH ĐỒ THỜI GIAN (TYPICAL CYCLE)

```
T+0:00  [Boot] User chạy bot
T+0:01  Init GUI, connect MT5, load configs
T+0:02  User click "Start Monitoring"
T+0:03  Monitor thread khởi động, load saved state
T+0:05  ★ M5 candle close → process all 8 symbols
        ├─ Fetch 151 bars
        ├─ Calculate EMA + ATR
        ├─ Detect crossover (nếu có)
        ├─ Run 6 filters
        └─ Update state machine

T+0:05:10  (After 10s window) Save JSON state, update GUI

T+0:10  ★ Next M5 candle close → repeat

…

T+0:25  [SCENARIO] BULLISH CROSSOVER detected ở EURUSD
        ├─ All 6 filters PASS
        ├─ entry_state: SCANNING → ARMED_LONG
        └─ Waiting for pullback...

T+0:30  ★ New candle = BEARISH (đúng pullback color)
        ├─ pullback_count = 1
        └─ Need 1 more

T+0:35  ★ New candle = BEARISH
        ├─ pullback_count = 2/2 ✅
        ├─ Open window: top/bottom limits
        └─ entry_state: ARMED_LONG → WINDOW_OPEN

T+0:40  ★ Price > top_limit → SUCCESS breakout
        ├─ Re-validate 6 filters
        ├─ Time filter check
        ├─ execute_trade()
        │   ├─ Calculate lot size (Dalio + ATR SL/TP)
        │   ├─ mt5.order_send()
        │   └─ Order #12345 filled @ 1.08423
        └─ entry_state: WINDOW_OPEN → IN_TRADE

T+0:45  ★ State machine SKIP (IN_TRADE locked)

…

T+5:30  Position hit TP → mt5.positions_get(symbol) = []
        ├─ entry_state: IN_TRADE → SCANNING
        └─ Unlock for new signals
```

---

## ⚠️ ERROR HANDLING WORKFLOW

### Khi MT5 IPC fail (Error -10001):
```
1. attempt_reconnect()
2. backoff = 2 * (2 ^ (attempts - 1))   # 2s, 4s, 8s
3. mt5.shutdown() + sleep + mt5.initialize()
4. Success → reset counter
5. Max 3 retries → ERROR + manual intervention required
```

### Khi config thiếu params:
```
1. Mark config['_config_valid'] = False
2. SKIP symbol mỗi monitor cycle
3. After 5 phút → retry_load_config()
4. Persistent miss → keep retrying (user phải fix file)
```

### Khi indicator/filter throw exception:
```
1. except → terminal_log(error)
2. return False (BLOCK trade)  ← KHÔNG return True (an toàn)
3. Continue next cycle
```

---

## 🎓 TÓM TẮT — 1 CÂU MỖI PHASE

| Phase | Mô tả |
|-------|-------|
| **A. Boot** | Khởi tạo GUI + MT5 + load 8 strategy configs |
| **B. Loop** | Polling smart mỗi 5 phút khi M5 candle close |
| **C. Signal** | Calculate EMA/ATR → detect crossover → 6 filters validate |
| **D. State** | SCANNING → ARMED (filter pass) → pullback wait → WINDOW (breakout) → ENTRY |
| **E. Execute** | Dalio sizing + broker-specific lot calc + ATR SL/TP → mt5.order_send() |
| **F. Shutdown** | Stop thread + save state JSON + close MT5 |
