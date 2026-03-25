"""
Director security limits and rate-limit protections.
Centralized constants used by agent.py and other modules.
"""

# Tool loop limits — no hard cap on tool calls, only iteration limit matters
MAX_TOOL_CALLS_PER_SESSION = 9999  # effectively unlimited
MAX_ITERATIONS_PER_SESSION = 30

# Token / result limits
MAX_RESULT_CHARS = 6_000
MAX_MEMORY_RESULTS = 10
MAX_DB_RESULTS = 50

# Pipeline safety
MAX_DAILY_TEST_PIPELINES = 5
MAX_CONCURRENT_TEST_PIPELINES = 2

# A/B test safety
MAX_DAILY_AB_TESTS = 2

# Notification spam prevention
MAX_NOTIFICATIONS_PER_HOUR = 5

# Gemini API rate limit retry
GEMINI_RETRY_DELAYS = [30, 30, 60]
GEMINI_MAX_RETRIES = 3

# Write protections
BLOCKED_TABLES_FOR_WRITE = frozenset([
    "jobs", "clips", "transcripts", "pipeline_audit_log",
    "channels",  # channel_dna is separate — controlled by _update_channel_dna
])

ALLOWED_WRITE_TABLES = frozenset([
    "director_memory", "director_recommendations", "director_conversations",
    "director_events", "director_analyses", "director_decision_journal",
    "director_test_runs", "director_cross_module_signals", "director_prompt_lab",
])


def validate_table_write(table_name: str) -> bool:
    """Check if Director is allowed to write to this table."""
    if table_name in BLOCKED_TABLES_FOR_WRITE:
        return False
    return table_name in ALLOWED_WRITE_TABLES


def clamp_db_results(sql: str, max_rows: int = MAX_DB_RESULTS) -> str:
    """Add LIMIT to SQL if not present."""
    if "LIMIT" not in sql.upper():
        return sql.rstrip("; \n") + f" LIMIT {max_rows}"
    return sql
