"""Read-only guard for LLM-generated Cypher (the free-form fallback path).

The Hybrid agent prefers vetted, parameterized query tools (``app.agent.tools``).
For genuinely open-ended questions it may fall back to LLM-authored Cypher — and
that text must never be trusted to only read. This module is the safety boundary:

  * :func:`assert_read_only` rejects any statement containing a write/admin
    clause (CREATE, MERGE, DELETE, SET, REMOVE, DROP, CALL ... write procs, ...).
  * :func:`run_read_query` executes a vetted statement inside an explicit Neo4j
    **read** transaction (``execute_read``), with a hard row cap so a runaway
    query can't stream the whole graph back to the model.

Defense in depth: even though ``execute_read`` already forbids writes at the
transaction level (Neo4j raises on a write in a read tx), we reject suspicious
text *before* it reaches the database so the failure is fast and legible.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from neo4j import Driver

from app.database.neo4j_client import DEFAULT_DATABASE

logger = logging.getLogger(__name__)

# Hard cap on rows returned to the model regardless of the query's own LIMIT.
MAX_ROWS = 200

# Write / schema / admin keywords that must never appear in a read query.
# Matched as whole words, case-insensitively.
_FORBIDDEN_KEYWORDS = (
    "CREATE", "MERGE", "DELETE", "DETACH", "SET", "REMOVE",
    "DROP", "FOREACH", "LOAD CSV", "CALL DBMS", "CALL DB.CREATE",
)

# Write-capable APOC procedures (read procs like apoc.map.* / apoc.coll.* are fine).
_FORBIDDEN_PATTERNS = (
    re.compile(r"\bapoc\.(create|merge|refactor|periodic|trigger|cypher\.runWrite)", re.I),
    re.compile(r"\bdbms\.", re.I),
)

_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)


class UnsafeCypherError(ValueError):
    """Raised when a generated Cypher statement is not provably read-only."""


def _strip_comments(cypher: str) -> str:
    """Remove comments so a keyword hidden in a comment can't smuggle past us
    — and a forbidden keyword can't be *evaded* by hiding the real one."""
    return _BLOCK_COMMENT.sub(" ", _LINE_COMMENT.sub(" ", cypher))


def assert_read_only(cypher: str) -> str:
    """Validate that ``cypher`` is a single, read-only statement.

    Returns the original statement on success; raises :class:`UnsafeCypherError`
    otherwise. The check is conservative — it would rather reject a benign-but-
    unusual query than admit a write.
    """
    if not cypher or not cypher.strip():
        raise UnsafeCypherError("Empty Cypher statement.")

    cleaned = _strip_comments(cypher)

    # Reject stacked statements (a trailing ';' on a lone statement is allowed).
    if cleaned.strip().rstrip(";").count(";"):
        raise UnsafeCypherError("Multiple statements are not allowed.")

    upper = cleaned.upper()
    for keyword in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", upper):
            raise UnsafeCypherError(f"Write/admin keyword not allowed: {keyword!r}.")

    for pattern in _FORBIDDEN_PATTERNS:
        if pattern.search(cleaned):
            raise UnsafeCypherError("Write-capable procedure not allowed.")

    return cypher


def run_read_query(
    driver: Driver,
    cypher: str,
    params: dict[str, Any] | None = None,
    database: str = DEFAULT_DATABASE,
    max_rows: int = MAX_ROWS,
) -> list[dict[str, Any]]:
    """Validate then execute a read-only Cypher query, capped at ``max_rows``.

    Runs inside ``session.execute_read`` so Neo4j itself enforces read-only at
    the transaction layer, on top of :func:`assert_read_only`'s static check.
    """
    assert_read_only(cypher)
    params = params or {}

    def _work(tx) -> list[dict[str, Any]]:
        result = tx.run(cypher, **params)
        rows: list[dict[str, Any]] = []
        for record in result:
            rows.append(record.data())
            if len(rows) >= max_rows:
                break
        return rows

    with driver.session(database=database) as session:
        rows = session.execute_read(_work)
    logger.info("Read query returned %d row(s) (cap %d).", len(rows), max_rows)
    return rows
