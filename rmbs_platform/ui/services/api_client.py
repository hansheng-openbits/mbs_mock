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


class APIClient:
    """
    Centralized API client with caching and error handling.

    Provides a clean interface for all API interactions with:
    - Automatic retry logic
    - Response caching
    - Error normalization
    - Progress tracking for long operations
    """

    def __init__(self, base_url: str = "http://127.0.0.1:8000", timeout: int = 30):
        """
        Initialize API client.

        Parameters
        ----------
        base_url : str
            Base URL for the API server
        timeout : int
            Default timeout for requests in seconds
        """
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

    def get_deal(self, deal_id: str) -> Dict[str, Any]:
        """
        Retrieve a specific deal by ID.

        Parameters
        ----------
        deal_id : str
            Deal identifier

        Returns
        -------
        dict
            Deal specification with metadata
        """
        return self._make_request("GET", f"/deals/{deal_id}")

    def reset_deal_data(
        self,
        deal_id: str,
        reset_token_holders: bool = True,
        reset_distributions: bool = True,
        reset_yield_distributions: bool = True,
        reset_performance: bool = False,
        reset_nft_records: bool = False,
        reset_tranche_registry: bool = False,
    ) -> Dict[str, Any]:
        """
        Reset all data associated with a deal for testing purposes.

        Parameters
        ----------
        deal_id : str
            Deal identifier
        reset_token_holders : bool
            Reset token holder records for this deal
        reset_distributions : bool
            Reset distribution cycles for this deal
        reset_yield_distributions : bool
            Reset yield distribution records for this deal
        reset_performance : bool
            Reset performance data for this deal
        reset_nft_records : bool
            Reset loan NFT records for this deal
        reset_tranche_registry : bool
            Reset tranche registry for this deal

        Returns
        -------
        dict
            Summary of reset actions performed
        """
        return self._make_request(
            "POST",
            f"/deals/{deal_id}/reset",
            json={
                "reset_token_holders": reset_token_holders,
                "reset_distributions": reset_distributions,
                "reset_yield_distributions": reset_yield_distributions,
                "reset_performance": reset_performance,
                "reset_nft_records": reset_nft_records,
                "reset_tranche_registry": reset_tranche_registry,
            },
        )

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

    def get_performance(self, deal_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve performance data for a deal.

        Parameters
        ----------
        deal_id : str
            Deal identifier

        Returns
        -------
        list
            List of period summaries with collections, principal, interest, etc.
        """
        result = self._make_request("GET", f"/performance/{deal_id}")
        return result.get("periods", [])

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

    def get_model_estimates(
        self,
        wa_fico: float = 720.0,
        wa_ltv: float = 75.0,
        wa_dti: float = 36.0,
        wa_coupon: float = 0.05,
        wa_seasoning: int = 12,
        current_market_rate: float = 0.065,
        rate_scenario: str = "base",
        economic_scenario: str = "stable",
        pct_high_ltv: float = 0.20,
        pct_investor: float = 0.05,
        pct_condo: float = 0.10,
        pct_judicial_states: float = 0.30,
    ) -> Dict[str, Any]:
        """
        Get model-driven estimates for CPR, CDR, and Severity.

        Parameters
        ----------
        wa_fico : float
            Weighted-average FICO score
        wa_ltv : float
            Weighted-average LTV ratio
        wa_dti : float
            Weighted-average DTI ratio
        wa_coupon : float
            Weighted-average coupon rate (decimal)
        wa_seasoning : int
            Average loan age in months
        current_market_rate : float
            Current mortgage rate (decimal)
        rate_scenario : str
            Rate scenario: rally, base, selloff
        economic_scenario : str
            Economic scenario: expansion, stable, mild_recession, severe_recession
        pct_high_ltv : float
            % of pool with LTV > 80
        pct_investor : float
            % investment properties
        pct_condo : float
            % condos/co-ops
        pct_judicial_states : float
            % in judicial foreclosure states

        Returns
        -------
        dict
            Model estimates with cpr, cdr, severity, ranges, and component breakdowns
        """
        payload = {
            "wa_fico": wa_fico,
            "wa_ltv": wa_ltv,
            "wa_dti": wa_dti,
            "wa_coupon": wa_coupon,
            "wa_seasoning": wa_seasoning,
            "current_market_rate": current_market_rate,
            "rate_scenario": rate_scenario,
            "economic_scenario": economic_scenario,
            "pct_high_ltv": pct_high_ltv,
            "pct_investor": pct_investor,
            "pct_condo": pct_condo,
            "pct_judicial_states": pct_judicial_states,
        }
        return self._make_request("POST", "/pricing/model-estimates", json=payload)

    def run_sensitivity_analysis(
        self,
        vary_param: str,
        vary_values: List[float],
        base_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Run sensitivity analysis by varying one parameter.

        Parameters
        ----------
        vary_param : str
            Parameter to vary
        vary_values : list
            Values to test
        base_params : dict, optional
            Base parameters (uses defaults if not provided)

        Returns
        -------
        dict
            Results with cpr, cdr, severity for each value
        """
        payload = {
            "base_params": base_params or {},
            "vary_param": vary_param,
            "vary_values": vary_values,
        }
        return self._make_request("POST", "/pricing/sensitivity", json=payload)

    def get_pricing_scenarios(self) -> Dict[str, Any]:
        """
        Get available rate and economic scenarios for model-driven pricing.

        Returns
        -------
        dict
            Rate scenarios and economic scenarios with their parameters
        """
        return self._make_request("GET", "/pricing/scenarios")

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

    def upload_performance(
        self,
        deal_id: str,
        file_content: str,
        filename: str,
        created_by: str,
        update_nfts: bool = False,
        loan_nft_contract: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Upload performance data with optional automatic NFT status updates.
        
        Parameters
        ----------
        update_nfts : bool
            If True, automatically update loan NFT statuses after upload
        loan_nft_contract : str, optional
            LoanNFT contract address (uses config default if not provided)
        """
        files = {"file": (filename, file_content, "text/csv")}
        data: Dict[str, Any] = {"created_by": created_by}
        if update_nfts:
            data["update_nfts"] = "true"
        if loan_nft_contract:
            data["loan_nft_contract"] = loan_nft_contract
        return self._make_request("POST", f"/performance/{deal_id}", files=files, data=data)

    # ---------------------------------------------------------------------
    # Web3 Integration Helpers
    # ---------------------------------------------------------------------
    def web3_health(self) -> Dict[str, Any]:
        return self._make_request("GET", "/web3/health")

    def web3_list_deals(self) -> List[Dict[str, Any]]:
        return self._make_request("GET", "/web3/deals")

    def web3_register_deal(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._make_request("POST", "/web3/deals", json=payload)

    def web3_publish_tranches(self, deal_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._make_request("POST", f"/web3/deals/{deal_id}/tranches/publish", json=payload)

    def web3_register_tranches(self, deal_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._make_request("POST", f"/web3/deals/{deal_id}/tranches/register", json=payload)

    def web3_get_tranche_registry(self, deal_id: str) -> Dict[str, Any]:
        return self._make_request("GET", f"/web3/deals/{deal_id}/tranches/registry")

    def web3_publish_waterfall(self, deal_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._make_request("POST", f"/web3/waterfall/publish/{deal_id}", json=payload)

    def web3_oracle_publish_period(self, deal_id: str, period: int) -> Dict[str, Any]:
        return self._make_request("POST", f"/web3/oracle/publish/{deal_id}/{period}")

    def web3_oracle_publish_range(self, deal_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._make_request("POST", f"/web3/oracle/publish/{deal_id}", json=payload)

    def web3_publish_full_deal(self, deal_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._make_request("POST", f"/web3/deals/{deal_id}/publish", json=payload)

    # Arranger methods for loan NFT minting
    def mint_loan_nfts(self, deal_id: str, recipient_address: str, loan_nft_contract: str) -> Dict[str, Any]:
        """Mint loan NFTs for all loans in a deal."""
        payload = {
            "recipient_address": recipient_address,
            "loan_nft_contract": loan_nft_contract
        }
        return self._make_request("POST", f"/web3/deals/{deal_id}/loans/mint", json=payload)

    # Issuer methods for tranche deployment and token issuance
    def deploy_tranches(
        self,
        deal_id: str,
        payment_token: str = "0x0000000000000000000000000000000000000000",
        admin: str = "0x0000000000000000000000000000000000000001"
    ) -> Dict[str, Any]:
        """Deploy tranche contracts for a deal (must be done before issuing tokens)."""
        payload = {
            "payment_token": payment_token,
            "admin": admin
        }
        return self._make_request("POST", f"/web3/deals/{deal_id}/tranches/deploy", json=payload)

    def get_tranche_registry(self, deal_id: str) -> Dict[str, Any]:
        """Get deployed tranche contract addresses for a deal."""
        return self._make_request("GET", f"/web3/deals/{deal_id}/tranches/registry")

    def issue_tranche_tokens(
        self,
        deal_id: str,
        tranche_id: str,
        token_holders: List[str],
        token_amounts: List[int]
    ) -> Dict[str, Any]:
        """Issue tranche tokens to investors."""
        payload = {
            "token_holders": token_holders,
            "token_amounts": token_amounts
        }
        return self._make_request("POST", f"/web3/deals/{deal_id}/tranches/{tranche_id}/tokens/issue", json=payload)

    def issue_all_tranche_tokens(
        self,
        deal_id: str,
        token_holders: List[str],
        token_allocations: Optional[Dict[str, List[int]]] = None
    ) -> Dict[str, Any]:
        """Issue tokens for all tranches in a deal."""
        params = {"token_holders": token_holders}
        if token_allocations:
            params["token_allocations"] = token_allocations
        return self._make_request("POST", f"/web3/deals/{deal_id}/tranches/issue-all", json=params)

    # Investor portfolio methods
    def get_investor_portfolio(
        self,
        holder_address: str,
        cpr: float = 0.10,
        cdr: float = 0.02,
        severity: float = 0.35,
        use_full_pricing: bool = True,
    ) -> Dict[str, Any]:
        """Get token holdings portfolio for an investor with pricing analytics."""
        params = {
            "cpr": cpr,
            "cdr": cdr,
            "severity": severity,
            "use_full_pricing": use_full_pricing,
        }
        return self._make_request("GET", f"/web3/portfolio/{holder_address}", params=params)

    def get_token_holders(self) -> List[Dict[str, Any]]:
        """Get list of all token holders."""
        return self._make_request("GET", "/web3/token-holders")

    def claim_yields(
        self,
        holder_address: str,
        claim_all: bool = True,
        specific_tokens: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Claim pending yields for an investor."""
        payload = {
            "holder_address": holder_address,
            "claim_all": claim_all,
        }
        if specific_tokens:
            payload["specific_tokens"] = specific_tokens
        return self._make_request("POST", f"/web3/portfolio/{holder_address}/claim-yields", json=payload)

    def get_cash_balance(self, holder_address: str) -> Dict[str, Any]:
        """Get cash balance for an investor."""
        return self._make_request("GET", f"/web3/portfolio/{holder_address}/cash")

    def get_yield_history(self, holder_address: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get yield claim history for an investor."""
        return self._make_request("GET", f"/web3/portfolio/{holder_address}/yield-history", params={"limit": limit})

    def deposit_cash(self, holder_address: str, amount: float) -> Dict[str, Any]:
        """Deposit cash into an investor's account."""
        return self._make_request("POST", f"/web3/portfolio/{holder_address}/deposit", json={"amount": amount})

    def withdraw_cash(self, holder_address: str, amount: float) -> Dict[str, Any]:
        """Withdraw cash from an investor's account."""
        return self._make_request("POST", f"/web3/portfolio/{holder_address}/withdraw", json={"amount": amount})

    # Servicer methods for NFT status updates
    def update_loan_nft_statuses(
        self,
        deal_id: str,
        loan_nft_contract: str,
        period: Optional[int] = None,
        loan_id_to_token_map: Optional[Dict[str, int]] = None
    ) -> Dict[str, Any]:
        """Update loan NFT statuses from performance data."""
        payload: Dict[str, Any] = {"loan_nft_contract": loan_nft_contract}
        if period is not None:
            payload["period"] = period
        if loan_id_to_token_map is not None:
            payload["loan_id_to_token_map"] = loan_id_to_token_map
        return self._make_request("POST", f"/web3/loans/{deal_id}/update-status", json=payload)

    # Trustee methods for deal administration
    def execute_waterfall(self, deal_id: str, period_number: int) -> Dict[str, Any]:
        """Execute waterfall distribution for a period."""
        payload = {
            "deal_id": deal_id,
            "period_number": period_number
        }
        return self._make_request("POST", "/web3/waterfall/execute", json=payload)

    def distribute_yield(self, deal_id: str, tranche_id: str, amount: float, period: int) -> Dict[str, Any]:
        """Distribute yield to tranche holders."""
        payload = {
            "deal_id": deal_id,
            "tranche_id": tranche_id,
            "amount": amount,
            "period": period
        }
        return self._make_request("POST", "/web3/yield/distribute", json=payload)

    # Distribution cycle methods
    def get_distribution_periods(self, deal_id: str) -> Dict[str, Any]:
        """Get all distribution periods for a deal."""
        return self._make_request("GET", f"/distributions/{deal_id}")

    def get_pending_distributions(self, deal_id: str) -> Dict[str, Any]:
        """Get pending distribution periods awaiting trustee action."""
        return self._make_request("GET", f"/distributions/{deal_id}/pending")

    def execute_distribution(self, deal_id: str, period_number: int, force_reprocess: bool = False) -> Dict[str, Any]:
        """
        Execute full distribution cycle for a period.
        
        This runs the waterfall and updates token balances.
        Called by Trustee after Servicer uploads tape.
        
        Parameters
        ----------
        deal_id : str
            Deal identifier
        period_number : int
            The distribution period to process
        force_reprocess : bool
            If True, allows re-processing of already distributed periods (for testing)
        """
        payload = {
            "deal_id": deal_id,
            "period_number": period_number,
            "force_reprocess": force_reprocess
        }
        return self._make_request("POST", "/web3/waterfall/execute-distribution", json=payload)

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