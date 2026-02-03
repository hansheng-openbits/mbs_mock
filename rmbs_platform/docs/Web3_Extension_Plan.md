# RMBS Platform - Web3 Extension Plan

This document defines a concrete, phased plan to extend the existing RMBS platform into a Web3-enabled application. It aligns with current architecture (FastAPI + Streamlit + core engine) and applies industry best practices for privacy, compliance, and smart contract security.

---

## 1) Objectives

- Tokenize RMBS tranches as regulated digital securities.
- Preserve off-chain privacy for loan-level data.
- Automate distributions and audit trails via on-chain records.
- Integrate KYC/AML and transfer restrictions by design.
- Provide institutional-grade governance, security, and auditability.

---

## 2) Current Architecture Snapshot

The platform already implements role-based workflows (Arranger, Servicer, Investor, Auditor) and provides a clean separation between UI, API, and engine.

Existing layers:
- UI: Streamlit portals in `ui/`
- API: FastAPI in `api_main.py`
- Engine: Waterfall, credit, and market analytics in `engine/`
- Data: Versioned JSON/CSV in `deals/`, `collateral/`, `performance/`

---

## 3) Target Web3 Architecture

### On-Chain (Smart Contracts)
- **DealRegistry**: Registers deals, metadata, and document hashes.
- **TrancheToken**: Security token for each tranche (ERC-3643 / ERC-1400).
- **ComplianceRegistry**: KYC/AML / accreditation / jurisdiction controls.
- **WaterfallExecution**: Records and executes distributions.
- **Treasury/Escrow**: Holds settlement assets for payout.
- **AuditLog**: Append-only log for proofs and audit bundles.

### Off-Chain (Services)
- **Tokenization Service**: Orchestrates issuance and on-chain state.
- **Oracle Publisher**: Signs engine outputs and submits proofs.
- **Compliance Service**: Integrates KYC/AML providers and sanctions lists.
- **Data Vault**: Encrypted storage of loan tapes and audit bundles.
- **Indexer/Analytics**: Event indexing and portfolio analytics.

---

## 4) Data & Privacy Model

- Loan-level data and PII never touch the public chain.
- Each dataset version is hashed (Merkle root) and anchored on-chain.
- Engine outputs are signed and submitted as oracle updates.
- Optional advanced privacy: TEE or ZK proofs in later phase.

---

## 5) Smart Contract Standards

Recommended baseline:
- **ERC-3643 (T-REX)** or **ERC-1400** for regulated securities.
- Transfer restrictions, partitioned balances, forced transfer, document registry.

---

## 6) Concrete Implementation Phases

### Phase 1: Tokenization MVP (4-6 weeks)
Deliverables:
- `contracts/` repo with DealRegistry + TrancheToken + ComplianceRegistry.
- New service module: `services/tokenization_service.py`
- New API endpoints:
  - `POST /web3/deals/{deal_id}/issue`
  - `GET /web3/deals/{deal_id}/status`
  - `POST /web3/investors/{address}/verify`
- UI additions: investor holdings + deal issuance status

Outcome:
- On-chain representation of tranches and cap table
- Compliance gate for transfers

### Phase 2: Oracle + Payout Automation (6-8 weeks)
Deliverables:
- `services/oracle_publisher.py`
- WaterfallExecution + Treasury contracts
- New API endpoints:
  - `POST /web3/deals/{deal_id}/payouts/preview`
  - `POST /web3/deals/{deal_id}/payouts/execute`
- Audit bundle anchoring (hash stored on-chain)

Outcome:
- Distribution records on-chain
- Automated payouts using stablecoins

### Phase 3: Privacy & Audit Hardening (6-10 weeks)
Deliverables:
- Merkle/MPC-based proof system for performance metrics
- TEE or ZK optional verification module
- Auditor portal enhancements:
  - Proof verification
  - Report attestation on-chain

Outcome:
- Higher regulatory confidence
- Auditable proof of cashflow computations

### Phase 4: Secondary Market + DeFi Integration (8-12 weeks)
Deliverables:
- Transfer-aware secondary market integration
- Permissioned AMM or ATS workflow
- On-chain lending/repurchase collateral hooks

Outcome:
- Liquidity options without sacrificing compliance

---

## 7) API & Service Integration Plan

### New Service Modules
- `services/tokenization_service.py`
- `services/oracle_publisher.py`
- `services/compliance_service.py`
- `services/web3_client.py` (chain provider + signing)

### API Routes (Proposed)
- `POST /web3/deals/{deal_id}/issue`
- `GET /web3/deals/{deal_id}/status`
- `POST /web3/deals/{deal_id}/payouts/preview`
- `POST /web3/deals/{deal_id}/payouts/execute`
- `POST /web3/investors/{address}/verify`
- `GET /web3/audit/{deal_id}/anchors`

---

## 8) Security & Governance Requirements

- Multi-sig ownership for contract admin and treasury.
- Timelock upgrades with 24-48h delay.
- Role-based access control mirroring platform roles.
- Key management via HSM/KMS.
- Mandatory audits for contract changes.

---

## 9) Testing Strategy

- Smart contract unit + integration tests.
- End-to-end tests: deal creation → issuance → payouts.
- Reconciliation tests: engine output vs on-chain records.

---

## 10) Risks & Mitigations

- **Regulatory risk**: Use regulated token standards and compliance registry.
- **Data privacy risk**: Off-chain encryption + hashed anchoring.
- **Oracle risk**: Signed results + multi-oracle validation.
- **Smart contract risk**: Audits, formal verification for critical paths.

---

## 11) Recommended Next Steps

1. Confirm chain choice (permissioned L2 vs regulated L1).
2. Define initial token standard (ERC-3643 vs ERC-1400).
3. Create contracts repository and CI pipeline.
4. Implement Phase 1 API endpoints + services.
5. Run pilot issuance with a test deal.

