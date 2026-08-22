"""
HABESHA SWING - Configuration
Validated 4h long-only momentum system (2026-08-22 stress test).
"""
import os
from dataclasses import dataclass

def _bool(v, default):
    if v is None: return default
    return str(v).strip().lower() in ('true','yes','1','t','y')

@dataclass
class SwingConfig:
    # Symbols: BTC + ETH validated as positive in ALL out-of-sample folds
    SYMBOLS: str = os.getenv("SWING_SYMBOLS", "BTCUSD,ETHUSD")
    PAPER_TRADING: bool = _bool(os.getenv("PAPER_TRADING"), True)

    # --- VALIDATED PARAMS (stress-tested, do not change without re-validating) ---
    LOOKBACK_BARS: int = int(os.getenv("SWING_LOOKBACK", "12"))   # 12 x 4h = 2 days
    MOMENTUM_THRESHOLD: float = float(os.getenv("SWING_MOM_TH", "0.05"))  # +5% over lookback
    STOP_MULT: float = float(os.getenv("SWING_STOP", "4.0"))      # 4x ATR stop
    TAKE_MULT: float = float(os.getenv("SWING_TAKE", "5.0"))      # 5x ATR target
    TRAIL_ACTIVATE_ATR: float = float(os.getenv("SWING_TRAIL", "1.5"))
    TRAIL_STOP_ATR: float = float(os.getenv("SWING_TRAIL_STOP", "0.8"))
    TREND_SMA: int = int(os.getenv("SWING_TREND", "20"))          # 20x4h = 3.3-day trend
    RSI_MAX: float = float(os.getenv("SWING_RSI_MAX", "80"))      # avoid overbought tops

    # --- RISK ---
    MAX_POS_SIZE_PCT: float = float(os.getenv("SWING_POS_PCT", "0.30"))  # 30% per position
    MAX_OPEN_POSITIONS: int = int(os.getenv("SWING_MAX_OPEN", "3"))
    MAX_DAILY_LOSS_PCT: float = float(os.getenv("SWING_DAILY_LOSS", "0.04"))
    CASH_BUFFER_PCT: float = float(os.getenv("SWING_CASH_BUFFER", "0.90"))

    # Tag for shared-account P&L attribution
    TRADE_TAG: str = "SWING"

    # DB / paths
    DB_PATH: str = os.getenv("SWING_DB", "/home/ubuntu/habesha-swing/swing.db")
    LOG_DIR: str = os.getenv("SWING_LOG_DIR", "/home/ubuntu/habesha-swing/logs")
    DATA_DIR_1H: str = "/home/ubuntu/titanium/history_data_1h"
    DATA_DIR_4H: str = "/home/ubuntu/titanium/history_data_4h"

CONFIG = SwingConfig()
