"""
Shared Neo4j async driver for VeriFarm.
"""

import os
from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase
load_dotenv()

NEO4J_URI      = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER     = os.environ.get("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

_driver = AsyncGraphDatabase.driver(NEO4J_URI, 
auth=(NEO4J_USER, NEO4J_PASSWORD),
connection_acquisition_timeout=60,connection_timeout=30)


async def close_driver():
    await _driver.close()


async def run_query(cypher: str, params: dict | None = None):
    """Run a read query and return records."""
    async with _driver.session(database=NEO4J_DATABASE) as session:
        result = await session.run(cypher, params or {})
        return await result.data()


async def run_write(cypher: str, params: dict | None = None):
    """Run a write query."""
    async with _driver.session(database=NEO4J_DATABASE) as session:
        result = await session.run(cypher, params or {})
        return await result.data()