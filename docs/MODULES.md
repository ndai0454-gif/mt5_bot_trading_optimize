# 📦 MODULES — File-by-File Reference

> **Mục đích:** Mô tả mỗi file trong codebase, vai trò, dependencies và public interface.

---

## 📁 ROOT FILES

### 1. `advanced_mt5_monitor_gui.py` ⭐ MAIN FILE
- **Size:** ~3,500 lines
- **Class chính:** `AdvancedMT5TradingMonitorGUI`
- **Trách nhiệm:** Toàn bộ logic — GUI, monitoring loop, state machine, signal detection, order execution
- **Entry point:** `main()` (line 4576)

#### Method Groups (theo line range):

| Group | Lines | Method | Mục đích |
|-------|-------|--------|----------|
| **GUI Setup** | 297-572 | `setup_gui`, `setup_left_panel`, `setup_right_panel`, `create_*_tab`, `setup_chart`, `create_status_bar` | Tạo Tkinter widgets |
| **Time/Path Helpers** | 574-690 | `update_time`, `get_resource_path`, `load_strategy_configurations` | Utilities |
| **Config Loading** | 691-955 | `load_utc_offset_from_config`, `on_utc_offset_change`, `parse_strategy_config`, `validate_critical_params`, `check_config_retry_needed`, `retry_load_config` | Đọc & validate strategy params |
| **MT5 Connection** | 957-1055 | `initialize_mt5_connection`, `initialize_signal_processing`, `attempt_reconnect` | Kết nối + reconnect |
| **Persistence** | 1057-1243 | `save_strategy_state`, `load_strategy_state`, `reset_strategy_memory` | JSON state persistence |
| **Lifecycle** | 1245-1301 | `start_monitoring`, `stop_monitoring` | Start/stop daemon thread |
| **Main Loop** | 1303-1572 | `advanced_monitoring_loop`, `monitor_strategy_phase` | Heartbeat + per-symbol orchestrator |
| **Filter Validation** | 1577-2000 | `_validate_atr_filter`, `_validate_angle_filter`, `_validate_price_filter`, `_validate_candle_direction`, `_validate_ema_ordering`, `_validate_ema_position_filter`, `_validate_time_filter` | 7 entry filters |
| **Crossover Detection** | 2002-2342 | `check_crossover_at_candle`, `detect_ema_crossovers` | Phát hiện EMA crossovers |
| **Indicators** | 2343-2487 | `calculate_indicators` | EMA + ATR + trend |
| **Value Extraction** | 2488-2547 | `_extract_value`, `extract_numeric_value`, `extract_float_value`, `extract_bool_value` | Parse config values |
| **State Helpers** | 2548-2598 | `_is_in_trading_time_range`, `_reset_entry_state` | Time + reset state |
| **State Machine** | 2599-3452 | `_phase3_open_breakout_window`, `_phase4_monitor_window`, `determine_strategy_phase` | 4-phase FSM |
| **Display Updates** | 3454-3725 | `update_strategy_displays`, `update_phases_tree`, `update_indicators_display`, `update_window_markers` | GUI refresh |
| **Charting** | 3726-3972 | `refresh_chart`, `plot_candlesticks` | Matplotlib chart rendering |
| **Logging/Summary** | 3973-4154 | `process_phase_updates`, `log_phase_summary`, `log_hourly_summary`, `terminal_log`, `clear_terminal`, `save_terminal_log` | Log management |
| **Event Handlers** | 4156-4209 | `on_strategy_phase_select`, `on_symbol_config_select`, `on_chart_symbol_change`, `toggle_connection` | UI events |
| **Trade Execution** | 4210-4547 | `_execute_entry`, `execute_trade` | Đặt lệnh MT5 |
| **Cleanup** | 4549-4574 | `disconnect_mt5`, `on_closing` | Shutdown |

#### Module-level constants (line 81-185):
```python
ASSET_ALLOCATIONS = {...}        # Ray Dalio % allocation per symbol
DEFAULT_RISK_PERCENT = 0.01      # 1% risk per trade
APP_VERSION = "1.2.3"
CRITICAL_PARAMS_CORE = [...]     # Required params validation
CRITICAL_PARAMS_SHORT = [...]    # Required if SHORT enabled
CONFIG_RETRY_INTERVAL = 300      # Retry config load interval
STATE_MAX_AGE_MINUTES = 30       # Stale state expiry
STATE_FILE_NAME = '...'
VALID_ENTRY_STATES = [...]
MAX_RECONNECT_ATTEMPTS = 3
MIN_BARS_REQUIRED = 100
BARS_TO_FETCH = 151
CHART_DISPLAY_BARS = 100
CANDLE_CHECK_SLEEP_SECONDS = 5
GUI_UPDATE_INTERVAL_MS = 1000
HOURLY_SUMMARY_MINUTES = 60
```

---

### 2. `requirements.txt`
- **Mục đích:** Liệt kê dependencies Python
- **Key packages:**
  - `MetaTrader5>=5.0.45` — MT5 Python API
  - `pandas>=1.5.0`, `numpy>=1.24.0` — Data processing
  - `matplotlib>=3.5.0`, `mplfinance>=0.12.0` — Charting (optional)
  - `python-dateutil>=2.8.0`, `pytz>=2022.1` — Time handling
  - `pyinstaller>=5.13.0` — Build .exe

### 3. `pyproject.toml`
- **Mục đích:** Project metadata + Pylance/Pyright config
- **Highlights:** Listing `src` and `strategies` packages, extraPaths for type checking

### 4. `setup.ps1`
- **Mục đích:** Automated setup PowerShell — tạo venv + cài deps

### 5. `run_bot.bat`
- **Mục đích:** Windows batch — activate venv + chạy `python advanced_mt5_monitor_gui.py`

### 6. `build_exe.bat`
- **Mục đích:** Build standalone .exe bằng PyInstaller. Output: `dist/MT5_Trading_Bot.exe`

### 7. `setup_autostart.bat` / `remove_autostart.bat`
- **Mục đích:** Đăng ký bot vào Windows startup (registry)

### 8. `fix_encoding.py` / `temp_fix.py`
- **Mục đích:** Utility scripts — fix encoding issues trong file Python (legacy)

### 9. `LICENSE`
- **Mục đích:** MIT License

### 10. `README.md`
- **Mục đích:** Documentation chính cho GitHub

---

## 📁 `src/` — LEGACY MODULES

### `src/__init__.py`
Empty package marker.

### `src/sunrise_signal_adapter.py` ⚠️ PLACEHOLDER
- **Status:** Implementation cũ, KHÔNG được dùng cho live logic
- **Lý do giữ:** `advanced_mt5_monitor_gui.py:74` vẫn import nhưng chỉ dùng cho `initialize_signal_processing()` — không thực thi logic chính
- **Classes:**
  - `SignalType` — Enum BUY/SELL/CLOSE_BUY/CLOSE_SELL/HOLD
  - `TradingSignal` — Container signal data
  - `SunriseSignalGenerator` — **Placeholder** — comment ghi rõ "replace with actual strategy logic"
  - `MultiSymbolSignalManager` — Manage multiple symbols
  - `MT5DataProvider` — Wrap mt5.copy_rates_from_pos()
- **Lưu ý:** Logic phân tích thực tế đã được port sang `advanced_mt5_monitor_gui.py`

### `src/mt5_live_trading_connector.py` ⚠️ LEGACY
- **Status:** Phiên bản đầu của connector — không được gọi từ GUI hiện tại
- **Use case tiềm năng:** Headless CLI mode (chưa phát triển)
- **Highlights:**
  - `DEMO_MODE_ONLY = True` — safety flag
  - `MAX_RISK_PER_TRADE = 0.01`
  - `MAX_DAILY_TRADES = 10`
  - `MAX_POSITION_SIZE = 0.1`

---

## 📁 `strategies/` — STRATEGY FILES (READ-ONLY) 🔒

### `strategies/__init__.py`
Empty package marker.

### `strategies/sunrise_ogle_*.py` (8 files)
- **Files:**
  - `sunrise_ogle_eurusd.py`
  - `sunrise_ogle_gbpusd.py`
  - `sunrise_ogle_xauusd.py`
  - `sunrise_ogle_audusd.py`
  - `sunrise_ogle_xagusd.py`
  - `sunrise_ogle_usdchf.py`
  - `sunrise_ogle_eurjpy.py`
  - `sunrise_ogle_usdjpy.py`

- **Class:** `SunriseOgle(bt.Strategy)` (Backtrader strategy class)
- **Class USDJPY:** `SunriseOgleUSDJPY` (variant cho JPY pair)

- **Quy ước:** **READ-ONLY** — không sửa nội dung trừ khi đã backtest lại
- **Lý do:** Đảm bảo live trading khớp với backtest (xem `docs/STRATEGY_FILES_POLICY.md`)

#### Method Groups (per file):

| Group | Methods |
|-------|---------|
| **Trade Reporting** | `_record_trade_entry`, `_record_trade_exit`, `_close_trade_reporting`, `_init_trade_reporting` |
| **Helpers** | `_cross_above`, `_cross_below`, `_angle` |
| **Position Sizing** | `_calculate_forex_position_size`, `_validate_forex_setup` |
| **Forex Config** | `_get_forex_instrument_config`, `_apply_forex_config`, `_format_forex_trade_info` |
| **State Reset** | `_reset_entry_state`, `_reset_pullback_state`, `_reset_signal_tracking` |
| **State Machine** | `_phase1_scan_for_signal`, `_phase2_confirm_pullback`, `_phase3_open_breakout_window`, `_phase4_monitor_window` |
| **Main Loop** | `next` (Backtrader callback) |
| **Entry Logic** | `_full_entry_signal`, `_standard_entry_signal`, `_standard_long_entry_signal`, `_handle_pullback_entry`, `_handle_long_pullback_entry` |
| **Filters** | `_basic_entry_conditions`, `_validate_all_entry_filters`, `_basic_short_entry_conditions`, `_validate_all_short_entry_filters` |
| **Time** | `_is_in_trading_time_range` |
| **Lifecycle** | `__init__`, `notify_order`, `notify_trade`, `stop`, `_cancel_all_pending_orders` |

- **Class phụ:** `SLTPObserver(bt.Observer)` — vẽ SL/TP trên chart Backtrader
- **Helper:** `parse_date(s)` — date parser cho Backtrader CLI

#### Params dict ở đầu mỗi file:
```python
class SunriseOgle(bt.Strategy):
    params = (
        # EMA periods
        ('ema_fast_length', 18),
        ('ema_medium_length', 18),
        ('ema_slow_length', 24),
        ('ema_filter_price_length', 100),
        
        # Risk
        ('long_atr_sl_multiplier', 4.5),
        ('long_atr_tp_multiplier', 6.5),
        
        # Pullback
        ('LONG_USE_PULLBACK_ENTRY', True),
        ('LONG_PULLBACK_MAX_CANDLES', 2),
        ('LONG_ENTRY_WINDOW_PERIODS', 10),
        
        # Window
        ('USE_WINDOW_TIME_OFFSET', False),
        ('WINDOW_OFFSET_MULTIPLIER', 1.0),
        ('WINDOW_PRICE_OFFSET_MULTIPLIER', 0.5),
        
        # Filters
        ('LONG_USE_ATR_FILTER', True),
        ('LONG_ATR_MIN_THRESHOLD', 0.0001),
        ('LONG_ATR_MAX_THRESHOLD', 0.005),
        ...
        
        # Time
        ('USE_TIME_RANGE_FILTER', True),
        ('ENTRY_START_HOUR', 8),
        ('ENTRY_END_HOUR', 16),
        
        # Direction
        ('ENABLE_LONG_TRADES', True),
        ('ENABLE_SHORT_TRADES', False),
    )
```

**Live bot parse các params này bằng regex** (không import trực tiếp) → store vào `strategy_configs[symbol]`.

---

## 📁 `testing/` — TEST SUITE

### `testing/test_setup.py`
- **Mục đích:** Verify installation (deps, MT5 connection, paths)
- **Run:** `python test_setup.py`

### `testing/test_monitor_components.py`
- **Mục đích:** Test GUI components
- **Test cases:** Tkinter widgets, chart rendering

### `testing/test_mt5_order.py`
- **Mục đích:** ⚠️ **Đặt order thật** (test execution path)
- **Khuyến cáo:** CHỈ chạy trên DEMO account!

### `testing/check_broker_specs.py`
- **Mục đích:** In ra broker specs (point, tick_value, contract_size, lot limits) cho 8 symbols
- **Use case:** Debug position sizing

### `testing/test_position_sizing.py`
- **Mục đích:** Test logic tính lot size với mock data
- **Verify:** lot_size = risk_amount / (sl_points × value_per_point)

### `testing/test_jpy_entries.py`
- **Mục đích:** Validate JPY pair entries (3-digit precision, 0.01 pip value)

### `testing/verify_all_symbols.py`
- **Mục đích:** Check tất cả 8 symbols load được config đúng

### `testing/test_signal_detection.py`
- **Mục đích:** Test crossover detection logic

### `testing/test_real_entry.py`
- **Mục đích:** End-to-end entry test (DEMO ONLY)

### `testing/deep_stress_test.py`
- **Mục đích:** Stress test với nhiều iterations

---

## 📁 `docs/` — DOCUMENTATION

### Essential docs:
| File | Mục đích |
|------|----------|
| `docs/README.md` | Documentation index |
| `docs/QUICK_START.md` | Hướng dẫn nhanh |
| `docs/START_TESTING_HERE.md` | Testing guide |
| `docs/DALIO_ALLOCATION_SYSTEM.md` | Ray Dalio implementation chi tiết |
| `docs/DALIO_QUICK_REFERENCE.md` | Quick reference position sizing |
| `docs/STRATEGY_FILES_POLICY.md` | READ-ONLY policy cho strategy files |
| `docs/strategy_comparison.md` | **Source of Truth** — params + logic comparison |
| `docs/CONTRIBUTING.md` | Contribution guidelines |
| `docs/DEPLOYMENT_GUIDE.md` | Deployment instructions |

### Bug fix history (chronological):
| File | Bug |
|------|-----|
| `docs/ATR_BUG_FIX_COMPLETE.md` | ATR filter integration bug |
| `docs/PULLBACK_SYSTEM_FIX.md` | Pullback flag check missing |
| `docs/POSITION_SIZING_FIX_CRITICAL.md` | Hardcoded pip value bug |
| `docs/UTC_TIMEZONE_FIX_SUMMARY.md` | DST handling fix |
| `docs/UTC_TIME_FILTER_FIX.md` | Time filter timezone fix |
| `docs/PULLBACK_COUNT_BUG_FIX.md` | Pullback counter bug |
| `docs/DUPLICATE_ENTRY_FIX.md` | Duplicate position bug |
| `docs/CRITICAL_FIXES_*.md` | Various critical fixes |
| `docs/MT5_LOG_ANALYSIS.md` | Log analysis examples |
| `docs/MT5_HISTORICAL_DATA_SETUP.md` | Historical data setup |
| `docs/MT5_EMA_SETUP_GUIDE.md` | MT5 EMA configuration |
| `docs/DEEP_STRATEGY_ANALYSIS_NOV14.md` | 25-page strategy analysis |

### `docs/archive/` — Historical docs (legacy, không dùng nữa)

### `docs/Advanced MT5 Monitor.png` — Screenshot GUI

---

## 📁 `config/` — CONFIGURATION FILES (Runtime)

### `config/mt5_credentials.json` (gitignored)
```json
{
  "account": 12345678,
  "password": "...",
  "server": "Broker-Demo"
}
```

### `config/mt5_credentials_template.json`
Template cho user copy.

### `config/broker_timezone.json` (auto-generated)
```json
{
  "utc_offset": 1,
  "description": "...",
  "last_updated": "2025-11-12 14:30:00"
}
```

---

## 📁 `logs/` — RUNTIME LOGS (gitignored)

### `mt5_advanced_monitor.log`
Full log file (UTF-8) — mọi `terminal_log()` calls.

### `terminal_log.txt` (manual save)
User-saved log từ GUI Terminal tab.

---

## 📁 `dist/` — BUILD OUTPUT (sau build_exe.bat)

### `dist/MT5_Trading_Bot.exe`
Standalone executable, bundle:
- Python interpreter
- All dependencies
- `strategies/`
- `config/` templates
- Resources

---

## 🔗 DEPENDENCY GRAPH

```
              advanced_mt5_monitor_gui.py
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
  Tkinter         MetaTrader5      pandas/numpy
  matplotlib      (Python API)     (data proc.)
                       │
                       ▼
              MT5 Terminal (locally)
                       │
                       ▼
                Broker Server
                       
              strategies/sunrise_ogle_*.py
                  (parsed by regex)
                       ▲
                       │
              advanced_mt5_monitor_gui.py
              (parse_strategy_config)

              src/sunrise_signal_adapter.py  (legacy)
                       ▲
                       │
              advanced_mt5_monitor_gui.py
              (only initialize_signal_processing)
```

---

## 📐 INTERFACE CONTRACTS

### Live Bot ↔ Strategy Files (regex parse)
- Bot reads: parameter names matching `param = value` or `param=value,`
- Strategy must use Python keyword=value syntax
- Comments allowed (split by `#`)

### Live Bot ↔ MT5 API
- `mt5.initialize()`, `mt5.shutdown()` — connection
- `mt5.account_info()` — get balance
- `mt5.symbol_info(symbol)` — get specs
- `mt5.symbol_info_tick(symbol)` — current tick (not used heavily)
- `mt5.copy_rates_from_pos(symbol, timeframe, start, count)` — historical bars
- `mt5.positions_get(symbol)` — open positions
- `mt5.order_send(request)` — execute order
- `mt5.last_error()` — error code

### Live Bot ↔ Filesystem
- `mt5_strategy_state.json` — Read on start, write on cycle (atomic)
- `config/broker_timezone.json` — Read on start, write on UTC change
- `config/mt5_credentials.json` — Read on connect (optional, MT5 may auto-login)
- `mt5_advanced_monitor.log` — Append-only log

---

## 🚨 CRITICAL DEPENDENCIES (Must NOT break)

1. **`adjust=False`** trong mọi `.ewm()` call — match Backtrader/MT5
2. **Forming candle removal** (`df.iloc[:-1]`) trước mọi indicator calc
3. **`broker_utc_offset`** correctly set (UTC+1/+2 theo DST)
4. **`ASSET_ALLOCATIONS` total = 100%** — đảm bảo Dalio principle
5. **6 filters return False on Exception** — never let trade slip through
6. **`signal_detection_atr`** stored cho ATR change calculation
7. **`signal_trigger_candle = Bar -1`** (not Bar 0) — match Backtrader
8. **Atomic file write** (.tmp + rename) — tránh corrupt JSON state
9. **MT5 filling mode detection** — IOC/FOK/RETURN tùy broker
10. **`positions_get()` duplicate check** — never open 2 positions on same symbol

---

## 📝 GLOSSARY

| Term | Định nghĩa |
|------|-----------|
| **EMA** | Exponential Moving Average |
| **ATR** | Average True Range — đo volatility |
| **Crossover** | Khi `Confirm EMA` cắt qua `Fast/Medium/Slow EMA` |
| **Pullback** | Nến điều chỉnh ngược trend tạm thời (LONG = bearish, SHORT = bullish) |
| **Window** | Khoảng giá ± offset từ pullback candle, có deadline N bars |
| **Top/Bottom Limit** | Boundary của window — SUCCESS/FAILURE breakout |
| **Trigger Candle** | Nến tại Bar -1 khi crossover detect |
| **Global Invalidation** | Reset state khi opposing crossover + matching color candle xuất hiện |
| **Dalio Allocation** | % capital cho mỗi asset (Ray Dalio All-Weather Portfolio) |
| **Tick Value** | Giá trị 1 tick trong account currency (broker-specific) |
| **Lot Step** | Bước nhảy nhỏ nhất của lot size (e.g., 0.01) |
| **Filling Mode** | Cách order được fill (IOC/FOK/RETURN) |
| **Magic Number** | ID phân biệt orders của bot (234000 trong code này) |
