"""
Audit Bundle Export Tests
=========================

Unit tests for the audit bundle download functionality.

Tests verify that:
- Audit bundles are returned as valid ZIP archives
- Required files are included (metadata, tape, events)
- Metadata contains expected fields
"""

from __future__ import annotations

import json
import zipfile
from io import BytesIO

from fastapi.testclient import TestClient

from rmbs_platform.api_main import (
    COLLATERAL_DB,
    DEALS_DB,
    JOBS_DB,
    PERFORMANCE_DB,
    app,
)

client = TestClient(app)


def test_audit_bundle_download() -> None:
    """
    Test that audit bundle download returns a valid ZIP with required contents.

    The bundle should include:
    - metadata.json: Job metadata and request parameters
    - detailed_tape.csv: Period-by-period simulation results
    - audit_events.jsonl: Relevant audit trail events
    """
    deal_id = "AUDIT_DEAL_1"
    DEALS_DB[deal_id] = {
        "meta": {"deal_id": deal_id},
        "bonds": [],
        "waterfalls": {},
    }
    COLLATERAL_DB[deal_id] = {"original_balance": 1000}
    PERFORMANCE_DB[deal_id] = [{"Period": 1, "InterestCollected": 10.0}]

    job_id = "job-audit-1"
    JOBS_DB[job_id] = {
        "status": "COMPLETED",
        "created_at": "2026-01-18T00:00:00Z",
        "request": {
            "deal_id": deal_id,
            "cpr": 0.1,
            "cdr": 0.01,
            "severity": 0.4,
        },
        "data": [{"Period": 1, "Var.PoolEndBalance": 990.0}],
        "reconciliation": [],
        "actuals_data": [],
        "actuals_summary": [],
        "simulated_summary": [],
        "last_actual_period": 1,
        "warnings": [],
        "model_info": {"ml_requested": False},
    }

    res = client.get(
        f"/audit/run/{job_id}/bundle", headers={"X-User-Role": "auditor"}
    )
    assert res.status_code == 200

    bundle = zipfile.ZipFile(BytesIO(res.content))
    names = set(bundle.namelist())
    assert "metadata.json" in names
    assert "detailed_tape.csv" in names
    assert "audit_events.jsonl" in names

    metadata = json.loads(bundle.read("metadata.json"))
    assert metadata.get("deal_id") == deal_id
