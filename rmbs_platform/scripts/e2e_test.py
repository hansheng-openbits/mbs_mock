#!/usr/bin/env python3
"""End-to-end API test for RMBS platform."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import sleep

import pandas as pd
import requests


def _fail(msg: str, code: int = 1) -> None:
    print(f"[FAIL] {msg}")
    sys.exit(code)


def _ok(msg: str) -> None:
    print(f"[OK] {msg}")


def _post_json(url: str, payload: dict) -> dict:
    res = requests.post(url, json=payload, timeout=30)
    if res.status_code != 200:
        _fail(f"POST {url} failed: {res.status_code} {res.text}")
    return res.json()


def _delete(url: str) -> dict:
    res = requests.delete(url, timeout=30)
    if res.status_code != 200:
        _fail(f"DELETE {url} failed: {res.status_code} {res.text}")
    return res.json()


def _post_file(url: str, file_path: Path) -> dict:
    with file_path.open("rb") as f:
        res = requests.post(url, files={"file": (file_path.name, f.read())}, timeout=60)
    if res.status_code != 200:
        _fail(f"POST {url} failed: {res.status_code} {res.text}")
    return res.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="RMBS end-to-end API test.")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--deal-id", default="SAMPLE_RMBS_2024")
    parser.add_argument("--use-ml", action="store_true")
    parser.add_argument("--dataset-dir", default="sample_data_freddie", help="Dataset directory under rmbs_platform.")
    parser.add_argument("--servicer-glob", default="servicer_*.csv", help="Glob for servicer tapes in dataset dir.")
    parser.add_argument("--prepay-model-key", default="prepay")
    parser.add_argument("--default-model-key", default="default")
    parser.add_argument("--rate-scenario", default="rally", choices=["rally", "selloff", "base"])
    parser.add_argument("--start-rate", type=float, default=0.045)
    parser.add_argument("--feature-source", default="simulated", choices=["simulated", "market_rates"])
    parser.add_argument("--origination-source-uri", default=None, help="Optional origination tape path for ML features.")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parents[1]
    sample_dir = base_dir / args.dataset_dir

    deal_path = sample_dir / "deal_rules.json"
    collateral_path = sample_dir / "collateral.json"
    servicer_files = sorted(sample_dir.glob(args.servicer_glob))

    if not servicer_files:
        _fail(f"No servicer files found with pattern '{args.servicer_glob}' in {sample_dir}.")

    deal = json.loads(deal_path.read_text())
    if "meta" not in deal:
        deal["meta"] = {}
    deal["meta"]["deal_id"] = args.deal_id

    _post_json(f"{args.api_url}/deals", {"deal_id": args.deal_id, "spec": deal})
    _ok("Deal uploaded.")

    collateral = json.loads(collateral_path.read_text())
    _post_json(f"{args.api_url}/collateral", {"deal_id": args.deal_id, "collateral": collateral})
    _ok("Collateral uploaded.")

    _delete(f"{args.api_url}/performance/{args.deal_id}")
    _ok("Performance cleared.")

    for path in servicer_files:
        _post_file(f"{args.api_url}/performance/{args.deal_id}", path)
    _ok(f"Uploaded {len(servicer_files)} servicer tapes.")

    expected_last_period = int(
        pd.concat([pd.read_csv(p)["Period"] for p in servicer_files]).max()
    )

    orig_source = args.origination_source_uri
    if args.use_ml and args.feature_source == "market_rates" and not orig_source and args.dataset_dir == "sample_data_freddie":
        orig_source = str(
            Path("/media/hansheng/cc7df9bc-e728-4b8d-a215-b64f31876acc/cdo-tee-mock/prepayment/data/Extracted_data/combined_sampled_mortgages_2017_2020.csv")
        )

    payload = {
        "deal_id": args.deal_id,
        "cpr": 0.10,
        "cdr": 0.01,
        "severity": 0.40,
        "use_ml_models": bool(args.use_ml),
        "prepay_model_key": args.prepay_model_key if args.use_ml else None,
        "default_model_key": args.default_model_key if args.use_ml else None,
        "rate_scenario": args.rate_scenario if args.use_ml else None,
        "start_rate": args.start_rate if args.use_ml else None,
        "feature_source": args.feature_source if args.use_ml else None,
        "origination_source_uri": orig_source if args.use_ml and orig_source else None,
    }

    job = _post_json(f"{args.api_url}/simulate", payload)
    job_id = job.get("job_id")
    if not job_id:
        _fail("Missing job_id from /simulate response.")

    for _ in range(60):
        sleep(1)
        res = requests.get(f"{args.api_url}/results/{job_id}", timeout=30)
        if res.status_code != 200:
            _fail(f"GET /results failed: {res.status_code} {res.text}")
        payload = res.json()
        status = payload.get("status")
        if status == "COMPLETED":
            break
        if status == "FAILED":
            _fail(f"Simulation failed: {payload.get('error')}")
    else:
        _fail("Simulation timed out.")

    warnings = payload.get("warnings") or []
    if warnings:
        _fail("Warnings detected in results payload.", code=2)

    last_actual_period = payload.get("last_actual_period")
    if last_actual_period != expected_last_period:
        _fail(f"Expected last actual period {expected_last_period}, got {last_actual_period}.")
    _ok("Actuals period alignment verified.")

    df = pd.DataFrame(payload.get("data", []))
    if df.empty:
        _fail("Empty simulation results.")

    if (df["Period"] <= expected_last_period).all():
        _fail("No simulated periods found beyond actuals.")
    _ok("Simulated periods present after actuals.")

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
