# Crypto Trading Bot

Automated trading bot using Grid and DCA strategies for BTC, ETH, and SOL on Kraken.

## Features

- **Grid Trading**: Places buy orders below and sell orders above current price, profiting from sideways movement
- **DCA (Dollar Cost Averaging)**: Scheduled buys + extra buys on price drops
- **Risk Management**: Position sizing, drawdown limits, daily loss limits
- **Paper Trading**: Test strategies without real money
- **State Persistence**: Survives restarts, tracks all trades

## Quick Start

### 1. Install dependencies

```bash
cd /home/ariana/project
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure API keys

```bash
cp .env.example .env
# Edit .env with your Kraken API credentials
```

Get API keys from: https://www.kraken.com/u/security/api

**Important**: Only enable "Query" and "Trade" permissions. Do NOT enable "Withdraw".

### 3. Run in paper trading mode (default)

```bash
python run.py
```

### 4. Go live (when ready)

Edit `.env`:
```
PAPER_TRADING=false
```

## Configuration

Edit `src/config.py` to adjust:

### Grid Strategy
- `num_grids`: Number of price levels (default: 10)
- `upper_price_pct`: How far above current price (default: 5%)
- `lower_price_pct`: How far below current price (default: 5%)
- `allocation_pct`: Portfolio % to allocate (default: 30%)

### DCA Strategy
- `buy_interval_hours`: Time between buys (default: 24h)
- `buy_amount_pct`: Portfolio % per buy (default: 2%)
- `price_drop_trigger_pct`: Extra buy trigger (default: 3% drop)
- `max_buys_per_day`: Daily buy limit (default: 3)

### Risk Management
- `max_risk_per_trade_pct`: Max risk per trade (default: 2%)
- `max_drawdown_pct`: Pause trading threshold (default: 10%)
- `stop_loss_pct`: Per-trade stop loss (default: 3%)
- `daily_loss_limit_pct`: Daily loss limit (default: 5%)

## Monitoring

### Logs
- `logs/bot_YYYYMMDD.log` - All bot activity
- `logs/trades_YYYYMMDD.log` - Trade-specific logs

### Database
- `trading_bot.db` - SQLite database with:
  - Order history
  - Trade history
  - Portfolio snapshots
  - Strategy state

### Check performance
```python
from src.database import get_performance_stats
stats = get_performance_stats(days=30)
print(stats)
```

## Architecture

```
src/
  bot.py        - Main orchestrator
  config.py     - Configuration
  exchange.py   - Kraken API connector (via ccxt)
  risk.py       - Risk management
  database.py   - SQLite persistence
  logger.py     - Logging setup
  strategies/
    base.py     - Strategy interface
    grid.py     - Grid trading
    dca.py      - Dollar cost averaging
```

## Safety Features

1. **Paper trading by default** - Test before risking real money
2. **No withdrawal API access** - Bot can't move funds out
3. **Drawdown pause** - Stops trading if losses exceed 10%
4. **Daily loss limit** - Stops trading if daily losses exceed 5%
5. **Position size limits** - Max 2% risk per trade
6. **State persistence** - Recovers from crashes

## Disclaimer

This bot is for educational purposes. Trading cryptocurrency involves significant risk. You can lose money. Past performance does not guarantee future results. Use at your own risk.
