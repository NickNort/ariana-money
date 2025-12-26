#!/usr/bin/env python3
"""
Trading Bot Dashboard - Real-time visualization of bot performance.
"""

import os
import sys
import time
from datetime import datetime, timedelta

from src.database import (
    get_portfolio_history,
    get_trades,
    get_performance_stats,
    get_bot_state,
    get_strategy_state,
)


def clear_screen():
    os.system("clear" if os.name == "posix" else "cls")


def format_currency(value: float) -> str:
    """Format value as currency."""
    if value >= 0:
        return f"${value:,.2f}"
    return f"-${abs(value):,.2f}"


def format_pct(value: float) -> str:
    """Format value as percentage with color indicator."""
    if value >= 0:
        return f"+{value:.2f}%"
    return f"{value:.2f}%"


def color(text: str, color_code: str) -> str:
    """Apply ANSI color to text."""
    colors = {
        "green": "\033[92m",
        "red": "\033[91m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "cyan": "\033[96m",
        "white": "\033[97m",
        "gray": "\033[90m",
        "bold": "\033[1m",
        "reset": "\033[0m",
    }
    return f"{colors.get(color_code, '')}{text}{colors['reset']}"


def pnl_color(value: float) -> str:
    """Color based on positive/negative."""
    return "green" if value >= 0 else "red"


def draw_box(title: str, content: list[str], width: int = 50) -> list[str]:
    """Draw a box around content."""
    lines = []
    lines.append(f"┌─ {title} " + "─" * (width - len(title) - 4) + "┐")
    for line in content:
        padding = width - len(line.replace("\033[92m", "").replace("\033[91m", "").replace("\033[93m", "").replace("\033[94m", "").replace("\033[96m", "").replace("\033[97m", "").replace("\033[90m", "").replace("\033[1m", "").replace("\033[0m", "")) - 2
        if padding < 0:
            padding = 0
        lines.append(f"│ {line}{' ' * padding}│")
    lines.append("└" + "─" * (width - 1) + "┘")
    return lines


def draw_mini_chart(values: list[float], width: int = 30, height: int = 5) -> list[str]:
    """Draw a simple ASCII chart."""
    if not values or len(values) < 2:
        return ["  No data yet..."]

    min_val = min(values)
    max_val = max(values)
    val_range = max_val - min_val if max_val != min_val else 1

    # Sample values to fit width
    step = max(1, len(values) // width)
    sampled = [values[i] for i in range(0, len(values), step)][:width]

    chart = []
    for row in range(height):
        line = ""
        threshold = max_val - (row / (height - 1)) * val_range
        for val in sampled:
            if val >= threshold:
                line += "█"
            else:
                line += " "
        chart.append(f"  {line}")

    return chart


def render_dashboard():
    """Render the main dashboard."""
    clear_screen()

    # Get data
    portfolio_history = get_portfolio_history(limit=100)
    trades = get_trades(limit=10)
    stats = get_performance_stats(days=30)
    risk_state = get_bot_state("risk_manager") or {}
    grid_state = get_strategy_state("Grid(SOL/USD)") or {}
    dca_state = get_strategy_state("DCA(SOL/USD)") or {}

    # Current values
    current_value = stats.get("ending_value_usd", 0)
    initial_value = stats.get("starting_value_usd", 0) or risk_state.get("initial_portfolio_value", 100)
    pnl = stats.get("pnl_usd", 0)
    pnl_pct = stats.get("pnl_pct", 0)

    # Header
    print()
    print(color("  ╔═══════════════════════════════════════════════════════════════╗", "cyan"))
    print(color("  ║", "cyan") + color("            🤖 TRADING BOT DASHBOARD                        ", "bold") + color("║", "cyan"))
    print(color("  ╚═══════════════════════════════════════════════════════════════╝", "cyan"))
    print()

    # Portfolio Overview
    portfolio_content = [
        f"Current Value:    {color(format_currency(current_value), 'bold')}",
        f"Initial Value:    {format_currency(initial_value)}",
        "",
        f"Total P&L:        {color(format_currency(pnl), pnl_color(pnl))} ({color(format_pct(pnl_pct), pnl_color(pnl_pct))})",
        f"Daily P&L:        {color(format_currency(risk_state.get('daily_pnl', 0)), pnl_color(risk_state.get('daily_pnl', 0)))}",
        "",
        f"Peak Value:       {format_currency(risk_state.get('peak_portfolio_value', current_value))}",
        f"Drawdown:         {color(format_pct(-risk_state.get('current_drawdown_pct', 0) * 100), 'yellow')}",
    ]

    # Risk Status
    is_paused = risk_state.get("is_paused", False)
    risk_content = [
        f"Status:           {color('⚠ PAUSED', 'red') if is_paused else color('● ACTIVE', 'green')}",
        f"Max Drawdown:     {format_pct(risk_state.get('max_drawdown_pct', 0.1) * 100)} limit",
        f"Daily Loss Limit: {format_pct(risk_state.get('daily_loss_limit_pct', 0.05) * 100)} limit",
    ]
    if is_paused:
        risk_content.append(f"Reason: {risk_state.get('pause_reason', 'Unknown')[:30]}")

    # Print side by side
    portfolio_box = draw_box("PORTFOLIO", portfolio_content, 40)
    risk_box = draw_box("RISK STATUS", risk_content, 35)

    for i in range(max(len(portfolio_box), len(risk_box))):
        left = portfolio_box[i] if i < len(portfolio_box) else " " * 40
        right = risk_box[i] if i < len(risk_box) else ""
        print(f"  {left}  {right}")

    print()

    # Strategy Status
    grid_content = [
        f"Base Price:       ${grid_state.get('base_price', 0):.2f}",
        f"Grid Levels:      {grid_state.get('num_levels', 0)}",
        f"Buy Orders:       {grid_state.get('buy_levels', 0)}",
        f"Sell Orders:      {grid_state.get('sell_levels', 0)}",
        f"Active Orders:    {grid_state.get('active_orders', 0)}",
    ]

    dca_content = [
        f"Avg Buy Price:    ${dca_state.get('average_price', 0):.2f}",
        f"Total Invested:   {format_currency(dca_state.get('total_invested', 0))}",
        f"Amount Bought:    {dca_state.get('total_amount_bought', 0):.6f} SOL",
        f"Buys Today:       {dca_state.get('buys_today', 0)}/{dca_state.get('max_buys_per_day', 3)}",
        f"Next Buy In:      {_time_until_next_buy(dca_state.get('last_buy_time', 0))}",
    ]

    grid_box = draw_box("GRID STRATEGY", grid_content, 40)
    dca_box = draw_box("DCA STRATEGY", dca_content, 35)

    for i in range(max(len(grid_box), len(dca_box))):
        left = grid_box[i] if i < len(grid_box) else " " * 40
        right = dca_box[i] if i < len(dca_box) else ""
        print(f"  {left}  {right}")

    print()

    # Portfolio Chart
    print(color("  ┌─ PORTFOLIO VALUE (30 day) " + "─" * 40 + "┐", "white"))
    if portfolio_history:
        values = [p["total_value_usd"] for p in reversed(portfolio_history)]
        chart = draw_mini_chart(values, width=60, height=6)
        for line in chart:
            print(f"  │{line:<67}│")
    else:
        print("  │  No portfolio history yet...                                     │")
    print("  └" + "─" * 68 + "┘")

    print()

    # Recent Trades
    print(color("  ┌─ RECENT TRADES " + "─" * 51 + "┐", "white"))
    if trades:
        print(f"  │ {'Time':<12} {'Side':<6} {'Amount':<14} {'Price':<12} {'Value':<12} │")
        print(f"  │ {'-'*12} {'-'*6} {'-'*14} {'-'*12} {'-'*12} │")
        for trade in trades[:5]:
            ts = datetime.fromtimestamp(trade["timestamp"]).strftime("%H:%M:%S")
            side_color = "green" if trade["side"] == "buy" else "red"
            side = color(trade["side"].upper(), side_color)
            # Pad to account for color codes
            side_padded = f"{side}{' ' * (6 - len(trade['side']))}"
            print(f"  │ {ts:<12} {side_padded} {trade['amount']:<14.6f} ${trade['price']:<11.2f} ${trade['value']:<11.2f} │")
    else:
        print("  │  No trades yet...                                                 │")
    print("  └" + "─" * 68 + "┘")

    print()

    # 30-day Stats
    stats_line = (
        f"  30-Day Stats: "
        f"Trades: {color(str(stats.get('total_trades', 0)), 'cyan')} | "
        f"Bought: {color(format_currency(stats.get('total_bought_usd', 0)), 'green')} | "
        f"Sold: {color(format_currency(stats.get('total_sold_usd', 0)), 'red')} | "
        f"Fees: {format_currency(stats.get('total_fees_usd', 0))}"
    )
    print(stats_line)

    print()
    print(color(f"  Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "gray"))
    print(color("  Press Ctrl+C to exit", "gray"))


def _time_until_next_buy(last_buy_time: float) -> str:
    """Calculate time until next DCA buy."""
    if last_buy_time == 0:
        return "Now"

    next_buy = last_buy_time + (24 * 3600)  # 24 hours
    remaining = next_buy - time.time()

    if remaining <= 0:
        return "Now"

    hours = int(remaining // 3600)
    minutes = int((remaining % 3600) // 60)
    return f"{hours}h {minutes}m"


def run_dashboard(refresh_interval: int = 5):
    """Run dashboard with auto-refresh."""
    try:
        while True:
            render_dashboard()
            time.sleep(refresh_interval)
    except KeyboardInterrupt:
        print("\n  Dashboard closed.")
        sys.exit(0)


if __name__ == "__main__":
    run_dashboard()
