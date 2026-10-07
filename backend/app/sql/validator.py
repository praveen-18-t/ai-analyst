"""SQL safety gate. The LLM is untrusted: nothing reaches a database without passing validate()."""
import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError


class SQLValidationError(ValueError):
    pass


_FORBIDDEN_NAMES = [
    "Insert", "Update", "Delete", "Drop", "Create", "Alter", "Command", "Merge", "Copy", "Set",
    "Use", "Pragma", "Attach", "Detach", "Transaction", "Commit", "Rollback", "LoadData", "Grant",
]
FORBIDDEN_NODES = tuple(getattr(exp, n) for n in _FORBIDDEN_NAMES if hasattr(exp, n))
ROOT_TYPES = tuple(
    t for t in (exp.Select, getattr(exp, "Union", None), getattr(exp, "SetOperation", None)) if t is not None
)
DENY_FUNCS = {
    "getenv", "current_setting", "glob", "query", "query_table", "sniff_csv", "load", "install",
    "pg_read_file", "pg_ls_dir", "lo_import", "system", "shell", "http_get", "httpfs", "parquet_scan",
    "csv_scan", "json_scan", "iceberg_scan", "delta_scan", "sqlite_scan", "postgres_scan", "mysql_scan",
}
DENY_PREFIXES = ("read_", "duckdb_", "pragma_", "sqlite_", "pg_")


def validate(sql: str, allowed_tables: set[str], dialect: str = "duckdb", max_rows: int = 10000) -> str:
    """Return a safe, row-capped SQL string or raise SQLValidationError."""
    if not sql or not sql.strip():
        raise SQLValidationError("Empty SQL")
    try:
        statements = [s for s in sqlglot.parse(sql, dialect=dialect) if s is not None]
    except SqlglotError as e:
        raise SQLValidationError(f"SQL parse error: {e}")
    if len(statements) != 1:
        raise SQLValidationError("Exactly one statement is allowed")
    tree = statements[0]
    if not isinstance(tree, ROOT_TYPES):
        raise SQLValidationError("Only SELECT queries are allowed")
    if FORBIDDEN_NODES and tree.find(*FORBIDDEN_NODES):
        raise SQLValidationError("Statement contains forbidden operations")

    allowed = {t.lower() for t in allowed_tables}
    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    for t in tree.find_all(exp.Table):
        if not isinstance(t.this, exp.Identifier):
            raise SQLValidationError("Table functions are not allowed")
        if t.db or t.catalog:
            raise SQLValidationError("Schema-qualified tables are not allowed")
        name = t.name.lower()
        if name not in ctes and name not in allowed:
            raise SQLValidationError(
                f'Table "{t.name}" is not available. Available tables: {", ".join(sorted(allowed))}'
            )

    for f in tree.find_all(exp.Func):
        name = (f.name if isinstance(f, exp.Anonymous) else f.sql_name()).lower()
        if name in DENY_FUNCS or name.startswith(DENY_PREFIXES):
            raise SQLValidationError(f"Function not allowed: {name}")

    limit = tree.args.get("limit")
    n = None
    if limit is not None:
        try:
            n = int(limit.expression.name)
        except (ValueError, AttributeError):
            n = None
    if limit is None or n is None or n > max_rows:
        tree = tree.limit(max_rows)
    return tree.sql(dialect=dialect)
