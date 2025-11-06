import logging
import pandas as pd
import json
import os
from datetime import datetime
from utils.config import get_section

# ───────────────────────────────
# Logger configuration
# ───────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "strategy.log")

logging.basicConfig(
    level=logging.DEBUG,  # 🔍 Enable detailed logs
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ───────────────────────────────
# Strategy class
# ───────────────────────────────
class FiveEMAStrategy:
    def __init__(self, kite_helper=None, trade_manager=None, mode="SELL"):
        self.kite_helper = kite_helper
        self.trade_manager = trade_manager
        self.mode = mode.upper()
        self.active_alert = None
        self.entry_triggered = False
        self.entry_details = None

        # Load configuration section for this mode
        self.cfg = get_section(self.mode)
        self.underlying = self.cfg["underlying"]
        self.timeframe = self.cfg["timeframe"]
        self.stoploss_points = self.cfg["stoploss_points"]
        self.lots = self.cfg["lots"]
        self.paper_mode = self.cfg["paper_mode"]
        self.gap_buffer = self.cfg["gap_between_candle_and_ema"]
        self.entry_offset_points = self.cfg["entry_offset_points"]

        logger.info(
            f"FiveEMAStrategy initialized | mode={self.mode}, timeframe={self.timeframe}, "
            f"paper_mode={self.paper_mode}, gap_buffer={self.gap_buffer}, entry_offset={self.entry_offset_points}"
        )

    # ───────────────────────────────
    # EMA Calculation
    # ───────────────────────────────
    def compute_ema(self, df):
        df["EMA_5"] = df["close"].ewm(span=5, adjust=False).mean()
        return df

    # ───────────────────────────────
    # Identify Alert Candle
    # ───────────────────────────────
    def identify_alert_candle(self, df):
        df = self.compute_ema(df.copy())
        if len(df) < 5:
            return None

        latest = df.iloc[-2]  # last completed candle
        ema = latest["EMA_5"]
        close, high, low = latest["close"], latest["high"], latest["low"]
        time = latest["datetime"]

        # 🔍 Diagnostic log for every candle
        logger.debug(
            f"🧩 {time.strftime('%I:%M %p')} | Close={close:.2f}, Low={low:.2f}, EMA={ema:.2f}, Gap={(low - ema):.2f}"
        )

        # Only create alert if none active yet
        can_refresh_alert = self.active_alert is None

        # SELL Mode (Bearish)
        if self.mode == "SELL" and can_refresh_alert:
            if close > ema and low > ema + self.gap_buffer:
                self.active_alert = {"type": "BEARISH", "price": close, "time": time, "low": low, "high": high}
                logger.info(f"📢 Alert Candle (BEARISH) | {time.strftime('%I:%M %p')} | Close={close:.2f}, EMA={ema:.2f}")

        # BUY Mode (Bullish)
        elif self.mode == "BUY" and can_refresh_alert:
            if close < ema and high < ema - self.gap_buffer:
                self.active_alert = {"type": "BULLISH", "price": close, "time": time, "low": low, "high": high}
                logger.info(f"📢 Alert Candle (BULLISH) | {time.strftime('%I:%M %p')} | Close={close:.2f}, EMA={ema:.2f}")

        return self.active_alert

    # ───────────────────────────────
    # Check for Entry
    # ───────────────────────────────
    def check_entry(self, df):
        if not self.active_alert or len(df) < 2:
            return None

        latest = df.iloc[-1]

        # SELL CALL (Bearish)
        if self.mode == "SELL" and latest["low"] < self.active_alert["low"]:
            raw_low = float(latest["low"])
            entry_price = raw_low + float(self.entry_offset_points)
            sl = float(self.active_alert["high"])
            rr_unit = sl - entry_price
            entry = {
                "signal": "SELL_CALL",
                "entry_price": round(entry_price, 2),
                "entry_time": latest["datetime"],
                "stop_loss": round(sl, 2),
                # Targets at 1R, 2R, 3R below entry
                "targets": [round(entry_price - rr_unit * i, 2) for i in range(1, 4)],
            }

            logger.info(
                f"🎯 Entry Triggered (BEARISH) | {latest['datetime'].strftime('%I:%M %p')} | "
                f"Entry={entry['entry_price']:.2f}, SL={entry['stop_loss']:.2f}"
            )

            self._reset_state()
            return entry

        # BUY PUT (Bullish)
        elif self.mode == "BUY" and latest["high"] > self.active_alert["high"]:
            raw_high = float(latest["high"])
            entry_price = raw_high - float(self.entry_offset_points)
            sl = float(self.active_alert["low"])
            rr_unit = entry_price - sl
            entry = {
                "signal": "SELL_PUT",
                "entry_price": round(entry_price, 2),
                "entry_time": latest["datetime"],
                "stop_loss": round(sl, 2),
                # Targets at 1R, 2R, 3R above entry
                "targets": [round(entry_price + rr_unit * i, 2) for i in range(1, 4)],
            }

            logger.info(
                f"🎯 Entry Triggered (BULLISH) | {latest['datetime'].strftime('%I:%M %p')} | "
                f"Entry={entry['entry_price']:.2f}, SL={entry['stop_loss']:.2f}"
            )

            self._reset_state()
            return entry

        return None

    # ───────────────────────────────
    # Reset State
    # ───────────────────────────────
    def _reset_state(self):
        self.entry_triggered = False
        self.entry_details = None
        self.active_alert = None
        logger.debug("🔄 Strategy state reset — ready for next signal.")

