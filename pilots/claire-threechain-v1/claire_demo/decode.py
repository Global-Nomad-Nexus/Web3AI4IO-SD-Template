"""Offline, block-streamed decoding. Native observations remain authoritative.

An EVM Transfer-shaped log is a candidate until a published platform token
declaration supplies standard evidence. Failed Solana instructions never imply
committed asset movements; successful transactions can contain caught failed CPI.
"""
from pathlib import Path
from collections import Counter, defaultdict
import base64
import hashlib
import json
import re

import base58
import pyarrow as pa
import pyarrow.parquet as pq
from eth_abi import decode as abi_decode, encode as abi_encode
from eth_utils import keccak

from . import registry
from .common import load_json, write_json, sha256

VERSION = "claire-decode/1.0.0"
S, I = pa.string(), pa.int64()
SCHEMAS = {
    "decoded_records": pa.schema([(k, S) for k in ["chain_id", "record_id", "source_record_id", "equivalent_source_record_id", "tx_id", "decoder_id", "decoder_version", "record_type", "decoded_arguments", "execution_effect", "decode_status", "raw_ref"]] + [("block_time", I)]),
    "asset_movements": pa.schema([(k, S) for k in ["chain_id", "movement_id", "tx_id", "asset_id", "from_account", "to_account", "amount_raw", "movement_type", "evidence_type", "execution_effect", "source_record_id", "standard_status", "raw_ref"]] + [("decimals", I), ("block_time", I)]),
    "platform_records": pa.schema([(k, S) for k in ["chain_id", "platform_id", "source_record_id", "tx_id", "object_id", "operation_type", "decoder_version", "attribution_evidence", "execution_effect", "decode_status", "raw_ref"]] + [("block_time", I), ("block_number_or_slot", I), ("tx_index", I), ("event_order", I)]),
    "platform_registry": pa.schema([(k, S) for k in ["platform_id", "chain_id", "program_or_contract", "version", "source_url", "source_revision", "verification_status", "layout_path"]] + [("valid_from_block", I), ("valid_to_block", I)]),
    "crosschain_links": pa.schema([(k, S) for k in ["link_id", "left_object_id", "right_object_id", "relation_type", "evidence_ref", "verification_status", "uncertainty_reason"]] + [("observed_at", I)]),
}
SYSTEM = "11111111111111111111111111111111"
TOKEN = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN22 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
ANCHOR_EVENT_CPI = bytes([228, 69, 165, 46, 81, 203, 154, 29])
TRANSFER = "0x" + keccak(text="Transfer(address,address,uint256)").hex()
ZERO = "0x" + "00" * 20
OPERATIONS = {"TokenCreate": "creation", "TokenCreated": "creation", "TokenPurchase": "trade", "TokenSale": "trade", "LiquidityAdded": "liquidity_add", "CreateEvent": "creation", "CompleteEvent": "curve_complete", "CompletePumpAmmMigrationEvent": "migration", "TradeEvent": "trade", "BuyEvent": "trade", "SellEvent": "trade", "CreatePoolEvent": "pool_initialization", "DepositEvent": "liquidity_add", "WithdrawEvent": "liquidity_remove"}


def compact(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def precise(value):
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if isinstance(value, (tuple, list)):
        return [precise(v) for v in value]
    if isinstance(value, dict):
        return {k: precise(v) for k, v in value.items()}
    return value


def oid(chain_id, address):
    if address is None:
        return None
    return address if address.startswith(chain_id + ":") else f"{chain_id}:{address}"


def read_shard(root, name, filename):
    path = Path(root) / "tables/base" / name / filename
    return pq.read_table(path).to_pylist() if path.exists() else []


def write_table(root, name, filename, rows):
    path = Path(root) / "tables/decoded" / name / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMAS[name]), path, compression="zstd")


def abi_type(field):
    return "(" + ",".join(abi_type(x) for x in field["components"]) + ")" + field["type"][5:] if field["type"].startswith("tuple") else field["type"]


def event_topics(abi):
    result = {}
    for event in abi:
        if event.get("type") == "event" and not event.get("anonymous"):
            signature = event["name"] + "(" + ",".join(abi_type(x) for x in event["inputs"]) + ")"
            result["0x" + keccak(text=signature).hex()] = event
    return result


def decode_evm_event(event, topics, data):
    indexed = [x for x in event["inputs"] if x.get("indexed")]
    regular = [x for x in event["inputs"] if not x.get("indexed")]
    if len(topics) != len(indexed) + 1:
        raise ValueError("indexed topic count differs from pinned ABI")
    types = [abi_type(x) for x in regular]
    encoded = bytes.fromhex(data.removeprefix("0x"))
    values = abi_decode(types, encoded, strict=True)
    if abi_encode(types, values) != encoded:
        raise ValueError("ABI payload is not the exact canonical pinned layout")
    output = {x["name"]: precise(v) for x, v in zip(regular, values)}
    for item, topic in zip(indexed, topics[1:]):
        typ = abi_type(item)
        if typ in ("string", "bytes") or "[" in typ or typ.startswith("("):
            output[item["name"] + "_indexed_hash"] = topic
        else:
            output[item["name"]] = precise(abi_decode([typ], bytes.fromhex(topic[2:]), strict=True)[0])
    return output


def decode_transfer(log, tx, known_tokens=()):
    topics = json.loads(log["topics"]) if isinstance(log["topics"], str) else log["topics"]
    if not topics or topics[0].lower() != TRANSFER:
        return None
    # ERC721 has four indexed topics. It is explicitly excluded, not coerced.
    if len(topics) != 3 or len(log["data_hex"].removeprefix("0x")) != 64:
        return None
    if any(len(t) != 66 or int(t[2:26], 16) != 0 for t in topics[1:]):
        return None
    cid, token = log["chain_id"], log["emitter"].lower()
    source, target = "0x" + topics[1][-40:].lower(), "0x" + topics[2][-40:].lower()
    return dict(chain_id=cid, movement_id=log["log_id"] + ":movement", tx_id=log["tx_id"], asset_id=oid(cid, token), from_account=oid(cid, source), to_account=oid(cid, target), amount_raw=str(int(log["data_hex"], 16)), decimals=None, movement_type="mint" if source == ZERO else "burn" if target == ZERO else "transfer", evidence_type="evm_transfer_log", execution_effect="committed" if tx.get("execution_status") == "success" and not log.get("removed") else "not_committed" if tx.get("execution_status") == "failed" or log.get("removed") else "unknown", source_record_id=log["log_id"], standard_status="platform_fungible_token" if token in known_tokens else "fungible_transfer_candidate", raw_ref=log.get("raw_ref"), block_time=log.get("block_time"))


class BorshReader:
    def __init__(self, data, definitions):
        self.data, self.position, self.definitions = data, 0, definitions

    def take(self, size):
        if self.position + size > len(self.data):
            raise ValueError("short Borsh payload")
        result = self.data[self.position:self.position + size]
        self.position += size
        return result

    def value(self, typ):
        if isinstance(typ, str):
            if typ == "pubkey":
                return base58.b58encode(self.take(32)).decode()
            if typ == "bool":
                v = self.take(1)[0]
                if v not in (0, 1):
                    raise ValueError("invalid Borsh bool")
                return bool(v)
            if re.fullmatch(r"[ui](8|16|32|64|128|256)", typ):
                return str(int.from_bytes(self.take(int(typ[1:]) // 8), "little", signed=typ.startswith("i")))
            if typ in ("string", "bytes"):
                n = int.from_bytes(self.take(4), "little")
                if n > len(self.data):
                    raise ValueError("invalid Borsh length")
                v = self.take(n)
                return v.decode("utf-8") if typ == "string" else "0x" + v.hex()
            raise ValueError(f"unsupported Borsh type {typ}")
        if "defined" in typ:
            name = typ["defined"] if isinstance(typ["defined"], str) else typ["defined"]["name"]
            spec = self.definitions[name]
            if spec["kind"] == "struct":
                fields = spec["fields"]
                if all(isinstance(x, dict) and "name" in x for x in fields):
                    return {x["name"]: self.value(x["type"]) for x in fields}
                # Anchor tuple structs (e.g. OptionBool) name no fields.
                return [self.value(x) for x in fields]
            if spec["kind"] == "enum":
                idx = self.take(1)[0]
                variant = spec["variants"][idx]
                vals = variant.get("fields", [])
                return {"variant": variant["name"], "values": [self.value(v.get("type", v) if isinstance(v, dict) else v) for v in vals]}
        if "option" in typ:
            flag = self.take(1)[0]
            if flag not in (0, 1):
                raise ValueError("invalid option tag")
            return self.value(typ["option"]) if flag else None
        if "vec" in typ or "array" in typ:
            elem, length = (typ["vec"], int.from_bytes(self.take(4), "little")) if "vec" in typ else typ["array"]
            if length > 100000:
                raise ValueError("unreasonable Borsh array length")
            return [self.value(elem) for _ in range(length)]
        raise ValueError(f"unsupported Borsh layout {typ}")


def decode_anchor(payload, item, idl, is_event=False):
    if payload[:8] != bytes(item["discriminator"]):
        raise ValueError("discriminator mismatch")
    definitions = {x["name"]: x["type"] for x in idl.get("types", [])}
    reader = BorshReader(payload[8:], definitions)
    args = definitions[item["name"]]["fields"] if is_event else item.get("args", [])
    result = {x["name"]: reader.value(x["type"]) for x in args}
    if reader.position != len(reader.data):
        raise ValueError("trailing bytes differ from pinned layout")
    return result


def execution_frames(log_messages, tx_status):
    """Actual runtime frames including failed CPI and ancestor rollback."""
    stack, frames, events = [], [], []
    for n, line in enumerate(log_messages or []):
        start = re.fullmatch(r"Program (\w+) invoke \[(\d+)\]", line)
        end = re.fullmatch(r"Program (\w+) (success|failed: .*)", line)
        if start:
            f = dict(program=start[1], depth=int(start[2]), parent=stack[-1] if stack else None, outcome="unknown", start=n)
            frames.append(f); stack.append(f)
        elif end and stack and stack[-1]["program"] == end[1]:
            stack.pop()["outcome"] = "success" if end[2] == "success" else "failed"
        elif line.startswith("Program data: ") and stack:
            events.append((n, line[len("Program data: "):], stack[-1]))
    def effect(f):
        if tx_status == "failed":
            return "not_committed"
        outcomes = []
        while f:
            outcomes.append(f["outcome"]); f = f["parent"]
        if "failed" in outcomes:
            return "not_committed"
        return "committed" if tx_status == "success" and outcomes and all(x == "success" for x in outcomes) else "unknown"
    for f in frames:
        f["effect"] = effect(f)
    return frames, events


def decode_solana_movement(ix, effect, token_accounts):
    cid = ix["chain_id"]
    accounts = json.loads(ix["account_ids"]) if isinstance(ix["account_ids"], str) else ix["account_ids"]
    data = base58.b58decode(ix["data_raw"])
    p = ix["program_id"]
    source = target = mint = amount = None
    kind, decimals = "transfer", None
    if p == SYSTEM and len(data) == 12 and int.from_bytes(data[:4], "little") == 2 and len(accounts) >= 2:
        source, target, amount, mint = accounts[0], accounts[1], int.from_bytes(data[4:], "little"), oid(cid, "native")
    elif p in (TOKEN, TOKEN22) and data:
        tag = data[0]
        if tag == 3 and len(data) == 9 and len(accounts) >= 3:
            source, target, amount = accounts[0], accounts[1], int.from_bytes(data[1:], "little")
            info = token_accounts.get(source) or token_accounts.get(target)
            if info:
                mint, decimals = info
        elif tag == 12 and len(data) == 10 and len(accounts) >= 4:
            source, mint, target, amount, decimals = accounts[0], accounts[1], accounts[2], int.from_bytes(data[1:9], "little"), data[9]
        elif tag in (7, 8, 14, 15) and len(data) == (10 if tag in (14, 15) else 9) and len(accounts) >= 3:
            amount = int.from_bytes(data[1:9], "little")
            if tag in (7, 14):
                kind, mint, target = "mint", accounts[0], accounts[1]
            else:
                kind, source, mint = "burn", accounts[0], accounts[1]
            decimals = data[9] if len(data) == 10 else (token_accounts.get(target or source) or (None, None))[1]
    if amount is None:
        return None
    return dict(chain_id=cid, movement_id=ix["instruction_id"] + ":movement", tx_id=ix["tx_id"], asset_id=mint, from_account=source, to_account=target, amount_raw=str(amount), decimals=decimals, movement_type=kind, evidence_type="solana_instruction", execution_effect=effect, source_record_id=ix["instruction_id"], standard_status="native" if p == SYSTEM else "spl_token_program", raw_ref=ix.get("raw_ref"), block_time=ix.get("block_time"))


def _decoded(record, source, tx, decoder, name, args, effect, status="decoded"):
    return dict(chain_id=tx["chain_id"], record_id=source + ":decoded", source_record_id=source, tx_id=tx["tx_id"], decoder_id=decoder, decoder_version=VERSION, record_type=name, decoded_arguments=compact(args), execution_effect=effect, decode_status=status, raw_ref=record.get("raw_ref"), block_time=tx.get("block_time"))


def _platform(record, source, tx, entry, name, args, effect, order, status="decoded", token_accounts=None):
    subject = next((args[k] for k in ("mint", "base_mint", "tokenAddress", "token", "base") if isinstance(args.get(k), str)), None)
    if subject is None and token_accounts:
        account = args.get("user_base_token_account")
        found = token_accounts.get(oid(tx["chain_id"], account)) if account else None
        subject = found[0] if found else None
    return dict(chain_id=tx["chain_id"], platform_id=entry["platform_id"], source_record_id=source, tx_id=tx["tx_id"], object_id=oid(tx["chain_id"], subject), operation_type=OPERATIONS.get(name, "other." + name) if status == "decoded" else "unknown", decoder_version=VERSION, attribution_evidence=compact({"address": entry["program_or_contract"], "source_revision": entry["source_revision"], "layout": entry.get("layout_path"), "historical_bounds": "unknown"}), execution_effect=effect, decode_status=status, raw_ref=record.get("raw_ref"), block_time=tx.get("block_time"), block_number_or_slot=tx.get("block_number_or_slot"), tx_index=tx.get("tx_index"), event_order=order)


def keep_address_observation(addresses, address, observation):
    """Select evidence by its own observation time, independent of shard order.

    first_seen_in_window is a global object aggregate. It must never be used to
    backdate a later row's source evidence, such as a contract role discovered
    after the same address was first seen as an ordinary transaction account.
    """
    def key(row):
        observed = row.get("observed_at")
        return (observed is None, observed if observed is not None else 0,
                str(row.get("raw_ref") or ""), str(row.get("object_id") or ""))
    old = addresses.get(address)
    if old is None or key(observation) < key(old):
        addresses[address] = observation


def same_address_link(address, left, right):
    left_time, right_time = left.get("observed_at"), right.get("observed_at")
    observed = max(left_time, right_time) if left_time is not None and right_time is not None else None
    uncertainty = "No claim of common controller, project identity, or cross-chain fund flow."
    if observed is None:
        uncertainty += " One or both supporting observation timestamps are unknown."
    return dict(link_id="same_address_bytes:" + address, left_object_id=left["object_id"], right_object_id=right["object_id"], relation_type="same_address_bytes", evidence_ref=compact([left["raw_ref"], right["raw_ref"]]), observed_at=observed, verification_status="verified_address_bytes_only", uncertainty_reason=uncertainty)


def run(root):
    root = Path(root)
    entries = registry.load(root)
    write_table(root, "platform_registry", "registry.parquet", entries)
    evm, solana = {}, {}
    for entry in entries:
        layout = registry.read_layout(root, entry) if entry.get("layout_path") else None
        if entry["chain_id"].startswith("eip155"):
            evm[(entry["chain_id"], entry["program_or_contract"].lower())] = (entry, event_topics(layout) if layout else {})
        else:
            solana[entry["program_or_contract"]] = (entry, layout)
    counts, status_counts = Counter(), Counter()
    evm_addresses = defaultdict(dict)
    known_tokens = defaultdict(set)
    clanker_pools = {}
    platform_counts = defaultdict(Counter)
    files = sorted((root / "tables/base/transactions").glob("*.parquet"))
    expected_names = {p.name for p in files}
    for table in ("decoded_records", "asset_movements", "platform_records"):
        for old in (root / "tables/decoded" / table).glob("*.parquet"):
            if old.name not in expected_names:
                old.unlink()
    for path in files:
        filename = path.name
        txs = {r["tx_id"]: r for r in pq.read_table(path).to_pylist()}
        if not txs:
            for table in ("decoded_records", "asset_movements", "platform_records"):
                write_table(root, table, filename, [])
                counts[table] += 0
            continue
        chain = next(iter(txs.values()))["chain"]
        height = int(filename.removesuffix(".parquet").rsplit("-", 1)[-1])
        for tx in txs.values():
            tx["block_number_or_slot"] = height
        out = {k: [] for k in ("decoded_records", "asset_movements", "platform_records")}
        if chain != "solana":
            logs = read_shard(root, "evm_logs", filename)
            # Parse declarations first so transfers in the same block gain evidence.
            for log in logs:
                tx = txs[log["tx_id"]]
                match = evm.get((log["chain_id"], log["emitter"].lower()))
                if not match:
                    continue
                entry, topics_map = match
                if entry["platform_id"] == "uniswap.v4":
                    continue
                topics = json.loads(log["topics"])
                event = topics_map.get(topics[0].lower()) if topics else None
                effect = "committed" if tx["execution_status"] == "success" and not log.get("removed") else "not_committed" if tx["execution_status"] == "failed" or log.get("removed") else "unknown"
                name, args, status = (event["name"], {}, "decoded") if event else ("unknown", {}, "unknown_layout")
                if event:
                    try:
                        args = decode_evm_event(event, topics, log["data_hex"])
                    except Exception as exc:
                        args, status = {"error": str(exc)}, "decode_error"
                out["decoded_records"].append(_decoded(log, log["log_id"], tx, entry["platform_id"] + "/" + entry["version"], name, args, effect, status))
                p = _platform(log, log["log_id"], tx, entry, name, args, effect, log["log_index"], status)
                out["platform_records"].append(p)
                if entry["platform_id"] == "clanker" and name == "TokenCreated" and status == "decoded" and effect == "committed" and args.get("poolId") and args.get("tokenAddress"):
                    clanker_pools[args["poolId"]] = (args["tokenAddress"], entry, log["log_id"])
                if status == "decoded" and effect == "committed" and p["object_id"] and p["operation_type"] in ("creation", "trade", "liquidity_add"):
                    known_tokens[log["chain_id"]].add(p["object_id"].split(":")[-1].lower())
            # PoolId attribution requires a factory declaration retained in this
            # snapshot. A generic v4 Swap is never automatically a Clanker trade.
            for log in logs:
                match = evm.get((log["chain_id"], log["emitter"].lower()))
                if not match or match[0]["platform_id"] != "uniswap.v4":
                    continue
                entry, topic_map = match
                tx = txs[log["tx_id"]]
                topics = json.loads(log["topics"])
                event = topic_map.get(topics[0].lower()) if topics else None
                if not event:
                    continue
                effect = "committed" if tx["execution_status"] == "success" and not log.get("removed") else "not_committed" if tx["execution_status"] == "failed" or log.get("removed") else "unknown"
                try:
                    args, status = decode_evm_event(event, topics, log["data_hex"]), "decoded"
                except Exception as exc:
                    args, status = {"error": str(exc)}, "decode_error"
                out["decoded_records"].append(_decoded(log, log["log_id"], tx, "uniswap.v4", event["name"], args, effect, status))
                pool = clanker_pools.get(args.get("id"))
                if status == "decoded" and pool:
                    token, factory, declaration = pool
                    args["tokenAddress"] = token
                    p = _platform(log, log["log_id"], tx, factory, event["name"], args, effect, log["log_index"])
                    if event["name"] == "Swap":
                        p["operation_type"] = "trade"
                    elif event["name"] == "Initialize":
                        p["operation_type"] = "pool_initialization"
                    elif event["name"] == "ModifyLiquidity":
                        delta = int(args["liquidityDelta"])
                        p["operation_type"] = "liquidity_add" if delta > 0 else "liquidity_remove" if delta < 0 else "liquidity_checkpoint"
                    p["attribution_evidence"] = compact({"factory_declaration": declaration, "pool_id": args["id"], "pool_manager": log["emitter"], "source_revision": entry["source_revision"]})
                    out["platform_records"].append(p)
            for log in logs:
                movement = decode_transfer(log, txs[log["tx_id"]], known_tokens[log["chain_id"]])
                if movement:
                    out["asset_movements"].append(movement)
                    out["decoded_records"].append(_decoded(log, log["log_id"], txs[log["tx_id"]], "erc20-transfer-shape", "Transfer", {"amount_raw": movement["amount_raw"], "from": movement["from_account"], "to": movement["to_account"], "standard_status": movement["standard_status"]}, movement["execution_effect"]))
            for obj in read_shard(root, "objects", filename):
                address = obj["address_or_pool_id"]
                if re.fullmatch(r"0x[0-9a-fA-F]{40}", address or ""):
                    keep_address_observation(evm_addresses[obj["chain_id"]], address.lower(), obj)
        else:
            balance_rows = read_shard(root, "balance_observations", filename)
            token_accounts = defaultdict(dict)
            for r in balance_rows:
                if r.get("asset_id") and not r["asset_id"].endswith(":native"):
                    token_accounts[r["tx_id"]][r["account_id"]] = (r["asset_id"], r["decimals"])
            raw_path = root / "raw/solana/blocks" / (filename.removeprefix("solana-").removesuffix(".parquet") + ".json.gz")
            raw = load_json(raw_path)
            block = raw.get("result", raw)
            txraw = {"solana:mainnet:tx:" + x["transaction"]["signatures"][0]: x for x in block.get("transactions", []) if x.get("transaction", {}).get("signatures")}
            frame_queues, native_events = {}, {}
            event_cpi_observations = defaultdict(list)
            for tid, tx in txs.items():
                frames, events = execution_frames((txraw.get(tid, {}).get("meta") or {}).get("logMessages"), tx["execution_status"])
                queues = defaultdict(list)
                for frame in frames:
                    queues[frame["program"]].append(frame)
                frame_queues[tid], native_events[tid] = queues, events
            instructions = read_shard(root, "solana_instructions", filename)
            instructions.sort(key=lambda r: (txs[r["tx_id"]]["tx_index"], r["outer_index"] if r["outer_index"] is not None else -1, -1 if r["inner_index"] is None else r["inner_index"]))
            for ix in instructions:
                tx = txs[ix["tx_id"]]
                queue = frame_queues[ix["tx_id"]][ix["program_id"]]
                instruction_frame = queue.pop(0) if queue else None
                effect = instruction_frame["effect"] if instruction_frame else "not_committed" if tx["execution_status"] == "failed" else "unknown"
                accounts = token_accounts[ix["tx_id"]]
                if ix["program_id"] in (SYSTEM, TOKEN, TOKEN22):
                    try:
                        movement = decode_solana_movement(ix, effect, accounts)
                        if movement:
                            out["asset_movements"].append(movement)
                            out["decoded_records"].append(_decoded(ix, ix["instruction_id"], tx, ix["program_id"], movement["movement_type"], {k: movement[k] for k in ("amount_raw", "asset_id", "from_account", "to_account")}, effect))
                    except (ValueError, IndexError, TypeError):
                        out["decoded_records"].append(_decoded(ix, ix["instruction_id"], tx, ix["program_id"], "unknown", {}, effect, "decode_error"))
                elif ix["program_id"] in solana:
                    entry, idl = solana[ix["program_id"]]
                    event_cpi = False
                    try:
                        data = base58.b58decode(ix["data_raw"])
                        event_cpi = data[:8] == ANCHOR_EVENT_CPI
                        payload = data[8:] if event_cpi else data
                        pool = idl.get("events", []) if event_cpi else idl["instructions"]
                        item = next((x for x in pool if bytes(x["discriminator"]) == payload[:8]), None)
                        args = decode_anchor(payload, item, idl, event_cpi) if item else {}
                        name, status = (item["name"], "decoded") if item else ("unknown", "unknown_discriminator")
                    except (ValueError, KeyError, TypeError, IndexError) as exc:
                        name, args, status = "unknown", {"error": str(exc)}, "decode_error"
                    out["decoded_records"].append(_decoded(ix, ix["instruction_id"], tx, entry["platform_id"], name if event_cpi else "instruction." + name, args, effect, status))
                    if event_cpi:
                        order = instruction_frame["start"] if instruction_frame else (ix["outer_index"] or 0) * 100000 + (ix["inner_index"] or 0)
                        platform_record = _platform(ix, ix["instruction_id"], tx, entry, name, args, effect, order, status, accounts)
                        out["platform_records"].append(platform_record)
                        parent = instruction_frame.get("parent") if instruction_frame else None
                        if parent and parent["program"] == ix["program_id"]:
                            event_cpi_observations[(tx["tx_id"], ix["program_id"], parent["start"], payload, effect)].append(platform_record)
            for tid, events in native_events.items():
                tx = txs[tid]
                accounts = token_accounts[tid]
                for log_index, b64, frame in events:
                    if frame["program"] not in solana:
                        continue
                    entry, idl = solana[frame["program"]]
                    source = f"{tid}:program_data:{log_index}"
                    rec = {"raw_ref": str(raw_path.relative_to(root)) + f"#/result/transactions/{tx['tx_index']}/meta/logMessages/{log_index}"}
                    payload = None
                    try:
                        payload = base64.b64decode(b64, validate=True)
                        item = next((x for x in idl.get("events", []) if bytes(x["discriminator"]) == payload[:8]), None)
                        args = decode_anchor(payload, item, idl, True) if item else {}
                        name, status = (item["name"], "decoded") if item else ("unknown", "unknown_discriminator")
                    except (ValueError, KeyError, TypeError, IndexError) as exc:
                        name, args, status = "unknown", {"error": str(exc)}, "decode_error"
                    decoded = _decoded(rec, source, tx, entry["platform_id"], name, args, frame["effect"], status)
                    # One event can be observed in both log data and emit_cpi.
                    # Pair identical complete payloads one-to-one across channels;
                    # never collapse multiple observations within one channel.
                    matches = event_cpi_observations.get((tid, frame["program"], frame["start"], payload, frame["effect"]), [])
                    if matches:
                        canonical = matches.pop(0)
                        decoded["equivalent_source_record_id"] = canonical["source_record_id"]
                        evidence = json.loads(canonical["attribution_evidence"])
                        evidence["equivalent_program_data_record"] = source
                        canonical["attribution_evidence"] = compact(evidence)
                        canonical["event_order"] = min(canonical["event_order"], log_index)
                    else:
                        out["platform_records"].append(_platform(rec, source, tx, entry, name, args, frame["effect"], log_index, status, accounts))
                    out["decoded_records"].append(decoded)
        for table, rows in out.items():
            write_table(root, table, filename, rows)
            counts[table] += len(rows)
            if table == "decoded_records":
                status_counts.update(x["decode_status"] for x in rows)
            if table == "platform_records":
                for row in rows:
                    platform_counts[row["platform_id"]][row["decode_status"]] += 1
    left, right = evm_addresses["eip155:56"], evm_addresses["eip155:8453"]
    links = []
    for address in sorted(left.keys() & right.keys()):
        a, b = left[address], right[address]
        links.append(same_address_link(address, a, b))
    write_table(root, "crosschain_links", "links.parquet", links)
    counts["crosschain_links"] = len(links)
    for table in ("decoded_records", "asset_movements", "platform_records"):
        if not (root / "tables/decoded" / table).exists():
            write_table(root, table, "empty.parquet", [])
    report = dict(status="completed" if files else "no_input", decoder_version=VERSION, input_shards=len(files), input_shard_files=[p.name for p in files], base_transactions_hashes={str(p.relative_to(root)): sha256(p) for p in files}, row_counts=dict(counts), decode_status_counts=dict(status_counts), platform_decode_status_counts={k: dict(v) for k, v in platform_counts.items()}, historical_platform_version_bounds="unknown", clanker_v4_pools_evidenced_in_snapshot=len(clanker_pools), fungible_transfer_policy="three-topic EVM Transfer without independent token evidence remains candidate; ERC721 excluded", execution_effect_values=["committed", "not_committed", "unknown"], limitations=["No external pool histories or historical state fetched by offline decoding.", "Clanker trades outside identified factory records require independently evidenced pool attribution; zero decoded trades is not zero market activity.", "IDL layout mismatches remain decode_error; raw observations are retained."])
    write_json(root / "reports/decode.json", report)
    return report
