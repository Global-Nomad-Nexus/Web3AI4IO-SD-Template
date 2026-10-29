# Complete research tables

Both released datasets are preserved without row sampling. Data use lossless gzip CSV shards; each shard has a header and contains complete logical records, including quoted multiline fields.

| Dataset | Logical tables | Start here |
|---|---:|---|
| Original seven-day Pump.fun cohort + 72-hour follow-up | 6 | [Legacy tables](legacy_7day_72h/README.md) |
| Formal three-chain Registry / Polymarket, P3 v6 | 15 | [P3 v6 tables](p3_v6/README.md) |

[Complete catalogue and row counts](../docs/TABLES.md) · [Ordered fields and original hashes](../metadata/tables.json) · [P3 field dictionary](../metadata/data_dictionary.csv) · [Three-chain display preview](../source/2026-10-27/registry_polymarket/p4/figures/real_three_chain_preview.csv)

From the repository root:

```bash
python3 pilots/shilin_v2/tools/data.py list
python3 pilots/shilin_v2/tools/data.py verify --deep
python3 pilots/shilin_v2/tools/data.py restore --output outputs/shilin_v2
```

Do not concatenate decompressed shards directly: that would repeat CSV headers. The restoration tool preserves exact original bytes and verifies full-file SHA-256. Use a new output directory. For direct analysis, read gzip shards with identifiers as strings; if using pandas, `dtype=str, keep_default_na=False` preserves long integer identifiers and original missingness codes.

The complete raw/normalized evidence capsule is separate in the paired GitHub Release. It is optional for analyzing these tables and required for full reconstruction. [Download and reconstruction guide](../docs/REPRODUCE.md).
