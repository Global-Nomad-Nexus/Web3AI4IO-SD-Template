# Ecosystem context v1

Market, network, news, mechanism and macroeconomic context for Solana, Base and BSC.
The release contains 27 CSV tables described by 47 chain-specific inventory entries.
Shared market and macroeconomic tables are stored once in `data/shared/layer5/`.

Start with [the data guide](data/README.md) and [the inventory](metadata/inventory.csv).
The companion reproduce archive supplies `reproduce/README.md` and the workflow to regenerate all tables.
Field meanings, units and missing values are in [the field dictionary](metadata/fields.csv).

The module runs independently from the parent repository's tutorials and pipeline.
Its upstream baseline is `Global-Nomad-Nexus/Web3AI4IO-SD-Template`, branch
`shilin_v2`, commit `c4c9b1427a7ef2fc2eac2ebf6eae10c91dd2d5a3`.

Two companion archives provide the data and reproduction files. Extract both into
the same directory to obtain this module layout. The data archive works on its own
for analysis; reproduction additionally uses the frozen inputs and Python program.

See [source attribution and conditions](metadata/SOURCES.md) for data use.
