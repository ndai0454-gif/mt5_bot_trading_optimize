"""
MT5 Bot - Claude Interface Tổng Hợp
=====================================
Script chính để Claude đọc logs, phân tích và điều khiển bot

Cách dùng:
    python claude_interface.py <command>

Commands:
    status      - Xem trạng thái tất cả symbols
    analyze     - Phân tích chi tiết (cho Claude)
    watch       - Watch real-time (Ctrl+C để dừng)
    send <cmd>  - Gửi lệnh cho bot
    help        - Xem help
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import re

# Fix Windows console encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Files
STATE_FILE = "mt5_strategy_state.json"
ACTIVITY_LOG = "bot_activity.json"
COMMAND_QUEUE = "bot_commands.json"

# ============================================
# STATE READING
# ============================================

def read_state():
    """Đọc trạng thái bot"""
    if not os.path.exists(STATE_FILE):
        return None

    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None

def get_symbol_info(symbol_data):
    """Trích xuất thông tin quan trọng của một symbol"""
    info = {
        'state': symbol_data.get('entry_state', 'UNKNOWN'),
        'phase': symbol_data.get('phase', 'UNKNOWN'),
        'direction': symbol_data.get('armed_direction'),
        'pullback': symbol_data.get('pullback_candle_count', 0),
        'current_bar': symbol_data.get('current_bar', 0),
        'window_active': symbol_data.get('window_active', False),
        'last_update': symbol_data.get('last_update'),
    }

    # Window info
    if info['window_active']:
        info['window_start'] = symbol_data.get('window_bar_start')
        info['window_expiry'] = symbol_data.get('window_expiry_bar')
        info['window_remaining'] = (info['window_expiry'] or 0) - info['current_bar']

    # Breakout info
    info['breakout_level'] = symbol_data.get('breakout_level')
    info['window_top'] = symbol_data.get('window_top_limit')
    info['window_bottom'] = symbol_data.get('window_bottom_limit')

    return info

# ============================================
# STATUS COMMANDS
# ============================================

def cmd_status():
    """Hiển thị trạng thái ngắn gọn"""
    state = read_state()

    if not state:
        print("❌ Bot chưa chạy hoặc không có state file")
        return

    print("\n" + "="*60)
    print("📊 MT5 BOT STATUS")
    print("="*60)

    for symbol, data in state.items():
        if not isinstance(data, dict):
            continue

        info = get_symbol_info(data)

        # Icon theo state
        icons = {
            'SCANNING': '🔍',
            'ARMED_LONG': '🟢',
            'ARMED_SHORT': '🔴',
            'WINDOW_OPEN': '🪟',
            'IN_TRADE': '📈',
        }
        icon = icons.get(info['state'], '❓')

        print(f"\n{icon} {symbol}: {info['state']}")

        if info['direction']:
            print(f"   Direction: {info['direction']}")

        if info['pullback'] > 0:
            print(f"   Pullback: {info['pullback']}/2 candles")

        if info['window_active']:
            print(f"   Window: {info['current_bar']}/{info['window_expiry']} "
                  f"(còn {info['window_remaining']} bars)")

        if info['last_update']:
            print(f"   Last Update: {info['last_update']}")

    print("\n" + "="*60)

def cmd_analyze():
    """Phân tích chi tiết cho Claude"""
    state = read_state()

    if not state:
        print("❌ Không có dữ liệu state")
        return

    analysis = []
    analysis.append("# MT5 BOT ANALYSIS - FOR CLAUDE")
    analysis.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    analysis.append("\n" + "="*50)

    # Phân tích từng symbol
    for symbol, data in state.items():
        if not isinstance(data, dict):
            continue

        info = get_symbol_info(data)

        analysis.append(f"\n## {symbol}")
        analysis.append(f"- **State**: {info['state']}")
        analysis.append(f"- **Direction**: {info['direction'] or 'None'}")
        analysis.append(f"- **Pullback Count**: {info['pullback']}/2")

        # Phân tích theo state
        if info['state'] == 'SCANNING':
            analysis.append("\n### Analysis:")
            analysis.append("- Bot đang trong trạng thái quét tín hiệu")
            analysis.append("- Đang đợi EMA crossover")
            analysis.append("- Action: Chờ signal")

        elif 'ARMED' in info['state']:
            direction = info['direction']
            remaining = 2 - info['pullback']

            analysis.append("\n### Analysis:")
            analysis.append(f"- Đã phát hiện signal {direction}")
            if remaining > 0:
                analysis.append(f"- Đợi thêm {remaining} nến pullback")
            else:
                analysis.append(f"- ✅ Đủ pullback, đợi breakout")

        elif info['state'] == 'WINDOW_OPEN':
            analysis.append("\n### Analysis:")
            analysis.append(f"- Đang monitor breakout")
            analysis.append(f"- Window còn {info['window_remaining']} bars")
            if info['breakout_level']:
                analysis.append(f"- Breakout level: {info['breakout_level']}")

        elif info['state'] == 'IN_TRADE':
            analysis.append("\n### Analysis:")
            analysis.append("- Bot đang có lệnh đang mở")
            analysis.append("- Không thể vào lệnh mới")

    # Recommendations
    analysis.append("\n" + "="*50)
    analysis.append("\n## RECOMMENDATIONS")

    can_enter = []
    waiting = []
    problems = []

    for symbol, data in state.items():
        if not isinstance(data, dict):
            continue

        info = get_symbol_info(data)
        state = info['state']

        if state == 'SCANNING':
            waiting.append(f"{symbol}: Đang quét signal")

        elif 'ARMED' in state and info['pullback'] >= 2:
            can_enter.append(f"{symbol}: Sẵn sàng breakout")

        elif state == 'WINDOW_OPEN':
            if info['window_remaining'] <= 5:
                problems.append(f"{symbol}: Window sắp hết hạn")

    if can_enter:
        analysis.append("\n### ✅ Sẵn sàng vào lệnh:")
        for item in can_enter:
            analysis.append(f"- {item}")

    if waiting:
        analysis.append("\n### ⏳ Đang chờ:")
        for item in waiting:
            analysis.append(f"- {item}")

    if problems:
        analysis.append("\n### ⚠️ Cần can thiệp:")
        for item in problems:
            analysis.append(f"- {item}")

    print("\n".join(analysis))

# ============================================
# COMMAND SENDING
# ============================================

def cmd_send(command_str):
    """Gửi lệnh cho bot"""
    # Parse command
    parts = command_str.split()
    if not parts:
        print("❌ Không có command")
        return

    cmd = parts[0].lower()
    params = parts[1:] if len(parts) > 1 else []

    commands = {
        'reset': 'RESET_STATE',
        'skip': 'SKIP_PULLBACK',
        'extend': 'EXTEND_WINDOW',
        'cancel': 'CANCEL_ENTRY',
    }

    if cmd in commands:
        if not params:
            print(f"❌ Thiếu symbol! Ví dụ: send {cmd} XAUUSD")
            return

        symbol = params[0]
        cmd_type = commands[cmd]
        extra = {}

        if cmd == 'extend' and len(params) > 1:
            extra['bars'] = int(params[1])

        # Write to command queue
        queue = []
        if os.path.exists(COMMAND_QUEUE):
            try:
                with open(COMMAND_QUEUE, 'r') as f:
                    queue = json.load(f)
            except:
                pass

        queue.append({
            'id': datetime.now().strftime('%Y%m%d%H%M%S%f'),
            'type': cmd_type,
            'params': {'symbol': symbol, **extra},
            'priority': 1,
            'created_at': datetime.now().isoformat(),
            'status': 'PENDING'
        })

        with open(COMMAND_QUEUE, 'w') as f:
            json.dump(queue, f, indent=2)

        print(f"✅ Đã gửi lệnh: {cmd_type} {symbol}")

    elif cmd == 'status':
        if os.path.exists(COMMAND_QUEUE):
            with open(COMMAND_QUEUE, 'r') as f:
                queue = json.load(f)
            pending = [c for c in queue if c.get('status') == 'PENDING']
            print(f"📋 Commands đang chờ: {len(pending)}")
            for c in pending:
                print(f"   - {c['type']}: {c.get('params', {})}")
        else:
            print("✅ Không có command nào")

    elif cmd == 'clear':
        with open(COMMAND_QUEUE, 'w') as f:
            json.dump([], f)
        print("🗑️ Đã clear tất cả commands")

    else:
        print(f"❌ Unknown command: {cmd}")
        print("Commands: reset, skip, extend, cancel, status, clear")

def cmd_watch():
    """Watch real-time"""
    print("🔴 Watching bot state... (Ctrl+C to stop)")
    print()

    last_state = None

    while True:
        try:
            state = read_state()

            if state != last_state:
                # State changed
                print(f"\n{datetime.now().strftime('%H:%M:%S')} - State changed:")
                for symbol, data in state.items():
                    if isinstance(data, dict):
                        info = get_symbol_info(data)
                        print(f"  {symbol}: {info['state']}")

                last_state = state
            else:
                # No change
                print(f".", end="", flush=True)

            import time
            time.sleep(5)

        except KeyboardInterrupt:
            print("\n👋 Stopped")
            break

# ==========================================
# MAIN
# ==========================================

def show_help():
    print("""
╔══════════════════════════════════════════════════════════════╗
║            MT5 BOT - CLAUDE INTERFACE                         ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Cách dùng: python claude_interface.py <command>            ║
║                                                              ║
║  Commands:                                                    ║
║                                                              ║
║    status           Xem trạng thái ngắn gọn                  ║
║       ví dụ: python claude_interface.py status              ║
║                                                              ║
║    analyze          Phân tích chi tiết (cho Claude)          ║
║       ví dụ: python claude_interface.py analyze             ║
║                                                              ║
║    watch            Watch real-time (5s refresh)             ║
║       ví dụ: python claude_interface.py watch              ║
║                                                              ║
║    send <cmd>       Gửi lệnh cho bot                         ║
║       ví dụ: python claude_interface.py send reset XAUUSD  ║
║                                                              ║
║    send status      Xem commands đang chờ                    ║
║    send clear       Clear all commands                       ║
║                                                              ║
║    help             Hiển thị help                             ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝

📌 CÁCH CLAUDE PHÂN TÍCH VÀ ĐIỀU KHIỂN:

   1. Claude đọc state:  python claude_interface.py status
   2. Claude phân tích:  python claude_interface.py analyze
   3. Claude gửi lệnh:    python claude_interface.py send reset XAUUSD

""")

def main():
    if len(sys.argv) < 2:
        show_help()
        return

    cmd = sys.argv[1].lower()

    if cmd == 'status':
        cmd_status()

    elif cmd == 'analyze':
        cmd_analyze()

    elif cmd == 'watch':
        cmd_watch()

    elif cmd == 'send':
        if len(sys.argv) < 3:
            print("❌ Thiếu command! Ví dụ: send reset XAUUSD")
        else:
            cmd_send(" ".join(sys.argv[2:]))

    elif cmd == 'help':
        show_help()

    else:
        print(f"❌ Unknown command: {cmd}")
        show_help()

if __name__ == "__main__":
    main()