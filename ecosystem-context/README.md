# Ecosystem context v1

Market, network, news, mechanism and macroeconomic context for Solana, Base and BSC.
The release contains 33 tables (27 CSV and 6 Parquet) described by 53 chain-specific inventory entries.
Shared market and macroeconomic tables are stored once in `data/shared/layer5/`.

Start with [the data guide](data/README.md) and [the inventory](metadata/inventory.csv).
See `reproduce/README.md` for the two offline commands that regenerate the 30 CSV and exchange-market tables, and the evidence for the three AWS-derived tables.
Field meanings, units and missing values are in [the field dictionary](metadata/fields.csv).

The module runs independently from the parent repository's tutorials and pipeline.
Its upstream baseline is `Global-Nomad-Nexus/Web3AI4IO-SD-Template`, branch
`shilin_v2`, commit `17bd1270aad5dfffe24ed7393e8aa177b57b1ce2`.

Download or clone this branch to obtain the data and frozen reproduction inputs.
Second-level files cover SOL/USDT (1–24 October 2026), ETH/USDC and BNB/USDC
(1–21 October 2026), with prices, volume, trade counts, returns and trailing 24-hour volatility.
The module occupies about 480 MB.

Second-level AWS-derived tables cover Base network activity, BSC network activity and
one Base Uniswap V2 WETH/USDC pool for 1 to 21 October 2026.

See [source attribution and conditions](metadata/SOURCES.md) for data use.
