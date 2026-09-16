# Data sources and access evidence

This pilot uses read-only requests to free RPC interfaces. The source candidates
below reflect `config/rpc.json`; the selected source is recorded by
`reports/preflight.json` and the target historical-window checks in
`reports/target_preflight.json`. This document does not duplicate volatile
transaction counts or convert a recent-block success into historical coverage.

| Chain | Configured source endpoints | Method/access documentation |
|---|---|---|
| Solana | `https://api.mainnet.solana.com`; `https://solana-rpc.publicnode.com` | [Solana RPC methods](https://solana.com/docs/rpc), [PublicNode](https://www.publicnode.com/) |
| BSC | `https://bsc-dataseed.bnbchain.org`; `https://bsc-rpc.publicnode.com` | [BSC endpoint documentation](https://docs.bnbchain.org/bnb-smart-chain/developers/json_rpc/json-rpc-endpoint/), [PublicNode](https://www.publicnode.com/) |
| Base | `https://mainnet.base.org`; `https://base-rpc.publicnode.com`; `https://base.llamarpc.com`; `https://base-mainnet.g.alchemy.com/public`; `https://rpc-base.blockmachine.io` | [Base RPC documentation](https://docs.base.org/base-chain/api-reference/rpc-overview), [Blockmachine Base RPC documentation](https://blockmachine.io/docs/base-rpc) |

`provenance/request_log.jsonl` preserves actual request times, methods,
parameters, source IDs and error evidence. Failed attempts remain informative:
providers may require a personal credential for historical receipts even when
public latest-block requests work. The configured no-key endpoint does not
authorize use of a paid product or bypass of provider restrictions. Failed
historical access triggers a documented free-source fallback or a blocked
collection state, never a smaller undisclosed sampling window.

The raw data are publicly observable chain RPC records. Source access and
redistribution permissions are separate matters: no blanket license over all
third-party source material is inferred from public access. Source definitions
and ABIs/IDLs retained under `sources/` keep their source provenance and applicable
license information. Any public redistribution must respect those records.
No credentials should be included in a snapshot.

## Query and state boundaries

- Solana uses full finalized block responses, with the currently supported
  transaction-version ceiling explicitly recorded. Version support must be
  tested against actual returned versions; it must not be assumed to end at 0.
- EVM chains use full block bodies plus all corresponding receipts. Returned
  logs are retained even when the platform decoder does not recognize them.
- Base system-record identification uses the L1-attributes sender and predeploy
  pair in the [OP Stack deposit specification](https://specs.optimism.io/protocol/deposits.html#l1-attributes-deposited-transaction).
  Deposit type `0x7e` alone also includes user deposits and is not a system flag.
  The raw `isSystemTx` consensus field has different, upgrade-dependent semantics.
- Historical first/middle/last target blocks are checked before committing to
  a provider for the entire interval. These probes reduce access uncertainty;
  only collection and validation establish whole-window coverage.
- EVM call traces are collected when the selected endpoint supports the
  required method. Availability, partial failures and actual coverage remain
  separate fields. A call tree is not an opcode trace or complete state dump.
- Arbitrary historical state is not implied by transaction completeness.
  Solana `getAccountInfo` cannot be treated as an arbitrary past-slot snapshot;
  current account responses do not backfill historical states.

Exact window, block lists and boundary hashes live in `reports/window.json`.
Coverage and finality checks live in `reports/coverage.csv` and
`reports/validation.json`. These reports, rather than a static document, are the
current acquisition evidence.
