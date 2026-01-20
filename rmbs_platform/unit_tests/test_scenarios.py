"""
Scenario Management Tests
=========================

Unit tests for scenario library CRUD operations.

Tests cover the complete scenario lifecycle:
- Create new scenarios
- List and filter scenarios
- Update scenario parameters
- Approve scenarios for production use
- Archive inactive scenarios
- Soft-delete obsolete scenarios
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from rmbs_platform.api_main import app

client = TestClient(app)


def test_create_and_list_scenario() -> None:
    """
    Test complete scenario lifecycle: create, list, update, approve, archive, delete.

    This test exercises all scenario management operations in sequence
    to validate the full workflow.
    """
    # Create scenario
    payload = {
        "name": "Base Case",
        "description": "Baseline scenario for testing",
        "params": {"deal_id": "DEAL_1", "cpr": 0.1, "cdr": 0.02, "severity": 0.4},
        "created_by": "unit-test",
        "tags": ["investor"],
    }
    res = client.post(
        "/scenarios", json=payload, headers={"X-User-Role": "investor"}
    )
    assert res.status_code == 200
    scenario_id = res.json().get("scenario_id")
    assert scenario_id

    # List scenarios and verify presence
    res_list = client.get("/scenarios", headers={"X-User-Role": "investor"})
    assert res_list.status_code == 200
    scenarios = res_list.json().get("scenarios", [])
    assert any(s.get("scenario_id") == scenario_id for s in scenarios)

    # Verify version history
    res_versions = client.get(
        f"/scenarios/{scenario_id}/versions", headers={"X-User-Role": "investor"}
    )
    assert res_versions.status_code == 200
    versions = res_versions.json().get("versions", [])
    assert versions

    # Update scenario
    update_payload = {
        "name": "Base Case v2",
        "description": "Updated scenario",
        "params": {"deal_id": "DEAL_1", "cpr": 0.12, "cdr": 0.02, "severity": 0.45},
        "updated_by": "unit-test",
        "tags": ["investor", "updated"],
    }
    res_update = client.put(
        f"/scenarios/{scenario_id}",
        json=update_payload,
        headers={"X-User-Role": "investor"},
    )
    assert res_update.status_code == 200
    updated = res_update.json().get("scenario", {})
    assert updated.get("name") == "Base Case v2"

    # Approve scenario
    res_approve = client.post(
        f"/scenarios/{scenario_id}/approve",
        json={"actor": "approver"},
        headers={"X-User-Role": "investor"},
    )
    assert res_approve.status_code == 200
    assert res_approve.json().get("scenario", {}).get("status") == "approved"

    # Archive scenario
    res_archive = client.post(
        f"/scenarios/{scenario_id}/archive",
        json={"actor": "archiver"},
        headers={"X-User-Role": "investor"},
    )
    assert res_archive.status_code == 200
    assert res_archive.json().get("scenario", {}).get("status") == "archived"

    # Soft-delete scenario
    res_delete = client.delete(
        f"/scenarios/{scenario_id}",
        params={"actor": "deleter"},
        headers={"X-User-Role": "investor"},
    )
    assert res_delete.status_code == 200
    assert res_delete.json().get("scenario", {}).get("status") == "deleted"
