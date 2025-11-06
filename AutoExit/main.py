"""
AutoExit Bot - Main Entry Point

Monitors open long positions via Kite API and automatically places target/SL exit orders.
Provides Telegram commands for dynamic control.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import List

from utils.common import setup_logger
from utils.config import get_section
from utils.kite_helper import KiteHelper
from strategies.position_monitor import PositionMonitor
from telegram_bot import TelegramBotHandler


async def run() -> None:
    """Start position monitor and optional Telegram bot and keep running until interrupted."""
    # Configure logging level from config
    sys_cfg = get_section("SYSTEM")
    log_level_name = sys_cfg.get("log_level", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    logger = setup_logger("autoexit", "autoexit.log", level=log_level)
    # Also route component logs into the same file for full visibility
    setup_logger("position_monitor", "autoexit.log", level=log_level)
    setup_logger("telegram_bot", "autoexit.log", level=log_level)
    logger.info("====== AutoExit Bot Initializing ======")

    # Initialize Kite helper from environment
    kite_helper = KiteHelper.from_env()
    monitor = PositionMonitor(kite_helper)

    # Initialize Telegram bot if configured
    bot: TelegramBotHandler | None = None
    try:
        bot = TelegramBotHandler(monitor)
        logger.info("Telegram bot initialized")
    except Exception as e:
        # Telegram is optional; if not configured, continue without it
        logger.warning(f"Telegram not started: {e}")
        bot = None

    tasks: List[asyncio.Task] = []
    tasks.append(asyncio.create_task(monitor.start(), name="position_monitor"))
    if bot:
        tasks.append(asyncio.create_task(bot.start(), name="telegram_bot"))

    # Graceful shutdown handlers (best-effort on Windows)
    stop_event = asyncio.Event()

    def _handle_signal(sig_num, _frame):
        logger.info(f"Received signal {sig_num}. Shutting down...")
        stop_event.set()

    for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
        if sig is not None:
            try:
                signal.signal(sig, _handle_signal)
            except Exception:
                pass

    try:
        # Wait until stop requested
        await stop_event.wait()
    finally:
        # Stop components
        await monitor.stop()
        if bot:
            try:
                await bot.stop()
            except Exception:
                pass

        # Cancel any remaining tasks
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        # Already handled by signal, just exit quietly
        pass
