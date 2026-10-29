# P3 v6 formal three-chain tables

All 15 logical tables. The declared platform scope contains 367,373 tokens. Registry and creation_events have identical original bytes, so one physical copy serves both logical views. Restoration recreates both original filenames.

| Table | Rows | Storage |
|---|---:|---|
| `context_daily` | 266 | [1 gzip CSV shard(s)](context_daily/) |
| `creation_events` | 367,373 | [Exact alias of registry](registry/) |
| `metadata_coverage` | 18,672 | [1 gzip CSV shard(s)](metadata_coverage/) |
| `metadata_observations` | 133,888 | [2 gzip CSV shard(s)](metadata_observations/) |
| `pm_activity` | 60 | [1 gzip CSV shard(s)](pm_activity/) |
| `pm_candidate_catalogue` | 445 | [1 gzip CSV shard(s)](pm_candidate_catalogue/) |
| `pm_mapping` | 28 | [1 gzip CSV shard(s)](pm_mapping/) |
| `pm_markets` | 60 | [1 gzip CSV shard(s)](pm_markets/) |
| `pm_match_status` | 6,156,902 | [20 gzip CSV shard(s)](pm_match_status/) |
| `pm_outcomes` | 120 | [1 gzip CSV shard(s)](pm_outcomes/) |
| `pm_prices` | 175,054 | [2 gzip CSV shard(s)](pm_prices/) |
| `registry` | 367,373 | [10 gzip CSV shard(s)](registry/) |
| `token_expectations_at_creation` | 6,156,902 | [43 gzip CSV shard(s)](token_expectations_at_creation/) |
| `token_id_crosswalk` | 4,668 | [1 gzip CSV shard(s)](token_id_crosswalk/) |
| `token_metadata_status` | 367,373 | [2 gzip CSV shard(s)](token_metadata_status/) |

[Data catalogue](../../docs/TABLES.md) · [Exact original paths, columns and hashes](../../metadata/tables.json) · [Restore and reproduce](../../docs/REPRODUCE.md)
