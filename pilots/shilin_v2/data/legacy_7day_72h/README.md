# Original seven days + 72-hour follow-up

All six original CSV tables. The cohort contains 4,668 events; 18,672 planned checkpoints all have terminal states. Original validation remains INCOMPLETE because four chain transactions were unresolved.

| Table | Rows | Storage |
|---|---:|---|
| `coverage_ledger` | 18,672 | [1 gzip CSV shard(s)](coverage_ledger/) |
| `field_observations` | 133,888 | [1 gzip CSV shard(s)](field_observations/) |
| `launch_events` | 4,668 | [1 gzip CSV shard(s)](launch_events/) |
| `observation_plan` | 18,672 | [1 gzip CSV shard(s)](observation_plan/) |
| `request_attempts` | 60,779 | [1 gzip CSV shard(s)](request_attempts/) |
| `response_snapshots` | 16,744 | [1 gzip CSV shard(s)](response_snapshots/) |

[Data catalogue](../../docs/TABLES.md) · [Exact original paths, columns and hashes](../../metadata/tables.json) · [Restore and reproduce](../../docs/REPRODUCE.md)
