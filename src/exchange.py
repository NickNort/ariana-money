import logging
from decimal import Decimal
from dataclasses import dataclass
from typing import Optional

import ccxt

from src.config import Config, TradingPair

logger = logging.getLogger(__name__)


@dataclass
class Ticker:
    symbol: str
    bid: float
    ask: float
    last: float
    timestamp: int


@dataclass
class Balance:
    currency: str
    free: float
    used: float
    total: float


@dataclass
class Order:
    id: str
    symbol: str
    side: str  # 'buy' or 'sell'
    type: str  # 'limit' or 'market'
    price: Optional[float]
    amount: float
    filled: float
    status: str  # 'open', 'closed', 'canceled'
    timestamp: int


class ExchangeConnector:
    def __init__(self, config: Config):
        self.config = config
        self.paper_trading = config.paper_trading

        if self.paper_trading:
            logger.info("Initializing exchange connector in PAPER TRADING mode")
            self._paper_balances = {"USD": 100.0, "BTC": 0.0, "ETH": 0.0, "SOL": 0.0}
            self._paper_orders: dict[str, Order] = {}
            self._paper_order_counter = 0

        self.exchange = ccxt.kraken(
            {
                "apiKey": config.api_key,
                "secret": config.api_secret,
                "enableRateLimit": True,
            }
        )

    async def get_ticker(self, symbol: str) -> Ticker:
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return Ticker(
                symbol=symbol,
                bid=ticker["bid"],
                ask=ticker["ask"],
                last=ticker["last"],
                timestamp=ticker["timestamp"],
            )
        except Exception as e:
            logger.error(f"Failed to fetch ticker for {symbol}: {e}")
            raise

    async def get_tickers(self, symbols: list[str]) -> dict[str, Ticker]:
        tickers = {}
        for symbol in symbols:
            tickers[symbol] = await self.get_ticker(symbol)
        return tickers

    async def get_balance(self, currency: str) -> Balance:
        if self.paper_trading:
            amount = self._paper_balances.get(currency, 0.0)
            return Balance(currency=currency, free=amount, used=0.0, total=amount)

        try:
            balance = self.exchange.fetch_balance()
            if currency in balance:
                return Balance(
                    currency=currency,
                    free=balance[currency]["free"],
                    used=balance[currency]["used"],
                    total=balance[currency]["total"],
                )
            return Balance(currency=currency, free=0.0, used=0.0, total=0.0)
        except Exception as e:
            logger.error(f"Failed to fetch balance for {currency}: {e}")
            raise

    async def get_all_balances(self) -> dict[str, Balance]:
        if self.paper_trading:
            return {
                currency: Balance(currency=currency, free=amount, used=0.0, total=amount)
                for currency, amount in self._paper_balances.items()
            }

        try:
            balance = self.exchange.fetch_balance()
            balances = {}
            for currency, data in balance.items():
                if isinstance(data, dict) and "free" in data:
                    balances[currency] = Balance(
                        currency=currency,
                        free=data["free"] or 0.0,
                        used=data["used"] or 0.0,
                        total=data["total"] or 0.0,
                    )
            return balances
        except Exception as e:
            logger.error(f"Failed to fetch balances: {e}")
            raise

    async def create_limit_order(
        self, symbol: str, side: str, amount: float, price: float
    ) -> Order:
        if self.paper_trading:
            return await self._paper_create_order(symbol, side, "limit", amount, price)

        try:
            logger.info(
                f"Creating {side} limit order: {amount} {symbol} @ {price}"
            )
            order = self.exchange.create_limit_order(symbol, side, amount, price)
            return self._parse_order(order)
        except Exception as e:
            logger.error(f"Failed to create limit order: {e}")
            raise

    async def create_market_order(self, symbol: str, side: str, amount: float) -> Order:
        if self.paper_trading:
            ticker = await self.get_ticker(symbol)
            price = ticker.ask if side == "buy" else ticker.bid
            return await self._paper_create_order(symbol, side, "market", amount, price)

        try:
            logger.info(f"Creating {side} market order: {amount} {symbol}")
            order = self.exchange.create_market_order(symbol, side, amount)
            return self._parse_order(order)
        except Exception as e:
            logger.error(f"Failed to create market order: {e}")
            raise

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        if self.paper_trading:
            if order_id in self._paper_orders:
                self._paper_orders[order_id].status = "canceled"
                logger.info(f"Paper trade: Canceled order {order_id}")
                return True
            return False

        try:
            logger.info(f"Canceling order {order_id} for {symbol}")
            self.exchange.cancel_order(order_id, symbol)
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def get_order(self, order_id: str, symbol: str) -> Optional[Order]:
        if self.paper_trading:
            return self._paper_orders.get(order_id)

        try:
            order = self.exchange.fetch_order(order_id, symbol)
            return self._parse_order(order)
        except Exception as e:
            logger.error(f"Failed to fetch order {order_id}: {e}")
            return None

    async def get_open_orders(self, symbol: Optional[str] = None) -> list[Order]:
        if self.paper_trading:
            orders = [
                o for o in self._paper_orders.values() if o.status == "open"
            ]
            if symbol:
                orders = [o for o in orders if o.symbol == symbol]
            return orders

        try:
            orders = self.exchange.fetch_open_orders(symbol)
            return [self._parse_order(o) for o in orders]
        except Exception as e:
            logger.error(f"Failed to fetch open orders: {e}")
            raise

    async def _paper_create_order(
        self, symbol: str, side: str, order_type: str, amount: float, price: float
    ) -> Order:
        self._paper_order_counter += 1
        order_id = f"paper_{self._paper_order_counter}"

        base, quote = symbol.split("/")

        # Simulate order execution for market orders
        if order_type == "market":
            if side == "buy":
                cost = amount * price
                if self._paper_balances.get(quote, 0) >= cost:
                    self._paper_balances[quote] -= cost
                    self._paper_balances[base] = self._paper_balances.get(base, 0) + amount
                    logger.info(
                        f"Paper trade: Bought {amount} {base} @ {price} (cost: {cost} {quote})"
                    )
                    status = "closed"
                    filled = amount
                else:
                    logger.warning(f"Paper trade: Insufficient {quote} balance for buy")
                    status = "canceled"
                    filled = 0.0
            else:  # sell
                if self._paper_balances.get(base, 0) >= amount:
                    self._paper_balances[base] -= amount
                    proceeds = amount * price
                    self._paper_balances[quote] = self._paper_balances.get(quote, 0) + proceeds
                    logger.info(
                        f"Paper trade: Sold {amount} {base} @ {price} (proceeds: {proceeds} {quote})"
                    )
                    status = "closed"
                    filled = amount
                else:
                    logger.warning(f"Paper trade: Insufficient {base} balance for sell")
                    status = "canceled"
                    filled = 0.0
        else:
            # Limit orders stay open until checked/filled
            status = "open"
            filled = 0.0

        order = Order(
            id=order_id,
            symbol=symbol,
            side=side,
            type=order_type,
            price=price,
            amount=amount,
            filled=filled,
            status=status,
            timestamp=int(self.exchange.milliseconds()),
        )
        self._paper_orders[order_id] = order
        return order

    async def check_and_fill_paper_orders(self) -> list[Order]:
        """Check if any paper limit orders should be filled based on current prices."""
        if not self.paper_trading:
            return []

        filled_orders = []
        for order in list(self._paper_orders.values()):
            if order.status != "open" or order.type != "limit":
                continue

            ticker = await self.get_ticker(order.symbol)
            should_fill = False

            if order.side == "buy" and ticker.last <= order.price:
                should_fill = True
            elif order.side == "sell" and ticker.last >= order.price:
                should_fill = True

            if should_fill:
                base, quote = order.symbol.split("/")
                if order.side == "buy":
                    cost = order.amount * order.price
                    if self._paper_balances.get(quote, 0) >= cost:
                        self._paper_balances[quote] -= cost
                        self._paper_balances[base] = (
                            self._paper_balances.get(base, 0) + order.amount
                        )
                        order.filled = order.amount
                        order.status = "closed"
                        logger.info(
                            f"Paper trade: Limit buy filled - {order.amount} {base} @ {order.price}"
                        )
                        filled_orders.append(order)
                else:
                    if self._paper_balances.get(base, 0) >= order.amount:
                        self._paper_balances[base] -= order.amount
                        proceeds = order.amount * order.price
                        self._paper_balances[quote] = (
                            self._paper_balances.get(quote, 0) + proceeds
                        )
                        order.filled = order.amount
                        order.status = "closed"
                        logger.info(
                            f"Paper trade: Limit sell filled - {order.amount} {base} @ {order.price}"
                        )
                        filled_orders.append(order)

        return filled_orders

    def _parse_order(self, order: dict) -> Order:
        return Order(
            id=order["id"],
            symbol=order["symbol"],
            side=order["side"],
            type=order["type"],
            price=order.get("price"),
            amount=order["amount"],
            filled=order.get("filled", 0.0),
            status=order["status"],
            timestamp=order.get("timestamp", 0),
        )

    def get_trading_pair_info(self, symbol: str) -> Optional[TradingPair]:
        for pair in self.config.trading_pairs:
            if pair.symbol == symbol:
                return pair
        return None
