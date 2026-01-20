"""
RBAC (Role-Based Access Control) Tests
======================================

Unit tests for verifying role-based access control enforcement.

Tests verify:
- Requests without X-User-Role header are rejected (401)
- Requests with unauthorized roles are rejected (403)
- Requests with authorized roles succeed (200)
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from rmbs_platform.api_main import app

client = TestClient(app)


def test_missing_role_header_rejected() -> None:
    """
    Test that requests without X-User-Role header receive 401 Unauthorized.

    All protected endpoints require the X-User-Role header for RBAC.
    """
    res = client.get("/deals")
    assert res.status_code == 401


def test_wrong_role_rejected() -> None:
    """
    Test that requests with unauthorized roles receive 403 Forbidden.

    The /deals endpoint is accessible to arranger and investor roles,
    so a servicer role should be rejected.
    """
    res = client.get("/deals", headers={"X-User-Role": "servicer"})
    assert res.status_code == 403


def test_allowed_role_passes() -> None:
    """
    Test that requests with authorized roles succeed.

    The investor role should have access to the /deals listing endpoint.
    """
    res = client.get("/deals", headers={"X-User-Role": "investor"})
    assert res.status_code == 200
