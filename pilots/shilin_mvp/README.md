# Pump.fun v3 cohort

This folder contains the code and the completed live dataset for one Pump.fun metadata cohort. The run enrolled newly created tokens for 24 hours and then observed the same tokens again after the collection window and after 36 further hours.

The cohort is a feasibility collection. It is not the seven-day, four-checkpoint dataset described in the formal study plan, and the observation clock is the collection start rather than each token’s chain time.

## What was done

One process started on the DKUCC common CPU partition at `2026-09-29T06:16:11Z`. That moment is T0. From then until `2026-09-30T06:16:11Z`, the process scanned the Pump.fun program for successful token-creation transactions and requested each declared metadata URI as the event was enrolled. The same cohort was requested again at `2026-09-30T06:16:11Z` (T+24h, the end of collection) and at `2026-10-01T18:16:11Z` (T+60h, 36 hours after collection ended). The job finished at `2026-10-01T21:33:14Z`.

Every enrolled creation stays in the denominator. A failed metadata request is recorded; it does not remove the event. The release validation status is `PASS`.

| Item | Result |
|---|---|
| Network and program | Solana mainnet, Pump.fun `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` |
| Enrolled creation events | 1,248 |
| Required observations | 3,744 (1,248 events × T0, T+24h, T+60h) |
| Metadata attempts | 11,539 |
| Successfully parsed observations | 3,216 |
| Request failures | 330 |
| Refused by collection policy | 198 |
| Parsed JSON fields | `name`, `symbol`, `description`, `createdOn`, `image`, `website`, `twitter`, `telegram` |

Checkpoint coverage among the 1,248 events: T0 parsed 1,077 responses, T+24h parsed 1,070, and T+60h parsed 1,069.

The collector does not download images, social posts, account pages, or chat text, and it does not label identity or fraud. Raw third-party response bodies remain in the run directory and are not marked for redistribution.

## Where the data came from

Chain events came from one public Solana JSON-RPC endpoint:

- `https://solana-rpc.publicnode.com` (PublicNode). The client connects over IPv4 and calls `getSignaturesForAddress` and `getTransaction`.

`https://api.mainnet-beta.solana.com` is listed in the source register and was not used. Its DNS answers did not connect from the DKUCC common CPU partition.

Metadata came from the URI written in the Pump.fun create instruction. The collector requests that declared URL first. If the declaration is an IPFS CID and the first request fails, it tries the same CID through these registered gateways:

- `https://pump.mypinata.cloud`
- `https://gateway.pinata.cloud`

In this run, most successful requests used the declared host directly. The largest declared hosts were `gateway.irys.xyz` and `pump.mypinata.cloud`, followed by smaller public HTTPS hosts named in individual creation transactions. `ipfs.io` and `arweave.net` are registered as unused because IPv4 connections from this partition timed out. Local and private hosts are refused before any request.

The source register, terms URLs, and access decisions are in `code/configs/source_register.csv`. The frozen protocol is `code/configs/mvp_protocol.json`.

## What is in this folder

| Path | Contents |
|---|---|
| `code/` | Standard-library Python collector, metadata observer, release builder, fixtures, and tests |
| `data/live-v3-20260929T061604Z/mvp_release/` | Published tables: events, observation plan, attempts, snapshots, fields, coverage ledger, and validation |
| `data/live-v3-20260929T061604Z/run/` | Receipts written during the run, including response bodies |

The offline fixture mode checks the pipeline and does not contact the network:

```bash
cd code
python3 run_mvp.py --mode fixture --output /tmp/pumpfun-v3-fixture
python3 -m unittest discover -s tests -v
```

Live collection uses the same entry point with `--mode rpc`. A live run waits through the 24-hour enrollment and the later checkpoints; it is not required to read the dataset already stored here.
