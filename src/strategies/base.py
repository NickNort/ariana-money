from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.exchange import ExchangeConnector, Ticker, Balance


class SignalType(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class StrategySignal:
    signal_type: SignalType
    symbol: str
    price: Optional[float]  # None for market orders
    amount: float
    order_type: str  # 'limit' or 'market'
    reason: str


class Strategy(ABC):
    def __init__(self, exchange: ExchangeConnector):
        self.exchange = exchange

    @abstractmethod
    async def evaluate(
        self, symbol: str, ticker: Ticker, balances: dict[str, Balance]
    ) -> list[StrategySignal]:
        """Evaluate market conditions and return trading signals."""
        pass

    @abstractmethod
    async def on_order_filled(self, order_id: str, symbol: str) -> None:
        """Called when an order is filled."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Return strategy name."""
        pass
