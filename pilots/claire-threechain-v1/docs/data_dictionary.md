# Implemented data dictionary

Generated from the Arrow schemas in `claire_demo/schemas.py`, `decode.py`, `events.py` and `provenance.py`. Each nullable field preserves unknown information; absence is never automatically zero. Raw RPC JSON remains authoritative and retains fields beyond these normalized views. Amounts and gas-related integers use exact strings where declared.

## blocks

One returned block, including explicitly marked boundary guards.

| Field | Arrow type | Encoding / meaning |
|---|---|---|
| `chain` | `string` | native Arrow scalar; Short chain label: solana, bsc or base. |
| `chain_id` | `string` | native Arrow scalar; Network-qualified namespace; addresses are never global identities. |
| `parser_version` | `string` | native Arrow scalar; Version of normalization code that generated this row. |
| `raw_ref` | `string` | native Arrow scalar; Relative raw file plus JSON pointer for evidence lookup. |
| `block_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `height` | `int64` | native Arrow scalar; Chain-native block index; see slot separately on Solana. |
| `slot` | `int64` | native Arrow scalar; Solana slot, not an EVM block height. |
| `hash` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `parent_hash` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `parent_slot` | `int64` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `block_time` | `int64` | native Arrow scalar; Block timestamp in UTC Unix seconds; null means unknown. |
| `time_status` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `tx_count` | `int64` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `finality_status` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `window_membership` | `string` | native Arrow scalar; main or boundary; only main records enter analytical population. |

## transactions

One main-window transaction in chain order, including failures and unknowns.

| Field | Arrow type | Encoding / meaning |
|---|---|---|
| `chain` | `string` | native Arrow scalar; Short chain label: solana, bsc or base. |
| `chain_id` | `string` | native Arrow scalar; Network-qualified namespace; addresses are never global identities. |
| `parser_version` | `string` | native Arrow scalar; Version of normalization code that generated this row. |
| `raw_ref` | `string` | native Arrow scalar; Relative raw file plus JSON pointer for evidence lookup. |
| `tx_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `block_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `tx_hash_or_signature` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `tx_index` | `int64` | native Arrow scalar; Transaction position within its block. |
| `block_time` | `int64` | native Arrow scalar; Block timestamp in UTC Unix seconds; null means unknown. |
| `tx_version` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `tx_type` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `execution_status` | `string` | native Arrow scalar; Recorded transaction execution success, failed, or unknown. |
| `error_raw` | `string` | canonical JSON string; Chain-native field; retain null when unavailable. |
| `fee_raw` | `string` | decimal integer string; Exact native-asset fee integer, not a floating-point amount. |
| `fee_asset_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `decode_status` | `string` | native Arrow scalar; Parser recognition status; unknown or unsupported does not remove raw data. |
| `execution_meta_status` | `string` | enum: provided / explicit_null / missing / invalid / not_applicable; Whether execution metadata was provided, explicit_null, missing or invalid. |
| `inner_instructions_status` | `string` | enum: provided / explicit_null / missing / invalid / not_applicable; Solana array availability: provided, explicit_null, missing or invalid; EVM not_applicable. |
| `log_messages_status` | `string` | enum: provided / explicit_null / missing / invalid / not_applicable; Solana log array availability: provided, explicit_null, missing or invalid; EVM not_applicable. |
| `is_vote` | `bool` | native Arrow scalar; Whether the transaction was identified as Solana vote traffic. |
| `is_system` | `bool` | native Arrow scalar; Whether the transaction was identified as chain system traffic. |

## transaction_accounts

One recorded transaction/account/role association, not a person.

| Field | Arrow type | Encoding / meaning |
|---|---|---|
| `chain` | `string` | native Arrow scalar; Short chain label: solana, bsc or base. |
| `chain_id` | `string` | native Arrow scalar; Network-qualified namespace; addresses are never global identities. |
| `parser_version` | `string` | native Arrow scalar; Version of normalization code that generated this row. |
| `raw_ref` | `string` | native Arrow scalar; Relative raw file plus JSON pointer for evidence lookup. |
| `tx_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `account_index` | `int64` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `account_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `role` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `is_signer` | `bool` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `is_writable` | `bool` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `role_source` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |

## evm_transaction_details

One EVM transaction's native envelope and receipt fields.

| Field | Arrow type | Encoding / meaning |
|---|---|---|
| `chain` | `string` | native Arrow scalar; Short chain label: solana, bsc or base. |
| `chain_id` | `string` | native Arrow scalar; Network-qualified namespace; addresses are never global identities. |
| `parser_version` | `string` | native Arrow scalar; Version of normalization code that generated this row. |
| `raw_ref` | `string` | native Arrow scalar; Relative raw file plus JSON pointer for evidence lookup. |
| `tx_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `from_account` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `to_account` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `nonce` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `value_raw` | `string` | decimal integer string; Chain-native field; retain null when unavailable. |
| `input_hex` | `string` | native Arrow scalar; Uninterpreted EVM transaction input bytes as hexadecimal. |
| `gas_limit` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `gas_used` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `effective_gas_price` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `contract_created` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |

## evm_logs

One emitted EVM log in a returned receipt.

| Field | Arrow type | Encoding / meaning |
|---|---|---|
| `chain` | `string` | native Arrow scalar; Short chain label: solana, bsc or base. |
| `chain_id` | `string` | native Arrow scalar; Network-qualified namespace; addresses are never global identities. |
| `parser_version` | `string` | native Arrow scalar; Version of normalization code that generated this row. |
| `raw_ref` | `string` | native Arrow scalar; Relative raw file plus JSON pointer for evidence lookup. |
| `log_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `tx_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `block_time` | `int64` | native Arrow scalar; Block timestamp in UTC Unix seconds; null means unknown. |
| `log_index` | `int64` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `emitter` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `topics` | `string` | canonical JSON string; JSON array of EVM log topics in original order. |
| `data_hex` | `string` | native Arrow scalar; Uninterpreted EVM log data bytes as hexadecimal. |
| `removed` | `bool` | native Arrow scalar; Chain-native field; retain null when unavailable. |

## solana_instructions

One top-level or inner Solana instruction; ordering is preserved.

| Field | Arrow type | Encoding / meaning |
|---|---|---|
| `chain` | `string` | native Arrow scalar; Short chain label: solana, bsc or base. |
| `chain_id` | `string` | native Arrow scalar; Network-qualified namespace; addresses are never global identities. |
| `parser_version` | `string` | native Arrow scalar; Version of normalization code that generated this row. |
| `raw_ref` | `string` | native Arrow scalar; Relative raw file plus JSON pointer for evidence lookup. |
| `instruction_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `tx_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `block_time` | `int64` | native Arrow scalar; Block timestamp in UTC Unix seconds; null means unknown. |
| `outer_index` | `int64` | native Arrow scalar; Top-level Solana instruction index. |
| `inner_index` | `int64` | native Arrow scalar; Inner-instruction position; null for top-level instruction. |
| `stack_height` | `int64` | native Arrow scalar; Recorded invocation depth when available. |
| `program_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `account_indices` | `string` | canonical JSON string; JSON array of native Solana account-key indices. |
| `account_ids` | `string` | canonical JSON string; JSON array of resolved chain-qualified account identifiers. |
| `data_raw` | `string` | native Arrow scalar; Uninterpreted Solana instruction data, preserving representation. |
| `decode_status` | `string` | native Arrow scalar; Parser recognition status; unknown or unsupported does not remove raw data. |

## balance_observations

One account/asset balance observation around a transaction; not a transfer.

| Field | Arrow type | Encoding / meaning |
|---|---|---|
| `chain` | `string` | native Arrow scalar; Short chain label: solana, bsc or base. |
| `chain_id` | `string` | native Arrow scalar; Network-qualified namespace; addresses are never global identities. |
| `parser_version` | `string` | native Arrow scalar; Version of normalization code that generated this row. |
| `raw_ref` | `string` | native Arrow scalar; Relative raw file plus JSON pointer for evidence lookup. |
| `tx_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `account_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `asset_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `owner_address` | `string` | native Arrow scalar; Recorded token-account owner when available; distinct from owning program. |
| `owner_status` | `string` | native Arrow scalar; Evidence/availability status of the owner field. |
| `pre_amount_raw` | `string` | decimal integer string; Exact balance before the transaction, if recorded. |
| `post_amount_raw` | `string` | decimal integer string; Exact balance after the transaction, if recorded. |
| `decimals` | `int64` | native Arrow scalar; Recorded asset precision; null is unknown, not zero decimals. |
| `source_kind` | `string` | native Arrow scalar; Kind of native observation supporting the balance row. |

## objects

One chain-qualified object observation within a block partition; the same object_id can occur in multiple partitions.

| Field | Arrow type | Encoding / meaning |
|---|---|---|
| `chain` | `string` | native Arrow scalar; Short chain label: solana, bsc or base. |
| `chain_id` | `string` | native Arrow scalar; Network-qualified namespace; addresses are never global identities. |
| `parser_version` | `string` | native Arrow scalar; Version of normalization code that generated this row. |
| `raw_ref` | `string` | native Arrow scalar; Relative raw file plus JSON pointer for evidence lookup. |
| `object_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `address_or_pool_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `object_type` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `type_evidence` | `string` | native Arrow scalar; Recorded basis for an object-type interpretation. |
| `observed_at` | `int64` | native Arrow scalar; UTC Unix seconds of this object's row-level observation, using its block timestamp; null means unknown. This may be later than first_seen_in_window. |
| `first_seen_in_window` | `int64` | native Arrow scalar; Minimum non-null observed_at across the entire main window for this chain-qualified object_id; repeated consistently on its observation rows. Not lifetime creation time. |
| `token_standard` | `string` | native Arrow scalar; Supported token-standard evidence, if available. |
| `decimals` | `int64` | native Arrow scalar; Recorded asset precision; null is unknown, not zero decimals. |
| `metadata_status` | `string` | native Arrow scalar; Availability of metadata; absent metadata is not an empty description. |

## object_relations

One evidence-backed relationship between observed objects.

| Field | Arrow type | Encoding / meaning |
|---|---|---|
| `chain` | `string` | native Arrow scalar; Short chain label: solana, bsc or base. |
| `chain_id` | `string` | native Arrow scalar; Network-qualified namespace; addresses are never global identities. |
| `parser_version` | `string` | native Arrow scalar; Version of normalization code that generated this row. |
| `raw_ref` | `string` | native Arrow scalar; Relative raw file plus JSON pointer for evidence lookup. |
| `relation_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `subject_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `predicate` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `object_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `evidence_ref` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `observed_at` | `int64` | native Arrow scalar; Evidence observation timestamp; not necessarily effective start time. |
| `effective_time_status` | `string` | native Arrow scalar; Whether the relation's historical effective time is known. |
| `relation_status` | `string` | native Arrow scalar; Evidence and uncertainty of the asserted relation. |

## decoded_records

One attempted or recognized decode of a chain-native record.

| Field | Arrow type | Encoding / meaning |
|---|---|---|
| `chain_id` | `string` | native Arrow scalar; Network-qualified namespace; addresses are never global identities. |
| `record_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `source_record_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `equivalent_source_record_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `tx_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `decoder_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `decoder_version` | `string` | native Arrow scalar; Version of the rule/layout that interpreted the native record. |
| `record_type` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `decoded_arguments` | `string` | JSON string; Chain-native field; retain null when unavailable. |
| `execution_effect` | `string` | native Arrow scalar; committed, not_committed or unknown; attempts are not state changes. |
| `decode_status` | `string` | native Arrow scalar; Parser recognition status; unknown or unsupported does not remove raw data. |
| `raw_ref` | `string` | native Arrow scalar; Relative raw file plus JSON pointer for evidence lookup. |
| `block_time` | `int64` | native Arrow scalar; Block timestamp in UTC Unix seconds; null means unknown. |

## asset_movements

One decoded or candidate movement, with execution and token-standard status.

| Field | Arrow type | Encoding / meaning |
|---|---|---|
| `chain_id` | `string` | native Arrow scalar; Network-qualified namespace; addresses are never global identities. |
| `movement_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `tx_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `asset_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `from_account` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `to_account` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `amount_raw` | `string` | exact decimal integer string; Chain-native field; retain null when unavailable. |
| `movement_type` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `evidence_type` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `execution_effect` | `string` | native Arrow scalar; committed, not_committed or unknown; attempts are not state changes. |
| `source_record_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `standard_status` | `string` | native Arrow scalar; Token-standard evidence; candidates differ from verified fungible tokens. |
| `raw_ref` | `string` | native Arrow scalar; Relative raw file plus JSON pointer for evidence lookup. |
| `decimals` | `int64` | native Arrow scalar; Recorded asset precision; null is unknown, not zero decimals. |
| `block_time` | `int64` | native Arrow scalar; Block timestamp in UTC Unix seconds; null means unknown. |

## platform_records

One recognized or attempted platform operation, preserving attribution evidence.

| Field | Arrow type | Encoding / meaning |
|---|---|---|
| `chain_id` | `string` | native Arrow scalar; Network-qualified namespace; addresses are never global identities. |
| `platform_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `source_record_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `tx_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `object_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `operation_type` | `string` | native Arrow scalar; Decoded platform operation; not a raw sampling rule. |
| `decoder_version` | `string` | native Arrow scalar; Version of the rule/layout that interpreted the native record. |
| `attribution_evidence` | `string` | JSON string; JSON of address/layout provenance and historical uncertainty. |
| `execution_effect` | `string` | native Arrow scalar; committed, not_committed or unknown; attempts are not state changes. |
| `decode_status` | `string` | native Arrow scalar; Parser recognition status; unknown or unsupported does not remove raw data. |
| `raw_ref` | `string` | native Arrow scalar; Relative raw file plus JSON pointer for evidence lookup. |
| `block_time` | `int64` | native Arrow scalar; Block timestamp in UTC Unix seconds; null means unknown. |
| `block_number_or_slot` | `int64` | native Arrow scalar; Canonical within-chain order key, retained when timestamps tie. |
| `tx_index` | `int64` | native Arrow scalar; Transaction position within its block. |
| `event_order` | `int64` | native Arrow scalar; Chain-native field; retain null when unavailable. |

## platform_registry

One registered platform contract/program and source layout definition.

| Field | Arrow type | Encoding / meaning |
|---|---|---|
| `platform_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `chain_id` | `string` | native Arrow scalar; Network-qualified namespace; addresses are never global identities. |
| `program_or_contract` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `version` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `source_url` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `source_revision` | `string` | native Arrow scalar; Pinned source revision or content identifier for the layout. |
| `verification_status` | `string` | native Arrow scalar; Exactly what the evidence verifies, such as address bytes only. |
| `layout_path` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `valid_from_block` | `int64` | native Arrow scalar; Known effective lower bound; null means historically unknown. |
| `valid_to_block` | `int64` | native Arrow scalar; Known effective upper bound; null does not prove indefinite validity. |

## crosschain_links

One same-address-bytes relation, without inferred common identity.

| Field | Arrow type | Encoding / meaning |
|---|---|---|
| `link_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `left_object_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `right_object_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `relation_type` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `evidence_ref` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `verification_status` | `string` | native Arrow scalar; Exactly what the evidence verifies, such as address bytes only. |
| `uncertainty_reason` | `string` | native Arrow scalar; Limit on the relation or identity claim. |
| `observed_at` | `int64` | native Arrow scalar; Evidence observation timestamp; not necessarily effective start time. |

## events

One versioned researcher-defined event with source evidence and parameters.

| Field | Arrow type | Encoding / meaning |
|---|---|---|
| `event_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `event_type` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `definition_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `definition_version` | `string` | native Arrow scalar; Version of the event rule applied to fixed source facts. |
| `chain_id` | `string` | native Arrow scalar; Network-qualified namespace; addresses are never global identities. |
| `subject_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `event_time` | `string` | native Arrow scalar; UTC time derived from block time, not lifetime first activity. |
| `evidence_record_ids` | `string` | JSON string; JSON array of supporting chain-native record identifiers. |
| `parameters` | `string` | JSON string; JSON rule parameters, editable separately from raw records. |
| `observation_window` | `string` | JSON string; JSON bounded interval used by the event definition. |
| `coverage_status` | `string` | native Arrow scalar; Observation-scope qualification, not complete lifecycle coverage. |
| `tx_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `platform_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `event_order` | `int64` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `block_time` | `int64` | native Arrow scalar; Block timestamp in UTC Unix seconds; null means unknown. |
| `block_number_or_slot` | `int64` | native Arrow scalar; Canonical within-chain order key, retained when timestamps tie. |
| `threshold` | `int64` | native Arrow scalar; Required distinct successful trade transaction count. |

## provenance_requests

One acquisition request with source, timing, outcome and context evidence.

| Field | Arrow type | Encoding / meaning |
|---|---|---|
| `source_id` | `string` | native Arrow scalar; Stable chain-qualified identifier. |
| `endpoint` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `rpc_method` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `request_params` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `requested_at` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `retrieved_at` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `chain_id` | `string` | native Arrow scalar; Network-qualified namespace; addresses are never global identities. |
| `response_status` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `raw_response_status` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `error_code` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `raw_path` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `raw_sha256` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `ledger_raw_sha256` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `raw_integrity` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `block_hash` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `block_context_source` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `block_context_status` | `string` | native Arrow scalar; resolved, requested_only, unknown or conflict; a requested height alone does not prove a returned block. |
| `parser_issues` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `provenance_parser_version` | `string` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `block_number_or_slot` | `int64` | native Arrow scalar; Canonical within-chain order key, retained when timestamps tie. |
| `response_context_slot` | `int64` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `retry_count` | `int64` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `http_status` | `int64` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `ledger_line` | `int64` | native Arrow scalar; Chain-native field; retain null when unavailable. |
| `request_params_redacted` | `bool` | native Arrow scalar; Chain-native field; retain null when unavailable. |

## Decoded and event layers

`tables/decoded/platform_records` has one recognized or attempted platform operation with source record ID, transaction ID, token/object ID, operation type, decoder version, attribution evidence, execution effect, decode status and order. Historical registry completeness is separately qualified.

`tables/decoded/asset_movements` has one candidate or recognized movement with asset, source/target accounts, exact amount, decimals, movement type, evidence type, execution effect, token-standard status and raw reference. Candidate records remain inspectable but are not automatically included in the token graph example.

`tables/decoded/crosschain_links` holds literal BSC/Base address-byte equality links. Verification status concerns bytes only, not common identity, ownership or funds flow.

`tables/events/events.parquet` has one derived event: `event_id`, `event_type`, `definition_id`, `definition_version`, `chain_id`, `subject_id`, `event_time`, `event_order`, `evidence_record_ids`, `parameters`, `observation_window`, `coverage_status`, `tx_id`, `platform_id`, `block_time`, `threshold`. Threshold events use distinct committed trade transactions; native lifecycle observations retain their own definition IDs.

## Provenance and capabilities

`provenance/request_log.jsonl` records method, parameters, source, retrieval timing, result/error and raw reference as implemented by acquisition. `reports/preflight.json` and `reports/coverage.csv` distinguish source capability from actual retrieved coverage. Trace and arbitrary historical state are not implied by core transaction completeness.
