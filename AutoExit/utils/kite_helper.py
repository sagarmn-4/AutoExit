# utils/kite_helper.py

from typing import Optional, Dict, List, Union, Any
from kiteconnect import KiteConnect
from kiteconnect.exceptions import KiteException, NetworkException
import json
import logging
import time
from functools import wraps
from datetime import datetime, timedelta
from .config import get_kite_credentials

# Rate limiting decorator
def rate_limit(calls: int, period: int):
    """Rate limiting decorator to prevent API throttling.
    
    Args:
        calls (int): Number of calls allowed
        period (int): Time period in seconds
    """
    def decorator(func):
        timestamps: List[float] = []
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            now = time.time()
            timestamps[:] = [t for t in timestamps if t > now - period]
            
            if len(timestamps) >= calls:
                sleep_time = timestamps[0] - (now - period)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
            timestamps.append(now)
            return func(*args, **kwargs)
        return wrapper
    return decorator

class KiteHelper:
    """Helper class for Kite Connect API operations with enhanced error handling and rate limiting."""
    
    def __init__(self, KITE_API_KEY: str, KITE_ACCESS_TOKEN: str):
        """Initialize KiteHelper with API credentials.
        
        Args:
            KITE_API_KEY (str): Kite API key
            KITE_ACCESS_TOKEN (str): Kite access token
        
        Raises:
            ValueError: If API credentials are invalid
        """
        if not KITE_API_KEY or not KITE_ACCESS_TOKEN:
            raise ValueError("Invalid API credentials")
            
        self.KITE_API_KEY = KITE_API_KEY
        self.KITE_ACCESS_TOKEN = KITE_ACCESS_TOKEN
        self.kite = KiteConnect(api_key=self.KITE_API_KEY)
        self.kite.set_access_token(self.KITE_ACCESS_TOKEN)
        self._last_error_time = None
        self._error_count = 0
        self._instruments_cache = {}
        
        # Configure logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

    @classmethod
    def from_env(cls):
        """Create a KiteHelper instance using credentials from environment (.env).

        This centralizes credential lookup and avoids ad-hoc env reads elsewhere.
        """
        creds = get_kite_credentials()
        return cls(creds.get("KITE_API_KEY"), creds.get("KITE_ACCESS_TOKEN"))

    def _handle_api_error(self, error: Exception, context: str) -> None:
        """Handle API errors with exponential backoff.
        
        Args:
            error: The exception that occurred
            context: Description of what operation was being performed
        """
        now = datetime.now()
        
        # Reset error count if last error was more than 5 minutes ago
        if self._last_error_time and (now - self._last_error_time) > timedelta(minutes=5):
            self._error_count = 0
            
        self._error_count += 1
        self._last_error_time = now
        
        # Calculate backoff time (exponential with max of 5 minutes)
        backoff = min(300, 2 ** self._error_count)
        
        self.logger.error(f"{context} failed: {str(error)}")
        self.logger.info(f"Backing off for {backoff} seconds")
        time.sleep(backoff)

    @rate_limit(calls=10, period=1)  # Max 10 calls per second
    def get_ltp(self, instrument_token: Union[int, str]) -> Optional[float]:
        """Fetch Last Traded Price for given instrument.
        
        Args:
            instrument_token: Instrument token or symbol
            
        Returns:
            float: Last traded price if successful, None if failed
            
        Example:
            >>> kite_helper.get_ltp("NSE:NIFTY50")
            17500.45
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                data = self.kite.ltp(instrument_token)
                if not data or str(instrument_token) not in data:
                    raise ValueError("Invalid response from Kite API")
                return data[str(instrument_token)]["last_price"]
                
            except (KiteException, NetworkException) as e:
                self._handle_api_error(e, f"LTP fetch attempt {attempt + 1}")
                if attempt == max_retries - 1:
                    self.logger.error(f"All retries failed for LTP fetch: {str(e)}")
                    return None
                    
            except Exception as e:
                self.logger.error(f"Unexpected error fetching LTP: {str(e)}")
                return None

    @rate_limit(calls=5, period=1)  # Max 5 orders per second
    def place_order(self, tradingsymbol: str, qty: int, transaction_type: str, 
                   order_type: str = "MARKET", product: str = "NRML", 
                   variety: str = "regular") -> Optional[str]:
        """Place a trading order.
        
        Args:
            tradingsymbol: Trading symbol (e.g., "NIFTY25NOV17500CE")
            qty: Order quantity
            transaction_type: "BUY" or "SELL"
            order_type: "MARKET", "LIMIT", etc.
            product: "NRML", "MIS", etc.
            variety: "regular", "amo", etc.
            
        Returns:
            str: Order ID if successful, None if failed
            
        Example:
            >>> kite_helper.place_order("NIFTY25NOV17500CE", 75, "BUY")
            "151220400000000"
        """
        # Validate inputs
        if not tradingsymbol or not isinstance(qty, int) or qty <= 0:
            raise ValueError("Invalid order parameters")
            
        if transaction_type not in ["BUY", "SELL"]:
            raise ValueError("Invalid transaction type")
            
        max_retries = 2  # Fewer retries for orders to avoid duplicates
        for attempt in range(max_retries):
            try:
                order_id = self.kite.place_order(
                    variety=variety,
                    tradingsymbol=tradingsymbol,
                    exchange="NFO",
                    transaction_type=transaction_type,
                    quantity=qty,
                    order_type=order_type,
                    product=product
                )
                self.logger.info(f"Order placed successfully: {order_id}")
                return order_id
                
            except (KiteException, NetworkException) as e:
                self._handle_api_error(e, f"Order placement attempt {attempt + 1}")
                if attempt == max_retries - 1:
                    self.logger.error(f"All retries failed for order placement: {str(e)}")
                    return None
                    
            except Exception as e:
                self.logger.error(f"Unexpected error placing order: {str(e)}")
                return None

    @rate_limit(calls=5, period=1)
    def get_positions(self) -> Optional[Dict[str, List[Dict[str, Any]]]]:
        """Get all open positions.
        
        Returns:
            Dict containing day and net positions if successful, None if failed
            
        Example:
            >>> positions = kite_helper.get_positions()
            >>> if positions:
            >>>     print(f"Net positions: {len(positions['net'])}")
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                positions = self.kite.positions()
                if not isinstance(positions, dict):
                    raise ValueError("Invalid response format from Kite API")
                return positions
                
            except (KiteException, NetworkException) as e:
                self._handle_api_error(e, f"Position fetch attempt {attempt + 1}")
                if attempt == max_retries - 1:
                    self.logger.error(f"All retries failed for position fetch: {str(e)}")
                    return None
                    
            except Exception as e:
                self.logger.error(f"Unexpected error fetching positions: {str(e)}")
                return None

    def check_connection(self) -> bool:
        """Check if the connection to Kite API is working.
        
        Returns:
            bool: True if connection is working, False otherwise
        """
        try:
            _ = self.kite.margins()
            return True
        except Exception:
            return False

    # ───────────────────────────────
    # Instruments & Options helpers
    # ───────────────────────────────
    def get_instruments(self, exchange: str = "NFO") -> Optional[List[Dict[str, Any]]]:
        """Return and cache instruments for an exchange (defaults to NFO).

        Caches results in-memory to avoid repeated large downloads during a run.
        """
        try:
            if exchange in self._instruments_cache:
                return self._instruments_cache[exchange]
            data = self.kite.instruments(exchange)
            if isinstance(data, list):
                self._instruments_cache[exchange] = data
                return data
            return None
        except Exception as e:
            self.logger.error(f"Failed to fetch instruments for {exchange}: {e}")
            return None

    def _map_underlying_name(self, label: str) -> str:
        """Map config label (e.g., 'NIFTY 50') to Kite 'name' in instruments (e.g., 'NIFTY')."""
        mapping = {
            "NIFTY 50": "NIFTY",
            "BANKNIFTY": "BANKNIFTY",
            "FINNIFTY": "FINNIFTY",
        }
        # Default to removing spaces
        return mapping.get(label.upper(), label.replace(" ", "").upper())

    def resolve_option_token(self, underlying_label: str, entry_dt: datetime, strike: int, option_type: str) -> Optional[int]:
        """Resolve the instrument_token for an index option given inputs.

        Chooses the nearest expiry on or after entry_dt.
        option_type: 'CALL'/'PUT' or 'CE'/'PE'
        """
        try:
            opt_type = option_type.upper()
            opt_type = "CE" if opt_type in ("CALL", "CE") else "PE"
            name = self._map_underlying_name(underlying_label)
            instruments = self.get_instruments("NFO")
            if not instruments:
                return None

            # Filter candidates
            candidates: List[Dict[str, Any]] = []
            for inst in instruments:
                try:
                    if inst.get("segment") != "NFO-OPT":
                        continue
                    if inst.get("exchange") != "NFO":
                        continue
                    if inst.get("name") != name:
                        continue
                    if int(inst.get("strike", 0)) != int(strike):
                        continue
                    if inst.get("instrument_type") != opt_type:
                        continue
                    expiry = inst.get("expiry")
                    # expiry comes as datetime
                    if not expiry:
                        continue
                    if isinstance(expiry, str):
                        try:
                            expiry = datetime.fromisoformat(expiry)
                        except Exception:
                            continue
                    if expiry.date() >= entry_dt.date():
                        candidates.append(inst)
                except Exception:
                    continue

            if not candidates:
                return None

            # Pick the nearest expiry
            candidates.sort(key=lambda x: x.get("expiry"))
            return int(candidates[0]["instrument_token"]) if "instrument_token" in candidates[0] else None
        except Exception as e:
            self.logger.error(f"resolve_option_token failed: {e}")
            return None

    def get_option_ltp(self, underlying_label: str, entry_dt: datetime, strike: int, option_type: str) -> Optional[float]:
        """Convenience method to fetch option LTP for given parameters."""
        try:
            token = self.resolve_option_token(underlying_label, entry_dt, strike, option_type)
            if token is None:
                return None
            return self.get_ltp(token)
        except Exception as e:
            self.logger.error(f"get_option_ltp failed: {e}")
            return None

    def exit_all_positions(self) -> bool:
        """Exit all open positions.
        
        Returns:
            bool: True if all positions were closed successfully, False otherwise
            
        Example:
            >>> success = kite_helper.exit_all_positions()
            >>> if success:
            >>>     print("All positions closed")
        """
        try:
            positions = self.get_positions()
            if not positions:
                return False

            success = True
            for pos in positions["net"]:
                if pos["quantity"] != 0:
                    transaction_type = "SELL" if pos["quantity"] > 0 else "BUY"
                    order_id = self.place_order(
                        tradingsymbol=pos["tradingsymbol"],
                        qty=abs(pos["quantity"]),
                        transaction_type=transaction_type
                    )
                    if not order_id:
                        success = False
                        self.logger.error(f"Failed to exit position: {pos['tradingsymbol']}")
                        
            if success:
                self.logger.info("✅ All open positions exited successfully")
            return success
            
        except Exception as e:
            self.logger.error(f"Error in exit_all_positions: {str(e)}")
            return False
