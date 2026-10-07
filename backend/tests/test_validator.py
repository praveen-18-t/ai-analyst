import pytest

from app.sql.validator import SQLValidationError, validate

T = {"sales", "customers"}


def ok(sql, **kw):
    return validate(sql, T, **kw)


def test_select_gets_limit():
    assert "LIMIT 10000" in ok('SELECT * FROM "sales"')


def test_limit_is_capped():
    assert "LIMIT 50" in ok("SELECT * FROM sales LIMIT 50", max_rows=100)
    assert "LIMIT 100" in ok("SELECT * FROM sales LIMIT 999999", max_rows=100)


def test_cte_and_join_allowed():
    ok("WITH a AS (SELECT * FROM sales) SELECT a.* FROM a JOIN customers c ON a.id=c.id")


@pytest.mark.parametrize("sql", [
    "DROP TABLE sales",
    "DELETE FROM sales",
    "INSERT INTO sales VALUES (1)",
    "UPDATE sales SET x=1",
    "CREATE TABLE x AS SELECT 1",
    "SELECT 1; DROP TABLE sales",
    "COPY sales TO '/tmp/x.csv'",
    "ATTACH 'x.db'",
    "PRAGMA database_list",
    "SET enable_external_access=true",
    "SELECT * FROM secrets",
    "SELECT * FROM read_csv('/etc/passwd')",
    "SELECT * FROM '/etc/passwd'",
    "SELECT * FROM information_schema.tables",
    "SELECT * FROM main.sales",
    "SELECT getenv('HOME')",
    "SELECT * FROM duckdb_settings()",
    "SELECT * FROM sales WHERE x IN (SELECT y FROM read_parquet('a.parquet'))",
    "",
])
def test_rejected(sql):
    with pytest.raises(SQLValidationError):
        ok(sql)
