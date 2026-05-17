"""
MT5 Data Export Script
Lấy dữ liệu OHLCV từ MT5 và export ra CSV để Claude phân tích
"""
import pandas as pd
import MetaTrader5 as mt5
from datetime import datetime, timedelta
import os

# Cấu hình
SYMBOL = "XAUUSD"          # Symbol cần lấy
TIMEFRAME = mt5.TIMEFRAME_H1  # Khung thời gian H1
BARS = 500                   # Số nến lấy về (tối đa 500000)
OUTPUT_FILE = "xauusd_h1_export.csv"

def connect_mt5():
    """Kết nối tới MT5"""
    if not mt5.initialize():
        print(f"❌ Không thể kết nối MT5. Lỗi: {mt5.last_error()}")
        return False

    account_info = mt5.account_info()
    if account_info is None:
        print("❌ Không lấy được thông tin tài khoản")
        return False

    print(f"✅ Đã kết nối MT5")
    print(f"   Account: {account_info.login}")
    print(f"   Server: {account_info.server}")
    print(f"   Balance: ${account_info.balance:.2f}")
    return True

def get_mt5_timeframe(timeframe_str):
    """Convert timeframe string to MT5 constant"""
    mapping = {
        'M1': mt5.TIMEFRAME_M1,
        'M5': mt5.TIMEFRAME_M5,
        'M15': mt5.TIMEFRAME_M15,
        'M30': mt5.TIMEFRAME_M30,
        'H1': mt5.TIMEFRAME_H1,
        'H4': mt5.TIMEFRAME_H4,
        'D1': mt5.TIMEFRAME_D1,
        'W1': mt5.TIMEFRAME_W1,
        'MN': mt5.TIMEFRAME_MN1,
    }
    return mapping.get(timeframe_str.upper(), mt5.TIMEFRAME_H1)

def export_ohlcv(symbol, timeframe, bars, output_file):
    """Export dữ liệu OHLCV từ MT5"""

    # Lấy dữ liệu
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)

    if rates is None:
        print(f"❌ Không lấy được dữ liệu cho {symbol}")
        return False

    # Chuyển sang DataFrame
    df = pd.DataFrame(rates)

    # Chuyển timestamp sang datetime
    df['time'] = pd.to_datetime(df['time'], unit='s')

    # Thêm các cột tính toán (hữu ích cho phân tích)
    df['candle_color'] = df.apply(lambda x: 'GREEN' if x['close'] > x['open'] else 'RED', axis=1)
    df['body_size'] = abs(df['close'] - df['open'])
    df['upper_shadow'] = df['high'] - df[['close', 'open']].max(axis=1)
    df['lower_shadow'] = df[['close', 'open']].min(axis=1) - df['low']
    df['candle_range'] = df['high'] - df['low']

    # Lưu ra CSV
    df.to_csv(output_file, index=False)

    print(f"\n✅ Đã export {len(df)} nến ra {output_file}")
    print(f"\n📊 Thông tin dữ liệu:")
    print(f"   Symbol: {symbol}")
    print(f"   Timeframe: {timeframe}")
    print(f"   Từ: {df['time'].iloc[0]}")
    print(f"   Đến: {df['time'].iloc[-1]}")
    print(f"\n📋 10 nến cuối cùng:")
    print(df[['time', 'open', 'high', 'low', 'close', 'volume', 'candle_color']].tail(10).to_string())

    return df

def calculate_indicators(df):
    """Tính các indicators cơ bản"""

    # EMA
    for period in [9, 21, 50, 200]:
        df[f'EMA_{period}'] = df['close'].ewm(span=period, adjust=False).mean()

    # RSI (14)
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss
    df['RSI_14'] = 100 - (100 / (1 + rs))

    # ATR (14)
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    tr = high_low.combine(high_close, max).combine(low_close, max)
    df['ATR_14'] = tr.rolling(14).mean()

    # VWAP
    df['VWAP'] = (df['close'] * df['volume']).cumsum() / df['volume'].cumsum()

    return df

def analyze_chart_simple(df):
    """Phân tích chart đơn giản"""

    print("\n" + "="*60)
    print("📈 PHÂN TÍCH CHART ĐƠN GIẢN")
    print("="*60)

    # Lấy dữ liệu mới nhất
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    print(f"\n🔹 Giá hiện tại:")
    print(f"   Close: {last['close']:.5f}")
    print(f"   Open: {last['open']:.5f}")
    print(f"   High: {last['high']:.5f}")
    print(f"   Low: {last['low']:.5f}")
    print(f"   Nến: {last['candle_color']}")

    # Xu hướng (so sánh EMA)
    ema_fast = df['EMA_21'].iloc[-1]
    ema_slow = df['EMA_50'].iloc[-1]

    print(f"\n🔹 Xu hướng (EMA):")
    print(f"   EMA 21: {ema_fast:.5f}")
    print(f"   EMA 50: {ema_slow:.5f}")

    if ema_fast > ema_slow:
        print(f"   → Trend: TĂNG (Bullish)")
    else:
        print(f"   → Trend: GIẢM (Bearish)")

    # RSI
    rsi = df['RSI_14'].iloc[-1]
    print(f"\n🔹 RSI (14): {rsi:.2f}")
    if rsi > 70:
        print(f"   → Overbought (có thể đảo chiều)")
    elif rsi < 30:
        print(f"   → Oversold (có thể bounce)")
    elif rsi > 50:
        print(f"   → Momentum bullish")
    else:
        print(f"   → Momentum bearish")

    # ATR
    atr = df['ATR_14'].iloc[-1]
    print(f"\n🔹 ATR (14): {atr:.5f}")

    # Tìm crossover gần nhất
    print(f"\n🔹 Tìm EMA Crossover gần nhất:")
    for i in range(len(df)-1, len(df)-20, -1):
        if i < 1:
            break
        ema21_now = df['EMA_21'].iloc[i]
        ema21_prev = df['EMA_21'].iloc[i-1]
        ema50_now = df['EMA_50'].iloc[i]
        ema50_prev = df['EMA_50'].iloc[i-1]

        # Bullish crossover
        if ema21_prev <= ema50_prev and ema21_now > ema50_now:
            print(f"   → BULLISH CROSSOVER tại nến {i}: {df['time'].iloc[i]}")
            break
        # Bearish crossover
        elif ema21_prev >= ema50_prev and ema21_now < ema50_now:
            print(f"   → BEARISH CROSSOVER tại nến {i}: {df['time'].iloc[i]}")
            break

    print("\n" + "="*60)

def main():
    print("📤 MT5 Data Export Tool")
    print("="*50)

    # Kết nối MT5
    if not connect_mt5():
        return

    # Export dữ liệu
    df = export_ohlcv(SYMBOL, TIMEFRAME, BARS, OUTPUT_FILE)

    if df is not None:
        # Tính indicators
        df = calculate_indicators(df)

        # Lưu lại với indicators
        df.to_csv(OUTPUT_FILE, index=False)
        print(f"✅ Đã thêm indicators vào {OUTPUT_FILE}")

        # Phân tích đơn giản
        analyze_chart_simple(df)

    # Ngắt kết nối
    mt5.shutdown()
    print("\n👋 Đã ngắt kết nối MT5")

if __name__ == "__main__":
    main()