import logging
from dataclasses import dataclass
from typing import Optional

from src.config import GridConfig, TradingPair
from src.exchange import ExchangeConnector, Ticker, Balance, Order
from src.strategies.base import Strategy, StrategySignal, SignalType

logger = logging.getLogger(__name__)


@dataclass
class GridLevel:
    price: float
    side: str  # 'buy' or 'sell'
    order_id: Optional[str] = None
    filled: bool = False


class GridStrategy(Strategy):
    """
    Grid trading strategy that places buy orders below current price
    and sell orders above current price. When a buy order fills, it places
    a sell order above. When a sell order fills, it places a buy order below.
    """

    def __init__(
        self,
        exchange: ExchangeConnector,
        config: GridConfig,
        trading_pair: TradingPair,
    ):
        super().__init__(exchange)
        self.config = config
        self.trading_pair = trading_pair
        self.grid_levels: list[GridLevel] = []
        self.initialized = False
        self.base_price: Optional[float] = None
        self.order_amount: Optional[float] = None

    def get_name(self) -> str:
        return f"Grid({self.trading_pair.symbol})"

    async def initialize_grid(
        self, current_price: float, available_quote: float
    ) -> list[StrategySignal]:
        """Set up the initial grid around the current price."""
        signals = []

        self.base_price = current_price
        upper_price = current_price * (1 + self.config.upper_price_pct)
        lower_price = current_price * (1 - self.config.lower_price_pct)
        price_range = upper_price - lower_price
        grid_spacing = price_range / self.config.num_grids

        # Calculate amount per grid level
        # Use allocation_pct of available quote, divided by number of buy grids
        num_buy_grids = self.config.num_grids // 2
        total_allocation = available_quote * self.config.allocation_pct
        amount_per_grid_usd = total_allocation / num_buy_grids

        self.grid_levels = []

        for i in range(self.config.num_grids):
            level_price = lower_price + (i * grid_spacing)
            level_price = round(level_price, self.trading_pair.price_precision)

            if level_price < current_price:
                # Buy level - below current price
                amount = amount_per_grid_usd / level_price
                amount = round(amount, self.trading_pair.amount_precision)

                if amount >= self.trading_pair.min_order_size:
                    grid_level = GridLevel(price=level_price, side="buy")
                    self.grid_levels.append(grid_level)

                    signals.append(
                        StrategySignal(
                            signal_type=SignalType.BUY,
                            symbol=self.trading_pair.symbol,
                            price=level_price,
                            amount=amount,
                            order_type="limit",
                            reason=f"Grid buy level at {level_price}",
                        )
                    )
            else:
                # Sell level - above current price (only if we have base currency)
                # These will be placed when buy orders fill
                grid_level = GridLevel(price=level_price, side="sell")
                self.grid_levels.append(grid_level)

        self.order_amount = amount_per_grid_usd
        self.initialized = True

        logger.info(
            f"Grid initialized for {self.trading_pair.symbol}: "
            f"{len(self.grid_levels)} levels from {lower_price} to {upper_price}"
        )

        return signals

    async def evaluate(
        self, symbol: str, ticker: Ticker, balances: dict[str, Balance]
    ) -> list[StrategySignal]:
        if symbol != self.trading_pair.symbol:
            return []

        quote_balance = balances.get(self.trading_pair.quote)
        if not quote_balance:
            logger.warning(f"No {self.trading_pair.quote} balance found")
            return []

        # Initialize grid on first run
        if not self.initialized:
            return await self.initialize_grid(ticker.last, quote_balance.free)

        # Check for grid levels that need orders placed
        signals = []
        current_price = ticker.last

        # Check if price has moved significantly outside our grid
        if self.base_price:
            price_change_pct = abs(current_price - self.base_price) / self.base_price
            if price_change_pct > 0.15:  # 15% move
                logger.info(
                    f"Price moved {price_change_pct:.1%} from base. Consider re-initializing grid."
                )

        return signals

    async def on_order_filled(self, order_id: str, symbol: str) -> list[StrategySignal]:
        """When a grid order fills, place the opposite order."""
        signals = []

        for level in self.grid_levels:
            if level.order_id == order_id:
                level.filled = True
                level.order_id = None

                if level.side == "buy":
                    # Buy filled - place a sell order above
                    sell_price = level.price * (
                        1 + (self.config.upper_price_pct / (self.config.num_grids / 2))
                    )
                    sell_price = round(sell_price, self.trading_pair.price_precision)

                    amount = self.order_amount / level.price if self.order_amount else 0
                    amount = round(amount, self.trading_pair.amount_precision)

                    if amount >= self.trading_pair.min_order_size:
                        signals.append(
                            StrategySignal(
                                signal_type=SignalType.SELL,
                                symbol=symbol,
                                price=sell_price,
                                amount=amount,
                                order_type="limit",
                                reason=f"Grid sell after buy fill at {level.price}",
                            )
                        )
                        logger.info(
                            f"Buy filled at {level.price}, placing sell at {sell_price}"
                        )

                elif level.side == "sell":
                    # Sell filled - place a buy order below
                    buy_price = level.price * (
                        1 - (self.config.lower_price_pct / (self.config.num_grids / 2))
                    )
                    buy_price = round(buy_price, self.trading_pair.price_precision)

                    ticker = await self.exchange.get_ticker(symbol)
                    amount = self.order_amount / buy_price if self.order_amount else 0
                    amount = round(amount, self.trading_pair.amount_precision)

                    if amount >= self.trading_pair.min_order_size:
                        signals.append(
                            StrategySignal(
                                signal_type=SignalType.BUY,
                                symbol=symbol,
                                price=buy_price,
                                amount=amount,
                                order_type="limit",
                                reason=f"Grid buy after sell fill at {level.price}",
                            )
                        )
                        logger.info(
                            f"Sell filled at {level.price}, placing buy at {buy_price}"
                        )

                break

        return signals

    def set_order_id(self, price: float, order_id: str) -> None:
        """Associate an order ID with a grid level."""
        for level in self.grid_levels:
            if abs(level.price - price) < 0.01:  # Small tolerance
                level.order_id = order_id
                break

    def get_status(self) -> dict:
        """Get current grid status."""
        return {
            "initialized": self.initialized,
            "base_price": self.base_price,
            "num_levels": len(self.grid_levels),
            "buy_levels": len([l for l in self.grid_levels if l.side == "buy"]),
            "sell_levels": len([l for l in self.grid_levels if l.side == "sell"]),
            "active_orders": len([l for l in self.grid_levels if l.order_id]),
        }
