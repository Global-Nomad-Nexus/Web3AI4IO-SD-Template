# Claire three-chain real-data pilot

This is the implementation behind the on-chain tutorial at `../../notebooks/01_On_Chain_Tutorial.ipynb`. The original teaching fixture is preserved separately; Shilin and integration are not claimed complete.

## Reproduction

The tutorial downloads a pinned raw-only archive from https://huggingface.co/datasets/global-nomad-nexus/claire-threechain-v1, checks SHA-256, obtains this code at a pinned commit, and rebuilds all tables. It works from an empty directory. Full precomputed data is also supplied on Hugging Face. See the tutorial for selection rationale, two editable Mermaid diagrams, source metadata, step explanations and actual outputs.

## Stage entry points

From this folder, with requirements installed: `python -m claire_demo --root /absolute/path/to/workdir STAGE`.

| Stage | Inputs and outputs | Check |
|---|---|---|
| preflight, resolve_window, collect | Free RPC and UTC interval → raw JSON and request receipts | Core capability, every block/receipt/meta, guards and retry lineage |
| provenance | Request ledger → typed request table | Failed and successful requests remain visible |
| normalize | Raw → base Parquet | Native units, chain IDs, nulls, source references |
| decode | Base + pinned sources → decoded Parquet | Unknown layouts/effects explicit |
| derive_events | Decoded facts → separate event table | Thresholds 1/3; raw/base unchanged |
| validate | Raw and derived layers → manifest and checks | Complete range/identity/precision/provenance checks |
| visualize | Tables → Mermaid and CSV | Descriptive scope, clipped display only |

The implementation never defines the raw population using selected platform events. Raw RPC envelopes preserve unknown fields. `docs/data_dictionary.md` defines table units/types; `config/platform_registry.json` pins sources. Reports in this checkout describe the original local baseline, with their own scope and dates. New notebook-run receipts are separate.

## Data and limitations

Whole-chain five-minute window: 2026-09-14 12:00:00–12:05:00 UTC, end exclusive, Solana/BSC/Base. Main 1,759 blocks / 1,253,955 transactions, no first-N cap. BSC traces and arbitrary historical state are not complete. Clanker trade attribution has limited pool evidence; zero recognized trades is not zero activity. Address-byte matches are not identity links. See `docs/limitations.md`.

Small descriptive CSVs here are inspection products, not the complete raw dataset. Complete inputs and processed data are on Hugging Face. Existing source notices are retained; code licensing does not confer a blanket license on external records.

## Verified public runs

[Local and hosted Colab evidence](docs/release_validation.md) records the complete 14-cell runs. [Selection rationale and citations](docs/data_selection_and_references.md) are supplied separately.
