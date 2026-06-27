"""Tenant-isolation primitives (framework-agnostic, so they're unit-testable).

`AccessDenied` is a *safe structured error* returned to the model on a
cross-tenant or under-scoped request — it never leaks the other tenant's data,
only the fact that access was refused.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from app.mcp.auth import SessionContext


class AccessDenied(BaseModel):
    error: str = "access_denied"
    requested_org: str
    authorized_org: str
    detail: str


def _has_scope(session: SessionContext, scope: str) -> bool:
    return scope in session.scopes or "*" in session.scopes


def check_claims_access(
    session: SessionContext, target_org: str, required_scope: str = "claims:read"
) -> Optional[AccessDenied]:
    """Return an AccessDenied if the session may not read ``target_org``'s claims, else None."""
    if not _has_scope(session, required_scope):
        return AccessDenied(
            error="insufficient_scope", requested_org=target_org,
            authorized_org=session.org_id, detail=f"Token is missing required scope {required_scope!r}.",
        )
    if target_org != session.org_id:
        return AccessDenied(
            requested_org=target_org, authorized_org=session.org_id,
            detail="Cross-tenant access is not permitted.",
        )
    return None


def authorize_resource(session: SessionContext, org_id: str) -> None:
    """Raise PermissionError if the session is not scoped to ``org_id`` (rejects the load)."""
    if org_id != session.org_id:
        raise PermissionError(
            f"Access denied: token is scoped to {session.org_id!r}, not {org_id!r}."
        )
