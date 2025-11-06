# 5EMA AutoTrader - AI Agent Instructions

## Architecture Overview

This is an **automated options trading system** for NIFTY index options using the **Five EMA (5-period Exponential Moving Average)** strategy. The system integrates with **Zerodha Kite Connect API** for live trading and **Telegram** for notifications.

**Key architectural patterns:**
- **Dual-mode operation**: Runs SELL (5-min bearish) and BUY (15-min bullish) strategies concurrently using separate threads (`main.py`)
- **Centralized configuration**: All secrets in `.env`, strategy parameters in `config.json`
- **Paper vs Live trading**: Controlled via `config.json` `paper_mode` flag—paper trades log to `paper_trades.csv` at repo root
- **Nested project structure**: Main code lives in `5EMA_AutoTrader/5EMA_AutoTrader/` (note the duplication)

## Critical File Locations

```
5EMA_AutoTrader/5EMA_AutoTrader/   # ← Main codebase (note nested structure)
├── main.py                         # Entry point - runs dual-strategy threads
├── config.json                     # Strategy parameters (timeframes, lots, strikes)
├── .env                           # Secrets (API keys, tokens) - NEVER commit
├── paper_trades.csv               # Simulated trade log
├── strategies/
│   └── five_ema_strategy.py       # Core strategy logic (alert + entry detection)
├── utils/
│   ├── config.py                  # Centralized config/env loader (use get_section, get_kite_credentials)
│   ├── common.py                  # Project paths, logger setup
│   ├── kite_helper.py             # Kite API wrapper with rate limiting
│   ├── trade_manager.py           # Trade execution (paper/live switching)
│   └── notifier.py                # Telegram notifications
└── tests/
    └── test_strategy.py           # Backtesting harness (dual-mode historical testing)
```

## Configuration Pattern

**Always use centralized config helpers** to avoid hardcoded env reads:

```python
from utils.config import get_kite_credentials, get_section, get_env_var

# Load Kite credentials from .env
creds = get_kite_credentials()
api_key = creds["KITE_API_KEY"]

# Load strategy config from config.json
sell_cfg = get_section("SELL")
timeframe = sell_cfg["timeframe"]     # "5minute"
lots = sell_cfg["lots"]               # 1
```

**Why**: Prevents scattered `os.getenv()` calls and ensures `.env` is loaded consistently via `utils.common.load_env()`.

## Strategy Logic Flow

1. **Alert Candle Detection** (`identify_alert_candle`):
   - SELL mode: Close > EMA AND Low > EMA + gap_buffer (bearish setup)
   - BUY mode: Close < EMA AND High < EMA - gap_buffer (bullish setup)
   - Only one active alert at a time—replaced when new alert forms

2. **Entry Trigger** (`check_entry`):
   - SELL: Next candle's low breaks alert candle's low → SELL CALL entry
   - BUY: Next candle's high breaks alert candle's high → BUY PUT entry
   - Entry price includes `entry_offset_points` from config

3. **State Management**:
   - `active_alert`: Stores pending alert until entry or replacement
   - `_reset_state()`: Clears alert after entry—ready for next signal
   - State is instance-scoped (each thread has separate strategy instance)

## Developer Workflows

### Initial Setup
```powershell
# Activate virtual environment (ALWAYS first step)
.\venv\Scripts\activate

# Generate new Kite access token (daily requirement)
python scripts\generate_token.py
# Follow browser login, paste request token → updates .env automatically

# Verify system health
python u_health_check.py
```

### Running Live Trading
```powershell
python main.py  # Starts both SELL (5m) and BUY (15m) threads
# Logs: logs/strategy_sell.log, logs/strategy_buy.log
# Ctrl+C for graceful shutdown
```

### Backtesting
```powershell
# Configure in .env:
# TEST_FROM_DATE=2024-10-01
# TEST_TO_DATE=2024-10-31
python tests\test_strategy.py
```

### Debugging Tips
- Check `logs/strategy.log` for detailed candle-by-candle diagnostics
- Paper mode trades recorded in `paper_trades.csv` with entry/exit/PnL
- Telegram messages include suggested strikes using `otm_strike_distance` from config

## Project-Specific Conventions

### Logging Standards
- Use `utils.common.setup_logger(name, logfile)` for consistent formatting
- Log levels: DEBUG for candle data, INFO for alerts/entries, ERROR for failures
- All logs go to `5EMA_AutoTrader/logs/` (relative to nested structure)

### Kite API Patterns
- **Always use `KiteHelper` wrapper** (includes rate limiting via `@rate_limit` decorator)
- Rate limits: 10 LTP calls/sec, 5 orders/sec
- Instrument tokens defined in `config.json` SYSTEM section (NIFTY 50: 256265)
- Example: `kite_helper.get_ltp(256265)` returns float or None

### Trade Execution
- `TradeManager.enter_trade(symbol, qty, signal)` handles paper/live switching internally
- Validates symbol via LTP fetch before placing orders
- Paper mode: Generates `SIM_{timestamp}` order IDs
- Live mode: Uses Kite's NRML product type (no intraday squareoff)

### Error Handling
- Kite API errors trigger exponential backoff (5s → 300s max)
- Strategy threads auto-restart on crashes with backoff
- `TradeValidationError` for business logic errors vs generic `Exception` for system errors

## Integration Points

### Zerodha Kite Connect
- **Authentication**: Daily access token generation via `scripts/generate_token.py`
- **Market data**: Historical data via `kite.historical_data(token, from, to, interval)`
- **Order placement**: Only during market hours (9:15 AM - 3:30 PM IST)
- **Limitations**: 3 API errors → 300s backoff (see `KiteHelper._handle_api_error`)

### Telegram Notifications
- **Format**: Uses `utils.notifier.format_trade_message()` for consistent structure
- **Content**: Includes suggested option type (CALL/PUT), strike, underlying LTP, targets
- **Fallback**: Logs warning if bot token missing, doesn't crash execution

### Data Flow
```
Kite API → KiteHelper (rate limiting) → FiveEMAStrategy (signal detection) 
→ TradeManager (execution) → Notifier (alerts) + paper_trades.csv (logging)
```

## Testing Strategy

- `test_strategy.py` runs dual-mode backtests over date ranges from `.env`
- Requires `TEST_FROM_DATE` and `TEST_TO_DATE` in `YYYY-MM-DD` format
- Uses same `FiveEMAStrategy` class as live trading (no mocks)
- Chronological alert sequencing ensures realistic signal timing

## Common Pitfalls

1. **Forgetting to activate venv**: Always run `.\venv\Scripts\activate` before any Python command
2. **Expired access token**: Kite tokens expire daily—re-run `generate_token.py` if you get auth errors
3. **Wrong working directory**: Scripts assume CWD is `5EMA_AutoTrader/5EMA_AutoTrader/` (nested level)
4. **Config section typos**: Use exact keys: "SELL", "BUY", "SYSTEM" (case-sensitive)
5. **CSV column order**: `paper_trades.csv` expects exact column order from `TradeManager._init_paper_trades_file()`

## When Modifying Strategy Logic

- **EMA calculation**: Uses pandas `.ewm(span=5, adjust=False)` in `compute_ema()`
- **Gap buffer**: Configured per mode in `config.json` (default 1 point)
- **Risk-reward targets**: Calculated as multiples of (SL - Entry) distance
- **Candle indexing**: `df.iloc[-2]` is last *completed* candle, `df.iloc[-1]` is current/incomplete

## Git Workflow

Commands reference: See `helpdocs/GitCommands.txt`. Standard workflow:
```powershell
git add .
git commit -m "descriptive message"
git push
```

Remember: `.env` is gitignored—never commit secrets. Share `.env.example` for team onboarding.
