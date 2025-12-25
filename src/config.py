import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class TradingPair:
    symbol: str
    base: str
    quote: str
    min_order_size: float
    price_precision: int
    amount_precision: int


@dataclass
class GridConfig:
    num_grids: int = 10
    upper_price_pct: float = 0.05  # 5% above current price
    lower_price_pct: float = 0.05  # 5% below current price
    allocation_pct: float = 0.3  # 30% of portfolio per pair


@dataclass
class DCAConfig:
    buy_interval_hours: int = 24
    buy_amount_pct: float = 0.02  # 2% of portfolio per buy
    price_drop_trigger_pct: float = 0.03  # Trigger extra buy on 3% drop
    max_buys_per_day: int = 3


@dataclass
class RiskConfig:
    max_risk_per_trade_pct: float = 0.02  # 2% max risk per trade
    max_drawdown_pct: float = 0.10  # 10% max drawdown before pause
    stop_loss_pct: float = 0.03  # 3% stop loss
    take_profit_pct: float = 0.05  # 5% take profit
    daily_loss_limit_pct: float = 0.05  # 5% daily loss limit


@dataclass
class Config:
    # API credentials
    api_key: str
    api_secret: str

    # Trading settings
    paper_trading: bool
    trading_pairs: list[TradingPair]

    # Strategy configs
    grid: GridConfig
    dca: DCAConfig
    risk: RiskConfig

    # Operational
    log_level: str
    check_interval_seconds: int = 60


# Default trading pairs for Kraken (USD pairs)
DEFAULT_TRADING_PAIRS = [
    TradingPair(
        symbol="BTC/USD",
        base="BTC",
        quote="USD",
        min_order_size=0.0001,
        price_precision=1,
        amount_precision=8,
    ),
    TradingPair(
        symbol="ETH/USD",
        base="ETH",
        quote="USD",
        min_order_size=0.001,
        price_precision=2,
        amount_precision=8,
    ),
    TradingPair(
        symbol="SOL/USD",
        base="SOL",
        quote="USD",
        min_order_size=0.01,
        price_precision=3,
        amount_precision=8,
    ),
]


def load_config() -> Config:
    api_key = os.getenv("KRAKEN_API_KEY")
    api_secret = os.getenv("KRAKEN_API_SECRET")

    if not api_key or not api_secret:
        raise ValueError("KRAKEN_API_KEY and KRAKEN_API_SECRET must be set in .env")

    paper_trading = os.getenv("PAPER_TRADING", "true").lower() == "true"
    log_level = os.getenv("LOG_LEVEL", "INFO")

    return Config(
        api_key=api_key,
        api_secret=api_secret,
        paper_trading=paper_trading,
        trading_pairs=DEFAULT_TRADING_PAIRS,
        grid=GridConfig(),
        dca=DCAConfig(),
        risk=RiskConfig(),
        log_level=log_level,
    )
