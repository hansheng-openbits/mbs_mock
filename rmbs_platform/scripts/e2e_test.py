#!/usr/bin/env python3
"""
End-to-End API Test
===================

Comprehensive integration test for the RMBS platform API. This script
validates the complete workflow from deal upload through simulation
completion, including actuals processing and projection generation.

Test Sequence
-------------
1. Upload deal structure (Arranger role)
2. Upload collateral attributes (Arranger role)
3. Clear and upload performance tapes (Servicer role)
4. Run simulation with optional ML models (Investor role)
5. Validate results (periods, balances, waterfall mechanics)

Usage
-----
Basic test with sample data::

    python scripts/e2e_test.py

Test with Freddie sample data and ML::

    python scripts/e2e_test.py \\
        --dataset-dir sample_data_freddie \\
        --servicer-glob "servicer_2017*.csv" \\
        --use-ml \\
        --rate-scenario selloff

Command Line Arguments
----------------------
--api-url : str
    API base URL (default: http://127.0.0.1:8000)
--deal-id : str
    Deal identifier to use (default: SAMPLE_RMBS_2024)
--dataset-dir : str
    Dataset directory under rmbs_platform (default: sample_data_freddie)
--servicer-glob : str
    Glob pattern for servicer tapes (default: servicer_*.csv)
--use-ml : flag
    Enable ML prepay/default models
--prepay-model-key : str
    Model registry key for prepayment (default: prepay)
--default-model-key : str
    Model registry key for default (default: default)
--rate-scenario : str
    Rate path scenario: rally, selloff, base (default: rally)
--start-rate : float
    Starting short rate (default: 0.045)
--feature-source : str
    ML feature source: simulated, market_rates (default: simulated)
--origination-source-uri : str
    Path to origination tape for ML features

Exit Codes
----------
- 0: All tests passed
- 1: Test failure (assertion or API error)
- 2: Warnings detected in results

Example
-------
>>> # Run from rmbs_platform parent directory
>>> python rmbs_platform/scripts/e2e_test.py --use-ml --rate-scenario rally
[OK] Deal uploaded.
[OK] Collateral uploaded.
[OK] Performance cleared.
[OK] Uploaded 6 servicer tapes.
[OK] Actuals period alignment verified.
[OK] Simulated periods present after actuals.
[OK] E2E test completed successfully.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import sleep
from typing import Any, Dict, Optional

import pandas as pd
import requests


def _fail(msg: str, code: int = 1) -> None:
    """
    Print failure message and exit.

    Parameters
    ----------
    msg : str
        Failure description.
    code : int
        Exit code (default: 1).
    """
    print(f"[FAIL] {msg}")
    sys.exit(code)


def _ok(msg: str) -> None:
    """
    Print success message.

    Parameters
    ----------
    msg : str
        Success description.
    """
    print(f"[OK] {msg}")


def _post_json(
    url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    POST JSON payload and return JSON response.

    Parameters
    ----------
    url : str
        API endpoint URL.
    payload : dict
        JSON-serializable request body.
    headers : dict, optional
        HTTP headers (including X-User-Role).

    Returns
    -------
    dict
        Parsed JSON response.

    Raises
    ------
    SystemExit
        If response status is not 200.
    """
    res = requests.post(url, json=payload, timeout=30, headers=headers)
    if res.status_code != 200:
        _fail(f"POST {url} failed: {res.status_code} {res.text}")
    return res.json()


def _delete(
    url: str, headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    DELETE an API resource and return JSON response.

    Parameters
    ----------
    url : str
        API endpoint URL.
    headers : dict, optional
        HTTP headers (including X-User-Role).

    Returns
    -------
    dict
        Parsed JSON response.

    Raises
    ------
    SystemExit
        If response status is not 200.
    """
    res = requests.delete(url, timeout=30, headers=headers)
    if res.status_code != 200:
        _fail(f"DELETE {url} failed: {res.status_code} {res.text}")
    return res.json()


def _post_file(
    url: str, file_path: Path, headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Upload a file to an API endpoint.

    Parameters
    ----------
    url : str
        API endpoint URL.
    file_path : Path
        Path to file to upload.
    headers : dict, optional
        HTTP headers (including X-User-Role).

    Returns
    -------
    dict
        Parsed JSON response.

    Raises
    ------
    SystemExit
        If response status is not 200.
    """
    with file_path.open("rb") as f:
        res = requests.post(
            url, files={"file": (file_path.name, f.read())}, timeout=60, headers=headers
        )
    if res.status_code != 200:
        _fail(f"POST {url} failed: {res.status_code} {res.text}")
    return res.json()


def main() -> None:
    """
    Execute the end-to-end test sequence.

    This function parses command line arguments, executes the test
    workflow, and validates results.
    """
    parser = argparse.ArgumentParser(description="RMBS end-to-end API test.")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--deal-id", default="SAMPLE_RMBS_2024")
    parser.add_argument("--use-ml", action="store_true")
    parser.add_argument(
        "--dataset-dir",
        default="sample_data_freddie",
        help="Dataset directory under rmbs_platform.",
    )
    parser.add_argument(
        "--servicer-glob",
        default="servicer_*.csv",
        help="Glob for servicer tapes in dataset dir.",
    )
    parser.add_argument("--prepay-model-key", default="prepay")
    parser.add_argument("--default-model-key", default="default")
    parser.add_argument(
        "--rate-scenario", default="rally", choices=["rally", "selloff", "base"]
    )
    parser.add_argument("--start-rate", type=float, default=0.045)
    parser.add_argument(
        "--feature-source", default="simulated", choices=["simulated", "market_rates"]
    )
    parser.add_argument(
        "--origination-source-uri",
        default=None,
        help="Optional origination tape path for ML features.",
    )
    args = parser.parse_args()

    # RBAC headers for each role
    headers = {
        "arranger": {"X-User-Role": "arranger"},
        "servicer": {"X-User-Role": "servicer"},
        "investor": {"X-User-Role": "investor"},
    }

    base_dir = Path(__file__).resolve().parents[1]
    sample_dir = base_dir / args.dataset_dir

    deal_path = sample_dir / "deal_rules.json"
    collateral_path = sample_dir / "collateral.json"
    servicer_files = sorted(sample_dir.glob(args.servicer_glob))

    if not servicer_files:
        _fail(
            f"No servicer files found with pattern '{args.servicer_glob}' in {sample_dir}."
        )

    # 1. Upload deal
    deal = json.loads(deal_path.read_text())
    if "meta" not in deal:
        deal["meta"] = {}
    deal["meta"]["deal_id"] = args.deal_id

    _post_json(
        f"{args.api_url}/deals",
        {"deal_id": args.deal_id, "spec": deal},
        headers=headers["arranger"],
    )
    _ok("Deal uploaded.")

    # 2. Upload collateral
    collateral = json.loads(collateral_path.read_text())
    _post_json(
        f"{args.api_url}/collateral",
        {"deal_id": args.deal_id, "collateral": collateral},
        headers=headers["arranger"],
    )
    _ok("Collateral uploaded.")

    # 3. Clear and upload performance
    _delete(f"{args.api_url}/performance/{args.deal_id}", headers=headers["servicer"])
    _ok("Performance cleared.")

    for path in servicer_files:
        _post_file(
            f"{args.api_url}/performance/{args.deal_id}",
            path,
            headers=headers["servicer"],
        )
    _ok(f"Uploaded {len(servicer_files)} servicer tapes.")

    expected_last_period = int(
        pd.concat([pd.read_csv(p)["Period"] for p in servicer_files]).max()
    )

    # 4. Prepare simulation request
    orig_source = args.origination_source_uri
    if (
        args.use_ml
        and args.feature_source == "market_rates"
        and not orig_source
        and args.dataset_dir == "sample_data_freddie"
    ):
        orig_source = str(
            Path(
                "/media/hansheng/cc7df9bc-e728-4b8d-a215-b64f31876acc/"
                "cdo-tee-mock/prepayment/data/Extracted_data/"
                "combined_sampled_mortgages_2017_2020.csv"
            )
        )

    feature_source = "simulated" if args.use_ml else None
    payload: Dict[str, Any] = {
        "deal_id": args.deal_id,
        "cpr": 0.10,
        "cdr": 0.01,
        "severity": 0.40,
        "use_ml_models": bool(args.use_ml),
        "prepay_model_key": args.prepay_model_key if args.use_ml else None,
        "default_model_key": args.default_model_key if args.use_ml else None,
        "rate_scenario": args.rate_scenario if args.use_ml else None,
        "start_rate": args.start_rate if args.use_ml else None,
        "feature_source": feature_source,
        "origination_source_uri": orig_source if args.use_ml and orig_source else None,
    }

    # 5. Run simulation
    job = _post_json(
        f"{args.api_url}/simulate", payload, headers=headers["investor"]
    )
    job_id = job.get("job_id")
    if not job_id:
        _fail("Missing job_id from /simulate response.")

    # 6. Poll for completion
    for _ in range(60):
        sleep(1)
        res = requests.get(
            f"{args.api_url}/results/{job_id}",
            timeout=30,
            headers=headers["investor"],
        )
        if res.status_code != 200:
            _fail(f"GET /results failed: {res.status_code} {res.text}")
        result_payload = res.json()
        status = result_payload.get("status")
        if status == "COMPLETED":
            break
        if status == "FAILED":
            _fail(f"Simulation failed: {result_payload.get('error')}")
    else:
        _fail("Simulation timed out.")

    # 7. Validate results
    warnings = result_payload.get("warnings") or []
    if warnings:
        _fail("Warnings detected in results payload.", code=2)

    last_actual_period = result_payload.get("last_actual_period")
    if last_actual_period != expected_last_period:
        _fail(
            f"Expected last actual period {expected_last_period}, "
            f"got {last_actual_period}."
        )
    _ok("Actuals period alignment verified.")

    df = pd.DataFrame(result_payload.get("data", []))
    if df.empty:
        _fail("Empty simulation results.")

    if (df["Period"] <= expected_last_period).all():
        _fail("No simulated periods found beyond actuals.")
    _ok("Simulated periods present after actuals.")

    # 8. Validate waterfall mechanics (if applicable)
    if "Bond.ClassA1.Balance" in df.columns:
        a1_zero = df[df["Bond.ClassA1.Balance"] <= 0.0]
        if not a1_zero.empty and "Bond.ClassA2.Prin_Paid" in df.columns:
            after_zero = df[df["Period"] > a1_zero["Period"].min()]
            if (after_zero["Bond.ClassA2.Prin_Paid"] <= 0).all():
                _fail("ClassA2 does not amortize after ClassA1 reaches zero.")
            _ok("ClassA2 amortizes after ClassA1 payoff.")

    _ok("E2E test completed successfully.")


if __name__ == "__main__":
    main()
