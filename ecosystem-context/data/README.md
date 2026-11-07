# Data guide

Each CSV has a header, UTF-8 text and one observation or authored record per row.
Dates use ISO 8601; timestamps carry a UTC indicator or explicit offset.

| Directory | Contents |
|---|---|
| `solana/layer2/` | 576 SOL/USDT hourly bars, 24 daily Raydium single-pool values, 240 sampled hourly transaction-count estimates and 12,000 sampled-block records |
| `solana/layer3/` | 16 news and announcement facts |
| `solana/layer4/` | 70 mechanism records |
| `base/layer2/` | 504 ETH/USDC hourly bars and 42 daily metric rows, covering two series over 21 days |
| `base/layer3/` | 14 news and announcement facts |
| `base/layer4/` | 29 mechanism records and 28 source-history records |
| `bsc/layer2/` | 504 BNB/USDC hourly bars and 504 derived return/volatility rows |
| `bsc/layer3/` | Five news and announcement facts |
| `bsc/layer4/` | 22 approved mechanism records and six source-date records |
| `shared/layer5/` | Eight files containing the ten shared inventory series |

Use [inventory.csv](../metadata/inventory.csv) to select a dataset and read its
coverage, measurement scope and source conditions. Its paths are relative to this
`data/` directory. A count in the inventory applies to the stated series or filter:
for example, the macro table contains EFFR, CPI-U and unemployment together.

The Base and BSC market windows are `[2026-10-01, 2026-10-22)` UTC; the Solana
market window is `[2026-10-01, 2026-10-25)` UTC. Solana sampled network counts cover
`[2026-10-08, 2026-10-18)` UTC. Each layer retains its own documented window.

Market values retain their source quote currency: SOL hourly bars use USDT;
Base/BSC hourly bars and shared daily bars use USDC. Join by the documented time
and asset fields. Chain context is supplied at the ecosystem level; token-level
joins require a separate research design.

Empty fields represent unavailable or inapplicable values. SOL current-supply
market capitalization remains empty. BSC has 503 returns and 480 trailing
volatilities: the initial observation and initial 24-observation window respectively
have insufficient preceding data. Preserve these blanks when loading the tables.

News facts preserve reported dates, plans and attributed statistical claims.
Mechanism tables preserve document versions and applicability. Selected source
dates describe the documentation chronology; deployed rule activation requires
separate on-chain evidence.

[Methods](../metadata/METHODS.md) describe calculations and factual curation.
[File manifest](../metadata/manifest.json) records row counts, columns and hashes.

## Second-level exchange data

The three `*_market_second.parquet` files contain 2,073,600 SOL/USDT rows and
1,814,400 rows each for ETH/USDC and BNB/USDC, at one row per second. These are
exchange-market context series. Prices retain USDT or USDC quote units.

Load a file with `pandas.read_parquet(path)`. Timestamps are UTC. `has_trade`
identifies seconds with an execution; quiet seconds retain the source close.
`available_at_utc` labels candle completion. It does not record archive publication.
The first return and first 86,400 volatility rows are null. Field definitions
and null counts are included in `metadata/fields.csv`.

## Second-level AWS-derived data

`base/layer2/aws_network_second.parquet` and `bsc/layer2/aws_network_second.parquet`
hold 1,814,400 rows each, one per second from 1 October 2026 up to 22 October 2026 UTC.
The Base table covers 907,200 blocks and 171,136,289 transactions. The BSC table covers
4,029,478 blocks and 336,224,798 transactions. Base produces a block about every two
seconds, so zero seconds are normal; a one-second bin gives no arrival time inside a block.

`base/layer2/uniswap_v2_weth_usdc_pool_second.parquet` holds 1,814,400 rows for pool
`0x88a43bbdf9d098eec7bceda4e2494615dfd9bb9c`. It covers this one pool, so it is not chain
TVL, DEX volume or application revenue. USDC values are not USD values, and input fees are
not protocol income. Fee fields are integer wei stored as `decimal128`.
