"""Data-linked Mermaid figures and CSV tables; no browser or network needed.

Rendering is optional. The authoritative outputs are Mermaid source and the
complete numerical tables used to construct each figure.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import csv
import html
import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from .common import CHAINS, START, END, load_json, write_json, sha256

LABELS = {"solana": "Solana", "bsc": "BSC", "base": "Base"}
PLATFORMS = {"solana": "Pump.fun", "bsc": "Four.meme", "base": "Clanker"}


def _report(root, name):
    p = root / "reports" / (name + ".json")
    return load_json(p) if p.exists() else {}


def _files(root, layer, table):
    p = root / "tables" / layer / table
    paths = sorted(p.glob("*.parquet")) if p.is_dir() else []
    flat = root / "tables" / layer / (table + ".parquet")
    return paths or ([flat] if flat.exists() else [])


def _frames(paths, columns=None):
    for path in paths:
        available = pq.read_schema(path).names
        keep = [c for c in columns if c in available] if columns else None
        for batch in pq.ParquetFile(path).iter_batches(batch_size=32768, columns=keep):
            yield batch.to_pandas()


def _chain(row):
    return row.get("chain") or next((k for k,v in CHAINS.items() if v == row.get("chain_id")), None)


def _window(frame, start, end):
    if "block_time" in frame:
        return frame.loc[frame.block_time.notna() & (frame.block_time >= start) & (frame.block_time < end)]
    return frame


def _csv(root, name, rows, fields):
    path = root / "figures" / "data" / (name + ".csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        out = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        out.writeheader()
        out.writerows(rows)
    return str(path.relative_to(root))


def _safe(value):
    return html.escape(str(value), quote=True).replace("\n", "<br/>").replace("|", "&#124;")


def _node(key, label):
    return f'  {key}["{_safe(label)}"]'


def _number(value):
    return "unknown" if value is None else f"{int(value):,}"


def _summary_mermaid(title, items):
    lines = ["flowchart TB", _node("title", title)]
    for i, item in enumerate(items):
        lines.extend([_node(f"n{i}", item), f"  title --- n{i}"])
    return "\n".join(lines) + "\n"


def _figure(root, identifier, title, source, caption, inputs):
    path = root / "figures" / (identifier + ".mmd")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    (root / "figures" / (identifier + ".md")).write_text(
        f"# {identifier}. {title}\n\n{caption}\n\n```mermaid\n{source}```\n\n"
        + "Data: " + ", ".join(f"[{Path(x).name}](../{x})" for x in inputs) + "\n")
    return dict(id=identifier, title=title, source=str(path.relative_to(root)),
                caption=caption, inputs=inputs, sha256=sha256(path), format="Mermaid",
                rendering="Optional Mermaid renderer; numerical tables and source work offline")


def _coverage(root, window):
    preflight = _report(root, "preflight")
    collection = _report(root, "collection")
    normalization = _report(root, "normalization")
    validation = _report(root, "validation")
    processing_valid = (normalization.get("complete") is True
                        and not normalization.get("errors")
                        and validation.get("passed") is True)
    records = []
    for chain in CHAINS:
        scope = window.get("chains", {}).get(chain, {})
        expected = scope.get("expected_blocks")
        heights = scope.get("main_blocks", [])
        block_files = [root / "raw" / chain / "blocks" / f"{h}.json.gz" for h in heights]
        block_observed = sum(p.exists() for p in block_files) if scope.get("resolved") else None
        normalized = sum((root / "tables/base/blocks" / f"{chain}-{h}.parquet").exists() for h in heights) if scope.get("resolved") else None
        checks = preflight.get("chains", {}).get(chain, {})
        selected = next((x for x in reversed(checks.get("checks", [])) if x.get("source_id") == checks.get("selected_source_id")), {})
        complete = bool(scope.get("resolved") and expected is not None and expected == normalized == block_observed
                        and collection.get("chains", {}).get(chain, {}).get("complete") is True
                        and processing_valid)
        records.append(dict(chain=chain, expected_blocks=expected, raw_blocks=block_observed,
                            normalized_blocks=normalized, core_coverage="complete" if complete else "unknown_or_partial",
                            skipped_slots=len(scope.get("skipped_slots", [])) if scope.get("resolved") else None,
                            uncertain_slots=len(scope.get("uncertain_slots", [])) if scope.get("resolved") else None,
                            trace=selected.get("trace", "unknown"), historical_state=selected.get("historical_state", "unknown")))
    return records


def _transaction_summaries(root, start, end, complete):
    counts, statuses, economic, available = Counter(), Counter(), Counter(), set()
    paths = _files(root, "base", "transactions")
    for frame in _frames(paths, ["chain", "chain_id", "block_time", "execution_status", "is_vote", "is_system"]):
        frame = _window(frame, start, end)
        for chain, group in frame.groupby("chain", dropna=False):
            available.add(chain)
            for ts, n in group.groupby((group.block_time.astype("int64")-start)//30).size().items():
                counts[(chain, int(ts))] += int(n)
            for status, n in group.execution_status.fillna("unknown").value_counts().items():
                statuses[(chain, str(status))] += int(n)
            keep = pd.Series(True, index=group.index)
            for col in ("is_vote", "is_system"):
                if col in group: keep &= ~group[col].fillna(False).astype(bool)
            for ts, n in group.loc[keep].groupby((group.loc[keep].block_time.astype("int64")-start)//30).size().items():
                economic[(chain, int(ts))] += int(n)
    rows, status_rows = [], []
    for chain in CHAINS:
        for minute in range((end-start+29)//30):
            observed = counts[(chain,minute)]
            filtered = economic[(chain,minute)]
            rows.append(dict(chain=chain, bin_start_utc=datetime.fromtimestamp(start+minute*30, timezone.utc).isoformat(),
                             bin_index=minute, bin_seconds=30, observed_transactions=observed if observed or complete[chain] else None,
                             excluding_identified_vote_system=filtered if filtered or complete[chain] else None,
                             coverage="complete" if complete[chain] else "unknown_or_partial"))
        keys = sorted({s for c,s in statuses if c == chain} | {"success", "failed", "unknown"})
        denominator=sum(n for (c,_),n in statuses.items() if c==chain)
        for status in keys:
            status_rows.append(dict(chain=chain, execution_status=status,
                                    observed_transactions=statuses[(chain,status)] if chain in available or complete[chain] else None,
                                    observed_denominator=denominator if chain in available or complete[chain] else None,
                                    observed_fraction=statuses[(chain,status)]/denominator if denominator else None,
                                    coverage="complete" if complete[chain] else "unknown_or_partial"))
    return rows, status_rows


def _platform_summaries(root, start, end, complete):
    paths = _files(root,"decoded","platform_records")
    counts, txs = Counter(), defaultdict(set)
    for frame in _frames(paths):
        for row in _window(frame,start,end).to_dict("records"):
            chain = _chain(row)
            if chain not in CHAINS: continue
            minute=int((row["block_time"]-start)//60)
            key = (chain, str(row.get("platform_id", PLATFORMS[chain])), str(row.get("operation_type","unknown")),
                   str(row.get("execution_effect","unknown")), str(row.get("decode_status","unknown")),minute)
            counts[key] += 1
            txs[key].add(row.get("tx_id"))
    rows = [dict(chain=k[0], platform=k[1], operation=k[2], execution_effect=k[3], decode_status=k[4],
                 minute_index=k[5],minute_utc=datetime.fromtimestamp(start+k[5]*60,timezone.utc).isoformat(),
                 record_count=n, distinct_transactions=len(txs[k]), coverage="complete" if complete[k[0]] else "unknown_or_partial")
            for k,n in sorted(counts.items())]
    for chain in CHAINS:
        files_for_chain = [p for p in paths if p.name.startswith(chain+"-")]
        decoder_known=bool(files_for_chain) and _report(root,"decode").get("status")=="completed"
        for minute in range((end-start+59)//60):
            for operation in ("creation","trade","curve_complete","migration","pool_initialization","liquidity_add","liquidity_remove"):
                if any(r["chain"]==chain and r["minute_index"]==minute and r["operation"]==operation for r in rows): continue
                mechanism_na=chain=="base" and operation in {"curve_complete","migration"}
                unknown=not (complete[chain] and decoder_known)
                rows.append(dict(chain=chain,platform=PLATFORMS[chain],operation=operation,
                                 execution_effect="not_applicable" if mechanism_na else "unknown" if unknown else "no_observed_record",
                                 decode_status="mechanism_not_applicable" if mechanism_na else "unknown" if unknown else "no_decoded_records",
                                 minute_index=minute,minute_utc=datetime.fromtimestamp(start+minute*60,timezone.utc).isoformat(),
                                 record_count=None if mechanism_na or unknown else 0,distinct_transactions=None if mechanism_na or unknown else 0,
                                 coverage="mechanism_not_applicable" if mechanism_na else "unknown_or_partial" if unknown else "observed_decoder_subset"))
    return rows


def _effective_movement(row):
    effect = str(row.get("execution_effect", "")).lower()
    typ = str(row.get("movement_type", "")).lower()
    evidence = str(row.get("evidence_type", "")).lower()
    standard = str(row.get("standard_status", "unknown")).lower()
    return (effect == "committed" and typ == "transfer"
            and standard in {"platform_fungible_token", "spl_token_program"}
            and "candidate" not in evidence)


def _node_roles(root, wanted):
    roles,evidence=defaultdict(set),defaultdict(set)
    for frame in _frames(_files(root,"base","objects"),["object_id","object_type","type_evidence"]):
        for row in frame.loc[frame.object_id.isin(wanted)].to_dict("records"):
            kind=row.get("object_type")
            if kind and kind!="account":
                roles[row["object_id"]].add(kind)
                evidence[row["object_id"]].add(str(row.get("type_evidence","unknown")))
    for frame in _frames(_files(root,"decoded","platform_registry")):
        for row in frame.to_dict("records"):
            address=str(row.get("program_or_contract",""))
            cid=str(row.get("chain_id",""))
            key=address if address.startswith(cid+":") else cid+":"+address
            if key in wanted:
                roles[key].add("platform_program" if cid.startswith("solana:") else "platform_contract")
                evidence[key].add("platform_registry:"+str(row.get("source_revision","unknown")))
    # Only layout-decoded explicit pool identifiers receive a pool label.
    for frame in _frames(_files(root,"decoded","decoded_records"),["chain_id","record_type","decoded_arguments","decode_status","execution_effect"]):
        for row in frame.to_dict("records"):
            if row.get("decode_status")!="decoded" or row.get("execution_effect")!="committed": continue
            if row.get("record_type") not in {"CreatePoolEvent","CompletePumpAmmMigrationEvent"}: continue
            try: args=json.loads(row.get("decoded_arguments") or "{}")
            except (ValueError,TypeError): continue
            for name in ("pool","pool_address","amm_pool"):
                address=args.get(name)
                if not isinstance(address,str): continue
                cid=str(row.get("chain_id"))
                key=address if address.startswith(cid+":") else cid+":"+address
                if key in wanted:
                    roles[key].add("pool")
                    evidence[key].add("decoded_explicit_pool_field:"+str(row["record_type"]))
    return [dict(account_id=account,roles="|".join(sorted(roles[account])) or "unclassified",
                 role_evidence="|".join(sorted(evidence[account])) or "no_verified_role_in_snapshot",
                 account_semantics="token_account_no_owner_projection" if account.startswith("solana:") else "chain_qualified_address")
            for account in sorted(wanted)]


def _graph_tables(root, start, end):
    paths = _files(root,"decoded","asset_movements")
    platform_assets=set()
    for frame in _frames(_files(root,"decoded","platform_records")):
        for row in _window(frame,start,end).to_dict("records"):
            if row.get("object_id") and row.get("decode_status")=="decoded" and row.get("execution_effect")=="committed":
                platform_assets.add((_chain(row),row["object_id"]))
    asset_counts = Counter()
    for frame in _frames(paths):
        for row in _window(frame,start,end).to_dict("records"):
            chain = _chain(row)
            if (chain,row.get("asset_id")) in platform_assets and _effective_movement(row):
                asset_counts[(chain,row["asset_id"])] += 1
    # This explicit analysis subset only controls the illustration, never raw collection.
    local_chosen = []
    for chain in CHAINS:
        local_chosen += sorted([k for k in asset_counts if k[0]==chain], key=lambda k:(-asset_counts[k],k[1]))[:1]
    gog_chosen=[]
    for chain in CHAINS:
        gog_chosen+=sorted([k for k in asset_counts if k[0]==chain],key=lambda k:(-asset_counts[k],k[1]))[:10]
    chosen=list(dict.fromkeys(local_chosen+gog_chosen))
    selected = set(chosen)
    edges, participants = Counter(), defaultdict(set)
    for frame in _frames(paths):
        for row in _window(frame,start,end).to_dict("records"):
            key = (_chain(row),row.get("asset_id"))
            if key not in selected or not _effective_movement(row): continue
            a,b = row.get("from_account"),row.get("to_account")
            if not a or not b: continue
            edges[(key[0],key[1],a,b)] += 1
            # Burn/mint sentinels are not participants and must not create GoG edges.
            participants[key].update(x for x in (a,b) if not str(x).endswith(":0x"+"0"*40))
    edge_rows = [dict(chain=k[0],asset_id=k[1],from_account=k[2],to_account=k[3],movement_count=v) for k,v in sorted(edges.items())]
    selection = [dict(chain=k[0],asset_id=k[1],eligible_movement_count=asset_counts[k],participant_count=len(participants[k]),local_graph=k in local_chosen,gog_graph=k in gog_chosen) for k in chosen]
    gog = []
    for i,a in enumerate(gog_chosen):
        for b in gog_chosen[i+1:]:
            # No cross-chain identity inference from a similar address string.
            if a[0] != b[0]: continue
            shared = participants[a] & participants[b]
            union=participants[a]|participants[b]
            gog.append(dict(chain=a[0],source_asset=a[1],target_asset=b[1],shared_addresses=len(shared),
                            union_addresses=len(union),jaccard=len(shared)/len(union) if union else None))
    wanted={r["from_account"] for r in edge_rows}|{r["to_account"] for r in edge_rows}
    roles=_node_roles(root,wanted) if wanted else []
    return selection, edge_rows, gog, roles, bool(paths)


def _event_summaries(root, complete):
    path = root / "tables/events/events.parquet"
    counts, attainments = Counter(), defaultdict(dict)
    receipt=_report(root,"events")
    evaluated=set(receipt.get("thresholds",[]))
    receipt_known=path.exists() and receipt.get("status")=="completed"
    pair_known=receipt_known and {1,3}.issubset(evaluated)
    if path.exists():
        for frame in _frames([path]):
            for row in frame.to_dict("records"):
                chain = _chain(row)
                if chain in CHAINS and row.get("event_type")=="window_activity_threshold":
                    value=row.get("threshold")
                    if pd.isna(value) or isinstance(value,bool): continue
                    try:
                        threshold=int(value)
                        if float(value)!=threshold: continue
                    except (ValueError,TypeError,OverflowError): continue
                    key = (chain,str(row.get("definition_id",row.get("event_type","unknown"))),threshold)
                    counts[key] += 1
                    if pair_known and threshold in (1,3):
                        attainments[(chain,row.get("subject_id"))][threshold]=row
    rows=[]
    for chain,cid in CHAINS.items():
        evidence=receipt.get("chains",{}).get(cid,{})
        for threshold in (1,3):
            known=receipt_known and threshold in evaluated
            value=counts[(chain,f"window_activity.{threshold}",threshold)]
            eligible=evidence.get("tokens_with_verified_trades")
            rows.append(dict(chain=chain,definition_id=f"window_activity.{threshold}",threshold=threshold,
                             event_count=value if known and (value or complete[chain]) else None,
                             eligible_observed_tokens=eligible if known and (eligible or complete[chain]) else None,
                             coverage="definition_not_evaluated" if receipt_known and threshold not in evaluated else "observed_decoded_subset" if known and complete[chain] else "unknown_or_partial"))
    deltas=[]
    for (chain,subject),events in sorted(attainments.items()):
        if 1 not in events or 3 not in events: continue
        t1,t3=events[1].get("block_time"),events[3].get("block_time")
        deltas.append(dict(chain=chain,subject_id=subject,threshold1_event_id=events[1].get("event_id"),
                           threshold3_event_id=events[3].get("event_id"),threshold1_time=events[1].get("event_time"),
                           threshold3_time=events[3].get("event_time"),delta_seconds=int(t3)-int(t1) if t1 is not None and t3 is not None else None))
    return rows, deltas, pair_known


def method_diagrams():
    return {
        "D1": ("How activities become observations", "flowchart TB\n  A[\"Users, creators and protocol actors\"] --> B[\"Transactions submitted to a chain\"]\n  B --> S[\"Solana program execution and consensus\"]\n  B --> E[\"BSC / Base EVM execution and consensus\"]\n  S --> SB[\"Solana blocks and transactions\"]\n  S --> SM[\"Execution meta: status, fees, balances, logs; outer and inner instructions\"]\n  E --> EB[\"EVM blocks and transaction envelopes\"]\n  E --> ER[\"Receipts: status, gas and emitted logs\"]\n  E -.-> ET[\"Call trees only when trace access is supported\"]\n  SB --> R[\"Immutable raw RPC snapshot\"]\n  SM --> R\n  EB --> R\n  ER --> R\n  ET -.-> R\n  R --> F[\"Chain-native facts and source references\"]\n  F --> D[\"Versioned researcher-defined events\"]\n  R -.-> U[\"Not directly observed: intent, real identity, arbitrary historical state\"]\n", "Solana execution exposes outer/inner instructions and metadata; BSC/Base EVM execution exposes transaction envelopes and receipts with logs. Call trees are a separate capability. These are different recording mechanisms; they are preserved before researcher-defined events are computed. Failed and unrecognized records remain in the raw snapshot."),
        "D2": ("Acquisition and reproducible processing", "flowchart LR\n  A[\"Free source capability checks\"] --> B[\"Resolve identical UTC window\"]\n  B --> C[\"All finalized blocks and transactions\"]\n  C --> D[\"Save raw responses and provenance\"]\n  D --> E[\"Normalize chain-native records\"]\n  E --> F[\"Decode platform and token facts\"]\n  F --> G[\"Apply replaceable event definitions\"]\n  E --> H[\"Descriptive tables and Mermaid figures\"]\n  F --> H\n  G --> H\n  C -.-> V[\"Validate coverage, IDs and source references\"]\n  E -.-> V\n  G -.-> V\n  D -.-> R[\"Offline snapshot replay\"]\n  R --> E\n", "The fixed window determines raw collection. Platform decoding and event definitions never filter or rewrite raw data. Offline replay begins from the saved snapshot; live source access is checked separately."),
    }
def run(root):
    root = Path(root)
    window = _report(root,"window")
    start = int(window.get("start_ts", datetime.fromisoformat(START.replace("Z","+00:00")).timestamp()))
    end = int(window.get("end_ts", datetime.fromisoformat(END.replace("Z","+00:00")).timestamp()))
    figures = []
    for identifier,(title,source,caption) in method_diagrams().items():
        figures.append(_figure(root,identifier,title,source,caption,[]))
    coverage = _coverage(root,window)
    complete = {r["chain"]:r["core_coverage"]=="complete" for r in coverage}
    summary_data = _csv(root,"F1_coverage_summary",coverage,list(coverage[0]))
    minute_coverage=_report(root,"coverage")
    if not isinstance(minute_coverage,list):
        minute_coverage=[dict(chain=chain,minute_utc=datetime.fromtimestamp(start+m*60,timezone.utc).isoformat(),minute_index=m,
                              data_type=kind,retrieved=None,expected=None,status="unknown: validation receipt not available",denominator_basis="unknown")
                         for chain in CHAINS for m in range((end-start+59)//60)
                         for kind in ("block_body","transactions","receipt_meta","native_logs_instructions","trace","historical_state")]
    data=_csv(root,"F1_coverage",minute_coverage,["chain","minute_utc","minute_index","data_type","retrieved","expected","status","denominator_basis"])
    items=[]
    for chain in CHAINS:
        for kind in ("block_body","transactions","receipt_meta","native_logs_instructions","trace","historical_state"):
            rs=sorted([r for r in minute_coverage if r["chain"]==chain and r["data_type"]==kind],key=lambda r:r["minute_index"])
            items.append(LABELS[chain]+" / "+kind+"\n"+("\n".join(f"Minute {r['minute_index']}: {_number(r['retrieved'])}/{_number(r['expected'])} [{r['status']}]" for r in rs) if rs else "unknown: no coverage receipt"))
    figures.append(_figure(root,"F1","Coverage and data availability",_summary_mermaid("F1: Coverage",items),"Counts refer only to main-window blocks; boundary guards are separate. The minute table is the last saved technical-validation coverage receipt and is unknown until that stage runs. Unknown or partial coverage is never replaced by zero. Trace availability is a capability observation, not full trace collection. Receipt/meta coverage and returned native-array coverage do not prove every possible execution detail is available.",[summary_data,data]))
    minute_rows,status_rows=_transaction_summaries(root,start,end,complete)
    paths=[_csv(root,"F2_30second_transactions",minute_rows,list(minute_rows[0])),_csv(root,"F2_execution_status",status_rows,list(status_rows[0]))]
    (root/"figures/data/F2_minute_transactions.csv").unlink(missing_ok=True)
    items=[]
    for chain in CHAINS:
        rs=[r for r in minute_rows if r["chain"]==chain]
        ss=[r for r in status_rows if r["chain"]==chain]
        items.append(LABELS[chain]+"\n30-second bins 0 to 9: "+", ".join(_number(r["observed_transactions"]) for r in rs)+"\nExcluding identified vote/system: "+", ".join(_number(r["excluding_identified_vote_system"]) for r in rs)+"\n"+"; ".join(r["execution_status"]+": "+_number(r["observed_transactions"])+" ("+(f"{r['observed_fraction']:.2%}" if r["observed_fraction"] is not None else "undefined/unknown")+")" for r in ss)+"\n"+("complete" if complete[chain] else "observed subset; coverage unknown/partial"))
    figures.append(_figure(root,"F2","Transaction counts and execution status",_summary_mermaid("F2: All transaction records",items),"Ten 30-second bins use block timestamps, not submission times. Counts include Solana vote transactions and chain system traffic; the companion view excludes identified vote/system records while retaining unclassified traffic. Status fractions use all observed transaction records as denominator; an empty or unavailable denominator is undefined/unknown. Transaction counts are not a ranking of economic activity.",paths))
    platforms=_platform_summaries(root,start,end,complete)
    data=_csv(root,"F3_platform_facts",platforms,list(platforms[0]))
    items=[]
    for chain in CHAINS:
        rs=[r for r in platforms if r["chain"]==chain]
        for operation in sorted({r["operation"] for r in rs}):
            values=[]
            for minute in range((end-start+59)//60):
                group=[r for r in rs if r["operation"]==operation and r["minute_index"]==minute]
                text="; ".join(f"{r['platform']}: {_number(r['record_count'])} [{r['execution_effect']}; {r['decode_status']}]" for r in group) if group else "unknown"
                values.append(f"Minute {minute}: {text}")
            items.append(LABELS[chain]+" / "+PLATFORMS[chain]+" / "+operation+"\n"+"\n".join(values))
    figures.append(_figure(root,"F3","Platform facts recognized after collection",_summary_mermaid("F3: Decoded platform observations",items),"Counts depend on the documented registry and decoder versions. An unrecognized call is not evidence of no platform activity. Operation categories can share a transaction. Neither platform counts nor zero records imply chain-wide launch-market coverage.",[data]))
    selection,edges,gog,roles,graph_available=_graph_tables(root,start,end)
    paths=[_csv(root,"F4_selected_assets",selection,["chain","asset_id","eligible_movement_count","participant_count","local_graph","gog_graph"]),_csv(root,"F4_local_edges",edges,["chain","asset_id","from_account","to_account","movement_count"]),_csv(root,"F4_gog_edges",gog,["chain","source_asset","target_asset","shared_addresses","union_addresses","jaccard"]),_csv(root,"F4_node_roles",roles,["account_id","roles","role_evidence","account_semantics"])]
    lines=["flowchart TB",_node("title","F4: Token-local movements and shared-address links")]
    asset_ids={r["asset_id"]:f"token{i}" for i,r in enumerate(selection) if r["gog_graph"]}
    role_lookup={r["account_id"]:r["roles"] for r in roles}
    if not selection:
        lines.extend([_node("empty","No eligible decoded movement graphs observed" if graph_available else "unknown: movement table unavailable"),"  title --- empty"])
    for i,row in enumerate(selection):
        if not row["local_graph"]: continue
        key=f"g{i}"
        lines.extend([f"  subgraph {key}[\"{_safe(LABELS[row['chain']]+': '+row['asset_id'][-16:])}\"]",_node(f"{key}s",f"{row['eligible_movement_count']} movements; {row['participant_count']} addresses")])
        eligible=[e for e in edges if e["asset_id"]==row["asset_id"]]
        node_counts=Counter()
        for edge in eligible:
            node_counts[edge["from_account"]]+=edge["movement_count"]
            node_counts[edge["to_account"]]+=edge["movement_count"]
        top_nodes=set(sorted(node_counts,key=lambda x:(-node_counts[x],x))[:30])
        subset=sorted([e for e in eligible if e["from_account"] in top_nodes and e["to_account"] in top_nodes],key=lambda e:(-e["movement_count"],e["from_account"],e["to_account"]))
        nodes={}
        for e in subset:
            for address in (e["from_account"],e["to_account"]):
                if address not in nodes:
                    nodes[address]=f"{key}a{len(nodes)}"
                    lines.append(_node(nodes[address],str(address)[-12:]+"\n"+role_lookup.get(address,"unclassified")))
            lines.append(f'    {nodes[e["from_account"]]} -->|{e["movement_count"]}| {nodes[e["to_account"]]}')
        lines.append("  end")
        lines.append(f"  title --- {key}s")
    if asset_ids:
        lines.append('  subgraph gog["Graph of graphs: up to ten platform-related tokens per chain"]')
        for row in selection:
            if row["gog_graph"]:
                lines.append(_node(asset_ids[row["asset_id"]],LABELS[row["chain"]]+": "+row["asset_id"][-16:]))
        lines.append("  end")
    for edge in gog:
        if edge["shared_addresses"]:
            lines.append(f'  {asset_ids[edge["source_asset"]]} -.-|shared {edge["shared_addresses"]}; J {edge["jaccard"]:.3f}| {asset_ids[edge["target_asset"]]}')
    lines.extend([_node("roles","Node roles are shown only when evidenced.\nUnverified pool/router roles stay unclassified.\nSolana token accounts are not projected to owners."),"  title --- roles"])
    figures.append(_figure(root,"F4","Local graphs and a graph of graphs", "\n".join(lines)+"\n", "Illustration subset: one platform-related token per chain, chosen by decoded committed fungible transfer count with token ID as tie-breaker. Local graphs show at most 30 addresses, ranked by incident transfer count then address ID; all aggregate edges for selected tokens remain in the CSV. Each chain's GoG uses at most ten platform-related tokens and their full observed address sets. Edge labels give shared-address count and Jaccard = shared / union. Pool, router and program roles are labeled only when verified; otherwise they remain unclassified. Solana nodes remain token accounts, with no owner projection. Infrastructure is included and can explain overlap. Shared addresses do not establish shared users or common ownership; cross-chain objects stay separate. Mint/burn, native currency, balance deltas and candidate/unknown token standards are excluded.",paths))
    events,deltas,event_available=_event_summaries(root,complete)
    data=_csv(root,"F5_event_definitions",events,["chain","definition_id","threshold","event_count","eligible_observed_tokens","coverage"])
    delta_data=_csv(root,"F5_attainment_deltas",deltas,["chain","subject_id","threshold1_event_id","threshold3_event_id","threshold1_time","threshold3_time","delta_seconds"])
    items=[]
    for chain in CHAINS:
        rs=[r for r in events if r["chain"]==chain]
        values=[r["delta_seconds"] for r in deltas if r["chain"]==chain and r["delta_seconds"] is not None]
        delta_text=(f"Both thresholds: {len(values)} tokens\nDelay seconds: median {pd.Series(values).median():g}; min {min(values)}; max {max(values)}" if values else "No computable attainment delay: no token with both timed events" if event_available else "Attainment delay unknown: event data or both evaluated definitions unavailable")
        items.append(LABELS[chain]+"\n"+"\n".join(f"Threshold {r['threshold']}: {_number(r['event_count'])} observed events" for r in rs)+"\nEligible observed tokens: "+_number(rs[0]["eligible_observed_tokens"])+"\n"+delta_text)
    figures.append(_figure(root,"F5","Changing an event definition on fixed observations",_summary_mermaid("F5: Threshold 1 versus 3 successful trade transactions",items),"Two definitions mark the first observed point at which an eligible token reaches one or three distinct successful trade transactions within the window. For tokens meeting both definitions, the second table reports threshold-3 time minus threshold-1 time in block-time seconds. No matching timed pair means no computable delay, not zero delay. These are left-censored window observations, not lifetime first trades or launch success. Raw and base hashes remain unchanged.",[data,delta_data]))
    (root/"figures/index.md").write_text("# Claire pilot: Mermaid figures\n\nFigures are generated from local tables. Render with a Mermaid-capable viewer; CSVs remain readable offline.\n\n"+"\n\n".join(f"- [{f['id']}: {f['title']}]({f['id']}.md)" for f in figures)+"\n")
    # Rendering uses a local bundle only. Sources and tables require no network.
    sections=[]
    for f in figures:
        source=(root/f["source"]).read_text()
        sections.append(f"<section><h2>{html.escape(f['id']+': '+f['title'])}</h2><p>{html.escape(f['caption'])}</p><pre class='mermaid'>{html.escape(source)}</pre><details><summary>Editable Mermaid source</summary><pre>{html.escape(source)}</pre></details></section>")
    vendor=root/"vendor/mermaid.min.js"
    renderer=("<script>(function(){const define=undefined,exports=undefined,module=undefined;"+vendor.read_text()+"})();mermaid.initialize({startOnLoad:false,securityLevel:'strict',maxTextSize:1000000,maxEdges:10000});mermaid.run({querySelector:'.mermaid'});</script>") if vendor.exists() else "<p>No local Mermaid bundle: showing editable source. Numerical CSV tables remain available offline.</p>"
    (root/"figures/index.html").write_text("<!doctype html><html><head><meta charset='utf-8'><title>Claire pilot figures</title></head><body><h1>Claire pilot figures</h1><p>Sources and numerical CSV tables work offline; no network renderer is loaded.</p>"+"".join(sections)+renderer+"</body></html>")
    report=dict(format="Mermaid only",figures=figures,raw_filtering="none",core_complete=all(complete.values()),
                numerical_data="figures/data",window=dict(start_ts=start,end_ts=end),
                no_external_assets=not vendor.exists(),rendering_requires_network=False,local_renderer_available=vendor.exists(),
                renderer_manifest="vendor/manifest.json" if vendor.exists() else None,
                renderer_license="vendor/mermaid-LICENSE.txt" if vendor.exists() else None)
    write_json(root/"reports/visualization.json",report)
    return report
