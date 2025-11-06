"""
Health check script for 5EMA AutoTrader system
Ensures:
 - .env is loaded properly
 - Kite API credentials are valid
 - Telegram notifications work
 - Optionally performs safe project cleanup
"""

import os
import logging
from kiteconnect import KiteConnect
import requests
import subprocess
import sys

from utils.config import get_kite_credentials, get_env_var
from utils.common import mask_secret

# ───────────────────────────────
# 🧠 Logging setup
# ───────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# ───────────────────────────────
# Load environment variables via centralized config helpers
# ───────────────────────────────
creds = get_kite_credentials()
KITE_API_KEY = creds.get("KITE_API_KEY")
KITE_ACCESS_TOKEN = creds.get("KITE_ACCESS_TOKEN")
bot_token = get_env_var("TELEGRAM_BOT_TOKEN")
chat_id = get_env_var("TELEGRAM_CHAT_ID")

masked_key = mask_secret(KITE_API_KEY)
masked_token = mask_secret(KITE_ACCESS_TOKEN)

logging.info(f"🔑 API Key: {masked_key}")
logging.info(f"🎟 Access Token: {masked_token}")
logging.info(f"💬 Telegram Chat ID: {chat_id}")

# ───────────────────────────────
# 🧩 Validation of environment variables
# ───────────────────────────────
if not all([KITE_API_KEY, KITE_ACCESS_TOKEN, bot_token, chat_id]):
    raise ValueError("❌ Missing one or more environment variables (KITE or Telegram) in .env or environment")

# ───────────────────────────────
# 🔗 Test Kite API connection
# ───────────────────────────────
try:
    kite = KiteConnect(api_key=KITE_API_KEY)
    kite.set_access_token(KITE_ACCESS_TOKEN)
    profile = kite.profile()
    logging.info("✅ Kite API connection successful")
    logging.info(f"👤 Logged in as: {profile.get('user_name')} ({profile.get('user_id')})")

    message = (
        "✅ <b>Health Check Passed</b>\n"
        "Kite API connection successful.\n"
        f"👤 User: {profile.get('user_name')} ({profile.get('user_id')})\n"
        "🚀 All systems operational."
    )
except Exception as e:
    logging.error(f"❌ Kite connection failed: {e}")
    message = f"❌ <b>Health Check Failed</b>\nError: {e}"

# ───────────────────────────────
# ✉️ Send Telegram Notification
# ───────────────────────────────
try:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    resp = requests.post(url, data=payload)
    if resp.status_code == 200:
        logging.info("📨 Telegram alert sent successfully")
    else:
        logging.error(f"⚠️ Telegram alert failed: {resp.text}")
except Exception as e:
    logging.error(f"❌ Telegram alert error: {e}")

# ───────────────────────────────
# 🧹 Optional Cleanup Prompt
# ───────────────────────────────
try:
    user_input = input("\n🧹 Run cleanup before exit? (y/n): ").strip().lower()
    if user_input == "y":
        cleanup_script = os.path.join(os.path.dirname(__file__), "u_cleanup_project.py")
        if os.path.exists(cleanup_script):
            logging.info("🧩 Running project cleanup...")
            subprocess.run([sys.executable, cleanup_script], check=True)
            logging.info("✅ Cleanup complete. Exiting health check.")
        else:
            logging.warning("⚠️ cleanup_project.py not found in the project directory.")
    else:
        logging.info("Skipping cleanup.")
except Exception as e:
    logging.error(f"⚠️ Cleanup step failed: {e}")
