# Web3 Test Cases Using Existing Deal Data

This document defines Web3 test cases that use the existing deal JSONs in `deals/`.
Each case maps to a workflow in the Web3 integration and highlights expected outcomes.

---

## Common Setup

- Load deal spec into the platform:
  - `POST /deals` with `deal_id` matching the JSON filename (without `.json`)
- Load performance tape for the same deal if oracle publishing is tested:
  - `POST /performance/{deal_id}`
- Ensure Web3 env vars are configured and API is running.

---

## Test Case Matrix

### TC-W3-001: Baseline Deal Publish (Prime)
- **Deal**: `PRIME_2024_1`
- **Purpose**: Validate standard fixed-rate multi-tranche publish.
- **Steps**:
  1. `POST /web3/deals/PRIME_2024_1/publish`
  2. (Optional) Register tranche addresses from deployment logs.
  3. `POST /web3/waterfall/publish/PRIME_2024_1`
- **Expected**:
  - Deal registered on-chain.
  - Tranche deployment tx hashes returned.
  - Waterfall configured (tx hash).

---

### TC-W3-002: Mixed Coupon Deal Publish (Sample RMBS)
- **Deal**: `SAMPLE_RMBS_2024`
- **Purpose**: Validate fixed + float + variable coupon handling in tranche publish.
- **Notes**:
  - Fixed-rate is used for coupon inference; floating/variable coupons default to 0 bps.
- **Steps**:
  1. `POST /web3/deals/SAMPLE_RMBS_2024/tranches/publish`
  2. `POST /web3/deals/SAMPLE_RMBS_2024/tranches/register`
  3. `POST /web3/waterfall/publish/SAMPLE_RMBS_2024`
- **Expected**:
  - Tranches deployed for ClassA1, ClassA2, ClassB, ClassIO, ClassR.
  - Waterfall configured with inferred rates.

---

### TC-W3-003: Non-QM Deal Publish (Non-QM)
- **Deal**: `NONQM_2023_1`
- **Purpose**: Validate tranche publish + waterfall config under trigger-driven structure.
- **Steps**:
  1. `POST /web3/deals/NONQM_2023_1/tranches/publish`
  2. `POST /web3/deals/NONQM_2023_1/tranches/register`
  3. `POST /web3/waterfall/publish/NONQM_2023_1`
- **Expected**:
  - Tranches deployed (ClassA1, ClassA2, ClassM1, ClassB).
  - Waterfall configured with sequential principal.

---

### TC-W3-004: Stressed Deal Publish (Subprime)
- **Deal**: `STRESSED_2022_1`
- **Purpose**: Validate publish workflow on a deal with trigger status and degraded balances.
- **Steps**:
  1. `POST /web3/deals/STRESSED_2022_1/tranches/publish`
  2. `POST /web3/deals/STRESSED_2022_1/tranches/register`
  3. `POST /web3/waterfall/publish/STRESSED_2022_1`
- **Expected**:
  - Tranches deployed (ClassA, ClassM, ClassB).
  - Waterfall configured (no on-chain trigger logic yet, but config accepted).

---

### TC-W3-005: Oracle Publish (Single Period)
- **Deal**: `PRIME_2024_1`
- **Purpose**: Verify platform-to-oracle publish for a single period.
- **Prerequisite**: Performance data loaded.
- **Steps**:
  1. `POST /web3/oracle/publish/PRIME_2024_1/1`
- **Expected**:
  - Loan tape tx hash returned.

---

### TC-W3-006: Oracle Publish (Range)
- **Deal**: `NONQM_2023_1`
- **Purpose**: Verify bulk publish across multiple periods.
- **Prerequisite**: Performance data loaded with at least 3 periods.
- **Steps**:
  1. `POST /web3/oracle/publish/NONQM_2023_1` with `{ "start_period": 1, "end_period": 3 }`
- **Expected**:
  - Three transaction hashes returned.

---

### TC-W3-007: Full Publish Workflow
- **Deal**: `PRIME_2024_1`
- **Purpose**: Validate combined deal → tranche → waterfall flow.
- **Steps**:
  1. `POST /web3/deals/PRIME_2024_1/publish`
  2. Provide `tranche_addresses` if already known.
- **Expected**:
  - `register_tx` returned.
  - `tranche_txs` list returned.
  - `waterfall_tx` returned if addresses provided or registry populated.

---

### TC-W3-008: Negative — Invalid Deal Spec
- **Deal**: `INVALID`
- **Purpose**: Ensure publish fails for invalid specs (no bonds).
- **Steps**:
  1. `POST /web3/deals/INVALID/tranches/publish`
- **Expected**:
  - HTTP 400 with message `has no bonds to publish`.

---

## Optional Validation Checks

- `GET /web3/deals` includes the new on-chain deal IDs.
- `GET /web3/deals/{deal_id}` returns metadata.
- `GET /web3/deals/{deal_id}/tranches/registry` returns recorded addresses.

---

## Runnable Script

Use `scripts/run_web3_test_cases.sh` to execute a canned flow using the deals above.
Set the required environment variables listed at the top of the script.
