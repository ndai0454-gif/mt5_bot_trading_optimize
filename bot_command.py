"""
MT5 Bot Command Interface
===========================
Cho phép Claude gửi lệnh điều khiển bot qua file command queue

Cách dùng:
1. Claude phân tích logs bằng log_monitor.py
2. Claude ghi lệnh vào command queue (bot_commands.json)
3. Bot đọc và thực thi lệnh
"""
import json
import os
from datetime import datetime
from pathlib import Path

# Command queue file
COMMAND_QUEUE = "bot_commands.json"

# Available commands
COMMANDS = {
    'RESET_STATE': 'Reset state của một symbol về SCANNING',
    'FORCE_ENTRY': 'Force bot vào lệnh (nếu đủ điều kiện)',
    'SKIP_PULLBACK': 'Bỏ qua pullback, vào thẳng WINDOW',
    'EXTEND_WINDOW': 'Gia hạn window thêm N bars',
    'CANCEL_ENTRY': 'Hủy lệnh đang chờ',
    'SET_FILTER': 'Thay đổi giá trị filter',
    'STATUS': 'Kiểm tra trạng thái',
    'HELP': 'Hiển thị help',
}

def write_command(command_type, params=None, priority=1):
    """Ghi một lệnh vào command queue"""
    commands = load_commands()

    new_command = {
        'id': datetime.now().strftime('%Y%m%d%H%M%S'),
        'type': command_type,
        'params': params or {},
        'priority': priority,
        'created_at': datetime.now().isoformat(),
        'status': 'PENDING'
    }

    commands.append(new_command)

    with open(COMMAND_QUEUE, 'w', encoding='utf-8') as f:
        json.dump(commands, f, indent=2, ensure_ascii=False)

    print(f"✅ Đã ghi lệnh: {command_type}")
    return new_command['id']

def load_commands():
    """Đọc tất cả commands từ queue"""
    if not os.path.exists(COMMAND_QUEUE):
        return []

    try:
        with open(COMMAND_QUEUE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def clear_commands():
    """Xóa tất cả commands"""
    with open(COMMAND_QUEUE, 'w', encoding='utf-8') as f:
        json.dump([], f)
    print("🗑️ Đã xóa tất cả commands")

def get_pending_commands():
    """Lấy các commands đang chờ"""
    commands = load_commands()
    return [c for c in commands if c.get('status') == 'PENDING']

def mark_command_done(command_id):
    """Đánh dấu command đã hoàn thành"""
    commands = load_commands()

    for cmd in commands:
        if cmd['id'] == command_id:
            cmd['status'] = 'DONE'
            cmd['completed_at'] = datetime.now().isoformat()

    with open(COMMAND_QUEUE, 'w', encoding='utf-8') as f:
        json.dump(commands, f, indent=2)

# ============================================
# CONVENIENCE FUNCTIONS - GỌI TRỰC TIẾP
# ============================================

def cmd_reset(symbol):
    """Reset một symbol về SCANNING"""
    return write_command('RESET_STATE', {'symbol': symbol})

def cmd_skip_pullback(symbol):
    """Bỏ qua pullback, vào thẳng window"""
    return write_command('SKIP_PULLBACK', {'symbol': symbol})

def cmd_extend_window(symbol, bars=10):
    """Gia hạn window thêm N bars"""
    return write_command('EXTEND_WINDOW', {'symbol': symbol, 'bars': bars})

def cmd_cancel_entry(symbol):
    """Hủy entry đang chờ"""
    return write_command('CANCEL_ENTRY', {'symbol': symbol})

def cmd_set_filter(symbol, filter_name, value):
    """Set filter value"""
    return write_command('SET_FILTER', {
        'symbol': symbol,
        'filter': filter_name,
        'value': value
    })

def cmd_status():
    """Kiểm tra status"""
    return write_command('STATUS', {})

# ============================================
# CLI INTERFACE
# ============================================

def show_help():
    """Hiển thị help"""
    print("""
╔════════════════════════════════════════════════════════════════╗
║           MT5 BOT COMMAND INTERFACE                           ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║  Cách dùng: python bot_command.py <command> [params]          ║
║                                                                ║
║  Commands:                                                     ║
║                                                                ║
║    reset <symbol>           Reset state về SCANNING            ║
║       ví dụ: python bot_command.py reset XAUUSD               ║
║                                                                ║
║    skip-pullback <symbol>  Bỏ qua pullback, vào window        ║
║       ví dụ: python bot_command.py skip-pullback XAUUSD      ║
║                                                                ║
║    extend <symbol> [bars]  Gia hạn window                     ║
║       ví dụ: python bot_command.py extend XAUUSD 20         ║
║                                                                ║
║    cancel <symbol>          Hủy entry đang chờ                ║
║       ví dụ: python bot_command.py cancel XAUUSD             ║
║                                                                ║
║    set <symbol> <filter> <value>  Set filter value            ║
║       ví dụ: python bot_command.py set XAUUSD LONG_ATR_MIN 3.0
║                                                                ║
║    status                   Xem trạng thái commands           ║
║                                                                ║
║    clear                   Xóa tất cả commands               ║
║                                                                ║
║    queue                   Xem commands đang chờ             ║
║                                                                ║
║    help                    Hiển thị help này                  ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
    """)

def main():
    import sys

    if len(sys.argv) < 2:
        show_help()
        return

    cmd = sys.argv[1].lower()

    if cmd == 'reset':
        if len(sys.argv) < 3:
            print("❌ Thiếu symbol! Ví dụ: python bot_command.py reset XAUUSD")
        else:
            cmd_reset(sys.argv[2])

    elif cmd == 'skip-pullback':
        if len(sys.argv) < 3:
            print("❌ Thiếu symbol! Ví dụ: python bot_command.py skip-pullback XAUUSD")
        else:
            cmd_skip_pullback(sys.argv[2])

    elif cmd == 'extend':
        if len(sys.argv) < 3:
            print("❌ Thiếu symbol! Ví dụ: python bot_command.py extend XAUUSD 20")
        else:
            bars = int(sys.argv[3]) if len(sys.argv) > 3 else 10
            cmd_extend_window(sys.argv[2], bars)

    elif cmd == 'cancel':
        if len(sys.argv) < 3:
            print("❌ Thiếu symbol! Ví dụ: python bot_command.py cancel XAUUSD")
        else:
            cmd_cancel_entry(sys.argv[2])

    elif cmd == 'set':
        if len(sys.argv) < 5:
            print("❌ Thiếu params! Ví dụ: python bot_command.py set XAUUSD LONG_ATR_MIN 3.0")
        else:
            cmd_set_filter(sys.argv[2], sys.argv[3], sys.argv[4])

    elif cmd == 'status':
        pending = get_pending_commands()
        if pending:
            print(f"📋 Commands đang chờ: {len(pending)}")
            for p in pending:
                print(f"   - {p['type']}: {p['params']}")
        else:
            print("✅ Không có command đang chờ")

    elif cmd == 'queue':
        commands = load_commands()
        print(f"📋 Tổng commands: {len(commands)}")
        for c in commands[-10:]:
            status_icon = "⏳" if c['status'] == 'PENDING' else "✅" if c['status'] == 'DONE' else "❌"
            print(f"   {status_icon} {c['type']} - {c.get('params', {})}")

    elif cmd == 'clear':
        clear_commands()

    elif cmd == 'help':
        show_help()

    else:
        print(f"❌ Unknown command: {cmd}")
        show_help()

if __name__ == "__main__":
    main()