# 🚀 OPTIMIZE — Đánh giá & Tối ưu hoá cho XAUUSD

> **Phạm vi:** XAUUSD (Gold) trên MT5 Live Trading Bot
> **Tham chiếu:** `trading_strategy.md` (Risk-first Approach) + `logic.md` + `STATE_MACHINE.md` + code hiện tại
> **Mục tiêu:** Đối chiếu spec ↔ implementation → đề xuất cải tiến cụ thể

---

## 1. EXECUTIVE SUMMARY

| Mục | Spec yêu cầu | Code hiện tại | Trạng thái |
|-----|--------------|---------------|-----------|
| Risk per trade | 1% account_balance | 1% × 18% allocated (≈ 0.18% tổng) | ⚠️ **MISMATCH** |
| SL/TP bắt buộc | Mọi lệnh phải có | Có (ATR-based) | ✅ OK |
| R:R ratio | 1:2 → 1:3 | 1:1.44 (4.5:6.5) | ❌ **VIOLATE** |
| TP Splitting (4 phần) | TP1=30%, TP2=20%, TP3=30%, TP4=20% | Single TP | ❌ **CHƯA CÓ** |
| Scaling (nhồi lệnh) | 1 base + 3 scaling khi TP1+TP2 hit | Không có | ❌ **CHƯA CÓ** |
| Move SL to entry | Sau khi scale | Không có | ❌ **CHƯA CÓ** |
| Long-term survivability | Capital protection first | Có Dalio + filter | ✅ Phù hợp |

**Kết luận:** Code hiện tại **không đáp ứng đầy đủ** spec trading_strategy.md. Cần refactor lớn ở 3 mảng: **R:R config, Partial TP system, Scaling system**.

---

## 2. PHÂN TÍCH CHI TIẾT KHÔNG TƯƠNG THÍCH

### 🔴 Vấn đề #1: RISK PER TRADE TÍNH SAI THEO SPEC

**Spec (trading_strategy.md §2.2):**
```
risk_per_trade = 1% × account_balance
Account: $1000  →  Risk: $10
```

**Code hiện tại (`execute_trade` line 4307-4318):**
```python
balance              = account_info.balance              # = $1000
allocation_percent   = ASSET_ALLOCATIONS['XAUUSD'] = 0.18  # 18%
allocated_capital    = balance * allocation_percent      # = $180
risk_percent         = config.get('RISK_PER_TRADE', 0.01)  # 1%
risk_amount          = allocated_capital * risk_percent  # = $1.80 ❌
```

**Hệ quả với XAUUSD:**
- Spec yêu cầu: $10 risk trên $1000
- Code thực tế: $1.80 risk trên $1000 (5.5x ÍT HƠN)
- Kết quả: lot size quá nhỏ → lợi nhuận tuyệt đối giảm tương ứng

### 🔧 Cách tối ưu:

**Option A — Disable Dalio cho XAUUSD (tuân thủ spec gốc):**
```python
# Trong execute_trade(), thêm flag override
USE_DALIO_ALLOCATION = config.get('USE_DALIO_ALLOCATION', True)

if USE_DALIO_ALLOCATION:
    allocated_capital = balance * allocation_percent
    risk_amount = allocated_capital * risk_percent
else:
    # Risk-first spec: 1% × balance trực tiếp
    risk_amount = balance * risk_percent
```

**Option B — Tăng `risk_percent` để bù:**
```python
# Trong sunrise_ogle_xauusd.py:
risk_percent = 0.0556  # = 1% / 18% allocation → effective 1% balance
```
⚠️ Không khuyến nghị — confusing và ảnh hưởng `validate` logic.

**Option C (KHUYẾN NGHỊ) — Hybrid:**
- Giữ Dalio cho portfolio diversification
- Thêm `risk_mode` config: `'allocated' | 'balance'`
- Cho phép XAUUSD chọn `'balance'` (ưu tiên spec)

---

### 🔴 Vấn đề #2: R:R RATIO VIOLATE SPEC

**Spec (trading_strategy.md §2.1):**
```
R:R ∈ [1:2, 1:3]
```

**Code hiện tại (`sunrise_ogle_xauusd.py:357-358`):**
```python
long_atr_sl_multiplier = 4.5   # SL = 4.5 × ATR
long_atr_tp_multiplier = 6.5   # TP = 6.5 × ATR
```

**Tính R:R thực tế:**
```
R:R = TP / SL = 6.5 / 4.5 = 1.444  ❌ THẤP HƠN MIN 1:2
```

### 🔧 Cách tối ưu:

```python
# OPTIONS để đạt 1:2 → 1:3:
long_atr_sl_multiplier = 2.5   # Giảm SL tighter
long_atr_tp_multiplier = 5.0   # Giảm TP nhưng tăng R:R = 1:2

# HOẶC giữ TP cao, giảm SL:
long_atr_sl_multiplier = 2.0
long_atr_tp_multiplier = 6.0   # R:R = 1:3 ✅

# HOẶC nếu muốn TP1/TP2/TP3/TP4 (xem #3 dưới đây):
long_atr_sl_multiplier = 2.5
long_atr_tp1_multiplier = 5.0    # TP1 = 1:2
long_atr_tp2_multiplier = 6.25   # TP2 = 1:2.5
long_atr_tp3_multiplier = 7.5    # TP3 = 1:3
long_atr_tp4_multiplier = 8.75   # TP4 = 1:3.5
```

⚠️ **Cảnh báo backtesting:** Strategy file là READ-ONLY (`docs/STRATEGY_FILES_POLICY.md`) — phải backtest lại bộ params mới trước khi deploy live.

---

### 🔴 Vấn đề #3: KHÔNG CÓ TP SPLITTING (4-PARTIAL)

**Spec (trading_strategy.md §2.3):**
```
TP1: 30% volume
TP2: 20% volume
TP3: 30% volume
TP4: 20% volume
```

**Code hiện tại:** `execute_trade()` chỉ gửi 1 order với 1 TP duy nhất (line 4470-4471):
```python
sl_price = price - sl_distance
tp_price = price + (atr * atr_tp_multiplier)
# Không có TP1/TP2/TP3/TP4
```

### 🔧 Cách tối ưu — Triển khai Multi-TP:

#### Approach 1: Pending Limit Orders song song
```python
def execute_trade_with_partial_tp(symbol, direction, price, lot_size, sl, atr, config):
    # Chia volume theo spec
    tp_split = {
        'tp1': {'pct': 0.30, 'multiplier': 5.0},
        'tp2': {'pct': 0.20, 'multiplier': 6.25},
        'tp3': {'pct': 0.30, 'multiplier': 7.5},
        'tp4': {'pct': 0.20, 'multiplier': 8.75},
    }
    
    # 1. Mở position chính với SL chung, KHÔNG có TP
    main_request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot_size,
        "type": ORDER_TYPE_BUY if direction=='LONG' else ORDER_TYPE_SELL,
        "price": price,
        "sl": sl,
        "tp": 0,  # Không TP ở order chính
        "magic": 234000,
        "comment": f"Sunrise_{direction}_BASE",
    }
    main_result = mt5.order_send(main_request)
    if main_result.retcode != TRADE_RETCODE_DONE:
        return False
    
    position_ticket = main_result.order
    
    # 2. Đặt 4 limit orders TP cho từng phần
    cumulative_pct = 0
    for tp_name, tp_data in tp_split.items():
        partial_volume = round(lot_size * tp_data['pct'] / lot_step) * lot_step
        if direction == 'LONG':
            tp_price = price + (atr * tp_data['multiplier'])
            close_type = ORDER_TYPE_SELL  # Close LONG = SELL limit
        else:
            tp_price = price - (atr * tp_data['multiplier'])
            close_type = ORDER_TYPE_BUY
        
        partial_request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": partial_volume,
            "type": ORDER_TYPE_SELL_LIMIT if direction=='LONG' else ORDER_TYPE_BUY_LIMIT,
            "price": tp_price,
            "magic": 234000 + len(tp_split) - cumulative_pct,  # Unique magic
            "comment": f"Sunrise_{direction}_{tp_name.upper()}",
            "type_time": ORDER_TIME_GTC,
            "type_filling": filling_type,
        }
        mt5.order_send(partial_request)
        cumulative_pct += 1
    
    return position_ticket
```

⚠️ **Lưu ý:**
- MT5 hedging accounts hỗ trợ multiple positions/symbol → dùng tickets riêng dễ
- MT5 netting accounts (default cho FX/Gold) → CHỈ 1 position/symbol → phải dùng pending close orders thay vì position chia nhỏ

#### Approach 2: Manual partial close khi giá chạm TP

```python
def monitor_partial_tp(self, symbol):
    """Theo dõi position, partial close khi chạm TP1, TP2, TP3, TP4"""
    state = self.strategy_states[symbol]
    if state['entry_state'] != 'IN_TRADE':
        return
    
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return
    
    pos = positions[0]
    current_price = mt5.symbol_info_tick(symbol).bid if pos.type == 0 else mt5.symbol_info_tick(symbol).ask
    
    # Stored TP levels khi vào lệnh
    tp_levels = state.get('tp_levels', [])  # [(tp1_price, tp1_volume_pct, hit), ...]
    
    for i, (tp_price, vol_pct, already_hit) in enumerate(tp_levels):
        if already_hit:
            continue
        
        is_hit = (
            (pos.type == 0 and current_price >= tp_price) or  # LONG
            (pos.type == 1 and current_price <= tp_price)      # SHORT
        )
        
        if is_hit:
            partial_volume = round(pos.volume * vol_pct / lot_step) * lot_step
            close_partial(symbol, pos.ticket, partial_volume, current_price)
            tp_levels[i] = (tp_price, vol_pct, True)  # Mark as hit
            
            # Trigger scaling check
            if i == 1:  # TP2 hit (>= 50% volume realized)
                self.check_scaling_opportunity(symbol)
```

---

### 🔴 Vấn đề #4: KHÔNG CÓ SCALING SYSTEM (NHỒI LỆNH)

**Spec (trading_strategy.md §3):**
```
- Reached TP1 + TP2 (≥ 50% TP)
- 75% H1 candle confirmation (no reversal)
- Max: 1 base + 3 scaling
- Move SL to entry after each scaling
```

**Code hiện tại:** Không có logic nào.

### 🔧 Cách tối ưu — Scaling State Machine:

```python
# Mở rộng state machine với states mới
VALID_ENTRY_STATES = [
    'SCANNING', 'ARMED_LONG', 'ARMED_SHORT', 'WINDOW_OPEN', 
    'IN_TRADE',                       # Position chính mở
    'IN_TRADE_TP1_HIT',              # TP1 đã chạm, partial closed 30%
    'IN_TRADE_TP2_HIT',              # TP2 đã chạm, sẵn sàng scale
    'SCALING_1', 'SCALING_2', 'SCALING_3',  # Đã scale lần n
    'IN_TRADE_FINAL',                # Đã scale max, chờ TP3+TP4
]

# Per-symbol scaling state
state['scaling'] = {
    'base_entry_price': 2000.00,
    'base_sl_price':    1990.00,
    'base_tp_levels':   [(2010, 0.30, False), (2014, 0.20, False), 
                         (2020, 0.30, False), (2024, 0.20, False)],
    'scaling_count':    0,                # 0 → 3 max
    'last_scale_time':  None,
    'scaling_orders':   [],               # List of (ticket, entry_price)
}

def check_scaling_opportunity(self, symbol):
    """Kiểm tra có nên scale không (sau khi TP2 hit)"""
    state = self.strategy_states[symbol]
    scaling = state.get('scaling', {})
    
    if scaling.get('scaling_count', 0) >= 3:
        self.terminal_log(f"{symbol}: Max scaling reached", "INFO")
        return False
    
    if state['entry_state'] not in ['IN_TRADE_TP2_HIT', 'SCALING_1', 'SCALING_2']:
        return False
    
    # Spec §3.1: 75% H1 candle confirmation (no reversal)
    if not self._validate_h1_no_reversal(symbol):
        return False
    
    # Đặt scaling order
    self._execute_scaling_entry(symbol)

def _validate_h1_no_reversal(self, symbol):
    """75% H1 candle confirmation - giá ko đảo chiều"""
    rates_h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 2)
    if rates_h1 is None or len(rates_h1) < 2:
        return False
    
    last_h1 = rates_h1[-1]
    candle_body = abs(last_h1['close'] - last_h1['open'])
    candle_range = last_h1['high'] - last_h1['low']
    
    if candle_range == 0:
        return False
    
    body_pct = candle_body / candle_range
    
    state = self.strategy_states[symbol]
    direction = state.get('armed_direction', 'LONG')
    
    # 75% body trong direction = không có reversal
    if direction == 'LONG':
        is_strong_bull = (last_h1['close'] > last_h1['open']) and body_pct >= 0.75
        return is_strong_bull
    else:
        is_strong_bear = (last_h1['close'] < last_h1['open']) and body_pct >= 0.75
        return is_strong_bear

def _execute_scaling_entry(self, symbol):
    state = self.strategy_states[symbol]
    scaling = state['scaling']
    
    current_tick = mt5.symbol_info_tick(symbol)
    if current_tick is None:
        return False
    
    direction = state['armed_direction']
    new_entry_price = current_tick.ask if direction == 'LONG' else current_tick.bid
    
    # Tính lot mới (cùng risk_amount như base hoặc giảm dần)
    # SPEC: 1% risk mỗi lần — KHÔNG tăng risk khi scaling
    new_lot = self._calculate_lot_size(symbol, scaling['base_sl_price'], new_entry_price)
    
    # Gửi order scale
    scale_request = {...}  # Tương tự execute_trade
    result = mt5.order_send(scale_request)
    
    if result.retcode == TRADE_RETCODE_DONE:
        scaling['scaling_count'] += 1
        scaling['scaling_orders'].append((result.order, new_entry_price))
        scaling['last_scale_time'] = datetime.now()
        
        # SPEC §3.3: Move SL của ALL existing positions to entry của lệnh trước đó
        self._move_sl_to_entry(symbol)
        
        state['entry_state'] = f"SCALING_{scaling['scaling_count']}"

def _move_sl_to_entry(self, symbol):
    """Move SL của tất cả positions hiện tại → entry của lệnh trước nó (risk-free)"""
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return
    
    state = self.strategy_states[symbol]
    scaling = state['scaling']
    
    # Sắp xếp positions theo time (oldest first)
    sorted_positions = sorted(positions, key=lambda p: p.time)
    
    for i, pos in enumerate(sorted_positions):
        if i == 0:
            # Position base → SL = entry (break-even)
            new_sl = pos.price_open
        else:
            # Position scaling N → SL = entry của position N-1
            new_sl = sorted_positions[i-1].price_open
        
        # Chỉ move SL nếu cải thiện (không downgrade SL)
        if pos.type == 0 and new_sl > pos.sl:  # LONG: SL phải cao hơn
            self._modify_position_sl(pos.ticket, new_sl, pos.tp)
        elif pos.type == 1 and new_sl < pos.sl:  # SHORT: SL phải thấp hơn
            self._modify_position_sl(pos.ticket, new_sl, pos.tp)

def _modify_position_sl(self, ticket, new_sl, tp):
    request = {
        "action":   mt5.TRADE_ACTION_SLTP,
        "position": ticket,
        "sl":       new_sl,
        "tp":       tp,
    }
    return mt5.order_send(request)
```

---

### 🟡 Vấn đề #5: POLLING LOOP CÓ BUG TIỀM NĂNG

**Code hiện tại (`monitor_strategy_phase` line 1532):**
```python
elif current_phase == 'WAITING_BREAKOUT':
    import random
    pullback_count = random.randint(1, 3)  # Simulate pullback count ❌
    state['pullback_count'] = pullback_count
```

**Vấn đề:** Pullback count đang được **simulate bằng random** thay vì lấy giá trị thật từ state machine. Đây là **bug nghiêm trọng** ảnh hưởng display & log.

### 🔧 Cách tối ưu:

```python
elif current_phase == 'WAITING_BREAKOUT':
    # Lấy giá trị THẬT từ state, không random
    pullback_count = state.get('pullback_candle_count', 0)
    transition_msg += f" | Pullback complete ({pullback_count} candles), window opening"
    state['window_active'] = True
```

---

### 🟡 Vấn đề #6: ATOMIC WRITE KHÔNG AN TOÀN TRÊN WINDOWS

**Code hiện tại (`save_strategy_state` line 1105-1107):**
```python
if os.path.exists(state_file):
    os.remove(state_file)
os.rename(temp_file, state_file)
```

**Vấn đề:** Khoảng giữa `os.remove` và `os.rename` → nếu crash → mất file state hoàn toàn.

### 🔧 Cách tối ưu:

```python
# Dùng os.replace() — atomic trên cả Windows & Unix (Python 3.3+)
os.replace(temp_file, state_file)  # Atomic swap, không cần xóa trước
```

---

### 🟡 Vấn đề #7: KHÔNG CÓ THREAD LOCK CHO STATE

**Code hiện tại:** `strategy_states[symbol]` được đọc/ghi từ:
- Monitor thread (mỗi 5 giây)
- Main thread (GUI updates qua `root.after()`)

**Rủi ro:** Race condition khi GUI đọc state lúc monitor đang ghi → đọc state nửa vời.

### 🔧 Cách tối ưu:

```python
import threading

class AdvancedMT5TradingMonitorGUI:
    def __init__(self, root):
        ...
        self.state_lock = threading.RLock()  # Re-entrant lock
        ...
    
    def monitor_strategy_phase(self, symbol):
        with self.state_lock:
            # Tất cả mutations vào strategy_states[symbol]
            ...
    
    def update_phases_tree(self):
        with self.state_lock:
            # Đọc state cho GUI
            for symbol, state in self.strategy_states.items():
                # Snapshot cần thiết
                ...
```

---

### 🟡 Vấn đề #8: TERMINAL LOG GỌI HOURLY SUMMARY MỖI MESSAGE

**Code hiện tại (`terminal_log` line 4087-4088):**
```python
# Check if it's time for hourly summary (but not if already in summary)
self.log_hourly_summary()  # Gọi MỖI message log!
```

**Vấn đề:** Mỗi log message → check `(now - last_hourly_summary).total_seconds() >= 3600`. Performance overhead không cần thiết khi log nhiều.

### 🔧 Cách tối ưu:

```python
# Cách A: Move check vào monitor loop chính
def advanced_monitoring_loop(self):
    while monitoring_active:
        ...
        # Check 1 lần per cycle thay vì mỗi log
        if time.time() - last_hourly_summary_check >= 60:
            self.log_hourly_summary()
            last_hourly_summary_check = time.time()
        ...

# Cách B: Schedule với root.after()
def schedule_hourly_summary(self):
    self.log_hourly_summary()
    self.root.after(3600 * 1000, self.schedule_hourly_summary)  # 1 hour
```

---

### 🟡 Vấn đề #9: NẾU ATR=0 SẼ INFINITE LOT

**Code hiện tại (`execute_trade` line 4347-4350):**
```python
if atr is None or atr <= 0 or (isinstance(atr, float) and pd.isna(atr)):
    self.terminal_log(f"[X] {symbol}: Invalid ATR value", "ERROR")
    return False
```

✅ Có check, nhưng:

**Vấn đề tiềm năng tại line 4402:**
```python
if value_per_point > 0 and sl_distance_in_points > 0:
    lot_size = risk_amount / (sl_distance_in_points * value_per_point)
```
Edge case: ATR rất nhỏ (e.g., 0.01 → sl_distance = 0.045 → 4.5 points cho XAUUSD) → lot_size = $1.80 / (4.5 × $1) = 0.4 lot → OK

Nhưng nếu config sai (ATR multiplier = 0) → infinite lot.

### 🔧 Cách tối ưu:

```python
# Thêm sanity check
MIN_SL_DISTANCE_POINTS = 50  # Tối thiểu 50 points (gold = 50 cents)
MAX_LOT_SAFETY = 5.0          # Hard cap

if sl_distance_in_points < MIN_SL_DISTANCE_POINTS:
    self.terminal_log(f"[X] {symbol}: SL distance quá nhỏ ({sl_distance_in_points} < {MIN_SL_DISTANCE_POINTS})", "ERROR")
    return False

lot_size = risk_amount / (sl_distance_in_points * value_per_point)

if lot_size > MAX_LOT_SAFETY:
    self.terminal_log(f"[!] {symbol}: Lot {lot_size} > safety cap, capping at {MAX_LOT_SAFETY}", "WARNING")
    lot_size = MAX_LOT_SAFETY
```

---

### 🟡 Vấn đề #10: EXIT LOGIC KHÔNG CÓ — DỰA HOÀN TOÀN VÀO MT5 SL/TP

**Code hiện tại:** Bot không có logic exit. Đặt SL/TP với MT5, để MT5 trigger.

**Vấn đề:**
- Nếu MT5 lỗi → SL/TP không trigger → loss tăng vô hạn
- Không thể implement trailing stop, time-based exit, EMA crossover exit
- Spec §6 yêu cầu monitoring để scaling → cần exit logic

### 🔧 Cách tối ưu — Thêm Exit Manager:

```python
def monitor_position_exits(self, symbol):
    """Chạy mỗi cycle khi entry_state in IN_TRADE*"""
    state = self.strategy_states[symbol]
    if not state['entry_state'].startswith('IN_TRADE') and not state['entry_state'].startswith('SCALING'):
        return
    
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return
    
    # 1. Check partial TP hits
    self.monitor_partial_tp(symbol)
    
    # 2. Check trailing stop (optional)
    if self._should_trail_stop(symbol):
        self._update_trailing_stop(symbol)
    
    # 3. Check EMA crossover exit (optional)
    if self._exit_on_opposite_crossover(symbol):
        self._close_all_positions(symbol)
    
    # 4. Check time-based exit (e.g., end of day)
    if self._should_close_by_time(symbol):
        self._close_all_positions(symbol)
    
    # 5. Trigger scaling check after TP hits
    self.check_scaling_opportunity(symbol)
```

---

## 3. ĐỀ XUẤT TỐI ƯU CHO XAUUSD CỤ THỂ

### 3.1 Bảng so sánh params hiện tại vs đề xuất

| Param | Hiện tại | Đề xuất | Lý do |
|-------|----------|---------|-------|
| `long_atr_sl_multiplier` | 4.5 | **2.5** | Đạt R:R 1:2 (spec) |
| `long_atr_tp_multiplier` | 6.5 | **6.25** | Total TP cho R:R 1:2.5 |
| `long_atr_tp1_multiplier` | — | **5.0** | TP1 = R:R 1:2 |
| `long_atr_tp2_multiplier` | — | **6.25** | TP2 = R:R 1:2.5 |
| `long_atr_tp3_multiplier` | — | **7.5** | TP3 = R:R 1:3 |
| `long_atr_tp4_multiplier` | — | **8.75** | TP4 = R:R 1:3.5 |
| `risk_percent` | 0.01 (× 18%) | **0.01** (× 100%) | Spec: 1% balance |
| `LONG_PULLBACK_MAX_CANDLES` | 3 | **2** | Cân bằng tần suất signal |
| `LONG_ENTRY_WINDOW_PERIODS` | 1 | **3-5** | Tránh miss breakout do window quá ngắn |
| `WINDOW_PRICE_OFFSET_MULTIPLIER` | 0.001 | **0.3** | XAUUSD spread biến động lớn |
| `ASSET_ALLOCATIONS['XAUUSD']` | 0.18 | **1.0** (nếu standalone) | Chạy single asset XAUUSD |
| `MAX_SCALING_ORDERS` | — | **3** | Spec §3.2 |
| `H1_CONFIRMATION_BODY_PCT` | — | **0.75** | Spec §3.1 |

### 3.2 File config mới cho XAUUSD (ngoài strategy file)

Tạo `config/xauusd_advanced.json`:
```json
{
    "use_dalio_allocation":     false,
    "risk_per_trade_mode":      "balance",
    "risk_per_trade_pct":       0.01,
    
    "use_partial_tp":           true,
    "tp_split": [
        {"name": "TP1", "volume_pct": 0.30, "atr_multiplier": 5.0},
        {"name": "TP2", "volume_pct": 0.20, "atr_multiplier": 6.25},
        {"name": "TP3", "volume_pct": 0.30, "atr_multiplier": 7.5},
        {"name": "TP4", "volume_pct": 0.20, "atr_multiplier": 8.75}
    ],
    
    "use_scaling":              true,
    "max_scaling_orders":       3,
    "scaling_trigger":          "tp2_hit",
    "h1_confirmation_pct":      0.75,
    "move_sl_after_scale":      true,
    "scaling_sl_mode":          "previous_entry",
    
    "use_trailing_stop":        false,
    "trailing_stop_atr_mult":   2.0,
    
    "max_lot_safety_cap":       5.0,
    "min_sl_distance_points":   50,
    
    "exit_on_opposite_signal":  false,
    "max_position_duration_h":  24
}
```

---

## 4. ROADMAP TRIỂN KHAI

### 🟢 PHASE 1 — Quick Wins (1-2 ngày)
1. ✅ Fix random pullback count (line 1532)
2. ✅ Replace `os.remove + os.rename` → `os.replace` (line 1105)
3. ✅ Move `log_hourly_summary` ra khỏi terminal_log
4. ✅ Thêm safety cap cho lot_size + min SL distance check
5. ✅ Disable Dalio allocation cho XAUUSD (config flag)
6. ✅ Update `long_atr_sl_multiplier=2.5`, `long_atr_tp_multiplier=6.25` (R:R 1:2.5)

### 🟡 PHASE 2 — Risk Management (3-5 ngày)
7. ✅ Thread lock cho `strategy_states`
8. ✅ Thêm `monitor_position_exits()` method
9. ✅ Implement partial close logic (TP1/TP2/TP3/TP4)
10. ✅ Track `tp_levels_hit` trong state dict
11. ✅ Test partial close trên DEMO account

### 🔴 PHASE 3 — Scaling System (1-2 tuần)
12. ✅ Mở rộng `VALID_ENTRY_STATES` với SCALING_1/2/3
13. ✅ Implement `check_scaling_opportunity()`
14. ✅ Implement `_validate_h1_no_reversal()`
15. ✅ Implement `_execute_scaling_entry()`
16. ✅ Implement `_move_sl_to_entry()`
17. ✅ Test toàn bộ flow scale trên DEMO
18. ✅ Backtest scale logic với historical data

### 🔵 PHASE 4 — Advanced Features (2-4 tuần)
19. Implement trailing stop logic
20. EMA crossover exit
21. Time-based exit
22. Performance dashboard cho R:R, win rate, drawdown
23. Audit log cho mọi scaling decision

---

## 5. RỦI RO & TRADE-OFFS

| Tối ưu | Risk | Mitigation |
|--------|------|------------|
| Tăng risk từ 0.18% → 1% balance | 5x drawdown nhanh hơn | Backtest kỹ, start với demo |
| Giảm SL multiplier 4.5→2.5 | Stop out nhiều hơn (ATR ngắn) | Window filter giúp lọc fake breakout |
| Multi-TP partial close | Phức tạp hơn để debug | Log chi tiết mỗi TP hit |
| Scaling system | Có thể nhân loss nếu logic sai | H1 confirmation + max 3 scales + move SL |
| Thread lock | Latency tăng nhẹ | RLock + minimal critical sections |
| Exit logic | Có thể conflict với MT5 SL/TP | Coordinate: MT5 = safety net, bot = primary |

---

## 6. CODE CHANGES SUMMARY (CHO XAUUSD)

### 6.1 New helper module (`risk_management.py`)
Tách logic position sizing, partial TP, scaling thành module riêng để testable.

```python
# risk_management.py — KHỞI TẠO MỚI
class RiskManager:
    def __init__(self, config):
        self.config = config
    
    def calculate_position_size(self, balance, sl_distance_points, value_per_point, mode='balance', allocation_pct=None):
        if mode == 'balance':
            risk_amount = balance * self.config['risk_per_trade_pct']
        else:  # 'allocated'
            risk_amount = balance * allocation_pct * self.config['risk_per_trade_pct']
        
        lot_size = risk_amount / (sl_distance_points * value_per_point)
        return lot_size, risk_amount
    
    def validate_rr_ratio(self, sl_dist, tp_dist):
        rr = tp_dist / sl_dist
        return 2.0 <= rr <= 3.5  # Spec range với buffer
    
    def split_tp(self, base_tp_distance, num_splits=4):
        """Trả về list (volume_pct, distance) cho TP1..TP4"""
        return [
            (0.30, base_tp_distance * 0.625),  # TP1 @ 62.5% range
            (0.20, base_tp_distance * 0.781),  # TP2 @ 78.1%
            (0.30, base_tp_distance * 0.937),  # TP3 @ 93.7%
            (0.20, base_tp_distance * 1.000),  # TP4 @ 100%
        ]
```

### 6.2 New scaling module (`scaling_manager.py`)
```python
class ScalingManager:
    def __init__(self, max_scales=3, h1_confirmation_pct=0.75):
        self.max_scales = max_scales
        self.h1_confirmation_pct = h1_confirmation_pct
    
    def can_scale(self, state, mt5_module):
        if state['scaling']['count'] >= self.max_scales:
            return False, "Max scales reached"
        
        if not self._h1_confirmation(state['symbol'], mt5_module, state['armed_direction']):
            return False, "H1 reversal detected"
        
        return True, "OK"
    
    # ... rest
```

### 6.3 Migration cho strategy file (KHÔNG sửa file gốc!)
Tạo `strategies/sunrise_ogle_xauusd_v2.py` (copy + modify):
```python
# Sửa params:
long_atr_sl_multiplier = 2.5
long_atr_tp_multiplier = 8.75  # TP4 = R:R 1:3.5
LONG_ENTRY_WINDOW_PERIODS = 5
WINDOW_PRICE_OFFSET_MULTIPLIER = 0.3
risk_percent = 0.01

# Thêm flag:
USE_PARTIAL_TP = True
USE_SCALING = True
USE_DALIO_ALLOCATION = False  # Pure risk-first
```

### 6.4 Backtest verification
Trước khi deploy:
```bash
cd testing/
python test_partial_tp.py XAUUSD --start 2024-01-01 --end 2025-11-01
python test_scaling.py XAUUSD --start 2024-01-01 --end 2025-11-01
python compare_rr_ratios.py XAUUSD  # So sánh 1:1.44 vs 1:2.5 vs 1:3
```

---

## 7. METRICS ĐỂ THEO DÕI

Sau khi triển khai, monitor các metrics sau trên XAUUSD:

| Metric | Target | Alert |
|--------|--------|-------|
| Win rate (TP1 hit) | > 60% | < 50% |
| Avg R:R realized | > 1:2 | < 1:1.5 |
| Max drawdown | < 10% | > 15% |
| Avg trades/month | 10-30 | < 5 hoặc > 50 |
| Scaling frequency | 20-40% trades | < 10% (logic ko trigger) |
| Position duration | < 24h | > 48h (stuck) |
| SL hit rate | < 30% | > 40% |
| Lot size variation | ± 20% | > 50% (atr volatile) |

Thêm vào GUI một tab "Performance" hiển thị các metrics này real-time.

---

## 8. CHECKLIST TRƯỚC KHI DEPLOY LIVE

- [ ] Disable Dalio allocation cho XAUUSD (`USE_DALIO_ALLOCATION = False`)
- [ ] Cập nhật ATR multipliers để R:R ∈ [1:2, 1:3]
- [ ] Implement & test partial TP system (DEMO ≥ 30 trades)
- [ ] Implement & test scaling system (DEMO ≥ 20 scaling events)
- [ ] Verify `move_sl_to_entry()` hoạt động đúng
- [ ] Verify H1 confirmation logic không quá strict (false negative)
- [ ] Add safety caps: max_lot, min_sl_distance, max_scales
- [ ] Thread-safe state operations
- [ ] Logging chi tiết cho mọi TP hit, scaling decision
- [ ] Backtest 1 năm history với params mới
- [ ] Compare backtest results vs current single-TP system
- [ ] Document mọi thay đổi vào CHANGELOG
- [ ] Tạo rollback plan (giữ version cũ trong git tag)

---

## 9. KẾT LUẬN

Code hiện tại có **kiến trúc vững chắc** (4-phase FSM, 6-layer filters, Dalio allocation) nhưng **chưa triển khai 3 tính năng cốt lõi** trong trading_strategy.md:

1. **Risk-first sizing** (1% balance, không phải 1% allocated)
2. **Partial TP system** (TP1/TP2/TP3/TP4)
3. **Scaling system** (1 base + 3 scales với H1 confirmation)

**Khuyến nghị ưu tiên:**
1. 🔴 **Cao nhất:** Fix R:R ratio + risk calculation (Phase 1) — vi phạm spec rõ ràng nhất
2. 🟡 **Trung bình:** Implement partial TP (Phase 2) — feature core của spec
3. 🟢 **Có thể chậm hơn:** Scaling system (Phase 3) — phức tạp, cần test kỹ

Tổng effort ước tính: **2-4 tuần** để hoàn thành Phase 1-3 với DEMO testing.

> ⚠️ **CẢNH BÁO:** Trước khi sửa `strategies/sunrise_ogle_xauusd.py`, đọc lại `docs/STRATEGY_FILES_POLICY.md` — file này READ-ONLY cho backtest integrity. Nên tạo **`sunrise_ogle_xauusd_v2.py`** mới và backtest song song.
