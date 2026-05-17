"""
Bot Notification System
=======================
Bot tự đẩy thông báo vào file để Claude đọc real-time

Cách dùng:
1. Bot ghi events vào bot_notifications.json
2. Claude đọc file này để biết bot đang làm gì
3. Claude có thể phản ứng ngay lập tức
"""
import json
import os
from datetime import datetime
from pathlib import Path
import threading

NOTIFICATION_FILE = "bot_notifications.json"

# Event types
EVENT_CROSSOVER = "CROSSOVER"
EVENT_ARMED = "ARMED"
EVENT_PULLBACK = "PULLBACK"
EVENT_WINDOW = "WINDOW"
EVENT_BREAKOUT = "BREAKOUT"
EVENT_ENTRY = "ENTRY"
EVENT_EXIT = "EXIT"
EVENT_FILTER_FAILED = "FILTER_FAILED"
EVENT_ERROR = "ERROR"
EVENT_INFO = "INFO"

class BotNotifier:
    """Thread-safe notification system cho bot"""

    def __init__(self, log_file=NOTIFICATION_FILE):
        self.log_file = log_file
        self.lock = threading.Lock()
        self.max_events = 100  # Giữ 100 event gần nhất

        # Initialize file
        self._init_file()

    def _init_file(self):
        """Khởi tạo file notification"""
        if not os.path.exists(self.log_file):
            self._write_events([])

    def _read_events(self):
        """Đọc events từ file"""
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []

    def _write_events(self, events):
        """Ghi events vào file"""
        try:
            with open(self.log_file, 'w', encoding='utf-8') as f:
                json.dump(events, f, indent=2, ensure_ascii=False)
        except:
            pass

    def push(self, event_type, symbol, message, data=None):
        """
        Push một event

        Args:
            event_type: EVENT_CROSSOVER, EVENT_ARMED, etc.
            symbol: Symbol name (XAUUSD, EURUSD, etc.)
            message: Mô tả ngắn
            data: Dict chứa thông tin bổ sung (optional)
        """
        with self.lock:
            events = self._read_events()

            event = {
                'timestamp': datetime.now().isoformat(),
                'type': event_type,
                'symbol': symbol,
                'message': message,
                'data': data or {}
            }

            events.append(event)

            # Keep only recent events
            if len(events) > self.max_events:
                events = events[-self.max_events:]

            self._write_events(events)

    def get_recent(self, count=10, event_type=None, symbol=None):
        """
        Lấy các event gần nhất

        Args:
            count: Số lượng event
            event_type: Lọc theo loại (optional)
            symbol: Lọc theo symbol (optional)
        """
        with self.lock:
            events = self._read_events()

            # Filter
            if event_type:
                events = [e for e in events if e['type'] == event_type]
            if symbol:
                events = [e for e in events if e['symbol'] == symbol]

            return events[-count:]

    def get_latest_by_symbol(self, symbol):
        """Lấy event cuối cùng của một symbol"""
        events = self.get_recent(50, symbol=symbol)
        if events:
            return events[-1]
        return None

    def clear(self):
        """Xóa tất cả notifications"""
        with self.lock:
            self._write_events([])

    def get_summary(self):
        """Lấy tóm tắt trạng thái"""
        with self.lock:
            events = self._read_events()

            # Group by symbol và type
            summary = {}
            for event in events:
                symbol = event['symbol']
                if symbol not in summary:
                    summary[symbol] = {}

                event_type = event['type']
                if event_type not in summary[symbol]:
                    summary[symbol][event_type] = 0

                summary[symbol][event_type] += 1

            return summary


# Convenience functions
_notifier = None

def get_notifier():
    """Lấy singleton notifier"""
    global _notifier
    if _notifier is None:
        _notifier = BotNotifier()
    return _notifier

def notify_crossover(symbol, direction, price, data=None):
    """Thông báo crossover"""
    get_notifier().push(EVENT_CROSSOVER, symbol,
        f"{direction} crossover at {price}",
        data)

def notify_armed(symbol, direction, price, data=None):
    """Thông báo ARMED"""
    get_notifier().push(EVENT_ARMED, symbol,
        f"ARMED_{direction} at {price}",
        data)

def notify_pullback(symbol, count, max_count, data=None):
    """Thông báo pullback"""
    get_notifier().push(EVENT_PULLBACK, symbol,
        f"Pullback {count}/{max_count}",
        data)

def notify_window(symbol, direction, expiry_bar, data=None):
    """Thông báo window opened"""
    get_notifier().push(EVENT_WINDOW, symbol,
        f"WINDOW_OPEN ({direction}) expires at bar {expiry_bar}",
        data)

def notify_breakout(symbol, direction, price, data=None):
    """Thông báo breakout"""
    get_notifier().push(EVENT_BREAKOUT, symbol,
        f"{direction} BREAKOUT at {price}",
        data)

def notify_entry(symbol, direction, price, ticket=None, data=None):
    """Thông báo entry executed"""
    d = data or {}
    if ticket:
        d['ticket'] = ticket

    get_notifier().push(EVENT_ENTRY, symbol,
        f"{direction} ENTRY at {price}" + (f" (Ticket: {ticket})" if ticket else ""),
        d)

def notify_exit(symbol, direction, pnl=None, data=None):
    """Thông báo exit"""
    d = data or {}
    if pnl is not None:
        d['pnl'] = pnl

    msg = f"{direction} EXIT"
    if pnl is not None:
        msg += f" | PnL: ${pnl:.2f}"

    get_notifier().push(EVENT_EXIT, symbol, msg, d)

def notify_filter_failed(symbol, filter_name, reason, data=None):
    """Thông báo filter failed"""
    get_notifier().push(EVENT_FILTER_FAILED, symbol,
        f"Filter {filter_name} failed: {reason}",
        data)

def notify_error(symbol, error_message, data=None):
    """Thông báo error"""
    get_notifier().push(EVENT_ERROR, symbol, error_message, data)

def notify_info(symbol, message, data=None):
    """Thông báo info"""
    get_notifier().push(EVENT_INFO, symbol, message, data)


# CLI interface
def main():
    import sys

    if len(sys.argv) < 2:
        # Show recent
        notifier = get_notifier()
        events = notifier.get_recent(10)

        print("="*60)
        print("📊 BOT NOTIFICATIONS (Last 10)")
        print("="*60)

        for e in events:
            print(f"\n[{e['timestamp']}] {e['type']} - {e['symbol']}")
            print(f"   {e['message']}")
            if e.get('data'):
                print(f"   Data: {e['data']}")

        print("\n" + "="*60)
        return

    cmd = sys.argv[1]

    if cmd == '--clear':
        get_notifier().clear()
        print("✅ Cleared notifications")

    elif cmd == '--summary':
        summary = get_notifier().get_summary()
        print("📊 Event Summary:")
        for symbol, events in summary.items():
            print(f"\n{symbol}:")
            for event_type, count in events.items():
                print(f"   {event_type}: {count}")

    elif cmd == '--watch':
        print("🔴 Watching notifications... (Ctrl+C to stop)")
        import time

        last_count = 0
        while True:
            try:
                events = get_notifier().get_recent(5)
                if len(events) > last_count:
                    # New events
                    print(f"\n{datetime.now().strftime('%H:%M:%S')} - New events:")
                    for e in events[last_count:]:
                        print(f"   {e['type']}: {e['symbol']} - {e['message']}")

                    last_count = len(events)

                time.sleep(2)

            except KeyboardInterrupt:
                print("\n👋 Stopped")
                break

    elif cmd == '--by-symbol':
        if len(sys.argv) < 3:
            print("Usage: python bot_notifier.py --by-symbol XAUUSD")
        else:
            symbol = sys.argv[2]
            events = get_notifier().get_recent(20, symbol=symbol)
            print(f"📋 Events for {symbol}:")
            for e in events:
                print(f"   {e['timestamp']} | {e['type']} | {e['message']}")

    elif cmd == '--help':
        print("""
Bot Notifier - CLI
===================

Usage: python bot_notifier.py [command]

Commands:
  (none)              Show last 10 notifications
  --clear             Clear all notifications
  --summary           Show event summary by symbol
  --watch             Watch real-time (Ctrl+C to stop)
  --by-symbol <sym>   Show events for a symbol
  --help              Show this help

Examples:
  python bot_notifier.py
  python bot_notifier.py --by-symbol XAUUSD
  python bot_notifier.py --watch
        """)

    else:
        print(f"Unknown command: {cmd}")
        print("Use --help for usage information")


if __name__ == "__main__":
    main()