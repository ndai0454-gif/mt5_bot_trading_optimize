"""
Auto Monitor - Claude Automated Bot Monitoring
================================================
Script chạy tự động để Claude monitor bot và ra quyết định

Cách dùng:
    python auto_monitor.py              # Chạy với default (30s)
    python auto_monitor.py --interval 60 # Chạy mỗi 60 giây
    python auto_monitor.py --once       # Chạy 1 lần rồi dừng
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Config
STATE_FILE = "mt5_strategy_state.json"
COMMAND_QUEUE = "bot_commands.json"
NOTIFICATION_FILE = "bot_notifications.json"
LOG_FILE = "auto_monitor.log"

DEFAULT_INTERVAL = 30  # 30 seconds

# Thresholds for auto-decisions
THRESHOLDS = {
    'WINDOW_EXPIRY_BARS': 5,  # Cảnh báo khi window còn < 5 bars
    'SCANNING_TIMEOUT_HOURS': 2,  # Cảnh báo khi SCANNING quá lâu
    'PULLBACK_TIMEOUT_BARS': 10,  # Reset nếu pullback quá lâu
}

def log(msg):
    """Log to file and console"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_msg = f"[{timestamp}] {msg}"

    print(log_msg)

    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_msg + '\n')
    except:
        pass

def read_state():
    """Đọc state từ file"""
    if not os.path.exists(STATE_FILE):
        return None

    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None

def read_notifications():
    """Đọc notifications"""
    if not os.path.exists(NOTIFICATION_FILE):
        return []

    try:
        with open(NOTIFICATION_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def send_command(cmd_type, symbol, params=None):
    """Gửi lệnh cho bot"""
    commands = []
    if os.path.exists(COMMAND_QUEUE):
        try:
            with open(COMMAND_QUEUE, 'r') as f:
                commands = json.load(f)
        except:
            pass

    cmd = {
        'id': datetime.now().strftime('%Y%m%d%H%M%S%f'),
        'type': cmd_type,
        'params': {'symbol': symbol, **(params or {})},
        'priority': 1,
        'created_at': datetime.now().isoformat(),
        'status': 'PENDING'
    }

    commands.append(cmd)

    try:
        with open(COMMAND_QUEUE, 'w', encoding='utf-8') as f:
            json.dump(commands, f, indent=2)
        return True
    except:
        return False

def analyze_and_decide(state):
    """Phân tích state và quyết định hành động"""
    if not state:
        return None, "No state data"

    actions = []

    for symbol, data in state.items():
        if not isinstance(data, dict):
            continue

        entry_state = data.get('entry_state', 'SCANNING')
        armed_direction = data.get('armed_direction')
        pullback_count = data.get('pullback_candle_count', 0)
        current_bar = data.get('current_bar', 0)
        window_expiry = data.get('window_expiry_bar')
        last_update = data.get('last_update')

        # =====================
        # RULE 1: Window sắp hết hạn
        # =====================
        if entry_state == 'WINDOW_OPEN' and window_expiry:
            remaining = window_expiry - current_bar

            if remaining <= 0:
                # Window đã hết hạn
                log(f"⚠️ {symbol}: Window EXPIRED - Auto reset")
                send_command('RESET_STATE', symbol)
                actions.append(f"RESET {symbol} (window expired)")

            elif remaining <= THRESHOLDS['WINDOW_EXPIRY_BARS']:
                log(f"⏰ {symbol}: Window còn {remaining} bars")

        # =====================
        # RULE 2: Pullback quá lâu
        # =====================
        if 'ARMED' in entry_state and pullback_count < 2:
            # Kiểm tra thời gian từ lúc ARMED
            if last_update:
                try:
                    update_time = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                    # Assume local time for now
                    update_time = datetime.strptime(last_update[:19], '%Y-%m-%d %H:%M:%S')

                    elapsed = datetime.now() - update_time

                    # Nếu ARMED quá lâu (> 2 giờ) và chưa đủ pullback
                    if elapsed.total_seconds() > 7200:  # 2 hours
                        log(f"⚠️ {symbol}: ARMED timeout (>2h) - Auto reset")
                        send_command('RESET_STATE', symbol)
                        actions.append(f"RESET {symbol} (armed timeout)")
                except:
                    pass

        # =====================
        # RULE 3: SCANNING quá lâu không signal
        # =====================
        if entry_state == 'SCANNING' and last_update:
            try:
                update_time = datetime.strptime(last_update[:19], '%Y-%m-%d %H:%M:%S')
                elapsed = datetime.now() - update_time

                hours = elapsed.total_seconds() / 3600

                if hours > THRESHOLDS['SCANNING_TIMEOUT_HOURS']:
                    log(f"💡 {symbol}: SCANNING > {THRESHOLDS['SCANNING_TIMEOUT_HOURS']}h without signal")
                    # Chỉ log, không auto reset - bình thường
            except:
                pass

        # =====================
        # RULE 4: Pullback đủ rồi, có thể vào lệnh
        # =====================
        if 'ARMED' in entry_state and pullback_count >= 2:
            log(f"✅ {symbol}: ARMED_{armed_direction} - Pullback complete, waiting breakout")

    return actions, "Analysis complete"

def check_notifications():
    """Kiểm tra notifications gần đây"""
    notifications = read_notifications()

    if not notifications:
        return []

    # Lấy notifications trong 5 phút gần đây
    recent = []
    now = datetime.now()

    for n in notifications[-10:]:  # Check last 10
        try:
            n_time = datetime.fromisoformat(n['timestamp'])
            if (now - n_time).total_seconds() < 300:  # 5 minutes
                recent.append(n)
        except:
            pass

    return recent

def one_cycle():
    """Một chu kỳ monitoring"""
    log("─" * 50)
    log("🔍 MONITORING CYCLE")

    # 1. Đọc state
    state = read_state()

    if not state:
        log("❌ Không đọc được state")
        return

    # 2. Hiển thị summary
    log("📊 State Summary:")
    for symbol, data in state.items():
        if isinstance(data, dict):
            state_str = data.get('entry_state', 'UNKNOWN')
            direction = data.get('armed_direction', '')
            pullback = data.get('pullback_candle_count', 0)

            icons = {
                'SCANNING': '🔍',
                'ARMED_LONG': '🟢',
                'ARMED_SHORT': '🔴',
                'WINDOW_OPEN': '🪟',
                'IN_TRADE': '📈',
            }
            icon = icons.get(state_str, '❓')

            info = f"{icon} {symbol}: {state_str}"
            if direction:
                info += f" ({direction})"
            if pullback > 0:
                info += f" | Pullback: {pullback}/2"

            log(f"   {info}")

    # 3. Kiểm tra notifications
    recent_notifs = check_notifications()
    if recent_notifs:
        log(f"📋 Recent notifications ({len(recent_notifs)}):")
        for n in recent_notifs[-3:]:
            log(f"   {n['type']}: {n['symbol']} - {n['message']}")

    # 4. Analyze và decide
    actions, _ = analyze_and_decide(state)

    if actions:
        log(f"🎯 Actions taken: {', '.join(actions)}")
    else:
        log("✅ No action needed")

    log("─" * 50)

def run_monitor(interval=DEFAULT_INTERVAL, run_once=False):
    """Chạy monitor loop"""
    log(f"🚀 Auto Monitor Started (interval: {interval}s)")

    if run_once:
        one_cycle()
    else:
        try:
            while True:
                one_cycle()
                time.sleep(interval)
        except KeyboardInterrupt:
            log("\n👋 Stopped by user")

def main():
    interval = DEFAULT_INTERVAL
    run_once = False

    # Parse args
    for arg in sys.argv[1:]:
        if arg == '--once':
            run_once = True
        elif arg.startswith('--interval'):
            # --interval 60
            parts = arg.split('=')
            if len(parts) > 1:
                interval = int(parts[1])
            elif len(sys.argv) > sys.argv.index(arg) + 1:
                interval = int(sys.argv[sys.argv.index(arg) + 1])
        elif arg == '--help':
            print("""
Auto Monitor - Claude Automated Bot Monitoring
================================================

Usage: python auto_monitor.py [options]

Options:
  --interval=N    Set check interval in seconds (default: 30)
  --once          Run only one cycle then stop
  --help          Show this help

Examples:
  python auto_monitor.py                    # Run every 30 seconds
  python auto_monitor.py --interval=60       # Run every 60 seconds
  python auto_monitor.py --once             # Run once and exit
            """)
            return

    run_monitor(interval, run_once)

if __name__ == "__main__":
    main()