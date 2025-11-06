import os
import csv
from typing import Optional, Dict, Union, List
import logging
import time
from datetime import datetime
from pathlib import Path

class TradeValidationError(Exception):
    """Custom exception for trade validation failures."""
    pass

class TradeManager:
    """Manages trade execution and tracking for both live and paper trading."""
    
    VALID_SIDES = ["BUY", "SELL"]
    
    def __init__(self, kite_helper, paper_mode: bool = False):
        """Initialize TradeManager.
        
        Args:
            kite_helper: Instance of KiteHelper for API interactions
            paper_mode: If True, simulates trades instead of real execution
            
        Raises:
            ValueError: If kite_helper is None
        """
        if not kite_helper:
            raise ValueError("KiteHelper instance is required")
            
        self.kite = kite_helper
        self.paper_mode = paper_mode
        self.logger = logging.getLogger(__name__)
        
        # Setup paper trading file (placed at repo root)
        self.paper_trades_file = (Path(__file__).resolve().parent.parent / "paper_trades.csv")
        self._init_paper_trades_file()

        self.logger.info(f"TradeManager initialized (Paper Mode = {self.paper_mode})")
        
    def _format_ctx(self, symbol: Optional[str] = None,
                    order_id: Optional[str] = None,
                    qty: Optional[int] = None,
                    side: Optional[str] = None) -> str:
        """Return a compact context string for logging."""
        parts: List[str] = []
        if symbol:
            parts.append(f"symbol={symbol}")
        if order_id:
            parts.append(f"order_id={order_id}")
        if qty is not None:
            parts.append(f"qty={qty}")
        if side:
            parts.append(f"side={side}")
        return " | " + " ".join(parts) if parts else ""
        
    def _init_paper_trades_file(self) -> None:
        """Initialize paper trades CSV file with headers if it doesn't exist."""
        if not self.paper_trades_file.exists():
            self.paper_trades_file.parent.mkdir(parents=True, exist_ok=True)
            fieldnames = [
                "timestamp", "symbol", "side", "entry_price", "exit_price",
                "qty", "pnl", "status", "rr_stage"
            ]
            with self.paper_trades_file.open(mode="w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

    def _validate_trade_params(self, symbol: str, qty: int, side: str) -> None:
        """Validate trade parameters before execution.
        
        Args:
            symbol: Trading symbol
            qty: Trade quantity
            side: Trade direction (BUY/SELL)
            
        Raises:
            TradeValidationError: If any parameter is invalid
        """
        if not symbol or not symbol.strip():
            raise TradeValidationError("Symbol cannot be empty")
            
        if not isinstance(qty, int) or qty <= 0:
            raise TradeValidationError("Quantity must be a positive integer")
            
        if side.upper() not in self.VALID_SIDES:
            raise TradeValidationError(f"Invalid side '{side}'. Must be one of {self.VALID_SIDES}")

    def enter_trade(self, symbol: str, qty: int, signal: str) -> Optional[str]:
        """Enter a new trade position.
        
        Args:
            symbol: Trading symbol (e.g., "NIFTY25NOV17500CE")
            qty: Trade quantity
            signal: Trade signal ("BUY"/"SELL")
            
        Returns:
            str: Order ID if successful (or simulated ID in paper mode), None if failed
            
        Raises:
            TradeValidationError: If trade parameters are invalid
        """
        try:
            # Normalize and validate inputs
            symbol = symbol.strip()
            signal = signal.upper()
            self._validate_trade_params(symbol, qty, signal)
            
            # Check if symbol exists and get price
            entry_price = self.kite.get_ltp(f"NFO:{symbol}")
            if entry_price is None:
                raise TradeValidationError(f"Could not fetch price for {symbol}")
            
            if self.paper_mode:
                order_id = f"SIM_{int(time.time())}"
                self.logger.info(
                    f"[PAPER] Opening {signal} {symbol} @ {entry_price:.2f}" +
                    self._format_ctx(symbol=symbol, qty=qty, side=signal)
                )
                self._record_paper_trade(symbol, signal, entry_price, qty)
                self.logger.debug(f"Simulated order id={order_id}" + self._format_ctx(order_id=order_id))
                return order_id
                
            else:
                # Place real trade
                order_id = self.kite.place_order(
                    tradingsymbol=symbol,
                    transaction_type=signal,
                    quantity=qty,
                    order_type="MARKET",
                    product="NRML"
                )
                
                if not order_id:
                    raise TradeValidationError("Order placement failed")

                self.logger.info(
                    f"[LIVE] Opened {signal} {symbol} @ {entry_price:.2f}" +
                    self._format_ctx(symbol=symbol, qty=qty, side=signal, order_id=order_id)
                )
                return order_id

        except TradeValidationError as e:
            self.logger.error(f"Trade validation failed: {str(e)}" + self._format_ctx(symbol=symbol if 'symbol' in locals() else None))
            raise

        except Exception as e:
            self.logger.exception(f"Error entering trade{self._format_ctx(symbol=symbol if 'symbol' in locals() else None)}")
            return None

    def exit_trade(self, symbol: str, rr_stage: Optional[str] = None) -> bool:
        """Exit an existing trade position.
        
        Args:
            symbol: Trading symbol to exit
            rr_stage: Optional risk/reward stage at exit
            
        Returns:
            bool: True if exit was successful, False otherwise
            
        Raises:
            TradeValidationError: If symbol is invalid or no position exists
        """
        try:
            symbol = symbol.strip()
            if not symbol:
                raise TradeValidationError("Symbol cannot be empty")
            
            # Get current price
            exit_price = self.kite.get_ltp(f"NFO:{symbol}")
            if exit_price is None:
                raise TradeValidationError(f"Could not fetch price for {symbol}")
            
            if self.paper_mode:
                self.logger.info(f"[PAPER] Closing {symbol} @ {exit_price:.2f}" + self._format_ctx(symbol=symbol))
                return self._update_paper_trade(symbol, exit_price, rr_stage)
            else:
                success = self.kite.exit_all_positions()
                if success:
                    self.logger.info(f"[LIVE] Closed {symbol} @ {exit_price:.2f}" + self._format_ctx(symbol=symbol))
                return success

        except TradeValidationError as e:
            self.logger.error(f"Trade exit validation failed: {str(e)}" + self._format_ctx(symbol=symbol if 'symbol' in locals() else None))
            raise

        except Exception as e:
            self.logger.exception(f"Error exiting trade{self._format_ctx(symbol=symbol if 'symbol' in locals() else None)}")
            return False

    def _record_paper_trade(self, symbol: str, side: str, entry_price: float, qty: int) -> bool:
        """Record a new paper trade entry.
        
        Args:
            symbol: Trading symbol
            side: Trade direction (BUY/SELL)
            entry_price: Entry price
            qty: Trade quantity
            
        Returns:
            bool: True if recorded successfully, False otherwise
        """
        try:
            fieldnames = [
                "timestamp", "symbol", "side", "entry_price", "exit_price",
                "qty", "pnl", "status", "rr_stage"
            ]
            with self.paper_trades_file.open(mode="a", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writerow({
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "symbol": symbol,
                    "side": side,
                    "entry_price": f"{entry_price:.2f}",
                    "exit_price": "",
                    "qty": str(qty),
                    "pnl": "",
                    "status": "OPEN",
                    "rr_stage": ""
                })
            self.logger.debug("Recorded paper trade" + self._format_ctx(symbol=symbol, qty=qty, side=side))
            return True

        except Exception as e:
            self.logger.exception("Error recording paper trade" + self._format_ctx(symbol=symbol if 'symbol' in locals() else None))
            return False

    def _update_paper_trade(self, symbol: str, exit_price: float, 
                          rr_stage: Optional[str] = None) -> bool:
        """Update an existing paper trade with exit information.
        
        Args:
            symbol: Trading symbol
            exit_price: Exit price
            rr_stage: Optional risk/reward stage at exit
            
        Returns:
            bool: True if updated successfully, False otherwise
            
        Raises:
            TradeValidationError: If no open trade exists for the symbol
        """
        try:
            # Read existing trades
            with self.paper_trades_file.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            if not rows:
                raise TradeValidationError("No trades recorded")

            # Find the last open trade for this symbol
            trade_found = False
            for row in reversed(rows):
                if row.get("symbol") == symbol and row.get("status") == "OPEN":
                    trade_found = True
                    entry_price = float(row.get("entry_price") or 0)
                    qty = int(row.get("qty") or 0)
                    side = row.get("side")

                    # Calculate PnL correctly for BUY/SELL
                    if side == "SELL":
                        pnl = (entry_price - exit_price) * qty
                    else:
                        pnl = (exit_price - entry_price) * qty

                    # Update trade record (store formatted strings)
                    row["exit_price"] = f"{exit_price:.2f}"
                    row["pnl"] = f"{pnl:.2f}"
                    row["status"] = "CLOSED"
                    row["rr_stage"] = rr_stage or ""
                    self.logger.info("Closed paper trade" + self._format_ctx(symbol=symbol, qty=qty, side=side) + f" pnl={pnl:.2f}")
                    break

            if not trade_found:
                raise TradeValidationError(f"No open trade found for {symbol}")

            # Write updated data back to CSV
            fieldnames = [
                "timestamp", "symbol", "side", "entry_price", "exit_price",
                "qty", "pnl", "status", "rr_stage"
            ]
            with self.paper_trades_file.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            return True

        except TradeValidationError:
            # Let callers handle validation errors
            raise

        except Exception as e:
            self.logger.error(f"Error updating paper trade: {str(e)}")
            return False

    # ---------------------------------------------------------------------
    # Summary Report (Optional)
    # ---------------------------------------------------------------------
    def daily_summary(self):
        """Print daily summary of simulated trades."""
        if not self.paper_trades_file.exists():
            logging.info("No paper trades yet.")
            return

        df = None
        try:
            import pandas as pd
            df = pd.read_csv(self.paper_trades_file)
            df["pnl"] = pd.to_numeric(df["pnl"], errors="coerce").fillna(0)
            today = datetime.now().strftime("%Y-%m-%d")
            today_df = df[df["timestamp"].str.startswith(today)]

            if len(today_df) == 0:
                logging.info("No trades today.")
                return

            total_trades = len(today_df)
            wins = len(today_df[today_df["pnl"] > 0])
            losses = len(today_df[today_df["pnl"] < 0])
            gross_pnl = today_df["pnl"].sum()

            logging.info("─────────────── 📅 PAPER TRADES SUMMARY ───────────────")
            logging.info(f"Total Trades: {total_trades}")
            logging.info(f"Wins: {wins} | Losses: {losses}")
            logging.info(f"Gross P/L: ₹{gross_pnl:.2f}")
            logging.info("───────────────────────────────────────────────────────")
        except Exception as e:
            logging.error(f"Error generating summary: {e}")
