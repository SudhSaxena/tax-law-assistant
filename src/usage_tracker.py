import time
from cache import get_connection

# claude-haiku-4-5-20251001 pricing as of Sep 2026 — update if pricing changes
INPUT_PRICE_PER_MILLION = 1.00
OUTPUT_PRICE_PER_MILLION = 5.00


def init_usage_table():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS request_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                cache_hit INTEGER NOT NULL,
                input_tokens INTEGER,
                output_tokens INTEGER,
                estimated_cost_usd REAL,
                flagged_injection INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL
            )
        """)
        conn.commit()


def estimate_cost(input_tokens, output_tokens):
    input_cost = (input_tokens / 1_000_000) * INPUT_PRICE_PER_MILLION
    output_cost = (output_tokens / 1_000_000) * OUTPUT_PRICE_PER_MILLION
    return round(input_cost + output_cost, 6)


def log_usage(question, endpoint, cache_hit, input_tokens=None, output_tokens=None, flagged_injection=False):
    """Logs one request's usage. Cache hits pass input_tokens=output_tokens=None
    (zero real API cost) so the table also captures how many requests were
    served free from cache — useful later for a "cost saved by caching" metric.
    """
    cost = None
    if input_tokens is not None and output_tokens is not None:
        cost = estimate_cost(input_tokens, output_tokens)

    with get_connection() as conn:
        conn.execute(
            """INSERT INTO request_usage
               (question, endpoint, cache_hit, input_tokens, output_tokens, estimated_cost_usd, flagged_injection, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (question, endpoint, int(cache_hit), input_tokens, output_tokens, cost, int(flagged_injection), time.time()),
        )
        conn.commit()

    return cost


def get_usage_summary():
    """Quick aggregate for sanity-checking: total requests, cache hit rate,
    total estimated spend. Not wired into the API yet — a dashboard (V2.0)
    would build on this.
    """
    with get_connection() as conn:
        row = conn.execute("""
            SELECT
                COUNT(*) as total_requests,
                SUM(cache_hit) as cache_hits,
                SUM(COALESCE(estimated_cost_usd, 0)) as total_cost
            FROM request_usage
        """).fetchone()
    return {
        "total_requests": row[0],
        "cache_hits": row[1] or 0,
        "cache_hit_rate": round((row[1] or 0) / row[0], 3) if row[0] else 0,
        "total_estimated_cost_usd": round(row[2] or 0, 4),
    }


init_usage_table()