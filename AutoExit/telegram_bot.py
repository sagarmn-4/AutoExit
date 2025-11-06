"""
Telegram Bot Handler for AutoExit
Provides command interface for controlling the position monitor.
"""
import logging
from typing import Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from utils.config import get_env_var, get_section
from utils.notifier import send_telegram


class TelegramBotHandler:
    """
    Handles Telegram bot commands for controlling AutoExit.
    
    Commands:
        /pause - Pause position monitoring
        /resume - Resume position monitoring
        /settarget <points> - Update target points
        /status - Show current bot status
    """
    
    def __init__(self, position_monitor):
        """
        Initialize Telegram bot handler.
        
        Args:
            position_monitor: PositionMonitor instance to control
        """
        self.monitor = position_monitor
        self.logger = logging.getLogger("telegram_bot")
        
        # Load config
        self.bot_token = get_env_var("TELEGRAM_BOT_TOKEN")
        self.chat_id = get_env_var("TELEGRAM_CHAT_ID")
        
        config = get_section("TELEGRAM")
        self.admin_users = set(config.get("admin_user_ids", []))
        
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not configured in .env")
        
        # Build application
        self.app = Application.builder().token(self.bot_token).build()
        
        # Register command handlers
        self.app.add_handler(CommandHandler("pause", self.pause_command))
        self.app.add_handler(CommandHandler("resume", self.resume_command))
        # Convenience aliases for pause/resume
        self.app.add_handler(CommandHandler("stop", self.pause_command))
        self.app.add_handler(CommandHandler("start", self.resume_command))
        self.app.add_handler(CommandHandler("settarget", self.set_target_command))
        self.app.add_handler(CommandHandler("paper", self.set_paper_mode_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
    
    def _is_authorized(self, update: Update) -> bool:
        """Check if user is authorized to use commands."""
        user_id = update.effective_user.id
        # If no admin list configured, allow the configured chat_id
        if not self.admin_users:
            return str(update.effective_chat.id) == self.chat_id
        return user_id in self.admin_users
    
    async def pause_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pause command."""
        if not self._is_authorized(update):
            await update.message.reply_text("❌ Unauthorized")
            return
        
        self.monitor.pause()
        await update.message.reply_text("⏸️ Monitoring paused")
    
    async def resume_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume command."""
        if not self._is_authorized(update):
            await update.message.reply_text("❌ Unauthorized")
            return
        
        self.monitor.resume()
        await update.message.reply_text("▶️ Monitoring resumed")
    
    async def set_target_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settarget <points> command."""
        if not self._is_authorized(update):
            await update.message.reply_text("❌ Unauthorized")
            return
        
        if not context.args or len(context.args) != 1:
            await update.message.reply_text("Usage: /settarget <points>\nExample: /settarget 50")
            return
        
        try:
            points = float(context.args[0])
            if points <= 0:
                await update.message.reply_text("❌ Target must be positive")
                return
            
            self.monitor.set_target(points)
            await update.message.reply_text(f"🎯 Target updated to {points} points")
        except ValueError:
            await update.message.reply_text("❌ Invalid number. Usage: /settarget <points>")
    
        # /setsl removed per simplified exit-only requirements

    async def set_paper_mode_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /paper <on|off> command to toggle paper mode at runtime."""
        if not self._is_authorized(update):
            await update.message.reply_text("❌ Unauthorized")
            return

        if not context.args or len(context.args) != 1:
            await update.message.reply_text("Usage: /paper <on|off>")
            return

        val = context.args[0].strip().lower()
        if val in ("on", "true", "1"):
            self.monitor.paper_mode = True
        elif val in ("off", "false", "0"):
            self.monitor.paper_mode = False
        else:
            await update.message.reply_text("❌ Invalid value. Use: on | off")
            return

        mode = "📝 PAPER MODE" if self.monitor.paper_mode else "🔴 LIVE MODE"
        # Confirm to the user and broadcast to the channel
        await update.message.reply_text(f"Mode updated: {mode}")
        try:
            send_telegram(f"⚙️ Mode toggled via bot: {mode}")
        except Exception:
            pass
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        if not self._is_authorized(update):
            await update.message.reply_text("❌ Unauthorized")
            return
        
        status = self.monitor.get_status()

        state = "⏸️ PAUSED" if status["paused"] else "▶️ RUNNING"
        mode = "📝 PAPER MODE" if status["paper_mode"] else "🔴 LIVE MODE"
        auto_exit = "✅ Enabled" if status["enable_auto_exit"] else "❌ Disabled"
        
        msg = (
            f"<b>AutoExit Bot Status</b>\n\n"
            f"State: {state}\n"
            f"Mode: {mode}\n"
            f"Auto-exit: {auto_exit}\n\n"
            f"🎯 Target: {status['target_points']} points\n"
            # Stop-loss removed
            f"📊 Tracked positions: {status['tracked_count']}"
        )
        await update.message.reply_text(msg, parse_mode="HTML")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        help_text = (
            "<b>AutoExit Bot Commands</b>\n\n"
            "/start - Resume monitoring\n"
            "/stop - Pause monitoring\n"
            "/resume - Resume monitoring (alias of /start)\n"
            "/pause - Pause monitoring (alias of /stop)\n"
            "/settarget &lt;points&gt; - Set target profit\n"
            "/paper &lt;on|off&gt; - Toggle paper mode\n"
            # /setsl removed
            "/status - Show bot status\n"
            "/help - Show this help"
        )
        await update.message.reply_text(help_text, parse_mode="HTML")
    
    async def start(self):
        """Start the Telegram bot."""
        self.logger.info("Starting Telegram bot")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
    
    async def stop(self):
        """Stop the Telegram bot."""
        self.logger.info("Stopping Telegram bot")
        await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()
