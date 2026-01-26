"""
API Client Service
==================

Centralized API client for RMBS platform UI with caching,
error handling, and async support.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from functools import lru_cache
import streamlit as st

import requests
from requests.exceptions import RequestException, Timeout, ConnectionError


class APIError(Exception):
    """Custom exception for API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


def _get_default_api_url() -> str:
    """
    Get API URL from Streamlit secrets, environment variable, or localhost default.

    Priority:
    1. Streamlit secrets (for Streamlit Cloud deployment)
    2. Environment variable RMBS_API_URL (for local dev with Cloud Run)
    3. Localhost default (for local dev with local API)
    """
    import os

    # Try Streamlit secrets first (for Streamlit Cloud)
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and 'RMBS_API_URL' in st.secrets:
            return st.secrets['RMBS_API_URL']
    except Exception:
        pass

    # Fall back to environment variable or localhost
    return os.environ.get("RMBS_API_URL", "http://127.0.0.1:8000")


class APIClient:
    """
    Centralized API client with caching and error handling.

    Provides a clean interface for all API interactions with:
    - Automatic retry logic
    - Response caching
    - Error normalization
    - Progress tracking for long operations

    Configure via environment variable:
        RMBS_API_URL=https://rmbs-api-xxxxx-uc.a.run.app
    """

    def __init__(self, base_url: str = None, timeout: int = 30):
        """
        Initialize API client.

        Parameters
        ----------
        base_url : str
            Base URL for the API server. If not provided, reads from
            RMBS_API_URL environment variable or defaults to localhost.
        timeout : int
            Default timeout for requests in seconds
        """
        if base_url is None:
            base_url = _get_default_api_url()
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.headers: Dict[str, str] = {}
        self._cache: Dict[str, Dict] = {}
        self._cache_expiry: Dict[str, float] = {}

    def set_headers(self, headers: Dict[str, str]) -> None:
        """Set default headers for all requests."""
        self.headers = headers

    def health_check(self) -> bool:
        """Check if API server is reachable."""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except (RequestException, Timeout):
            return False

    def get_deals(self) -> List[Dict[str, Any]]:
        """
        Retrieve available deals from the API.

        Returns
        -------
        list of dict
            Deal summaries with metadata
        """
        try:
            response = self._make_request("GET", "/deals")
            return response.get("deals", [])
        except APIError:
            return []

    def get_collateral(self, deal_id: str) -> Dict[str, Any]:
        """
        Retrieve collateral data for a deal.

        Parameters
        ----------
        deal_id : str
            Deal identifier

        Returns
        -------
        dict
            Collateral data
        """
        return self._make_request("GET", f"/collateral/{deal_id}")

    def get_scenarios(self, include_archived: bool = True) -> List[Dict[str, Any]]:
        """
        Retrieve scenario definitions.

        Parameters
        ----------
        include_archived : bool
            Whether to include archived scenarios

        Returns
        -------
        list of dict
            Scenario definitions
        """
        try:
            response = self._make_request(
                "GET",
                "/scenarios",
                params={"include_archived": str(include_archived).lower()}
            )
            return response.get("scenarios", [])
        except APIError:
            return []

    def get_versions(self, path: str) -> List[Dict[str, Any]]:
        """
        Retrieve version metadata for a resource.

        Parameters
        ----------
        path : str
            API path suffix (e.g., "/deals/DEAL_1/versions")

        Returns
        -------
        list of dict
            Version metadata entries
        """
        try:
            response = self._make_request("GET", path)
            return response.get("versions", [])
        except APIError:
            return []

    def get_model_registry(self) -> Dict[str, Any]:
        """
        Retrieve the model registry from the API.

        Returns
        -------
        dict
            Registry mapping model keys to metadata. Returns empty dict on error.
        """
        try:
            response = self._make_request("GET", "/models/registry")
            registry = response.get("registry", {})
            return registry if isinstance(registry, dict) else {}
        except APIError:
            return {}

    def simulate_deal(
        self,
        deal_id: str,
        cpr: float,
        cdr: float,
        severity: float,
        horizon_periods: int = 60,
        scenario_id: Optional[str] = None,
        prepay_model_key: Optional[str] = None,
        default_model_key: Optional[str] = None,
        use_ml: bool = False,
        progress_callback: Optional[callable] = None,
        job_id_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Run deal simulation with progress tracking.

        Parameters
        ----------
        deal_id : str
            Deal identifier to simulate
        cpr : float
            Constant prepayment rate
        cdr : float
            Constant default rate
        severity : float
            Loss severity rate
        use_ml : bool
            Whether to use ML models
        progress_callback : callable, optional
            Function to call with progress updates

        Returns
        -------
        dict
            Simulation results
        """
        payload = {
            "deal_id": deal_id,
            "cpr": cpr,
            "cdr": cdr,
            "severity": severity,
            "horizon_periods": int(horizon_periods),
            "use_ml_models": use_ml
        }
        if scenario_id:
            payload["scenario_id"] = scenario_id
        if prepay_model_key:
            payload["prepay_model_key"] = prepay_model_key
        if default_model_key:
            payload["default_model_key"] = default_model_key

        # Submit simulation
        response = self._make_request("POST", "/simulate", json=payload)
        job_id = response.get("job_id")

        if not job_id:
            raise APIError("Simulation did not return a job ID")

        if job_id_callback:
            try:
                job_id_callback(str(job_id))
            except Exception:
                # Never let UI callbacks break the simulation polling.
                pass

        # Poll for completion with progress
        while True:
            try:
                status_response = self._make_request("GET", f"/results/{job_id}")
                # Ensure the caller always has the job_id available.
                if isinstance(status_response, dict) and "job_id" not in status_response:
                    status_response["job_id"] = job_id

                if progress_callback:
                    # Estimate progress based on status
                    status = status_response.get("status", "")
                    if status == "COMPLETED":
                        progress_callback(100, "Complete")
                    elif status == "RUNNING":
                        progress_callback(50, "Processing...")
                    elif status == "QUEUED":
                        progress_callback(10, "Queued...")
                    elif status == "FAILED":
                        raise APIError(
                            f"Simulation failed: {status_response.get('error', 'Unknown error')}"
                        )

                if status == "COMPLETED":
                    return status_response
                elif status == "FAILED":
                    raise APIError(f"Simulation failed: {status_response.get('error', 'Unknown error')}")

                time.sleep(1)  # Poll every second

            except APIError:
                raise
            except Exception as e:
                raise APIError(f"Error polling simulation status: {e}")

    def upload_deal(self, deal_id: str, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Upload deal specification."""
        payload = {"deal_id": deal_id, "spec": spec}
        return self._make_request("POST", "/deals", json=payload)

    def upload_collateral(self, deal_id: str, collateral: Dict[str, Any]) -> Dict[str, Any]:
        """Upload collateral data."""
        payload = {"deal_id": deal_id, "collateral": collateral}
        return self._make_request("POST", "/collateral", json=payload)

    def upload_loan_tape(self, deal_id: str, file_content: bytes, filename: str) -> Dict[str, Any]:
        """Upload loan tape data."""
        files = {"file": (filename, file_content, "text/csv")}
        return self._make_request("POST", f"/loan-tape/{deal_id}", files=files)

    def upload_performance(self, deal_id: str, file_content: str, filename: str, created_by: str) -> Dict[str, Any]:
        """Upload performance data."""
        files = {"file": (filename, file_content, "text/csv")}
        data = {"created_by": created_by}
        return self._make_request("POST", f"/performance/{deal_id}", files=files, data=data)

    def validate_deal(self, spec: Optional[Dict] = None, deal_id: Optional[str] = None) -> Dict[str, Any]:
        """Validate deal specification."""
        payload = {}
        if spec:
            payload["spec"] = spec
        if deal_id:
            payload["deal_id"] = deal_id
        return self._make_request("POST", "/deal/validate", json=payload)

    def validate_performance(self, rows: Optional[List[Dict]] = None, deal_id: Optional[str] = None) -> Dict[str, Any]:
        """Validate performance data."""
        payload = {}
        if rows:
            payload["rows"] = rows
        if deal_id:
            payload["deal_id"] = deal_id
        return self._make_request("POST", "/validation/performance", json=payload)

    def create_scenario(self, scenario_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new scenario."""
        return self._make_request("POST", "/scenarios", json=scenario_data)

    def _make_request(
        self,
        method: str,
        endpoint: str,
        json: Optional[Dict] = None,
        params: Optional[Dict] = None,
        files: Optional[Dict] = None,
        data: Optional[Dict] = None,
        retry_count: int = 2
    ) -> Dict[str, Any]:
        """
        Make HTTP request with error handling and retries.

        Parameters
        ----------
        method : str
            HTTP method (GET, POST, etc.)
        endpoint : str
            API endpoint path
        json : dict, optional
            JSON payload
        params : dict, optional
            Query parameters
        files : dict, optional
            File uploads
        data : dict, optional
            Form data
        retry_count : int
            Number of retries on failure

        Returns
        -------
        dict
            Response JSON data

        Raises
        ------
        APIError
            If request fails after retries
        """
        url = f"{self.base_url}{endpoint}"

        for attempt in range(retry_count + 1):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    json=json,
                    params=params,
                    files=files,
                    data=data,
                    timeout=self.timeout
                )

                if response.status_code >= 200 and response.status_code < 300:
                    try:
                        return response.json()
                    except ValueError:
                        return {"status": "success"}

                elif response.status_code == 401:
                    raise APIError("Authentication required", response.status_code)
                elif response.status_code == 403:
                    raise APIError("Access denied", response.status_code)
                elif response.status_code >= 500:
                    if attempt < retry_count:
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    raise APIError(f"Server error: {response.text}", response.status_code)
                else:
                    raise APIError(f"Request failed: {response.text}", response.status_code)

            except (Timeout, ConnectionError) as e:
                if attempt < retry_count:
                    time.sleep(2 ** attempt)
                    continue
                raise APIError(f"Connection failed: {e}", None)

            except RequestException as e:
                raise APIError(f"Request error: {e}", None)

        # Should not reach here
        raise APIError("Request failed after all retries", None)