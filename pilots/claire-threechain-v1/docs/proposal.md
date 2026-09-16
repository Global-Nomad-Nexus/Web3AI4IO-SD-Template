# Claire's on-chain pilot proposal

## Contribution and intended reuse

This component provides an evidence-preserving construction workflow for a
three-chain dataset of transaction records, reusable token/platform facts and
replaceable research events. It supports the Web3AI4IO adaptation into a Data
Descriptor by emphasizing creation, documentation, technical quality and reuse.
This pilot makes no new causal, predictive, fraud or token-success claim.

The same saved transactions can support different event definitions. For
example, a researcher can require one or three distinct successful trade
transactions before marking a token as active within the window. These choices
do not change which original records were collected. Social scientists can
inspect participation proxies, information-systems researchers can examine
recording and measurement boundaries, and graph researchers can reconstruct
observed token-address relations.

## Actors, activities and observations

Users and creators submit signed transactions; contracts and programs execute
instructions, sometimes invoking additional programs or contracts. Chain
execution and consensus produce blocks, transactions and chain-native execution
records. RPC providers expose those records. A saved raw observation is an RPC
response envelope; the normalized tables have explicit row units such as one
transaction, one EVM log or one Solana instruction. Events are derived rows,
not the raw population definition.

See editable [D1](../figures/D1.mmd). Recorded success is execution success, not
economic success. An address is not a person. A submitted transaction is not
necessarily included, and this finalized-block snapshot does not cover the
mempool or transactions never included in a block.

## Population and pilot selection

The fixed interval is **2026-09-14 12:00:00 UTC inclusive to 12:05:00 UTC
exclusive** on Solana mainnet, BSC mainnet and Base mainnet. All finalized
transaction records in blocks assigned to the interval are included. There is
no token, platform, popularity, transaction-count or event-type filter in raw
collection. Failed, vote/system, unknown-version and undecodable records remain.
Adjacent boundary blocks are retained for validation and excluded from the main
analytical tables. Missing and uncertain records remain visible in reports.

The window is intentionally short to test the whole pipeline with limited data
volume. It does not provide a complete lifecycle or a representative estimate of
platform adoption. Pump.fun, Four.meme and Clanker are decoding lenses applied
after collection. Their registries do not select the raw transactions.

## Computational workflow

See editable [D2](../figures/D2.mmd). Stages correspond directly to the local CLI:

| Stage | Purpose | Input | Output and principal check |
|---|---|---|---|
| `preflight` | Check free source capabilities | `config/rpc.json` | Source receipts; do not infer archive support from a successful latest-block read |
| `resolve_window` | Freeze heights/slots and boundaries | UTC interval, source access | `reports/window.json`, boundary records; retain unknown time membership |
| `collect` | Preserve all scoped native records | Frozen block lists | `raw/` and request provenance; no hidden first-N truncation |
| `crosscheck` | Compare bounded independent observations | Saved blocks plus another source | Cross-source receipt; failures and unavailable sources stay explicit |
| `transaction_probe` | Check Solana RPC method consistency | Seeded bounded transactions from saved blocks | Same-source `getTransaction` versus `getBlock` comparison; not independent corroboration |
| `provenance` | Make acquisition receipts queryable | Preserved request ledger | `provenance/requests.parquet`; requested block context remains distinct from resolved response evidence |
| `normalize` | Expose typed source-linked facts | Raw envelopes | `tables/base/`; retain exact amounts, ordered IDs and unknowns |
| `decode` | Interpret recognized programs and layouts | Base tables and versioned source definitions | `tables/decoded/`; report unmatched and failed decodes |
| `derive_events` | Apply researcher-defined rules | Fixed decoded facts | `tables/events/`; thresholds change without raw/base changes |
| `visualize` | Demonstrate bounded descriptive reuse | Tables and reports | Mermaid sources, numerical CSVs and captions |
| `validate` | Check technical integrity | All scoped artifacts | Actual coverage, count, identity and raw-reference checks |
| `replay` | Test snapshot reconstruction | Saved raw snapshot | Offline rebuilt outputs; raw hashes preserved |
| `reproduce` | Record fresh-runtime reconstruction evidence | Versioned code and snapshot | `reports/reproduction.json`; separate from notebook execution and Colab tests |
| `execute_notebook` | Execute the local eight-part tutorial | Complete validated snapshot | Executed notebook and execution receipt; temporary kernel, failure capture and default event restoration |

Files are in `claire_demo/`, data under `raw/` and `tables/`, and evidence under
`reports/` and `provenance/`. No public repository commit or Drive link is claimed
until a separately authorized publication/upload is actually completed.

## Future integration and scale

The future off-chain component may link a document to a chain-qualified token,
contract or platform version using explicit documentary evidence. It must
separate publication, observation and retrieval times and retain ambiguity and
unmatched cases. This pilot only preserves the identifiers and provenance needed
for that later work; it does not implement or validate integration.

Scaling extends the time interval and decoding coverage while preserving the
raw/facts/events separation. It requires measured RPC throughput, missingness and
storage costs. Historical traces and historical account states remain separately
scoped data products; collecting transactions does not imply collecting all
execution or state information.
