# RMBS Web3 Tokenization Platform

Investment-ready demo implementation following industry best practices.

## 🏗️ Project Structure

```
web3/
├── contracts/                    # Smart contracts (Foundry)
│   ├── src/
│   │   ├── interfaces/          # IERC1400, ITransferValidator
│   │   ├── tokens/              # RMBSTranche, TrancheFactory
│   │   ├── compliance/          # TransferValidator
│   │   ├── waterfall/           # WaterfallEngine
│   │   ├── oracle/              # ServicerOracle
│   │   └── access/              # RoleRegistry
│   ├── test/                    # Comprehensive test suite
│   └── script/                  # Deployment scripts
└── README.md
```

## ✅ Build Status

| Phase | Component | Status | LOC |
|-------|-----------|--------|-----|
| 1 | Smart Contracts | ✅ Complete | ~4,000 |
| 1 | Test Suite | ✅ Complete | ~2,000 |
| 2 | Deployment Scripts | ⏳ Pending | - |
| 2 | Core API Web3 Integration | ✅ Integrated | - |
| 3 | ZK Circuits | ⏳ Pending | - |

## 🚀 Quick Start

### Prerequisites

- [Foundry](https://book.getfoundry.sh/getting-started/installation)
- Node.js 18+ (for frontend/backend)

### Install Dependencies

```bash
cd contracts

# Install OpenZeppelin contracts
forge install OpenZeppelin/openzeppelin-contracts-upgradeable --no-commit
forge install OpenZeppelin/openzeppelin-contracts --no-commit
```

### Run Tests

```bash
cd contracts

# Run all tests
forge test

# Run with verbosity
forge test -vvv

# Run specific test file
forge test --match-path test/RMBSTranche.t.sol

# Run specific test
forge test --match-test test_snapshotPreventsGaming

# Run attack simulation tests
forge test --match-path test/AttackSimulation.t.sol -vvv

# Run with gas report
forge test --gas-report

# Run coverage
forge coverage
```

### Build Contracts

```bash
forge build
```

### Deploy (Testnet)

```bash
# Set environment variables
export ARBITRUM_SEPOLIA_RPC_URL="your-rpc-url"
export PRIVATE_KEY="your-private-key"

# Deploy (script pending)
forge script script/Deploy.s.sol --rpc-url $ARBITRUM_SEPOLIA_RPC_URL --broadcast
```

## 📊 Test Coverage

| Contract | Unit Tests | Integration | Attack Simulation |
|----------|------------|-------------|-------------------|
| RMBSTranche | ✅ 25+ tests | ✅ | ✅ MEV, Flash Loan, DoS |
| TransferValidator | ✅ 20+ tests | ✅ | ✅ Sanctions bypass |
| TrancheFactory | ⏳ | ✅ | - |
| WaterfallEngine | ⏳ | ✅ | - |
| ServicerOracle | ⏳ | ✅ | - |
| RoleRegistry | ⏳ | ✅ | - |

### Attack Vectors Tested

| Attack | Prevention | Test File |
|--------|------------|-----------|
| **Snapshot Gaming (MEV)** | Atomic ERC20Snapshot | AttackSimulation.t.sol |
| **Flash Loan Yield Theft** | Snapshot-based calculation | AttackSimulation.t.sol |
| **Sandwich Attack** | Immutable record date | AttackSimulation.t.sol |
| **Gas Exhaustion DoS** | MAX_CLAIM_PERIODS limit | AttackSimulation.t.sol |
| **Double Claim** | lastClaimedPeriod tracking | RMBSTranche.t.sol |
| **KYC Bypass** | Multi-layer validation | TransferValidator.t.sol |

## 🔒 Security Features

### MEV Protection
- **Atomic Snapshots**: ERC20Snapshot prevents front-running yield distributions
- **Record Date**: Balances locked at distribution time, not claim time

### DoS Prevention
- **Loop Limits**: MAX_CLAIM_PERIODS = 100 prevents gas exhaustion
- **Batch Claims**: `claimYieldUpTo()` for long-inactive holders

### Compliance
- **KYC/AML**: Investor verification with expiration
- **Accreditation**: Accredited investor checks
- **Jurisdiction**: Country-level restrictions
- **Sanctions**: OFAC sanctions screening
- **Lock-up**: Configurable holding periods

## 📜 Smart Contract Architecture

```
                          ┌─────────────────┐
                          │  RoleRegistry   │ ← Platform-wide RBAC
                          │   (Central)     │
                          └────────┬────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         │                         │                         │
         ▼                         ▼                         ▼
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│ TrancheFactory  │      │ WaterfallEngine │      │  ServicerOracle │
│  (Deployer)     │      │  (Distributor)  │      │    (Data)       │
└────────┬────────┘      └────────┬────────┘      └────────┬────────┘
         │                        │                         │
         ▼                        │                         │
┌─────────────────┐               │                         │
│  RMBSTranche    │◄──────────────┴─────────────────────────┘
│  (ERC-1400)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│TransferValidator│ ← Compliance Engine
│  (Compliance)   │
└─────────────────┘
```

## 📖 Documentation

- [Implementation Status](./IMPLEMENTATION_STATUS.md) - Progress tracking
- [Security Fixes](./SECURITY_FIXES.md) - Security vulnerability documentation
- [Technical Review](./TECHNICAL_REVIEW.md) - Code review notes
- [Web3 Design Document](../docs/Web3_Tokenization_Design.md) - Full architecture

## 🛡️ License

MIT
