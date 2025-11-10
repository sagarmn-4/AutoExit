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
        # Pending exits map: pos_key -> remaining quantity to exit
        self.pending_exits: Dict[str, int] = {}
        self.paused = False
        self.running = False
        # Track when all qualifying positions are covered by exit orders to avoid spamming
        self.last_all_covered = None
        
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

    def set_poll_interval(self, seconds: float):
        """Update polling interval (seconds) at runtime with basic safety limits."""
        try:
            val = float(seconds)
        except (TypeError, ValueError):
            raise ValueError("poll interval must be a number (seconds)")

        # Safety bounds: avoid too-frequent calls and excessively slow loops
        MIN_S = 2.0
        MAX_S = 120.0
        clamped = max(MIN_S, min(val, MAX_S))
        if clamped != val:
            self.logger.info(f"Requested poll interval {val}s clamped to {clamped}s")
        self.poll_interval = clamped
        self.logger.info(f"Poll interval updated to {self.poll_interval}s")
        try:
            send_telegram(f"⏱️ Poll interval set to {self.poll_interval} seconds")
        except Exception:
            pass
    
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
            "enable_auto_exit": self.enable_auto_exit,
            "poll_interval_seconds": self.poll_interval,
        }
    
    async def _check_positions(self):
        """Check positions and place exit orders for new longs."""
        try:
            positions = await asyncio.to_thread(self.kite_helper.kite.positions)
            # Fetch current open orders to compute existing pending exits
            try:
                orders = await asyncio.to_thread(self.kite_helper.kite.orders)
            except Exception:
                orders = []

            pending_sell_by_key: Dict[str, int] = {}
            for od in orders or []:
                try:
                    if od.get("transaction_type") != "SELL":
                        continue
                    status = (od.get("status") or "").upper()
                    if status not in ("OPEN", "TRIGGER PENDING"):
                        continue
                    sym = od.get("tradingsymbol")
                    prod = od.get("product")
                    pos_key = f"{sym}_{prod}"
                    pend = od.get("pending_quantity")
                    if pend is None:
                        qty = int(od.get("quantity", 0))
                        filled = int(od.get("filled_quantity", 0))
                        pend = max(qty - filled, 0)
                    pending_sell_by_key[pos_key] = pending_sell_by_key.get(pos_key, 0) + int(pend)
                except Exception:
                    continue

            net_positions = positions.get("net", [])
            any_qualifying = False
            uncovered_found = False

            for position in net_positions:
                quantity = position.get("quantity", 0)
                if quantity <= 0:
                    continue
                pos_key = self._position_key(position)
                avg_price = position.get("average_price", 0.0)
                if avg_price <= self.min_entry_price:
                    continue
                any_qualifying = True

                pending_sell = int(pending_sell_by_key.get(pos_key, 0))
                net_qty = int(quantity)
                desired_remaining = max(net_qty - pending_sell, 0)

                # Pending continuation
                if pos_key in self.pending_exits:
                    if desired_remaining <= 0:
                        del self.pending_exits[pos_key]
                        self.tracked_positions.add(pos_key)
                        self.logger.info(f"{pos_key}: fully covered by existing exit orders; clearing pending")
                        continue
                    if self.pending_exits[pos_key] != desired_remaining:
                        self.logger.info(f"{pos_key}: adjust pending remainder {self.pending_exits[pos_key]} -> {desired_remaining}")
                        self.pending_exits[pos_key] = desired_remaining
                    self.logger.info(f"Continuing pending exits for {pos_key}; remaining={self.pending_exits[pos_key]}")
                    cont_ok = await self._place_exit_orders(position, resume_pending=True)
                    if cont_ok and pos_key not in self.pending_exits and desired_remaining > 0:
                        self.tracked_positions.add(pos_key)
                    if desired_remaining > 0 and pos_key in self.pending_exits:
                        uncovered_found = True
                    continue

                if pos_key in self.tracked_positions:
                    continue

                if desired_remaining <= 0:
                    self.tracked_positions.add(pos_key)
                    self.logger.info(f"{pos_key}: exit orders already cover full qty; skipping placement")
                    continue

                self.logger.info(f"New long position detected: {pos_key} (remaining to cover: {desired_remaining})")
                self.pending_exits[pos_key] = desired_remaining
                placed = await self._place_exit_orders(position, resume_pending=True)
                if placed and pos_key not in self.pending_exits:
                    self.tracked_positions.add(pos_key)
                else:
                    uncovered_found = True

            new_all_covered = (any_qualifying and not uncovered_found)
            if new_all_covered and self.last_all_covered is not True:
                try:
                    send_telegram("✅ All qualifying positions have exit orders in place.")
                except Exception:
                    pass
                self.logger.info("All qualifying positions have exit orders in place.")
            self.last_all_covered = new_all_covered
                
        except Exception as e:
            self.logger.error(f"Error checking positions: {e}", exc_info=True)
    
    async def _place_exit_orders(self, position: Dict, resume_pending: bool = False) -> bool:
        """
        Place target and stop-loss orders for a position.
        
        Args:
            position: Position dict from Kite API
        """
        try:
            symbol = position["tradingsymbol"]
            quantity = int(position["quantity"])
            avg_price = position["average_price"]
            exchange = position["exchange"]
            product = position.get("product", "NRML")
            pos_key = self._position_key(position)
            
            if not self.enable_auto_exit:
                self.logger.info(f"Auto-exit disabled, skipping {symbol}")
                return False

            # Skip low-price entries (likely hedge OTM options)
            if avg_price <= self.min_entry_price:
                self.logger.info(
                    f"Skipping {symbol}: entry ₹{avg_price} <= min_entry_price ₹{self.min_entry_price}"
                )
                return False
            
            # Calculate exit price (target only) and snap to valid tick size
            target_raw = avg_price + self.target_points
            tick = 0.05 if exchange == "NFO" else 0.05  # default tick
            # Snap to nearest tick and 2 decimals
            target_steps = round(target_raw / tick)
            target_price = round(target_steps * tick, 2)
            
            # Display the actual position entry (prefer buy_price if present, else average_price)
            try:
                raw_buy_price = position.get("buy_price")
                if raw_buy_price is not None:
                    display_entry = round(float(raw_buy_price), 2)
                else:
                    display_entry = round(float(avg_price), 2)
            except Exception:
                display_entry = round(float(avg_price), 2)
            self.logger.info(f"Placing target exit for {symbol}: Entry={display_entry}, Target={target_price}")
            
            if self.paper_mode:
                # Paper mode: just log and notify
                msg = (
                    f"📊 <b>Paper Mode Exit Orders</b>\n\n"
                    f"Symbol: {symbol}\n"
                    f"Qty: {quantity}\n"
                    f"Entry: ₹{display_entry}\n"
                    f"🎯 Target: ₹{target_price} (+{self.target_points})"
                )
                send_telegram(msg)
                self.logger.info(f"Paper mode: Would place exits for {symbol}")
            else:
                # Live mode: place actual orders
                from utils.config import get_section as _get_section
                cfg = _get_section("EXIT_STRATEGY")
                max_per_order = int(cfg.get("max_order_quantity", 1800))
                remaining = int(self.pending_exits.get(pos_key, quantity))
                placed_orders = []
                slices_attempted = 0
                slices_placed = 0
                while remaining > 0:
                    slice_qty = min(remaining, max_per_order)
                    slices_attempted += 1
                    self.logger.info(f"Placing target exit for {symbol}: Entry={display_entry}, Target={target_price}")
                    try:
                        target_order = await asyncio.to_thread(
                            self.kite_helper.kite.place_order,
                            variety="regular",
                            exchange=exchange,
                            tradingsymbol=symbol,
                            transaction_type="SELL",
                            quantity=slice_qty,
                            product=product,
                            order_type="LIMIT",
                            price=target_price,
                        )
                        placed_orders.append(target_order)
                        slices_placed += 1
                        self.logger.info(
                            f"Placed target exit slice for {symbol}: qty={slice_qty}, price={target_price}, order={target_order}"
                        )
                        remaining -= slice_qty
                    except Exception as slice_err:
                        # On failure, persist remaining and break to retry later
                        self.pending_exits[pos_key] = remaining
                        self.logger.error(
                            f"Slice failed for {symbol} qty={slice_qty}: {slice_err}. Remaining to exit later: {remaining}",
                            exc_info=True,
                        )
                        break

                # If fully exited, cleanup pending map
                if remaining <= 0 and pos_key in self.pending_exits:
                    del self.pending_exits[pos_key]

                # Notify summary
                if placed_orders:
                    msg = (
                        f"✅ <b>Exit Orders Placed</b>\n\n"
                        f"Symbol: {symbol}\n"
                        f"Qty: {quantity} (sliced <= {max_per_order})\n"
                        f"Entry: ₹{display_entry}\n"
                        f"🎯 Target: ₹{target_price} (Orders: {', '.join(map(str, placed_orders))})\n"
                        f"🧮 Placed slices: {slices_placed}/{slices_attempted}"
                    )
                    if pos_key in self.pending_exits:
                        msg += f"\n⏳ Pending remaining qty: {self.pending_exits[pos_key]}"
                    send_telegram(msg)
                else:
                    # No order placed at all; report and remember remaining
                    self.pending_exits[pos_key] = remaining
                    send_telegram(
                        f"❌ Could not place any exit slice for {symbol}. Will retry. Remaining qty: {remaining}"
                    )
            return True
                
        except Exception as e:
            self.logger.error(f"Error placing exit orders: {e}", exc_info=True)
            send_telegram(f"❌ Error placing exits for {position['tradingsymbol']}: {str(e)}")
            return False
