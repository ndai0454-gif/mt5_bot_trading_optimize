# 📚 DOCUMENTATION INDEX

> **Bộ tài liệu phân tích codebase MT5 Live Trading Bot — Sunrise Ogle Strategy**
> Tạo bởi quá trình review source code, tập trung vào architecture & workflow.

---

## 🗺️ LỘ TRÌNH ĐỌC (THEO THỨ TỰ KHUYẾN NGHỊ)

### 🟢 Step 1 — Hiểu kiến trúc tổng thể
👉 **[ARCHITECTURE.md](ARCHITECTURE.md)** — Bird's-eye view, layer, components, patterns

**Trả lời câu hỏi:**
- Hệ thống có những thành phần gì?
- Layer nào làm gì?
- Threading, persistence, communication ra sao?
- Deployment models?

---

### 🟢 Step 2 — Hiểu workflow vận hành
👉 **[WORKFLOW.md](WORKFLOW.md)** — Step-by-step từ boot đến shutdown

**Trả lời câu hỏi:**
- Khi user chạy bot, điều gì xảy ra tuần tự?
- Monitor loop hoạt động thế nào?
- Một signal đi qua những bước nào để thành order?
- Error handling khi nào kick in?

---

### 🟢 Step 3 — Hiểu signal & state logic chi tiết
👉 **[logic.md](logic.md)** — Toàn bộ logic phân tích tín hiệu & vào lệnh

👉 **[STATE_MACHINE.md](STATE_MACHINE.md)** — Chi tiết 4-phase FSM

**Trả lời câu hỏi:**
- Signal được phát hiện như thế nào?
- 6 filter validation hoạt động cụ thể?
- State chuyển đổi theo điều kiện nào?
- Edge cases được xử lý ra sao?

---

### 🟢 Step 4 — Hiểu luồng dữ liệu
👉 **[DATA_FLOW.md](DATA_FLOW.md)** — Data transformation từ MT5 đến order

**Trả lời câu hỏi:**
- Dữ liệu thị trường được fetch thế nào?
- Shape/type của DataFrame ra sao?
- EMA, ATR được tính chính xác bằng công thức nào?
- Order request được build ra sao?

---

### 🟢 Step 5 — Tra cứu từng file/module
👉 **[MODULES.md](MODULES.md)** — File-by-file reference

**Trả lời câu hỏi:**
- File nào làm gì?
- Method nào ở line số bao nhiêu?
- File nào là legacy (không dùng)?
- Test scripts có những gì?

---

## 📂 CẤU TRÚC TÀI LIỆU MỚI

| File | Size | Mục đích | Ai nên đọc |
|------|------|----------|------------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | ~300 lines | Tổng thể kiến trúc | New devs, architects |
| [WORKFLOW.md](WORKFLOW.md) | ~470 lines | Step-by-step operation | Operators, debuggers |
| [logic.md](logic.md) | ~600 lines | Signal & entry logic | Strategy devs |
| [STATE_MACHINE.md](STATE_MACHINE.md) | ~550 lines | 4-phase FSM detail | Logic debuggers |
| [DATA_FLOW.md](DATA_FLOW.md) | ~430 lines | Data pipeline | Data analysts |
| [MODULES.md](MODULES.md) | ~430 lines | File-by-file ref | Anyone navigating code |
| [INDEX.md](INDEX.md) (this file) | — | Reading roadmap | Start here! |

---

## 🎯 USE CASE → TÀI LIỆU PHÙ HỢP

### ❓ "Tôi mới gia nhập team, bắt đầu từ đâu?"
1. README.md (project overview)
2. **ARCHITECTURE.md** (high-level)
3. **WORKFLOW.md** (operational flow)
4. **MODULES.md** (file map)

### ❓ "Tôi cần debug một bug về signal detection"
1. **logic.md** (signal logic chi tiết)
2. **STATE_MACHINE.md** (state transitions)
3. **DATA_FLOW.md** (data shape)
4. `docs/` (history bug fixes)

### ❓ "Tôi muốn thêm asset mới (e.g., NZDUSD)"
1. **MODULES.md** (file map)
2. **logic.md** § config params
3. `strategies/sunrise_ogle_eurusd.py` (template)
4. `docs/STRATEGY_FILES_POLICY.md`

### ❓ "Tôi cần tối ưu hiệu suất bot"
1. **ARCHITECTURE.md** § Pattern Architecture (Fast Path)
2. **WORKFLOW.md** § Smart Polling
3. **MODULES.md** § dependencies

### ❓ "Tôi muốn refactor codebase"
1. **ARCHITECTURE.md** § Hướng mở rộng
2. **MODULES.md** § interfaces
3. **STATE_MACHINE.md** § edge cases

### ❓ "Tôi cần audit risk management"
1. **WORKFLOW.md** § Phần E: Order Execution
2. **DATA_FLOW.md** § §6: Order Execution Flow
3. `docs/DALIO_ALLOCATION_SYSTEM.md`

### ❓ "Tôi muốn viết test cho signal logic"
1. **logic.md** (rules cần test)
2. **STATE_MACHINE.md** § transitions table
3. `testing/` existing tests

---

## 🔗 OFFICIAL DOCS (DO PROJECT MAINTAIN)

Trong thư mục `docs/`:

### Essential
- [docs/README.md](docs/README.md) — Documentation index của project
- [docs/QUICK_START.md](docs/QUICK_START.md) — Hướng dẫn nhanh
- [docs/START_TESTING_HERE.md](docs/START_TESTING_HERE.md) — Testing guide
- [docs/STRATEGY_FILES_POLICY.md](docs/STRATEGY_FILES_POLICY.md) — READ-ONLY policy

### Core Strategy
- [docs/DALIO_ALLOCATION_SYSTEM.md](docs/DALIO_ALLOCATION_SYSTEM.md) — Ray Dalio implementation
- [docs/DALIO_QUICK_REFERENCE.md](docs/DALIO_QUICK_REFERENCE.md) — Position sizing
- [docs/strategy_comparison.md](docs/strategy_comparison.md) — **Source of truth** cho params

### Technical Deep Dives
- [docs/DEEP_STRATEGY_ANALYSIS_NOV14.md](docs/DEEP_STRATEGY_ANALYSIS_NOV14.md) — 25-page analysis
- [docs/POSITION_SIZING_FIX_CRITICAL.md](docs/POSITION_SIZING_FIX_CRITICAL.md) — Position sizing internals
- [docs/PULLBACK_SYSTEM_FIX.md](docs/PULLBACK_SYSTEM_FIX.md) — Pullback flag fix
- [docs/UTC_TIMEZONE_FIX_SUMMARY.md](docs/UTC_TIMEZONE_FIX_SUMMARY.md) — DST handling
- [docs/ATR_BUG_FIX_COMPLETE.md](docs/ATR_BUG_FIX_COMPLETE.md) — ATR filter integration

### Setup
- [docs/MT5_EMA_SETUP_GUIDE.md](docs/MT5_EMA_SETUP_GUIDE.md) — MT5 EMA setup
- [docs/MT5_HISTORICAL_DATA_SETUP.md](docs/MT5_HISTORICAL_DATA_SETUP.md) — Historical data
- [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) — Deployment

### Archive (Historical, ít liên quan hiện tại)
- `docs/archive/` — Old bug fixes, deprecated docs

---

## 📊 TÓM TẮT QUAN TRỌNG NHẤT

### ⭐ 5 Điều cốt lõi cần nhớ

1. **Monolith Architecture**
   File chính `advanced_mt5_monitor_gui.py` chứa MỌI thứ. Strategy files chỉ là config source.

2. **4-Phase State Machine**
   `SCANNING → ARMED → WINDOW_OPEN → IN_TRADE → SCANNING`
   Mỗi phase có conditions và exit paths rõ ràng.

3. **6-Layer Filter Cascade**
   ATR → Angle → Price → Candle → EMA Order → EMA Position → (Time @ entry).
   Tất cả phải pass mới ARM. Re-check tại breakout.

4. **Ray Dalio Position Sizing**
   `risk = balance × allocation% × risk_percent`. Lot tính từ broker tick value thật, KHÔNG hardcode.

5. **Smart Polling**
   Bot chỉ work khi M5 candle close (`minute % 5 == 0`). Fast path khi WINDOW_OPEN. Persistence với atomic write.

---

## 🏷️ VERSION HISTORY

| Version | Date | Highlights |
|---------|------|-----------|
| v1.2.3 | Current | Global Invalidation fix |
| v1.2.0 | 2025-12-03 | JPY pairs (EURJPY, USDJPY) |
| v2.2.0 | 2025-11-16 | UTC timezone & DST fix |
| v2.1.0 | 2025-11-10 | Position sizing fix (broker tick value) |
| v2.0.1 | 2025-11-11 | Pullback system fix |
| v1.1.0 | 2025-10-31 | ATR filter integration |

---

## 🤝 ĐÓNG GÓP & CẢI THIỆN TÀI LIỆU

Nếu bạn:
- Phát hiện logic không đúng → update `logic.md`, `STATE_MACHINE.md`
- Tìm thấy edge case mới → bổ sung vào `STATE_MACHINE.md` § Edge Cases
- Có ý tưởng refactor → ghi vào `ARCHITECTURE.md` § Hướng mở rộng
- Phát hiện tài liệu lỗi thời → mark deprecated trong `MODULES.md`

**Lưu ý:**
- Tài liệu này focus vào CODE STRUCTURE, không trùng lặp với `docs/` (focus vào TRADING STRATEGY)
- Khi code thay đổi (line numbers shift), update tài liệu để giữ chính xác

---

## 🆘 TROUBLESHOOTING REFERENCE

| Triệu chứng | Đọc tài liệu nào |
|------------|------------------|
| Bot không phát hiện signal | logic.md § Crossover, STATE_MACHINE.md § Phase 1 |
| Pullback không activate | STATE_MACHINE.md § Phase 2 |
| Window không mở | STATE_MACHINE.md § Phase 3 |
| Order không gửi được | WORKFLOW.md § Phần E, MODULES.md § MT5 API |
| State bị reset không lý do | STATE_MACHINE.md § Invalidation Rules |
| Lot size sai | DATA_FLOW.md § §6 Order Execution, docs/POSITION_SIZING_FIX_CRITICAL.md |
| Time filter sai | logic.md § Filter 7, docs/UTC_TIMEZONE_FIX_SUMMARY.md |
| MT5 disconnect | WORKFLOW.md § Error Handling, ARCHITECTURE.md § Safety |
| Memory bị stale | STATE_MACHINE.md § Edge Cases 9.5 |
| Crossover bị duplicate | logic.md § Crossover, line 2099 anti-dup |
