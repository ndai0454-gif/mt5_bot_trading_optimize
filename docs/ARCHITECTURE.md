# 🏗️ ARCHITECTURE — MT5 Live Trading Bot

> **Mục đích:** Mô tả kiến trúc tổng thể, layer, responsibility và communication patterns.

---

## 1. BIRD'S-EYE VIEW

```
                      ┌─────────────────────────────────────┐
                      │       USER (Trader / Operator)      │
                      └────────────────┬────────────────────┘
                                       │
                                  GUI (Tkinter)
                                       │
              ┌────────────────────────▼────────────────────────────┐
              │   advanced_mt5_monitor_gui.py (MONOLITH ~3,500 LOC) │
              │                                                     │
              │  ┌──────────────────────────────────────────────┐   │
              │  │       AdvancedMT5TradingMonitorGUI class     │   │
              │  │                                              │   │
              │  │   PRESENTATION │ ORCHESTRATION │ TRADING     │   │
              │  │   (GUI/Charts) │ (Threads)     │ (Logic)     │   │
              │  └──────────────────────────────────────────────┘   │
              └────────────┬──────────────────────────┬──────────────┘
                           │                          │
                           ▼                          ▼
              ┌────────────────────┐      ┌──────────────────────────┐
              │  strategies/       │      │   config/                │
              │  sunrise_ogle_*.py │      │   - mt5_credentials.json │
              │  (READ-ONLY, 8 file)│      │   - broker_timezone.json│
              │  Source-of-truth   │      │                          │
              │  cho params        │      └──────────────────────────┘
              └────────────────────┘
                           │
                  (Configuration parsing)
                           │
                           ▼
              ┌─────────────────────────┐
              │  MetaTrader5 Terminal   │
              │  (Python API mt5.*)     │
              └────────────┬────────────┘
                           │
                  (Live Market Data + Orders)
                           │
                           ▼
              ┌─────────────────────────┐
              │   BROKER SERVER         │
              │   (Demo / Live)         │
              └─────────────────────────┘
```

---

## 2. KIẾN TRÚC LAYER

Hệ thống tuân theo mô hình **3-tier monolith** (mọi layer đều nằm trong cùng 1 file Python, phân chia bằng convention method-naming):

### 🎨 Layer 1 — Presentation (GUI)
- **Trách nhiệm:** Hiển thị real-time, nhận input từ user
- **Tech:** Tkinter + Matplotlib + mplfinance
- **Methods chính:**
  - `setup_gui()`, `setup_left_panel()`, `setup_right_panel()`
  - `create_strategy_phases_tab()`, `create_configuration_tab()`, `create_indicators_tab()`
  - `create_charts_tab()`, `create_terminal_tab()`, `create_window_markers_tab()`
  - `refresh_chart()`, `plot_candlesticks()`, `update_phases_tree()`, `update_indicators_display()`
  - `terminal_log()` — central logger với queue thread-safe

### ⚙️ Layer 2 — Orchestration (Threads & State)
- **Trách nhiệm:** Quản lý lifecycle, đa luồng, persistence
- **Tech:** `threading.Thread`, `queue.Queue`, JSON files
- **Methods chính:**
  - `advanced_monitoring_loop()` — daemon thread chính, polling theo candle-close
  - `monitor_strategy_phase()` — per-symbol orchestrator
  - `save_strategy_state()` / `load_strategy_state()` — persistence với atomic write
  - `attempt_reconnect()` — IPC recovery với exponential backoff
  - `start_monitoring()` / `stop_monitoring()` — lifecycle
  - `process_phase_updates()` — queue consumer cho GUI updates

### 💹 Layer 3 — Trading Logic (Core)
- **Trách nhiệm:** Phân tích tín hiệu, state machine, vào lệnh
- **Tech:** Pandas/NumPy, MetaTrader5 API
- **Methods chính:**
  - `calculate_indicators()` — EMA, ATR
  - `detect_ema_crossovers()` — phát hiện crossover
  - `_validate_*_filter()` — 6 entry filters
  - `determine_strategy_phase()` — 4-phase state machine
  - `_phase3_open_breakout_window()` / `_phase4_monitor_window()` — window control
  - `_execute_entry()` / `execute_trade()` — gửi order MT5

---

## 3. COMPONENT MAP

```
┌──────────────────────────────────────────────────────────────────────┐
│                  AdvancedMT5TradingMonitorGUI                        │
├──────────────────────────────────────────────────────────────────────┤
│ STATE (in-memory)                                                    │
│  ├─ strategy_states[symbol]   : per-symbol state dict                │
│  ├─ strategy_configs[symbol]  : parsed config from strategy files    │
│  ├─ chart_data[symbol]        : last DataFrame + indicators          │
│  ├─ window_markers[symbol]    : breakout boundaries for plotting     │
│  ├─ config_errors[symbol]     : missing param tracker                │
│  ├─ hourly_events             : counters for hourly summary          │
│  ├─ bot_startup_time          : ignore stale crossovers              │
│  └─ broker_utc_offset         : 1/2/3 — DST handling                 │
├──────────────────────────────────────────────────────────────────────┤
│ THREADS                                                              │
│  ├─ Main (Tkinter mainloop)                                          │
│  ├─ monitor_thread (daemon, advanced_monitoring_loop)                │
│  └─ phase_update_queue (cross-thread GUI updates)                    │
├──────────────────────────────────────────────────────────────────────┤
│ PERSISTENT FILES                                                     │
│  ├─ mt5_strategy_state.json   : strategy_states snapshot             │
│  ├─ config/broker_timezone.json: UTC offset                          │
│  ├─ config/mt5_credentials.json: account credentials                 │
│  └─ mt5_advanced_monitor.log  : full log file                        │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 4. CRITICAL CONSTANTS (Configuration)

Tại đầu file `advanced_mt5_monitor_gui.py`:

| Constant | Value | Mục đích |
|----------|-------|----------|
| `ASSET_ALLOCATIONS` | Dict 8 symbols | Ray Dalio % allocation |
| `DEFAULT_RISK_PERCENT` | 0.01 | 1% risk per trade |
| `APP_VERSION` | "1.2.3" | Phiên bản app |
| `CRITICAL_PARAMS_CORE` | List 8 params | Required cho mọi symbol |
| `CRITICAL_PARAMS_SHORT` | List 4 params | Required nếu SHORT enabled |
| `CONFIG_RETRY_INTERVAL` | 300s | Retry config load |
| `STATE_MAX_AGE_MINUTES` | 30 | Stale state expiry |
| `STATE_FILE_NAME` | "mt5_strategy_state.json" | Persistence file |
| `VALID_ENTRY_STATES` | ['SCANNING','ARMED_LONG','ARMED_SHORT','WINDOW_OPEN'] | State validation |
| `MAX_RECONNECT_ATTEMPTS` | 3 | IPC reconnect limit |
| `RECONNECT_BACKOFF_SECONDS` | 2 | Initial backoff |
| `MIN_BARS_REQUIRED` | 100 | Min data cho indicator |
| `BARS_TO_FETCH` | 151 | Fetch từ MT5 mỗi lần |
| `CHART_DISPLAY_BARS` | 100 | Bars hiển thị trên chart |
| `CANDLE_CHECK_SLEEP_SECONDS` | 5 | Sleep giữa các check |
| `GUI_UPDATE_INTERVAL_MS` | 1000 | GUI refresh rate |
| `HOURLY_SUMMARY_MINUTES` | 60 | Hourly log interval |

---

## 5. PATTERN ARCHITECTURE

### 5.1 Single Source of Truth — Strategy Files
- 8 files trong `strategies/sunrise_ogle_*.py` là **READ-ONLY**
- Live bot **parse** params từ các file này (regex matching key=value)
- Đảm bảo backtest ↔ live trading dùng cùng tham số

### 5.2 State Persistence Pattern
```
[Memory state]  ←→  [JSON file]
     ↑                  ↑
     │                  │
  Atomic write     Auto-expire (>30min)
  (temp + rename)  Validate entry_state
                   Discard if stale
```

### 5.3 Smart Polling (NOT busy-wait)
- Vòng lặp `advanced_monitoring_loop()` chỉ xử lý khi `minute % 5 == 0 AND second <= 10`
- Tránh fetch dữ liệu lặp lại trong cùng nến → tiết kiệm IPC

### 5.4 Fast Path Optimization
- Khi `entry_state == WINDOW_OPEN`: fetch ít data hơn, dùng indicators đã cache
- Skip `calculate_indicators()` (vốn tốn ~70% CPU)
- Chỉ check breakout boundary với close price mới

### 5.5 Defensive Programming
- **Filter trên Exception → BLOCK trade** (không vào lệnh nếu lỗi validate)
- **Orphan position detect** — sync state nếu phát hiện position lệch với state
- **Duplicate prevention** — `positions_get()` check trước mỗi entry
- **Critical params validation** — disable trading nếu thiếu config, retry sau 5 phút
- **Stale crossover skip** — bỏ qua tín hiệu < bot_startup_time

### 5.6 Cross-Thread Communication
```
monitor_thread (background)
    │
    │  push update
    ▼
phase_update_queue (queue.Queue)
    │
    │  poll every 1000ms via root.after()
    ▼
Main thread (Tkinter) → update GUI safely
```

---

## 6. DEPENDENCY GRAPH

```
                   ┌─────────────────────┐
                   │  Tkinter (built-in) │
                   └──────────┬──────────┘
                              │
                   ┌──────────▼──────────┐         ┌─────────────────┐
                   │  Main GUI Class     │ ──────► │  MetaTrader5    │
                   │  (3,500 LOC)        │ ◄────── │  Python API     │
                   └──┬──────────────┬───┘         └─────────────────┘
                      │              │
              ┌───────▼──────┐  ┌───▼─────┐
              │   Pandas     │  │ Numpy   │       ┌────────────────┐
              │ (DataFrame,  │  │ (Array, │ ────► │  matplotlib +  │
              │  ewm, ATR)   │  │ atan…)  │       │  mplfinance    │
              └──────────────┘  └─────────┘       └────────────────┘
                                                  (Optional — chart)
```

External deps cài qua `requirements.txt`:
- `MetaTrader5>=5.0.45`
- `pandas>=1.5.0`
- `numpy>=1.24.0`
- `matplotlib>=3.5.0`
- `mplfinance>=0.12.0`
- `python-dateutil>=2.8.0`
- `pytz>=2022.1`
- `pyinstaller>=5.13.0` (build .exe)

---

## 7. DEPLOYMENT MODELS

### 🐍 Mode 1: Python script (dev)
```bash
python advanced_mt5_monitor_gui.py
```

### 📦 Mode 2: Standalone EXE (production)
```bash
build_exe.bat          # → dist/MT5_Trading_Bot.exe
```
Sử dụng `pyinstaller`, bundle toàn bộ strategies + config templates.

### 🔄 Mode 3: Auto-start với Windows
```bash
setup_autostart.bat    # Tạo registry entry
remove_autostart.bat   # Gỡ
```

---

## 8. INDEPENDENT MODULES (KHÔNG dùng trong runtime hiện tại)

### ⚠️ `src/sunrise_signal_adapter.py`
- **Status:** Placeholder cũ — comment ghi rõ *"This is a placeholder implementation - replace with actual strategy logic"*
- **Class:** `SunriseSignalGenerator`, `MultiSymbolSignalManager`, `MT5DataProvider`
- **Use case:** Đã được tích hợp `import` ở `advanced_mt5_monitor_gui.py:74-78` nhưng chỉ dùng cho `initialize_signal_processing()` (không thực thi logic chính)
- **Lý do:** Logic phân tích thực tế đã được port sang `advanced_mt5_monitor_gui.py`

### ⚠️ `src/mt5_live_trading_connector.py`
- **Status:** Phiên bản đầu của connector — không gọi từ GUI
- **Use case:** Có thể dùng cho headless CLI mode (nếu phát triển tương lai)

---

## 9. HƯỚNG MỞ RỘNG (Tiềm năng refactor)

| Hạn chế hiện tại | Cải tiến đề xuất |
|------------------|------------------|
| Monolith 3,500 LOC | Tách `signal/`, `state/`, `executor/`, `gui/` |
| GUI và logic trộn chung | Tách MVC: `model` + `view` + `controller` |
| Strategy file dùng regex parse | Dùng `importlib` import trực tiếp params |
| Polling 5s sleep | Event-driven với MT5 WebSocket (nếu có) |
| Single-threaded scan loop | Async per-symbol scanning |
| Không có unit test cho logic core | Pytest cho `_validate_*` functions |

---

## 10. SECURITY & SAFETY

| Cơ chế | Implementation |
|--------|----------------|
| Credential isolation | `config/mt5_credentials.json` gitignored |
| Demo mode default | `DEMO_MODE_ONLY=True` trong connector cũ |
| Risk cap 1% | Per allocated capital, không phải total portfolio |
| Duplicate position prevent | `mt5.positions_get(symbol)` check |
| Orphan detection | Sync state nếu position tồn tại mà state không match |
| State stale expiry | 30 phút → discard |
| Atomic file write | Temp + rename pattern |
| Filter-on-error block | Return False nếu Exception trong validate |
| Stale crossover skip | So với `bot_startup_time` |
