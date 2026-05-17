"""
Claude Trading Assistant
=========================
Automated trading assistant that:
1. Monitors bot state
2. Analyzes market conditions
3. Makes auto-decisions
4. Executes commands

Usage:
    python claude_trader.py --run           # Run continuous
    python claude_trader.py --analyze       # Analyze once
    python claude_trader.py --report        # Generate report
"""
import json
import os
import sys
import time
import MetaTrader5 as mt5
from datetime import datetime
import pandas as pd

# Fix Windows encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

STATE_FILE = "mt5_strategy_state.json"
COMMAND_QUEUE = "bot_commands.json"
LOG_FILE = "claude_trader.log"

class ClaudeTrader:
    def __init__(self):
        self.mt5_connected = False

    def connect_mt5(self):
        """Connect to MT5"""
        if not mt5.initialize():
            print("Cannot connect to MT5")
            return False

        account = mt5.account_info()
        if account is None:
            print("Cannot get account info")
            return False

        self.mt5_connected = True
        print(f"Connected: {account.login} ({account.server})")
        return True

    def get_market_data(self, symbol, bars=50):
        """Get OHLCV data for analysis"""
        if not self.mt5_connected:
            return None

        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, bars)
        if rates is None:
            return None

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')

        # Calculate indicators
        df['EMA21'] = df['close'].ewm(span=21).mean()
        df['EMA50'] = df['close'].ewm(span=50).mean()
        df['EMA200'] = df['close'].ewm(span=200).mean()

        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + gain / loss))

        # ATR
        df['ATR'] = (df['high'] - df['low']).rolling(14).mean()

        return df

    def analyze_symbol(self, symbol):
        """Analyze a single symbol"""
        df = self.get_market_data(symbol)
        if df is None:
            return None

        last = df.iloc[-1]

        # Trend
        if last['EMA21'] > last['EMA50']:
            trend = "UP"
        elif last['EMA21'] < last['EMA50']:
            trend = "DOWN"
        else:
            trend = "SIDEWAYS"

        # RSI
        rsi = last['RSI']
        if rsi > 70:
            rsi_zone = "OVERBOUGHT"
        elif rsi < 30:
            rsi_zone = "OVERSOLD"
        else:
            rsi_zone = "NEUTRAL"

        return {
            'symbol': symbol,
            'price': last['close'],
            'trend': trend,
            'ema21': last['EMA21'],
            'ema50': last['EMA50'],
            'rsi': rsi,
            'rsi_zone': rsi_zone,
            'atr': last['ATR'],
            'candle': 'GREEN' if last['close'] > last['open'] else 'RED'
        }

    def read_state(self):
        """Read bot state"""
        if not os.path.exists(STATE_FILE):
            return {}

        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}

    def send_command(self, cmd_type, symbol, params=None):
        """Send command to bot"""
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
            with open(COMMAND_QUEUE, 'w') as f:
                json.dump(commands, f, indent=2)
            return True
        except:
            return False

    def make_decision(self):
        """Analyze and make trading decisions"""
        state = self.read_state()

        if not state:
            print("No state data")
            return

        decisions = []

        for symbol, data in state.items():
            if not isinstance(data, dict):
                continue

            # Analyze market
            market = self.analyze_symbol(symbol)
            if not market:
                continue

            bot_state = data.get('entry_state', 'SCANNING')
            direction = data.get('armed_direction')
            pullback = data.get('pullback_candle_count', 0)

            # Decision logic
            if bot_state == 'SCANNING':
                # Check if good entry opportunity
                if market['trend'] == 'UP' and market['rsi'] < 70:
                    decisions.append({
                        'symbol': symbol,
                        'action': 'WAIT',
                        'reason': 'Market bullish, waiting for crossover'
                    })

                elif market['trend'] == 'DOWN' and market['rsi'] > 30:
                    decisions.append({
                        'symbol': symbol,
                        'action': 'WAIT',
                        'reason': 'Market bearish'
                    })

            elif 'ARMED' in bot_state:
                # Check if should skip pullback
                if pullback >= 1:  # Already have 1 pullback
                    # Good momentum, may skip
                    if market['trend'] == 'UP' and market['rsi'] < 65:
                        decisions.append({
                            'symbol': symbol,
                            'action': 'SKIP_PULLBACK',
                            'reason': f'Strong momentum, RSI OK ({market["rsi"]:.1f})'
                        })

            elif bot_state == 'WINDOW_OPEN':
                # Check if should extend or cancel
                current_bar = data.get('current_bar', 0)
                window_exp = data.get('window_expiry_bar', 50)
                remaining = window_exp - current_bar

                # If market moved against direction
                if direction == 'LONG' and market['trend'] == 'DOWN':
                    decisions.append({
                        'symbol': symbol,
                        'action': 'CANCEL',
                        'reason': 'Trend reversed to DOWN'
                    })
                elif direction == 'SHORT' and market['trend'] == 'UP':
                    decisions.append({
                        'symbol': symbol,
                        'action': 'CANCEL',
                        'reason': 'Trend reversed to UP'
                    })
                elif remaining <= 3:
                    decisions.append({
                        'symbol': symbol,
                        'action': 'EXTEND',
                        'params': {'bars': 10},
                        'reason': f'Window expiring soon ({remaining} bars)'
                    })

        return decisions, market

    def run_cycle(self):
        """Run one analysis cycle"""
        print("\n" + "="*60)
        print(f"CLAUDE TRADING CYCLE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)

        # Get market analysis
        print("\n📊 Market Analysis:")

        state = self.read_state()
        for symbol in state.keys():
            market = self.analyze_symbol(symbol)
            if market:
                print(f"\n  {symbol}:")
                print(f"    Price: {market['price']:.5f}")
                print(f"    Trend: {market['trend']} | RSI: {market['rsi']:.1f} ({market['rsi_zone']})")
                print(f"    EMA21: {market['ema21']:.5f} | EMA50: {market['ema50']:.5f}")
                print(f"    Candle: {market['candle']} | ATR: {market['atr']:.5f}")

        # Get bot state
        print("\n🤖 Bot State:")
        for symbol, data in state.items():
            if isinstance(data, dict):
                bot_state = data.get('entry_state', 'UNKNOWN')
                direction = data.get('armed_direction', '')
                pullback = data.get('pullback_candle_count', 0)

                print(f"  {symbol}: {bot_state}", end="")
                if direction:
                    print(f" ({direction})", end="")
                if pullback > 0:
                    print(f" | Pullback: {pullback}/2", end="")
                print()

        # Make decisions
        decisions, last_market = self.make_decision()

        print("\n🎯 Decisions:")
        if decisions:
            for d in decisions:
                print(f"  {d['symbol']}: {d['action']} - {d['reason']}")

                # Execute
                if d['action'] == 'SKIP_PULLBACK':
                    self.send_command('SKIP_PULLBACK', d['symbol'])
                elif d['action'] == 'CANCEL':
                    self.send_command('CANCEL_ENTRY', d['symbol'])
                elif d['action'] == 'EXTEND':
                    self.send_command('EXTEND_WINDOW', d['symbol'], d.get('params'))
        else:
            print("  No actions needed")

        print("="*60)

def main():
    trader = ClaudeTrader()

    if '--analyze' in sys.argv or '--run' in sys.argv:
        if not trader.connect_mt5():
            print("Failed to connect to MT5")
            return

    if '--analyze' in sys.argv:
        # Single analysis
        trader.run_cycle()

    elif '--report' in sys.argv:
        # Generate report
        state = trader.read_state()

        print("\n" + "="*60)
        print("CLAUDE TRADING REPORT")
        print("="*60)

        for symbol, data in state.items():
            if not isinstance(data, dict):
                continue

            print(f"\n{symbol}:")
            print(f"  Bot State: {data.get('entry_state', 'UNKNOWN')}")
            print(f"  Direction: {data.get('armed_direction', 'N/A')}")
            print(f"  Pullback: {data.get('pullback_candle_count', 0)}/2")
            print(f"  Window: {data.get('window_active', False)}")
            print(f"  Last Update: {data.get('last_update', 'N/A')}")

            # Market analysis
            market = trader.analyze_symbol(symbol)
            if market:
                print(f"  Market Trend: {market['trend']}")
                print(f"  RSI: {market['rsi']:.1f} ({market['rsi_zone']})")

    elif '--run' in sys.argv:
        # Continuous run
        interval = 30
        for i, arg in enumerate(sys.argv):
            if arg == '--interval' and i+1 < len(sys.argv):
                interval = int(sys.argv[i+1])

        print(f"Starting Claude Trader (interval: {interval}s)")

        try:
            while True:
                trader.run_cycle()
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\nStopped")

    else:
        print("""
Claude Trading Assistant
========================

Usage: python claude_trader.py [command]

Commands:
  --analyze     Run single analysis cycle
  --run         Run continuous (default 30s interval)
  --report      Generate status report

Options:
  --interval=N  Set interval in seconds (for --run)

Examples:
  python claude_trader.py --analyze
  python claude_trader.py --run
  python claude_trader.py --run --interval=60
  python claude_trader.py --report
        """)

if __name__ == "__main__":
    main()