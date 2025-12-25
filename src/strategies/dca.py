import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from src.config import DCAConfig, TradingPair
from src.exchange import ExchangeConnector, Ticker, Balance
from src.strategies.base import Strategy, StrategySignal, SignalType

logger = logging.getLogger(__name__)


@dataclass
class DCAState:
    last_buy_time: float = 0.0
    last_buy_price: float = 0.0
    buys_today: int = 0
    day_start: float = 0.0
    total_invested: float = 0.0
    total_amount_bought: float = 0.0
    average_price: float = 0.0


class DCAStrategy(Strategy):
    """
    Dollar Cost Averaging strategy that:
    1. Buys at regular intervals regardless of price
    2. Buys extra when price drops significantly from last buy
    3. Limits buys per day to manage risk
    """

    def __init__(
        self,
        exchange: ExchangeConnector,
        config: DCAConfig,
        trading_pair: TradingPair,
    ):
        super().__init__(exchange)
        self.config = config
        self.trading_pair = trading_pair
        self.state = DCAState()

    def get_name(self) -> str:
        return f"DCA({self.trading_pair.symbol})"

    def _reset_daily_counter(self) -> None:
        """Reset daily buy counter if it's a new day."""
        current_time = time.time()
        seconds_per_day = 86400

        if current_time - self.state.day_start >= seconds_per_day:
            self.state.buys_today = 0
            self.state.day_start = current_time
            logger.info(f"DCA daily counter reset for {self.trading_pair.symbol}")

    def _can_buy(self) -> bool:
        """Check if we can make another buy."""
        self._reset_daily_counter()
        return self.state.buys_today < self.config.max_buys_per_day

    def _time_for_scheduled_buy(self) -> bool:
        """Check if enough time has passed for a scheduled buy."""
        if self.state.last_buy_time == 0:
            return True

        hours_since_last = (time.time() - self.state.last_buy_time) / 3600
        return hours_since_last >= self.config.buy_interval_hours

    def _price_dropped_enough(self, current_price: float) -> bool:
        """Check if price has dropped enough to trigger an extra buy."""
        if self.state.last_buy_price == 0:
            return False

        price_change = (self.state.last_buy_price - current_price) / self.state.last_buy_price
        return price_change >= self.config.price_drop_trigger_pct

    async def evaluate(
        self, symbol: str, ticker: Ticker, balances: dict[str, Balance]
    ) -> list[StrategySignal]:
        if symbol != self.trading_pair.symbol:
            return []

        signals = []
        current_price = ticker.last

        quote_balance = balances.get(self.trading_pair.quote)
        if not quote_balance or quote_balance.free <= 0:
            logger.debug(f"No {self.trading_pair.quote} balance for DCA")
            return []

        if not self._can_buy():
            logger.debug(f"DCA max daily buys reached for {symbol}")
            return []

        should_buy = False
        reason = ""

        # Check for scheduled buy
        if self._time_for_scheduled_buy():
            should_buy = True
            reason = f"Scheduled DCA buy (every {self.config.buy_interval_hours}h)"

        # Check for price drop trigger (extra buy opportunity)
        elif self._price_dropped_enough(current_price):
            should_buy = True
            drop_pct = (
                (self.state.last_buy_price - current_price)
                / self.state.last_buy_price
                * 100
            )
            reason = f"Price drop DCA buy ({drop_pct:.1f}% drop from last buy)"

        if should_buy:
            # Calculate buy amount
            buy_amount_usd = quote_balance.free * self.config.buy_amount_pct
            amount = buy_amount_usd / current_price
            amount = round(amount, self.trading_pair.amount_precision)

            if amount >= self.trading_pair.min_order_size:
                signals.append(
                    StrategySignal(
                        signal_type=SignalType.BUY,
                        symbol=symbol,
                        price=None,  # Market order
                        amount=amount,
                        order_type="market",
                        reason=reason,
                    )
                )
                logger.info(f"DCA signal: {reason} - {amount} {self.trading_pair.base}")
            else:
                logger.debug(
                    f"DCA buy amount {amount} below minimum {self.trading_pair.min_order_size}"
                )

        return signals

    async def on_order_filled(self, order_id: str, symbol: str) -> list[StrategySignal]:
        """Update state when a DCA buy is filled."""
        # Note: The actual price and amount should be passed in
        # For now, this is called by the orchestrator with order details
        return []

    def record_buy(self, price: float, amount: float) -> None:
        """Record a completed buy."""
        self.state.last_buy_time = time.time()
        self.state.last_buy_price = price
        self.state.buys_today += 1
        self.state.total_invested += price * amount
        self.state.total_amount_bought += amount

        if self.state.total_amount_bought > 0:
            self.state.average_price = (
                self.state.total_invested / self.state.total_amount_bought
            )

        logger.info(
            f"DCA buy recorded: {amount} @ {price}, "
            f"avg price: {self.state.average_price:.2f}, "
            f"total invested: {self.state.total_invested:.2f}"
        )

    def get_status(self) -> dict:
        """Get current DCA status."""
        return {
            "last_buy_time": self.state.last_buy_time,
            "last_buy_price": self.state.last_buy_price,
            "buys_today": self.state.buys_today,
            "max_buys_per_day": self.config.max_buys_per_day,
            "total_invested": self.state.total_invested,
            "total_amount_bought": self.state.total_amount_bought,
            "average_price": self.state.average_price,
            "buy_interval_hours": self.config.buy_interval_hours,
        }

    def load_state(self, state_dict: dict) -> None:
        """Load state from persistence."""
        self.state.last_buy_time = state_dict.get("last_buy_time", 0.0)
        self.state.last_buy_price = state_dict.get("last_buy_price", 0.0)
        self.state.buys_today = state_dict.get("buys_today", 0)
        self.state.day_start = state_dict.get("day_start", 0.0)
        self.state.total_invested = state_dict.get("total_invested", 0.0)
        self.state.total_amount_bought = state_dict.get("total_amount_bought", 0.0)
        self.state.average_price = state_dict.get("average_price", 0.0)
