# 5EMA AutoTrader

An automated trading system built around the Five EMA (Exponential Moving Average) strategy for NIFTY index options. It integrates Zerodha Kite Connect API for market data and Telegram for trade alerts.

---

## Quick start

1) Activate the virtual environment

- VS Code ➝ Terminal ➝ New Terminal
- Run:

```
.\venv\Scripts\activate
```

2) Generate a fresh Kite access token (required daily)

- Run the helper and follow the prompt to complete browser login, then paste the request token:

```
python scripts\generate_token.py
```

- The script updates your `.env` automatically with the new `KITE_ACCESS_TOKEN`.

3) Health check

- Verifies environment, config, and basic API access:

```
python u_health_check.py
```

4) Backtest (optional)

- Set date range in `.env`:
	- `TEST_FROM_DATE=YYYY-MM-DD`
	- `TEST_TO_DATE=YYYY-MM-DD`
- Run the dual-mode harness:

```
python tests\test_strategy.py
```

5) Live notifications (Phase 1)

- Ensure Telegram keys are present in `.env` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`).
- Ensure `SELL.paper_mode` and `BUY.paper_mode` in `config.json` are `true` (no live orders in Phase 1).
- Start the concurrent SELL (5m) and BUY (15m) watchers:

```
python main.py
```

- Logs are written to `logs/strategy_sell.log` and `logs/strategy_buy.log`. Use Ctrl+C for graceful shutdown.

---

## Configuration and environment

- Secrets (.env) — Kite keys/tokens and Telegram credentials
- Strategy/system parameters — `config.json`

Central helpers (import from `utils.config`):

- `get_kite_credentials()` ➝ `{ "KITE_API_KEY", "KITE_API_SECRET", "KITE_ACCESS_TOKEN" }`
- `get_section(name)` ➝ Retrieves a section from `config.json` (e.g., `"SELL"`, `"BUY"`, `"SYSTEM"`)
- `get_env_var(key, default=None)` ➝ Safe env lookup

Notes:

- `SYSTEM.instrument_tokens` maps underlying labels (e.g., `"NIFTY 50"`) to instrument tokens
- `SYSTEM.warmup_days` controls historical window for EMA warm-up
- `SELL` (5m) and `BUY` (15m) run concurrently; adjust lots, gaps, and offsets per section

---

## Contributing and Git

When ready to persist changes:

```
git add .
git commit -m "Describe your change"
git push
```

See `helpdocs/GitCommands.txt` for more.

---

## Code examples

Kite credentials in code:

```py
from utils.config import get_kite_credentials

creds = get_kite_credentials()
api_key = creds.get("KITE_API_KEY")
access_token = creds.get("KITE_ACCESS_TOKEN")
```

Read a strategy section:

```py
from utils.config import get_section

cfg = get_section("SELL")
timeframe = cfg["timeframe"]
```
