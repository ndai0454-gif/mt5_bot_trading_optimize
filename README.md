# 🥇 MT5 Live Trading Bot: Advanced XAUUSD Engine
*Institutional-grade automated trading system, exclusively optimized for Gold (XAUUSD) on MetaTrader 5.*

**Python 3.8+ | MetaTrader 5 | License: MIT**

![Advanced MT5 Monitor GUI](https://img.shields.io/badge/GUI-Advanced_Monitor-blue) ![Asset](https://img.shields.io/badge/Asset-XAUUSD_Exclusive-gold) ![Risk](https://img.shields.io/badge/Risk-1%25_Hard_Cap-red)

---

## 🎯 What This Bot Does
This bot is a highly specialized, autonomous trading engine dedicated strictly to **XAUUSD (Gold)**. It abandons multi-pair diversification in favor of extreme precision, scaling capabilities, and aggressive risk management on a single high-volatility asset.

### 🔥 Key Features (Latest Updates)
* 🛡️ **Risk-First Management:** Hard-coded **1% maximum account risk** per trade. Lot sizing is dynamically calculated based on the SL distance and real broker tick values.
* 💰 **4-Level TP Splitting:** Profits are secured progressively at 4 levels: **30% / 20% / 30% / 20%**.
* 🔒 **Auto-Breakeven:** Once TP2 (50% of the trade) is reached, Stop Loss is instantly moved to the entry price, securing a Risk-Free trade.
* 🚀 **Scaling Engine (Nhồi lệnh):** Capitalizes on massive trends by adding up to **3 additional scaling orders** (pyramiding) if the initial trade is winning and the H1 candle shows extreme momentum (Body ≥ 75%).
* ⚡ **Ultra-Fast Polling:** Latency reduced from 5 seconds to **500ms** during the Breakout Window to catch Gold's explosive movements instantly.
* 📊 **Spread Safety Lock:** Monitors live broker spread and absolutely refuses to trade if the spread exceeds **80 points ($0.80)** during news spikes.
* 🕒 **24/5 Operations:** Fully unchained time limits; trades all valid configurations during the 24/5 market open.

---

## 🚀 Quick Start

### 1. Installation
```powershell
# Clone repository
git clone https://github.com/ndai0454-gif/mt5_bot_trading_optimize.git
cd mt5_bot_trading_optimize

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration
1. Open your MetaTrader 5 Terminal and log into your **Demo Account**.
2. Ensure **"Allow algorithmic trading"** is enabled in MT5 settings (`Ctrl+O` -> Expert Advisors).
3. Ensure **XAUUSD** is visible in your Market Watch (`Ctrl+U`).

*(Optional: Edit `config/mt5_credentials.json` if you wish to let the bot auto-login)*

### 3. Launch
```powershell
# Start the trading bot
python advanced_mt5_monitor_gui.py
```
*In the GUI, click **Connect**, ensure XAUUSD is selected, and click **Start**.*

---

## 📈 System Architecture & Mechanics

### The 4-Phase State Machine
1. `[SCANNING]` → Scanning for valid EMA Crossovers (Fast/Med/Slow) and RSI alignment.
2. `[ARMED]` → Signal detected. Waiting for 1-3 pullback candles to confirm direction.
3. `[WINDOW_OPEN]` → Polling at **500ms**. Waiting for price to break the confirmation boundary.
4. `[IN_POSITION]` → Trade executed. `GoldPositionManager` takes over for TP splitting and scaling.

### Scaling Engine Logic (Pyramiding)
*Only adds risk when winning.*
* **Trigger:** The base order hits TP2.
* **Validation:** Checks the **H1 Timeframe**. The H1 candle must be aligned with the trade direction, and its body must represent at least **75%** of the entire candle (Wick-to-Wick), proving massive institutional momentum.
* **Execution:** A new sub-order is placed with its own 1% risk SL/TP parameters. Stop Loss of previous orders are trailed.

---

## 📁 Project Structure (Cleaned)

```
mt5_bot_trading_optimize/
├── advanced_mt5_monitor_gui.py    # Main GUI & Execution Engine
├── gold_enhancements.py           # Core logic for TP Splitting & Scaling
├── requirements.txt               # Dependencies
│
├── config/                        # Credentials configuration
├── strategies/                    # Base strategy definitions
├── testing/                       # Sandbox scripts (Order tests, Broker checks)
└── docs/                          # All documentation & architectural notes
    ├── ARCHITECTURE.md            
    ├── trading_strategy.md        # Strategy Specifications
    └── archive/                   # Historical bug fixes & logs
```

---

## 🧪 Testing (Sandbox)
Before running the bot on a live account, use the `testing/` folder to verify your broker's compatibility:

```powershell
# Verify Broker Specs (Tick size, digits, minimum lot)
python testing/check_broker_specs.py

# Test Mathematical Sizing (Ensures 1% risk calculation is perfect)
python testing/test_position_sizing.py

# Test Order Execution (Places a 0.01 micro-lot to verify API rights)
python testing/test_mt5_order.py
```

---

## 🛡️ Risk Disclaimer
**This software is for educational purposes only.**
Trading Gold (XAUUSD) on leverage carries exceptionally high risk. The Scaling Engine is an aggressive tactic that increases margin utilization. 
* **ALWAYS test on a DEMO account first.**
* The developers assume no responsibility for your trading results. Use at your own risk.