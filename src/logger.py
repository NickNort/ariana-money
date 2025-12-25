import logging
import sys
from datetime import datetime
from pathlib import Path


LOG_DIR = Path(__file__).parent.parent / "logs"


def setup_logging(level: str = "INFO") -> None:
    """Set up logging configuration."""
    LOG_DIR.mkdir(exist_ok=True)

    # Create formatters
    console_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File handler - daily rotating
    log_file = LOG_DIR / f"bot_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Trade-specific log file
    trade_file = LOG_DIR / f"trades_{datetime.now().strftime('%Y%m%d')}.log"
    trade_handler = logging.FileHandler(trade_file)
    trade_handler.setLevel(logging.INFO)
    trade_handler.setFormatter(file_formatter)

    trade_logger = logging.getLogger("trades")
    trade_logger.addHandler(trade_handler)
    trade_logger.propagate = False

    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("ccxt").setLevel(logging.WARNING)

    logging.info(f"Logging initialized - level: {level}, log dir: {LOG_DIR}")


def log_trade(
    action: str,
    symbol: str,
    side: str,
    amount: float,
    price: float,
    strategy: str,
    order_id: str = "",
    extra: str = "",
) -> None:
    """Log a trade with structured format."""
    trade_logger = logging.getLogger("trades")
    trade_logger.info(
        f"{action} | {symbol} | {side.upper()} | "
        f"amount={amount:.8f} | price={price:.2f} | "
        f"value={amount * price:.2f} USD | strategy={strategy} | "
        f"order_id={order_id} | {extra}"
    )


def log_portfolio(
    total_value: float,
    balances: dict,
    pnl: float = 0,
    pnl_pct: float = 0,
) -> None:
    """Log portfolio status."""
    logger = logging.getLogger(__name__)

    balance_str = " | ".join(
        f"{currency}: {amount:.4f}" for currency, amount in balances.items() if amount > 0
    )

    pnl_str = f"+{pnl:.2f}" if pnl >= 0 else f"{pnl:.2f}"
    pnl_pct_str = f"+{pnl_pct:.2f}%" if pnl_pct >= 0 else f"{pnl_pct:.2f}%"

    logger.info(
        f"Portfolio: ${total_value:.2f} | PnL: {pnl_str} ({pnl_pct_str}) | {balance_str}"
    )


def log_strategy_status(strategy_name: str, status: dict) -> None:
    """Log strategy status."""
    logger = logging.getLogger(__name__)
    status_str = " | ".join(f"{k}={v}" for k, v in status.items())
    logger.info(f"Strategy [{strategy_name}]: {status_str}")


def log_risk_status(status: dict) -> None:
    """Log risk management status."""
    logger = logging.getLogger(__name__)

    if status.get("is_paused"):
        logger.warning(f"RISK PAUSED: {status.get('pause_reason', 'Unknown')}")
    else:
        drawdown_pct = status.get("current_drawdown_pct", 0) * 100
        daily_pnl = status.get("daily_pnl", 0)
        logger.info(
            f"Risk: drawdown={drawdown_pct:.2f}% | daily_pnl=${daily_pnl:.2f} | "
            f"portfolio=${status.get('current_portfolio_value', 0):.2f}"
        )
