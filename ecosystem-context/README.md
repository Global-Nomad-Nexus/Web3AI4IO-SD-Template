# Ecosystem context v1

Market, network, news, mechanism and macroeconomic context for Solana, Base and BSC.
The release contains 30 tables (27 CSV and 3 Parquet) described by 50 chain-specific inventory entries.
Shared market and macroeconomic tables are stored once in `data/shared/layer5/`.

Start with [the data guide](data/README.md) and [the inventory](metadata/inventory.csv).
See `reproduce/README.md` for the two offline commands that regenerate all released tables.
Field meanings, units and missing values are in [the field dictionary](metadata/fields.csv).

The module runs independently from the parent repository's tutorials and pipeline.
Its upstream baseline is `Global-Nomad-Nexus/Web3AI4IO-SD-Template`, branch
`shilin_v2`, commit `379fa57b7a29d1a69693ab3b8d17f3943933acb8`.

Download or clone this branch to obtain the data and frozen reproduction inputs.
Second-level files cover SOL/USDT (1–24 October 2026), ETH/USDC and BNB/USDC
(1–21 October 2026), with prices, volume, trade counts, returns and trailing 24-hour volatility.
The current module occupies about 310 MB.

Three further local tables cover Base/BSC network activity and one Base pool.
Their data remain outside this public package pending provider-specific redistribution
conditions; [the availability list](metadata/not-released.csv) describes their scope.

See [source attribution and conditions](metadata/SOURCES.md) for data use.
