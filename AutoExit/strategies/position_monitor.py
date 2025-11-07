"""
AutoExit Position Monitor
Monitors open long positions and places target exit orders.
"""
import asyncio
import logging
from typing import Dict, List, Optional, Set
from datetime import datetime

from utils.kite_helper import KiteHelper
from utils.config import get_section
from utils.notifier import send_telegram


class PositionMonitor:
    """
    Monitors positions via Kite API and places automatic exit orders.
    
    Attributes:
        kite_helper: KiteHelper instance for API access
        target_points: Target profit points above entry
        stoploss_points: Stop-loss points below entry
        tracked_positions: Set of position keys already processed
        paused: Whether monitoring is currently paused
    """
    
    def __init__(self, kite_helper: KiteHelper):
        """
        Initialize position monitor.
        
        Args:
            kite_helper: KiteHelper instance for Kite API access
        """
        self.kite_helper = kite_helper
        self.logger = logging.getLogger("position_monitor")
        
        # Load config
        config = get_section("EXIT_STRATEGY")
        self.target_points = config["target_points"]
        # Simplified: no stop-loss orders and no product/variety in config
        self.enable_auto_exit = config["enable_auto_exit"]
        self.paper_mode = config["paper_mode"]
        # Minimum entry price threshold to skip cheap hedge positions
        self.min_entry_price = float(config.get("min_entry_price", 50))
        
        system_config = get_section("SYSTEM")
        self.poll_interval = system_config["poll_interval_seconds"]
        self.max_retries = system_config["max_api_retries"]
        self.retry_backoff = system_config["retry_backoff_seconds"]
        
        # State
        self.tracked_positions: Set[str] = set()
        self.paused = False
        self.running = False
        
    def _position_key(self, position: Dict) -> str:
        """Generate unique key for a position."""
        return f"{position['tradingsymbol']}_{position['product']}"
    
    async def start(self):
        """Start the position monitoring loop."""
        self.running = True
        self.logger.info("Position monitor started")
        send_telegram("✅ AutoExit Bot Started\nMonitoring positions...")
        
        while self.running:
            try:
                if not self.paused:
                    await self._check_positions()
                await asyncio.sleep(self.poll_interval)
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}", exc_info=True)
                await asyncio.sleep(self.retry_backoff)
    
    async def stop(self):
        """Stop the position monitoring loop."""
        self.running = False
        self.logger.info("Position monitor stopped")
    
    def pause(self):
        """Pause monitoring."""
        self.paused = True
        self.logger.info("Position monitor paused")
        send_telegram("⏸️ Monitoring Paused")
    
    def resume(self):
        """Resume monitoring."""
        self.paused = False
        self.logger.info("Position monitor resumed")
        send_telegram("▶️ Monitoring Resumed")
    
    def set_target(self, points: float):
        """Update target points dynamically."""
        self.target_points = points
        self.logger.info(f"Target updated to {points} points")
        send_telegram(f"🎯 Target updated: {points} points")
    
    # Stop-loss functionality intentionally removed per simplified requirements
    
    def get_status(self) -> Dict:
        """Get current bot status."""
        return {
            "paused": self.paused,
            "running": self.running,
            "target_points": self.target_points,
            # stoploss_points removed in simplified mode
            "tracked_count": len(self.tracked_positions),
            "paper_mode": self.paper_mode,
            "enable_auto_exit": self.enable_auto_exit
        }
    
    async def _check_positions(self):
        """Check positions and place exit orders for new longs."""
        try:
            positions = await asyncio.to_thread(self.kite_helper.kite.positions)
            net_positions = positions.get("net", [])
            
            for position in net_positions:
                # Only process long positions (quantity > 0)
                quantity = position.get("quantity", 0)
                if quantity <= 0:
                    continue
                
                pos_key = self._position_key(position)
                
                # Skip if already tracked
                if pos_key in self.tracked_positions:
                    continue
                
                # New long position detected
                self.logger.info(f"New long position detected: {pos_key}")
                placed = await self._place_exit_orders(position)
                # Only mark as tracked if we actually placed (or simulated) exits
                if placed:
                    self.tracked_positions.add(pos_key)
                
        except Exception as e:
            self.logger.error(f"Error checking positions: {e}", exc_info=True)
    
    async def _place_exit_orders(self, position: Dict) -> bool:
        """
        Place target and stop-loss orders for a position.
        
        Args:
            position: Position dict from Kite API
        """
        try:
            symbol = position["tradingsymbol"]
            quantity = position["quantity"]
            avg_price = position["average_price"]
            exchange = position["exchange"]
            
            if not self.enable_auto_exit:
                self.logger.info(f"Auto-exit disabled, skipping {symbol}")
                return False

            # Skip low-price entries (likely hedge OTM options)
            if avg_price <= self.min_entry_price:
                self.logger.info(
                    f"Skipping {symbol}: entry ₹{avg_price} <= min_entry_price ₹{self.min_entry_price}"
                )
                return False
            
            # Calculate exit price (target only)
            target_price = round(avg_price + self.target_points, 2)
            
            self.logger.info(f"Placing target exit for {symbol}: Entry={avg_price}, Target={target_price}")
            
            if self.paper_mode:
                # Paper mode: just log and notify
                msg = (
                    f"📊 <b>Paper Mode Exit Orders</b>\n\n"
                    f"Symbol: {symbol}\n"
                    f"Qty: {quantity}\n"
                    f"Entry: ₹{avg_price}\n"
                    f"🎯 Target: ₹{target_price} (+{self.target_points})"
                )
                send_telegram(msg)
                self.logger.info(f"Paper mode: Would place exits for {symbol}")
            else:
                # Live mode: place actual orders
                # Target order (limit sell)
                target_order = await asyncio.to_thread(
                    self.kite_helper.kite.place_order,
                    variety="regular",
                    exchange=exchange,
                    tradingsymbol=symbol,
                    transaction_type="SELL",
                    quantity=quantity,
                    product="NRML",
                    order_type="LIMIT",
                    price=target_price
                )

                msg = (
                    f"✅ <b>Exit Orders Placed</b>\n\n"
                    f"Symbol: {symbol}\n"
                    f"Qty: {quantity}\n"
                    f"Entry: ₹{avg_price}\n"
                    f"🎯 Target: ₹{target_price} (Order: {target_order})"
                )
                send_telegram(msg)
                self.logger.info(f"Placed target exit for {symbol}: Target={target_order}")
            return True
                
        except Exception as e:
            self.logger.error(f"Error placing exit orders: {e}", exc_info=True)
            send_telegram(f"❌ Error placing exits for {position['tradingsymbol']}: {str(e)}")
            return False
