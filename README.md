# AutoExit - Automated Position Exit Bot for Zerodha Kite

## Overview

**AutoExit** is an automated trading bot that monitors open long positions in Zerodha Kite and automatically places target and stop-loss exit orders. Features real-time Telegram commands for dynamic control.

### Key Features
- ✅ Continuous position monitoring via Kite Connect API
- 🎯 Automatic target and stop-loss order placement
- 📱 Telegram bot with command interface
- ⚙️ Dynamic configuration (adjust target/SL on the fly)
- 🔄 Auto-restart supervisor for 24/7 operation
- 📝 Paper trading mode for testing
- 🛡️ Graceful error handling and retry logic

## Architecture

```
Position Monitoring Loop ──┬──> Detect New Long Positions
                           │
                           ├──> Calculate Target/SL Prices
                           │
                           └──> Place Exit Orders (Paper/Live)

Telegram Bot ──────────────────> Commands: /pause /resume /settarget /setsl /status
```

### Components
- **Position Monitor** (`strategies/position_monitor.py`): Async position polling and exit order placement
- **Telegram Bot** (`telegram_bot.py`): Command handler for user control
- **Main Coordinator** (`main.py`): Runs both components concurrently
- **Supervisor** (`supervisor.sh`): Auto-restart wrapper for production

## Requirements

- Python 3.10+
- Zerodha Kite Connect API account
- Telegram bot token
- Ubuntu 22.04 LTS (for production deployment on AWS EC2)

## Setup

### 1. Local Development (Windows)

```powershell
# Clone and navigate
cd D:\Work\AI\AutoExit

# Create virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install dependencies
cd AutoExit
pip install -r requirements.txt
```

### 2. AWS EC2 Deployment (Ubuntu)

```bash
# Clone repo
cd ~
git clone git@github.com:your-username/AutoExit.git
cd AutoExit

# Create venv
python3 -m venv venv
source venv/bin/activate

# Install dependencies (Linux-safe)
cd AutoExit
sed '/^pywin32/d' requirements.txt > requirements-linux.txt
pip install -r requirements-linux.txt
```

### 3. Configuration

Create `.env` in the nested `AutoExit/` folder:

```bash
KITE_API_KEY=your_kite_api_key
KITE_API_SECRET=your_kite_api_secret
KITE_ACCESS_TOKEN=
REDIRECT_URL=https://127.0.0.1

TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

Edit `config.json`:

```json
{
  "SYSTEM": {
    "poll_interval_seconds": 10,
    "max_api_retries": 3,
    "retry_backoff_seconds": 5,
    "log_level": "INFO"
  },
  "EXIT_STRATEGY": {
    "target_points": 50,
    "stoploss_points": 30,
    "product_type": "NRML",
    "order_variety": "regular",
    "enable_auto_exit": true,
    "paper_mode": true
  },
  "TELEGRAM": {
    "enable_commands": true,
    "admin_user_ids": []
  }
}
```

### 4. Daily Token Refresh

Kite access tokens expire daily:

```bash
source ../venv/bin/activate
python -m scripts.generate_token
# Open login URL, authorize, paste request_token
```

### 5. Health Check

```bash
python u_health_check.py
```

Expected output:
- ✅ Kite API connection successful
- ✅ Telegram alert sent successfully

## Usage

### Run Directly (Foreground)

```bash
source ../venv/bin/activate
python main.py
```

### Run with Supervisor (Background, Auto-restart)

```bash
chmod +x supervisor.sh
./supervisor.sh
```

Supervisor will:
- Start the bot in background with nohup
- Restart automatically if it crashes
- Write logs to `logs/bot.log`
- Maintain PID file for process tracking

To stop:
```bash
kill $(cat autoexit.pid)
```

### Run as systemd Service (Recommended for Production)

Create `/etc/systemd/system/autoexit.service`:

```ini
[Unit]
Description=AutoExit Position Manager
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/AutoExit/AutoExit
ExecStart=/home/ubuntu/AutoExit/venv/bin/python /home/ubuntu/AutoExit/AutoExit/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now autoexit
sudo systemctl status autoexit
journalctl -u autoexit -f
```

## Telegram Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/pause` | Pause position monitoring | `/pause` |
| `/resume` | Resume monitoring | `/resume` |
| `/settarget <points>` | Update target profit | `/settarget 60` |
| `/setsl <points>` | Update stop-loss | `/setsl 40` |
| `/status` | Show bot status | `/status` |
| `/help` | Command list | `/help` |

## Configuration Reference

### SYSTEM
- `poll_interval_seconds`: How often to check positions (default: 10)
- `max_api_retries`: Max retries on API failure (default: 3)
- `retry_backoff_seconds`: Delay between retries (default: 5)
- `log_level`: Logging verbosity (INFO, DEBUG, WARNING, ERROR)

### EXIT_STRATEGY
- `target_points`: Points above entry for target order
- `stoploss_points`: Points below entry for SL order
- `product_type`: Order product type (NRML, MIS, CNC)
- `order_variety`: Order variety (regular, amo, co, iceberg)
- `enable_auto_exit`: Enable/disable automatic exit orders
- `paper_mode`: If true, only log exits without placing orders

### TELEGRAM
- `enable_commands`: Enable Telegram bot commands
- `admin_user_ids`: List of authorized Telegram user IDs (empty = use chat_id from .env)

## Operational Workflow

### Daily Startup (EC2)
```bash
# 1. SSH into EC2
ssh -i your-key.pem ubuntu@your-ec2-ip

# 2. Refresh Kite token
cd ~/AutoExit/AutoExit
source ../venv/bin/activate
python -m scripts.generate_token

# 3. Verify health
python u_health_check.py

# 4. Start/restart service
sudo systemctl restart autoexit
sudo systemctl status autoexit
```

### Monitoring
```bash
# Live logs
journalctl -u autoexit -f

# Or if using supervisor
tail -f logs/bot.log

# Telegram status
# Send /status command to bot
```

### Switching to Live Mode

1. Test thoroughly in paper mode first
2. Edit `config.json`:
   ```json
   "paper_mode": false
   ```
3. Restart the bot:
   ```bash
   sudo systemctl restart autoexit
   ```
4. Verify via `/status` that mode is LIVE

## Development

### Project Structure
```
AutoExit/AutoExit/
├── main.py                    # Entry point & coordinator
├── telegram_bot.py            # Telegram command handler
├── config.json                # Configuration
├── .env                       # Secrets (gitignored)
├── supervisor.sh              # Auto-restart script
├── strategies/
│   └── position_monitor.py    # Position polling & exit logic
├── utils/
│   ├── common.py             # Logger, paths
│   ├── config.py             # Config loader
│   ├── kite_helper.py        # Kite API wrapper
│   ├── notifier.py           # Telegram notifications
│   └── trade_manager.py      # Trade execution (future)
├── scripts/
│   └── generate_token.py     # Daily token refresh
└── logs/
    ├── autoexit.log          # Application logs
    └── bot.log               # Supervisor logs
```

### Adding New Features

**Example: Add trailing stop-loss**

1. Update `config.json` with trailing_sl config
2. Modify `PositionMonitor._check_positions()` to track price movement
3. Add `/settrailing` command in `TelegramBotHandler`
4. Test in paper mode
5. Deploy to EC2

### Testing

```bash
# Paper mode testing
python main.py

# Send test commands via Telegram
/status
/settarget 100
/setsl 50
/pause
/resume
```

## Security

- ✅ `.env` is gitignored—never commit secrets
- ✅ Telegram commands check authorization (admin_user_ids or chat_id)
- ✅ Use paper mode before live trading
- ✅ Keep EC2 security group SSH restricted to your IP
- ✅ Rotate Kite API keys if exposed

## Troubleshooting

### Bot not starting
```bash
# Check logs
journalctl -u autoexit -n 50 --no-pager

# Verify Python/venv path
which python3
ls -l /home/ubuntu/AutoExit/venv/bin/python

# Test manually
source venv/bin/activate
python main.py
```

### Kite API errors
```bash
# Regenerate token
python -m scripts.generate_token

# Verify credentials in .env
cat .env | grep KITE
```

### Telegram not responding
```bash
# Check bot token and chat ID
python -c "from utils.config import get_env_var; print(get_env_var('TELEGRAM_BOT_TOKEN'))"

# Test with health check
python u_health_check.py
```

### Exit orders not placed
- Check `paper_mode` in config.json (should be false for live)
- Check `enable_auto_exit` is true
- Verify sufficient margin/balance in Kite account
- Check logs for API errors

## License

Private project - not for public distribution.

## Support

For issues or questions, check:
1. Application logs: `logs/autoexit.log`
2. Supervisor logs: `logs/bot.log`
3. Systemd logs: `journalctl -u autoexit -f`
4. Telegram bot status: `/status` command
