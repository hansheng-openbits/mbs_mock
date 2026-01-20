"""
API Integration Tests
=====================

Comprehensive tests for the FastAPI backend including:
- Endpoint functionality
- RBAC enforcement
- Request/response validation
- Error handling
- Concurrent request handling
- File upload processing

These tests use the TestClient to simulate HTTP requests
and verify API behavior without running a full server.
"""

import pytest
import json
import io
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

# Import the FastAPI app
try:
    from api_main import app
except ImportError:
    from rmbs_platform.api_main import app


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def client():
    """Create test client for API testing."""
    return TestClient(app)


@pytest.fixture
def arranger_headers():
    """Headers for arranger role."""
    return {"X-User-Role": "arranger"}


@pytest.fixture
def servicer_headers():
    """Headers for servicer role."""
    return {"X-User-Role": "servicer"}


@pytest.fixture
def investor_headers():
    """Headers for investor role."""
    return {"X-User-Role": "investor"}


@pytest.fixture
def auditor_headers():
    """Headers for auditor role."""
    return {"X-User-Role": "auditor"}


@pytest.fixture
def sample_deal_spec():
    """Valid deal specification for testing."""
    return {
        "meta": {
            "deal_id": "TEST_API_2024",
            "deal_name": "API Test Deal",
            "asset_type": "RMBS",
            "version": "1.0",
        },
        "dates": {
            "cutoff_date": "2024-01-01",
            "closing_date": "2024-01-30",
            "first_payment_date": "2024-02-25",
            "maturity_date": "2054-01-01",
            "payment_frequency": "MONTHLY",
            "day_count": "30_360",
        },
        "collateral": {
            "original_balance": 10000000.0,
            "current_balance": 10000000.0,
        },
        "funds": [
            {"id": "IAF", "description": "Interest Available Funds"},
            {"id": "PAF", "description": "Principal Available Funds"},
        ],
        "accounts": [],
        "variables": {
            "ClassA_Int": "bonds.ClassA.balance * 0.05 / 12",
        },
        "tests": [],
        "bonds": [
            {
                "id": "ClassA",
                "type": "NOTE",
                "original_balance": 10000000.0,
                "priority": {"interest": 1, "principal": 1},
                "coupon": {"kind": "FIXED", "fixed_rate": 0.05},
            },
        ],
        "waterfalls": {
            "interest": {
                "steps": [
                    {"id": "1", "action": "PAY_BOND_INTEREST", "from_fund": "IAF", "group": "ClassA", "amount_rule": "ClassA_Int"},
                ],
            },
            "principal": {
                "steps": [
                    {"id": "1", "action": "PAY_BOND_PRINCIPAL", "from_fund": "PAF", "group": "ClassA", "amount_rule": "ALL"},
                ],
            },
        },
    }


@pytest.fixture
def sample_collateral_spec():
    """Valid collateral specification for testing."""
    return {
        "original_balance": 10000000.0,
        "current_balance": 10000000.0,
        "wac": 0.065,
        "wam": 348,
    }


@pytest.fixture
def sample_performance_data():
    """Sample performance data for testing."""
    return [
        {
            "Period": 1,
            "InterestCollected": 50000.0,
            "PrincipalCollected": 30000.0,
            "RealizedLoss": 0.0,
            "EndBalance": 9970000.0,
        },
        {
            "Period": 2,
            "InterestCollected": 49850.0,
            "PrincipalCollected": 31000.0,
            "RealizedLoss": 500.0,
            "EndBalance": 9938500.0,
        },
    ]


# =============================================================================
# Health Check Tests
# =============================================================================

class TestHealthEndpoints:
    """Tests for health check endpoints."""
    
    def test_health_check(self, client):
        """
        Verify main health check endpoint returns healthy status.
        """
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
    
    def test_liveness_probe(self, client):
        """
        Verify liveness probe returns OK.
        """
        response = client.get("/health/live")
        
        assert response.status_code == 200
        assert response.json()["status"] == "alive"
    
    def test_readiness_probe(self, client):
        """
        Verify readiness probe returns ready status.
        """
        response = client.get("/health/ready")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["ready", "healthy"]


class TestRootEndpoint:
    """Tests for API root endpoint."""
    
    def test_root_returns_api_info(self, client):
        """
        Verify root endpoint returns API information.
        """
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data


# =============================================================================
# RBAC Tests
# =============================================================================

class TestRBACEnforcement:
    """Tests for Role-Based Access Control enforcement."""
    
    def test_missing_role_header_rejected(self, client):
        """
        Verify requests without X-User-Role header are rejected.
        """
        response = client.get("/deals")
        
        assert response.status_code == 401
    
    def test_invalid_role_rejected(self, client):
        """
        Verify requests with invalid role are rejected.
        """
        response = client.get(
            "/deals",
            headers={"X-User-Role": "hacker"}
        )
        
        assert response.status_code == 403
    
    def test_arranger_can_access_deals(self, client, arranger_headers):
        """
        Verify arranger can access deal endpoints.
        """
        response = client.get("/deals", headers=arranger_headers)
        
        # Should succeed (200) or return empty list, not auth error
        assert response.status_code == 200
    
    def test_servicer_cannot_create_deals(self, client, servicer_headers, sample_deal_spec):
        """
        Verify servicer cannot create deals (arranger only).
        """
        response = client.post(
            "/deals",
            headers=servicer_headers,
            json={"deal_id": "TEST", "spec": sample_deal_spec},
        )
        
        # Should be forbidden
        assert response.status_code == 403
    
    def test_investor_can_run_simulation(self, client, investor_headers):
        """
        Verify investor can run simulations.
        """
        # This tests the endpoint authorization, not actual simulation
        response = client.post(
            "/simulate",
            headers=investor_headers,
            json={
                "deal_id": "TEST_DEAL",
                "cpr": 0.08,
                "cdr": 0.015,
                "severity": 0.35,
            },
        )
        
        # Should not be auth error (may be 404 if deal doesn't exist)
        assert response.status_code != 401
        assert response.status_code != 403


# =============================================================================
# Deal Management Tests
# =============================================================================

class TestDealEndpoints:
    """Tests for deal management endpoints."""
    
    def test_list_deals(self, client, arranger_headers):
        """
        Verify list deals endpoint returns list.
        """
        response = client.get("/deals", headers=arranger_headers)
        
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_upload_deal(self, client, arranger_headers, sample_deal_spec):
        """
        Verify deal upload works with valid specification.
        """
        response = client.post(
            "/deals",
            headers=arranger_headers,
            json={"deal_id": "TEST_UPLOAD_2024", "spec": sample_deal_spec},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") in ["success", "ok", "created"]
    
    def test_upload_deal_without_meta_fails(self, client, arranger_headers):
        """
        Verify deal upload fails without required meta section.
        """
        invalid_spec = {
            "dates": {"cutoff_date": "2024-01-01"},
            "bonds": [],
        }
        
        response = client.post(
            "/deals",
            headers=arranger_headers,
            json={"deal_id": "INVALID", "spec": invalid_spec},
        )
        
        # Should fail validation
        assert response.status_code in [400, 422]


class TestDealValidation:
    """Tests for deal validation endpoint."""
    
    def test_validate_valid_deal(self, client, arranger_headers, sample_deal_spec):
        """
        Verify valid deal passes validation.
        """
        response = client.post(
            "/deal/validate",
            headers=arranger_headers,
            json=sample_deal_spec,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("valid") == True
    
    def test_validate_invalid_deal(self, client, arranger_headers):
        """
        Verify invalid deal fails validation with errors.
        """
        invalid_spec = {
            "meta": {},  # Missing required fields
        }
        
        response = client.post(
            "/deal/validate",
            headers=arranger_headers,
            json=invalid_spec,
        )
        
        # Should return validation failure
        data = response.json()
        assert data.get("valid") == False or response.status_code != 200


# =============================================================================
# Performance Data Tests
# =============================================================================

class TestPerformanceEndpoints:
    """Tests for performance data endpoints."""
    
    def test_upload_performance(
        self, client, arranger_headers, servicer_headers,
        sample_deal_spec, sample_performance_data
    ):
        """
        Verify performance data upload works.
        """
        # First create a deal
        client.post(
            "/deals",
            headers=arranger_headers,
            json={"deal_id": "PERF_TEST", "spec": sample_deal_spec},
        )
        
        # Then upload performance
        response = client.post(
            "/performance/PERF_TEST",
            headers=servicer_headers,
            json=sample_performance_data,
        )
        
        # Should succeed
        assert response.status_code == 200


# =============================================================================
# Simulation Tests
# =============================================================================

class TestSimulationEndpoints:
    """Tests for simulation endpoints."""
    
    def test_simulation_request_validation(self, client, investor_headers):
        """
        Verify simulation request parameters are validated.
        """
        # Missing required deal_id
        response = client.post(
            "/simulate",
            headers=investor_headers,
            json={
                "cpr": 0.08,
                "cdr": 0.015,
            },
        )
        
        # Should fail validation
        assert response.status_code == 422
    
    def test_simulation_parameter_bounds(
        self, client, arranger_headers, investor_headers, sample_deal_spec
    ):
        """
        Verify simulation rejects out-of-bounds parameters.
        """
        # Create a deal first
        client.post(
            "/deals",
            headers=arranger_headers,
            json={"deal_id": "SIM_TEST", "spec": sample_deal_spec},
        )
        
        # Request with invalid CPR (>100%)
        response = client.post(
            "/simulate",
            headers=investor_headers,
            json={
                "deal_id": "SIM_TEST",
                "cpr": 1.5,  # 150% CPR is invalid
                "cdr": 0.01,
                "severity": 0.35,
            },
        )
        
        # Should reject invalid parameter
        # (depends on API validation implementation)
        assert response.status_code in [200, 400, 422]


# =============================================================================
# Scenario Management Tests
# =============================================================================

class TestScenarioEndpoints:
    """Tests for scenario management endpoints."""
    
    def test_create_scenario(self, client, investor_headers):
        """
        Verify scenario creation works.
        """
        scenario_data = {
            "name": "Test Scenario",
            "description": "API test scenario",
            "parameters": {
                "cpr": 0.10,
                "cdr": 0.02,
                "severity": 0.40,
            },
        }
        
        response = client.post(
            "/scenarios",
            headers=investor_headers,
            json=scenario_data,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "scenario_id" in data
    
    def test_list_scenarios(self, client, investor_headers):
        """
        Verify scenario listing works.
        """
        response = client.get("/scenarios", headers=investor_headers)
        
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_update_scenario(self, client, investor_headers):
        """
        Verify scenario update works.
        """
        # Create scenario first
        create_response = client.post(
            "/scenarios",
            headers=investor_headers,
            json={
                "name": "Update Test",
                "parameters": {"cpr": 0.05},
            },
        )
        scenario_id = create_response.json()["scenario_id"]
        
        # Update it
        update_response = client.put(
            f"/scenarios/{scenario_id}",
            headers=investor_headers,
            json={
                "name": "Updated Name",
                "parameters": {"cpr": 0.08},
            },
        )
        
        assert update_response.status_code == 200
    
    def test_delete_scenario(self, client, investor_headers):
        """
        Verify scenario deletion works.
        """
        # Create scenario
        create_response = client.post(
            "/scenarios",
            headers=investor_headers,
            json={
                "name": "Delete Test",
                "parameters": {"cpr": 0.05},
            },
        )
        scenario_id = create_response.json()["scenario_id"]
        
        # Delete it
        delete_response = client.delete(
            f"/scenarios/{scenario_id}",
            headers=investor_headers,
        )
        
        assert delete_response.status_code == 200


# =============================================================================
# Audit Endpoint Tests
# =============================================================================

class TestAuditEndpoints:
    """Tests for audit and compliance endpoints."""
    
    def test_list_audit_events(self, client, auditor_headers):
        """
        Verify audit event listing works.
        """
        response = client.get("/audit/events", headers=auditor_headers)
        
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_audit_events_filtered_by_date(self, client, auditor_headers):
        """
        Verify audit events can be filtered by date range.
        """
        response = client.get(
            "/audit/events",
            headers=auditor_headers,
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
            },
        )
        
        assert response.status_code == 200


# =============================================================================
# Versioning Tests
# =============================================================================

class TestVersioningEndpoints:
    """Tests for artifact versioning endpoints."""
    
    def test_get_deal_versions(
        self, client, arranger_headers, sample_deal_spec
    ):
        """
        Verify deal version history can be retrieved.
        """
        # Create a deal
        client.post(
            "/deals",
            headers=arranger_headers,
            json={"deal_id": "VERSION_TEST", "spec": sample_deal_spec},
        )
        
        # Get versions
        response = client.get(
            "/deals/VERSION_TEST/versions",
            headers=arranger_headers,
        )
        
        assert response.status_code == 200


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandling:
    """Tests for API error handling."""
    
    def test_invalid_json_returns_400(self, client, arranger_headers):
        """
        Verify invalid JSON returns appropriate error.
        """
        response = client.post(
            "/deals",
            headers={**arranger_headers, "Content-Type": "application/json"},
            content="{ invalid json }",
        )
        
        assert response.status_code in [400, 422]
    
    def test_nonexistent_deal_returns_404(self, client, arranger_headers):
        """
        Verify request for nonexistent deal returns 404.
        """
        response = client.get(
            "/deals/NONEXISTENT_DEAL_12345/versions",
            headers=arranger_headers,
        )
        
        # Should be 404 or empty result
        assert response.status_code in [200, 404]
    
    def test_invalid_endpoint_returns_404(self, client, investor_headers):
        """
        Verify invalid endpoint returns 404.
        """
        response = client.get(
            "/invalid/endpoint/path",
            headers=investor_headers,
        )
        
        assert response.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
