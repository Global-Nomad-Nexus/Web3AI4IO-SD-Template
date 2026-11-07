# Ecosystem context v1

Market, network, news, mechanism and macroeconomic context for Solana, Base and BSC.
The release contains 31 tables (25 CSV and 6 Parquet) described by 51 chain-specific inventory entries.
Shared market and macroeconomic tables are stored once in `data/shared/layer5/`.

Start with [the data guide](data/README.md) and [the inventory](metadata/inventory.csv).
See `reproduce/README.md` for the three offline commands that regenerate all 31 tables.
Field meanings, units and missing values are in [the field dictionary](metadata/fields.csv).

The module runs independently from the parent repository's tutorials and pipeline.
Its upstream baseline is `Global-Nomad-Nexus/Web3AI4IO-SD-Template`, branch
`shilin_v2`, commit `08b0a8ccbc510f389b2c663e168025130adaf979`.

Download or clone this branch to obtain the data and frozen reproduction inputs.
Second-level files cover SOL/USDT (1–24 October 2026), ETH/USDC and BNB/USDC
(1–21 October 2026), with prices, volume, trade counts, returns and trailing 24-hour volatility.
The AWS-derived tables need 2.31 GB of frozen inputs, published as release assets.
The module occupies about 480 MB.

Second-level AWS-derived tables cover Base network activity, BSC network activity and
one Base Uniswap V2 WETH/USDC pool for 1 to 21 October 2026.

See [source attribution and conditions](metadata/SOURCES.md) for data use.
