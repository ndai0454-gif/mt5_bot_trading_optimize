"""
MT5 Bot Log Monitor & Claude Interface
=========================================
Hệ thống để Claude đọc logs từ bot và phân tích/trả lời

Cách dùng:
1. Bot chạy và ghi log ra bot_activity.log (JSON format)
2. Chạy script này để Claude đọc và phân tích logs
3. Claude có thể đưa ra recommendations
"""
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

# File log của bot (sẽ được bot ghi ra)
ACTIVITY_LOG = "bot_activity.json"
STATE_FILE = "mt5_strategy_state.json"

def load_activity_log():
    """Đọc activity log từ bot"""
    if not os.path.exists(ACTIVITY_LOG):
        return None

    try:
        with open(ACTIVITY_LOG, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None

def load_strategy_state():
    """Đọc trạng thái strategy từ file state"""
    if not os.path.exists(STATE_FILE):
        return None

    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None

def parse_advanced_log():
    """Parse log từ advanced_mt5_monitor_gui.py (nếu có)"""
    log_files = [
        "mt5_advanced_monitor.log",
        "bot_output.log",
        "advanced_mt5_monitor.log"
    ]

    all_logs = []

    for log_file in log_files:
        if os.path.exists(log_file):
            try:
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    for line in lines:
                        all_logs.append({
                            'source': log_file,
                            'content': line.strip(),
                            'timestamp': None  # Parse timestamp if available
                        })
            except:
                pass

    return all_logs

def analyze_current_state():
    """Phân tích trạng thái hiện tại của bot"""
    print("="*70)
    print("📊 TRẠNG THÁI BOT MT5 - BÁO CÁO CHO CLAUDE")
    print("="*70)

    # 1. Đọc strategy state
    state = load_strategy_state()

    if state is None:
        print("\n❌ Không đọc được file trạng thái (mt5_strategy_state.json)")
        print("   → Bot có thể chưa chạy hoặc chưa lưu state")
    else:
        print(f"\n✅ Đã đọc trạng thái từ {STATE_FILE}")
        print(f"\n📋 Các cặp đang theo dõi:")

        for symbol, data in state.items():
            if isinstance(data, dict):
                entry_state = data.get('entry_state', 'UNKNOWN')
                phase = data.get('phase', 'UNKNOWN')
                direction = data.get('armed_direction', None)

                # Status icon
                if entry_state == 'SCANNING':
                    icon = "🔍"
                    desc = "Đang quét tín hiệu"
                elif 'ARMED' in entry_state:
                    icon = "⚔️"
                    desc = f"Đã phát hiện signal {direction}" if direction else "Đã ARM"
                elif entry_state == 'WINDOW_OPEN':
                    icon = "🪟"
                    desc = "Đang chờ breakout"
                elif entry_state == 'IN_TRADE':
                    icon = "📈"
                    desc = "Đang có lệnh"
                else:
                    icon = "❓"
                    desc = entry_state

                print(f"\n   {icon} {symbol}")
                print(f"      State: {entry_state} | Phase: {phase}")
                if direction:
                    print(f"      Direction: {direction}")

                # Pullback count
                pullback_count = data.get('pullback_candle_count', 0)
                if pullback_count > 0:
                    print(f"      Pullback: {pullback_count} candles")

                # Window info
                window_active = data.get('window_active', False)
                if window_active:
                    window_start = data.get('window_bar_start', 'N/A')
                    window_expiry = data.get('window_expiry_bar', 'N/A')
                    current_bar = data.get('current_bar', 'N/A')
                    print(f"      Window: Bar {window_start} - {window_expiry} (current: {current_bar})")

                # Last update
                last_update = data.get('last_update', None)
                if last_update:
                    print(f"      Last Update: {last_update}")

    # 2. Đọc activity log
    activity = load_activity_log()
    if activity:
        print(f"\n📜 Activity Log ({len(activity)} entries):")
        # Show last 5 activities
        for item in activity[-5:]:
            print(f"   {item.get('time', 'N/A')}: {item.get('message', 'N/A')}")

    # 3. Parse advanced logs
    logs = parse_advanced_log()
    if logs:
        print(f"\n📝 Log Files ({len(logs)} lines):")

        # Tìm các log quan trọng
        important_patterns = [
            (r'CROSSOVER', '🔄 Crossover'),
            (r'ARMED', '⚔️ Armed'),
            (r'WINDOW', '🪟 Window'),
            (r'BREAKOUT', '💥 Breakout'),
            (r'ENTRY|EXECUTE', '✅ Entry'),
            (r'FILTER|FAIL|BLOCK', '❌ Filter'),
            (r'RESET|INVALIDATION', '⛔ Reset'),
        ]

        important_logs = []
        for log in logs[-50:]:  # Last 50 lines
            content = log['content']
            if len(content) > 10:  # Skip empty lines
                for pattern, label in important_patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        important_logs.append(f"   {label}: {content[:100]}")
                        break

        # Deduplicate and show
        seen = set()
        for log in important_logs:
            if log not in seen:
                print(log)
                seen.add(log)

    print("\n" + "="*70)
    return state

def get_summary_for_claude():
    """Tạo summary ngắn gọn để Claude phân tích"""
    state = load_strategy_state()

    if not state:
        return "❌ Không có dữ liệu state"

    summary = []

    for symbol, data in state.items():
        if not isinstance(data, dict):
            continue

        entry_state = data.get('entry_state', 'UNKNOWN')
        direction = data.get('armed_direction', '')
        pullback = data.get('pullback_candle_count', 0)

        if entry_state == 'SCANNING':
            summary.append(f"{symbol}: SCANNING - Đang quét")
        elif 'ARMED' in entry_state:
            summary.append(f"{symbol}: {entry_state} - Signal {direction}, Pullback {pullback}/2")
        elif entry_state == 'WINDOW_OPEN':
            window_exp = data.get('window_expiry_bar', 'N/A')
            current_bar = data.get('current_bar', 'N/A')
            summary.append(f"{symbol}: WINDOW_OPEN - Chờ breakout (bar {current_bar}/{window_exp})")
        elif entry_state == 'IN_TRADE':
            summary.append(f"{symbol}: IN_TRADE - Đang có lệnh {direction}")

    return "\n".join(summary)

def check_pending_actions():
    """Kiểm tra các hành động cần thiết"""
    print("\n" + "="*70)
    print("🎯 CLAUDE - CÁC QUYẾT ĐỊNH CẦN THIẾT")
    print("="*70)

    state = load_strategy_state()

    if not state:
        print("❌ Không có dữ liệu")
        return

    for symbol, data in state.items():
        if not isinstance(data, dict):
            continue

        entry_state = data.get('entry_state', '')

        # Phân tích từng trạng thái
        if entry_state == 'SCANNING':
            # Check for crossover signals from indicators
            indicators = data.get('indicators', {})
            if indicators:
                # Check EMA crossover
                print(f"\n{symbol}: SCANNING - Đang quét tín hiệu")

        elif 'ARMED' in entry_state:
            direction = data.get('armed_direction', '')
            pullback_count = data.get('pullback_candle_count', 0)
            max_pullback = 2  # Default

            print(f"\n{symbol}: ARMED_{direction}")
            print(f"   Pullback: {pullback_count}/{max_pullback}")

            if pullback_count >= max_pullback:
                print(f"   ✅ Đủ pullback - Đợi breakout")
            else:
                print(f"   ⏳ Đợi thêm {max_pullback - pullback_count} nến pullback")

        elif entry_state == 'WINDOW_OPEN':
            window_exp = data.get('window_expiry_bar', 0)
            current_bar = data.get('current_bar', 0)
            remaining = window_exp - current_bar

            print(f"\n{symbol}: WINDOW_OPEN")
            print(f"   Bars còn lại: {remaining}")
            print(f"   Trạng thái: Đang monitor breakout")

            if remaining <= 0:
                print(f"   ⚠️ Window sắp hết hạn!")

    print("\n" + "="*70)

def generate_claude_prompt():
    """Generate prompt để gửi cho Claude"""
    summary = get_summary_for_claude()

    prompt = f"""
# MT5 Bot Status - Claude Analysis Request

## Current State:
{summary}

## Yêu cầu:
1. Phân tích xem bot có đang ở trạng thái sẵn sàng vào lệnh không
2. Nếu có cơ hội vào lệnh, phân tích các điều kiện
3. Đưa ra khuyến nghị

## Các câu hỏi:
- Bot có đang chờ tín hiệu gì?
- Có nên can thiệp thủ công không?
- Có vấn đề gì cần lưu ý không?
"""

    return prompt

def main():
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == '--summary':
            print(get_summary_for_claude())
        elif sys.argv[1] == '--prompt':
            print(generate_claude_prompt())
        elif sys.argv[1] == '--check':
            check_pending_actions()
        elif sys.argv[1] == '--help':
            print("""
MT5 Bot Log Monitor - Claude Interface
=======================================

Cách dùng:
  python log_monitor.py              # Phân tích toàn bộ state
  python log_monitor.py --summary   # Xem nhanh các state
  python log_monitor.py --prompt    # Generate prompt cho Claude
  python log_monitor.py --check     # Kiểm tra actions cần thiết
  python log_monitor.py --watch     # Watch logs real-time
            """)
        elif sys.argv[1] == '--watch':
            watch_logs()
        else:
            print(f"Unknown command: {sys.argv[1]}")
    else:
        # Default: full analysis
        analyze_current_state()
        check_pending_actions()

def watch_logs():
    """Watch logs real-time"""
    print("🔴 Watching logs... (Ctrl+C to stop)")

    last_size = 0

    while True:
        try:
            # Check state file
            state = load_strategy_state()
            if state:
                summary = get_summary_for_claude()
                print(f"\n{datetime.now().strftime('%H:%M:%S')}")
                print(summary)

            import time
            time.sleep(10)  # Check every 10 seconds

        except KeyboardInterrupt:
            print("\n👋 Stopped watching")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()