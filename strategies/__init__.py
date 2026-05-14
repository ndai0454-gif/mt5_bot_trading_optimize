"""
MT5 Live Trading Bot - Sunrise Strategies
==========================================

This module contains independent copies of the Sunrise trading strategies
for use with the MT5 live trading system.

These strategies are completely independent from the original quant_bot_project
development environment and can be used for live trading without external dependencies.

Available Strategies:
- sunrise_ogle_eurusd: EUR/USD trading strategy
- sunrise_ogle_gbpusd: GBP/USD trading strategy  
- sunrise_ogle_xauusd: Gold (XAU/USD) trading strategy
- sunrise_ogle_audusd: AUD/USD trading strategy
- sunrise_ogle_xagusd: Silver (XAG/USD) trading strategy
- sunrise_ogle_usdchf: USD/CHF trading strategy
"""

# Import all strategies for easier access
try:
    from .sunrise_ogle_eurusd import SunriseOgle as SunriseOgleEURUSD  # type: ignore
except ImportError:
    SunriseOgleEURUSD = None  # type: ignore

try:
    from .sunrise_ogle_gbpusd import SunriseOgle as SunriseOgleGBPUSD  # type: ignore
except ImportError:
    SunriseOgleGBPUSD = None  # type: ignore

try:
    from .sunrise_ogle_xauusd import SunriseOgle as SunriseOgleXAUUSD  # type: ignore
except ImportError:
    SunriseOgleXAUUSD = None  # type: ignore

try:
    from .sunrise_ogle_audusd import SunriseOgle as SunriseOgleAUDUSD  # type: ignore
except ImportError:
    SunriseOgleAUDUSD = None  # type: ignore

try:
    from .sunrise_ogle_xagusd import SunriseOgle as SunriseOgleXAGUSD  # type: ignore
except ImportError:
    SunriseOgleXAGUSD = None  # type: ignore

try:
    from .sunrise_ogle_usdchf import SunriseOgle as SunriseOgleUSDCHF  # type: ignore
except ImportError:
    SunriseOgleUSDCHF = None  # type: ignore

try:
    from .sunrise_ogle_eurjpy import SunriseOgle as SunriseOgleEURJPY  # type: ignore
except ImportError:
    SunriseOgleEURJPY = None  # type: ignore

try:
    from .sunrise_ogle_usdjpy import SunriseOgleUSDJPY  # type: ignore
except ImportError:
    SunriseOgleUSDJPY = None  # type: ignore

# Export all available strategies
__all__ = [
    'SunriseOgleEURUSD',
    'SunriseOgleGBPUSD', 
    'SunriseOgleXAUUSD',
    'SunriseOgleAUDUSD',
    'SunriseOgleXAGUSD',
    'SunriseOgleUSDCHF',
    'SunriseOgleEURJPY',
    'SunriseOgleUSDJPY',
]

# Strategy mapping for easy access
STRATEGY_CLASSES = {
    'EURUSD': SunriseOgleEURUSD,
    'GBPUSD': SunriseOgleGBPUSD,
    'XAUUSD': SunriseOgleXAUUSD,
    'AUDUSD': SunriseOgleAUDUSD,
    'XAGUSD': SunriseOgleXAGUSD,
    'USDCHF': SunriseOgleUSDCHF,
    'EURJPY': SunriseOgleEURJPY,
    'USDJPY': SunriseOgleUSDJPY,
}