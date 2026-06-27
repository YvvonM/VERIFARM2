"""The analytical path's single tool: LLM-authored, read-only Cypher.

Strict Pydantic tool schema (``CypherExecutionTool``) forces the model to supply
both the query *and its rationale* before execution — which makes the agent's
reasoning inspectable and debugging far easier. The schema is bound onto the
model with ``ChatOpenAI.bind_tools([CypherExecutionTool])`` so the model either
returns a valid {query, rationale} tool call or a final answer. Execution is
delegated to :mod:`app.agent.cypher_guard`, so the naive "keyword in string"
check from the blueprint is replaced by word-boundary matching, comment
stripping, stacked-statement rejection, a forced **read transaction**, and a
hard row cap.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.agent.cypher_guard import UnsafeCypherError, run_read_query
from app.database.neo4j_client import get_shared_driver

logger = logging.getLogger(__name__)


class CypherExecutionTool(BaseModel):
    """Executes a strictly read-only Cypher query against the VeriFarm database."""

    query: str = Field(
        ...,
        description="The Cypher query to execute. MUST strictly adhere to the reified "
        "schema and be read-only (no CREATE/MERGE/SET/DELETE/REMOVE). Prefer returning "
        "named columns the UI can render, e.g. RETURN f.id AS farmer_id, c.value_numeric AS hectares.",
    )
    rationale: str = Field(
        ...,
        description="A brief explanation of why this query accurately answers the user's request.",
    )


def execute_read_only_cypher(tool_call: CypherExecutionTool) -> list[dict[str, Any]]:
    """Validate and run the LLM-generated Cypher; never raise into the loop.

    Returns the result rows, or a single ``{"error": ...}`` row that is fed back
    to the model so it can correct itself on the next ReAct step.
    """
    try:
        rows = run_read_query(get_shared_driver(), tool_call.query)
        logger.info("Analytical Cypher returned %d row(s). Rationale: %s",
                    len(rows), tool_call.rationale)
        return rows
    except UnsafeCypherError as exc:
        logger.warning("Rejected unsafe Cypher: %s", exc)
        return [{"error": f"Query rejected (read-only only): {exc}"}]
    except Exception as exc:  # noqa: BLE001 - surface to the model, not the user.
        logger.exception("Cypher execution failed.")
        return [{"error": f"Cypher execution failed: {exc}"}]
