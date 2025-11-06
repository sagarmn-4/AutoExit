"""# main.py

AutoExit Bot - Main Entry Point"""

Automated position exit management with Telegram controls.Main runner for the 5EMA automation.

- Runs SELL (5-min) and BUY (15-min) strategies concurrently.

This bot monitors open long positions via Kite API and automatically places- Each strategy uses the FiveEMAStrategy class in strategies/five_ema_strategy.py

target and stop-loss orders. Provides Telegram commands for dynamic control.- Uses utils.KiteHelper and utils.TradeManager for API and execution.

"""

Author: AutoExit Bot

Python: 3.10+import os

"""import time

import asyncioimport threading

import loggingimport logging

import signalfrom logging.handlers import RotatingFileHandler

import sysfrom utils.config import get_kite_credentials, get_section

from pathlib import Path

# local imports

# Ensure project root is on path for importsfrom utils.kite_helper import KiteHelper

PROJECT_ROOT = Path(__file__).resolve().parentfrom utils.trade_manager import TradeManager

if str(PROJECT_ROOT) not in sys.path:from strategies.five_ema_strategy import FiveEMAStrategy

    sys.path.insert(0, str(PROJECT_ROOT))

# ------------- Configuration & logging setup -------------

from strategies.position_monitor import PositionMonitor# Load credentials from centralized helper (checks .env)

from telegram_bot import TelegramBotHandlercreds = get_kite_credentials()

from utils.kite_helper import KiteHelperKITE_API_KEY = creds.get("KITE_API_KEY")

from utils.config import get_kite_credentials, get_sectionKITE_API_SECRET = creds.get("KITE_API_SECRET")

from utils.common import setup_logger, load_envKITE_ACCESS_TOKEN = creds.get("KITE_ACCESS_TOKEN")



# If access token wasn't provided in the environment, fall back to file

class AutoExitBot:if not KITE_ACCESS_TOKEN:

    """    KITE_ACCESS_TOKEN_PATH = os.path.join(os.path.dirname(__file__), "KITE_ACCESS_TOKEN.txt")

    Main bot coordinator.    if not os.path.exists(KITE_ACCESS_TOKEN_PATH):

    Manages position monitor and Telegram bot in concurrent async tasks.        raise SystemExit("KITE_ACCESS_TOKEN not found in env or file. Run scripts/generate_token.py to generate it.")

    """    with open(KITE_ACCESS_TOKEN_PATH, "r") as f:

            KITE_ACCESS_TOKEN = f.read().strip()

    def __init__(self):

        """Initialize the AutoExit bot."""# Create logs directory

        # Load environmentLOG_DIR = os.path.join(os.path.dirname(__file__), "logs")

        load_env()os.makedirs(LOG_DIR, exist_ok=True)

        

        # Setup logging# root logger

        system_config = get_section("SYSTEM")root_logger = logging.getLogger()

        log_level = getattr(logging, system_config.get("log_level", "INFO"))root_logger.setLevel(logging.INFO)

        self.logger = setup_logger("autoexit", "autoexit.log", log_level)fmt = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")

        

        self.logger.info("=" * 60)# console handler

        self.logger.info("AutoExit Bot Initializing")ch = logging.StreamHandler()

        self.logger.info("=" * 60)ch.setFormatter(fmt)

        root_logger.addHandler(ch)

        # Initialize Kite API

        creds = get_kite_credentials()def make_file_logger(name, logfile):

        self.kite_helper = KiteHelper(    logger = logging.getLogger(name)

            creds["KITE_API_KEY"],    logger.setLevel(logging.INFO)

            creds["KITE_ACCESS_TOKEN"]    # Avoid adding multiple handlers when reloading

        )    if not any(isinstance(h, RotatingFileHandler) and h.baseFilename.endswith(logfile) for h in logger.handlers):

        self.logger.info("Kite API initialized")        fh = RotatingFileHandler(os.path.join(LOG_DIR, logfile), maxBytes=5_000_000, backupCount=5)

                fh.setFormatter(fmt)

        # Initialize position monitor        logger.addHandler(fh)

        self.position_monitor = PositionMonitor(self.kite_helper)    return logger

        self.logger.info("Position monitor initialized")

        # ------------- Kite Helper & Trade Manager Initialization -------------

        # Initialize Telegram botkite_helper = KiteHelper(KITE_API_KEY=KITE_API_KEY, KITE_ACCESS_TOKEN=KITE_ACCESS_TOKEN)

        telegram_config = get_section("TELEGRAM")trade_manager = TradeManager(kite_helper)

        if telegram_config.get("enable_commands", True):

            self.telegram_bot = TelegramBotHandler(self.position_monitor)# ------------- Strategy Worker Thread Function -------------

            self.logger.info("Telegram bot initialized")def strategy_worker(mode):

        else:    """

            self.telegram_bot = None    Worker wrapper to run a strategy instance with basic restart/backoff on exception.

            self.logger.info("Telegram commands disabled")    mode: "SELL" or "BUY"

            """

        # Signal handling    logger = make_file_logger(f"strategy_{mode}", f"strategy_{mode.lower()}.log")

        self.shutdown_event = asyncio.Event()    logger.info(f"Starting strategy worker for mode={mode}")

        signal.signal(signal.SIGINT, self._signal_handler)

        signal.signal(signal.SIGTERM, self._signal_handler)    backoff = 5  # seconds, initial

        max_backoff = 300  # 5 minutes

    def _signal_handler(self, sig, frame):

        """Handle shutdown signals gracefully."""    while not stop_event.is_set():

        self.logger.info(f"Received signal {sig}, initiating shutdown...")        try:

        self.shutdown_event.set()            # instantiate fresh strategy object each run (clean state)

                strat = FiveEMAStrategy(kite_helper=kite_helper, trade_manager=trade_manager, mode=mode)

    async def run(self):            logger.info(f"Initialized {mode} strategy. Entering execute loop.")

        """Run the bot with all components."""            # run strategy; this blocks until the strategy's execute_strategy returns (it loops inside)

        try:            strat.execute_strategy()

            # Start tasks concurrently            # If execution returns normally (rare), restart after short delay

            tasks = [            logger.warning(f"{mode} strategy exited execute_strategy() — restarting after short delay.")

                asyncio.create_task(self.position_monitor.start(), name="position_monitor")            time.sleep(5)

            ]            backoff = 5

                    except Exception as e:

            if self.telegram_bot:            logger.exception(f"Unhandled exception in {mode} strategy: {e}")

                tasks.append(            # exponential backoff to avoid tight crash loops

                    asyncio.create_task(self.telegram_bot.start(), name="telegram_bot")            logger.info(f"Restarting {mode} strategy after {backoff} seconds.")

                )            time.sleep(backoff)

                        backoff = min(backoff * 2, max_backoff)

            self.logger.info("All components started successfully")    logger.info(f"{mode} worker stopped.")

            

            # Wait for shutdown signal# ------------- Start Threads -------------

            await self.shutdown_event.wait()stop_event = threading.Event()

            threads = []

            # Graceful shutdown

            self.logger.info("Shutting down...")def start_all():

                for mode in ("SELL", "BUY"):

            await self.position_monitor.stop()        t = threading.Thread(target=strategy_worker, args=(mode,), daemon=True, name=f"strat-{mode}")

            if self.telegram_bot:        threads.append(t)

                await self.telegram_bot.stop()        t.start()

                    logging.info(f"Thread started for {mode} strategy: {t.name}")

            # Cancel remaining tasks    logging.info("All strategy threads started.")

            for task in tasks:

                if not task.done():def stop_all():

                    task.cancel()    logging.info("Stop signal received. Stopping strategy threads...")

                stop_event.set()

            await asyncio.gather(*tasks, return_exceptions=True)    # Give threads some time to exit

                for t in threads:

            self.logger.info("Shutdown complete")        if t.is_alive():

                        t.join(timeout=10)

        except Exception as e:    logging.info("All threads requested to stop. Exiting main.")

            self.logger.error(f"Fatal error in main loop: {e}", exc_info=True)

            sys.exit(1)# ------------- Graceful shutdown handling -------------

if __name__ == "__main__":

    try:

async def main():        logging.info("----- 5EMA AutoTrader starting -----")

    """Async entry point."""        start_all()

    bot = AutoExitBot()        # Keep main thread alive while worker threads run

    await bot.run()        while True:

            time.sleep(1)

    except KeyboardInterrupt:

if __name__ == "__main__":        logging.info("KeyboardInterrupt received — shutting down.")

    try:        stop_all()

        asyncio.run(main())    except Exception as e:

    except KeyboardInterrupt:        logging.exception(f"Fatal error in main: {e}")

        print("\nShutdown initiated by user")        stop_all()

    except Exception as e:    finally:

        print(f"Fatal error: {e}")        logging.info("Main terminated.")

        sys.exit(1)
