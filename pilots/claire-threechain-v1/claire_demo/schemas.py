"""Versioned, typed Arrow interfaces for the evidence-preserving base layer.

JSON-valued columns contain compact, sorted-key JSON strings, never Python repr.
All raw amount and gas fields are decimal integer strings: this accommodates
uint256 and arbitrary token precision without silently coercing to float.
"""
import pyarrow as pa

PARSER_VERSION = "claire-base/1.2.0"
CHAIN_IDS = {"solana": "solana:mainnet", "bsc": "eip155:56", "base": "eip155:8453"}
S, I, B = pa.string(), pa.int64(), pa.bool_()
COMMON = [("chain", S), ("chain_id", S), ("parser_version", S), ("raw_ref", S)]
FIELDS = {
    "blocks": [("block_id", S), ("height", I), ("slot", I), ("hash", S), ("parent_hash", S),
               ("parent_slot", I), ("block_time", I), ("time_status", S), ("tx_count", I),
               ("finality_status", S), ("window_membership", S)],
    "transactions": [("tx_id", S), ("block_id", S), ("tx_hash_or_signature", S), ("tx_index", I),
                     ("block_time", I), ("tx_version", S), ("tx_type", S), ("execution_status", S),
                     ("error_raw", S), ("fee_raw", S), ("fee_asset_id", S), ("decode_status", S),
                     ("execution_meta_status", S), ("inner_instructions_status", S), ("log_messages_status", S),
                     ("is_vote", B), ("is_system", B)],
    "transaction_accounts": [("tx_id", S), ("account_index", I), ("account_id", S), ("role", S),
                             ("is_signer", B), ("is_writable", B), ("role_source", S)],
    "evm_transaction_details": [("tx_id", S), ("from_account", S), ("to_account", S), ("nonce", S),
                                ("value_raw", S), ("input_hex", S), ("gas_limit", S), ("gas_used", S),
                                ("effective_gas_price", S), ("contract_created", S)],
    "evm_logs": [("log_id", S), ("tx_id", S), ("block_time", I), ("log_index", I), ("emitter", S),
                 ("topics", S), ("data_hex", S), ("removed", B)],
    "solana_instructions": [("instruction_id", S), ("tx_id", S), ("block_time", I),
                            ("outer_index", I), ("inner_index", I), ("stack_height", I),
                            ("program_id", S), ("account_indices", S), ("account_ids", S),
                            ("data_raw", S), ("decode_status", S)],
    "balance_observations": [("tx_id", S), ("account_id", S), ("asset_id", S), ("owner_address", S),
                             ("owner_status", S), ("pre_amount_raw", S), ("post_amount_raw", S),
                             ("decimals", I), ("source_kind", S)],
    "objects": [("object_id", S), ("address_or_pool_id", S), ("object_type", S), ("type_evidence", S),
                ("observed_at", I), ("first_seen_in_window", I), ("token_standard", S), ("decimals", I), ("metadata_status", S)],
    "object_relations": [("relation_id", S), ("subject_id", S), ("predicate", S), ("object_id", S),
                         ("evidence_ref", S), ("observed_at", I), ("effective_time_status", S),
                         ("relation_status", S)],
}
SCHEMAS = {name: pa.schema(COMMON + fields, metadata={b"parser_version": PARSER_VERSION.encode()})
           for name, fields in FIELDS.items()}
BASE_SCHEMAS = SCHEMAS
JSON_FIELDS = {"transactions": ["error_raw"], "evm_logs": ["topics"],
               "solana_instructions": ["account_indices", "account_ids", "data_raw (parsed instructions only)"]}


def schema_dictionary():
    """Machine-readable dictionary used by docs, validation and notebooks."""
    return {
        name: [{"name": field.name, "type": str(field.type), "nullable": True,
                "description": ("Block timestamp of this evidence observation; null when unavailable." if name == "objects" and field.name == "observed_at" else
                                "Minimum non-null observed_at for this object_id across all main-window observations; null when all times are unknown. Missing block times prevent complete-window acceptance." if name == "objects" and field.name == "first_seen_in_window" else None),
                "encoding": ("enum: provided / explicit_null / missing / invalid / not_applicable" if field.name in
                             ("execution_meta_status", "inner_instructions_status", "log_messages_status") else
                             "canonical JSON string" if field.name in JSON_FIELDS.get(name, []) else
                             "decimal integer string" if field.name.endswith("_raw") and field.name != "error_raw"
                             and field.name != "data_raw" else "native Arrow scalar")}
               for field in schema]
        for name, schema in SCHEMAS.items()
    }


def object_id(chain, address):
    return f"{CHAIN_IDS[chain]}:{address}" if address is not None else None


def transaction_id(chain, signature):
    return f"{CHAIN_IDS[chain]}:tx:{signature}"
