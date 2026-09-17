# Shilin v2 bounded extension: data dictionary and claim limits

The extension uses Claire's unchanged five-minute on-chain input through Shilin v1's pinned 116-event cohort. Its additional observations are source requests, field states, and binary-resource receipts. None of these prove project identity, website ownership, or availability at token creation.

| Public release table | Observation unit | Main keys and interpretation |
| --- | --- | --- |
| `metadata_field_audit.parquet` | One of 14 prespecified fields in one of the 57 v1 metadata snapshots | `(snapshot_id, field_name)`; `field_state` distinguishes `absent`, `null`, `empty`, `nonempty`, and `other_type`; `value_sha256` is the digest of the exact string value, if any; `declared_url` is released only for specified URL fields; `url_syntax_valid` checks syntax, not target ownership or availability. |
| `event_metadata_checks.parquet` | One of the 61 Pump creation events | `launch_record_id` joins Claire's event to its v1 metadata URI; `name_exact_match` and `symbol_exact_match` compare literal strings. A mismatch would require review and would not prove fraud. |
| `metadata_refetch.parquet` | One of the 57 distinct v1 metadata URIs | `original_uri` and `v1_snapshot_id`; `same_bytes_as_v1` compares SHA-256 digests when a second response was obtained. `not_attempted` and request failures remain explicit. A same-byte result measures current access and byte stability only. |
| `image_acquisition.parquet` | One distinct image URI declared by the 57 fixed metadata objects | `image_uri` and `source_snapshot_ids`; a request receipt, HTTP status, response SHA-256, media type, and magic-byte class. A successful response does not grant redistribution rights or verify image meaning. |
| `url_semantic_checks.parquet` | One of the 39 v1 URL-field declarations | `declaration_id` joins v1. `semantic_state` identifies profile, post, other web target, or a field/target mismatch needing review; `distinct_token_count_for_url` flags URL reuse. These are automated review flags, not adjudicated identity errors. |
| `event_extension_coverage.parquet` | One of the 116 fixed creation events | `launch_record_id`; preserves v1 coverage while adding metadata-refetch and image-acquisition status. Four.meme rows remain `not_applicable_no_verified_source` for v2. |
| `human_review_queue.parquet` | One selected event awaiting independent review | `launch_record_id`, stratum and pending status; the queue is not a completed annotation, gold standard, precision estimate, or recall estimate. |
| `image_source_rights.csv` | One distinct image-serving hostname | URI count and unresolved raw-binary redistribution status. A gateway host is not necessarily the content owner. |

All normalized request times are UTC. `chain_event_time_utc` belongs to Claire's creation event; `requested_at_utc` and `retrieved_at_utc` belong to later off-chain requests. Do not infer a historical `valid_from` time from a retrieval. When a request fails, response properties and `same_bytes_as_v1` are null rather than false.

Third-party JSON and image response bodies remain in the ignored local cache because redistribution rights are unresolved. The public release provides source URI, request receipt, hashes, field states, and derived comparisons. The fixed v1 release and Claire revision are separate cited inputs, not copied or modified by this extension.
