# RMBS Web3 Tokenization Platform Design

**Document Version:** 1.1  
**Date:** January 29, 2026  
**Author:** RMBS Platform Development Team  
**Status:** Design Draft - Pending Review  
**Change Log:** v1.1 - Added comprehensive Auditor stakeholder integration  

---

## Executive Summary

This document outlines the design for extending the RMBS Platform into a **Web3-native tokenization platform** that enables:

1. **Arrangers/Issuers** to tokenize RMBS tranches and distribute them to investors
2. **Investors** to purchase, hold, and trade tokenized tranche securities
3. **Servicers** to update loan performance data with on-chain verification
4. **Auditors/Regulators** to access transparent, verifiable deal performance

The design prioritizes **privacy**, **security**, and **regulatory compliance** while leveraging blockchain's transparency and programmability benefits.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Stakeholder Roles](#stakeholder-roles)
3. [Privacy Architecture](#privacy-architecture)
4. [Security Framework](#security-framework)
5. [Smart Contract Design](#smart-contract-design)
6. [Tokenization Mechanics](#tokenization-mechanics)
7. [Servicer Integration](#servicer-integration)
8. [Investor Experience](#investor-experience)
9. [Auditor Integration](#auditor-integration)
10. [Compliance & Regulatory](#compliance--regulatory)
11. [Technical Implementation](#technical-implementation)
12. [Risk Mitigation](#risk-mitigation)
13. [Roadmap](#roadmap)

---

## Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         WEB3 RMBS TOKENIZATION PLATFORM                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     APPLICATION LAYER                                │    │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐           │    │
│  │  │  Arranger │ │  Investor │ │  Servicer │ │  Auditor  │           │    │
│  │  │   Portal  │ │   Portal  │ │   Portal  │ │   Portal  │           │    │
│  │  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘           │    │
│  └────────┼─────────────┼─────────────┼─────────────┼───────────────────┘    │
│           │             │             │             │                        │
│  ┌────────▼─────────────▼─────────────▼─────────────▼───────────────────┐    │
│  │                     MIDDLEWARE LAYER                                  │    │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                 │    │
│  │  │     API      │ │   Privacy    │ │   Oracle     │                 │    │
│  │  │   Gateway    │ │   Gateway    │ │   Network    │                 │    │
│  │  │  (REST/WS)   │ │ (ZK Proofs)  │ │ (Chainlink)  │                 │    │
│  │  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘                 │    │
│  └─────────┼────────────────┼────────────────┼──────────────────────────┘    │
│            │                │                │                               │
│  ┌─────────▼────────────────▼────────────────▼──────────────────────────┐    │
│  │                     PRIVACY COMPUTE LAYER                             │    │
│  │  ┌──────────────────────────────────────────────────────────────┐   │    │
│  │  │              TRUSTED EXECUTION ENVIRONMENT (TEE)              │   │    │
│  │  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐            │   │    │
│  │  │  │  Loan Data  │ │  Cashflow   │ │  Credit     │            │   │    │
│  │  │  │  Processor  │ │  Calculator │ │  Analytics  │            │   │    │
│  │  │  └─────────────┘ └─────────────┘ └─────────────┘            │   │    │
│  │  │                  (SGX/Nitro/SEV)                              │   │    │
│  │  └──────────────────────────────────────────────────────────────┘   │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                │                                             │
│  ┌─────────────────────────────▼────────────────────────────────────────┐    │
│  │                     BLOCKCHAIN LAYER                                  │    │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                 │    │
│  │  │   Tranche    │ │  Waterfall   │ │   Access     │                 │    │
│  │  │   Tokens     │ │   Contract   │ │   Control    │                 │    │
│  │  │  (ERC-1400)  │ │  (Payouts)   │ │    (RBAC)    │                 │    │
│  │  └──────────────┘ └──────────────┘ └──────────────┘                 │    │
│  │                                                                      │    │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                 │    │
│  │  │    Deal      │ │   Oracle     │ │  Compliance  │                 │    │
│  │  │   Registry   │ │   Consumer   │ │   Registry   │                 │    │
│  │  └──────────────┘ └──────────────┘ └──────────────┘                 │    │
│  │                                                                      │    │
│  │              Ethereum L2 (Arbitrum/Optimism/zkSync)                 │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │                     DATA LAYER (Off-Chain)                           │    │
│  │  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐              │    │
│  │  │   Encrypted   │ │    RMBS       │ │   Document    │              │    │
│  │  │   Loan Data   │ │   Engine      │ │    Vault      │              │    │
│  │  │   (IPFS+Enc)  │ │  (Existing)   │ │   (Legal)     │              │    │
│  │  └───────────────┘ └───────────────┘ └───────────────┘              │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Design Principles

1. **Privacy by Design**: Sensitive loan data never touches the public blockchain
2. **Defense in Depth**: Multiple security layers (TEE, encryption, access control)
3. **Regulatory Alignment**: Securities law compliance built into smart contracts
4. **Scalability**: Off-chain computation, on-chain verification
5. **Interoperability**: Standard interfaces (ERC-1400, ERC-3643)
6. **Auditability**: Complete audit trail with cryptographic proofs

---

## Stakeholder Roles

### Role Matrix

| Role | On-Chain Actions | Off-Chain Access | KYC/AML | Verification |
|------|------------------|------------------|---------|--------------|
| **Arranger** | Deploy deal, mint tokens, configure waterfall | Full deal data, loan tape | Required | Institutional |
| **Issuer** | Approve issuance, manage SPV | Deal structure, legal docs | Required | SPV verification |
| **Investor** | Buy/sell tokens, claim yields | Portfolio, aggregated metrics | Required | Accredited investor |
| **Servicer** | Submit performance data (via oracle) | Loan-level data | Required | Licensed servicer |
| **Trustee** | Trigger waterfall, manage reserves | Full deal access | Required | Licensed trustee |
| **Auditor** | View audit logs, challenge data, generate attestations | Full historical data, loan tape (time-limited) | Required | Certified auditor |
| **Regulator** | Emergency pause, subpoena data | Full access on demand | N/A | Government authority |

### Auditor Role Types

| Auditor Type | Scope | Access Level | Typical Duration | Certification |
|--------------|-------|--------------|------------------|---------------|
| **External Financial Auditor** | Annual financial statements, deal performance | Full deal + loan tape | 4-8 weeks/year | CPA, Big 4 |
| **Internal Auditor** | Ongoing compliance, controls testing | Continuous access to select deals | Permanent | CIA, CISA |
| **Rating Agency Analyst** | Credit surveillance, rating review | Performance data, stratifications | Quarterly review | S&P, Moody's, Fitch |
| **Regulatory Examiner** | Compliance examination | Full access (subpoena) | As needed | SEC, OCC, CFPB |
| **Forensic Auditor** | Fraud investigation, dispute resolution | Full + historical archives | Event-driven | CFE, forensic specialist |
| **Smart Contract Auditor** | Code security, ZK circuit review | Contract source, deployment logs | Pre-launch + updates | Trail of Bits, OZ |

### Access Control Architecture

```solidity
// Role-based access control hierarchy
enum Role {
    NONE,           // 0 - No access
    INVESTOR,       // 1 - Can hold tokens, view portfolio
    SERVICER,       // 2 - Can submit performance data
    TRUSTEE,        // 3 - Can execute waterfall, manage funds
    ARRANGER,       // 4 - Can deploy deals, configure structure
    AUDITOR,        // 5 - Can view all data, generate reports
    ADMIN,          // 6 - Can manage roles, upgrade contracts
    REGULATOR       // 7 - Emergency powers, full access
}

// Multi-sig requirements by action
ActionType.DEPLOY_DEAL       → 2-of-3 Arranger + 1-of-2 Issuer
ActionType.MINT_TOKENS       → 2-of-3 Arranger + 1-of-1 Trustee
ActionType.EXECUTE_WATERFALL → 1-of-1 Trustee (or 2-of-3 if delayed)
ActionType.EMERGENCY_PAUSE   → 1-of-1 Regulator (or 3-of-5 Trustees)
ActionType.UPGRADE_CONTRACT  → 3-of-5 Admin + 48hr timelock
```

---

## Privacy Architecture

### Privacy Threat Model

| Data Type | Sensitivity | Privacy Requirement | Solution |
|-----------|-------------|---------------------|----------|
| Loan-level PII | Critical | Zero public exposure | TEE + encryption |
| Individual loan balance | High | Aggregation only | ZK proofs |
| Investor holdings | Medium | Private to investor | Encrypted storage |
| Pool-level metrics | Low | Public transparency | On-chain |
| Waterfall cashflows | Low | Public transparency | On-chain |

### Zero-Knowledge Proof Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ZERO-KNOWLEDGE PROOF SYSTEM                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────┐         ┌──────────────────┐                      │
│  │   Private Input  │         │   Public Output  │                      │
│  │  (Loan Tape)     │   ───▶  │  (Pool Metrics)  │                      │
│  │                  │   ZK    │                  │                      │
│  │  • 1000 loans    │  Proof  │  • Total balance │                      │
│  │  • FICO scores   │         │  • Avg FICO      │                      │
│  │  • LTV ratios    │         │  • Avg LTV       │                      │
│  │  • Addresses     │         │  • DQ rate       │                      │
│  └──────────────────┘         └──────────────────┘                      │
│           │                            │                                 │
│           │                            │                                 │
│           ▼                            ▼                                 │
│  ┌──────────────────┐         ┌──────────────────┐                      │
│  │  ZK Circuit      │         │   Verifier       │                      │
│  │  (Circom/Noir)   │         │   (On-chain)     │                      │
│  │                  │         │                  │                      │
│  │  Computes:       │         │  Verifies:       │                      │
│  │  sum(balances)   │         │  proof is valid  │                      │
│  │  avg(FICO)       │         │  metrics correct │                      │
│  │  delinq_rate     │         │  no data leaked  │                      │
│  └──────────────────┘         └──────────────────┘                      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### ZK Circuits for RMBS

```typescript
// ZK Circuit: Pool Metrics Proof
circuit PoolMetricsProof {
    // Private inputs (loan tape - never revealed)
    private input loan_balances[1000]: Field;
    private input loan_ficos[1000]: Field;
    private input loan_ltvs[1000]: Field;
    private input loan_status[1000]: Field; // 0=current, 1=30DQ, 2=60DQ, etc.
    
    // Public inputs (commitments)
    public input loan_tape_hash: Field; // Merkle root of encrypted loan data
    public input reporting_period: Field;
    
    // Public outputs (verified metrics)
    public output total_balance: Field;
    public output weighted_avg_fico: Field;
    public output weighted_avg_ltv: Field;
    public output current_rate: Field;
    public output delinquency_30: Field;
    public output delinquency_60_plus: Field;
    
    // Constraints
    // 1. Sum of balances equals total_balance
    // 2. Weighted average calculations are correct
    // 3. Delinquency buckets are correctly computed
    // 4. Loan tape hash matches committed data
}

// ZK Circuit: Waterfall Calculation Proof
circuit WaterfallProof {
    // Private inputs
    private input collections: Field;
    private input bond_balances[10]: Field;
    private input coupon_rates[10]: Field;
    
    // Public inputs
    public input waterfall_rules_hash: Field; // Commitment to deal rules
    
    // Public outputs
    public output interest_payments[10]: Field;
    public output principal_payments[10]: Field;
    public output remaining_funds: Field;
    
    // Constraints: Waterfall rules correctly applied
}
```

### Trusted Execution Environment (TEE) Design

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     TEE ENCLAVE (Intel SGX / AWS Nitro)                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    SECURE PROCESSING ZONE                         │   │
│  │                                                                   │   │
│  │  Input (Encrypted)          Process              Output (Signed)  │   │
│  │  ┌─────────────┐           ┌─────────────┐      ┌─────────────┐  │   │
│  │  │ Loan Tape   │──decrypt──│ RMBS Engine │──────│Pool Metrics │  │   │
│  │  │ (AES-256)   │           │ (Waterfall) │      │(Attestation)│  │   │
│  │  └─────────────┘           └─────────────┘      └─────────────┘  │   │
│  │                                                                   │   │
│  │  Keys sealed to enclave identity (MRENCLAVE)                     │   │
│  │  Remote attestation verifiable on-chain                          │   │
│  │                                                                   │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  Memory encryption: AES-128-CTR (hardware)                              │
│  Code integrity: Measured boot, signed enclave                          │
│  Side-channel protection: Constant-time operations                       │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Data Encryption Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     DATA ENCRYPTION LAYERS                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Layer 1: Field-Level Encryption (PII)                                  │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Loan ID: 12345                                                   │   │
│  │ Borrower Name: [AES-256-GCM encrypted] ─────▶ Only Servicer     │   │
│  │ SSN: [AES-256-GCM encrypted] ───────────────▶ Only Servicer     │   │
│  │ Property Address: [AES-256-GCM encrypted] ──▶ Only Servicer     │   │
│  │ Balance: 250000 (plain - needed for metrics)                    │   │
│  │ FICO: 750 (plain - needed for metrics)                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  Layer 2: Document Encryption (Loan Files)                              │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Note: [encrypted, IPFS CID: Qm...]                              │   │
│  │ Mortgage: [encrypted, IPFS CID: Qm...]                          │   │
│  │ Appraisal: [encrypted, IPFS CID: Qm...]                         │   │
│  │                                                                  │   │
│  │ Key: Shamir's Secret Sharing (3-of-5 trustees)                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  Layer 3: Transport Encryption                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ All API calls: TLS 1.3 with certificate pinning                 │   │
│  │ Wallet connections: Encrypted channel via WalletConnect v2      │   │
│  │ P2P data: Noise protocol (libp2p)                               │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Security Framework

### Smart Contract Security

#### 1. Multi-Signature Controls

```solidity
// Multi-sig treasury contract
contract DealTreasury is MultiSigWallet {
    // Thresholds by action type
    mapping(ActionType => uint8) public requiredSignatures;
    
    constructor() {
        requiredSignatures[ActionType.DISTRIBUTE_INTEREST] = 1; // Trustee only
        requiredSignatures[ActionType.DISTRIBUTE_PRINCIPAL] = 2; // 2 of 3 trustees
        requiredSignatures[ActionType.EMERGENCY_WITHDRAW] = 3; // 3 of 5 trustees
        requiredSignatures[ActionType.UPGRADE_CONTRACT] = 4; // 4 of 5 + timelock
    }
    
    function executeAction(
        ActionType action,
        bytes calldata data,
        bytes[] calldata signatures
    ) external {
        require(signatures.length >= requiredSignatures[action], "Insufficient signatures");
        // Verify signatures and execute
    }
}
```

#### 2. Time-Lock Mechanisms

```solidity
// Timelock for critical operations
contract TimelockController {
    uint256 public constant MIN_DELAY = 48 hours;
    uint256 public constant MAX_DELAY = 30 days;
    
    mapping(bytes32 => uint256) public pendingActions;
    
    function scheduleAction(
        address target,
        bytes calldata data,
        uint256 delay
    ) external onlyRole(ADMIN_ROLE) returns (bytes32) {
        require(delay >= MIN_DELAY && delay <= MAX_DELAY, "Invalid delay");
        
        bytes32 actionId = keccak256(abi.encode(target, data, block.timestamp));
        pendingActions[actionId] = block.timestamp + delay;
        
        emit ActionScheduled(actionId, target, data, block.timestamp + delay);
        return actionId;
    }
    
    function executeAction(bytes32 actionId) external {
        require(pendingActions[actionId] != 0, "Action not scheduled");
        require(block.timestamp >= pendingActions[actionId], "Timelock not expired");
        
        // Execute action
        delete pendingActions[actionId];
    }
    
    function cancelAction(bytes32 actionId) external onlyRole(ADMIN_ROLE) {
        delete pendingActions[actionId];
        emit ActionCancelled(actionId);
    }
}
```

#### 3. Circuit Breakers

```solidity
// Emergency pause mechanism
contract EmergencyPausable {
    bool public paused;
    uint256 public pausedAt;
    uint256 public constant AUTO_RESUME_DELAY = 7 days;
    
    // Roles that can pause
    mapping(address => bool) public pausers;
    
    modifier whenNotPaused() {
        require(!paused || _canAutoResume(), "Contract is paused");
        _;
    }
    
    function pause(string calldata reason) external {
        require(pausers[msg.sender], "Not authorized to pause");
        paused = true;
        pausedAt = block.timestamp;
        emit Paused(msg.sender, reason);
    }
    
    function unpause() external onlyRole(ADMIN_ROLE) {
        paused = false;
        emit Unpaused(msg.sender);
    }
    
    function _canAutoResume() internal view returns (bool) {
        // Auto-resume after 7 days unless explicitly extended
        return block.timestamp > pausedAt + AUTO_RESUME_DELAY;
    }
}
```

### Oracle Security

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     ORACLE SECURITY ARCHITECTURE                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    DATA SUBMISSION FLOW                          │   │
│  │                                                                  │   │
│  │  Servicer                  TEE Oracle              Smart Contract│   │
│  │     │                         │                          │       │   │
│  │     │  1. Submit loan data    │                          │       │   │
│  │     │  (encrypted + signed)   │                          │       │   │
│  │     │ ───────────────────────▶│                          │       │   │
│  │     │                         │                          │       │   │
│  │     │                         │ 2. Decrypt in TEE        │       │   │
│  │     │                         │    Validate data         │       │   │
│  │     │                         │    Compute metrics       │       │   │
│  │     │                         │    Generate ZK proof     │       │   │
│  │     │                         │                          │       │   │
│  │     │                         │ 3. Submit metrics + proof│       │   │
│  │     │                         │ ────────────────────────▶│       │   │
│  │     │                         │                          │       │   │
│  │     │                         │                          │ 4. Verify│
│  │     │                         │                          │    proof │
│  │     │                         │                          │    Store │
│  │     │                         │                          │    metrics
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  Security Measures:                                                      │
│  • Data signed by servicer's registered key                             │
│  • TEE attestation verified on-chain                                    │
│  • ZK proof ensures computation integrity                               │
│  • Staked oracle operators (slashable for misbehavior)                  │
│  • Multi-oracle aggregation for critical data                           │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Management

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     KEY MANAGEMENT HIERARCHY                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Master Key (Cold Storage - HSM)                                        │
│  └── Deal Key (Per-Deal)                                                │
│      ├── Servicer Key (Loan data access)                                │
│      │   └── Derived per servicer, rotated quarterly                   │
│      ├── Trustee Key (Waterfall execution)                              │
│      │   └── Shamir 3-of-5 split across trustees                       │
│      ├── Investor Key (Portfolio access)                                │
│      │   └── Derived per investor, tied to wallet                      │
│      └── Auditor Key (Historical data access)                           │
│          └── Time-limited, audit-scoped                                 │
│                                                                          │
│  Key Derivation: BIP-32 HD paths                                        │
│  Encryption: AES-256-GCM                                                │
│  Signing: ECDSA secp256k1 (Ethereum) + Ed25519 (off-chain)             │
│  Key Storage: AWS KMS / Azure Key Vault / HashiCorp Vault               │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Smart Contract Design

### Contract Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     SMART CONTRACT HIERARCHY                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │                      CORE CONTRACTS                             │    │
│  │                                                                 │    │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────┐ │    │
│  │  │  DealRegistry   │  │  TokenFactory   │  │ AccessControl  │ │    │
│  │  │  (Singleton)    │  │  (Singleton)    │  │  (Singleton)   │ │    │
│  │  └────────┬────────┘  └────────┬────────┘  └───────┬────────┘ │    │
│  │           │                    │                   │          │    │
│  └───────────┼────────────────────┼───────────────────┼──────────┘    │
│              │                    │                   │               │
│  ┌───────────▼────────────────────▼───────────────────▼──────────┐    │
│  │                      DEAL CONTRACTS (Per Deal)                │    │
│  │                                                               │    │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │    │
│  │  │   DealProxy     │  │  WaterfallEngine│  │   Treasury   │ │    │
│  │  │  (Upgradeable)  │  │  (Waterfall)    │  │   (Escrow)   │ │    │
│  │  └────────┬────────┘  └────────┬────────┘  └──────┬───────┘ │    │
│  │           │                    │                  │         │    │
│  │  ┌────────▼────────┐  ┌────────▼────────┐  ┌──────▼───────┐│    │
│  │  │TrancheToken[0]  │  │  PerformanceLog │  │  ReserveFund ││    │
│  │  │  (ERC-1400)     │  │  (Oracle Data)  │  │  (Interest)  ││    │
│  │  └─────────────────┘  └─────────────────┘  └──────────────┘│    │
│  │  ┌─────────────────┐                                       │    │
│  │  │TrancheToken[1]  │                                       │    │
│  │  │  (ERC-1400)     │                                       │    │
│  │  └─────────────────┘                                       │    │
│  │           ...                                               │    │
│  └───────────────────────────────────────────────────────────────┘    │
│                                                                        │
│  ┌───────────────────────────────────────────────────────────────┐    │
│  │                      INFRASTRUCTURE CONTRACTS                  │    │
│  │                                                                │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │    │
│  │  │  OracleHub   │  │ Compliance   │  │  Timelock    │        │    │
│  │  │ (Chainlink)  │  │  (KYC/AML)   │  │  Controller  │        │    │
│  │  └──────────────┘  └──────────────┘  └──────────────┘        │    │
│  │                                                                │    │
│  └───────────────────────────────────────────────────────────────┘    │
│                                                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

### ERC-1400 Security Token Implementation

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";

/**
 * @title TrancheToken
 * @notice ERC-1400 compliant security token representing an RMBS tranche
 * 
 * Features:
 * - Partitioned balances (for different investor classes)
 * - Transfer restrictions (KYC/AML, accreditation)
 * - Forced transfers (regulatory compliance)
 * - Document management (linked legal documents)
 * - Controller operations (corporate actions)
 */
contract TrancheToken is ERC20, AccessControl {
    
    // Roles
    bytes32 public constant CONTROLLER_ROLE = keccak256("CONTROLLER");
    bytes32 public constant TRANSFER_AGENT_ROLE = keccak256("TRANSFER_AGENT");
    
    // Deal reference
    address public immutable deal;
    uint256 public immutable trancheIndex;
    string public trancheClass; // "A1", "A2", "B", "M", etc.
    
    // Token metadata
    uint256 public couponRate; // bps (e.g., 500 = 5.00%)
    uint256 public originalBalance;
    uint256 public currentFactor; // 1e18 = 100%
    
    // Transfer restrictions
    mapping(address => bool) public frozenAccounts;
    mapping(bytes32 => mapping(address => bool)) public partitionOperators;
    
    // Compliance
    address public complianceRegistry;
    
    // Events (ERC-1400)
    event TransferByPartition(
        bytes32 indexed fromPartition,
        address operator,
        address indexed from,
        address indexed to,
        uint256 value,
        bytes data,
        bytes operatorData
    );
    
    event AuthorizedOperatorByPartition(
        bytes32 indexed partition,
        address indexed operator,
        address indexed tokenHolder
    );
    
    constructor(
        address _deal,
        uint256 _trancheIndex,
        string memory _name,
        string memory _symbol,
        uint256 _couponRate,
        uint256 _originalBalance
    ) ERC20(_name, _symbol) {
        deal = _deal;
        trancheIndex = _trancheIndex;
        couponRate = _couponRate;
        originalBalance = _originalBalance;
        currentFactor = 1e18;
        
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(CONTROLLER_ROLE, _deal);
    }
    
    // ========== TRANSFER RESTRICTIONS ==========
    
    /**
     * @notice Check if transfer is valid
     * @dev Implements ERC-1400 canTransfer
     */
    function canTransfer(
        address from,
        address to,
        uint256 value,
        bytes calldata data
    ) external view returns (bool, bytes1, bytes32) {
        // Check frozen accounts
        if (frozenAccounts[from] || frozenAccounts[to]) {
            return (false, 0x50, "Account frozen");
        }
        
        // Check KYC/AML compliance
        if (!IComplianceRegistry(complianceRegistry).isVerified(to)) {
            return (false, 0x51, "Recipient not verified");
        }
        
        // Check accreditation (for US investors)
        if (!IComplianceRegistry(complianceRegistry).isAccredited(to)) {
            return (false, 0x52, "Recipient not accredited");
        }
        
        // Check balance
        if (balanceOf(from) < value) {
            return (false, 0x53, "Insufficient balance");
        }
        
        return (true, 0x00, "");
    }
    
    /**
     * @notice Transfer with compliance check
     */
    function transfer(address to, uint256 amount) public override returns (bool) {
        (bool canDo, bytes1 code, ) = this.canTransfer(msg.sender, to, amount, "");
        require(canDo, string(abi.encodePacked("Transfer restricted: ", code)));
        
        return super.transfer(to, amount);
    }
    
    // ========== CONTROLLER OPERATIONS ==========
    
    /**
     * @notice Forced transfer by controller (regulatory compliance)
     * @dev Only callable by CONTROLLER_ROLE with documented reason
     */
    function controllerTransfer(
        address from,
        address to,
        uint256 value,
        bytes calldata data,
        bytes calldata operatorData
    ) external onlyRole(CONTROLLER_ROLE) {
        require(bytes(operatorData).length > 0, "Reason required");
        
        _transfer(from, to, value);
        
        emit TransferByPartition(
            bytes32(0),
            msg.sender,
            from,
            to,
            value,
            data,
            operatorData
        );
    }
    
    /**
     * @notice Redeem tokens (principal paydown)
     * @dev Called by waterfall contract when principal is distributed
     */
    function redeem(
        address holder,
        uint256 value,
        bytes calldata data
    ) external onlyRole(CONTROLLER_ROLE) {
        _burn(holder, value);
        
        // Update factor
        uint256 totalSupply_ = totalSupply();
        if (totalSupply_ > 0) {
            currentFactor = (totalSupply_ * 1e18) / originalBalance;
        } else {
            currentFactor = 0;
        }
    }
    
    // ========== ACCOUNT MANAGEMENT ==========
    
    /**
     * @notice Freeze account (regulatory/compliance)
     */
    function freezeAccount(address account) external onlyRole(TRANSFER_AGENT_ROLE) {
        frozenAccounts[account] = true;
        emit AccountFrozen(account);
    }
    
    /**
     * @notice Unfreeze account
     */
    function unfreezeAccount(address account) external onlyRole(TRANSFER_AGENT_ROLE) {
        frozenAccounts[account] = false;
        emit AccountUnfrozen(account);
    }
    
    // ========== DOCUMENT MANAGEMENT ==========
    
    mapping(bytes32 => string) public documents;
    
    function setDocument(bytes32 name, string calldata uri) external onlyRole(DEFAULT_ADMIN_ROLE) {
        documents[name] = uri;
        emit DocumentUpdated(name, uri);
    }
    
    event AccountFrozen(address indexed account);
    event AccountUnfrozen(address indexed account);
    event DocumentUpdated(bytes32 indexed name, string uri);
}
```

### Waterfall Contract

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/security/Pausable.sol";

/**
 * @title WaterfallEngine
 * @notice Executes RMBS waterfall logic on-chain
 * 
 * Waterfall priority:
 * 1. Trustee fees
 * 2. Servicer fees
 * 3. Senior interest
 * 4. Senior principal
 * 5. Mezzanine interest
 * 6. Mezzanine principal
 * 7. Subordinate interest
 * 8. Subordinate principal
 * 9. Residual/excess spread
 */
contract WaterfallEngine is ReentrancyGuard, Pausable {
    
    // Deal configuration
    address public immutable deal;
    address public immutable treasury;
    uint256 public immutable numTranches;
    
    // Tranche tokens
    address[] public tranches;
    
    // Waterfall configuration
    struct WaterfallStep {
        StepType stepType;
        uint256 trancheIndex;
        uint256 amount; // 0 = all available
        bool isPercentage; // true = amount is bps of available funds
    }
    
    enum StepType {
        FEE,
        INTEREST,
        PRINCIPAL,
        RESERVE_DEPOSIT,
        RESERVE_RELEASE,
        RESIDUAL
    }
    
    WaterfallStep[] public interestWaterfall;
    WaterfallStep[] public principalWaterfall;
    
    // Period state
    uint256 public currentPeriod;
    mapping(uint256 => PeriodState) public periodStates;
    
    struct PeriodState {
        uint256 interestCollected;
        uint256 principalCollected;
        uint256 lossesRealized;
        bool waterfallExecuted;
        mapping(uint256 => uint256) interestPaid; // trancheIndex => amount
        mapping(uint256 => uint256) principalPaid;
    }
    
    // Events
    event WaterfallExecuted(
        uint256 indexed period,
        uint256 interestDistributed,
        uint256 principalDistributed,
        uint256 residual
    );
    
    event TranchePaid(
        uint256 indexed period,
        uint256 indexed trancheIndex,
        uint256 interestAmount,
        uint256 principalAmount
    );
    
    constructor(
        address _deal,
        address _treasury,
        address[] memory _tranches
    ) {
        deal = _deal;
        treasury = _treasury;
        tranches = _tranches;
        numTranches = _tranches.length;
    }
    
    /**
     * @notice Execute waterfall for current period
     * @dev Called by trustee or automated keeper
     * 
     * @param interestCollected Interest received from collateral
     * @param principalCollected Principal received from collateral
     * @param lossesRealized Losses to allocate
     * @param oracleProof ZK proof of oracle data validity
     */
    function executeWaterfall(
        uint256 interestCollected,
        uint256 principalCollected,
        uint256 lossesRealized,
        bytes calldata oracleProof
    ) external nonReentrant whenNotPaused {
        require(msg.sender == trustee || hasRole(KEEPER_ROLE, msg.sender), "Not authorized");
        
        // Verify oracle proof
        require(_verifyOracleProof(oracleProof, interestCollected, principalCollected, lossesRealized), "Invalid proof");
        
        // Initialize period state
        PeriodState storage state = periodStates[currentPeriod];
        require(!state.waterfallExecuted, "Already executed");
        
        state.interestCollected = interestCollected;
        state.principalCollected = principalCollected;
        state.lossesRealized = lossesRealized;
        
        // Execute interest waterfall
        uint256 interestRemaining = interestCollected;
        for (uint256 i = 0; i < interestWaterfall.length && interestRemaining > 0; i++) {
            WaterfallStep memory step = interestWaterfall[i];
            uint256 payment = _executeStep(step, interestRemaining, state, true);
            interestRemaining -= payment;
        }
        
        // Execute principal waterfall
        uint256 principalRemaining = principalCollected;
        for (uint256 i = 0; i < principalWaterfall.length && principalRemaining > 0; i++) {
            WaterfallStep memory step = principalWaterfall[i];
            uint256 payment = _executeStep(step, principalRemaining, state, false);
            principalRemaining -= payment;
        }
        
        // Allocate losses (reverse seniority)
        if (lossesRealized > 0) {
            _allocateLosses(lossesRealized);
        }
        
        state.waterfallExecuted = true;
        currentPeriod++;
        
        emit WaterfallExecuted(
            currentPeriod - 1,
            interestCollected - interestRemaining,
            principalCollected - principalRemaining,
            interestRemaining + principalRemaining
        );
    }
    
    function _executeStep(
        WaterfallStep memory step,
        uint256 available,
        PeriodState storage state,
        bool isInterest
    ) internal returns (uint256 payment) {
        // Calculate payment amount
        if (step.isPercentage) {
            payment = (available * step.amount) / 10000;
        } else if (step.amount == 0) {
            payment = available;
        } else {
            payment = step.amount > available ? available : step.amount;
        }
        
        if (payment == 0) return 0;
        
        // Execute based on step type
        if (step.stepType == StepType.INTEREST || step.stepType == StepType.PRINCIPAL) {
            // Transfer to token holders
            address tranche = tranches[step.trancheIndex];
            ITreasury(treasury).distribute(tranche, payment);
            
            if (isInterest) {
                state.interestPaid[step.trancheIndex] += payment;
            } else {
                state.principalPaid[step.trancheIndex] += payment;
                // Burn tokens for principal paydown
                ITrancheToken(tranche).redeem(address(treasury), payment, "");
            }
            
            emit TranchePaid(currentPeriod, step.trancheIndex, 
                isInterest ? payment : 0, 
                isInterest ? 0 : payment);
        } else if (step.stepType == StepType.FEE) {
            // Pay fee to designated recipient
            ITreasury(treasury).payFee(step.trancheIndex, payment);
        } else if (step.stepType == StepType.RESERVE_DEPOSIT) {
            ITreasury(treasury).depositReserve(payment);
        }
        
        return payment;
    }
    
    function _allocateLosses(uint256 losses) internal {
        // Allocate losses in reverse seniority (subordinate first)
        uint256 remaining = losses;
        for (uint256 i = numTranches; i > 0 && remaining > 0; i--) {
            address tranche = tranches[i - 1];
            uint256 balance = ITrancheToken(tranche).totalSupply();
            uint256 lossAllocation = remaining > balance ? balance : remaining;
            
            if (lossAllocation > 0) {
                ITrancheToken(tranche).allocateLoss(lossAllocation);
                remaining -= lossAllocation;
                
                emit LossAllocated(currentPeriod, i - 1, lossAllocation);
            }
        }
    }
    
    function _verifyOracleProof(
        bytes calldata proof,
        uint256 interest,
        uint256 principal,
        uint256 losses
    ) internal view returns (bool) {
        // Verify ZK proof from oracle
        return IZKVerifier(zkVerifier).verify(proof, 
            abi.encode(deal, currentPeriod, interest, principal, losses));
    }
    
    event LossAllocated(uint256 indexed period, uint256 indexed trancheIndex, uint256 amount);
}
```

---

## Tokenization Mechanics

### Token Lifecycle

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     TOKEN LIFECYCLE                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. ORIGINATION                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Arranger deploys DealProxy contract                            │   │
│  │  → Deal structure defined (tranches, waterfall rules)           │   │
│  │  → Legal documents attached (IPFS hashes)                       │   │
│  │  → Compliance rules configured                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  2. TOKENIZATION                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  TokenFactory mints TrancheToken contracts                      │   │
│  │  → ERC-1400 tokens with transfer restrictions                   │   │
│  │  → Initial supply = original balance                            │   │
│  │  → Tokens held in escrow until distribution                     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  3. PRIMARY DISTRIBUTION                                                │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Investors subscribe via compliant channels                     │   │
│  │  → KYC/AML verification                                         │   │
│  │  → Accreditation check (if required)                            │   │
│  │  → USDC/USDT payment to escrow                                  │   │
│  │  → Tokens released to investor wallets                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  4. ONGOING OPERATIONS                                                  │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Monthly/Quarterly:                                             │   │
│  │  → Servicer submits performance data (via oracle)               │   │
│  │  → Waterfall executes (trustee/keeper)                          │   │
│  │  → Interest distributed to token holders                        │   │
│  │  → Principal paydown burns tokens (factor decreases)            │   │
│  │  → Investors claim yields via claim() function                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  5. SECONDARY TRADING                                                   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Investors trade on compliant venues                            │   │
│  │  → OTC desk (bilateral, compliance-checked)                     │   │
│  │  → ATS (Alternative Trading System)                             │   │
│  │  → DEX with compliance wrapper (future)                         │   │
│  │  → Transfer restrictions enforced on-chain                      │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  6. MATURITY/REDEMPTION                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Deal winds down:                                               │   │
│  │  → All principal returned (factor → 0)                          │   │
│  │  → Tokens fully burned                                          │   │
│  │  → Deal marked as terminated                                    │   │
│  │  → Audit trail preserved                                        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Yield Distribution

```solidity
/**
 * @title YieldDistributor
 * @notice Manages yield distribution to token holders
 * 
 * Features:
 * - Pull-based claiming (gas-efficient)
 * - Compound interest option
 * - Tax withholding support
 * - Multiple payment currencies (USDC, USDT, DAI)
 */
contract YieldDistributor {
    
    // Yield accounting per tranche per period
    mapping(address => mapping(uint256 => YieldRecord)) public yields;
    
    struct YieldRecord {
        uint256 totalYield;
        uint256 yieldPerToken; // Scaled by 1e18
        uint256 snapshotSupply;
        uint256 claimDeadline;
    }
    
    // Investor claim state
    mapping(address => mapping(address => uint256)) public lastClaimedPeriod;
    // investor => tranche => period
    
    // Unclaimed yields (escheated after deadline)
    mapping(address => uint256) public unclaimedYields;
    
    /**
     * @notice Record yield for distribution
     * @dev Called by WaterfallEngine after interest waterfall
     */
    function recordYield(
        address tranche,
        uint256 period,
        uint256 amount
    ) external onlyWaterfall {
        uint256 supply = IERC20(tranche).totalSupply();
        require(supply > 0, "No tokens outstanding");
        
        yields[tranche][period] = YieldRecord({
            totalYield: amount,
            yieldPerToken: (amount * 1e18) / supply,
            snapshotSupply: supply,
            claimDeadline: block.timestamp + 365 days
        });
        
        emit YieldRecorded(tranche, period, amount, supply);
    }
    
    /**
     * @notice Claim accumulated yields
     * @param tranche Tranche token address
     * @param periods Array of periods to claim
     */
    function claimYield(
        address tranche,
        uint256[] calldata periods
    ) external nonReentrant {
        uint256 totalClaim = 0;
        
        for (uint256 i = 0; i < periods.length; i++) {
            uint256 period = periods[i];
            YieldRecord memory record = yields[tranche][period];
            
            require(block.timestamp <= record.claimDeadline, "Claim deadline passed");
            require(period > lastClaimedPeriod[msg.sender][tranche], "Already claimed");
            
            // Calculate claim based on holdings at snapshot
            // Note: For precise accounting, would need historical balance snapshot
            uint256 balance = IERC20(tranche).balanceOf(msg.sender);
            uint256 claim = (balance * record.yieldPerToken) / 1e18;
            
            totalClaim += claim;
            lastClaimedPeriod[msg.sender][tranche] = period;
        }
        
        require(totalClaim > 0, "Nothing to claim");
        
        // Transfer yield (USDC)
        IERC20(paymentToken).safeTransfer(msg.sender, totalClaim);
        
        emit YieldClaimed(msg.sender, tranche, totalClaim);
    }
    
    /**
     * @notice Compound yields into additional tokens (optional)
     * @dev Reinvests yield by purchasing more tranche tokens
     */
    function compoundYield(
        address tranche,
        uint256[] calldata periods
    ) external nonReentrant {
        uint256 totalClaim = _calculateClaim(msg.sender, tranche, periods);
        
        // Purchase additional tokens at current price
        uint256 tokenPrice = _getTokenPrice(tranche);
        uint256 tokensToMint = (totalClaim * 1e18) / tokenPrice;
        
        ITrancheToken(tranche).mint(msg.sender, tokensToMint);
        
        emit YieldCompounded(msg.sender, tranche, totalClaim, tokensToMint);
    }
    
    event YieldRecorded(address indexed tranche, uint256 indexed period, uint256 amount, uint256 supply);
    event YieldClaimed(address indexed investor, address indexed tranche, uint256 amount);
    event YieldCompounded(address indexed investor, address indexed tranche, uint256 yieldAmount, uint256 tokensReceived);
}
```

---

## Servicer Integration

### Servicer Portal Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     SERVICER INTEGRATION FLOW                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    SERVICER PORTAL                                 │  │
│  │                                                                    │  │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐      │  │
│  │  │   Loan Status  │  │   Payment      │  │  Delinquency   │      │  │
│  │  │    Updates     │  │   Processing   │  │   Management   │      │  │
│  │  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘      │  │
│  │          │                   │                   │                │  │
│  └──────────┼───────────────────┼───────────────────┼────────────────┘  │
│             │                   │                   │                   │
│             ▼                   ▼                   ▼                   │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    DATA VALIDATION LAYER                          │  │
│  │                                                                   │  │
│  │  • Schema validation (loan fields, data types)                   │  │
│  │  • Business rule checks (balance reconciliation)                 │  │
│  │  • Anomaly detection (unusual activity flags)                    │  │
│  │  • Digital signature verification                                │  │
│  │                                                                   │  │
│  └───────────────────────────────┬──────────────────────────────────┘  │
│                                  │                                      │
│                                  ▼                                      │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    TEE PROCESSING ENCLAVE                         │  │
│  │                                                                   │  │
│  │  1. Decrypt servicer data (AES-256)                              │  │
│  │  2. Run RMBS engine calculations                                 │  │
│  │  3. Generate pool-level metrics                                  │  │
│  │  4. Create ZK proof of computation                               │  │
│  │  5. Sign output with enclave attestation                         │  │
│  │                                                                   │  │
│  └───────────────────────────────┬──────────────────────────────────┘  │
│                                  │                                      │
│                                  ▼                                      │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    ON-CHAIN SUBMISSION                            │  │
│  │                                                                   │  │
│  │  Oracle.submitPerformanceData({                                  │  │
│  │    dealId: "DEAL_2024_001",                                      │  │
│  │    period: 12,                                                   │  │
│  │    metrics: {                                                    │  │
│  │      totalBalance: 450_000_000,                                  │  │
│  │      interestCollected: 2_000_000,                               │  │
│  │      principalCollected: 5_000_000,                              │  │
│  │      delinquency60Plus: 0.025,                                   │  │
│  │      cpr: 0.12,                                                  │  │
│  │      cdr: 0.008                                                  │  │
│  │    },                                                            │  │
│  │    zkProof: "0x...",                                             │  │
│  │    attestation: "0x..."                                          │  │
│  │  })                                                              │  │
│  │                                                                   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Servicer Data Submission Contract

```solidity
/**
 * @title PerformanceOracle
 * @notice Receives and validates servicer performance data
 */
contract PerformanceOracle {
    
    // Registered servicers
    mapping(address => mapping(address => bool)) public authorizedServicers;
    // deal => servicer => authorized
    
    // Performance data
    mapping(address => mapping(uint256 => PerformanceData)) public performanceHistory;
    // deal => period => data
    
    struct PerformanceData {
        uint256 totalBalance;
        uint256 interestCollected;
        uint256 principalCollected;
        uint256 lossesRealized;
        uint256 delinquency30;
        uint256 delinquency60Plus;
        uint256 cpr; // bps
        uint256 cdr; // bps
        uint256 submittedAt;
        address submittedBy;
        bytes32 dataHash;
        bool verified;
    }
    
    // ZK verifier
    address public zkVerifier;
    
    // TEE attestation registry
    address public attestationRegistry;
    
    /**
     * @notice Submit monthly performance data
     * @dev Only callable by authorized servicer with valid proof
     */
    function submitPerformanceData(
        address deal,
        uint256 period,
        uint256[] calldata metrics, // [balance, interest, principal, loss, dq30, dq60, cpr, cdr]
        bytes calldata zkProof,
        bytes calldata teeAttestation
    ) external {
        require(authorizedServicers[deal][msg.sender], "Not authorized servicer");
        require(performanceHistory[deal][period].submittedAt == 0, "Already submitted");
        
        // Verify ZK proof
        require(_verifyZKProof(deal, period, metrics, zkProof), "Invalid ZK proof");
        
        // Verify TEE attestation
        require(_verifyAttestation(teeAttestation), "Invalid TEE attestation");
        
        // Store performance data
        performanceHistory[deal][period] = PerformanceData({
            totalBalance: metrics[0],
            interestCollected: metrics[1],
            principalCollected: metrics[2],
            lossesRealized: metrics[3],
            delinquency30: metrics[4],
            delinquency60Plus: metrics[5],
            cpr: metrics[6],
            cdr: metrics[7],
            submittedAt: block.timestamp,
            submittedBy: msg.sender,
            dataHash: keccak256(abi.encode(metrics)),
            verified: true
        });
        
        emit PerformanceDataSubmitted(deal, period, msg.sender, metrics);
        
        // Trigger waterfall if auto-execute enabled
        if (IDeal(deal).autoExecuteWaterfall()) {
            IDeal(deal).waterfallEngine().executeWaterfall(
                metrics[1], // interest
                metrics[2], // principal
                metrics[3], // losses
                zkProof
            );
        }
    }
    
    /**
     * @notice Challenge submitted data (dispute mechanism)
     * @dev Can be called by trustee or authorized auditor
     */
    function challengeData(
        address deal,
        uint256 period,
        bytes calldata evidence
    ) external onlyRole(AUDITOR_ROLE) {
        PerformanceData storage data = performanceHistory[deal][period];
        require(data.submittedAt > 0, "No data submitted");
        require(block.timestamp < data.submittedAt + CHALLENGE_PERIOD, "Challenge period ended");
        
        // Mark as disputed
        data.verified = false;
        
        emit DataChallenged(deal, period, msg.sender, evidence);
        
        // Initiate dispute resolution
        IDisputeResolver(disputeResolver).initiateDispute(deal, period, evidence);
    }
    
    function _verifyZKProof(
        address deal,
        uint256 period,
        uint256[] calldata metrics,
        bytes calldata proof
    ) internal view returns (bool) {
        // Public inputs for verification
        bytes32 publicInput = keccak256(abi.encode(deal, period, metrics));
        return IZKVerifier(zkVerifier).verify(proof, publicInput);
    }
    
    function _verifyAttestation(bytes calldata attestation) internal view returns (bool) {
        return IAttestationRegistry(attestationRegistry).verify(attestation);
    }
    
    event PerformanceDataSubmitted(
        address indexed deal,
        uint256 indexed period,
        address servicer,
        uint256[] metrics
    );
    
    event DataChallenged(
        address indexed deal,
        uint256 indexed period,
        address challenger,
        bytes evidence
    );
}
```

---

## Investor Experience

### Investor Portal Features

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     INVESTOR PORTAL                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  DASHBOARD                                                        │  │
│  │  ┌────────────────────────────────────────────────────────────┐ │  │
│  │  │  Portfolio Value: $2,450,000                               │ │  │
│  │  │  Unrealized P&L: +$45,000 (+1.8%)                          │ │  │
│  │  │  Pending Yields: $12,500 (3 claims available)              │ │  │
│  │  │  [Claim All Yields]                                        │ │  │
│  │  └────────────────────────────────────────────────────────────┘ │  │
│  │                                                                   │  │
│  │  HOLDINGS                                                        │  │
│  │  ┌────────────────────────────────────────────────────────────┐ │  │
│  │  │  Token      │ Balance  │ Factor │ YTM   │ OAS   │ Value    │ │  │
│  │  │  ───────────┼──────────┼────────┼───────┼───────┼──────────│ │  │
│  │  │  DEAL24-A1  │ 1.0M     │ 95.2%  │ 5.25% │ 45bps │ $980,000 │ │  │
│  │  │  DEAL24-A2  │ 500K     │ 92.1%  │ 5.75% │ 65bps │ $475,000 │ │  │
│  │  │  DEAL24-M   │ 250K     │ 88.5%  │ 7.50% │ 180bps│ $235,000 │ │  │
│  │  │  DEAL23-B   │ 800K     │ 78.2%  │ 9.25% │ 350bps│ $760,000 │ │  │
│  │  └────────────────────────────────────────────────────────────┘ │  │
│  │                                                                   │  │
│  │  DEAL PERFORMANCE (Selected: DEAL24-A1)                          │  │
│  │  ┌────────────────────────────────────────────────────────────┐ │  │
│  │  │  Pool Balance: $450M (Factor: 90%)                         │ │  │
│  │  │  CPR: 12.5% | CDR: 0.8% | DQ60+: 2.5%                      │ │  │
│  │  │                                                             │ │  │
│  │  │  [Chart: Historical Pool Balance]                          │ │  │
│  │  │  [Chart: CPR/CDR Trends]                                   │ │  │
│  │  │  [Chart: Delinquency Buckets]                              │ │  │
│  │  │                                                             │ │  │
│  │  │  Last Waterfall: Jan 15, 2026                              │ │  │
│  │  │  Interest Paid: $2.1M | Principal Paid: $5.0M              │ │  │
│  │  └────────────────────────────────────────────────────────────┘ │  │
│  │                                                                   │  │
│  │  ACTIONS                                                         │  │
│  │  ┌────────────────────────────────────────────────────────────┐ │  │
│  │  │  [View Deal Documents] [Download Tax Forms]                │ │  │
│  │  │  [Request Trade Quote] [View Audit Trail]                  │ │  │
│  │  │  [Set Alert Thresholds] [Export Portfolio]                 │ │  │
│  │  └────────────────────────────────────────────────────────────┘ │  │
│  │                                                                   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Investment Flow

```solidity
/**
 * @title InvestmentManager
 * @notice Handles investor subscriptions and redemptions
 */
contract InvestmentManager {
    
    // Compliance registry
    IComplianceRegistry public complianceRegistry;
    
    // Subscription state
    mapping(address => mapping(address => Subscription)) public subscriptions;
    // investor => deal => subscription
    
    struct Subscription {
        uint256 amount;
        uint256 timestamp;
        SubscriptionStatus status;
        bytes32 kycHash;
    }
    
    enum SubscriptionStatus {
        PENDING,
        APPROVED,
        FUNDED,
        COMPLETED,
        REJECTED
    }
    
    /**
     * @notice Subscribe to a deal tranche
     * @dev Requires KYC/AML verification
     */
    function subscribe(
        address deal,
        uint256 trancheIndex,
        uint256 amount
    ) external {
        // Check investor compliance
        require(complianceRegistry.isVerified(msg.sender), "KYC not complete");
        require(complianceRegistry.isAccredited(msg.sender), "Not accredited");
        require(!complianceRegistry.isSanctioned(msg.sender), "Sanctioned address");
        
        // Check deal is open for subscription
        IDeal dealContract = IDeal(deal);
        require(dealContract.subscriptionOpen(), "Subscription closed");
        
        // Check minimum investment
        require(amount >= dealContract.minimumInvestment(), "Below minimum");
        
        // Create subscription
        subscriptions[msg.sender][deal] = Subscription({
            amount: amount,
            timestamp: block.timestamp,
            status: SubscriptionStatus.PENDING,
            kycHash: complianceRegistry.getKYCHash(msg.sender)
        });
        
        emit SubscriptionCreated(msg.sender, deal, trancheIndex, amount);
    }
    
    /**
     * @notice Fund subscription with stablecoin payment
     */
    function fundSubscription(
        address deal,
        address paymentToken
    ) external {
        Subscription storage sub = subscriptions[msg.sender][deal];
        require(sub.status == SubscriptionStatus.APPROVED, "Not approved");
        
        // Accept payment
        IERC20(paymentToken).safeTransferFrom(msg.sender, address(this), sub.amount);
        
        sub.status = SubscriptionStatus.FUNDED;
        
        emit SubscriptionFunded(msg.sender, deal, sub.amount);
    }
    
    /**
     * @notice Complete subscription by minting tokens
     * @dev Called by arranger after primary close
     */
    function completeSubscription(
        address investor,
        address deal,
        uint256 trancheIndex
    ) external onlyRole(ARRANGER_ROLE) {
        Subscription storage sub = subscriptions[investor][deal];
        require(sub.status == SubscriptionStatus.FUNDED, "Not funded");
        
        // Mint tranche tokens
        address tranche = IDeal(deal).tranches(trancheIndex);
        uint256 tokens = _calculateTokens(sub.amount, tranche);
        
        ITrancheToken(tranche).mint(investor, tokens);
        
        // Transfer payment to deal treasury
        IDeal(deal).treasury().deposit(sub.amount);
        
        sub.status = SubscriptionStatus.COMPLETED;
        
        emit SubscriptionCompleted(investor, deal, trancheIndex, tokens);
    }
    
    event SubscriptionCreated(address indexed investor, address indexed deal, uint256 tranche, uint256 amount);
    event SubscriptionFunded(address indexed investor, address indexed deal, uint256 amount);
    event SubscriptionCompleted(address indexed investor, address indexed deal, uint256 tranche, uint256 tokens);
}
```

---

## Auditor Integration

### Auditor Role Overview

Auditors play a critical role in the RMBS ecosystem, providing independent verification of:
- **Financial Accuracy**: Waterfall calculations, payment distributions, fee computations
- **Data Integrity**: Servicer-reported performance data, loan tape accuracy
- **Compliance**: Regulatory adherence, deal document alignment
- **Security**: Smart contract behavior, access control enforcement

### Auditor Portal Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     AUDITOR PORTAL                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  DASHBOARD                                                            │  │
│  │  ┌────────────────────────────────────────────────────────────────┐ │  │
│  │  │  Active Engagements: 5                                         │ │  │
│  │  │  Pending Reviews: 12 deals                                     │ │  │
│  │  │  Open Findings: 3 (2 Medium, 1 Low)                            │ │  │
│  │  │  Attestations Due: 2 (within 7 days)                           │ │  │
│  │  └────────────────────────────────────────────────────────────────┘ │  │
│  │                                                                       │  │
│  │  DEAL AUDIT WORKSPACE (Selected: DEAL_2024_001)                      │  │
│  │  ┌────────────────────────────────────────────────────────────────┐ │  │
│  │  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐ │ │  │
│  │  │  │ Waterfall        │  │ Performance      │  │ Compliance   │ │ │  │
│  │  │  │ Verification     │  │ Data Audit       │  │ Checklist    │ │ │  │
│  │  │  │ ──────────────   │  │ ──────────────   │  │ ──────────   │ │ │  │
│  │  │  │ ✓ Period 1-10    │  │ ✓ CPR/CDR valid  │  │ ✓ KYC/AML    │ │ │  │
│  │  │  │ ✓ Period 11-20   │  │ ✓ DQ buckets     │  │ ✓ Reg D      │ │ │  │
│  │  │  │ ⏳ Period 21-24  │  │ ⚠ Loss severity  │  │ ✓ Sanctions  │ │ │  │
│  │  │  │                  │  │   (review needed)│  │ ⏳ 144A      │ │ │  │
│  │  │  └──────────────────┘  └──────────────────┘  └──────────────┘ │ │  │
│  │  └────────────────────────────────────────────────────────────────┘ │  │
│  │                                                                       │  │
│  │  AUDIT TRAIL EXPLORER                                                │  │
│  │  ┌────────────────────────────────────────────────────────────────┐ │  │
│  │  │  Filter: [All Events ▼] [Period 1-24 ▼] [All Actors ▼]        │ │  │
│  │  │  ────────────────────────────────────────────────────────────  │ │  │
│  │  │  2026-01-15 14:32:01 │ WaterfallExecuted │ Trustee             │ │  │
│  │  │  2026-01-15 14:31:45 │ PerformanceData   │ Servicer ABC        │ │  │
│  │  │  2026-01-15 14:30:22 │ ZKProofVerified   │ Oracle Node 3       │ │  │
│  │  │  2026-01-01 09:00:00 │ YieldClaimed      │ Investor 0x7a2...   │ │  │
│  │  │  2025-12-15 14:35:12 │ WaterfallExecuted │ Trustee             │ │  │
│  │  │  ...                                                           │ │  │
│  │  │  [Export CSV] [Export JSON] [Generate Report]                  │ │  │
│  │  └────────────────────────────────────────────────────────────────┘ │  │
│  │                                                                       │  │
│  │  VERIFICATION TOOLS                                                  │  │
│  │  ┌────────────────────────────────────────────────────────────────┐ │  │
│  │  │  [Recalculate Waterfall]  [Verify ZK Proofs]  [Reconcile Data] │ │  │
│  │  │  [Compare to Deal Docs]   [Stratification]    [Trend Analysis] │ │  │
│  │  │  [Challenge Data]         [Request TEE Access] [Export Workpapers]│ │  │
│  │  └────────────────────────────────────────────────────────────────┘ │  │
│  │                                                                       │  │
│  │  FINDINGS & ATTESTATIONS                                             │  │
│  │  ┌────────────────────────────────────────────────────────────────┐ │  │
│  │  │  [Create Finding]  [Draft Attestation]  [Sign & Publish]       │ │  │
│  │  │  [View Historical Findings]  [Dispute Resolution]              │ │  │
│  │  └────────────────────────────────────────────────────────────────┘ │  │
│  │                                                                       │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Audit Trail Smart Contract

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/AccessControl.sol";

/**
 * @title AuditTrailRegistry
 * @notice Immutable on-chain audit trail for all deal activities
 * 
 * Features:
 * - Tamper-proof event logging
 * - Cryptographic linkage (hash chain)
 * - Multi-deal indexing
 * - Auditor attestation recording
 * - Finding and dispute tracking
 */
contract AuditTrailRegistry is AccessControl {
    
    bytes32 public constant AUDITOR_ROLE = keccak256("AUDITOR");
    bytes32 public constant RECORDER_ROLE = keccak256("RECORDER"); // Contracts that can log
    
    // Event types
    enum EventType {
        DEAL_CREATED,
        TOKENS_MINTED,
        WATERFALL_EXECUTED,
        PERFORMANCE_SUBMITTED,
        YIELD_DISTRIBUTED,
        PRINCIPAL_PAID,
        LOSS_ALLOCATED,
        TRIGGER_BREACHED,
        TRIGGER_CURED,
        COMPLIANCE_CHECK,
        TRANSFER_EXECUTED,
        ACCOUNT_FROZEN,
        AUDITOR_ATTESTATION,
        FINDING_CREATED,
        DISPUTE_OPENED,
        DISPUTE_RESOLVED
    }
    
    // Audit event structure
    struct AuditEvent {
        uint256 eventId;
        address deal;
        EventType eventType;
        address actor;
        uint256 timestamp;
        bytes32 dataHash;      // Hash of event-specific data
        bytes32 previousHash;  // Link to previous event (hash chain)
        bytes signature;       // Actor's signature
    }
    
    // Storage
    mapping(uint256 => AuditEvent) public events;
    uint256 public eventCount;
    bytes32 public latestHash;
    
    // Index by deal
    mapping(address => uint256[]) public dealEvents;
    
    // Index by actor
    mapping(address => uint256[]) public actorEvents;
    
    // Index by event type
    mapping(EventType => uint256[]) public eventsByType;
    
    // Auditor attestations
    struct Attestation {
        address auditor;
        address deal;
        uint256 periodStart;
        uint256 periodEnd;
        bytes32 findingsHash;   // IPFS hash of detailed findings
        AttestationType attestationType;
        uint256 timestamp;
        bytes signature;
    }
    
    enum AttestationType {
        UNQUALIFIED,           // Clean opinion
        QUALIFIED,             // With exceptions
        ADVERSE,               // Material misstatement
        DISCLAIMER             // Unable to audit
    }
    
    mapping(bytes32 => Attestation) public attestations;
    mapping(address => bytes32[]) public dealAttestations;
    
    // Findings
    struct Finding {
        bytes32 findingId;
        address auditor;
        address deal;
        FindingSeverity severity;
        string title;
        bytes32 detailsHash;   // IPFS hash of detailed finding
        FindingStatus status;
        uint256 createdAt;
        uint256 resolvedAt;
        address resolver;
    }
    
    enum FindingSeverity {
        INFORMATIONAL,
        LOW,
        MEDIUM,
        HIGH,
        CRITICAL
    }
    
    enum FindingStatus {
        OPEN,
        ACKNOWLEDGED,
        IN_PROGRESS,
        RESOLVED,
        DISPUTED,
        CLOSED
    }
    
    mapping(bytes32 => Finding) public findings;
    mapping(address => bytes32[]) public dealFindings;
    
    // Events
    event AuditEventRecorded(
        uint256 indexed eventId,
        address indexed deal,
        EventType indexed eventType,
        address actor,
        bytes32 dataHash
    );
    
    event AttestationRecorded(
        bytes32 indexed attestationId,
        address indexed deal,
        address indexed auditor,
        AttestationType attestationType
    );
    
    event FindingCreated(
        bytes32 indexed findingId,
        address indexed deal,
        address indexed auditor,
        FindingSeverity severity
    );
    
    event FindingStatusChanged(
        bytes32 indexed findingId,
        FindingStatus oldStatus,
        FindingStatus newStatus
    );
    
    /**
     * @notice Record an audit event
     * @dev Only callable by authorized recorder contracts
     */
    function recordEvent(
        address deal,
        EventType eventType,
        address actor,
        bytes32 dataHash,
        bytes calldata signature
    ) external onlyRole(RECORDER_ROLE) returns (uint256) {
        eventCount++;
        
        AuditEvent storage evt = events[eventCount];
        evt.eventId = eventCount;
        evt.deal = deal;
        evt.eventType = eventType;
        evt.actor = actor;
        evt.timestamp = block.timestamp;
        evt.dataHash = dataHash;
        evt.previousHash = latestHash;
        evt.signature = signature;
        
        // Update hash chain
        latestHash = keccak256(abi.encode(
            eventCount, deal, eventType, actor, block.timestamp, dataHash, latestHash
        ));
        
        // Update indices
        dealEvents[deal].push(eventCount);
        actorEvents[actor].push(eventCount);
        eventsByType[eventType].push(eventCount);
        
        emit AuditEventRecorded(eventCount, deal, eventType, actor, dataHash);
        
        return eventCount;
    }
    
    /**
     * @notice Record auditor attestation
     * @dev Only callable by registered auditors
     */
    function recordAttestation(
        address deal,
        uint256 periodStart,
        uint256 periodEnd,
        bytes32 findingsHash,
        AttestationType attestationType,
        bytes calldata signature
    ) external onlyRole(AUDITOR_ROLE) returns (bytes32) {
        bytes32 attestationId = keccak256(abi.encode(
            msg.sender, deal, periodStart, periodEnd, block.timestamp
        ));
        
        attestations[attestationId] = Attestation({
            auditor: msg.sender,
            deal: deal,
            periodStart: periodStart,
            periodEnd: periodEnd,
            findingsHash: findingsHash,
            attestationType: attestationType,
            timestamp: block.timestamp,
            signature: signature
        });
        
        dealAttestations[deal].push(attestationId);
        
        // Record as audit event
        recordEvent(
            deal,
            EventType.AUDITOR_ATTESTATION,
            msg.sender,
            attestationId,
            signature
        );
        
        emit AttestationRecorded(attestationId, deal, msg.sender, attestationType);
        
        return attestationId;
    }
    
    /**
     * @notice Create an audit finding
     */
    function createFinding(
        address deal,
        FindingSeverity severity,
        string calldata title,
        bytes32 detailsHash
    ) external onlyRole(AUDITOR_ROLE) returns (bytes32) {
        bytes32 findingId = keccak256(abi.encode(
            msg.sender, deal, title, block.timestamp
        ));
        
        findings[findingId] = Finding({
            findingId: findingId,
            auditor: msg.sender,
            deal: deal,
            severity: severity,
            title: title,
            detailsHash: detailsHash,
            status: FindingStatus.OPEN,
            createdAt: block.timestamp,
            resolvedAt: 0,
            resolver: address(0)
        });
        
        dealFindings[deal].push(findingId);
        
        emit FindingCreated(findingId, deal, msg.sender, severity);
        
        return findingId;
    }
    
    /**
     * @notice Update finding status
     */
    function updateFindingStatus(
        bytes32 findingId,
        FindingStatus newStatus
    ) external {
        Finding storage finding = findings[findingId];
        require(finding.createdAt > 0, "Finding not found");
        
        // Authorization: auditor can update any status, deal admin can acknowledge/resolve
        require(
            hasRole(AUDITOR_ROLE, msg.sender) ||
            (hasRole(DEFAULT_ADMIN_ROLE, msg.sender) && 
             (newStatus == FindingStatus.ACKNOWLEDGED || 
              newStatus == FindingStatus.IN_PROGRESS ||
              newStatus == FindingStatus.RESOLVED)),
            "Not authorized"
        );
        
        FindingStatus oldStatus = finding.status;
        finding.status = newStatus;
        
        if (newStatus == FindingStatus.RESOLVED || newStatus == FindingStatus.CLOSED) {
            finding.resolvedAt = block.timestamp;
            finding.resolver = msg.sender;
        }
        
        emit FindingStatusChanged(findingId, oldStatus, newStatus);
    }
    
    // ========== QUERY FUNCTIONS ==========
    
    /**
     * @notice Get all events for a deal
     */
    function getDealEvents(address deal) external view returns (uint256[] memory) {
        return dealEvents[deal];
    }
    
    /**
     * @notice Get events for a deal within a time range
     */
    function getDealEventsInRange(
        address deal,
        uint256 startTime,
        uint256 endTime
    ) external view returns (uint256[] memory) {
        uint256[] memory allEvents = dealEvents[deal];
        uint256 count = 0;
        
        // Count matching events
        for (uint256 i = 0; i < allEvents.length; i++) {
            AuditEvent memory evt = events[allEvents[i]];
            if (evt.timestamp >= startTime && evt.timestamp <= endTime) {
                count++;
            }
        }
        
        // Populate result
        uint256[] memory result = new uint256[](count);
        uint256 idx = 0;
        for (uint256 i = 0; i < allEvents.length; i++) {
            AuditEvent memory evt = events[allEvents[i]];
            if (evt.timestamp >= startTime && evt.timestamp <= endTime) {
                result[idx++] = allEvents[i];
            }
        }
        
        return result;
    }
    
    /**
     * @notice Verify hash chain integrity
     */
    function verifyHashChain(uint256 fromEvent, uint256 toEvent) external view returns (bool) {
        require(fromEvent > 0 && toEvent >= fromEvent && toEvent <= eventCount, "Invalid range");
        
        bytes32 computedHash = events[fromEvent].previousHash;
        
        for (uint256 i = fromEvent; i <= toEvent; i++) {
            AuditEvent memory evt = events[i];
            bytes32 expectedHash = keccak256(abi.encode(
                evt.eventId, evt.deal, evt.eventType, evt.actor, 
                evt.timestamp, evt.dataHash, computedHash
            ));
            
            if (i < toEvent && expectedHash != events[i + 1].previousHash) {
                return false;
            }
            computedHash = expectedHash;
        }
        
        return computedHash == latestHash || toEvent < eventCount;
    }
    
    /**
     * @notice Get attestation history for a deal
     */
    function getDealAttestations(address deal) external view returns (bytes32[] memory) {
        return dealAttestations[deal];
    }
    
    /**
     * @notice Get open findings for a deal
     */
    function getOpenFindings(address deal) external view returns (bytes32[] memory) {
        bytes32[] memory allFindings = dealFindings[deal];
        uint256 count = 0;
        
        for (uint256 i = 0; i < allFindings.length; i++) {
            if (findings[allFindings[i]].status == FindingStatus.OPEN ||
                findings[allFindings[i]].status == FindingStatus.ACKNOWLEDGED ||
                findings[allFindings[i]].status == FindingStatus.IN_PROGRESS) {
                count++;
            }
        }
        
        bytes32[] memory result = new bytes32[](count);
        uint256 idx = 0;
        for (uint256 i = 0; i < allFindings.length; i++) {
            Finding memory f = findings[allFindings[i]];
            if (f.status == FindingStatus.OPEN ||
                f.status == FindingStatus.ACKNOWLEDGED ||
                f.status == FindingStatus.IN_PROGRESS) {
                result[idx++] = allFindings[i];
            }
        }
        
        return result;
    }
}
```

### Auditor Access Control Contract

```solidity
/**
 * @title AuditorAccessControl
 * @notice Manages time-limited, scoped access for auditors
 * 
 * Security features:
 * - Time-bound access grants
 * - Scope-limited permissions
 * - Multi-party approval for sensitive data
 * - Access logging
 */
contract AuditorAccessControl is AccessControl {
    
    bytes32 public constant ACCESS_ADMIN_ROLE = keccak256("ACCESS_ADMIN");
    
    // Access grant structure
    struct AccessGrant {
        address auditor;
        address deal;
        AccessScope scope;
        uint256 grantedAt;
        uint256 expiresAt;
        address grantedBy;
        bytes32 purposeHash;     // Hash of audit engagement letter
        bool revoked;
    }
    
    enum AccessScope {
        PERFORMANCE_ONLY,       // Pool metrics, waterfall results
        LOAN_TAPE_ANONYMIZED,   // Loan data without PII
        LOAN_TAPE_FULL,         // Full loan tape (requires TEE)
        FULL_DEAL_ACCESS,       // Everything including legal docs
        REGULATORY_SUBPOENA     // Unrestricted (regulator only)
    }
    
    // Storage
    mapping(bytes32 => AccessGrant) public accessGrants;
    mapping(address => bytes32[]) public auditorGrants;
    mapping(address => bytes32[]) public dealGrants;
    
    // Access log
    struct AccessLog {
        bytes32 grantId;
        address auditor;
        address deal;
        string dataType;
        uint256 timestamp;
        bytes32 queryHash;
    }
    
    AccessLog[] public accessLogs;
    mapping(address => uint256[]) public auditorAccessLogs;
    
    // Events
    event AccessGranted(
        bytes32 indexed grantId,
        address indexed auditor,
        address indexed deal,
        AccessScope scope,
        uint256 expiresAt
    );
    
    event AccessRevoked(
        bytes32 indexed grantId,
        address indexed revokedBy,
        string reason
    );
    
    event DataAccessed(
        bytes32 indexed grantId,
        address indexed auditor,
        string dataType,
        bytes32 queryHash
    );
    
    /**
     * @notice Grant audit access to a deal
     * @dev Requires ACCESS_ADMIN_ROLE
     */
    function grantAccess(
        address auditor,
        address deal,
        AccessScope scope,
        uint256 duration,
        bytes32 purposeHash
    ) external onlyRole(ACCESS_ADMIN_ROLE) returns (bytes32) {
        require(duration <= 365 days, "Max 1 year access");
        require(scope != AccessScope.REGULATORY_SUBPOENA, "Use grantRegulatoryAccess");
        
        bytes32 grantId = keccak256(abi.encode(
            auditor, deal, scope, block.timestamp
        ));
        
        accessGrants[grantId] = AccessGrant({
            auditor: auditor,
            deal: deal,
            scope: scope,
            grantedAt: block.timestamp,
            expiresAt: block.timestamp + duration,
            grantedBy: msg.sender,
            purposeHash: purposeHash,
            revoked: false
        });
        
        auditorGrants[auditor].push(grantId);
        dealGrants[deal].push(grantId);
        
        emit AccessGranted(grantId, auditor, deal, scope, block.timestamp + duration);
        
        return grantId;
    }
    
    /**
     * @notice Grant regulatory/subpoena access
     * @dev Requires multi-sig or regulator role
     */
    function grantRegulatoryAccess(
        address regulator,
        address deal,
        bytes32 subpoenaHash,
        bytes[] calldata approvalSignatures
    ) external returns (bytes32) {
        // Verify multi-sig approval (3-of-5 trustees) or regulator role
        require(
            hasRole(keccak256("REGULATOR"), msg.sender) ||
            _verifyMultiSig(approvalSignatures, 3),
            "Insufficient approval"
        );
        
        bytes32 grantId = keccak256(abi.encode(
            regulator, deal, AccessScope.REGULATORY_SUBPOENA, block.timestamp
        ));
        
        accessGrants[grantId] = AccessGrant({
            auditor: regulator,
            deal: deal,
            scope: AccessScope.REGULATORY_SUBPOENA,
            grantedAt: block.timestamp,
            expiresAt: block.timestamp + 90 days, // 90-day default for regulatory
            grantedBy: msg.sender,
            purposeHash: subpoenaHash,
            revoked: false
        });
        
        auditorGrants[regulator].push(grantId);
        dealGrants[deal].push(grantId);
        
        emit AccessGranted(grantId, regulator, deal, AccessScope.REGULATORY_SUBPOENA, block.timestamp + 90 days);
        
        return grantId;
    }
    
    /**
     * @notice Revoke access grant
     */
    function revokeAccess(bytes32 grantId, string calldata reason) external onlyRole(ACCESS_ADMIN_ROLE) {
        AccessGrant storage grant = accessGrants[grantId];
        require(grant.grantedAt > 0, "Grant not found");
        require(!grant.revoked, "Already revoked");
        
        grant.revoked = true;
        
        emit AccessRevoked(grantId, msg.sender, reason);
    }
    
    /**
     * @notice Check if auditor has valid access
     */
    function hasValidAccess(
        address auditor,
        address deal,
        AccessScope requiredScope
    ) external view returns (bool, bytes32) {
        bytes32[] memory grants = auditorGrants[auditor];
        
        for (uint256 i = 0; i < grants.length; i++) {
            AccessGrant memory grant = accessGrants[grants[i]];
            
            if (grant.deal == deal &&
                !grant.revoked &&
                block.timestamp <= grant.expiresAt &&
                uint8(grant.scope) >= uint8(requiredScope)) {
                return (true, grants[i]);
            }
        }
        
        return (false, bytes32(0));
    }
    
    /**
     * @notice Log data access (called by data providers)
     */
    function logAccess(
        bytes32 grantId,
        string calldata dataType,
        bytes32 queryHash
    ) external {
        AccessGrant memory grant = accessGrants[grantId];
        require(grant.grantedAt > 0 && !grant.revoked, "Invalid grant");
        require(block.timestamp <= grant.expiresAt, "Grant expired");
        
        accessLogs.push(AccessLog({
            grantId: grantId,
            auditor: grant.auditor,
            deal: grant.deal,
            dataType: dataType,
            timestamp: block.timestamp,
            queryHash: queryHash
        }));
        
        auditorAccessLogs[grant.auditor].push(accessLogs.length - 1);
        
        emit DataAccessed(grantId, grant.auditor, dataType, queryHash);
    }
    
    function _verifyMultiSig(bytes[] calldata signatures, uint8 threshold) internal view returns (bool) {
        // Multi-sig verification logic
        return signatures.length >= threshold;
    }
}
```

### ZK-Verified Audit Proofs

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     ZK-VERIFIED AUDIT PROOFS                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Auditors can verify computations without accessing raw loan data:          │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  WATERFALL VERIFICATION PROOF                                         │  │
│  │                                                                       │  │
│  │  Public Inputs:                          Private Inputs (TEE):        │  │
│  │  • Interest collected: $2,000,000        • Individual loan payments   │  │
│  │  • Principal collected: $5,000,000       • Loan balances             │  │
│  │  • Tranche A interest paid: $1,200,000   • Delinquency status        │  │
│  │  • Tranche A principal: $3,000,000       • Prepayment amounts        │  │
│  │  • Tranche B interest paid: $500,000                                 │  │
│  │  • Reserve fund balance: $300,000        ZK Proof:                   │  │
│  │  • Waterfall rules hash                  • Collections match         │  │
│  │                                          • Waterfall correctly applied│  │
│  │  Auditor Verification:                   • No funds misallocated     │  │
│  │  ✓ Verify ZK proof on-chain                                          │  │
│  │  ✓ Compare to expected waterfall rules                               │  │
│  │  ✓ Reconcile to tranche token balances                               │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  LOAN TAPE STRATIFICATION PROOF                                       │  │
│  │                                                                       │  │
│  │  Auditor Request:                        ZK Circuit Computes:         │  │
│  │  "Show me FICO distribution without      • Count per FICO bucket     │  │
│  │   revealing individual scores"           • Balance per bucket        │  │
│  │                                          • % of pool per bucket      │  │
│  │  Public Output:                                                       │  │
│  │  ┌──────────────────────────────────────────────────────────────┐   │  │
│  │  │  FICO Range   │  Count  │  Balance     │  % of Pool           │   │  │
│  │  │  ≥760         │   250   │  $112.5M     │  25.0%               │   │  │
│  │  │  720-759      │   300   │  $135.0M     │  30.0%               │   │  │
│  │  │  680-719      │   275   │  $123.75M    │  27.5%               │   │  │
│  │  │  640-679      │   125   │  $56.25M     │  12.5%               │   │  │
│  │  │  <640         │    50   │  $22.5M      │   5.0%               │   │  │
│  │  │  ───────────────────────────────────────────────────────────  │   │  │
│  │  │  Total        │  1000   │  $450.0M     │ 100.0%               │   │  │
│  │  └──────────────────────────────────────────────────────────────┘   │  │
│  │                                                                       │  │
│  │  ZK Proof verifies: Sum equals total, no individual data leaked      │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  COMPLIANCE ATTESTATION PROOF                                         │  │
│  │                                                                       │  │
│  │  Statement: "All token holders passed KYC and are accredited"        │  │
│  │                                                                       │  │
│  │  ZK Circuit Checks:                                                   │  │
│  │  • For each holder: ComplianceRegistry.isVerified(holder) == true    │  │
│  │  • For each US holder: ComplianceRegistry.isAccredited(holder) == true│  │
│  │  • No holder on sanctions list                                        │  │
│  │                                                                       │  │
│  │  Output: Boolean + ZK Proof (no holder addresses revealed)           │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Auditor Report Generation

```typescript
// Auditor Report Generator (Backend)
interface AuditReport {
  reportId: string;
  dealId: string;
  auditor: AuditorInfo;
  period: { start: Date; end: Date };
  scope: AuditScope;
  sections: ReportSection[];
  findings: AuditFinding[];
  attestation: Attestation;
  signatures: DigitalSignature[];
  attachments: Attachment[];
}

interface ReportSection {
  title: string;
  content: string;
  verificationMethod: 'ZK_PROOF' | 'TEE_ATTESTATION' | 'ON_CHAIN_QUERY' | 'MANUAL_REVIEW';
  evidenceHashes: string[];
  conclusion: 'VERIFIED' | 'EXCEPTION_NOTED' | 'UNABLE_TO_VERIFY';
}

// Standard Report Sections for RMBS Audit
const STANDARD_SECTIONS = [
  {
    title: "1. Waterfall Calculation Verification",
    checks: [
      "Interest payments match servicer remittance",
      "Principal allocation follows deal documents",
      "Fee calculations are accurate",
      "Reserve fund movements are correct",
      "Trigger tests accurately computed"
    ]
  },
  {
    title: "2. Performance Data Integrity",
    checks: [
      "CPR/CDR calculations are correct",
      "Delinquency buckets accurately reported",
      "Loss severity properly calculated",
      "Prepayment vectors are reasonable",
      "Data reconciles to servicer reports"
    ]
  },
  {
    title: "3. Compliance Verification",
    checks: [
      "All holders passed KYC/AML",
      "Accreditation requirements met",
      "Transfer restrictions enforced",
      "Sanctions screening current",
      "Regulatory filings up to date"
    ]
  },
  {
    title: "4. Smart Contract Review",
    checks: [
      "Deployed code matches audited version",
      "Access controls properly configured",
      "No unauthorized upgrades",
      "Oracle data feeds functioning",
      "Emergency mechanisms operational"
    ]
  },
  {
    title: "5. Token Accounting",
    checks: [
      "Token balances match investor records",
      "Factor calculations are accurate",
      "Yield distributions reconcile",
      "Burn events match principal payments",
      "Transfer logs are complete"
    ]
  }
];

// Report generation function
async function generateAuditReport(
  dealId: string,
  auditorGrant: AccessGrant,
  auditProcedures: AuditProcedure[]
): Promise<AuditReport> {
  const report: AuditReport = {
    reportId: generateReportId(),
    dealId,
    auditor: await getAuditorInfo(auditorGrant.auditor),
    period: {
      start: new Date(auditorGrant.grantedAt * 1000),
      end: new Date()
    },
    scope: auditorGrant.scope,
    sections: [],
    findings: [],
    attestation: null,
    signatures: [],
    attachments: []
  };
  
  // Execute each audit procedure
  for (const procedure of auditProcedures) {
    const result = await executeProcedure(procedure, dealId);
    report.sections.push(result.section);
    if (result.findings.length > 0) {
      report.findings.push(...result.findings);
    }
    report.attachments.push(...result.evidence);
  }
  
  // Generate attestation based on findings
  report.attestation = generateAttestation(report.findings);
  
  // Sign report
  report.signatures = await collectSignatures(report, auditorGrant.auditor);
  
  // Store report hash on-chain
  await recordReportOnChain(report);
  
  return report;
}
```

### Dispute Resolution Mechanism

```solidity
/**
 * @title DisputeResolver
 * @notice Handles disputes between auditors, servicers, and other parties
 */
contract DisputeResolver is AccessControl {
    
    struct Dispute {
        bytes32 disputeId;
        address deal;
        address initiator;
        address respondent;
        DisputeType disputeType;
        bytes32 evidenceHash;
        DisputeStatus status;
        uint256 createdAt;
        uint256 deadline;
        address[] arbitrators;
        mapping(address => Vote) votes;
        bytes32 resolution;
    }
    
    enum DisputeType {
        DATA_ACCURACY,          // Servicer data challenged
        WATERFALL_CALCULATION,  // Waterfall execution challenged
        COMPLIANCE_VIOLATION,   // Compliance breach alleged
        ACCESS_DENIAL,          // Auditor access improperly denied
        FINDING_CONTESTED       // Audit finding contested
    }
    
    enum DisputeStatus {
        OPENED,
        EVIDENCE_SUBMITTED,
        ARBITRATION,
        RESOLVED,
        APPEALED
    }
    
    struct Vote {
        bool hasVoted;
        bool inFavorOfInitiator;
        bytes32 reasonHash;
    }
    
    mapping(bytes32 => Dispute) public disputes;
    
    // Escalation thresholds
    uint256 public constant EVIDENCE_PERIOD = 7 days;
    uint256 public constant ARBITRATION_PERIOD = 14 days;
    uint256 public constant APPEAL_PERIOD = 7 days;
    
    event DisputeOpened(
        bytes32 indexed disputeId,
        address indexed deal,
        address initiator,
        DisputeType disputeType
    );
    
    event DisputeResolved(
        bytes32 indexed disputeId,
        bool inFavorOfInitiator,
        bytes32 resolutionHash
    );
    
    /**
     * @notice Open a dispute
     */
    function openDispute(
        address deal,
        address respondent,
        DisputeType disputeType,
        bytes32 evidenceHash
    ) external returns (bytes32) {
        // Verify initiator has standing (auditor, investor, etc.)
        require(
            hasRole(keccak256("AUDITOR"), msg.sender) ||
            hasRole(keccak256("INVESTOR"), msg.sender) ||
            hasRole(keccak256("TRUSTEE"), msg.sender),
            "No standing to dispute"
        );
        
        bytes32 disputeId = keccak256(abi.encode(
            deal, msg.sender, respondent, disputeType, block.timestamp
        ));
        
        Dispute storage d = disputes[disputeId];
        d.disputeId = disputeId;
        d.deal = deal;
        d.initiator = msg.sender;
        d.respondent = respondent;
        d.disputeType = disputeType;
        d.evidenceHash = evidenceHash;
        d.status = DisputeStatus.OPENED;
        d.createdAt = block.timestamp;
        d.deadline = block.timestamp + EVIDENCE_PERIOD;
        
        // Assign arbitrators (3 from pool)
        d.arbitrators = _selectArbitrators(disputeType);
        
        emit DisputeOpened(disputeId, deal, msg.sender, disputeType);
        
        return disputeId;
    }
    
    /**
     * @notice Submit response/counter-evidence
     */
    function submitResponse(
        bytes32 disputeId,
        bytes32 responseEvidenceHash
    ) external {
        Dispute storage d = disputes[disputeId];
        require(msg.sender == d.respondent, "Not respondent");
        require(d.status == DisputeStatus.OPENED, "Wrong status");
        require(block.timestamp <= d.deadline, "Evidence period ended");
        
        d.status = DisputeStatus.EVIDENCE_SUBMITTED;
        d.deadline = block.timestamp + ARBITRATION_PERIOD;
        
        // Store response evidence hash (combined with original)
        d.evidenceHash = keccak256(abi.encode(d.evidenceHash, responseEvidenceHash));
    }
    
    /**
     * @notice Cast arbitrator vote
     */
    function castVote(
        bytes32 disputeId,
        bool inFavorOfInitiator,
        bytes32 reasonHash
    ) external {
        Dispute storage d = disputes[disputeId];
        require(_isArbitrator(d, msg.sender), "Not arbitrator");
        require(d.status == DisputeStatus.EVIDENCE_SUBMITTED || 
                d.status == DisputeStatus.ARBITRATION, "Wrong status");
        require(!d.votes[msg.sender].hasVoted, "Already voted");
        
        d.status = DisputeStatus.ARBITRATION;
        d.votes[msg.sender] = Vote({
            hasVoted: true,
            inFavorOfInitiator: inFavorOfInitiator,
            reasonHash: reasonHash
        });
        
        // Check if we have majority
        uint256 votesFor = 0;
        uint256 votesAgainst = 0;
        for (uint256 i = 0; i < d.arbitrators.length; i++) {
            Vote memory v = d.votes[d.arbitrators[i]];
            if (v.hasVoted) {
                if (v.inFavorOfInitiator) votesFor++;
                else votesAgainst++;
            }
        }
        
        // Majority reached (2 of 3)
        if (votesFor >= 2 || votesAgainst >= 2) {
            _resolveDispute(disputeId, votesFor >= 2);
        }
    }
    
    function _resolveDispute(bytes32 disputeId, bool inFavorOfInitiator) internal {
        Dispute storage d = disputes[disputeId];
        d.status = DisputeStatus.RESOLVED;
        d.resolution = keccak256(abi.encode(inFavorOfInitiator, block.timestamp));
        d.deadline = block.timestamp + APPEAL_PERIOD;
        
        // Execute resolution actions
        if (inFavorOfInitiator) {
            if (d.disputeType == DisputeType.DATA_ACCURACY) {
                // Mark servicer data as disputed, require resubmission
                IPerformanceOracle(oracle).markDisputed(d.deal, disputeId);
            }
        }
        
        emit DisputeResolved(disputeId, inFavorOfInitiator, d.resolution);
    }
    
    function _selectArbitrators(DisputeType) internal view returns (address[] memory) {
        // Select from qualified arbitrator pool
        address[] memory selected = new address[](3);
        // ... arbitrator selection logic
        return selected;
    }
    
    function _isArbitrator(Dispute storage d, address account) internal view returns (bool) {
        for (uint256 i = 0; i < d.arbitrators.length; i++) {
            if (d.arbitrators[i] == account) return true;
        }
        return false;
    }
}
```

### Auditor Certification & Registry

```solidity
/**
 * @title AuditorRegistry
 * @notice Maintains registry of certified auditors
 */
contract AuditorRegistry is AccessControl {
    
    struct AuditorProfile {
        address auditorAddress;
        string name;
        string firm;
        AuditorType auditorType;
        bytes32[] certifications;     // Hash of certification documents
        uint256 registeredAt;
        uint256 lastActivityAt;
        bool isActive;
        uint256 reputationScore;      // 0-1000
        uint256 completedAudits;
        uint256 disputesLost;
    }
    
    enum AuditorType {
        FINANCIAL_AUDITOR,
        INTERNAL_AUDITOR,
        RATING_AGENCY,
        REGULATORY_EXAMINER,
        FORENSIC_AUDITOR,
        SMART_CONTRACT_AUDITOR
    }
    
    mapping(address => AuditorProfile) public auditors;
    address[] public registeredAuditors;
    
    // Certification requirements by type
    mapping(AuditorType => bytes32[]) public requiredCertifications;
    
    event AuditorRegistered(address indexed auditor, AuditorType auditorType, string firm);
    event AuditorSuspended(address indexed auditor, string reason);
    event ReputationUpdated(address indexed auditor, uint256 oldScore, uint256 newScore);
    
    /**
     * @notice Register a new auditor
     * @dev Requires verification of certifications
     */
    function registerAuditor(
        address auditorAddress,
        string calldata name,
        string calldata firm,
        AuditorType auditorType,
        bytes32[] calldata certificationHashes,
        bytes[] calldata certificationProofs
    ) external onlyRole(DEFAULT_ADMIN_ROLE) {
        require(auditors[auditorAddress].registeredAt == 0, "Already registered");
        
        // Verify certifications
        bytes32[] memory required = requiredCertifications[auditorType];
        require(_verifyCertifications(required, certificationHashes, certificationProofs), 
                "Missing certifications");
        
        auditors[auditorAddress] = AuditorProfile({
            auditorAddress: auditorAddress,
            name: name,
            firm: firm,
            auditorType: auditorType,
            certifications: certificationHashes,
            registeredAt: block.timestamp,
            lastActivityAt: block.timestamp,
            isActive: true,
            reputationScore: 500,  // Start at midpoint
            completedAudits: 0,
            disputesLost: 0
        });
        
        registeredAuditors.push(auditorAddress);
        _grantRole(keccak256("AUDITOR"), auditorAddress);
        
        emit AuditorRegistered(auditorAddress, auditorType, firm);
    }
    
    /**
     * @notice Update auditor reputation based on completed audit
     */
    function recordAuditCompletion(
        address auditor,
        bool withFindings,
        bool findingsValidated
    ) external onlyRole(DEFAULT_ADMIN_ROLE) {
        AuditorProfile storage profile = auditors[auditor];
        require(profile.isActive, "Auditor not active");
        
        profile.completedAudits++;
        profile.lastActivityAt = block.timestamp;
        
        uint256 oldScore = profile.reputationScore;
        
        // Reputation adjustment
        if (findingsValidated) {
            // Findings were confirmed - boost reputation
            profile.reputationScore = min(1000, profile.reputationScore + 10);
        } else if (withFindings && !findingsValidated) {
            // Findings were disputed and lost
            profile.reputationScore = max(0, profile.reputationScore - 20);
            profile.disputesLost++;
        } else {
            // Clean audit, small boost
            profile.reputationScore = min(1000, profile.reputationScore + 2);
        }
        
        emit ReputationUpdated(auditor, oldScore, profile.reputationScore);
    }
    
    /**
     * @notice Suspend auditor for cause
     */
    function suspendAuditor(address auditor, string calldata reason) external onlyRole(DEFAULT_ADMIN_ROLE) {
        AuditorProfile storage profile = auditors[auditor];
        profile.isActive = false;
        _revokeRole(keccak256("AUDITOR"), auditor);
        
        emit AuditorSuspended(auditor, reason);
    }
    
    /**
     * @notice Get auditors by type with minimum reputation
     */
    function getQualifiedAuditors(
        AuditorType auditorType,
        uint256 minReputation
    ) external view returns (address[] memory) {
        uint256 count = 0;
        for (uint256 i = 0; i < registeredAuditors.length; i++) {
            AuditorProfile memory p = auditors[registeredAuditors[i]];
            if (p.isActive && p.auditorType == auditorType && p.reputationScore >= minReputation) {
                count++;
            }
        }
        
        address[] memory result = new address[](count);
        uint256 idx = 0;
        for (uint256 i = 0; i < registeredAuditors.length; i++) {
            AuditorProfile memory p = auditors[registeredAuditors[i]];
            if (p.isActive && p.auditorType == auditorType && p.reputationScore >= minReputation) {
                result[idx++] = registeredAuditors[i];
            }
        }
        
        return result;
    }
    
    function _verifyCertifications(
        bytes32[] memory required,
        bytes32[] calldata provided,
        bytes[] calldata proofs
    ) internal pure returns (bool) {
        // Certification verification logic
        return provided.length >= required.length && proofs.length == provided.length;
    }
    
    function min(uint256 a, uint256 b) internal pure returns (uint256) {
        return a < b ? a : b;
    }
    
    function max(uint256 a, uint256 b) internal pure returns (uint256) {
        return a > b ? a : b;
    }
}
```

---

## Compliance & Regulatory

### Compliance Framework

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     COMPLIANCE FRAMEWORK                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  REGULATORY REQUIREMENTS                                          │  │
│  │                                                                   │  │
│  │  US Securities Laws:                                              │  │
│  │  • Reg D (506b/506c) - Private placement exemption               │  │
│  │  • Reg S - Offshore offerings                                    │  │
│  │  • Rule 144A - QIB resales                                       │  │
│  │                                                                   │  │
│  │  AML/KYC:                                                         │  │
│  │  • Bank Secrecy Act compliance                                   │  │
│  │  • OFAC sanctions screening                                      │  │
│  │  • Beneficial ownership identification                           │  │
│  │                                                                   │  │
│  │  Data Privacy:                                                    │  │
│  │  • GLBA (Gramm-Leach-Bliley) for loan data                      │  │
│  │  • CCPA/GDPR for investor data                                  │  │
│  │                                                                   │  │
│  │  Securities Reporting:                                            │  │
│  │  • Form D filing                                                 │  │
│  │  • Blue Sky state filings                                        │  │
│  │  • Reg AB II (if SEC-registered)                                 │  │
│  │                                                                   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  ON-CHAIN COMPLIANCE ENFORCEMENT                                  │  │
│  │                                                                   │  │
│  │  Transfer Restrictions:                                           │  │
│  │  ┌────────────────────────────────────────────────────────────┐ │  │
│  │  │  canTransfer(from, to, amount) {                           │ │  │
│  │  │    // 1. KYC verification                                  │ │  │
│  │  │    require(complianceRegistry.isVerified(to));             │ │  │
│  │  │                                                            │ │  │
│  │  │    // 2. Accreditation (for US investors)                  │ │  │
│  │  │    if (isUSPerson(to)) {                                   │ │  │
│  │  │      require(complianceRegistry.isAccredited(to));         │ │  │
│  │  │    }                                                       │ │  │
│  │  │                                                            │ │  │
│  │  │    // 3. Sanctions check                                   │ │  │
│  │  │    require(!complianceRegistry.isSanctioned(from));        │ │  │
│  │  │    require(!complianceRegistry.isSanctioned(to));          │ │  │
│  │  │                                                            │ │  │
│  │  │    // 4. Lock-up period (Reg D)                            │ │  │
│  │  │    require(block.timestamp > lockupEnd[from]);             │ │  │
│  │  │                                                            │ │  │
│  │  │    // 5. Maximum holder limit                              │ │  │
│  │  │    require(holderCount < MAX_HOLDERS);                     │ │  │
│  │  │                                                            │ │  │
│  │  │    return true;                                            │ │  │
│  │  │  }                                                         │ │  │
│  │  └────────────────────────────────────────────────────────────┘ │  │
│  │                                                                   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  COMPLIANCE REGISTRY (Off-Chain + On-Chain)                       │  │
│  │                                                                   │  │
│  │  Off-Chain (KYC Provider):                                        │  │
│  │  • Identity verification (document check, biometrics)            │  │
│  │  • Accreditation verification (net worth, income)                │  │
│  │  • Sanctions screening (OFAC, EU, UN lists)                      │  │
│  │  • Ongoing monitoring (transaction patterns)                     │  │
│  │                                                                   │  │
│  │  On-Chain (ComplianceRegistry.sol):                               │  │
│  │  • Verified addresses (hash of KYC ID)                           │  │
│  │  • Accreditation status (US/non-US)                              │  │
│  │  • Jurisdiction flags                                            │  │
│  │  • Lock-up expiry dates                                          │  │
│  │  • Blacklist (sanctioned addresses)                              │  │
│  │                                                                   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Compliance Registry Contract

```solidity
/**
 * @title ComplianceRegistry
 * @notice Maintains investor compliance status on-chain
 * 
 * Integrates with off-chain KYC providers (Chainalysis, Jumio, etc.)
 */
contract ComplianceRegistry is AccessControl {
    
    bytes32 public constant KYC_PROVIDER_ROLE = keccak256("KYC_PROVIDER");
    bytes32 public constant COMPLIANCE_OFFICER_ROLE = keccak256("COMPLIANCE_OFFICER");
    
    struct InvestorStatus {
        bool isVerified;
        bool isAccredited;
        bool isSanctioned;
        bytes2 jurisdiction; // ISO 3166-1 alpha-2
        uint256 kycExpiry;
        uint256 accreditationExpiry;
        bytes32 kycHash; // Hash of off-chain KYC record ID
        uint256 lockupExpiry;
    }
    
    mapping(address => InvestorStatus) public investors;
    
    // Jurisdiction-based restrictions
    mapping(bytes2 => bool) public blockedJurisdictions;
    
    /**
     * @notice Register investor KYC status
     * @dev Only callable by authorized KYC provider
     */
    function registerInvestor(
        address investor,
        bool verified,
        bool accredited,
        bytes2 jurisdiction,
        uint256 kycExpiry,
        uint256 accreditationExpiry,
        bytes32 kycHash
    ) external onlyRole(KYC_PROVIDER_ROLE) {
        investors[investor] = InvestorStatus({
            isVerified: verified,
            isAccredited: accredited,
            isSanctioned: false,
            jurisdiction: jurisdiction,
            kycExpiry: kycExpiry,
            accreditationExpiry: accreditationExpiry,
            kycHash: kycHash,
            lockupExpiry: 0
        });
        
        emit InvestorRegistered(investor, jurisdiction, kycHash);
    }
    
    /**
     * @notice Add address to sanctions list
     * @dev Called when sanctions match detected
     */
    function addToSanctionsList(
        address account,
        string calldata reason
    ) external onlyRole(COMPLIANCE_OFFICER_ROLE) {
        investors[account].isSanctioned = true;
        emit Sanctioned(account, reason);
    }
    
    /**
     * @notice Check if address can receive tokens
     */
    function canReceive(address account) external view returns (bool) {
        InvestorStatus memory status = investors[account];
        
        if (status.isSanctioned) return false;
        if (!status.isVerified) return false;
        if (status.kycExpiry < block.timestamp) return false;
        if (blockedJurisdictions[status.jurisdiction]) return false;
        
        return true;
    }
    
    /**
     * @notice Check if address can transfer tokens
     */
    function canTransfer(address account) external view returns (bool) {
        InvestorStatus memory status = investors[account];
        
        if (status.isSanctioned) return false;
        if (status.lockupExpiry > block.timestamp) return false;
        
        return true;
    }
    
    /**
     * @notice Check accreditation (for US securities law compliance)
     */
    function isAccredited(address account) external view returns (bool) {
        InvestorStatus memory status = investors[account];
        return status.isAccredited && status.accreditationExpiry > block.timestamp;
    }
    
    event InvestorRegistered(address indexed investor, bytes2 jurisdiction, bytes32 kycHash);
    event Sanctioned(address indexed account, string reason);
}
```

---

## Technical Implementation

### Technology Stack

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     TECHNOLOGY STACK                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  BLOCKCHAIN LAYER                                                       │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  • Chain: Ethereum L2 (Arbitrum or Optimism)                     │  │
│  │  • Smart Contracts: Solidity 0.8.20                              │  │
│  │  • Framework: Foundry (testing, deployment)                      │  │
│  │  • Upgradeability: OpenZeppelin UUPS                             │  │
│  │  • Token Standard: ERC-1400 (security tokens)                    │  │
│  │  • Oracle: Chainlink (external data) + Custom (servicer data)    │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  PRIVACY LAYER                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  • ZK Framework: Noir (Aztec) or Circom                          │  │
│  │  • ZK Proving: Groth16 or PLONK                                  │  │
│  │  • TEE: Intel SGX (Gramine) or AWS Nitro Enclaves               │  │
│  │  • Encryption: AES-256-GCM (data), ECIES (keys)                 │  │
│  │  • Key Management: AWS KMS / HashiCorp Vault                     │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  BACKEND LAYER                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  • Language: Python 3.11+ (RMBS Engine), Rust (ZK, TEE)         │  │
│  │  • API: FastAPI (REST), GraphQL (queries)                       │  │
│  │  • Database: PostgreSQL (structured), IPFS (documents)          │  │
│  │  • Message Queue: Redis + Bull (job processing)                 │  │
│  │  • Caching: Redis (hot data), S3 (cold storage)                 │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  FRONTEND LAYER                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  • Framework: Next.js 14 (React)                                 │  │
│  │  • Styling: Tailwind CSS + shadcn/ui                            │  │
│  │  • Web3: wagmi + viem (Ethereum), WalletConnect v2              │  │
│  │  • Charts: Recharts, D3.js                                      │  │
│  │  • State: TanStack Query (server state), Zustand (client)       │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  INFRASTRUCTURE                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  • Cloud: AWS (primary), with multi-cloud failover               │  │
│  │  • Containers: Docker, Kubernetes (EKS)                         │  │
│  │  • CI/CD: GitHub Actions                                         │  │
│  │  • Monitoring: Prometheus, Grafana, PagerDuty                   │  │
│  │  • Security: WAF, DDoS protection, HSM                          │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Integration Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     SYSTEM INTEGRATION                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  EXISTING RMBS ENGINE                      WEB3 EXTENSION                │
│  ┌─────────────────────┐                  ┌─────────────────────┐       │
│  │  engine/            │                  │  web3/              │       │
│  │  ├── waterfall.py   │◀────────────────▶│  ├── contracts/     │       │
│  │  ├── collateral.py  │     Adapter      │  │   ├── Tranche.sol│       │
│  │  ├── pricing.py     │                  │  │   ├── Waterfall. │       │
│  │  ├── market_risk.py │                  │  │   └── ...        │       │
│  │  └── ...            │                  │  ├── oracle/        │       │
│  └─────────────────────┘                  │  │   ├── tee/       │       │
│           │                               │  │   └── zk/        │       │
│           │                               │  ├── api/           │       │
│           │                               │  │   └── routes.py  │       │
│           ▼                               │  └── frontend/      │       │
│  ┌─────────────────────┐                  │      └── ...        │       │
│  │  ADAPTER LAYER      │                  └─────────────────────┘       │
│  │                     │                                                 │
│  │  WaterfallAdapter:  │                                                 │
│  │  • Converts Python  │                                                 │
│  │    cashflows to     │                                                 │
│  │    Solidity-format  │                                                 │
│  │    payloads         │                                                 │
│  │                     │                                                 │
│  │  OracleAdapter:     │                                                 │
│  │  • Runs RMBS engine │                                                 │
│  │    in TEE           │                                                 │
│  │  • Generates ZK     │                                                 │
│  │    proofs           │                                                 │
│  │  • Submits to       │                                                 │
│  │    on-chain oracle  │                                                 │
│  │                     │                                                 │
│  │  PricingAdapter:    │                                                 │
│  │  • Calls pricing    │                                                 │
│  │    engine           │                                                 │
│  │  • Returns OAS,     │                                                 │
│  │    duration, etc.   │                                                 │
│  │                     │                                                 │
│  └─────────────────────┘                                                 │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Risk Mitigation

### Risk Matrix

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Smart Contract Vulnerability** | Medium | Critical | Multiple audits, formal verification, bug bounty |
| **Oracle Manipulation** | Low | Critical | TEE attestation, ZK proofs, multi-source aggregation |
| **Key Compromise** | Low | Critical | HSM, Shamir splitting, threshold signatures |
| **Regulatory Action** | Medium | High | Compliance-first design, legal opinion, regulatory engagement |
| **Privacy Breach** | Low | High | TEE, encryption, minimal on-chain data |
| **Market Manipulation** | Medium | Medium | Transfer restrictions, circuit breakers, surveillance |
| **Servicer Fraud** | Low | High | ZK proofs, trustee verification, audit trail |
| **Platform Downtime** | Medium | Medium | Multi-region deployment, fallback mechanisms |

### Security Audit Requirements

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     AUDIT REQUIREMENTS                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  PHASE 1: Smart Contract Audit (Pre-Mainnet)                            │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  Auditor 1: Trail of Bits or OpenZeppelin                        │  │
│  │  Scope: All core contracts (TrancheToken, Waterfall, Treasury)   │  │
│  │  Duration: 4-6 weeks                                             │  │
│  │  Deliverables: Report, remediation verification                  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  PHASE 2: ZK Circuit Audit                                              │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  Auditor: Veridise or Zellic                                     │  │
│  │  Scope: All ZK circuits (PoolMetrics, Waterfall)                 │  │
│  │  Duration: 3-4 weeks                                             │  │
│  │  Deliverables: Soundness analysis, edge case review              │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  PHASE 3: TEE Security Review                                           │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  Auditor: NCC Group or Cure53                                    │  │
│  │  Scope: Enclave code, attestation flow, key management          │  │
│  │  Duration: 2-3 weeks                                             │  │
│  │  Deliverables: Security assessment, hardening recommendations    │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  PHASE 4: Penetration Testing (Pre-Production)                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  Auditor: Halborn or Slowmist                                    │  │
│  │  Scope: Full stack (frontend, API, blockchain, infrastructure)  │  │
│  │  Duration: 2-3 weeks                                             │  │
│  │  Deliverables: Vulnerability report, risk rating                 │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ONGOING: Bug Bounty Program                                            │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  Platform: Immunefi                                               │  │
│  │  Rewards: $1K - $100K based on severity                          │  │
│  │  Scope: All production contracts and infrastructure              │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Roadmap

### Implementation Phases

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     IMPLEMENTATION ROADMAP                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  PHASE 1: FOUNDATION (Weeks 1-8)                                        │
│  ─────────────────────────────────────────────────────────────────────  │
│  Week 1-2:  Smart Contract Development                                  │
│             • TrancheToken (ERC-1400)                                   │
│             • DealRegistry                                              │
│             • AccessControl                                             │
│                                                                          │
│  Week 3-4:  Waterfall Engine                                            │
│             • WaterfallEngine contract                                  │
│             • Treasury contract                                         │
│             • YieldDistributor                                          │
│                                                                          │
│  Week 5-6:  Oracle Infrastructure                                       │
│             • PerformanceOracle                                         │
│             • TEE enclave (basic)                                       │
│             • RMBS Engine adapter                                       │
│                                                                          │
│  Week 7-8:  Testing & Audit Prep                                        │
│             • Unit tests (100% coverage)                                │
│             • Integration tests                                         │
│             • Testnet deployment (Sepolia)                              │
│                                                                          │
│  ═══════════════════════════════════════════════════════════════════════│
│                                                                          │
│  PHASE 2: PRIVACY & SECURITY (Weeks 9-16)                               │
│  ─────────────────────────────────────────────────────────────────────  │
│  Week 9-10:  ZK Circuit Development                                     │
│              • PoolMetrics circuit                                      │
│              • Waterfall verification circuit                           │
│                                                                          │
│  Week 11-12: TEE Integration                                            │
│              • SGX/Nitro enclave production                             │
│              • Attestation flow                                         │
│              • Key management integration                               │
│                                                                          │
│  Week 13-14: Compliance Registry                                        │
│              • KYC provider integration                                 │
│              • Transfer restrictions                                    │
│              • Sanctions screening                                      │
│                                                                          │
│  Week 15-16: Security Audit (Phase 1)                                   │
│              • Smart contract audit                                     │
│              • Remediation                                              │
│                                                                          │
│  ═══════════════════════════════════════════════════════════════════════│
│                                                                          │
│  PHASE 3: USER EXPERIENCE (Weeks 17-26)                                 │
│  ─────────────────────────────────────────────────────────────────────  │
│  Week 17-18: Arranger Portal                                            │
│              • Deal creation wizard                                     │
│              • Tokenization flow                                        │
│              • Document management                                      │
│                                                                          │
│  Week 19-20: Investor Portal                                            │
│              • Dashboard                                                │
│              • Subscription flow                                        │
│              • Yield claiming                                           │
│                                                                          │
│  Week 21-22: Servicer Portal                                            │
│              • Data submission interface                                │
│              • Validation feedback                                      │
│              • Historical views                                         │
│                                                                          │
│  Week 23-24: Auditor Portal                                             │
│              • Audit trail explorer                                     │
│              • ZK-verified waterfall verification                       │
│              • Stratification report generator                          │
│              • Finding management & attestation workflow                │
│              • Dispute resolution interface                             │
│              • Access grant management                                  │
│                                                                          │
│  Week 25-26: Integration Testing                                        │
│              • End-to-end flows                                         │
│              • User acceptance testing                                  │
│              • Performance optimization                                 │
│              • Auditor workflow testing                                 │
│                                                                          │
│  ═══════════════════════════════════════════════════════════════════════│
│                                                                          │
│  PHASE 4: PRODUCTION LAUNCH (Weeks 27-36)                               │
│  ─────────────────────────────────────────────────────────────────────  │
│  Week 27-28: Security Audit (Phase 2-4)                                 │
│              • ZK circuit audit                                         │
│              • TEE security review                                      │
│              • Penetration testing                                      │
│              • Auditor contract review                                  │
│                                                                          │
│  Week 29-30: Mainnet Preparation                                        │
│              • L2 deployment (Arbitrum/Optimism)                        │
│              • Infrastructure hardening                                 │
│              • Monitoring setup                                         │
│              • Auditor registry deployment                              │
│                                                                          │
│  Week 31-32: Pilot Launch                                               │
│              • Limited deal (single issuer)                             │
│              • Whitelisted investors                                    │
│              • Registered auditors onboarded                            │
│              • Close monitoring                                         │
│                                                                          │
│  Week 33-34: Auditor Pilot                                              │
│              • First external audit conducted                           │
│              • Attestation workflow validated                           │
│              • Dispute resolution tested                                │
│              • Report generation verified                               │
│                                                                          │
│  Week 35-36: General Availability                                       │
│              • Public launch                                            │
│              • Bug bounty activation                                    │
│              • Auditor ecosystem launch                                 │
│              • Marketing/communications                                 │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Resource Requirements

| Role | Count | Duration | Notes |
|------|-------|----------|-------|
| Smart Contract Engineer | 2 | 36 weeks | Solidity, security, audit contracts |
| ZK Engineer | 1 | 20 weeks | Circom/Noir, audit verification circuits |
| Backend Engineer | 2 | 36 weeks | Python, Rust, TEE, audit trail |
| Frontend Engineer | 2 | 28 weeks | React, Web3, auditor portal |
| DevOps/Security | 1 | 36 weeks | AWS, K8s, security, access control |
| Product Manager | 1 | 36 weeks | Requirements, coordination |
| Compliance/Legal | 1 | 36 weeks | Regulatory, KYC, auditor certification |
| **Total** | **10** | | |

**Budget Estimate:** $1.8M - $3.0M (including auditor ecosystem development, certification framework, and additional security audits)

---

## Conclusion

This design provides a comprehensive framework for extending the RMBS Platform into a Web3-native tokenization platform with:

### Key Features

✅ **Security Token Issuance**: ERC-1400 compliant tokens with built-in compliance  
✅ **Privacy-Preserving Analytics**: ZK proofs + TEE for sensitive loan data  
✅ **Automated Waterfall**: On-chain execution with cryptographic verification  
✅ **Regulatory Compliance**: KYC/AML, transfer restrictions, audit trail  
✅ **Multi-Stakeholder Support**: Arranger, Investor, Servicer, Auditor portals  
✅ **Comprehensive Audit Infrastructure**: Immutable audit trail, ZK-verified attestations, dispute resolution  
✅ **Auditor Ecosystem**: Certified auditor registry, time-limited access grants, reputation tracking  

### Unique Value Proposition

| Traditional RMBS | Web3 RMBS Platform |
|------------------|--------------------|
| Monthly paper reports | Real-time on-chain transparency |
| Manual settlement (T+3) | Automated settlement (T+0) |
| Opaque waterfall execution | Verifiable, auditable waterfall |
| Limited secondary liquidity | 24/7 trading (compliant) |
| High administrative costs | Reduced operational overhead |
| Siloed data systems | Unified on-chain registry |
| Periodic external audits | Continuous, cryptographically-verified auditing |
| Paper-based audit trails | Immutable on-chain audit log with hash chain |
| Manual data reconciliation | ZK-proof verified data integrity |
| Subjective audit findings | Transparent, disputable findings with arbitration |

### Next Steps

1. **Stakeholder Review**: Present design to arrangers, investors, regulators
2. **Legal Opinion**: Obtain securities law analysis for token structure
3. **POC Development**: Build minimal viable product for single deal
4. **Pilot Program**: Launch with trusted partner institution

---

**Document Version:** 1.1  
**Last Updated:** January 29, 2026  
**Author:** RMBS Platform Development Team  
**Status:** Design Draft - Ready for Review  
**Timeline:** 36 weeks (9 months)  
**Stakeholders:** Arranger, Issuer, Investor, Servicer, Trustee, Auditor, Regulator

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| **ERC-1400** | Security token standard with transfer restrictions |
| **TEE** | Trusted Execution Environment (Intel SGX, AWS Nitro) |
| **ZK Proof** | Zero-Knowledge Proof (cryptographic privacy) |
| **Oracle** | Off-chain data provider |
| **KYC/AML** | Know Your Customer / Anti-Money Laundering |
| **OFAC** | Office of Foreign Assets Control (US sanctions) |
| **Reg D** | SEC exemption for private placements |
| **QIB** | Qualified Institutional Buyer |
| **HSM** | Hardware Security Module |
| **Attestation** | Formal auditor opinion on deal performance/compliance |
| **Audit Trail** | Immutable record of all platform activities |
| **Hash Chain** | Linked cryptographic hashes ensuring data integrity |
| **Finding** | Auditor-identified issue requiring resolution |
| **Dispute Resolution** | Arbitration process for contested findings |
| **Access Grant** | Time-limited permission for auditor data access |
| **Stratification** | Loan pool breakdown by characteristic (FICO, LTV, etc.) |
| **CPA** | Certified Public Accountant |
| **CIA** | Certified Internal Auditor |
| **CFE** | Certified Fraud Examiner |
| **Big 4** | Deloitte, PwC, EY, KPMG (major audit firms) |

## Appendix B: Reference Implementations

- **Centrifuge**: Real-world asset tokenization protocol
- **Maple Finance**: Institutional DeFi lending
- **Goldfinch**: Credit protocol with off-chain underwriting
- **Securitize**: Security token issuance platform
- **Polymath**: ERC-1400 token standard pioneer

## Appendix C: Regulatory Resources

- SEC Staff Guidance on Digital Assets
- CFTC Digital Asset Derivatives Guidance
- FinCEN Cryptocurrency AML Requirements
- OCC Crypto Custody Interpretive Letters
- European MiCA Regulation Framework

## Appendix D: Auditor Standards & Frameworks

### Financial Audit Standards
- **AICPA AU-C Sections**: Clarified auditing standards for financial statements
- **PCAOB Standards**: Public company audit oversight requirements
- **ISA (International Standards on Auditing)**: Global audit framework
- **SSAE 18 (SOC 1/2/3)**: Service organization control reports

### ABS/MBS Specific Guidelines
- **SEC Reg AB II**: Asset-backed securities disclosure requirements
- **FASB ASC 860**: Securitization accounting guidance
- **FAS 166/167**: Off-balance sheet consolidation rules
- **Basel III Securitization Framework**: Capital requirements

### Blockchain/Smart Contract Audit Standards
- **EIP-2535 (Diamond Standard)**: Upgradeable contract patterns
- **OpenZeppelin Audit Checklist**: Security best practices
- **Consensys Smart Contract Best Practices**: Development guidelines
- **Trail of Bits Building Secure Contracts**: Security patterns

### Data Privacy & Security
- **SOX Section 404**: Internal control over financial reporting
- **ISO 27001**: Information security management
- **NIST Cybersecurity Framework**: Risk management guidelines
- **GDPR Article 30**: Record-keeping requirements
