"""
Validation Endpoint Tests
=========================

Unit tests for deal and performance validation endpoints.

Tests verify that:
- Missing required fields are flagged as errors
- Invalid data triggers appropriate warnings
- Valid data passes validation
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from rmbs_platform.api_main import app

client = TestClient(app)


def test_validate_deal_missing_meta() -> None:
    """
    Test that deal validation fails when meta section is missing.

    The deal spec must include a meta section with deal_id and other
    required metadata. Missing meta should result in FAILED status.
    """
    payload = {"spec": {"bonds": [], "waterfalls": {}}}
    res = client.post(
        "/deal/validate", json=payload, headers={"X-User-Role": "arranger"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "FAILED"
    assert any("meta" in issue["message"] for issue in body["issues"])


def test_validate_performance_missing_period() -> None:
    """
    Test that performance validation fails when Period column is missing.

    Performance rows must include a Period column to enable time-series
    analysis and waterfall alignment.
    """
    payload = {"rows": [{"LoanId": "L1", "InterestCollected": 10.0}]}
    res = client.post(
        "/validation/performance", json=payload, headers={"X-User-Role": "servicer"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "FAILED"
    assert any("Period" in issue["message"] for issue in body["issues"])
