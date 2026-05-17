"""
Command Processor cho Bot
===========================
Script này cần được tích hợp vào bot để đọc và thực thi commands
từ file bot_commands.json

Đặt code này vào vòng lặp chính của bot (trong check_and_update_all_symbols)
"""
import json
import os
import sys
from datetime import datetime

# Fix Windows console encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

COMMAND_QUEUE = "bot_commands.json"

def process_commands(strategy_states, logger=None):
    """
    Đọc và thực thi commands từ queue

    Args:
        strategy_states: Dictionary chứa state của các symbols
        logger: Hàm log (nếu có)

    Returns:
        bool: Có command nào được thực thi không
    """
    if not os.path.exists(COMMAND_QUEUE):
        return False

    try:
        with open(COMMAND_QUEUE, 'r', encoding='utf-8') as f:
            commands = json.load(f)
    except:
        return False

    # Lọc commands pending
    pending = [c for c in commands if c.get('status') == 'PENDING']

    if not pending:
        return False

    executed = False

    for cmd in pending:
        cmd_type = cmd.get('type', '')
        params = cmd.get('params', {})
        symbol = params.get('symbol', '')

        success = False

        if cmd_type == 'RESET_STATE':
            # Reset state về SCANNING
            if symbol in strategy_states:
                strategy_states[symbol]['entry_state'] = 'SCANNING'
                strategy_states[symbol]['phase'] = 'SCANNING'
                strategy_states[symbol]['armed_direction'] = None
                strategy_states[symbol]['pullback_candle_count'] = 0
                strategy_states[symbol]['window_active'] = False

                if logger:
                    logger(f"🔄 Command: Reset {symbol} to SCANNING")

                success = True

        elif cmd_type == 'SKIP_PULLBACK':
            # Bỏ qua pullback, chuyển thẳng sang WINDOW_OPEN
            if symbol in strategy_states:
                state = strategy_states[symbol]
                if 'ARMED' in state.get('entry_state', ''):
                    state['pullback_candle_count'] = 2  # Force complete
                    # Sẽ được xử lý trong state machine

                    if logger:
                        logger(f"⏭️ Command: Skip pullback for {symbol}")

                    success = True

        elif cmd_type == 'EXTEND_WINDOW':
            # Gia hạn window
            bars = params.get('bars', 10)
            if symbol in strategy_states:
                state = strategy_states[symbol]
                current_exp = state.get('window_expiry_bar', 0)
                state['window_expiry_bar'] = current_exp + bars

                if logger:
                    logger(f"⏰ Command: Extend window for {symbol} +{bars} bars")

                success = True

        elif cmd_type == 'CANCEL_ENTRY':
            # Hủy entry đang chờ
            if symbol in strategy_states:
                strategy_states[symbol]['entry_state'] = 'SCANNING'
                strategy_states[symbol]['phase'] = 'SCANNING'

                if logger:
                    logger(f"❌ Command: Cancel entry for {symbol}")

                success = True

        elif cmd_type == 'SET_FILTER':
            # Set filter value (cần thêm implementation)
            filter_name = params.get('filter')
            value = params.get('value')

            if logger:
                logger(f"⚙️ Command: Set {symbol} {filter_name} = {value}")

            success = True

        # Update command status
        if success:
            cmd['status'] = 'DONE'
            cmd['executed_at'] = datetime.now().isoformat()
            executed = True

    # Lưu lại command queue
    if executed:
        try:
            with open(COMMAND_QUEUE, 'w', encoding='utf-8') as f:
                json.dump(commands, f, indent=2, ensure_ascii=False)
        except:
            pass

    return executed

# Standalone test
if __name__ == "__main__":
    import sys

    # Test state
    test_states = {
        'XAUUSD': {
            'entry_state': 'ARMED_LONG',
            'phase': 'WAITING_PULLBACK',
            'armed_direction': 'LONG',
            'pullback_candle_count': 1,
            'window_active': False
        }
    }

    print("Testing command processor...")

    # Simulate sending a command
    test_cmd = [
        {
            'id': 'test001',
            'type': 'RESET_STATE',
            'params': {'symbol': 'XAUUSD'},
            'priority': 1,
            'created_at': datetime.now().isoformat(),
            'status': 'PENDING'
        }
    ]

    with open(COMMAND_QUEUE, 'w') as f:
        json.dump(test_cmd, f)

    # Process
    result = process_commands(test_states)

    print(f"Commands processed: {result}")
    print(f"XAUUSD state: {test_states['XAUUSD']['entry_state']}")

    # Clean up
    os.remove(COMMAND_QUEUE)
    print("✅ Test complete")