# RMBS Platform Deployment Guide

This guide covers deploying the RMBS Platform smart contracts to Arbitrum (testnet and mainnet).

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Environment Setup](#environment-setup)
3. [Deployment Steps](#deployment-steps)
4. [Post-Deployment Configuration](#post-deployment-configuration)
5. [Verification](#verification)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Tools
- **Foundry** (forge, cast, anvil)
  ```bash
  curl -L https://foundry.paradigm.xyz | bash
  foundryup
  ```

- **Node.js** v18+ (for additional tooling)
- **Git**

### Required Accounts
1. **Deployer Account**: Funded with ETH for gas fees
2. **Admin Account**: Platform administrator
3. **Compliance Officer**: KYC/AML oversight
4. **Trustee Account** (optional for initial deployment)
5. **Servicer Account** (optional for initial deployment)

### Network Configuration

#### Arbitrum Sepolia (Testnet)
- **RPC URL**: `https://sepolia-rollup.arbitrum.io/rpc`
- **Chain ID**: 421614
- **Block Explorer**: https://sepolia.arbiscan.io
- **Faucet**: https://faucet.quicknode.com/arbitrum/sepolia

#### Arbitrum One (Mainnet)
- **RPC URL**: `https://arb1.arbitrum.io/rpc`
- **Chain ID**: 42161
- **Block Explorer**: https://arbiscan.io

---

## Environment Setup

### 1. Clone and Install
```bash
cd contracts
forge install
```

### 2. Configure Environment Variables

Copy the example environment file:
```bash
cp .env.example .env
```

Edit `.env` with your values:

```bash
# Deployer Private Key (NEVER commit this!)
DEPLOYER_PRIVATE_KEY=0x...

# Network RPCs
ARBITRUM_RPC_URL=https://arb1.arbitrum.io/rpc
ARBITRUM_SEPOLIA_RPC_URL=https://sepolia-rollup.arbitrum.io/rpc

# Platform Addresses
ADMIN_ADDRESS=0x...
COMPLIANCE_OFFICER_ADDRESS=0x...

# Contract Verification (optional)
ARBISCAN_API_KEY=...

# For Sample Deal Deployment
PAYMENT_TOKEN_ADDRESS=0x... # USDC address on target chain
TRUSTEE_ADDRESS=0x...
SERVICER_ADDRESS=0x...
```

### 3. Fund Deployer Account

**Testnet (Sepolia ETH)**:
- Use faucet: https://faucet.quicknode.com/arbitrum/sepolia
- Need ~0.1 ETH for deployment

**Mainnet (ETH)**:
- Bridge ETH to Arbitrum One
- Need ~0.05 ETH for deployment (estimate, varies with gas)

---

## Deployment Steps

### Step 1: Deploy Core Contracts

#### Testnet Deployment
```bash
forge script script/Deploy.s.sol:Deploy \
  --rpc-url $ARBITRUM_SEPOLIA_RPC_URL \
  --broadcast \
  --verify \
  --etherscan-api-key $ARBISCAN_API_KEY \
  -vvvv
```

#### Mainnet Deployment (DRY RUN FIRST!)
```bash
# 1. Dry run (no broadcast)
forge script script/Deploy.s.sol:Deploy \
  --rpc-url $ARBITRUM_RPC_URL \
  -vvvv

# 2. If dry run succeeds, broadcast
forge script script/Deploy.s.sol:Deploy \
  --rpc-url $ARBITRUM_RPC_URL \
  --broadcast \
  --verify \
  --etherscan-api-key $ARBISCAN_API_KEY \
  -vvvv
```

**Expected Output**:
```
=== RMBS Platform Deployment ===
Deployer: 0x...
Admin: 0x...
Compliance Officer: 0x...

Step 1: Deploying implementation contracts...
RMBSTranche Implementation: 0x...
TransferValidator Implementation: 0x...
... (more addresses)

=== Deployment Complete ===
=== Proxy Contracts (Use These) ===
RoleRegistry: 0x...
ServicerOracle: 0x...
...
```

**Save these proxy addresses!** You'll need them for:
- Sample deal deployment
- Frontend integration
- Backend integration

### Step 2: Deploy Sample Deal (Optional)

After core deployment, update `.env` with the proxy addresses:
```bash
FACTORY_ADDRESS=0x...           # From Deploy output
VALIDATOR_ADDRESS=0x...         # From Deploy output
WATERFALL_ADDRESS=0x...         # From Deploy output
ORACLE_ADDRESS=0x...            # From Deploy output
PAYMENT_TOKEN_ADDRESS=0x...     # USDC on target chain
```

Deploy sample deal:
```bash
forge script script/DeploySampleDeal.s.sol:DeploySampleDeal \
  --rpc-url $ARBITRUM_SEPOLIA_RPC_URL \
  --broadcast \
  -vvvv
```

**Expected Output**:
```
=== Sample Deal Deployment ===
...
Step 3: Deploying tranches...
Senior Tranche (A): 0x...
Mezz Tranche (M): 0x...
Junior Tranche (B): 0x...

=== Deal Deployment Complete ===
Total Face Value: $100,000,000
```

---

## Post-Deployment Configuration

### 1. Add Additional Jurisdictions

```bash
# Example: Add GB (United Kingdom)
cast send $VALIDATOR_ADDRESS \
  "addJurisdiction(bytes2)" \
  "0x4742" \ # "GB" in hex
  --rpc-url $ARBITRUM_SEPOLIA_RPC_URL \
  --private-key $DEPLOYER_PRIVATE_KEY
```

Common jurisdiction codes:
- US: `0x5553`
- GB: `0x4742`
- CA: `0x4341`
- DE: `0x4445`
- FR: `0x4652`

### 2. Setup KYC for Investors

```bash
# Grant KYC to an investor
cast send $VALIDATOR_ADDRESS \
  "setKYCStatus(address,bool,uint256)" \
  <INVESTOR_ADDRESS> \
  true \
  $(($(date +%s) + 365*24*60*60)) \ # 1 year expiry
  --rpc-url $ARBITRUM_SEPOLIA_RPC_URL \
  --private-key $DEPLOYER_PRIVATE_KEY
```

### 3. Set Investor Jurisdiction

```bash
cast send $VALIDATOR_ADDRESS \
  "setJurisdiction(address,bytes2)" \
  <INVESTOR_ADDRESS> \
  "0x5553" \ # US
  --rpc-url $ARBITRUM_SEPOLIA_RPC_URL \
  --private-key $DEPLOYER_PRIVATE_KEY
```

### 4. Issue Tokens to Investors

```bash
# Issue $1M of Senior Tranche to investor
cast send $SENIOR_TRANCHE_ADDRESS \
  "issue(address,uint256)" \
  <INVESTOR_ADDRESS> \
  1000000000000000000000000 \ # 1M * 1e18
  --rpc-url $ARBITRUM_SEPOLIA_RPC_URL \
  --private-key $DEPLOYER_PRIVATE_KEY
```

---

## Verification

### 1. Verify Contract Sources on Arbiscan

If `--verify` failed during deployment, manually verify:

```bash
forge verify-contract \
  --chain-id 42161 \
  --compiler-version v0.8.20+commit.a1b79de6 \
  --num-of-optimizations 200 \
  <CONTRACT_ADDRESS> \
  <CONTRACT_NAME> \
  --etherscan-api-key $ARBISCAN_API_KEY
```

Example:
```bash
forge verify-contract \
  --chain-id 421614 \
  --compiler-version v0.8.20+commit.a1b79de6 \
  --num-of-optimizations 200 \
  0x1234... \
  src/tokens/RMBSTranche.sol:RMBSTranche \
  --etherscan-api-key $ARBISCAN_API_KEY
```

### 2. Test Contract Interactions

#### Check Admin Role
```bash
cast call $FACTORY_ADDRESS \
  "hasRole(bytes32,address)(bool)" \
  $(cast keccak "DEFAULT_ADMIN_ROLE()") \
  $ADMIN_ADDRESS \
  --rpc-url $ARBITRUM_SEPOLIA_RPC_URL
```

#### Check Tranche Info
```bash
cast call $SENIOR_TRANCHE_ADDRESS \
  "getTrancheInfo()(bytes32,string,uint256,uint256,uint256,uint8,uint256,uint256,bool)" \
  --rpc-url $ARBITRUM_SEPOLIA_RPC_URL
```

---

## Troubleshooting

### Common Issues

#### 1. "Insufficient Funds for Gas"
**Solution**: Fund deployer account with more ETH

#### 2. "Nonce Too Low/High"
**Solution**: Reset nonce
```bash
cast nonce $DEPLOYER_ADDRESS --rpc-url $ARBITRUM_SEPOLIA_RPC_URL
```

#### 3. "Contract Already Deployed"
**Solution**: Use a different deployer account or deploy to a different network

#### 4. "Verification Failed"
**Solution**: 
- Wait 30-60 seconds after deployment
- Try manual verification (see Verification section)
- Check compiler version matches exactly

#### 5. "Access Control Error"
**Solution**: Ensure `ADMIN_ADDRESS` is set correctly in `.env`

### Gas Estimation

Approximate gas costs (at 0.1 gwei):

| Contract | Deployment Gas | Cost (ETH) |
|----------|----------------|------------|
| RMBSTranche Impl | ~3M | ~0.0003 |
| TransferValidator Impl | ~2.5M | ~0.00025 |
| TrancheFactory Impl | ~3.5M | ~0.00035 |
| WaterfallEngine Impl | ~4M | ~0.0004 |
| ServicerOracle Impl | ~3M | ~0.0003 |
| RoleRegistry Impl | ~2M | ~0.0002 |
| All Proxies | ~2M | ~0.0002 |
| **Total** | **~20M** | **~0.002 ETH** |

*Note: Arbitrum gas is significantly cheaper than Ethereum mainnet*

### Support

For deployment support:
1. Check deployment logs in `broadcast/` directory
2. Review transaction on Arbiscan
3. Check contract events for errors

---

## Security Checklist

Before mainnet deployment:

- [ ] All private keys stored securely (hardware wallet recommended)
- [ ] Multi-sig setup for admin operations
- [ ] Timelock configured for critical functions
- [ ] Smart contracts audited by reputable firm
- [ ] Bug bounty program established
- [ ] Emergency pause procedure documented
- [ ] Monitoring and alerting configured
- [ ] Backup RPC endpoints configured

---

## Next Steps After Deployment

1. **Frontend Integration**: Update frontend with contract addresses
2. **Backend Integration**: Configure backend services with contract ABIs
3. **Monitoring**: Setup contract event monitoring
4. **Documentation**: Update API documentation with contract addresses
5. **User Onboarding**: Begin KYC process for initial investors

---

## Deployment Checklist

### Pre-Deployment
- [ ] Foundry installed and updated
- [ ] Environment variables configured
- [ ] Deployer account funded
- [ ] USDC address confirmed for target network
- [ ] Admin/Compliance Officer addresses confirmed

### Deployment
- [ ] Core contracts deployed successfully
- [ ] All proxies initialized correctly
- [ ] Contract verification completed on Arbiscan
- [ ] Deployment addresses documented

### Post-Deployment
- [ ] Roles and permissions configured
- [ ] Additional jurisdictions added
- [ ] Sample deal deployed (if testing)
- [ ] Contract interactions tested
- [ ] Frontend/Backend updated with addresses

---

## Contract Addresses Reference

Keep a record of your deployed contract addresses:

### Core Implementations
- RMBSTranche: `0x...`
- TransferValidator: `0x...`
- TrancheFactory: `0x...`
- WaterfallEngine: `0x...`
- ServicerOracle: `0x...`
- RoleRegistry: `0x...`

### Proxies (Primary Interfaces)
- RoleRegistry Proxy: `0x...`
- ServicerOracle Proxy: `0x...`
- TransferValidator Proxy: `0x...`
- TrancheFactory Proxy: `0x...`
- WaterfallEngine Proxy: `0x...`

### Sample Deal (if deployed)
- Senior Tranche (A): `0x...`
- Mezz Tranche (M): `0x...`
- Junior Tranche (B): `0x...`

---

## License

MIT License - See LICENSE file for details
