#!/bin/bash
# Simple local deployment script

set -e

export PATH="$HOME/.foundry/bin:$PATH"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║          LOCAL TESTNET DEPLOYMENT                              ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check if Anvil is running
if ! curl -s -X POST http://localhost:8545 -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' > /dev/null 2>&1; then
    echo "⚠️  Anvil is not running. Starting Anvil..."
    echo ""
    echo "Please run this in a separate terminal:"
    echo "  anvil --port 8545 --chain-id 31337"
    echo ""
    echo "Then press Enter to continue..."
    read
fi

echo "✅ Anvil detected on localhost:8545"
echo ""
echo "🚀 Deploying contracts..."
echo ""

# Deploy using Foundry
forge script script/Deploy.s.sol:Deploy \
    --rpc-url http://localhost:8545 \
    --broadcast \
    --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
    -vvv

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "  ✅ DEPLOYMENT SUCCESSFUL!"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    echo "📝 Deployment addresses saved to:"
    echo "   broadcast/Deploy.s.sol/31337/run-latest.json"
    echo ""
    echo "🔍 Check logs above for contract addresses"
    echo ""
else
    echo ""
    echo "❌ Deployment failed"
    exit $EXIT_CODE
fi
