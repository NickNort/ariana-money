import asyncio
import logging
import signal
import time
from typing import Optional

from src.config import Config, load_config
from src.database import (
    init_database,
    save_order,
    update_order_status,
    save_trade,
    save_portfolio_snapshot,
    save_strategy_state,
    get_strategy_state,
    save_bot_state,
    get_bot_state,
    get_performance_stats,
)
from src.exchange import ExchangeConnector, Order
from src.logger import (
    setup_logging,
    log_trade,
    log_portfolio,
    log_strategy_status,
    log_risk_status,
)
from src.risk import RiskManager
from src.strategies import GridStrategy, DCAStrategy
from src.strategies.base import Strategy, StrategySignal, SignalType

logger = logging.getLogger(__name__)


class TradingBot:
    """Main trading bot orchestrator."""

    def __init__(self, config: Config):
        self.config = config
        self.exchange = ExchangeConnector(config)
        self.risk_manager = RiskManager(config.risk)
        self.strategies: list[Strategy] = []
        self.running = False
        self._shutdown_event = asyncio.Event()

    def _setup_strategies(self) -> None:
        """Initialize trading strategies."""
        for pair in self.config.trading_pairs:
            # Grid strategy for each pair
            grid = GridStrategy(self.exchange, self.config.grid, pair)
            self.strategies.append(grid)

            # DCA strategy for each pair
            dca = DCAStrategy(self.exchange, self.config.dca, pair)
            self.strategies.append(dca)

            logger.info(f"Initialized strategies for {pair.symbol}")

    async def _load_state(self) -> None:
        """Load persisted state."""
        # Load risk manager state
        risk_state = get_bot_state("risk_manager")
        if risk_state:
            self.risk_manager.load_state(risk_state)
            logger.info("Loaded risk manager state")

        # Load strategy states
        for strategy in self.strategies:
            state = get_strategy_state(strategy.get_name())
            if state and hasattr(strategy, "load_state"):
                strategy.load_state(state)
                logger.info(f"Loaded state for {strategy.get_name()}")

    async def _save_state(self) -> None:
        """Save current state for persistence."""
        # Save risk manager state
        save_bot_state("risk_manager", self.risk_manager.get_status())

        # Save strategy states
        for strategy in self.strategies:
            if hasattr(strategy, "get_status"):
                save_strategy_state(strategy.get_name(), strategy.get_status())

    async def _calculate_portfolio_value(self) -> tuple[float, dict[str, float], dict[str, float]]:
        """Calculate total portfolio value in USD."""
        balances = await self.exchange.get_all_balances()
        symbols = [pair.symbol for pair in self.config.trading_pairs]
        tickers = await self.exchange.get_tickers(symbols)

        total_value = 0.0
        balance_dict = {}
        price_dict = {}

        # USD balance
        usd_balance = balances.get("USD")
        if usd_balance:
            total_value += usd_balance.total
            balance_dict["USD"] = usd_balance.total

        # Crypto balances converted to USD
        for pair in self.config.trading_pairs:
            ticker = tickers.get(pair.symbol)
            balance = balances.get(pair.base)

            if ticker:
                price_dict[pair.symbol] = ticker.last

            if balance and ticker and balance.total > 0:
                value = balance.total * ticker.last
                total_value += value
                balance_dict[pair.base] = balance.total

        return total_value, balance_dict, price_dict

    async def _execute_signal(self, signal: StrategySignal, strategy: Strategy) -> Optional[Order]:
        """Execute a trading signal."""
        # Get current ticker for validation
        ticker = await self.exchange.get_ticker(signal.symbol)
        balances = await self.exchange.get_all_balances()

        # Validate against risk manager
        is_valid, reason = self.risk_manager.validate_signal(signal, balances, ticker)
        if not is_valid:
            logger.warning(f"Signal rejected by risk manager: {reason}")
            return None

        # Execute order
        try:
            if signal.order_type == "market":
                order = await self.exchange.create_market_order(
                    signal.symbol, signal.signal_type.value, signal.amount
                )
            else:
                order = await self.exchange.create_limit_order(
                    signal.symbol,
                    signal.signal_type.value,
                    signal.amount,
                    signal.price,
                )

            # Log and persist
            price = signal.price or ticker.last
            log_trade(
                action="ORDER_CREATED",
                symbol=signal.symbol,
                side=signal.signal_type.value,
                amount=signal.amount,
                price=price,
                strategy=strategy.get_name(),
                order_id=order.id,
                extra=signal.reason,
            )

            save_order(
                order_id=order.id,
                symbol=signal.symbol,
                side=signal.signal_type.value,
                order_type=signal.order_type,
                price=signal.price,
                amount=signal.amount,
                status=order.status,
                strategy=strategy.get_name(),
            )

            # If it's a grid strategy, associate order with grid level
            if isinstance(strategy, GridStrategy) and signal.price:
                strategy.set_order_id(signal.price, order.id)

            # If market order filled immediately, record trade
            if order.status == "closed":
                save_trade(
                    order_id=order.id,
                    symbol=signal.symbol,
                    side=signal.signal_type.value,
                    price=price,
                    amount=signal.amount,
                    strategy=strategy.get_name(),
                )

                # Update DCA state if applicable
                if isinstance(strategy, DCAStrategy) and signal.signal_type == SignalType.BUY:
                    strategy.record_buy(price, signal.amount)

                log_trade(
                    action="ORDER_FILLED",
                    symbol=signal.symbol,
                    side=signal.signal_type.value,
                    amount=signal.amount,
                    price=price,
                    strategy=strategy.get_name(),
                    order_id=order.id,
                )

            return order

        except Exception as e:
            logger.error(f"Failed to execute signal: {e}")
            return None

    async def _check_filled_orders(self) -> None:
        """Check for filled orders and trigger strategy callbacks."""
        if self.config.paper_trading:
            filled_orders = await self.exchange.check_and_fill_paper_orders()
            for order in filled_orders:
                update_order_status(order.id, order.status, order.filled)

                save_trade(
                    order_id=order.id,
                    symbol=order.symbol,
                    side=order.side,
                    price=order.price,
                    amount=order.amount,
                )

                # Notify strategies of filled orders
                for strategy in self.strategies:
                    signals = await strategy.on_order_filled(order.id, order.symbol)
                    for signal in signals:
                        await self._execute_signal(signal, strategy)

    async def _run_cycle(self) -> None:
        """Run one trading cycle."""
        try:
            # Calculate portfolio value
            total_value, balances, prices = await self._calculate_portfolio_value()

            # Update risk manager
            self.risk_manager.update_portfolio_value(total_value)

            # Save portfolio snapshot
            save_portfolio_snapshot(total_value, balances, prices)

            # Log status
            risk_status = self.risk_manager.get_status()
            initial_value = risk_status.get("initial_portfolio_value", total_value)
            pnl = total_value - initial_value
            pnl_pct = (pnl / initial_value * 100) if initial_value > 0 else 0

            log_portfolio(total_value, balances, pnl, pnl_pct)
            log_risk_status(risk_status)

            # Check if trading is paused
            if risk_status["is_paused"]:
                logger.warning("Trading paused - skipping strategy evaluation")
                return

            # Check for filled orders
            await self._check_filled_orders()

            # Get current tickers
            symbols = [pair.symbol for pair in self.config.trading_pairs]
            tickers = await self.exchange.get_tickers(symbols)
            balance_objs = await self.exchange.get_all_balances()

            # Evaluate strategies
            for strategy in self.strategies:
                try:
                    for symbol, ticker in tickers.items():
                        signals = await strategy.evaluate(symbol, ticker, balance_objs)

                        for signal in signals:
                            await self._execute_signal(signal, strategy)

                    # Log strategy status
                    if hasattr(strategy, "get_status"):
                        log_strategy_status(strategy.get_name(), strategy.get_status())

                except Exception as e:
                    logger.error(f"Strategy {strategy.get_name()} error: {e}")

            # Save state periodically
            await self._save_state()

        except Exception as e:
            logger.error(f"Error in trading cycle: {e}", exc_info=True)

    async def run(self) -> None:
        """Main bot loop."""
        logger.info("Starting trading bot...")

        # Initialize
        init_database()
        self._setup_strategies()
        await self._load_state()

        # Initialize risk manager with current portfolio
        total_value, _, _ = await self._calculate_portfolio_value()
        if self.risk_manager.state.initial_portfolio_value == 0:
            self.risk_manager.initialize(total_value)

        self.running = True
        logger.info(
            f"Bot started - Paper trading: {self.config.paper_trading}, "
            f"Portfolio: ${total_value:.2f}"
        )

        # Main loop
        while self.running:
            try:
                await self._run_cycle()

                # Wait for next cycle or shutdown
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=self.config.check_interval_seconds,
                    )
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    pass  # Normal timeout, continue loop

            except Exception as e:
                logger.error(f"Bot loop error: {e}", exc_info=True)
                await asyncio.sleep(10)  # Back off on error

        await self._shutdown()

    async def _shutdown(self) -> None:
        """Clean shutdown."""
        logger.info("Shutting down bot...")
        self.running = False

        # Save final state
        await self._save_state()

        # Log final stats
        stats = get_performance_stats(days=30)
        logger.info(f"30-day performance: {stats}")

        logger.info("Bot shutdown complete")

    def stop(self) -> None:
        """Signal the bot to stop."""
        logger.info("Stop signal received")
        self._shutdown_event.set()


def main() -> None:
    """Main entry point."""
    # Load config
    config = load_config()

    # Setup logging
    setup_logging(config.log_level)

    # Create bot
    bot = TradingBot(config)

    # Handle signals
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}")
        bot.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run bot
    asyncio.run(bot.run())


if __name__ == "__main__":
    main()
