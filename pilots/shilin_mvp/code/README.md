# Pump.fun MVP implementation

This folder combines the v2 metadata routes with the DKUCC collection path. It uses the Python standard library only.

- `mvp/acquire_chain.py` decodes Pump.fun create instructions and talks to Solana JSON-RPC over IPv4. Failed calls are retried inside the client.
- `mvp/live_cohort.py` enrolls creates for 24 hours from the moment the process starts. That moment is T0. The same process then collects T+24h and, after 36 more hours, T+60h. It does not replay a frozen historical window.
- `mvp/observe_metadata.py` requests the declared URI first, keeps that URI in every receipt, and records `request_url` plus `route_id` for IPFS and Arweave gateways. Public hosts are allowed. Local and private hosts are refused.
- `mvp/gateway_preflight.py` checks metadata gateways before a live run. A failed check is retried, then collection continues.
- `mvp/build_release.py` parses fixed JSON pointers, writes the coverage ledger, records validation differences, and still publishes the release.

The default `fixture` mode is deterministic and offline. It checks the pipeline. It is not a scientific observation. `rpc` mode uses `solana-rpc.publicnode.com` because that host answers on IPv4 from the DKUCC common CPU. `api.mainnet-beta.solana.com` is registered as not used from this partition.

## Run

```bash
cd "/work/so192/scientific data/code v3"
python run_mvp.py --mode fixture --output "/work/so192/scientific data/data/fixture-demo"
python -m unittest discover -s tests -v
```

Live collection is one process. It enrolls Pump.fun creates for 24 hours from the moment it starts, treats that moment as T0, requests metadata as each create appears, waits, then collects the same cohort at T+24h and again 36 hours later at T+60h. After the last checkpoint it parses fields, writes the coverage ledger, and publishes `mvp_release/`. Nothing in that process waits for a person. The run needs about 60 hours:

```bash
cd "/work/so192/scientific data/code v3"
python run_mvp.py --mode rpc --output "/work/so192/scientific data/data"
```

Receipts are rewritten as events and metadata attempts arrive. If that process stops before `run/cohort_status.json` says `finished`, running the same command again resumes the newest unfinished cohort instead of starting over. A failed RPC page, transaction fetch, gateway check, or metadata request is saved and tried again. The run does not stop for a manual review, and it does not switch the RPC endpoint on its own.

A short connectivity check that does not start the 60-hour wait:

```bash
python -m mvp.smoke_rpc --output "/work/so192/scientific data/data/smoke"
```
