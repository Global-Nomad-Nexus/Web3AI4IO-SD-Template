# Complete data catalogue

All 21 logical tables are included without row sampling. Exact CSV hashes, original byte lengths, ordered columns, shard hashes and restoration paths are in [`metadata/tables.json`](../metadata/tables.json). The P3 field dictionary contains 251 entries.

| Release | Table | Rows | Grain / use |
|---|---|---:|---|
| p3_v6 | [`context_daily`](../data/p3_v6/context_daily/) | 266 | Daily context anchors and creation activity |
| p3_v6 | [`creation_events`](../metadata/tables.json) | 367,373 | Creation-event view; exact-byte alias of registry |
| p3_v6 | [`metadata_coverage`](../data/p3_v6/metadata_coverage/) | 18,672 | Legacy event × checkpoint coverage and terminal state |
| p3_v6 | [`metadata_observations`](../data/p3_v6/metadata_observations/) | 133,888 | Historical metadata field observations with provenance |
| p3_v6 | [`pm_activity`](../data/p3_v6/pm_activity/) | 60 | Activity snapshot scope |
| p3_v6 | [`pm_candidate_catalogue`](../data/p3_v6/pm_candidate_catalogue/) | 445 | Search catalogue, including nonselected candidates |
| p3_v6 | [`pm_mapping`](../data/p3_v6/pm_mapping/) | 28 | Reviewed chain/platform/economic background mappings |
| p3_v6 | [`pm_markets`](../data/p3_v6/pm_markets/) | 60 | Frozen market snapshots and rule references |
| p3_v6 | [`pm_match_status`](../data/p3_v6/pm_match_status/) | 6,156,902 | Every token × mapping assessment and reason |
| p3_v6 | [`pm_outcomes`](../data/p3_v6/pm_outcomes/) | 120 | Native outcome identities |
| p3_v6 | [`pm_prices`](../data/p3_v6/pm_prices/) | 175,054 | Time-bounded outcome scalar observations |
| p3_v6 | [`registry`](../data/p3_v6/registry/) | 367,373 | One row per token in declared platform scope |
| p3_v6 | [`token_expectations_at_creation`](../data/p3_v6/token_expectations_at_creation/) | 6,156,902 | Strictly earlier information-time alignment |
| p3_v6 | [`token_id_crosswalk`](../data/p3_v6/token_id_crosswalk/) | 4,668 | Legacy-to-formal identity reconciliation |
| p3_v6 | [`token_metadata_status`](../data/p3_v6/token_metadata_status/) | 367,373 | Metadata availability for every formal token |
| legacy_7day_72h | [`coverage_ledger`](../data/legacy_7day_72h/coverage_ledger/) | 18,672 | Required checkpoints and final coverage states |
| legacy_7day_72h | [`field_observations`](../data/legacy_7day_72h/field_observations/) | 133,888 | Original allowed fields and observation states |
| legacy_7day_72h | [`launch_events`](../data/legacy_7day_72h/launch_events/) | 4,668 | Original seven-day creation cohort |
| legacy_7day_72h | [`observation_plan`](../data/legacy_7day_72h/observation_plan/) | 18,672 | T0 / T24 / T48 / T72 schedule |
| legacy_7day_72h | [`request_attempts`](../data/legacy_7day_72h/request_attempts/) | 60,779 | All recorded acquisition attempts |
| legacy_7day_72h | [`response_snapshots`](../data/legacy_7day_72h/response_snapshots/) | 16,744 | Recorded metadata response snapshots |

The original seven-day release manifest and validation report are retained under `source/1021/scientific-data-essential/data/7day-72h-20261008-release/`. Its original manifest also names JSONL files omitted from that older compact release. They were never available in this source package; their absence is documented, not silently filled with new requests.

The frozen original P3 processed manifest remains in `metadata/p3_original_processed_manifest.csv`. This manifest describes original paths/bytes; `metadata/tables.json` describes GitHub storage shards and aliases.

All declared days are UTC, with the half-open creation window `[2026-10-08, 2026-10-15)`. Addresses and identifiers remain strings. Each long-table row is an assessment or observation, not an independent token. The 6,156,902 expectation rows include 5,856,212 valid matches. The 28 mappings supply shared context; direct token-identity mappings number zero.
