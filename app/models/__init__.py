"""Query functions, grouped by table. Each function takes a
sqlite3.Connection explicitly rather than reaching for a global, so
tests can pass a throwaway in-memory connection instead of touching the
real database file."""
