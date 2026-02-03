# Chain Configuration

This directory contains network configuration files for different blockchain networks.

## Files

| File | Network | Description |
|------|---------|-------------|
| `localhost.json` | Local | Hardhat/Ganache local development |
| `polygon.json` | Polygon | Polygon mainnet (production) |
| `mainnet.json` | Ethereum | Ethereum mainnet (production) |

## Configuration Fields

```json
{
  "network": {
    "name": "network_name",
    "chain_id": 137,
    "rpc_url": "https://...",
    "block_explorer": "https://...",
    "is_testnet": false
  },
  "contracts": {
    "payment_token": "0x...",     // USDC/USDT address
    "deal_registry": "0x...",     // Central deal registry
    "loan_nft_factory": "0x...",  // Factory for loan NFTs
    "tranche_token_factory": "0x...", // Factory for tranche tokens
    "waterfall_engine": "0x..."   // Waterfall execution contract
  },
  "settings": {
    "gas_limit": 8000000,
    "gas_price_gwei": 50,
    "confirmation_blocks": 5,
    "mock_mode": false
  }
}
```

## Adding a New Network

1. Create `{network_name}.json` in this directory
2. Add deployment scripts for that network
3. Update `ACTIVE_NETWORK` in api_main.py
