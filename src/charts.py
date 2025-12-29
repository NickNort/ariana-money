#!/usr/bin/env python3
"""
Generate visual charts for the trading bot.
"""

import os
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter

from src.database import (
    get_portfolio_history,
    get_trades,
    get_performance_stats,
    get_bot_state,
    get_strategy_state,
)

# Use non-interactive backend for server environments
plt.switch_backend('Agg')

CHART_DIR = Path(__file__).parent.parent / "charts"


def ensure_chart_dir():
    """Create charts directory if it doesn't exist."""
    CHART_DIR.mkdir(exist_ok=True)


def currency_formatter(x, p):
    """Format y-axis as currency."""
    return f'${x:,.2f}'


def generate_portfolio_chart(output_path: str = None) -> str:
    """Generate portfolio value over time chart."""
    ensure_chart_dir()
    output_path = output_path or str(CHART_DIR / "portfolio.png")

    history = get_portfolio_history(limit=500)

    if not history or len(history) < 2:
        # Generate placeholder chart
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.text(0.5, 0.5, 'Not enough data yet...\nRun the bot longer to see portfolio history.',
                ha='center', va='center', fontsize=14, color='gray',
                transform=ax.transAxes)
        ax.set_facecolor('#1a1a2e')
        fig.patch.set_facecolor('#0f0f1a')
        plt.savefig(output_path, dpi=100, bbox_inches='tight', facecolor='#0f0f1a')
        plt.close()
        return output_path

    # Parse data (history is reversed - newest first)
    history = list(reversed(history))
    timestamps = [datetime.fromtimestamp(p["timestamp"]) for p in history]
    values = [p["total_value_usd"] for p in history]

    # Create figure with dark theme
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor('#0f0f1a')
    ax.set_facecolor('#1a1a2e')

    # Plot portfolio value
    ax.plot(timestamps, values, color='#00d4ff', linewidth=2, label='Portfolio Value')
    ax.fill_between(timestamps, values, alpha=0.3, color='#00d4ff')

    # Add initial value line
    if values:
        ax.axhline(y=values[0], color='#666666', linestyle='--', linewidth=1, label=f'Initial: ${values[0]:.2f}')

    # Styling
    ax.set_title('Portfolio Value Over Time', fontsize=16, color='white', pad=20)
    ax.set_xlabel('Time', fontsize=12, color='white')
    ax.set_ylabel('Value (USD)', fontsize=12, color='white')
    ax.yaxis.set_major_formatter(FuncFormatter(currency_formatter))
    ax.tick_params(colors='white')
    ax.spines['bottom'].set_color('#333333')
    ax.spines['top'].set_color('#333333')
    ax.spines['left'].set_color('#333333')
    ax.spines['right'].set_color('#333333')
    ax.grid(True, alpha=0.2, color='#333333')
    ax.legend(facecolor='#1a1a2e', edgecolor='#333333', labelcolor='white')

    # Format x-axis dates
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
    plt.xticks(rotation=45)

    plt.tight_layout()
    plt.savefig(output_path, dpi=100, bbox_inches='tight', facecolor='#0f0f1a')
    plt.close()

    return output_path


def generate_trades_chart(output_path: str = None) -> str:
    """Generate chart showing trade history."""
    ensure_chart_dir()
    output_path = output_path or str(CHART_DIR / "trades.png")

    trades = get_trades(limit=100)

    if not trades:
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.text(0.5, 0.5, 'No trades yet...',
                ha='center', va='center', fontsize=14, color='gray',
                transform=ax.transAxes)
        ax.set_facecolor('#1a1a2e')
        fig.patch.set_facecolor('#0f0f1a')
        plt.savefig(output_path, dpi=100, bbox_inches='tight', facecolor='#0f0f1a')
        plt.close()
        return output_path

    # Parse data
    trades = list(reversed(trades))
    timestamps = [datetime.fromtimestamp(t["timestamp"]) for t in trades]
    prices = [t["price"] for t in trades]
    sides = [t["side"] for t in trades]
    values = [t["value"] for t in trades]

    # Create figure
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), height_ratios=[2, 1])
    fig.patch.set_facecolor('#0f0f1a')

    # Top chart: Price with buy/sell markers
    ax1.set_facecolor('#1a1a2e')
    ax1.plot(timestamps, prices, color='#888888', linewidth=1, alpha=0.5)

    for i, (ts, price, side, val) in enumerate(zip(timestamps, prices, sides, values)):
        if side == 'buy':
            ax1.scatter(ts, price, color='#00ff88', s=val*50, marker='^', zorder=5, alpha=0.8)
        else:
            ax1.scatter(ts, price, color='#ff4444', s=val*50, marker='v', zorder=5, alpha=0.8)

    ax1.set_title('Trade History - Price & Execution Points', fontsize=16, color='white', pad=20)
    ax1.set_ylabel('Price (USD)', fontsize=12, color='white')
    ax1.yaxis.set_major_formatter(FuncFormatter(currency_formatter))
    ax1.tick_params(colors='white')
    ax1.spines['bottom'].set_color('#333333')
    ax1.spines['top'].set_color('#333333')
    ax1.spines['left'].set_color('#333333')
    ax1.spines['right'].set_color('#333333')
    ax1.grid(True, alpha=0.2, color='#333333')

    # Add legend
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker='^', color='w', markerfacecolor='#00ff88', markersize=10, label='Buy', linestyle='None'),
        Line2D([0], [0], marker='v', color='w', markerfacecolor='#ff4444', markersize=10, label='Sell', linestyle='None'),
    ]
    ax1.legend(handles=legend_elements, facecolor='#1a1a2e', edgecolor='#333333', labelcolor='white')

    # Bottom chart: Trade values as bar chart
    ax2.set_facecolor('#1a1a2e')
    colors = ['#00ff88' if s == 'buy' else '#ff4444' for s in sides]
    ax2.bar(timestamps, values, color=colors, alpha=0.7, width=0.01)

    ax2.set_title('Trade Values', fontsize=14, color='white', pad=10)
    ax2.set_xlabel('Time', fontsize=12, color='white')
    ax2.set_ylabel('Value (USD)', fontsize=12, color='white')
    ax2.yaxis.set_major_formatter(FuncFormatter(currency_formatter))
    ax2.tick_params(colors='white')
    ax2.spines['bottom'].set_color('#333333')
    ax2.spines['top'].set_color('#333333')
    ax2.spines['left'].set_color('#333333')
    ax2.spines['right'].set_color('#333333')
    ax2.grid(True, alpha=0.2, color='#333333')

    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
    plt.xticks(rotation=45)

    plt.tight_layout()
    plt.savefig(output_path, dpi=100, bbox_inches='tight', facecolor='#0f0f1a')
    plt.close()

    return output_path


def generate_performance_summary(output_path: str = None) -> str:
    """Generate a performance summary infographic."""
    ensure_chart_dir()
    output_path = output_path or str(CHART_DIR / "summary.png")

    stats = get_performance_stats(days=30)
    risk_state = get_bot_state("risk_manager") or {}
    dca_state = get_strategy_state("DCA(SOL/USD)") or {}
    grid_state = get_strategy_state("Grid(SOL/USD)") or {}

    # Create figure
    fig = plt.figure(figsize=(14, 10))
    fig.patch.set_facecolor('#0f0f1a')

    # Title
    fig.suptitle('Trading Bot Performance Summary', fontsize=24, color='white', y=0.98)

    # Create grid for layout
    gs = fig.add_gridspec(3, 3, hspace=0.4, wspace=0.3, left=0.08, right=0.92, top=0.9, bottom=0.08)

    # Portfolio Value Card
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_facecolor('#1a1a2e')
    ax1.axis('off')
    current_value = stats.get('ending_value_usd', 0)
    ax1.text(0.5, 0.7, 'Portfolio Value', ha='center', va='center', fontsize=12, color='#888888', transform=ax1.transAxes)
    ax1.text(0.5, 0.4, f'${current_value:,.2f}', ha='center', va='center', fontsize=28, color='#00d4ff', fontweight='bold', transform=ax1.transAxes)
    for spine in ax1.spines.values():
        spine.set_edgecolor('#333333')
        spine.set_linewidth(2)

    # Total P&L Card
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.set_facecolor('#1a1a2e')
    ax2.axis('off')
    pnl = stats.get('pnl_usd', 0)
    pnl_pct = stats.get('pnl_pct', 0)
    pnl_color = '#00ff88' if pnl >= 0 else '#ff4444'
    ax2.text(0.5, 0.7, 'Total P&L', ha='center', va='center', fontsize=12, color='#888888', transform=ax2.transAxes)
    sign = '+' if pnl >= 0 else ''
    ax2.text(0.5, 0.4, f'{sign}${pnl:,.2f}', ha='center', va='center', fontsize=28, color=pnl_color, fontweight='bold', transform=ax2.transAxes)
    ax2.text(0.5, 0.15, f'({sign}{pnl_pct:.2f}%)', ha='center', va='center', fontsize=14, color=pnl_color, transform=ax2.transAxes)
    for spine in ax2.spines.values():
        spine.set_edgecolor('#333333')
        spine.set_linewidth(2)

    # Total Trades Card
    ax3 = fig.add_subplot(gs[0, 2])
    ax3.set_facecolor('#1a1a2e')
    ax3.axis('off')
    total_trades = stats.get('total_trades', 0)
    ax3.text(0.5, 0.7, 'Total Trades', ha='center', va='center', fontsize=12, color='#888888', transform=ax3.transAxes)
    ax3.text(0.5, 0.4, f'{total_trades}', ha='center', va='center', fontsize=28, color='#ffaa00', fontweight='bold', transform=ax3.transAxes)
    for spine in ax3.spines.values():
        spine.set_edgecolor('#333333')
        spine.set_linewidth(2)

    # Buy/Sell Breakdown Pie Chart
    ax4 = fig.add_subplot(gs[1, 0])
    ax4.set_facecolor('#1a1a2e')
    bought = stats.get('total_bought_usd', 0)
    sold = stats.get('total_sold_usd', 0)
    if bought > 0 or sold > 0:
        sizes = [bought, sold] if sold > 0 else [bought]
        labels = ['Bought', 'Sold'] if sold > 0 else ['Bought']
        colors = ['#00ff88', '#ff4444'] if sold > 0 else ['#00ff88']
        ax4.pie(sizes, labels=labels, colors=colors, autopct='$%.2f', startangle=90,
                textprops={'color': 'white', 'fontsize': 10})
    ax4.set_title('Buy/Sell Volume', fontsize=14, color='white', pad=10)

    # DCA Stats
    ax5 = fig.add_subplot(gs[1, 1])
    ax5.set_facecolor('#1a1a2e')
    ax5.axis('off')
    ax5.text(0.5, 0.9, 'DCA Strategy', ha='center', va='center', fontsize=14, color='white', fontweight='bold', transform=ax5.transAxes)

    dca_info = [
        f"Avg Price: ${dca_state.get('average_price', 0):.2f}",
        f"Invested: ${dca_state.get('total_invested', 0):.2f}",
        f"SOL Bought: {dca_state.get('total_amount_bought', 0):.6f}",
        f"Buys Today: {dca_state.get('buys_today', 0)}/3",
    ]
    for i, info in enumerate(dca_info):
        ax5.text(0.5, 0.7 - i*0.18, info, ha='center', va='center', fontsize=11, color='#cccccc', transform=ax5.transAxes)
    for spine in ax5.spines.values():
        spine.set_edgecolor('#333333')
        spine.set_linewidth(2)

    # Grid Stats
    ax6 = fig.add_subplot(gs[1, 2])
    ax6.set_facecolor('#1a1a2e')
    ax6.axis('off')
    ax6.text(0.5, 0.9, 'Grid Strategy', ha='center', va='center', fontsize=14, color='white', fontweight='bold', transform=ax6.transAxes)

    grid_info = [
        f"Base Price: ${grid_state.get('base_price', 0):.2f}",
        f"Grid Levels: {grid_state.get('num_levels', 0)}",
        f"Active Orders: {grid_state.get('active_orders', 0)}",
        f"Buy/Sell: {grid_state.get('buy_levels', 0)}/{grid_state.get('sell_levels', 0)}",
    ]
    for i, info in enumerate(grid_info):
        ax6.text(0.5, 0.7 - i*0.18, info, ha='center', va='center', fontsize=11, color='#cccccc', transform=ax6.transAxes)
    for spine in ax6.spines.values():
        spine.set_edgecolor('#333333')
        spine.set_linewidth(2)

    # Risk Status Bar
    ax7 = fig.add_subplot(gs[2, :])
    ax7.set_facecolor('#1a1a2e')
    ax7.axis('off')

    drawdown = risk_state.get('current_drawdown_pct', 0) * 100
    max_drawdown = risk_state.get('max_drawdown_pct', 0.1) * 100
    is_paused = risk_state.get('is_paused', False)

    status_color = '#ff4444' if is_paused else '#00ff88'
    status_text = '⚠ PAUSED' if is_paused else '● ACTIVE'

    ax7.text(0.1, 0.7, 'Risk Status:', ha='left', va='center', fontsize=14, color='white', fontweight='bold', transform=ax7.transAxes)
    ax7.text(0.25, 0.7, status_text, ha='left', va='center', fontsize=14, color=status_color, fontweight='bold', transform=ax7.transAxes)

    ax7.text(0.1, 0.35, f'Current Drawdown: {drawdown:.2f}% / {max_drawdown:.0f}% max', ha='left', va='center', fontsize=12, color='#cccccc', transform=ax7.transAxes)

    # Drawdown progress bar
    bar_width = 0.5
    bar_start = 0.1
    ax7.add_patch(plt.Rectangle((bar_start, 0.05), bar_width, 0.15, facecolor='#333333', transform=ax7.transAxes))
    fill_width = min(bar_width * (drawdown / max_drawdown), bar_width) if max_drawdown > 0 else 0
    bar_color = '#00ff88' if drawdown < max_drawdown * 0.5 else '#ffaa00' if drawdown < max_drawdown * 0.8 else '#ff4444'
    ax7.add_patch(plt.Rectangle((bar_start, 0.05), fill_width, 0.15, facecolor=bar_color, transform=ax7.transAxes))

    for spine in ax7.spines.values():
        spine.set_edgecolor('#333333')
        spine.set_linewidth(2)

    # Timestamp
    fig.text(0.5, 0.02, f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
             ha='center', fontsize=10, color='#666666')

    plt.savefig(output_path, dpi=100, bbox_inches='tight', facecolor='#0f0f1a')
    plt.close()

    return output_path


def generate_all_charts() -> dict[str, str]:
    """Generate all charts and return paths."""
    return {
        "portfolio": generate_portfolio_chart(),
        "trades": generate_trades_chart(),
        "summary": generate_performance_summary(),
    }


if __name__ == "__main__":
    print("Generating charts...")
    paths = generate_all_charts()
    for name, path in paths.items():
        print(f"  {name}: {path}")
    print("Done!")
