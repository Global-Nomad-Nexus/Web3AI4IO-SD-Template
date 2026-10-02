# MVP data dictionary

| Table | Primary key | Meaning |
|---|---|---|
| `launch_events.csv` | `event_key` | Successful Pump.fun creation events. Live mode enrolls them during the 24 hours after collection start. Fixture mode keeps events inside the protocol window. |
| `observation_plan.csv` | `event_key, checkpoint` | Required T0/T+24h/T+60h schedule. T+24h ends the 24-hour collection. T+60h is 36 hours of follow-up observation later. Live checkpoints are anchored to collection start. Fixture checkpoints are anchored to `block_time`. |
| `request_attempts.csv` | `request_id, attempt` | Every attempt, including retries, policy refusals, and failures. `uri` is the declared value. `request_url` and `route_id` identify the route that was actually called. |
| `response_snapshots.csv` | `request_id` | Hash, size, content type and parse state for responses that returned a body. |
| `field_observations.csv` | `request_id, field_name` | Fixed JSON pointer, presence, type and publication-safe value/hash. |
| `coverage_ledger.csv` | `event_key, checkpoint` | Terminal event-by-checkpoint state and timing status. |
| `cohort_status.json` | run directory | Rolling-cohort progress. `phase` stays `running` until T+60h has been attempted. A later process resumes while it is not `finished`. |

All timestamps are explicit UTC ISO-8601 values. Missing URI, local or private host, request failure, parse failure and an absent JSON field are separate states.

For `ipfs://` and `ar://` declarations, `uri` remains the original on-chain declaration. A gateway fallback is a separate attempt and does not overwrite that URI. Each attempt is written before the next one starts. A failed checkpoint keeps being retried until T+60h, and then for `max_retry_rounds` more rounds, before the cohort is allowed to finish.
