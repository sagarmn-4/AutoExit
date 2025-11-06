"""
Centralized Notification and Logging Utility
Used by both test_strategy and live_autotrader.
"""

import logging, requests, os
from datetime import datetime
from dotenv import load_dotenv

from utils.config import get_env_var, get_config, get_section
from utils.common import setup_logger

# Load telegram credentials via centralized helper
bot_token = get_env_var("TELEGRAM_BOT_TOKEN")
chat_id = get_env_var("TELEGRAM_CHAT_ID")

# Use centralized logger helper for notifier
logger = setup_logger("Notifier")

# ───────────────────────────────
# Telegram Helper
# ───────────────────────────────
def send_telegram(message: str):
    """Send formatted message to Telegram"""
    if not bot_token or not chat_id:
        logger.warning("⚠️ Telegram not configured — skipping message.")
        return
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        logger.error(f"❌ Telegram send failed: {e}")

# ───────────────────────────────
# Message Builder
# ───────────────────────────────
def format_trade_message(entry, underlying, mode, timeframe=None, live=False, kite_helper=None):
    """Generate consistent Telegram message format.

    New: suggests option type (CALL/PUT), suggested strike (using config.otm_strike_distance),
    includes underlying LTP (when `kite_helper` provided) and number of lots from config.
    """
    sentiment_icon = "🟥" if mode in ["SELL", "BEARISH"] else "🟩"
    label = "BEARISH" if mode in ["SELL", "BEARISH"] else "BULLISH"

    targets_text = (
        " | ".join([f"{t:.2f}" for t in entry.get("targets", [])])
        if entry.get("targets")
        else "—"
    )

    context_date = "LIVE" if live else entry["entry_time"].strftime("%d %b %Y")
    time_text = datetime.now().strftime("%I:%M %p") if live else entry["entry_time"].strftime("%I:%M %p")

    # Read config for strike distance and lots
    try:
        section = "SELL" if mode in ["SELL", "BEARISH"] else "BUY"
        mode_cfg = get_section(section)
        otm_dist = int(mode_cfg.get("otm_strike_distance", 0))
        lots = int(mode_cfg.get("lots", 1))
    except Exception:
        otm_dist = 0
        lots = 1

    # Attempt to fetch underlying LTP via kite_helper (requires instrument token in config.SYSTEM)
    suggested_strike = None
    option_type = "CALL" if label == "BEARISH" else "PUT"
    try:
        cfg_all = get_config()
        instr_map = cfg_all.get("SYSTEM", {}).get("instrument_tokens", {})
        instr_token = instr_map.get(underlying.upper())
        # simple strike rounding heuristic — default 50 for index strikes
        # Get strike interval from config (default 50 for compatibility)
        strike_step = cfg_all.get("SYSTEM", {}).get("strike_intervals", {}).get(underlying.upper(), 50)

        # Use entry price for strike calculation (more relevant than current LTP)
        if entry["entry_price"] is not None:
                entry_price = float(entry["entry_price"])
                
                # Calculate nearest strike based on entry price
                base_strike = (entry_price // strike_step) * strike_step
                
                if label == "BEARISH":
                    # For BEARISH: Use next strike above entry
                    # If entry is 25108.70 -> 25150
                    # If entry is 25258.15 -> 25300
                    suggested_strike = int(base_strike + strike_step)
                    if suggested_strike - entry_price > strike_step:
                        suggested_strike = int(base_strike)
                else:
                    # For BULLISH: Use nearest strike below entry
                    # If entry is 25214.10 -> 25200
                    suggested_strike = int(base_strike)
    except Exception:
        suggested_strike = None

    # Try to fetch option LTP for suggested strike at entry time, if possible
    opt_price_text = "N/A"
    try:
        if kite_helper and suggested_strike is not None and "entry_time" in entry:
            opt_ltp = kite_helper.get_option_ltp(
                underlying_label=underlying,
                entry_dt=entry["entry_time"],
                strike=int(suggested_strike),
                option_type=option_type,
            )
            if opt_ltp is not None:
                opt_price_text = f"{opt_ltp:.2f}"
    except Exception:
        pass

    msg = (
        f"{sentiment_icon} <b>{label} Entry Triggered {'(LIVE)' if live else ''}</b>\n"
        f"🔹 {underlying}{f' ({timeframe})' if timeframe else ''} | {context_date}\n"
        f"🕒 Time: {time_text}\n"
        f"💰 Entry: {entry['entry_price']:.2f}\n"
        f"🛑 Stop Loss: {entry['stop_loss']:.2f}\n"
        f"🎯 Targets: {targets_text}\n"
        f"⚙️ Mode: {label}\n"
        f"🔧 Suggestion: SELL {option_type} | Strike: {suggested_strike if suggested_strike else '—'} | Est Option Price: {opt_price_text}\n"
        f"📦 Lots: {lots}"
    )
    return msg

# ───────────────────────────────
# Logging Helper
# ───────────────────────────────
def log_trade(entry, underlying, mode, kite_helper=None):
    """Consistent log output including option suggestion and lots when possible."""
    label = "BEARISH" if mode in ["SELL", "BEARISH"] else "BULLISH"
    time_str = (
        entry["entry_time"].strftime("%I:%M %p")
        if "entry_time" in entry
        else datetime.now().strftime("%I:%M %p")
    )
    price = entry.get("entry_price", 0)

    # Try to include lots and suggested strike
    try:
        section = "SELL" if mode in ["SELL", "BEARISH"] else "BUY"
        mode_cfg = get_section(section)
        otm_dist = int(mode_cfg.get("otm_strike_distance", 0))
        lots = int(mode_cfg.get("lots", 1))
    except Exception:
        otm_dist = 0
        lots = 1

    suggested = "—"
    try:
        cfg_all = get_config()
        # Get strike interval from config
        strike_step = cfg_all.get("SYSTEM", {}).get("strike_intervals", {}).get(underlying.upper(), 50)
        
        if price:
            # Use entry price (not LTP) for strike calculation
            entry_price = float(price)
            base_strike = (entry_price // strike_step) * strike_step
            
            if label == "BEARISH":
                # For BEARISH: Use next strike above entry
                suggested = int(base_strike + strike_step)
                if suggested - entry_price > strike_step:
                    suggested = int(base_strike)
            else:
                # For BULLISH: Use nearest strike below entry
                suggested = int(base_strike)
    except Exception:
        suggested = "—"

    logger.info(f"📢 {underlying} {label} | {time_str} | {price} | StrikeSuggestion={suggested} | Lots={lots}")
