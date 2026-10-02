# API selection

- Status: **direct_collection**
- Candidate: `publicnode-solana-mainnet`
- Endpoint: `https://solana-rpc.publicnode.com`
- Address family: IPv4
- RPC mode enrolls for 24 hours from the process start. T0 is that start, then the same process collects T+24h and observes again at T+60h, 36 hours after collection ends. Failed calls are saved and retried.
