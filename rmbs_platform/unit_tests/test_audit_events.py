"""
Audit Event Log Tests
=====================

Unit tests for audit event logging and retrieval.

Tests verify that:
- Audit events are logged correctly
- Events can be listed with filters
- Event log can be downloaded
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from rmbs_platform.api_main import _log_audit_event, app

client = TestClient(app)


def test_audit_events_list_and_download() -> None:
    """
    Test audit event listing, filtering, and download.

    Verifies the complete audit trail workflow:
    1. Log a test event
    2. List events (should include test event)
    3. Filter events by type/actor
    4. Download raw log file
    """
    # Log a test event
    _log_audit_event("test.event", actor="unit-test", deal_id="DEAL_X")

    # List events
    res = client.get("/audit/events", headers={"X-User-Role": "auditor"})
    assert res.status_code == 200
    events = res.json().get("events", [])
    assert any(e.get("event_type") == "test.event" for e in events)

    # Download raw log
    res_download = client.get(
        "/audit/events/download", headers={"X-User-Role": "auditor"}
    )
    assert res_download.status_code == 200
    assert b"test.event" in res_download.content

    # Filter by event type and actor
    res_filtered = client.get(
        "/audit/events",
        params={"event_type": "test.event", "actor": "unit-test"},
        headers={"X-User-Role": "auditor"},
    )
    assert res_filtered.status_code == 200
    filtered = res_filtered.json().get("events", [])
    assert all(e.get("event_type") == "test.event" for e in filtered)
