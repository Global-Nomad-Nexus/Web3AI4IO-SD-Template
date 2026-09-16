"""Offline acceptance evidence. Missing material is a failed check, never zero activity."""
from collections import Counter, defaultdict
from pathlib import Path
import hashlib
import json
import random
import csv
import re
import sqlite3
import tempfile
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from .common import CHAINS, load_json, write_json, file_hashes, sha256, START, END, timestamp
from .schemas import SCHEMAS as BASE_SCHEMAS
from .normalize import integer, amount, field_status

def rows(path):
    path=Path(path)
    files=sorted(path.rglob("*.parquet")) if path.is_dir() else ([path] if path.exists() else [])
    for file in files:
        for batch in pq.ParquetFile(file).iter_batches(batch_size=4096):
            yield from batch.to_pylist()

def semantic_hash(path, row_observer=None):
    """Streaming logical row hash, independent of Parquet compression/metadata."""
    h=hashlib.sha256(); count=0
    for row in rows(path):
        if row_observer is not None: row_observer(row)
        h.update(json.dumps(row,sort_keys=True,ensure_ascii=False,separators=(",",":"),default=str).encode()+b"\n")
        count+=1
    return {"sha256":h.hexdigest(),"rows":count,"ordering":"sorted partition paths then canonical stored row order"}

def semantic_tables(root, observers=None):
    """Canonical enumeration shared by validation, replay and packaging."""
    root=Path(root)
    paths=[p for parent in ("base","decoded","events") for p in sorted((root/"tables"/parent).glob("*"))
           if p.is_dir() or p.suffix==".parquet"]
    provenance_table=root/"provenance/requests.parquet"
    if provenance_table.exists(): paths.append(provenance_table)
    observers=observers or {}
    return {str(p.relative_to(root)):semantic_hash(p,observers.get(str(p.relative_to(root)))) for p in paths}

class ObjectTimeAudit:
    """Validate global minima during the existing logical-hash stream.

    Memory is bounded by an 8192-row buffer and SQLite's 8 MiB page cache.
    No second traversal of the 54-million-row base layer is introduced.
    """
    def __init__(self, source_times):
        self.source_times=source_times;self.buffer=[];self.errors=[];self.error_count=0
        self.observation_rows=0
    def __enter__(self):
        self.directory=tempfile.TemporaryDirectory(prefix="claire-object-time-audit-")
        self.db=sqlite3.connect(str(Path(self.directory.name)/"audit.sqlite"))
        self.db.execute("PRAGMA journal_mode=OFF")
        self.db.execute("PRAGMA synchronous=OFF")
        self.db.execute("PRAGMA cache_size=-8192")
        self.db.execute("CREATE TABLE seen (object_id TEXT PRIMARY KEY, actual_min INTEGER, claimed INTEGER, conflict INTEGER) WITHOUT ROWID")
        return self
    def error(self,message):
        self.error_count+=1
        if len(self.errors)<50: self.errors.append(message)
    def add(self,row):
        self.observation_rows+=1
        oid=row.get("object_id");observed=row.get("observed_at");claimed=row.get("first_seen_in_window")
        source=(row.get("raw_ref") or "").partition("#")[0]
        if source not in self.source_times or observed!=self.source_times.get(source):
            self.error(f"object observed_at differs from source block: {oid} at {row.get('raw_ref')}")
        if not oid:
            self.error("object observation has no object_id");return
        self.buffer.append((oid,observed,claimed))
        if len(self.buffer)>=8192: self.flush()
    def flush(self):
        if not self.buffer:return
        self.db.executemany("""INSERT INTO seen VALUES (?, ?, ?, 0) ON CONFLICT(object_id) DO UPDATE SET
          actual_min=CASE WHEN seen.actual_min IS NULL THEN excluded.actual_min
                          WHEN excluded.actual_min IS NULL THEN seen.actual_min
                          ELSE MIN(seen.actual_min,excluded.actual_min) END,
          conflict=CASE WHEN seen.claimed IS NOT excluded.claimed THEN 1 ELSE seen.conflict END""",self.buffer)
        self.buffer.clear()
    def finish(self):
        self.flush();self.db.commit()
        invalid="conflict=1 OR claimed IS NOT actual_min"
        wrong=self.db.execute("SELECT COUNT(*) FROM seen WHERE "+invalid).fetchone()[0]
        self.error_count+=wrong
        for oid,actual,claimed,conflict in self.db.execute("SELECT object_id,actual_min,claimed,conflict FROM seen WHERE "+invalid+" LIMIT ?",(max(0,50-len(self.errors)),)):
            self.errors.append(f"object first_seen_in_window is not global MIN(observed_at): {oid}; expected={actual}, claimed={claimed}, conflicting_rows={bool(conflict)}")
        return {"passed":self.error_count==0,"error_count":self.error_count,"errors":self.errors,
                "observation_rows":self.observation_rows,
                "unique_objects":self.db.execute("SELECT COUNT(*) FROM seen").fetchone()[0],
                "implementation":"disk-backed aggregation during existing objects semantic-hash stream"}
    def __exit__(self,*args):
        self.db.close();self.directory.cleanup()

def resolve_raw_ref(root, ref):
    filename,sep,pointer=ref.partition("#")
    if not (root/filename).resolve().is_relative_to(root.resolve()):
        raise ValueError("raw_ref escapes dataset")
    value=load_json(root/filename)
    if pointer:
        for segment in pointer.lstrip("/").split("/"):
            segment=segment.replace("~1","/").replace("~0","~")
            value=value[int(segment)] if isinstance(value,list) else value[segment]
    return value

def load_report(root, name):
    try:
        value=load_json(root/"reports"/(name+".json"))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError): return {}

def provenance_errors(root, hashes):
    """Compare original receipts; verify assembly contents, not only its inputs."""
    ledger=root/"provenance/request_log.jsonl"
    if not ledger.exists(): return ["missing acquisition ledger"]
    expected=defaultdict(set); errors=[]; checked=set()
    for number,line in enumerate(ledger.read_text().splitlines()):
        try: item=json.loads(line)
        except ValueError:
            errors.append(f"malformed acquisition receipt {number+1}"); continue
        if item.get("raw_path") and item.get("raw_sha256"):
            expected[item["raw_path"]].add(item["raw_sha256"])
    def verify(relative,trail=()):
        if relative in checked: return
        if relative in trail:
            errors.append(f"cyclic lineage {relative}"); return
        if relative not in hashes or not (root/relative).resolve().is_relative_to(root.resolve()):
            errors.append(f"missing/unsafe raw lineage input {relative}"); return
        if relative in expected:
            if expected[relative]!={hashes[relative]}: errors.append(f"acquisition hash mismatch {relative}")
            checked.add(relative); return
        try: raw=load_json(root/relative)
        except (OSError,ValueError):
            errors.append(f"unreadable raw {relative}"); return
        if not isinstance(raw,dict) or raw.get("_assembled_from")!="transaction_receipts":
            errors.append(f"no acquisition receipt {relative}"); return
        inputs=raw.get("_input_files"); result=raw.get("result")
        if not isinstance(inputs,dict) or not isinstance(result,list) or len(inputs)!=len(result):
            errors.append(f"invalid assembled lineage {relative}"); return
        assembled=[]
        for child,digest in inputs.items():
            verify(child,trail+(relative,))
            if hashes.get(child)!=digest:
                errors.append(f"lineage hash differs {relative}:{child}"); continue
            try: assembled.append(load_json(root/child)["result"])
            except (OSError,ValueError,KeyError): errors.append(f"unreadable assembly input {child}")
        canonical=lambda xs:Counter(json.dumps(r,sort_keys=True,separators=(",",":")) for r in xs)
        if canonical(assembled)!=canonical(result): errors.append(f"assembly differs from inputs {relative}")
        checked.add(relative)
    for relative in hashes: verify(relative)
    errors.extend(f"ledger references missing raw file {p}" for p in expected if p not in hashes)
    return errors

def inspect_table(path, schema):
    """Validate a typed shard and exact integer columns, with bounded memory."""
    if not path.exists(): return None,[f"missing table shard {path.name}"]
    errors=[]
    try:
        file=pq.ParquetFile(path)
        if not file.schema_arrow.equals(schema,check_metadata=False): errors.append(f"schema differs {path.name}")
        names=[n for n in schema.names if n in ("fee_raw","value_raw","nonce","gas_limit","gas_used","effective_gas_price","pre_amount_raw","post_amount_raw","amount_raw")]
        for batch in file.iter_batches(columns=names,batch_size=65536) if names else []:
            for col,name in zip(batch.columns,names):
                if not pa.types.is_string(col.type): errors.append(f"non-string amount {path.name}:{name}"); continue
                invalid=pc.and_(pc.is_valid(col),pc.invert(pc.match_substring_regex(col,r"^-?[0-9]+$")))
                if pc.any(invalid).as_py(): errors.append(f"non-integer amount {path.name}:{name}")
        return file.metadata.num_rows,errors
    except Exception as exc: return None,[f"unreadable table {path.name}:{type(exc).__name__}"]

def typed_provenance_errors(root,raw_hashes):
    """A formerly valid prefix is not a complete ledger after acquisition grows."""
    from .provenance import SCHEMA, VERSION
    summary=load_report(root,"provenance_summary")
    errors=[];ledger=root/"provenance/request_log.jsonl";table=root/"provenance/requests.parquet"
    if summary.get("passed") is not True or summary.get("status")!="completed":
        errors.append("provenance summary missing/not passed")
    if summary.get("provenance_parser_version")!=VERSION:
        errors.append("provenance parser version differs")
    if summary.get("ledger_path")!="provenance/request_log.jsonl" or summary.get("output_path")!="provenance/requests.parquet":
        errors.append("provenance summary paths differ")
    if not ledger.exists(): return errors+["missing request ledger"]
    size=ledger.stat().st_size;ledger_hash=sha256(ledger)
    byte_fields=("ledger_snapshot_bytes","covered_ledger_bytes","ledger_bytes_at_finish")
    if any(summary.get(k)!=size for k in byte_fields):
        errors.append("provenance covers stale/incomplete ledger prefix")
    if summary.get("ledger_snapshot_sha256")!=ledger_hash:
        errors.append("provenance ledger prefix hash differs")
    if summary.get("ledger_prefix_unchanged") is not True or summary.get("unparsed_trailing_bytes")!=0 or summary.get("appended_bytes_during_run")!=0:
        errors.append("provenance parsing did not cover one complete stable ledger")
    if summary.get("parser_issues"):
        errors.append("provenance parser reports unresolved issues")
    number,problems=inspect_table(table,SCHEMA);errors.extend(problems)
    if table.exists() and summary.get("output_sha256")!=sha256(table):
        errors.append("typed provenance output hash differs")
    if number!=summary.get("rows"):
        errors.append("typed provenance row count differs from summary")
    if number is None: return errors
    typed=iter(rows(table));line_count=0
    with ledger.open("rb") as fh:
        for line_count,line in enumerate(fh,1):
            if not line.endswith(b"\n"):
                errors.append("request ledger has unparsed trailing bytes");break
            try: original=json.loads(line)
            except (ValueError,UnicodeDecodeError):
                errors.append(f"malformed original ledger row {line_count}");continue
            if not isinstance(original,dict):
                errors.append(f"non-object original ledger row {line_count}");continue
            row=next(typed,None)
            if row is None:
                errors.append("typed provenance omits original ledger rows");break
            if row.get("ledger_line")!=line_count or row.get("provenance_parser_version")!=VERSION:
                errors.append(f"typed provenance order/version differs {line_count}")
            rel=original.get("raw_path");original_hash=original.get("raw_sha256")
            expected_hash=raw_hashes.get(rel) if rel else None
            if row.get("raw_path")!=rel or row.get("ledger_raw_sha256")!=original_hash:
                errors.append(f"typed provenance changes original raw reference {line_count}")
            if rel:
                if expected_hash is None or original_hash!=expected_hash or row.get("raw_sha256")!=expected_hash or row.get("raw_integrity")!="matched":
                    errors.append(f"typed provenance raw integrity differs {line_count}")
            elif row.get("raw_sha256")!=original_hash or row.get("raw_integrity")!="no_raw_response":
                errors.append(f"typed provenance invents a raw response {line_count}")
            if row.get("parser_issues")!="[]":
                errors.append(f"typed provenance parser issue {line_count}")
    if next(typed,None) is not None or line_count!=number:
        errors.append("typed provenance row count differs from complete ledger")
    if ledger.stat().st_size!=size or sha256(ledger)!=ledger_hash:
        errors.append("request ledger changed during validation")
    return errors

def native_counts(chain,txs,receipts):
    """Independent record counts; absent native arrays never mean empty arrays."""
    errors=[]; logs=instructions=balances=0
    if chain!="solana":
        for receipt in receipts or []:
            if not isinstance(receipt,dict) or not isinstance(receipt.get("logs"),list): errors.append("receipt logs missing/non-array")
            else: logs+=len(receipt["logs"])
    else:
        for i,tx in enumerate(txs):
            msg=(tx.get("transaction") or {}).get("message"); meta=tx.get("meta")
            if not isinstance(msg,dict) or not isinstance(msg.get("instructions"),list): errors.append(f"tx {i}: missing outer instructions")
            else: instructions+=len(msg["instructions"])
            if not isinstance(meta,dict): errors.append(f"tx {i}: missing meta"); continue
            if "err" not in meta: errors.append(f"tx {i}: missing execution status")
            inner=meta.get("innerInstructions")
            if inner is None and "innerInstructions" in meta: pass
            elif not isinstance(inner,list): errors.append(f"tx {i}: inner instructions missing/invalid")
            else:
                for group in inner:
                    if not isinstance(group,dict) or not isinstance(group.get("instructions"),list): errors.append(f"tx {i}: malformed inner group")
                    else: instructions+=len(group["instructions"])
            log_status=field_status(meta,"logMessages",list)
            if log_status in ("missing","invalid"): errors.append(f"tx {i}: logMessages missing/invalid")
            pre,post=meta.get("preBalances"),meta.get("postBalances")
            if not isinstance(pre,list) or not isinstance(post,list): errors.append(f"tx {i}: native balances unavailable")
            else: balances+=max(len(pre),len(post))
            keys=set()
            for name in ("preTokenBalances","postTokenBalances"):
                array=meta.get(name)
                if not isinstance(array,list): errors.append(f"tx {i}: {name} unavailable"); continue
                for b in array:
                    if not isinstance(b,dict): errors.append(f"tx {i}: malformed token balance")
                    else: keys.add((b.get("accountIndex"),b.get("mint"),b.get("owner")))
            balances+=len(keys)
    return {"evm_logs":logs,"solana_instructions":instructions,"balance_observations":balances},errors

def run(root):
    root=Path(root)
    checks=[]; coverage=[]; samples=[]; counts={}
    def check(name,passed,details=None):
        checks.append({"check":name,"passed":bool(passed),"details":details})
    wpath=root/"reports/window.json"
    window=load_json(wpath) if wpath.exists() else {"chains":{},"resolved":False}
    pfpath=root/"reports/preflight.json"
    preflight=load_json(pfpath) if pfpath.exists() else {"chains":{}}
    normalization=load_report(root,"normalization")
    decode_report=load_report(root,"decode"); events_report=load_report(root,"events")
    check("window_resolved_three_chains",window.get("resolved") and set(window.get("chains",{}))==set(CHAINS) and window.get("start_ts")==timestamp(START) and window.get("end_ts")==timestamp(END))
    check("normalization_completed_without_errors",normalization.get("complete") is True and not normalization.get("errors"),normalization.get("errors","missing report"))
    raw_hashes=file_hashes(root,("raw",)); p_errors=provenance_errors(root,raw_hashes)
    check("acquisition_hashes_and_assembly_lineage",bool(raw_hashes) and not p_errors,p_errors)
    typed_errors=typed_provenance_errors(root,raw_hashes)
    check("typed_provenance_covers_complete_current_ledger",not typed_errors,typed_errors)
    base_errors=[]; expected_partitions={n:set() for n in BASE_SCHEMAS}; base_counts={n:Counter() for n in BASE_SCHEMAS}
    object_source_times={}
    expected_decoded=set()
    start,end=timestamp(START),timestamp(END)
    for chain in CHAINS:
        scope=window.get("chains",{}).get(chain,{})
        main=scope.get("main_blocks",[]); guards=scope.get("boundary_blocks",[])
        total_raw=total_normal=0; chain_ok=bool(scope.get("resolved")); blocktimes={}; actual={}; errors=[]
        if scope.get("uncertain_slots") or scope.get("expected_blocks")!=len(main) or len(main)!=len(set(main)) or set(main)&set(guards):
            errors.append("inconsistent or uncertain window manifest");chain_ok=False
        rng=random.Random(20260914); reservoir=[]; seen=0; special={}
        previous=None
        for height in sorted(set(main+guards)):
            filename=f"{chain}-{height}.parquet"
            shard_counts={}
            for table,schema in BASE_SCHEMAS.items():
                if height not in main and table!="blocks": continue
                expected_partitions[table].add(filename)
                number,problems=inspect_table(root/"tables/base"/table/filename,schema)
                shard_counts[table]=number
                base_counts[table][chain]+=number or 0
                base_errors.extend(f"{table}/{filename}: {p}" for p in problems)
            if height in main: expected_decoded.add(filename)
            path=root/"raw"/chain/"blocks"/f"{height}.json.gz"
            if not path.exists(): errors.append(f"missing block {height}"); chain_ok=False; continue
            block=load_json(path).get("result")
            if not isinstance(block,dict): errors.append(f"null block {height}");chain_ok=False;continue
            bt=block.get("blockTime") if chain=="solana" else int(block["timestamp"],16)
            blocktimes[height]=bt
            if chain!="solana" and integer(block.get("number"))!=height:
                errors.append(f"wrong EVM block number {height}");chain_ok=False
            if previous is not None:
                expected_parent=previous[1].get("blockhash") if chain=="solana" else previous[1].get("hash")
                parent=block.get("previousBlockhash") if chain=="solana" else block.get("parentHash")
                if parent != expected_parent: errors.append(f"parent hash mismatch {height}");chain_ok=False
                if chain=="solana" and block.get("parentSlot")!=previous[0]: errors.append(f"unaccounted produced slot before {height}");chain_ok=False
                if chain!="solana" and height!=previous[0]+1: errors.append(f"noncontiguous EVM heights before {height}");chain_ok=False
            previous=(height,block)
            if height not in main: continue
            object_source_times[f"raw/{chain}/blocks/{height}.json.gz"]=bt
            if chain!="solana":
                object_source_times[f"raw/{chain}/receipts/{height}.json.gz"]=bt
            if bt is None or not start<=bt<end: errors.append(f"wrong/unknown UTC membership {height}");chain_ok=False
            txs=block.get("transactions")
            if not isinstance(txs,list):
                errors.append(f"transactions missing/non-array {height}");chain_ok=False;continue
            native_ids=[t["transaction"]["signatures"][0] for t in txs] if chain=="solana" else [t["hash"] for t in txs]
            normalized=list(rows(root/"tables/base/transactions"/f"{chain}-{height}.parquet"))
            normal_ids=[r["tx_hash_or_signature"] for r in normalized]
            if native_ids!=normal_ids: errors.append(f"transaction list differs {height}");chain_ok=False
            total_raw+=len(txs);total_normal+=len(normalized)
            receipts=None
            if chain!="solana":
                rp=root/"raw"/chain/"receipts"/f"{height}.json.gz"
                receipts=load_json(rp).get("result") if rp.exists() else None
                if not isinstance(receipts,list) or any(not isinstance(r,dict) for r in receipts):
                    errors.append(f"receipt missing/non-array {height}");chain_ok=False;receipts=[]
                if Counter(r.get("transactionHash") for r in receipts)!=Counter(native_ids):
                    errors.append(f"receipt missing/duplicate {height}");chain_ok=False
                elif any(r.get("blockHash")!=block.get("hash") or int(r["blockNumber"],16)!=height for r in receipts):
                    errors.append(f"receipt block mismatch {height}");chain_ok=False
            source_counts,source_errors=native_counts(chain,txs,receipts)
            if source_errors: errors.extend(f"{height}: {p}" for p in source_errors);chain_ok=False
            for table,expected in source_counts.items():
                number=shard_counts.get(table)
                if number!=expected: base_errors.append(f"source count differs {table}/{filename}: {number} != {expected}")
            meta_count=sum(t.get("meta") is not None for t in txs) if chain=="solana" else len(receipts or [])
            actual[height]={"block_body":1,"transactions":len(txs),"receipt_meta":meta_count,
                            "native_logs_instructions":source_counts["solana_instructions" if chain=="solana" else "evm_logs"],
                            "native_arrays_complete":not source_errors and (chain!="solana" or all(field_status(t.get("meta"),"innerInstructions",list)=="provided" and field_status(t.get("meta"),"logMessages",list)=="provided" for t in txs))}
            receipt_map={r["transactionHash"]:r for r in receipts or []}
            for index,row in enumerate(normalized):
                if index>=len(txs): break
                native=txs[index]; identity=native_ids[index]
                expected_ref=f"raw/{chain}/blocks/{height}.json.gz#/result/transactions/{index}"
                if chain=="solana":
                    meta=native.get("meta")
                    status="unknown" if not isinstance(meta,dict) or "err" not in meta else "success" if meta["err"] is None else "failed"
                    source_statuses={"execution_meta_status":field_status(native,"meta",dict),
                                     "inner_instructions_status":field_status(meta,"innerInstructions",list),
                                     "log_messages_status":field_status(meta,"logMessages",list)}
                else:
                    rs=integer(receipt_map.get(identity,{}).get("status"));status="success" if rs==1 else "failed" if rs==0 else "unknown"
                    source_statuses={n:"not_applicable" for n in ("execution_meta_status","inner_instructions_status","log_messages_status")}
                if any(row.get(n)!=v for n,v in source_statuses.items()):
                    errors.append(f"native availability state differs {height}:{index}");chain_ok=False
                if row.get("raw_ref")!=expected_ref or row.get("tx_id")!=f"{CHAINS[chain]}:tx:{identity}" or row.get("execution_status")!=status or row.get("block_time")!=bt:
                    errors.append(f"tx identity/status/raw_ref differs {height}:{index}");chain_ok=False
                if chain=="solana" and row.get("fee_raw")!=amount((native.get("meta") or {}).get("fee")):
                    errors.append(f"tx fee differs {height}:{index}");chain_ok=False
                seen+=1
                sample={"chain":chain,"height":height,"tx_id":row["tx_id"],"raw_ref":row["raw_ref"],"tx_version":row.get("tx_version"),"execution_status":row.get("execution_status")}
                if len(reservoir)<20: reservoir.append(sample)
                else:
                    idx=rng.randrange(seen)
                    if idx<20: reservoir[idx]=sample
                special.setdefault((str(row.get("tx_version")),str(row.get("execution_status"))),sample)
            if chain!="solana":
                details={r["tx_id"]:r for r in rows(root/"tables/base/evm_transaction_details"/filename)}
                for tx in txs:
                    detail=details.get(f"{CHAINS[chain]}:tx:{tx['hash']}")
                    if detail is None or detail.get("value_raw")!=amount(tx.get("value")):
                        base_errors.append(f"raw EVM value differs {filename}:{tx['hash']}")
        if main and len(guards)==2:
            before=blocktimes.get(min(guards));after=blocktimes.get(max(guards))
            if before is None or after is None or not before<start or not after>=end:
                errors.append("boundary blocks do not bracket UTC window");chain_ok=False
        else: errors.append("no resolved window/boundary blocks");chain_ok=False
        for sample in reservoir+list(special.values()):
            try:
                raw=resolve_raw_ref(root,sample["raw_ref"])
                sample["raw_ref_resolves"]=raw is not None
                if raw is None: chain_ok=False;errors.append("sample raw_ref resolves to null")
            except Exception as exc: sample["raw_ref_resolves"]=False;sample["error"]=str(exc);chain_ok=False
            samples.append(sample)
        counts[chain]={"raw_transactions":total_raw,"normalized_transactions":total_normal,"expected_blocks":scope.get("expected_blocks"),"retrieved_main_blocks":len(actual),"skipped_slots":len(scope.get("skipped_slots",[])),"uncertain_slots":scope.get("uncertain_slots",[])}
        if not main:
            for table,schema in BASE_SCHEMAS.items():
                empty=f"{chain}-empty.parquet";expected_partitions[table].add(empty)
                number,problems=inspect_table(root/"tables/base"/table/empty,schema)
                base_errors.extend(problems)
                if number!=0: base_errors.append(f"nonempty empty-scope shard {table}/{empty}")
        check(chain+"_core_integrity",chain_ok,errors)
        for minute in range(5):
            heights=[h for h in main if blocktimes.get(h) is not None and start+minute*60<=blocktimes[h]<start+(minute+1)*60]
            denominator_known=scope.get("resolved",False) and all(h in blocktimes and blocktimes[h] is not None for h in main)
            for kind in ("block_body","transactions","receipt_meta","native_logs_instructions","trace","historical_state"):
                got=sum(actual.get(h,{}).get(kind,0) for h in heights)
                expected=(len(heights) if kind=="block_body" else sum(actual.get(h,{}).get("transactions",0) for h in heights)) if kind in ("block_body","transactions","receipt_meta") and denominator_known else None
                if kind=="native_logs_instructions": expected=got if denominator_known and all(h in actual and actual[h]["native_arrays_complete"] for h in heights) else None
                status="complete" if expected is not None and got==expected else "partial" if got else "unknown"
                if kind=="trace":
                    capability=preflight.get("chains",{}).get(chain,{})
                    selected=next((c for c in capability.get("checks",[]) if c["source_id"]==capability.get("selected_source_id")),{})
                    status="not_applicable" if chain=="solana" else selected.get("trace","unknown")
                    got=None;expected=None
                    if chain!="solana" and status=="available":
                        got=0
                        for h in heights:
                            tp=root/"raw"/chain/"traces"/f"{h}.json.gz"
                            if tp.exists(): got+=sum(isinstance(t,dict) and t.get("result") is not None for t in (load_json(tp).get("result") or []))
                        expected=sum(actual.get(h,{}).get("transactions",0) for h in heights) if denominator_known else None
                        status="complete" if expected is not None and got==expected else "partial" if got else "unavailable"
                if kind=="historical_state":status="unavailable";got=None;expected=None
                coverage.append(dict(chain=chain,minute_utc=f"12:{minute:02d}",minute_index=minute,data_type=kind,retrieved=got,expected=expected,status=status,denominator_basis="canonical block transaction list" if kind in ("transactions","receipt_meta") else "returned native arrays" if kind=="native_logs_instructions" else "resolved block range"))
    movement_errors=[]
    for row in rows(root/"tables/decoded/asset_movements"):
        if row.get("execution_effect") not in ("committed","not_committed","unknown"):
            movement_errors.append(row.get("movement_id"))
        movement_amount=row.get("amount_raw")
        if movement_amount is not None and (not isinstance(movement_amount,str) or not re_integer(movement_amount)):
            movement_errors.append(row.get("movement_id"))
    check("movement_amounts_exact_and_effect_explicit",not movement_errors,movement_errors[:20])
    for table in BASE_SCHEMAS:
        found={p.name for p in (root/"tables/base"/table).glob("*.parquet")}
        if found!=expected_partitions[table]:
            base_errors.append(f"partition set differs {table}: missing={sorted(expected_partitions[table]-found)} extra={sorted(found-expected_partitions[table])}")
        if any(base_counts[table][chain]!=normalization.get("counts",{}).get(table,{}).get(chain) for chain in CHAINS):
            base_errors.append(f"normalization report count differs {table}")
    check("all_base_tables_typed_and_source_counts_match",not base_errors,base_errors)
    from .decode import SCHEMAS as DECODE_SCHEMAS
    from .events import SCHEMA as EVENT_SCHEMA
    derived_errors=[]
    if decode_report.get("status")!="completed": derived_errors.append("decode report missing/not completed")
    base_input_hashes={str(p.relative_to(root)):sha256(p) for p in sorted((root/"tables/base/transactions").glob("*.parquet"))}
    if decode_report.get("base_transactions_hashes")!=base_input_hashes: derived_errors.append("decode transaction input hashes differ")
    for table,schema in DECODE_SCHEMAS.items():
        directory=root/"tables/decoded"/table
        expected={"registry.parquet"} if table=="platform_registry" else {"links.parquet"} if table=="crosschain_links" else {Path(p).name for p in base_input_hashes}
        found={p.name for p in directory.glob("*.parquet")}
        if found!=expected: derived_errors.append(f"decoded partition set differs {table}")
        total=0
        for p in sorted(directory.glob("*.parquet")):
            number,problems=inspect_table(p,schema);total+=number or 0
            derived_errors.extend(f"{table}: {problem}" for problem in problems)
        if table!="platform_registry" and total!=decode_report.get("row_counts",{}).get(table,0):
            derived_errors.append(f"decode report count differs {table}")
    if events_report.get("status")!="completed" or events_report.get("raw_base_unchanged") is not True:
        derived_errors.append("events missing/not completed/inputs changed")
    current_inputs=dict(raw_hashes,**file_hashes(root,("tables/base",)))
    if events_report.get("input_hashes")!=current_inputs: derived_errors.append("event inputs differ from current raw/base")
    event_count,event_errors=inspect_table(root/"tables/events/events.parquet",EVENT_SCHEMA)
    derived_errors.extend(event_errors)
    if event_count!=events_report.get("events"): derived_errors.append("event report count differs")
    check("decoded_and_event_outputs_present_and_current",not derived_errors,derived_errors)
    with ObjectTimeAudit(object_source_times) as object_audit:
        table_hashes=semantic_tables(root,{"tables/base/objects":object_audit.add})
        object_time_result=object_audit.finish()
    check("object_observation_times_and_global_first_seen",object_time_result["passed"],object_time_result)
    manifest={"dataset_version":"claire-threechain-v1","window":{"start":START,"end":END},"raw_files":raw_hashes,"semantic_tables":table_hashes,"raw_bytes":sum(p.stat().st_size for p in (root/"raw").rglob("*") if p.is_file()),"acceptance":"passed" if all(c["passed"] for c in checks) else "failed","acceptance_scope":"raw/base/decoded/event integrity only","independent_chain_validation":"See reports/cross_source.json; a file checksum alone is not independent validation"}
    write_json(root/"manifest.json",manifest)
    report={"passed":all(c["passed"] for c in checks),"checks":checks,"counts":counts,"acceptance_scope":manifest["acceptance_scope"],"snapshot_replay":"not_tested_by_this_command","colab_compatibility":"not_tested_by_this_command"}
    write_json(root/"reports/validation.json",report)
    write_json(root/"reports/sampled_transactions.json",samples)
    write_json(root/"reports/coverage.json",coverage)
    with (root/"reports/coverage.csv").open("w") as fh:
        writer=csv.DictWriter(fh,fieldnames=list(coverage[0]));writer.writeheader();writer.writerows(coverage)
    return report

def re_integer(value):
    return isinstance(value,str) and re.fullmatch(r"-?[0-9]+",value) is not None
