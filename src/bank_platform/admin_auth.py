"""Interim gate for endpoints that must be admin/staff-only before real IAM
exists (Phase 6 - Auth & Authorisation, not started). Checks a static shared
secret header against ADMIN_API_KEY in .env. This is NOT real
authentication or authorisation - no identity, no roles, no audit trail -
just enough to keep an elevated-access endpoint unreachable by an ordinary
caller (customer or agent) in the meantime. Replace with real IAM in
Phase 6, don't extend this pattern to new endpoints.
"""

import os

from fastapi import Header, HTTPException


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    expected = os.environ.get("ADMIN_API_KEY")
    if not expected or x_admin_key != expected:
        raise HTTPException(status_code=403, detail="Admin access required")
