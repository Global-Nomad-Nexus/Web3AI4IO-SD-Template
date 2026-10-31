# Source acquisition

The release reproduces a frozen snapshot. Source URLs, selected versions and
retrieval metadata accompany the records and [input provenance](../metadata/input-provenance.json).
New acquisition produces a new snapshot with its own retrieval time and hashes.

| Source | Acquisition route | Historical-snapshot behavior |
|---|---|---|
| Binance Vision | Download each CSV ZIP and its `.CHECKSUM` from the row's `source_url` | Archives identify pair, interval and date; verify SHA-256 before parsing |
| Raydium | `/pools/line/liquidity?id=58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2` at `https://api-v3.raydium.io` | The API serves a rolling history; retain the response when collecting |
| Solana | `https://api.mainnet.solana.com`, finalized `getBlocks` and `getBlock` | Historical block availability depends on the serving node; preserve the exact selected slots |
| growthepie | `https://api.growthepie.com/v1/metrics/chains/base/fees.json` and `txcount.json` | Updated responses may revise previous daily values |
| Coin Metrics | Community API `timeseries/asset-metrics`; exact queries in the output | Historical values can change with provider revisions |
| CoinSpectrum | Internet Archive captures linked by `archive_url` | The release uses one retained generation time; archive availability controls reacquisition |
| CoinMarketCap | Global metrics chart response identified by each row's URL | The frozen response supplies this release's selected dates |
| New York Fed | EFFR API linked in `source_url` | Values and revision indicators follow the downloaded snapshot |
| BLS | Public API and dated archived release URLs | Reference month, scheduled embargo end and retrieval version have separate meanings |
| U.S. Treasury | Official yield-curve XML linked in `source_url` | Parse the 10-year par-yield field and retain the download version |
| News and mechanisms | Row-level publication URLs, fixed Git commits and source sections | Read sources and retain attributed fact status, dates, scope and version |

For a new RPC acquisition, retain the fixed selected slots, use finalized blocks,
request transaction details sufficient to count all returned transactions, and
include successful, failed and vote transactions. Retry the same unavailable slot
without substituting another block. The original procedure used 50 distinct blocks
per hour from the provider-returned frame. The seed was
`NatureSD|solana-data-v1|2026-10-08/2026-10-18|50-blocks-per-hour|v1`.
The selection table supplies the exact slots and inclusion probabilities used here.

Source-specific use conditions remain in [the inventory](../metadata/inventory.csv).
