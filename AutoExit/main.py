# main.py
"""
Main runner for the 5EMA automation.
- Runs SELL (5-min) and BUY (15-min) strategies concurrently.
- Each strategy uses the FiveEMAStrategy class in strategies/five_ema_strategy.py
- Uses utils.KiteHelper and utils.TradeManager for API and execution.
"""

import os
import time
import threading
import logging
from logging.handlers import RotatingFileHandler
from utils.config import get_kite_credentials, get_section

# local imports
from utils.kite_helper import KiteHelper
from utils.trade_manager import TradeManager
from strategies.five_ema_strategy import FiveEMAStrategy

# ------------- Configuration & logging setup -------------
# Load credentials from centralized helper (checks .env)
creds = get_kite_credentials()
KITE_API_KEY = creds.get("KITE_API_KEY")
KITE_API_SECRET = creds.get("KITE_API_SECRET")
KITE_ACCESS_TOKEN = creds.get("KITE_ACCESS_TOKEN")

# If access token wasn't provided in the environment, fall back to file
if not KITE_ACCESS_TOKEN:
    KITE_ACCESS_TOKEN_PATH = os.path.join(os.path.dirname(__file__), "KITE_ACCESS_TOKEN.txt")
    if not os.path.exists(KITE_ACCESS_TOKEN_PATH):
        raise SystemExit("KITE_ACCESS_TOKEN not found in env or file. Run scripts/generate_token.py to generate it.")
    with open(KITE_ACCESS_TOKEN_PATH, "r") as f:
        KITE_ACCESS_TOKEN = f.read().strip()

# Create logs directory
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
fmt = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")

# console handler
ch = logging.StreamHandler()
ch.setFormatter(fmt)
root_logger.addHandler(ch)

def make_file_logger(name, logfile):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    # Avoid adding multiple handlers when reloading
    if not any(isinstance(h, RotatingFileHandler) and h.baseFilename.endswith(logfile) for h in logger.handlers):
        fh = RotatingFileHandler(os.path.join(LOG_DIR, logfile), maxBytes=5_000_000, backupCount=5)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger

# ------------- Kite Helper & Trade Manager Initialization -------------
kite_helper = KiteHelper(KITE_API_KEY=KITE_API_KEY, KITE_ACCESS_TOKEN=KITE_ACCESS_TOKEN)
trade_manager = TradeManager(kite_helper)

# ------------- Strategy Worker Thread Function -------------
def strategy_worker(mode):
    """
    Worker wrapper to run a strategy instance with basic restart/backoff on exception.
    mode: "SELL" or "BUY"
    """
    logger = make_file_logger(f"strategy_{mode}", f"strategy_{mode.lower()}.log")
    logger.info(f"Starting strategy worker for mode={mode}")

    backoff = 5  # seconds, initial
    max_backoff = 300  # 5 minutes

    while not stop_event.is_set():
        try:
            # instantiate fresh strategy object each run (clean state)
            strat = FiveEMAStrategy(kite_helper=kite_helper, trade_manager=trade_manager, mode=mode)
            logger.info(f"Initialized {mode} strategy. Entering execute loop.")
            # run strategy; this blocks until the strategy's execute_strategy returns (it loops inside)
            strat.execute_strategy()
            # If execution returns normally (rare), restart after short delay
            logger.warning(f"{mode} strategy exited execute_strategy() — restarting after short delay.")
            time.sleep(5)
            backoff = 5
        except Exception as e:
            logger.exception(f"Unhandled exception in {mode} strategy: {e}")
            # exponential backoff to avoid tight crash loops
            logger.info(f"Restarting {mode} strategy after {backoff} seconds.")
            time.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
    logger.info(f"{mode} worker stopped.")

# ------------- Start Threads -------------
stop_event = threading.Event()
threads = []

def start_all():
    for mode in ("SELL", "BUY"):
        t = threading.Thread(target=strategy_worker, args=(mode,), daemon=True, name=f"strat-{mode}")
        threads.append(t)
        t.start()
        logging.info(f"Thread started for {mode} strategy: {t.name}")
    logging.info("All strategy threads started.")

def stop_all():
    logging.info("Stop signal received. Stopping strategy threads...")
    stop_event.set()
    # Give threads some time to exit
    for t in threads:
        if t.is_alive():
            t.join(timeout=10)
    logging.info("All threads requested to stop. Exiting main.")

# ------------- Graceful shutdown handling -------------
if __name__ == "__main__":
    try:
        logging.info("----- 5EMA AutoTrader starting -----")
        start_all()
        # Keep main thread alive while worker threads run
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt received — shutting down.")
        stop_all()
    except Exception as e:
        logging.exception(f"Fatal error in main: {e}")
        stop_all()
    finally:
        logging.info("Main terminated.")
