"""Offline, one-block-at-a-time normalization without event-based selection.

One Parquet shard is emitted for every table and input block, including typed
empty shards. Object rows retain their own observed_at and evidence; a two-pass
disk-backed reduction adds the same global first_seen_in_window to every row
with that object_id. Unknown observation times are never filled with zero.
"""
from collections import defaultdict
from contextlib import closing
from pathlib import Path
import json
import hashlib
import sqlite3
import tempfile
import pyarrow as pa
import pyarrow.parquet as pq

from .common import load_json, write_json
from .schemas import CHAIN_IDS, PARSER_VERSION, SCHEMAS, object_id, transaction_id

VOTE_PROGRAM = "Vote111111111111111111111111111111111111111"
SYSTEM_PROGRAM = "11111111111111111111111111111111"


def compact(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False) if value is not None else None


def integer(value):
    """Lossless integer parse; absent and malformed remain unknown, never zero."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 16) if value.startswith(("0x", "0X")) else int(value)
        except ValueError:
            return None
    return None


def amount(value):
    parsed = integer(value)
    return str(parsed) if parsed is not None else None


def field_status(container, field, expected_type):
    """Keep an explicit source null distinct from an absent/invalid field."""
    if not isinstance(container, dict) or field not in container:
        return "missing"
    value = container[field]
    return "explicit_null" if value is None else "provided" if isinstance(value, expected_type) else "invalid"


class BlockRows:
    def __init__(self, chain, block_time):
        self.chain = chain
        self.block_time = block_time
        self.tables = {name: [] for name in SCHEMAS}
        self.issues = []
        self._objects = set()
        self._relations = set()

    def add(self, table, raw_ref, **fields):
        self.tables[table].append(dict(chain=self.chain, chain_id=CHAIN_IDS[self.chain],
                                       parser_version=PARSER_VERSION, raw_ref=raw_ref, **fields))

    def issue(self, code, raw_ref, severity="error", **details):
        self.issues.append(dict(code=code, raw_ref=raw_ref, severity=severity, **details))

    def obj(self, address, raw_ref, kind="account", evidence="observed_address", decimals=None,
            token_standard=None):
        if not isinstance(address, str) or not address:
            return None
        oid = object_id(self.chain, address)
        key = (oid, kind, evidence, decimals, token_standard)
        if key not in self._objects:
            self._objects.add(key)
            self.add("objects", raw_ref, object_id=oid, address_or_pool_id=address,
                     object_type=kind, type_evidence=evidence, observed_at=self.block_time, first_seen_in_window=None,
                     token_standard=token_standard, decimals=decimals, metadata_status="not_requested")
        return oid

    def rel(self, subject, predicate, obj, raw_ref, status="observed"):
        if subject is None or obj is None:
            return
        key = (subject, predicate, obj, raw_ref)
        if key not in self._relations:
            self._relations.add(key)
            self.add("object_relations", raw_ref,
                     relation_id="relation:" + hashlib.sha256(compact(key).encode()).hexdigest(),
                     subject_id=subject, predicate=predicate, object_id=obj, evidence_ref=raw_ref,
                     observed_at=self.block_time, effective_time_status="observation_only",
                     relation_status=status)


def _evm(rows, block, height, block_path, receipts, receipts_path):
    block_ref = f"{block_path}#/result"
    block_id = f"{CHAIN_IDS[rows.chain]}:block:{height}"
    txs = block.get("transactions")
    if not isinstance(txs, list):
        rows.issue("transactions_missing_or_not_array", block_ref)
        txs = []
    rows.add("blocks", block_ref, block_id=block_id, height=integer(block.get("number")), slot=None,
             hash=block.get("hash"), parent_hash=block.get("parentHash"), parent_slot=None,
             block_time=rows.block_time, time_status="provided" if rows.block_time is not None else "missing",
             tx_count=len(txs), finality_status="finalized_window", window_membership="main")
    receipt_map = {}
    for ri, receipt in enumerate(receipts):
        if not isinstance(receipt, dict):
            rows.issue("malformed_receipt", f"{receipts_path}#/result/{ri}")
            continue
        th = receipt.get("transactionHash")
        if th in receipt_map:
            rows.issue("duplicate_receipt", f"{receipts_path}#/result/{ri}", tx_hash=th)
        receipt_map[th] = (receipt, ri)
    hashes = set()
    for ti, rawtx in enumerate(txs):
        tx_ref = f"{block_path}#/result/transactions/{ti}"
        tx = rawtx if isinstance(rawtx, dict) else {"hash": rawtx} if isinstance(rawtx, str) else {}
        th = tx.get("hash")
        hashes.add(th)
        tx_id = transaction_id(rows.chain, th or f"unidentified:{height}:{ti}")
        receipt, ri = receipt_map.get(th, ({}, None))
        rref = f"{receipts_path}#/result/{ri}" if ri is not None else tx_ref
        good_receipt = bool(receipt)
        if receipt:
            if receipt.get("blockHash") is not None and receipt.get("blockHash") != block.get("hash"):
                rows.issue("receipt_block_hash_mismatch", rref, tx_hash=th)
                good_receipt = False
            if receipt.get("blockNumber") is not None and integer(receipt["blockNumber"]) != height:
                rows.issue("receipt_block_number_mismatch", rref, tx_hash=th)
                good_receipt = False
        else:
            rows.issue("missing_receipt", tx_ref, tx_hash=th)
        status = integer(receipt.get("status")) if good_receipt else None
        gas_used = integer(receipt.get("gasUsed")) if good_receipt else None
        gas_price = integer(receipt.get("effectiveGasPrice")) if good_receipt else None
        # Base adds L1 data fees. Never label gasUsed*gasPrice alone as its total fee.
        fee = gas_used * gas_price if gas_used is not None and gas_price is not None else None
        if rows.chain == "base" and integer(tx.get("type")) != 126:
            l1_fee = integer(receipt.get("l1Fee"))
            fee = fee + l1_fee if fee is not None and l1_fee is not None else None
        typ = integer(tx.get("type"))
        decode_status = "parsed" if isinstance(rawtx, dict) and th else "incomplete_transaction"
        if not isinstance(rawtx, dict) or not th:
            rows.issue("incomplete_transaction", tx_ref)
        rows.add("transactions", tx_ref, tx_id=tx_id, block_id=block_id, tx_hash_or_signature=th,
                 tx_index=integer(tx.get("transactionIndex")) if tx.get("transactionIndex") is not None else ti,
                 block_time=rows.block_time, tx_version=None, tx_type=str(typ) if typ is not None else None,
                 execution_status="success" if status == 1 else "failed" if status == 0 else "unknown",
                 error_raw=None, fee_raw=str(fee) if fee is not None else None,
                 fee_asset_id=f"{CHAIN_IDS[rows.chain]}:native", decode_status=decode_status,
                 execution_meta_status="not_applicable", inner_instructions_status="not_applicable", log_messages_status="not_applicable",
                 # OP deposit type also includes user deposits. Identify only
                 # the protocol L1-attributes sender/recipient pair as system.
                 is_vote=False, is_system=(typ == 126 and
                     str(tx.get("from", "")).lower()=="0xdeaddeaddeaddeaddeaddeaddeaddeaddead0001" and
                     str(tx.get("to", "")).lower()=="0x4200000000000000000000000000000000000015") if rows.chain == "base" else False)
        from_id = rows.obj(tx.get("from"), tx_ref + "/from", evidence="transaction_sender")
        to_id = rows.obj(tx.get("to"), tx_ref + "/to", evidence="transaction_recipient")
        for ai, (aid, role) in enumerate(((from_id, "sender"), (to_id, "recipient"))):
            if aid:
                rows.add("transaction_accounts", tx_ref + ("/from" if ai == 0 else "/to"), tx_id=tx_id,
                         account_index=None, account_id=aid, role=role, is_signer=None, is_writable=None,
                         role_source="transaction_field")
        contract_id = rows.obj(receipt.get("contractAddress"), rref + "/contractAddress",
                               "contract", "receipt_contractAddress") if good_receipt else None
        rows.rel(tx_id, "created_contract", contract_id, rref + "/contractAddress")
        rows.add("evm_transaction_details", tx_ref, tx_id=tx_id, from_account=from_id, to_account=to_id,
                 nonce=amount(tx.get("nonce")), value_raw=amount(tx.get("value")), input_hex=tx.get("input"),
                 gas_limit=amount(tx.get("gas")), gas_used=amount(receipt.get("gasUsed")) if good_receipt else None,
                 effective_gas_price=amount(receipt.get("effectiveGasPrice")) if good_receipt else None,
                 contract_created=contract_id)
    # Receipt logs remain queryable even if the receipt is orphaned or inconsistent.
    for ri, receipt in enumerate(receipts):
        if not isinstance(receipt, dict):
            continue
        th = receipt.get("transactionHash")
        rref = f"{receipts_path}#/result/{ri}"
        if th not in hashes:
            rows.issue("orphan_receipt", rref, tx_hash=th)
        tx_id = transaction_id(rows.chain, th or f"unidentified_receipt:{height}:{ri}")
        if not isinstance(receipt.get("logs"), list):
            rows.issue("receipt_logs_missing", rref)
            continue
        for li, log in enumerate(receipt["logs"]):
            lref = f"{rref}/logs/{li}"
            if not isinstance(log, dict):
                rows.issue("malformed_log", lref)
                continue
            lindex = integer(log.get("logIndex"))
            rows.add("evm_logs", lref, log_id=f"{tx_id}:log:{lindex if lindex is not None else 'unknown:' + str(li)}",
                     tx_id=tx_id, block_time=rows.block_time, log_index=lindex,
                     emitter=log.get("address"), topics=compact(log.get("topics")),
                     data_hex=log.get("data"), removed=log.get("removed"))
            emitter_id = rows.obj(log.get("address"), lref + "/address", "contract", "log_emitter")
            rows.rel(tx_id, "emitted_log_from", emitter_id, lref)


def _key(value):
    return value.get("pubkey") if isinstance(value, dict) else value if isinstance(value, str) else None


def _solana(rows, block, slot, block_path):
    block_ref = f"{block_path}#/result"
    block_id = f"{CHAIN_IDS[rows.chain]}:slot:{slot}"
    txs = block.get("transactions")
    if not isinstance(txs, list):
        rows.issue("transactions_missing_or_not_array", block_ref)
        txs = []
    rows.add("blocks", block_ref, block_id=block_id, height=integer(block.get("blockHeight")), slot=slot,
             hash=block.get("blockhash"), parent_hash=block.get("previousBlockhash"),
             parent_slot=integer(block.get("parentSlot")), block_time=rows.block_time,
             time_status="provided_estimate" if rows.block_time is not None else "missing",
             tx_count=len(txs), finality_status="finalized_window", window_membership="main")
    for ti, item in enumerate(txs):
        tref = f"{block_path}#/result/transactions/{ti}"
        if not isinstance(item, dict):
            item = {}
        rawtx = item.get("transaction")
        tx = rawtx if isinstance(rawtx, dict) else {}
        sigs = tx.get("signatures") or []
        sig = sigs[0] if sigs and isinstance(sigs[0], str) else None
        tx_id = transaction_id(rows.chain, sig or f"unidentified:{slot}:{ti}")
        rawmeta = item.get("meta")
        meta = rawmeta if isinstance(rawmeta, dict) else {}
        rawmsg = tx.get("message")
        msg = rawmsg if isinstance(rawmsg, dict) else {}
        version = item.get("version")
        ver = str(version) if version is not None else None
        has_structure = isinstance(rawmsg, dict) and isinstance(msg.get("accountKeys"), list)
        known_version = version in (None, "legacy", 0)
        decode_status = "parsed" if has_structure and known_version else "parsed_unknown_version" if has_structure else "unrecognized_message"
        if not has_structure or not sig:
            rows.issue("unrecognized_message", tref, version=ver)
        elif not known_version:
            rows.issue("unrecognized_transaction_version", tref, severity="warning", version=ver)
        if not isinstance(rawmeta, dict):
            rows.issue("missing_meta", tref)
        if "err" not in meta:
            execution = "unknown"
        else:
            execution = "success" if meta["err"] is None else "failed"
        keys = msg.get("accountKeys") if isinstance(msg.get("accountKeys"), list) else []
        key_addresses = [_key(k) for k in keys]
        # jsonParsed keys already contain lookup-table accounts with source=lookupTable.
        parsed_expanded = any(isinstance(k, dict) and k.get("source") == "lookupTable" for k in keys)
        loaded = meta.get("loadedAddresses") if isinstance(meta.get("loadedAddresses"), dict) else {}
        writable_loaded = list(loaded.get("writable") or []) if not parsed_expanded else []
        readonly_loaded = list(loaded.get("readonly") or []) if not parsed_expanded else []
        key_addresses += [_key(k) for k in writable_loaded] + [_key(k) for k in readonly_loaded]
        header = msg.get("header") if isinstance(msg.get("header"), dict) else {}
        signers = integer(header.get("numRequiredSignatures"))
        ro_signed = integer(header.get("numReadonlySignedAccounts"))
        ro_unsigned = integer(header.get("numReadonlyUnsignedAccounts"))
        key_ids = []
        for ai, address in enumerate(key_addresses):
            kref = (f"{tref}/transaction/message/accountKeys/{ai}" if ai < len(keys) else
                    f"{tref}/meta/loadedAddresses/writable/{ai - len(keys)}" if ai < len(keys) + len(writable_loaded) else
                    f"{tref}/meta/loadedAddresses/readonly/{ai - len(keys) - len(writable_loaded)}")
            aid = rows.obj(address, kref)
            key_ids.append(aid)
            if aid is None:
                rows.issue("unresolved_account_key", kref, account_index=ai)
                continue
            rawkey = keys[ai] if ai < len(keys) else None
            signer = writable = None
            if isinstance(rawkey, dict):
                signer, writable = rawkey.get("signer"), rawkey.get("writable")
            elif ai >= len(keys):
                signer, writable = False, ai < len(keys) + len(writable_loaded)
            elif signers is not None:
                signer = ai < signers
                if signer and ro_signed is not None:
                    writable = ai < signers - ro_signed
                elif not signer and ro_unsigned is not None:
                    writable = ai < len(keys) - ro_unsigned
            role = "fee_payer" if ai == 0 else "signer" if signer else "account"
            rows.add("transaction_accounts", kref, tx_id=tx_id, account_index=ai, account_id=aid,
                     role=role, is_signer=signer, is_writable=writable, role_source="message_account_order")
        outer = msg.get("instructions") if isinstance(msg.get("instructions"), list) else []
        if not isinstance(msg.get("instructions"), list):
            rows.issue("instructions_missing_or_not_array", tref + "/transaction/message")
        program_ids = []

        def instruction(ins, oi, ii, iref):
            if not isinstance(ins, dict):
                rows.issue("malformed_instruction", iref)
                return
            pi = integer(ins.get("programIdIndex"))
            program = ins.get("programId") or (key_addresses[pi] if pi is not None and 0 <= pi < len(key_addresses) else None)
            if ii is None:
                program_ids.append(program)
            raw_accounts = ins.get("accounts")
            indices, accounts = [], []
            if isinstance(raw_accounts, list):
                for value in raw_accounts:
                    index = integer(value)
                    if isinstance(value, int):
                        indices.append(index)
                        accounts.append(key_ids[index] if 0 <= index < len(key_ids) else None)
                    elif isinstance(value, str):
                        indices.append(None)
                        accounts.append(object_id("solana", value))
            data = ins.get("data")
            if data is None and "parsed" in ins:
                data = compact(ins["parsed"])
            elif data is not None and not isinstance(data, str):
                data = compact(data)
            rows.add("solana_instructions", iref,
                     instruction_id=f"{tx_id}:ix:{oi}:{'outer' if ii is None else ii}",
                     tx_id=tx_id, block_time=rows.block_time, outer_index=oi, inner_index=ii,
                     stack_height=integer(ins.get("stackHeight")), program_id=program,
                     account_indices=compact(indices) if raw_accounts is not None else None,
                     account_ids=compact(accounts) if raw_accounts is not None else None,
                     data_raw=data, decode_status="parsed" if "parsed" in ins else
                     "compiled" if program is not None else "unresolved_program")
            pid = rows.obj(program, iref, "program", "instruction_program")
            rows.rel(tx_id, "invoked_program", pid, iref)
            if program is None:
                rows.issue("unresolved_program", iref)
            if any(a is None for a in accounts):
                rows.issue("unresolved_instruction_account", iref)

        for oi, ins in enumerate(outer):
            instruction(ins, oi, None, f"{tref}/transaction/message/instructions/{oi}")
        inner = meta.get("innerInstructions")
        if isinstance(inner, list):
            for group_i, group in enumerate(inner):
                if not isinstance(group, dict) or not isinstance(group.get("instructions"), list):
                    rows.issue("malformed_inner_instruction_group", f"{tref}/meta/innerInstructions/{group_i}")
                    continue
                oi = integer(group.get("index"))
                for ii, ins in enumerate(group["instructions"]):
                    instruction(ins, oi, ii, f"{tref}/meta/innerInstructions/{group_i}/instructions/{ii}")
        rows.add("transactions", tref, tx_id=tx_id, block_id=block_id, tx_hash_or_signature=sig, tx_index=ti,
                 block_time=rows.block_time, tx_version=ver, tx_type="solana", execution_status=execution,
                 error_raw=compact(meta.get("err")), fee_raw=amount(meta.get("fee")),
                 fee_asset_id=f"{CHAIN_IDS['solana']}:native", decode_status=decode_status,
                 execution_meta_status=field_status(item, "meta", dict),
                 inner_instructions_status=field_status(rawmeta, "innerInstructions", list),
                 log_messages_status=field_status(rawmeta, "logMessages", list),
                 is_vote=VOTE_PROGRAM in program_ids if has_structure else None, is_system=False)
        pre = meta.get("preBalances") if isinstance(meta.get("preBalances"), list) else []
        post = meta.get("postBalances") if isinstance(meta.get("postBalances"), list) else []
        if isinstance(rawmeta, dict) and (len(pre) != len(key_ids) or len(post) != len(key_ids)):
            rows.issue("native_balance_account_count_mismatch", tref + "/meta",
                       accounts=len(key_ids), pre=len(pre), post=len(post))
        for ai in range(max(len(pre), len(post))):
            aid = key_ids[ai] if ai < len(key_ids) else None
            rows.add("balance_observations", f"{tref}/meta", tx_id=tx_id, account_id=aid,
                     asset_id=f"{CHAIN_IDS['solana']}:native", owner_address=None, owner_status="not_applicable",
                     pre_amount_raw=amount(pre[ai]) if ai < len(pre) else None,
                     post_amount_raw=amount(post[ai]) if ai < len(post) else None, decimals=9,
                     source_kind="solana_native_balance_meta")
        balances = {}
        for side, field in (("pre", "preTokenBalances"), ("post", "postTokenBalances")):
            if not isinstance(meta.get(field), list):
                continue
            for bi, balance in enumerate(meta[field]):
                if not isinstance(balance, dict):
                    rows.issue("malformed_token_balance", f"{tref}/meta/{field}/{bi}")
                    continue
                index = integer(balance.get("accountIndex"))
                mint = balance.get("mint")
                # Owner may change in one transaction: keep distinct observations.
                owner = balance.get("owner")
                key = (index, mint, owner)
                balances.setdefault(key, {})[side] = (balance, f"{tref}/meta/{field}/{bi}")
        for (index, mint, owner), sides in balances.items():
            aid = key_ids[index] if index is not None and 0 <= index < len(key_ids) else None
            values, decimals = {}, None
            ref = next(iter(sides.values()))[1]
            token_program = None
            for side, (balance, bref) in sides.items():
                value = balance.get("uiTokenAmount") or {}
                values[side] = amount(value.get("amount"))
                d = integer(value.get("decimals"))
                if decimals is not None and d is not None and decimals != d:
                    rows.issue("token_decimals_conflict", bref)
                if d is not None:
                    decimals = d
                token_program = balance.get("programId") or token_program
            asset = rows.obj(mint, ref + "/mint", "token", "token_balance_mint", decimals=decimals,
                             token_standard=token_program)
            rows.add("balance_observations", ref, tx_id=tx_id, account_id=aid, asset_id=asset,
                     owner_address=owner, owner_status="provided" if owner else "not_provided",
                     pre_amount_raw=values.get("pre"), post_amount_raw=values.get("post"),
                     decimals=decimals, source_kind="solana_token_balance_meta")
            rows.rel(aid, "holds_token", asset, ref)
            if owner:
                owner_id = rows.obj(owner, ref + "/owner", evidence="token_balance_owner")
                rows.rel(aid, "token_account_owner", owner_id, ref)


def _write_shard(path, rows, schema):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".parquet.tmp")
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), temporary, compression="zstd")
    temporary.replace(path)


def annotate_object_first_seen(root):
    """Two passes over objects only, with a temporary disk-backed minimum index."""
    paths = sorted((Path(root) / "tables/base/objects").glob("*.parquet"))
    result = {"observation_rows": 0, "unknown_observation_times": 0,
              "unique_objects": 0, "objects_with_only_unknown_times": 0,
              "method": "two-pass disk-backed MIN(observed_at) per chain-qualified object_id"}
    with tempfile.TemporaryDirectory(prefix="claire-object-first-seen-") as directory:
        with closing(sqlite3.connect(str(Path(directory) / "first_seen.sqlite"))) as db:
            db.execute("PRAGMA journal_mode=OFF")
            db.execute("PRAGMA synchronous=OFF")
            db.execute("PRAGMA cache_size=-8192")
            db.execute("CREATE TABLE seen (object_id TEXT PRIMARY KEY, first_seen INTEGER) WITHOUT ROWID")
            upsert = """INSERT INTO seen VALUES (?, ?) ON CONFLICT(object_id) DO UPDATE SET first_seen =
                CASE WHEN seen.first_seen IS NULL THEN excluded.first_seen
                     WHEN excluded.first_seen IS NULL THEN seen.first_seen
                     ELSE MIN(seen.first_seen, excluded.first_seen) END"""
            for path in paths:
                for batch in pq.ParquetFile(path).iter_batches(columns=["object_id", "observed_at"], batch_size=8192):
                    observations = list(zip(batch.column(0).to_pylist(), batch.column(1).to_pylist()))
                    if any(oid is None for oid, _ in observations):
                        raise ValueError(f"Object observation has no object_id: {path}")
                    db.executemany(upsert, observations)
                    result["observation_rows"] += len(observations)
                    result["unknown_observation_times"] += sum(t is None for _, t in observations)
            db.commit()
            result["unique_objects"] = db.execute("SELECT COUNT(*) FROM seen").fetchone()[0]
            result["objects_with_only_unknown_times"] = db.execute("SELECT COUNT(*) FROM seen WHERE first_seen IS NULL").fetchone()[0]
            for path in paths:
                table = pq.read_table(path)
                ids = table.column("object_id").to_pylist()
                unique = sorted(set(ids))
                minimums = {}
                for offset in range(0, len(unique), 400):
                    chunk = unique[offset:offset + 400]
                    query = "SELECT object_id, first_seen FROM seen WHERE object_id IN (" + ",".join("?" for _ in chunk) + ")"
                    minimums.update(db.execute(query, chunk).fetchall())
                first_seen = pa.array([minimums[oid] for oid in ids], type=pa.int64())
                table = table.set_column(table.schema.get_field_index("first_seen_in_window"),
                                         SCHEMAS["objects"].field("first_seen_in_window"), first_seen)
                temporary = path.with_suffix(".parquet.tmp")
                pq.write_table(table, temporary, compression="zstd")
                temporary.replace(path)
    return result


def run(root):
    """Normalize only declared main blocks. No network access or implicit sampling."""
    root = Path(root)
    window_path = root / "reports/window.json"
    window = load_json(window_path)
    counts = {name: {chain: 0 for chain in CHAIN_IDS} for name in SCHEMAS}
    report = {"parser_version": PARSER_VERSION, "complete": True, "counts": counts,
              "errors": [], "warnings": [], "completed_blocks": {chain: [] for chain in CHAIN_IDS},
              "completed_boundary_blocks": {chain: [] for chain in CHAIN_IDS},
              "shards": [], "object_deduplication": "within_block_observation; observed_at belongs to each row; first_seen_in_window is global per object_id",
              "amount_encoding": "decimal integer strings", "json_encoding": "compact sorted-key JSON strings"}
    written = set()
    for chain in CHAIN_IDS:
        cfg = window.get("chains", {}).get(chain, {})
        heights = cfg.get("main_blocks", [])
        if not cfg.get("resolved", False):
            report["complete"] = False
            report["errors"].append({"chain": chain, "code": "window_not_resolved"})
        for height in heights:
            block_path = Path("raw") / chain / "blocks" / f"{height}.json.gz"
            receipts_path = Path("raw") / chain / "receipts" / f"{height}.json.gz"
            try:
                envelope = load_json(root / block_path)
                block = envelope.get("result")
                if not isinstance(block, dict):
                    raise ValueError("Raw block result is not an object")
            except (OSError, ValueError, TypeError) as exc:
                report["complete"] = False
                report["errors"].append({"chain": chain, "block": height, "code": "unreadable_block", "detail": str(exc)})
                continue
            time = integer(block.get("blockTime") if chain == "solana" else block.get("timestamp"))
            rows = BlockRows(chain, time)
            if time is None:
                rows.issue("block_time_missing", f"{block_path}#/result")
            elif not window["start_ts"] <= time < window["end_ts"]:
                rows.issue("main_block_outside_window", f"{block_path}#/result", timestamp=time)
            if chain == "solana":
                _solana(rows, block, height, block_path.as_posix())
            else:
                try:
                    receipts = load_json(root / receipts_path).get("result")
                    if not isinstance(receipts, list):
                        raise ValueError("Raw receipts result is not an array")
                except (OSError, ValueError, TypeError) as exc:
                    receipts = []
                    rows.issue("unreadable_receipts", receipts_path.as_posix(), detail=str(exc))
                _evm(rows, block, height, block_path.as_posix(), receipts, receipts_path.as_posix())
            for name, schema in SCHEMAS.items():
                rel = Path("tables/base") / name / f"{chain}-{height}.parquet"
                _write_shard(root / rel, rows.tables[name], schema)
                report["shards"].append(rel.as_posix())
                written.add(root / rel)
                counts[name][chain] += len(rows.tables[name])
            report["completed_blocks"][chain].append(height)
            for issue in rows.issues:
                target = "warnings" if issue.get("severity") == "warning" else "errors"
                report[target].append(dict(chain=chain, block=height, **issue))
            if any(i.get("severity") != "warning" for i in rows.issues):
                report["complete"] = False
        # Boundary blocks prove the time cut; their transactions are not normalized
        # into the main sample. Complete boundary RPC content remains in raw.
        for height in cfg.get("boundary_blocks", []):
            if height in heights:
                continue
            block_path = Path("raw") / chain / "blocks" / f"{height}.json.gz"
            try:
                block = load_json(root / block_path).get("result")
                if not isinstance(block, dict):
                    raise ValueError("Boundary block result is not an object")
                time = integer(block.get("blockTime") if chain == "solana" else block.get("timestamp"))
                rows = BlockRows(chain, time)
                txs = block.get("transactions")
                rows.add("blocks", f"{block_path}#/result",
                         block_id=f"{CHAIN_IDS[chain]}:{'slot' if chain == 'solana' else 'block'}:{height}",
                         height=integer(block.get("blockHeight" if chain == "solana" else "number")),
                         slot=height if chain == "solana" else None,
                         hash=block.get("blockhash" if chain == "solana" else "hash"),
                         parent_hash=block.get("previousBlockhash" if chain == "solana" else "parentHash"),
                         parent_slot=integer(block.get("parentSlot")), block_time=time,
                         time_status=("provided_estimate" if chain == "solana" else "provided") if time is not None else "missing",
                         tx_count=len(txs) if isinstance(txs, list) else None,
                         finality_status="finalized_window", window_membership="boundary")
                rel = Path("tables/base/blocks") / f"{chain}-{height}.parquet"
                _write_shard(root / rel, rows.tables["blocks"], SCHEMAS["blocks"])
                counts["blocks"][chain] += 1
                report["shards"].append(rel.as_posix())
                written.add(root / rel)
                report["completed_boundary_blocks"][chain].append(height)
            except (OSError, ValueError, TypeError) as exc:
                report["complete"] = False
                report["errors"].append({"chain": chain, "block": height, "code": "unreadable_boundary_block", "detail": str(exc)})
        if not report["completed_blocks"][chain]:
            for name, schema in SCHEMAS.items():
                rel = Path("tables/base") / name / f"{chain}-empty.parquet"
                _write_shard(root / rel, [], schema)
                report["shards"].append(rel.as_posix())
                written.add(root / rel)
    # Remove only generated partitions no longer in this declared window.
    for name in SCHEMAS:
        for chain in CHAIN_IDS:
            for prior in (root / "tables/base" / name).glob(f"{chain}-*.parquet"):
                if prior not in written:
                    prior.unlink()
    report["object_first_seen"] = annotate_object_first_seen(root)
    write_json(root / "reports/normalization.json", report)
    return report
