"""Inbound source connectors — pull data from external systems into the graph.

A connector talks to an external system (a pooled async SQL registry, a
warehouse, an API) and yields raw rows. Mapping rows onto the reified contract is
the adapter's job (``app.ingestion.sql_adapters``); enforcing the schema split
and writing is ``app.ingestion.reified_guard``'s. Connectors stay thin.
"""

from app.ingestion.connectors.postgres import (
    SourceNotConfigured,
    dispose_engines,
    fetch_all,
    get_engine,
    stream,
)

__all__ = ["SourceNotConfigured", "get_engine", "stream", "fetch_all", "dispose_engines"]
