# Shilin pilot data dictionary

Every identifier is scoped to the fixed Claire release. UTC strings end in `Z`. A missing value means unknown or unavailable, never a numeric zero. `creation` means a supported decoded platform creation event in this five-minute snapshot, not a complete platform launch universe.

| File | One row represents | Primary key | Important fields and meaning |
|---|---|---|---|
| `onchain_launch_cohort.parquet` | One committed, decoded creation event | `launch_record_id` | `chain_id` and `object_id` form a chain-qualified token reference; `creation_source_record_id` and `creation_raw_ref` locate Claire's native evidence; `metadata_uri_declared` comes from decoded Pump `CreateEvent.uri`; `chain_event_time_unix` is block time, not retrieval time. |
| `offchain_requests.jsonl` | One HTTP attempt, including a failed attempt and a retry | `request_id` | `original_uri` is the exact chain declaration; `resolved_url` is the gateway/endpoint actually contacted; `requested_at_utc`, `retrieved_at_utc`, status, code, redirects, response hash and byte count are acquisition evidence. Public release omits local raw-response paths. |
| `offchain_snapshots.parquet` | One selected successful response for a distinct URI | `snapshot_id` | `raw_sha256` fixes retrieved bytes; `parse_status` distinguishes a JSON object from errors; `cid_integrity_status` says whether a CIDv1 raw/sha2-256 digest was checked, CIDv0 DAG-PB was not checked, or the URI was not IPFS. `raw_redistribution_status=not_cleared` means raw bytes are not in this release. |
| `offchain_declarations.parquet` | One website, X/Twitter or Telegram field observed in a JSON response | `declaration_id` | `snapshot_id`, `field_name`, `json_pointer`, `raw_value`, `target_class`, and `first_verified_at_utc` retain the exact field and observation time. A `twitter` field may link to a post rather than an account; a `website` field may link to a social site. The field is a *declaration*, not independent proof of website ownership. |
| `linkage_candidates.parquet` | One candidate pair from exact on-chain URI or metadata field | `candidate_id` | `candidate_rule` names the generation rule; `status` describes the decision on that typed declaration. `source_uri` and `parent_candidate_id` trace a URL-field candidate through the original chain-declared URI candidate. |
| `linkage_evidence.parquet` | One source item supporting a candidate | `evidence_id` | `raw_ref` locates Claire's on-chain record or `snapshot_id` and `field_pointer` locate a JSON field; `polarity` is support or contradiction. |
| `linkage_assertions.parquet` | One typed, evidence-backed assertion | `assertion_id` | `object_id`, `relation_type`, `right_value`, `evidence_ids`, `chain_event_time_utc`, `first_verified_at_utc`, `as_of_eligibility`. The linked declaration table carries `target_class`. Relation names describe the *source field* (`declares_twitter_field_url`, etc.), not verified account ownership or target type. A metadata URL observed after creation has `as_of_eligibility=unknown`, even if it is content-addressed, because external website state was not observed then. |
| `coverage_ledger.parquet` | One eligible creation event and its off-chain outcome | `launch_record_id` | `coverage_state` separates declaration observed, no link field, request or parse failure, access restriction and not attempted. |
| `fourmeme_probe.json` | One exact BSC address API probe | `(launch_record_id, endpoint)` | Query parameter is the full contract address. HTTP 403 is `access_restricted_here`, not evidence that the token lacks a platform record. |

The release also includes `cohort_report.json`, `processing_report.json`, `validation.json`, `validation_report.md`, `rights_sources.csv`, and `release_manifest.json`. Candidate and assertion IDs are deterministic hashes of typed source identifiers. Snapshot IDs depend on the request ID and response digest; repeat retrievals intentionally create new observations.

## Missingness and time rules

- `no_declaration`: a retrieved, parseable metadata JSON object lacks the covered link fields. It does not prove there was never a website or account.
- `not_attempted`: no request was made for the event's exact source in this run.
- `access_restricted_here`: the tested endpoint blocked this research environment. Other access routes or authorized archival access may exist.
- `as_of_eligibility=creation_record_only`: the creation transaction itself contains the URI.
- `as_of_eligibility=unknown`: a later retrieved metadata response supports the field at retrieval, but does not establish historical website/account state.

Neither `same_address_bytes` in Claire's release nor the same name, symbol, domain or account is evidence of a common person or owner.
