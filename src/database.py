import json
import logging
import time
from pathlib import Path
from typing import Optional
import sqlite3
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "trading_bot.db"


@contextmanager
def get_connection():
    """Get a database connection with context manager."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database() -> None:
    """Initialize database tables."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Orders table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                type TEXT NOT NULL,
                price REAL,
                amount REAL NOT NULL,
                filled REAL DEFAULT 0,
                status TEXT NOT NULL,
                strategy TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)

        # Trades table (filled orders)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                price REAL NOT NULL,
                amount REAL NOT NULL,
                value REAL NOT NULL,
                fee REAL DEFAULT 0,
                strategy TEXT,
                timestamp REAL NOT NULL
            )
        """)

        # Portfolio snapshots
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                total_value_usd REAL NOT NULL,
                balances_json TEXT NOT NULL,
                prices_json TEXT NOT NULL
            )
        """)

        # Bot state (for persistence across restarts)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
        """)

        # Strategy state
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_state (
                strategy_name TEXT PRIMARY KEY,
                state_json TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
        """)

        logger.info(f"Database initialized at {DB_PATH}")


def save_order(
    order_id: str,
    symbol: str,
    side: str,
    order_type: str,
    price: Optional[float],
    amount: float,
    status: str,
    strategy: Optional[str] = None,
) -> None:
    """Save or update an order."""
    now = time.time()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO orders (id, symbol, side, type, price, amount, status, strategy, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (order_id, symbol, side, order_type, price, amount, status, strategy, now, now),
        )


def update_order_status(order_id: str, status: str, filled: float = 0) -> None:
    """Update order status."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE orders SET status = ?, filled = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, filled, time.time(), order_id),
        )


def get_open_orders() -> list[dict]:
    """Get all open orders from database."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE status = 'open'")
        return [dict(row) for row in cursor.fetchall()]


def save_trade(
    order_id: str,
    symbol: str,
    side: str,
    price: float,
    amount: float,
    fee: float = 0,
    strategy: Optional[str] = None,
) -> None:
    """Record a completed trade."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO trades (order_id, symbol, side, price, amount, value, fee, strategy, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (order_id, symbol, side, price, amount, price * amount, fee, strategy, time.time()),
        )


def get_trades(
    symbol: Optional[str] = None,
    since: Optional[float] = None,
    limit: int = 100,
) -> list[dict]:
    """Get trade history."""
    with get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM trades WHERE 1=1"
        params = []

        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)

        if since:
            query += " AND timestamp >= ?"
            params.append(since)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def save_portfolio_snapshot(
    total_value: float, balances: dict, prices: dict
) -> None:
    """Save a portfolio snapshot."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO portfolio_snapshots (timestamp, total_value_usd, balances_json, prices_json)
            VALUES (?, ?, ?, ?)
            """,
            (time.time(), total_value, json.dumps(balances), json.dumps(prices)),
        )


def get_portfolio_history(since: Optional[float] = None, limit: int = 1000) -> list[dict]:
    """Get portfolio value history."""
    with get_connection() as conn:
        cursor = conn.cursor()

        if since:
            cursor.execute(
                """
                SELECT * FROM portfolio_snapshots
                WHERE timestamp >= ?
                ORDER BY timestamp DESC LIMIT ?
                """,
                (since, limit),
            )
        else:
            cursor.execute(
                "SELECT * FROM portfolio_snapshots ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )

        results = []
        for row in cursor.fetchall():
            d = dict(row)
            d["balances"] = json.loads(d.pop("balances_json"))
            d["prices"] = json.loads(d.pop("prices_json"))
            results.append(d)
        return results


def save_bot_state(key: str, value: dict) -> None:
    """Save bot state."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO bot_state (key, value_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = excluded.updated_at
            """,
            (key, json.dumps(value), time.time()),
        )


def get_bot_state(key: str) -> Optional[dict]:
    """Get bot state."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value_json FROM bot_state WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row:
            return json.loads(row["value_json"])
        return None


def save_strategy_state(strategy_name: str, state: dict) -> None:
    """Save strategy state."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO strategy_state (strategy_name, state_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(strategy_name) DO UPDATE SET
                state_json = excluded.state_json,
                updated_at = excluded.updated_at
            """,
            (strategy_name, json.dumps(state), time.time()),
        )


def get_strategy_state(strategy_name: str) -> Optional[dict]:
    """Get strategy state."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT state_json FROM strategy_state WHERE strategy_name = ?",
            (strategy_name,),
        )
        row = cursor.fetchone()
        if row:
            return json.loads(row["state_json"])
        return None


def get_performance_stats(days: int = 30) -> dict:
    """Calculate performance statistics."""
    since = time.time() - (days * 86400)

    with get_connection() as conn:
        cursor = conn.cursor()

        # Get trade stats
        cursor.execute(
            """
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN side = 'buy' THEN value ELSE 0 END) as total_bought,
                SUM(CASE WHEN side = 'sell' THEN value ELSE 0 END) as total_sold,
                SUM(fee) as total_fees
            FROM trades
            WHERE timestamp >= ?
            """,
            (since,),
        )
        trade_stats = dict(cursor.fetchone())

        # Get portfolio change
        cursor.execute(
            """
            SELECT total_value_usd FROM portfolio_snapshots
            WHERE timestamp >= ?
            ORDER BY timestamp ASC LIMIT 1
            """,
            (since,),
        )
        start_row = cursor.fetchone()
        start_value = start_row["total_value_usd"] if start_row else 0

        cursor.execute(
            "SELECT total_value_usd FROM portfolio_snapshots ORDER BY timestamp DESC LIMIT 1"
        )
        end_row = cursor.fetchone()
        end_value = end_row["total_value_usd"] if end_row else 0

        pnl = end_value - start_value if start_value > 0 else 0
        pnl_pct = (pnl / start_value * 100) if start_value > 0 else 0

        return {
            "period_days": days,
            "total_trades": trade_stats["total_trades"] or 0,
            "total_bought_usd": trade_stats["total_bought"] or 0,
            "total_sold_usd": trade_stats["total_sold"] or 0,
            "total_fees_usd": trade_stats["total_fees"] or 0,
            "starting_value_usd": start_value,
            "ending_value_usd": end_value,
            "pnl_usd": pnl,
            "pnl_pct": pnl_pct,
        }
