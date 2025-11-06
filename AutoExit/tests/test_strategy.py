"""
Dual-Mode, Multi-Timeframe Test Harness for Five EMA Strategy
BEARISH (5-minute) + BULLISH (15-minute)
Chronological Alert Sequence + Original Telegram Format + Correct EMA Warm-up
"""

import sys
import os
import json
import logging
import requests
from typing import Dict, List, Optional
import pandas as pd
from datetime import datetime, timedelta
from kiteconnect import KiteConnect
from kiteconnect.exceptions import KiteException

# Constants
REQUIRED_ENV_VARS = [
    "KITE_API_KEY",
    "KITE_ACCESS_TOKEN",
    "TEST_FROM_DATE",
    "TEST_TO_DATE"
]
OPTIONAL_ENV_VARS = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID"
]
DATE_FORMAT = "%Y-%m-%d"

# ───────────────────────────────
# Ensure project root is importable
# ───────────────────────────────
current_file = os.path.abspath(__file__)
project_root = os.path.abspath(os.path.join(os.path.dirname(current_file), ".."))  # one level up from /tests/
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# ───────────────────────────────
# Imports from internal modules
# ───────────────────────────────
from utils.notifier import send_telegram, format_trade_message, log_trade
from strategies.five_ema_strategy import FiveEMAStrategy
from utils.kite_helper import KiteHelper
from utils.trade_manager import TradeManager
from utils.config import get_kite_credentials, get_env_var, get_config

# ───────────────────────────────
# Logging setup
# ───────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("test_strategy")

# ───────────────────────────────
# Load env + config
# ───────────────────────────────
def validate_environment() -> Dict[str, str]:
    """Validate and load environment variables using centralized helpers."""
    creds = get_kite_credentials()
    env_vars: Dict[str, Optional[str]] = {}
    missing_vars = []

    for var in REQUIRED_ENV_VARS:
        if var in ("KITE_API_KEY", "KITE_ACCESS_TOKEN"):
            value = creds.get(var)
        else:
            value = get_env_var(var)

        if not value:
            missing_vars.append(var)
        env_vars[var] = value

    if missing_vars:
        raise EnvironmentError(f"❌ Missing required environment variables: {', '.join(missing_vars)}")

    # Optional variables
    for var in OPTIONAL_ENV_VARS:
        env_vars[var] = get_env_var(var)

    if not all([env_vars.get("TELEGRAM_BOT_TOKEN"), env_vars.get("TELEGRAM_CHAT_ID")]):
        logger.warning("⚠️ Telegram credentials missing in .env — alerts disabled.")

    # Cast values to plain dict[str,str] for callers
    return {k: (v if v is not None else "") for k, v in env_vars.items()}

# Load environment variables
env_vars = validate_environment()
api_key = env_vars["KITE_API_KEY"]
access_token = env_vars["KITE_ACCESS_TOKEN"]
bot_token = env_vars["TELEGRAM_BOT_TOKEN"]
chat_id = env_vars["TELEGRAM_CHAT_ID"]
test_from_env = env_vars["TEST_FROM_DATE"]
test_to_env = env_vars["TEST_TO_DATE"]

def validate_config(config: dict) -> dict:
    """
    Validate configuration structure and required fields.
    Returns validated config if successful, raises ValueError if invalid.
    """
    required_sections = ["SYSTEM", "SELL", "BUY"]
    required_fields = {
        "SYSTEM": ["instrument_tokens", "warmup_days"],
        "SELL": ["timeframe", "underlying", "gap_between_candle_and_ema", "stoploss_points", 
                "max_stoploss_per_day", "lots", "otm_strike_distance", "paper_mode"],
        "BUY": ["timeframe", "underlying", "gap_between_candle_and_ema", "stoploss_points", 
               "max_stoploss_per_day", "lots", "otm_strike_distance", "paper_mode"]
    }
    
    # Check required sections
    missing_sections = [section for section in required_sections if section not in config]
    if missing_sections:
        raise ValueError(f"❌ Missing required sections in config: {', '.join(missing_sections)}")
    
    # Check required fields in each section
    for section, fields in required_fields.items():
        missing_fields = [field for field in fields if field not in config[section]]
        if missing_fields:
            raise ValueError(f"❌ Missing required fields in {section}: {', '.join(missing_fields)}")
    
    # Validate specific field values
    if config["SYSTEM"]["warmup_days"] < 1:
        raise ValueError("❌ warmup_days must be at least 1")
    
    # Validate matching underlying assets
    if config["SELL"]["underlying"] != config["BUY"]["underlying"]:
        raise ValueError("❌ SELL and BUY configurations must use the same underlying")
    
    # Validate instrument tokens
    if config["SELL"]["underlying"] not in config["SYSTEM"]["instrument_tokens"]:
        raise ValueError(f"❌ No instrument token found for {config['SELL']['underlying']}")
    
    return config

def load_config() -> dict:
    """Return validated configuration using centralized config helper."""
    cfg_all = get_config()
    return validate_config(cfg_all)

# Load and validate configuration
cfg_all = load_config()
cfg_sell = cfg_all["SELL"]
cfg_buy = cfg_all["BUY"]

underlying = cfg_sell["underlying"]
timeframe_sell = cfg_sell["timeframe"]
timeframe_buy = cfg_buy["timeframe"]

logger.info("✅ Configuration loaded and validated successfully")

# ───────────────────────────────
# Kite setup
# ───────────────────────────────
kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)
kite_helper = KiteHelper(api_key, access_token)
trade_manager = TradeManager(kite_helper=kite_helper, paper_mode=True)

strategy_sell = FiveEMAStrategy(kite_helper=kite_helper, trade_manager=trade_manager, mode="SELL")
strategy_buy = FiveEMAStrategy(kite_helper=kite_helper, trade_manager=trade_manager, mode="BUY")

# ───────────────────────────────
# Date Range
# ───────────────────────────────
if not test_from_env or not test_to_env:
    raise EnvironmentError("❌ TEST_FROM_DATE and TEST_TO_DATE must be set in .env")

from_date = datetime.strptime(test_from_env, "%Y-%m-%d")
to_date = datetime.strptime(test_to_env, "%Y-%m-%d") + timedelta(days=1)
logger.info(f"📅 Using TEST_FROM_DATE={test_from_env}, TEST_TO_DATE={test_to_env}")

# ───────────────────────────────
# Instrument Mapping
# ───────────────────────────────
instrument_token = cfg_all["SYSTEM"]["instrument_tokens"].get(underlying.upper())
if not instrument_token:
    raise ValueError(f"❌ Unsupported underlying '{underlying}'.")

# ───────────────────────────────
# Fetch Historical Candles (keep full series for warm-up)
# ───────────────────────────────
def fetch_and_process_candles(kite: KiteConnect, instrument_token: int, 
                            start_date: datetime, end_date: datetime, 
                            timeframe: str, direction: str) -> pd.DataFrame:
    """Fetch and process historical candles with error handling."""
    try:
        logger.info(f"🔄 Fetching {underlying} {timeframe} candles (for {direction}) with warm-up")
        candles = kite.historical_data(instrument_token, start_date, end_date, interval=timeframe)
        
        if not candles:
            raise ValueError(f"No data returned for {underlying} {timeframe}")
            
        df = pd.DataFrame(candles)
        
        # Standardize datetime column name
        if "date" in df.columns:
            df.rename(columns={"date": "datetime"}, inplace=True)
        elif "timestamp" in df.columns:
            df.rename(columns={"timestamp": "datetime"}, inplace=True)
            
        df["datetime"] = pd.to_datetime(df["datetime"])
        return df
        
    except KiteException as e:
        logger.error(f"❌ Kite API error while fetching {timeframe} data: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error while fetching {timeframe} data: {str(e)}")
        raise

warmup_days = cfg_all["SYSTEM"]["warmup_days"]
fetch_from = from_date - timedelta(days=warmup_days)
fetch_to = to_date

# Fetch historical data for both timeframes
df_sell_all = fetch_and_process_candles(kite, instrument_token, fetch_from, fetch_to, 
                                      timeframe_sell, "BEARISH")
df_buy_all = fetch_and_process_candles(kite, instrument_token, fetch_from, fetch_to, 
                                     timeframe_buy, "BULLISH")

logger.info(
    f"✅ Data ranges → BEARISH ({timeframe_sell}): {df_sell_all['datetime'].min()}–{df_sell_all['datetime'].max()} | "
    f"BULLISH ({timeframe_buy}): {df_buy_all['datetime'].min()}–{df_buy_all['datetime'].max()}"
)

# ───────────────────────────────
# Run both strategies across all dates
# ───────────────────────────────
def process_strategy(df: pd.DataFrame, strategy: FiveEMAStrategy, 
                    direction: str, timeframe: str, date: datetime.date) -> List[dict]:
    """Process a single strategy (BEARISH/BULLISH) for one day."""
    entries = []
    indices = df.index[df["datetime"].dt.date == date].tolist()
    
    if not indices:
        return entries
    
    strategy._reset_state()
    
    for pos in indices:
        subset = df.iloc[: pos + 1].reset_index(drop=True)
        strategy.identify_alert_candle(subset)
        entry = strategy.check_entry(subset)
        if entry:
            entry["direction"] = direction
            entry["timeframe"] = timeframe
            entries.append(entry)
    
    return entries

def process_trading_day(date: datetime.date, df_sell: pd.DataFrame, df_buy: pd.DataFrame,
                       strategy_sell: FiveEMAStrategy, strategy_buy: FiveEMAStrategy,
                       timeframe_sell: str, timeframe_buy: str) -> List[dict]:
    """Process both strategies for a single trading day."""
    if date < from_date.date() or date >= to_date.date():
        return []
        
    logger.info(f"📆 Processing date: {date}")
    
    # Process both strategies
    entries_sell = process_strategy(df_sell, strategy_sell, "BEARISH", timeframe_sell, date)
    entries_buy = process_strategy(df_buy, strategy_buy, "BULLISH", timeframe_buy, date)
    
    # Combine and sort entries chronologically
    all_entries = entries_sell + entries_buy
    if all_entries:
        all_entries.sort(key=lambda x: x["entry_time"])
        logger.info(f"   - Found {len(entries_sell)} BEARISH and {len(entries_buy)} BULLISH entries")
    
    return all_entries

# Process all trading days
entries = []
dates_in_range = sorted(df_sell_all["datetime"].dt.date.unique())

for current_date in dates_in_range:
    day_entries = process_trading_day(
        current_date, df_sell_all, df_buy_all,
        strategy_sell, strategy_buy,
        timeframe_sell, timeframe_buy
    )
    entries.extend(day_entries)

# ───────────────────────────────
# Analysis and Performance Metrics
# ───────────────────────────────
def analyze_entries(entries: List[dict], timeframe_sell: str, timeframe_buy: str) -> dict:
    """Analyze trade entries and compute performance metrics."""
    if not entries:
        return {
            "total_entries": 0,
            "bearish_entries": 0,
            "bullish_entries": 0,
            "entries_by_date": {},
            "timeframes": {"BEARISH": timeframe_sell, "BULLISH": timeframe_buy}
        }

    analysis = {
        "total_entries": len(entries),
        "bearish_entries": sum(1 for e in entries if e["direction"] == "BEARISH"),
        "bullish_entries": sum(1 for e in entries if e["direction"] == "BULLISH"),
        "entries_by_date": {},
        "timeframes": {"BEARISH": timeframe_sell, "BULLISH": timeframe_buy}
    }

    # Group entries by date
    for entry in entries:
        date = entry["entry_time"].date()
        if date not in analysis["entries_by_date"]:
            analysis["entries_by_date"][date] = {"BEARISH": 0, "BULLISH": 0}
        analysis["entries_by_date"][date][entry["direction"]] += 1

    return analysis

def log_summary(analysis: dict) -> None:
    """Log trade summary."""
    if analysis["total_entries"] == 0:
        logger.info("ℹ️ No trade entries found for either timeframe.")
        return

    logger.info(f"\n📈 Trade Summary:")
    logger.info(f"   Total Entries: {analysis['total_entries']}")
    logger.info(f"   - BEARISH ({analysis['timeframes']['BEARISH']}): {analysis['bearish_entries']}")
    logger.info(f"   - BULLISH ({analysis['timeframes']['BULLISH']}): {analysis['bullish_entries']}")

# ───────────────────────────────
# Process Results and Send Alerts
# ───────────────────────────────
def process_and_notify(entries: List[dict], underlying: str) -> None:
    """Process trade entries and send notifications."""
    if not entries:
        logger.info("ℹ️ No trade entries found for either timeframe.")
        return

    entries.sort(key=lambda x: x["entry_time"])
    
    for idx, entry in enumerate(entries, start=1):
        mode = entry["direction"]
        try:
            # Build message via notifier (keeps original format) and enrich with kite_helper
            msg = format_trade_message(entry, underlying, mode, timeframe=entry.get("timeframe"), kite_helper=kite_helper)
            # Log via notifier (consistent log format) with kite_helper to include suggestions
            log_trade(entry, underlying, mode, kite_helper=kite_helper)
            # Send telegram via notifier
            if bot_token and chat_id:  # Only send if Telegram is configured
                send_telegram(msg)
        except Exception as e:
            logger.error(f"❌ Error processing entry {idx}: {str(e)}")
            continue

# Generate analysis and process results
analysis = analyze_entries(entries, timeframe_sell, timeframe_buy)
log_summary(analysis)
process_and_notify(entries, underlying)
