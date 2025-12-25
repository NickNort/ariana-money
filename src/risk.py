import logging
import time
from dataclasses import dataclass
from typing import Optional

from src.config import RiskConfig
from src.exchange import Balance, Ticker
from src.strategies.base import StrategySignal, SignalType

logger = logging.getLogger(__name__)


@dataclass
class RiskState:
    initial_portfolio_value: float = 0.0
    peak_portfolio_value: float = 0.0
    current_portfolio_value: float = 0.0
    daily_starting_value: float = 0.0
    daily_pnl: float = 0.0
    day_start_timestamp: float = 0.0
    is_paused: bool = False
    pause_reason: str = ""


class RiskManager:
    """
    Risk management layer that:
    1. Enforces position sizing limits
    2. Monitors drawdown and pauses trading if exceeded
    3. Tracks daily P&L limits
    4. Validates all trades before execution
    """

    def __init__(self, config: RiskConfig):
        self.config = config
        self.state = RiskState()

    def initialize(self, portfolio_value: float) -> None:
        """Initialize risk manager with starting portfolio value."""
        self.state.initial_portfolio_value = portfolio_value
        self.state.peak_portfolio_value = portfolio_value
        self.state.current_portfolio_value = portfolio_value
        self.state.daily_starting_value = portfolio_value
        self.state.day_start_timestamp = time.time()

        logger.info(f"Risk manager initialized with portfolio value: ${portfolio_value:.2f}")

    def update_portfolio_value(self, value: float) -> None:
        """Update current portfolio value and check risk limits."""
        self.state.current_portfolio_value = value

        # Update peak
        if value > self.state.peak_portfolio_value:
            self.state.peak_portfolio_value = value

        # Reset daily tracking if new day
        self._check_daily_reset()

        # Calculate metrics
        self.state.daily_pnl = value - self.state.daily_starting_value

        # Check for drawdown breach
        self._check_drawdown()

        # Check daily loss limit
        self._check_daily_loss_limit()

    def _check_daily_reset(self) -> None:
        """Reset daily tracking if it's a new day."""
        current_time = time.time()
        seconds_per_day = 86400

        if current_time - self.state.day_start_timestamp >= seconds_per_day:
            self.state.daily_starting_value = self.state.current_portfolio_value
            self.state.day_start_timestamp = current_time
            self.state.daily_pnl = 0.0

            # Unpause if we were paused due to daily limit
            if self.state.is_paused and "daily" in self.state.pause_reason.lower():
                self.state.is_paused = False
                self.state.pause_reason = ""
                logger.info("New day - daily loss limit reset, trading resumed")

    def _check_drawdown(self) -> None:
        """Check if drawdown exceeds maximum allowed."""
        if self.state.peak_portfolio_value == 0:
            return

        drawdown = (
            self.state.peak_portfolio_value - self.state.current_portfolio_value
        ) / self.state.peak_portfolio_value

        if drawdown >= self.config.max_drawdown_pct:
            self.state.is_paused = True
            self.state.pause_reason = (
                f"Max drawdown exceeded: {drawdown:.1%} >= {self.config.max_drawdown_pct:.1%}"
            )
            logger.warning(f"TRADING PAUSED: {self.state.pause_reason}")

    def _check_daily_loss_limit(self) -> None:
        """Check if daily loss limit is exceeded."""
        if self.state.daily_starting_value == 0:
            return

        daily_loss_pct = -self.state.daily_pnl / self.state.daily_starting_value

        if daily_loss_pct >= self.config.daily_loss_limit_pct:
            self.state.is_paused = True
            self.state.pause_reason = (
                f"Daily loss limit exceeded: {daily_loss_pct:.1%} >= "
                f"{self.config.daily_loss_limit_pct:.1%}"
            )
            logger.warning(f"TRADING PAUSED: {self.state.pause_reason}")

    def validate_signal(
        self, signal: StrategySignal, balances: dict[str, Balance], ticker: Ticker
    ) -> tuple[bool, str]:
        """
        Validate a trading signal against risk parameters.
        Returns (is_valid, reason).
        """
        if self.state.is_paused:
            return False, f"Trading paused: {self.state.pause_reason}"

        # Calculate trade value
        price = signal.price if signal.price else ticker.last
        trade_value = signal.amount * price

        # Check position size limit
        max_trade_value = (
            self.state.current_portfolio_value * self.config.max_risk_per_trade_pct
        )
        if trade_value > max_trade_value:
            return False, (
                f"Trade value ${trade_value:.2f} exceeds max "
                f"${max_trade_value:.2f} ({self.config.max_risk_per_trade_pct:.1%} of portfolio)"
            )

        # Check balance for buys
        if signal.signal_type == SignalType.BUY:
            quote = signal.symbol.split("/")[1]
            quote_balance = balances.get(quote)
            if not quote_balance or quote_balance.free < trade_value:
                available = quote_balance.free if quote_balance else 0
                return False, f"Insufficient {quote} balance: need ${trade_value:.2f}, have ${available:.2f}"

        # Check balance for sells
        elif signal.signal_type == SignalType.SELL:
            base = signal.symbol.split("/")[0]
            base_balance = balances.get(base)
            if not base_balance or base_balance.free < signal.amount:
                available = base_balance.free if base_balance else 0
                return False, f"Insufficient {base} balance: need {signal.amount}, have {available}"

        return True, "OK"

    def calculate_position_size(
        self, symbol: str, entry_price: float, stop_loss_price: float
    ) -> float:
        """
        Calculate position size based on risk per trade.
        Uses the formula: Position Size = Risk Amount / (Entry - Stop Loss)
        """
        risk_amount = self.state.current_portfolio_value * self.config.max_risk_per_trade_pct
        price_risk = abs(entry_price - stop_loss_price)

        if price_risk == 0:
            return 0.0

        position_size = risk_amount / price_risk
        return position_size

    def get_stop_loss_price(self, entry_price: float, side: str) -> float:
        """Calculate stop loss price based on config."""
        if side == "buy":
            return entry_price * (1 - self.config.stop_loss_pct)
        else:
            return entry_price * (1 + self.config.stop_loss_pct)

    def get_take_profit_price(self, entry_price: float, side: str) -> float:
        """Calculate take profit price based on config."""
        if side == "buy":
            return entry_price * (1 + self.config.take_profit_pct)
        else:
            return entry_price * (1 - self.config.take_profit_pct)

    def resume_trading(self) -> bool:
        """Manually resume trading after a pause."""
        if not self.state.is_paused:
            return True

        # Only allow resume if drawdown has recovered
        current_drawdown = (
            self.state.peak_portfolio_value - self.state.current_portfolio_value
        ) / self.state.peak_portfolio_value

        if current_drawdown < self.config.max_drawdown_pct * 0.8:  # 80% recovery
            self.state.is_paused = False
            self.state.pause_reason = ""
            logger.info("Trading resumed after risk recovery")
            return True

        logger.warning(
            f"Cannot resume: drawdown still at {current_drawdown:.1%}, "
            f"need recovery to {self.config.max_drawdown_pct * 0.8:.1%}"
        )
        return False

    def force_resume(self) -> None:
        """Force resume trading (use with caution)."""
        self.state.is_paused = False
        self.state.pause_reason = ""
        logger.warning("Trading FORCE resumed - risk limits may be exceeded")

    def get_status(self) -> dict:
        """Get current risk status."""
        drawdown = 0.0
        if self.state.peak_portfolio_value > 0:
            drawdown = (
                self.state.peak_portfolio_value - self.state.current_portfolio_value
            ) / self.state.peak_portfolio_value

        daily_return = 0.0
        if self.state.daily_starting_value > 0:
            daily_return = self.state.daily_pnl / self.state.daily_starting_value

        return {
            "is_paused": self.state.is_paused,
            "pause_reason": self.state.pause_reason,
            "current_portfolio_value": self.state.current_portfolio_value,
            "peak_portfolio_value": self.state.peak_portfolio_value,
            "initial_portfolio_value": self.state.initial_portfolio_value,
            "current_drawdown_pct": drawdown,
            "max_drawdown_pct": self.config.max_drawdown_pct,
            "daily_pnl": self.state.daily_pnl,
            "daily_return_pct": daily_return,
            "daily_loss_limit_pct": self.config.daily_loss_limit_pct,
        }

    def load_state(self, state_dict: dict) -> None:
        """Load state from persistence."""
        self.state.initial_portfolio_value = state_dict.get("initial_portfolio_value", 0.0)
        self.state.peak_portfolio_value = state_dict.get("peak_portfolio_value", 0.0)
        self.state.current_portfolio_value = state_dict.get("current_portfolio_value", 0.0)
        self.state.daily_starting_value = state_dict.get("daily_starting_value", 0.0)
        self.state.daily_pnl = state_dict.get("daily_pnl", 0.0)
        self.state.day_start_timestamp = state_dict.get("day_start_timestamp", 0.0)
        self.state.is_paused = state_dict.get("is_paused", False)
        self.state.pause_reason = state_dict.get("pause_reason", "")
