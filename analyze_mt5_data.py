"""
MT5 Data Analyzer
Đọc file CSV export từ MT5 và phân tích chi tiết cho Claude
"""
import pandas as pd
import sys
import os

def load_csv(file_path):
    """Load dữ liệu từ CSV"""
    if not os.path.exists(file_path):
        print(f"❌ File không tồn tại: {file_path}")
        return None

    df = pd.read_csv(file_path)

    # Parse time column
    if 'time' in df.columns:
        df['time'] = pd.to_datetime(df['time'])

    return df

def add_indicators(df):
    """Thêm indicators vào dataframe"""
    # EMA các chu kỳ
    for period in [9, 21, 50, 100, 200]:
        df[f'EMA_{period}'] = df['close'].ewm(span=period, adjust=False).mean()

    # SMA
    for period in [20, 50, 200]:
        df[f'SMA_{period}'] = df['close'].rolling(window=period).mean()

    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # MACD
    df['EMA_12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['EMA_26'] = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = df['EMA_12'] - df['EMA_26']
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']

    # ATR
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    tr = high_low.combine(high_close, max).combine(low_close, max)
    df['ATR'] = tr.rolling(14).mean()

    # Bollinger Bands
    df['BB_Middle'] = df['close'].rolling(20).mean()
    df['BB_Std'] = df['close'].rolling(20).std()
    df['BB_Upper'] = df['BB_Middle'] + (df['BB_Std'] * 2)
    df['BB_Lower'] = df['BB_Middle'] - (df['BB_Std'] * 2)

    # Candle info
    df['candle_color'] = df.apply(lambda x: 'GREEN' if x['close'] > x['open'] else 'RED', axis=1)
    df['body_size'] = abs(df['close'] - df['open'])
    df['candle_range'] = df['high'] - df['low']
    df['upper_shadow'] = df['high'] - df[['close', 'open']].max(axis=1)
    df['lower_shadow'] = df[['close', 'open']].min(axis=1) - df['low']

    return df

def analyze_trend(df):
    """Phân xu hướng"""
    print("\n" + "="*60)
    print("📈 XU HƯỚNG (TREND ANALYSIS)")
    print("="*60)

    # Lấy dữ liệu mới nhất
    last = df.iloc[-1]

    # EMA Analysis
    ema21 = last.get('EMA_21', None)
    ema50 = last.get('EMA_50', None)
    ema100 = last.get('EMA_100', None)
    ema200 = last.get('EMA_200', None)

    if ema21 and ema50:
        print(f"\nEMA Cross Status:")
        print(f"  EMA 21: {ema21:.5f}")
        print(f"  EMA 50: {ema50:.5f}")

        if ema21 > ema50:
            print(f"  → EMA 21 > 50: UPTREND (Bullish)")
        else:
            print(f"  → EMA 21 < 50: DOWNTREND (Bearish)")

    # Kiểm tra EMA 200 (key level)
    if ema200:
        print(f"\nEMA 200 (Long-term): {ema200:.5f}")
        if last['close'] > ema200:
            print(f"  → Price > EMA200: ABOVE long-term trend")
        else:
            print(f"  → Price < EMA200: BELOW long-term trend")

    # Price position
    print(f"\nPrice Position:")
    print(f"  Close: {last['close']:.5f}")
    if ema50:
        diff_pips = (last['close'] - ema50) * 10000
        print(f"  vs EMA50: {diff_pips:+.1f} pips")

def analyze_momentum(df):
    """Phân tích momentum"""
    print("\n" + "="*60)
    print("📊 MOMENTUM ANALYSIS")
    print("="*60)

    last = df.iloc[-1]

    # RSI
    rsi = last.get('RSI', None)
    if rsi:
        print(f"\nRSI (14): {rsi:.2f}")
        if rsi > 70:
            print(f"  → Overbought (>70): Có thể đảo chiều giảm")
        elif rsi < 30:
            print(f"  → Oversold (<30): Có thể bounce tăng")
        elif rsi > 50:
            print(f"  → Bullish Zone (50-70): Momentum tăng")
        else:
            print(f"  → Bearish Zone (30-50): Momentum giảm")

    # MACD
    macd = last.get('MACD', None)
    signal = last.get('MACD_Signal', None)
    if macd and signal:
        print(f"\nMACD:")
        print(f"  MACD Line: {macd:.5f}")
        print(f"  Signal Line: {signal:.5f}")
        if macd > signal:
            print(f"  → MACD > Signal: BULLISH momentum")
        else:
            print(f"  → MACD < Signal: BEARISH momentum")

        # MACD Histogram
        hist = last.get('MACD_Hist', None)
        if hist:
            print(f"  Histogram: {hist:.5f} ({'Growing' if hist > 0 else 'Falling'})")

def analyze_volatility(df):
    """Phân tích biến động"""
    print("\n" + "="*60)
    print("🌊 VOLATILITY (BIẾN ĐỘNG)")
    print("="*60)

    last = df.iloc[-1]

    # ATR
    atr = last.get('ATR', None)
    if atr:
        print(f"\nATR (14): {atr:.5f}")
        # So với giá
        atr_pct = (atr / last['close']) * 100
        print(f"  → ATR %: {atr_pct:.3f}%")

        # So sánh với ATR trung bình 20 nến
        avg_atr = df['ATR'].tail(20).mean()
        if atr > avg_atr:
            print(f"  → ATR cao hơn trung bình 20 nến: BIẾN ĐỘNG TĂNG")
        else:
            print(f"  → ATR thấp hơn trung bình 20 nến: BIẾN ĐỘNG GIẢM")

    # Bollinger Bands
    bb_upper = last.get('BB_Upper', None)
    bb_lower = last.get('BB_Lower', None)
    bb_middle = last.get('BB_Middle', None)

    if bb_upper and bb_lower:
        print(f"\nBollinger Bands:")
        print(f"  Upper: {bb_upper:.5f}")
        print(f"  Middle: {bb_middle:.5f}")
        print(f"  Lower: {bb_lower:.5f}")

        # Price position in BB
        if last['close'] > bb_upper:
            print(f"  → Price Above Upper BB: QUÁ MUA")
        elif last['close'] < bb_lower:
            print(f"  → Price Below Lower BB: QUÁ BÁN")
        else:
            # Tính vị trí %
            position = (last['close'] - bb_lower) / (bb_upper - bb_lower) * 100
            print(f"  → Price trong BB: {position:.1f}%")

def find_crossover(df):
    """Tìm các crossover gần nhất"""
    print("\n" + "="*60)
    print("🔄 EMA CROSSOVERS (10 nến gần nhất)")
    print("="*60)

    df_cros = df.tail(11).copy()

    for i in range(len(df_cros)-1, 0, -1):
        idx = df.index[len(df) - 11 + i]
        prev_idx = idx - 1

        if 'EMA_21' not in df.columns or 'EMA_50' not in df.columns:
            break

        ema21_now = df.loc[idx, 'EMA_21']
        ema21_prev = df.loc[prev_idx, 'EMA_21']
        ema50_now = df.loc[idx, 'EMA_50']
        ema50_prev = df.loc[prev_idx, 'EMA_50']

        # Bullish crossover
        if ema21_prev <= ema50_prev and ema21_now > ema50_now:
            print(f"\n🟢 BULLISH CROSSOVER:")
            print(f"   Thời gian: {df.loc[idx, 'time']}")
            print(f"   Close: {df.loc[idx, 'close']:.5f}")
            break

        # Bearish crossover
        elif ema21_prev >= ema50_prev and ema21_now < ema50_now:
            print(f"\n🔴 BEARISH CROSSOVER:")
            print(f"   Thời gian: {df.loc[idx, 'time']}")
            print(f"   Close: {df.loc[idx, 'close']:.5f}")
            break

    # Nếu không tìm thấy trong 10 nến
    print(f"\n(Trong 10 nến gần nhất không có crossover)")

def analyze_candles(df):
    """Phân tích nến"""
    print("\n" + "="*60)
    print("🕯️ CANDLE PATTERN ANALYSIS")
    print("="*60)

    # 5 nến gần nhất
    print("\n5 nến gần nhất:")
    print("-" * 80)

    for i in range(-1, -6, -1):
        row = df.iloc[i]
        time = row['time']
        o = row['open']
        h = row['high']
        l = row['low']
        c = row['close']
        color = row.get('candle_color', 'N/A')

        body_size = abs(c - o)
        total_range = h - l

        print(f"{time}")
        print(f"   O:{o:.5f} H:{h:.5f} L:{l:.5f} C:{c:.5f} | {color}")
        print(f"   Body: {body_size:.5f} ({body_size/total_range*100:.0f}% of range)")

    # Thống kê
    recent = df.tail(20)
    green_count = (recent['candle_color'] == 'GREEN').sum()
    red_count = (recent['candle_color'] == 'RED').sum()

    print(f"\n20 nến gần nhất:")
    print(f"  Green: {green_count} ({green_count/20*100:.0f}%)")
    print(f"  Red: {red_count} ({red_count/20*100:.0f}%)")

def summarize_state_machine(df, config=None):
    """Tóm tắt trạng thái state machine"""
    print("\n" + "="*60)
    print("🎯 BOT STATE MACHINE STATUS")
    print("="*60)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Giả định các tham số (có thể thay đổi theo config)
    ema_fast = 21
    ema_medium = 50
    ema_slow = 100

    # Lấy EMA
    ema_f = last.get('EMA_21', None)
    ema_m = last.get('EMA_50', None)
    ema_s = last.get('EMA_100', None)
    ema_confirm = last.get('EMA_9', last['close'])

    if not all([ema_f, ema_m, ema_s]):
        print("❌ Không đủ dữ liệu EMA để xác định state")
        return

    # Kiểm tra crossover gần nhất
    bullish_cross = False
    bearish_cross = False

    for i in range(len(df)-1, max(0, len(df)-20), -1):
        prev_row = df.iloc[i-1]
        curr_row = df.iloc[i]

        # EMA 21 vs EMA 50
        if (prev_row['EMA_21'] <= prev_row['EMA_50']) and (curr_row['EMA_21'] > curr_row['EMA_50']):
            print(f"🟢 Bullish EMA21/50 crossover: {curr_row['time']}")
            break
        elif (prev_row['EMA_21'] >= prev_row['EMA_50']) and (curr_row['EMA_21'] < curr_row['EMA_50']):
            print(f"🔴 Bearish EMA21/50 crossover: {curr_row['time']}")
            break

    # Xác định state giả định
    print(f"\n📊 Current Status:")

    # Check trend
    if ema_f > ema_m:
        print(f"   → Trend: UP (EMA21 > EMA50)")
        trend = "BULLISH"
    else:
        print(f"   → Trend: DOWN (EMA21 < EMA50)")
        trend = "BEARISH"

    # Check price position
    if last['close'] > ema_f:
        print(f"   → Price: Above EMA21")
    else:
        print(f"   → Price: Below EMA21")

    # RSI
    rsi = last.get('RSI', 50)
    print(f"   → RSI: {rsi:.1f}")

    # Giả định state
    print(f"\n🎯 Giả định State (dựa trên config mặc định):")

    # Bullish scenario
    if trend == "BULLISH" and rsi >= 50:
        # Check if price above all EMAs
        if last['close'] > ema_f and last['close'] > ema_m:
            print(f"   → ARMED_LONG (Có thể chuyển sang PULLBACK/WINDOW)")
        else:
            print(f"   → SCANNING (Đang chờ xác nhận)")

    print(f"\n💡 Để bot vào lệnh BUY, cần:")
    print(f"   1. Giá đóng nến trên EMA 21/50/100")
    print(f"   2. Xuất hiện 2 nến đỏ (pullback)")
    print(f"   3. Giá phá đỉnh nến pullback")
    print(f"   4. Pass tất cả filters (RSI, ATR, Angle, Time)")

def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_mt5_data.py <file.csv>")
        print("Example: python analyze_mt5_data.py xauusd_h1.csv")
        sys.exit(1)

    file_path = sys.argv[1]

    print(f"📊 Đang đọc file: {file_path}")
    df = load_csv(file_path)

    if df is None:
        sys.exit(1)

    print(f"✅ Loaded {len(df)} candles")
    print(f"   Từ: {df['time'].iloc[0]}")
    print(f"   Đến: {df['time'].iloc[-1]}")

    # Thêm indicators
    df = add_indicators(df)

    # Phân tích
    analyze_trend(df)
    analyze_momentum(df)
    analyze_volatility(df)
    find_crossover(df)
    analyze_candles(df)
    summarize_state_machine(df)

if __name__ == "__main__":
    main()