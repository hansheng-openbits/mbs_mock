# Web3 Sync Directory

This directory contains **cached blockchain state** for the RMBS platform.

## Files

| File | Description |
|------|-------------|
| `token_balances.json` | Cached token holder balances (mirrors on-chain state) |
| `yield_distributions.json` | Cached yield distribution events |
| `distribution_cycles.json` | Distribution period tracking |
| `sync_state.json` | Blockchain sync checkpoint |

## Important Notes

1. **Source of Truth**: In production, the blockchain is the source of truth. These files are caches.
2. **Mock Mode**: In development/demo mode, these files ARE the source of truth.
3. **Sync**: When connected to a real chain, run the sync process to update these caches.

## Data Flow

```
Blockchain → Sync Process → web3_sync/*.json → API → UI
```

## Resetting

To reset all Web3 data, use the Arranger portal's "Reset Deal Data" feature or manually clear these files.
