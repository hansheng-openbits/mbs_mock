# Quick Start: Deploy to Arbitrum Sepolia Testnet

**Last Updated**: January 30, 2026  
**Estimated Time**: 10 minutes  
**Cost**: FREE (testnet)

---

## ✅ Prerequisites (Already Done!)

- [x] Foundry installed
- [x] Smart contracts compiled
- [x] Deployment scripts ready
- [x] Test account generated
- [x] Environment configured

---

## 🚀 3-Step Deployment

### Step 1: Get Testnet ETH (2 minutes)

**Your Testnet Address:**
```
0x54d353CFA012F1E0D848F23d42755e98995Dc5f2
```

**Get FREE testnet ETH from any faucet:**

#### Option A: QuickNode (Fastest - No signup)
1. Visit: https://faucet.quicknode.com/arbitrum/sepolia
2. Paste address: `0x54d353CFA012F1E0D848F23d42755e98995Dc5f2`
3. Solve CAPTCHA
4. Click "Request"
5. Receive 0.01 ETH instantly

#### Option B: Alchemy (Most generous)
1. Visit: https://www.alchemy.com/faucets/arbitrum-sepolia
2. Sign up (free, takes 1 minute)
3. Paste address: `0x54d353CFA012F1E0D848F23d42755e98995Dc5f2`
4. Receive 0.5 ETH/day

#### Option C: Chainlink
1. Visit: https://faucets.chain.link/arbitrum-sepolia
2. Connect wallet OR paste address
3. Receive 0.1 ETH

---

### Step 2: Verify Balance (30 seconds)

```bash
cd contracts
cast balance 0x54d353CFA012F1E0D848F23d42755e98995Dc5f2 \
  --rpc-url https://sepolia-rollup.arbitrum.io/rpc \
  --ether
```

**Expected**: Should show `> 0.001` ETH

---

### Step 3: Deploy! (5 minutes)

#### Option A: Automated Deployment (Recommended)
```bash
./deploy_when_funded.sh
```
This will:
- Check your balance
- Deploy all 6 contracts automatically
- Save deployment addresses
- Print success message

#### Option B: Manual Deployment
```bash
forge script script/Deploy.s.sol:Deploy \
  --rpc-url https://sepolia-rollup.arbitrum.io/rpc \
  --broadcast \
  -vvv
```

---

## 🎉 After Deployment

### What You'll Get

```
✅ 6 Implementation Contracts Deployed
✅ 5 Proxy Contracts Deployed & Initialized
✅ Roles Configured (Admin, Compliance Officer)
✅ US Jurisdiction Added
✅ Contracts Linked

💰 Gas Used: ~0.00126 ETH (~$3.15)
⏱️ Time: ~30-60 seconds
```

### Deployment Addresses

All deployment addresses will be saved to:
```
broadcast/Deploy.s.sol/421614/run-latest.json
```

### View on Arbiscan

```
https://sepolia.arbiscan.io/address/0x54d353CFA012F1E0D848F23d42755e98995Dc5f2
```

---

## 🔍 Verify Deployment

Check that everything deployed correctly:

```bash
# Check TrancheFactory (example)
FACTORY_ADDRESS="<address from deployment>"
cast call $FACTORY_ADDRESS \
  "hasRole(bytes32,address)(bool)" \
  $(cast keccak "DEFAULT_ADMIN_ROLE()") \
  0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 \
  --rpc-url https://sepolia-rollup.arbitrum.io/rpc
```

**Expected**: `true`

---

## 📚 Next Steps After Deployment

### 1. Deploy a Sample Deal (5 minutes)

Update `.env` with deployed contract addresses, then:

```bash
forge script script/DeploySampleDeal.s.sol:DeploySampleDeal \
  --rpc-url https://sepolia-rollup.arbitrum.io/rpc \
  --broadcast \
  -vvv
```

This will create:
- Sample RMBS Deal "2026-1"
- 3 Tranches (Senior, Mezzanine, Junior)
- $100M total face value
- Waterfall configuration

### 2. Test Full Workflow

#### A. Setup KYC for Test Investor
```bash
VALIDATOR="<TransferValidator address>"
INVESTOR="0x70997970C51812dc3A010C7d01b50e0d17dc79C8"

cast send $VALIDATOR \
  "setKYCStatus(address,bool,uint256)" \
  $INVESTOR \
  true \
  $(($(date +%s) + 31536000)) \
  --rpc-url https://sepolia-rollup.arbitrum.io/rpc \
  --private-key $DEPLOYER_PRIVATE_KEY
```

#### B. Set Investor Jurisdiction
```bash
cast send $VALIDATOR \
  "setJurisdiction(address,bytes2)" \
  $INVESTOR \
  "0x5553" \
  --rpc-url https://sepolia-rollup.arbitrum.io/rpc \
  --private-key $DEPLOYER_PRIVATE_KEY
```

#### C. Issue Tokens
```bash
TRANCHE_A="<Senior tranche address>"

cast send $TRANCHE_A \
  "issue(address,uint256)" \
  $INVESTOR \
  1000000000000000000000000 \
  --rpc-url https://sepolia-rollup.arbitrum.io/rpc \
  --private-key $DEPLOYER_PRIVATE_KEY
```

#### D. Check Balance
```bash
cast call $TRANCHE_A \
  "balanceOf(address)(uint256)" \
  $INVESTOR \
  --rpc-url https://sepolia-rollup.arbitrum.io/rpc
```

---

## 🐛 Troubleshooting

### Issue: "insufficient funds for gas"
**Solution**: Get more testnet ETH from faucet

### Issue: "nonce too low/high"
**Solution**: 
```bash
cast nonce 0x54d353CFA012F1E0D848F23d42755e98995Dc5f2 \
  --rpc-url https://sepolia-rollup.arbitrum.io/rpc
```

### Issue: Deployment script fails
**Solution**: Check logs in `broadcast/` directory

### Issue: Can't get testnet ETH
**Solution**: Try different faucets or wait 24 hours

---

## 📊 Gas Cost Breakdown

| Item | Gas | Cost (ETH) | Cost (USD) |
|------|-----|------------|------------|
| RMBSTranche Impl | ~4M | 0.00016 | $0.40 |
| TransferValidator Impl | ~2.6M | 0.00010 | $0.26 |
| TrancheFactory Impl | ~2.7M | 0.00011 | $0.27 |
| WaterfallEngine Impl | ~3.6M | 0.00014 | $0.36 |
| ServicerOracle Impl | ~2.9M | 0.00012 | $0.29 |
| RoleRegistry Impl | ~3.2M | 0.00013 | $0.32 |
| All Proxies | ~2M | 0.00008 | $0.20 |
| Initialization | ~10M | 0.00040 | $1.00 |
| **TOTAL** | **~31.6M** | **~0.00126** | **~$3.15** |

*Assumes gas price of 0.04 gwei (typical for Arbitrum) and ETH = $2,500*

---

## 🔒 Security Reminders

- ✅ This is a TESTNET deployment
- ✅ Private key is for TESTING ONLY
- ❌ NEVER use this private key on mainnet
- ❌ NEVER send real ETH to this address
- ✅ Keep test_wallet.txt and TESTNET_ACCOUNT.txt secure
- ✅ Don't commit .env to version control

---

## 📞 Support

**Deployment not working?**
1. Check your balance has > 0.002 ETH
2. Verify RPC is responding
3. Check gas prices aren't spiking
4. Review error logs in terminal

**Need help?**
- Check `DEPLOYMENT.md` for detailed guide
- Review Foundry docs: https://book.getfoundry.sh/
- Arbitrum Sepolia explorer: https://sepolia.arbiscan.io/

---

## ✅ Success Checklist

After deployment, you should have:

- [ ] All 6 implementation contracts deployed
- [ ] All 5 proxy contracts deployed
- [ ] Deployment addresses saved to broadcast/
- [ ] Admin role verified
- [ ] Compliance officer role granted
- [ ] US jurisdiction added
- [ ] Contracts verified on Arbiscan (optional)
- [ ] Sample deal deployed (optional)

---

**Ready? Let's deploy!** 🚀
