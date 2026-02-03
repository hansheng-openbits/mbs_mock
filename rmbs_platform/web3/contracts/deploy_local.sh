#!/bin/bash
set -e

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║     RMBS Platform - Local Testnet Deployment (Anvil)         ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""
echo "✨ Benefits:"
echo "   - Instant deployment (no waiting for faucets)"
echo "   - 10,000 ETH pre-funded accounts"
echo "   - Fast transactions (no network delays)"
echo "   - Perfect for testing full workflow"
echo ""

# Update .env for local deployment
cat > .env << 'LOCALENV'
DEPLOYER_PRIVATE_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
ADMIN_ADDRESS=0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
COMPLIANCE_OFFICER_ADDRESS=0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
TRUSTEE_ADDRESS=0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
SERVICER_ADDRESS=0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266
LOCALHOST_RPC_URL=http://127.0.0.1:8545
PAYMENT_TOKEN_ADDRESS=0x0000000000000000000000000000000000000001
LOCALENV

echo "🔧 Starting Anvil local testnet..."
pkill -f anvil 2>/dev/null || true
sleep 1

# Start Anvil in background
anvil --port 8545 --chain-id 31337 > anvil.log 2>&1 &
ANVIL_PID=$!
echo $ANVIL_PID > anvil.pid

echo "⏳ Waiting for Anvil to start..."
sleep 3

# Check if Anvil is running
if ! curl -s -X POST -H "Content-Type: application/json" \
     --data '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' \
     http://127.0.0.1:8545 > /dev/null; then
    echo "❌ Anvil failed to start"
    exit 1
fi

echo "✅ Anvil started (PID: $ANVIL_PID)"
echo ""

# Show pre-funded accounts
echo "📊 Pre-funded Test Accounts (each has 10,000 ETH):"
echo ""
echo "Account #0 (Deployer/Admin):"
echo "  Address: 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
echo "  Private Key: 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
echo ""
echo "Account #1 (Investor 1):"
echo "  Address: 0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
echo "  Private Key: 0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
echo ""
echo "Account #2 (Investor 2):"
echo "  Address: 0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"
echo "  Private Key: 0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a"
echo ""

echo "═══════════════════════════════════════════════════════════════"
echo "  DEPLOYING SMART CONTRACTS"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Deploy contracts
forge script script/Deploy.s.sol:Deploy \
  --rpc-url http://127.0.0.1:8545 \
  --broadcast \
  -vvv

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║              ✅ DEPLOYMENT SUCCESSFUL! ✅                     ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo ""
    echo "📁 Deployment saved to: broadcast/Deploy.s.sol/31337/"
    echo "🌐 Local RPC: http://127.0.0.1:8545"
    echo "⚡ Chain ID: 31337"
    echo ""
    echo "🎯 Next Steps:"
    echo "   1. Deploy sample deal: ./deploy_sample_deal_local.sh"
    echo "   2. Test full workflow"
    echo "   3. Anvil is running in background (PID: $ANVIL_PID)"
    echo ""
    echo "💡 To stop Anvil: kill $ANVIL_PID"
    echo "📝 View logs: tail -f anvil.log"
else
    echo ""
    echo "❌ Deployment failed"
    kill $ANVIL_PID 2>/dev/null || true
    exit 1
fi
