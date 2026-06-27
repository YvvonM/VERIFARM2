"""External API client layer (Sprint 1 — API Adapter Pattern).

  http_client — resilient async httpx client (retries, 429 backoff, OAuth2/Bearer)
  auth        — BearerAuth / OAuth2ClientCredentials strategies
  cache       — idempotent lookup cache (memory / Redis)
  fmis        — FMIS GraphQL → strict Pydantic → reified bundle
  (registry lookups live in app.verification.registry_lookup)
"""

from app.clients.auth import BearerAuth, OAuth2ClientCredentials
from app.clients.http_client import APIClientError, AsyncAPIClient

__all__ = ["AsyncAPIClient", "APIClientError", "BearerAuth", "OAuth2ClientCredentials"]
