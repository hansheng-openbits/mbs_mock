#!/usr/bin/env markdown
# Web3 End-to-End Testing Guide

This guide defines an end-to-end workflow test plan for the current Web3 implementation.
It includes step-by-step commands (curl) and expected outcomes. Run these against a
configured environment with deployed contracts.

---

## 1) Prerequisites

- Contracts deployed (TrancheFactory, TransferValidator, ServicerOracle, WaterfallEngine)
- Environment configured:
  - `RMBS_WEB3_ENABLED=true`
  - `RMBS_WEB3_RPC_URL=...`
  - `RMBS_WEB3_ADMIN_PRIVATE_KEY=...`
  - `RMBS_WEB3_TRANCHE_FACTORY=0x...`
  - `RMBS_WEB3_TRANSFER_VALIDATOR=0x...`
  - `RMBS_WEB3_SERVICER_ORACLE=0x...`
  - `RMBS_WEB3_WATERFALL_ENGINE=0x...`
- API running: `uvicorn api_main:app --reload`
- Deal data loaded into RMBS platform:
  - Upload deal spec (`POST /deals`)
  - Upload performance tape (`POST /performance/{deal_id}`)

---

## 2) Test Workflow Overview

End-to-end flow covers:
1. Web3 connectivity and health
2. On-chain deal registration
3. Tranche deployment from deal spec
4. Tranche address registry
5. Waterfall configuration from deal spec
6. Servicer oracle loan tape submission
7. Waterfall execution
8. Full publish workflow (combined)

---

## 3) End-to-End Steps

### Step 1 — Web3 Health
```bash
curl -s http://localhost:8000/web3/health
```
Expected:
- `connected: true`

---

### Step 2 — Register Deal On-Chain
```bash
curl -s -X POST http://localhost:8000/web3/deals \
  -H "Content-Type: application/json" \
  -H "X-User-Role: arranger" \
  -d '{
    "deal_id": "DEAL_2026_001",
    "deal_name": "RMBS 2026-1",
    "arranger": "0xArranger...",
    "closing_date": 1767225600,
    "maturity_date": 1893456000
  }'
```
Expected:
- `transaction_hash`

---

### Step 3 — Publish Tranches From Deal Spec
```bash
curl -s -X POST http://localhost:8000/web3/deals/DEAL_2026_001/tranches/publish \
  -H "Content-Type: application/json" \
  -H "X-User-Role: arranger" \
  -d '{
    "payment_token": "0xUSDC...",
    "transfer_validator": "0xValidator...",
    "admin": "0xAdmin...",
    "issuer": "0xIssuer...",
    "trustee": "0xTrustee...",
    "payment_frequency": 1
  }'
```
Expected:
- List of tranche transaction hashes

---

### Step 4 — Register Tranche Addresses
Since tranche addresses are not auto-discovered yet, record them after deployment.
```bash
curl -s -X POST http://localhost:8000/web3/deals/DEAL_2026_001/tranches/register \
  -H "Content-Type: application/json" \
  -H "X-User-Role: arranger" \
  -d '{
    "tranches": [
      "0xTrancheA...",
      "0xTrancheM...",
      "0xTrancheB..."
    ]
  }'
```
Expected:
- Registry saved in `results/web3_registry.json`

---

### Step 5 — Publish Waterfall From Deal Spec
```bash
curl -s -X POST http://localhost:8000/web3/waterfall/publish/DEAL_2026_001 \
  -H "Content-Type: application/json" \
  -H "X-User-Role: arranger" \
  -d '{
    "payment_token": "0xUSDC...",
    "tranches": [
      "0xTrancheA...",
      "0xTrancheM...",
      "0xTrancheB..."
    ],
    "trustee_address": "0xTrustee...",
    "servicer_address": "0xServicer...",
    "trustee_fees_bps": 10,
    "servicer_fees_bps": 25,
    "principal_sequential": true
  }'
```
Expected:
- `transaction_hash`

---

### Step 6 — Publish Loan Tape From Platform (Single Period)
```bash
curl -s -X POST http://localhost:8000/web3/oracle/publish/DEAL_2026_001/1 \
  -H "Content-Type: application/json" \
  -H "X-User-Role: servicer"
```
Expected:
- `transaction_hash`

---

### Step 7 — Publish Loan Tape Range
```bash
curl -s -X POST http://localhost:8000/web3/oracle/publish/DEAL_2026_001 \
  -H "Content-Type: application/json" \
  -H "X-User-Role: servicer" \
  -d '{"start_period": 1, "end_period": 3}'
```
Expected:
- `transactions` list with 3 hashes

---

### Step 8 — Execute Waterfall
```bash
curl -s -X POST http://localhost:8000/web3/waterfall/execute \
  -H "Content-Type: application/json" \
  -H "X-User-Role: arranger" \
  -d '{
    "deal_id": "DEAL_2026_001",
    "period_number": 1
  }'
```
Expected:
- `transaction_hash`

---

### Step 9 — Full Publish Workflow (Combined)
```bash
curl -s -X POST http://localhost:8000/web3/deals/DEAL_2026_001/publish \
  -H "Content-Type: application/json" \
  -H "X-User-Role: arranger" \
  -d '{
    "deal_name": "RMBS 2026-1",
    "arranger": "0xArranger...",
    "closing_date": 1767225600,
    "maturity_date": 1893456000,
    "payment_token": "0xUSDC...",
    "transfer_validator": "0xValidator...",
    "admin": "0xAdmin...",
    "issuer": "0xIssuer...",
    "trustee": "0xTrustee...",
    "trustee_address": "0xTrustee...",
    "servicer_address": "0xServicer..."
  }'
```
Expected:
- `register_tx` and `tranche_txs`
- `waterfall_tx` if tranche addresses were registered or provided

---

## 4) Validation Checklist

- Web3 health returns `connected: true`
- Deal appears in `GET /web3/deals`
- Tranches exist and addresses are recorded
- Waterfall configured successfully (tx hash)
- Oracle submissions succeed (tx hash)
- Waterfall execution succeeds (tx hash)

---

## 5) Notes

- Waterfall execution requires collections data and adequate funding.
- ServicerOracle expects sequential periods.
- Tranche address registry is stored in `results/web3_registry.json`.
