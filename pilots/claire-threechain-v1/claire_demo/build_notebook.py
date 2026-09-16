"""Generate the editable eight-part Claire tutorial; no collection or network."""
from pathlib import Path
import json
import hashlib
import nbformat as nbf


def snapshot_baseline(root):
    """Capture the supplied manifest before any rebuilding stage can replace it."""
    path=Path(root)/"manifest.json"
    payload=path.read_bytes()
    baseline=json.loads(payload)
    if baseline.get("acceptance")!="passed" or any(
        not isinstance(baseline.get(key),dict) or not baseline[key]
        for key in ("raw_files","semantic_tables","window")
    ):
        raise RuntimeError("Snapshot requires a passed manifest with raw and semantic baselines")
    return {**baseline,"manifest_sha256":hashlib.sha256(payload).hexdigest()}


def compare_snapshot_manifest(baseline, current):
    """Compare retained dictionaries exactly, but return only a bounded summary."""
    result={"baseline_manifest_sha256":baseline["manifest_sha256"],
            "window_equal":baseline.get("window")==current.get("window")}
    for key in ("raw_files","semantic_tables"):
        before=baseline.get(key,{})
        after=current.get(key,{})
        changed=[name for name in sorted(set(before)|set(after)) if before.get(name)!=after.get(name)]
        result[key]={"equal":before==after,"baseline_entries":len(before),
                     "rebuilt_entries":len(after),"changed_entries":len(changed),
                     "first_changed_paths":changed[:10]}
    result["passed"]=(result["window_equal"] and current.get("acceptance")=="passed"
                      and all(result[key]["equal"] for key in ("raw_files","semantic_tables")))
    return result


def prepare_live_root(snapshot_root):
    """Create a fresh task-local collector; never copy raw evidence or caches."""
    from datetime import datetime, timezone
    import shutil
    snapshot_root=Path(snapshot_root).resolve()
    destination=snapshot_root/"live_runs"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    destination.mkdir(parents=True,exist_ok=False)
    for name in ("claire_demo","config","sources","vendor","docs"):
        if (snapshot_root/name).is_dir():
            shutil.copytree(snapshot_root/name,destination/name,
                            ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
    for path in snapshot_root.glob("requirements*.txt"):
        shutil.copy2(path,destination/path.name)
    if not (destination/"claire_demo/__main__.py").exists() or not (destination/"config/rpc.json").exists():
        raise RuntimeError("Live run requires implementation and RPC configuration")
    return destination


def is_real_colab():
    """Require Colab's active shell; a package import alone is not runtime evidence."""
    import os
    import sys
    if os.environ.get("CLAIRE_NOTEBOOK_EXECUTOR")=="local" or "google.colab" not in sys.modules:
        return False
    try:
        from IPython import get_ipython
        shell=get_ipython()
        return shell is not None and type(shell).__module__.startswith("google.colab.")
    except ImportError:
        return False


def write_colab_receipt(root, mode, completed_parts, completed_stages, comparison):
    """Record a real, completed snapshot replay in Colab, never a local simulation."""
    if not is_real_colab():
        return {"status":"not_written","reason":"This is not a Google Colab runtime"}
    if mode!="snapshot":
        return {"status":"not_written","reason":"Live collection has separate reports; this receipt verifies uploaded-snapshot replay"}
    root=Path(root)
    validation=json.loads((root/"reports/validation.json").read_text())
    events=json.loads((root/"reports/events.json").read_text())
    required_stages={"provenance","normalize","decode","derive_events","validate","visualize"}
    if (not set(("I","II","III","IV","V","VI","VII")).issubset(completed_parts)
        or not required_stages.issubset(completed_stages)
        or validation.get("passed") is not True or comparison.get("passed") is not True
        or events.get("thresholds")!=[1,3]):
        raise RuntimeError("Colab receipt requires completed prior parts, validation, restored event defaults and matching snapshot baselines")
    import importlib.metadata
    import os
    import platform
    import sys
    from datetime import datetime, timezone
    cpu_model=platform.processor() or "unknown"
    cpuinfo=Path("/proc/cpuinfo")
    if cpuinfo.exists():
        cpu_model=next((line.split(":",1)[1].strip() for line in cpuinfo.read_text().splitlines()
                        if line.startswith("model name")),cpu_model)
    value={"status":"completed","passed":True,"executed_at":datetime.now(timezone.utc).isoformat(),
           "environment":"Google Colab active shell","mode":mode,"python_version":sys.version,
           "package_versions":{name:importlib.metadata.version(name) for name in ("pandas","pyarrow","nbformat","nbclient","ipykernel")},
           "runtime":{"os":platform.system(),"architecture":platform.machine(),
                      "cpu_model":cpu_model,"logical_cpu_count":os.cpu_count()},
           "window":json.loads((root/"manifest.json").read_text()).get("window"),
           "snapshot_comparison":comparison,"completed_parts":list(completed_parts)+["VIII"],
           "completed_stages":list(completed_stages),"validation_passed":True,
           "scope":"Actual Colab notebook snapshot reconstruction; not independent source or author cross-reproduction"}
    (root/"reports/colab.json").write_text(json.dumps(value,indent=2)+"\n")
    return value


def write_dictionary(root):
    from .schemas import schema_dictionary
    from .decode import SCHEMAS as DECODE_SCHEMAS
    from .events import SCHEMA as EVENT_SCHEMA
    from .provenance import SCHEMA as PROVENANCE_SCHEMA
    from .common import write_json
    dictionary=schema_dictionary()
    for name,schema in list(DECODE_SCHEMAS.items())+[("events",EVENT_SCHEMA),("provenance_requests",PROVENANCE_SCHEMA)]:
        dictionary[name]=[{"name":field.name,"type":str(field.type),"nullable":field.nullable,
                           "encoding":"JSON string" if field.name in {"decoded_arguments","attribution_evidence","evidence_record_ids","parameters","observation_window"} else "exact decimal integer string" if field.name=="amount_raw" else "native Arrow scalar"} for field in schema]
    units={"blocks":"One returned block, including explicitly marked boundary guards.",
           "transactions":"One main-window transaction in chain order, including failures and unknowns.",
           "transaction_accounts":"One recorded transaction/account/role association, not a person.",
           "evm_transaction_details":"One EVM transaction's native envelope and receipt fields.",
           "evm_logs":"One emitted EVM log in a returned receipt.",
           "solana_instructions":"One top-level or inner Solana instruction; ordering is preserved.",
           "balance_observations":"One account/asset balance observation around a transaction; not a transfer.",
           "objects":"One chain-qualified object observation within a block partition; the same object_id can occur in multiple partitions.",
           "object_relations":"One evidence-backed relationship between observed objects.",
           "decoded_records":"One attempted or recognized decode of a chain-native record.",
           "asset_movements":"One decoded or candidate movement, with execution and token-standard status.",
           "platform_records":"One recognized or attempted platform operation, preserving attribution evidence.",
           "platform_registry":"One registered platform contract/program and source layout definition.",
           "crosschain_links":"One same-address-bytes relation, without inferred common identity.",
           "events":"One versioned researcher-defined event with source evidence and parameters.",
           "provenance_requests":"One acquisition request with source, timing, outcome and context evidence."}
    meanings={"chain":"Short chain label: solana, bsc or base.","chain_id":"Network-qualified namespace; addresses are never global identities.",
              "parser_version":"Version of normalization code that generated this row.","raw_ref":"Relative raw file plus JSON pointer for evidence lookup.",
              "block_time":"Block timestamp in UTC Unix seconds; null means unknown.","height":"Chain-native block index; see slot separately on Solana.",
              "slot":"Solana slot, not an EVM block height.","window_membership":"main or boundary; only main records enter analytical population.",
              "execution_status":"Recorded transaction execution success, failed, or unknown.","fee_raw":"Exact native-asset fee integer, not a floating-point amount.",
              "is_vote":"Whether the transaction was identified as Solana vote traffic.","is_system":"Whether the transaction was identified as chain system traffic.",
              "decode_status":"Parser recognition status; unknown or unsupported does not remove raw data.","tx_index":"Transaction position within its block.",
              "outer_index":"Top-level Solana instruction index.","inner_index":"Inner-instruction position; null for top-level instruction.",
              "stack_height":"Recorded invocation depth when available.","account_indices":"JSON array of native Solana account-key indices.",
              "account_ids":"JSON array of resolved chain-qualified account identifiers.","topics":"JSON array of EVM log topics in original order.",
              "data_hex":"Uninterpreted EVM log data bytes as hexadecimal.","input_hex":"Uninterpreted EVM transaction input bytes as hexadecimal.",
              "data_raw":"Uninterpreted Solana instruction data, preserving representation.","decimals":"Recorded asset precision; null is unknown, not zero decimals.",
              "owner_address":"Recorded token-account owner when available; distinct from owning program.","owner_status":"Evidence/availability status of the owner field.",
              "pre_amount_raw":"Exact balance before the transaction, if recorded.","post_amount_raw":"Exact balance after the transaction, if recorded.",
              "source_kind":"Kind of native observation supporting the balance row.","first_seen_in_window":"Minimum non-null observed_at across the entire main window for this chain-qualified object_id; repeated consistently on its observation rows. Not lifetime creation time.",
              "type_evidence":"Recorded basis for an object-type interpretation.","token_standard":"Supported token-standard evidence, if available.",
              "metadata_status":"Availability of metadata; absent metadata is not an empty description.","observed_at":"Evidence observation timestamp; not necessarily effective start time.",
              "effective_time_status":"Whether the relation's historical effective time is known.","relation_status":"Evidence and uncertainty of the asserted relation."}
    meanings.update({"block_number_or_slot":"Canonical within-chain order key, retained when timestamps tie.",
                     "execution_meta_status":"Whether execution metadata was provided, explicit_null, missing or invalid.",
                     "inner_instructions_status":"Solana array availability: provided, explicit_null, missing or invalid; EVM not_applicable.",
                     "log_messages_status":"Solana log array availability: provided, explicit_null, missing or invalid; EVM not_applicable.",
                     "execution_effect":"committed, not_committed or unknown; attempts are not state changes.",
                     "standard_status":"Token-standard evidence; candidates differ from verified fungible tokens.",
                     "decoder_version":"Version of the rule/layout that interpreted the native record.",
                     "source_revision":"Pinned source revision or content identifier for the layout.",
                     "attribution_evidence":"JSON of address/layout provenance and historical uncertainty.",
                     "operation_type":"Decoded platform operation; not a raw sampling rule.",
                     "valid_from_block":"Known effective lower bound; null means historically unknown.",
                     "valid_to_block":"Known effective upper bound; null does not prove indefinite validity.",
                     "verification_status":"Exactly what the evidence verifies, such as address bytes only.",
                     "uncertainty_reason":"Limit on the relation or identity claim.",
                     "event_time":"UTC time derived from block time, not lifetime first activity.",
                     "definition_version":"Version of the event rule applied to fixed source facts.",
                     "evidence_record_ids":"JSON array of supporting chain-native record identifiers.",
                     "threshold":"Required distinct successful trade transaction count.",
                     "parameters":"JSON rule parameters, editable separately from raw records.",
                     "observation_window":"JSON bounded interval used by the event definition.",
                     "coverage_status":"Observation-scope qualification, not complete lifecycle coverage."})
    meanings["block_context_status"]="resolved, requested_only, unknown or conflict; a requested height alone does not prove a returned block."
    lines=["# Implemented data dictionary\n", "Generated from the Arrow schemas in `claire_demo/schemas.py`, `decode.py`, `events.py` and `provenance.py`. Each nullable field preserves unknown information; absence is never automatically zero. Raw RPC JSON remains authoritative and retains fields beyond these normalized views. Amounts and gas-related integers use exact strings where declared.\n"]
    for table,fields in dictionary.items():
        lines.extend([f"## {table}\n",units.get(table,"")+"\n","| Field | Arrow type | Encoding / meaning |\n|---|---|---|"])
        for field in fields:
            name=field["name"]
            explanation=meanings.get(name,"Stable chain-qualified identifier." if name.endswith("_id") else "Chain-native field; retain null when unavailable.")
            if table=="objects" and name=="observed_at":
                explanation="UTC Unix seconds of this object's row-level observation, using its block timestamp; null means unknown. This may be later than first_seen_in_window."
            field["description"]=explanation
            lines.append(f"| `{name}` | `{field['type']}` | {field['encoding']}; {explanation} |")
        lines.append("")
    lines += ["## Decoded and event layers\n",
              "`tables/decoded/platform_records` has one recognized or attempted platform operation with source record ID, transaction ID, token/object ID, operation type, decoder version, attribution evidence, execution effect, decode status and order. Historical registry completeness is separately qualified.\n",
              "`tables/decoded/asset_movements` has one candidate or recognized movement with asset, source/target accounts, exact amount, decimals, movement type, evidence type, execution effect, token-standard status and raw reference. Candidate records remain inspectable but are not automatically included in the token graph example.\n",
              "`tables/decoded/crosschain_links` holds literal BSC/Base address-byte equality links. Verification status concerns bytes only, not common identity, ownership or funds flow.\n",
              "`tables/events/events.parquet` has one derived event: `event_id`, `event_type`, `definition_id`, `definition_version`, `chain_id`, `subject_id`, `event_time`, `event_order`, `evidence_record_ids`, `parameters`, `observation_window`, `coverage_status`, `tx_id`, `platform_id`, `block_time`, `threshold`. Threshold events use distinct committed trade transactions; native lifecycle observations retain their own definition IDs.\n",
              "## Provenance and capabilities\n",
              "`provenance/request_log.jsonl` records method, parameters, source, retrieval timing, result/error and raw reference as implemented by acquisition. `reports/preflight.json` and `reports/coverage.csv` distinguish source capability from actual retrieved coverage. Trace and arbitrary historical state are not implied by core transaction completeness.\n"]
    write_json(root/"docs/data_dictionary.json",dictionary)
    (root/"docs/data_dictionary.md").write_text("\n".join(lines))


def run(root):
    root=Path(root)
    (root/"docs").mkdir(exist_ok=True)
    write_dictionary(root)
    cells=[]
    def md(text): cells.append(nbf.v4.new_markdown_cell(text))
    def code(text): cells.append(nbf.v4.new_code_cell(text))
    md("""# Claire: an evidence-preserving three-chain pilot

**On-chain component only.** This tutorial collects every finalized transaction
in the same five-minute interval on Solana, BSC and Base. It then separates
chain-native facts from researcher-defined events. The off-chain component and
the integration tutorial are separate work.

Default mode replays the supplied snapshot without chain access. Live mode uses
free public sources and stops if its capability or coverage checks fail. A live
query and a snapshot replay answer different reproducibility questions.
""")
    md("""## I. Overview

A **block** is a bundle of transactions accepted by a chain. A **transaction** is
a signed request to execute operations; it may succeed or fail. An EVM
**receipt** records execution status and emitted logs. Solana instead returns
transaction metadata and nested program instructions. A researcher-defined
**event**, such as a token reaching three trades, is computed later.

The population is all finalized transaction records whose block timestamp falls
in **2026-09-14 12:00:00 UTC inclusive to 12:05:00 UTC exclusive**. This is a
demonstration window, not a representative sample of launch-platform activity.
It retains unrecognized calls, failed transactions, vote and system transactions.
Adjacent blocks are saved to verify the time boundaries and are excluded from
the main analysis. Solana block times are estimates.

The contribution to the Web3AI4IO adaptation is a reusable construction and
validation workflow. It does not estimate a launchpad's causal effect, identify
people behind addresses, or label tokens as successful or fraudulent.

**D1. Data-generating process.** Actors submit transactions; chain execution
produces recorded observations. Events are interpretations of those observations.

```mermaid
{D1_MERMAID}
```
The editable source is `figures/D1.mmd`.
""")
    md("""## II. Sources and dictionary

Sources are read-only JSON-RPC interfaces: a request names a method and explicit
parameters, and a response returns chain records. `config/rpc.json` records the
candidate endpoints; `reports/preflight.json` records the endpoints actually
tested and selected. `reports/target_preflight.json` separately records checks
against the fixed historical window. A successful latest-block request is not
evidence of historical receipt access. Access results depend on environment and date.

Official method references: [Solana getBlock](https://solana.com/docs/rpc/http/getblock),
[Solana JSON structures](https://solana.com/docs/rpc/json-structures),
[BSC endpoints](https://docs.bnbchain.org/bnb-smart-chain/developers/json_rpc/json-rpc-endpoint/),
[Base RPC](https://docs.base.org/base-chain/api-reference/rpc-overview),
[Blockmachine Base RPC](https://blockmachine.io/docs/base-rpc),
[Ethereum JSON-RPC](https://ethereum.org/developers/docs/apis/json-rpc/).
The configured source candidates and access boundaries are listed in
`docs/sources.md`; actual selected providers are read from the saved reports.

IDs include the chain. Amounts remain exact integer strings with separate
decimals. `null` is unknown, and is different from zero, no matching records,
not applicable, or unavailable source access. Raw responses retain fields that
the base schema does not yet expose. The generated dictionary below describes
the actual implemented base tables, rather than a hypothetical future schema.

**Local setup:** open this notebook from the pilot directory or its `notebooks/`
folder with the supplied dependencies installed. **Colab setup:** upload
the supplied `claire-demo*.tar.gz` when prompted. The raw-only package saves upload
space and rebuilds all processed tables. There is no fabricated public download URL.
Extraction creates an isolated folder. Do not upload credentials. Installing
dependencies requires package-index access; replay itself does not use chain APIs.
""")
    code("""from pathlib import Path
import sys, os, json, gzip, subprocess, tarfile, importlib.metadata

MODE = os.environ.get("CLAIRE_DEMO_MODE", "snapshot")  # use live explicitly for recollection
try:
    from IPython import get_ipython
    _shell = get_ipython()
    IN_COLAB = ("google.colab" in sys.modules and _shell is not None
                and type(_shell).__module__.startswith("google.colab.")
                and os.environ.get("CLAIRE_NOTEBOOK_EXECUTOR") != "local")
except ImportError:
    IN_COLAB = False
INSTALL_DEPENDENCIES = IN_COLAB

def find_root():
    here = Path.cwd()
    candidates = [here, here.parent, here / "claire-threechain-v1", here / "claire-demo"]
    candidates += list(here.glob("*/claire_demo/../"))
    return next((p.resolve() for p in candidates if (p / "claire_demo/__main__.py").exists()), None)

ROOT = find_root()
if ROOT is None and IN_COLAB:
    from google.colab import files
    uploaded = files.upload()
    archives = [name for name in uploaded if name.endswith(".tar.gz")]
    if len(archives) != 1:
        raise RuntimeError("Upload exactly one supplied claire-demo*.tar.gz archive")
    destination = Path.cwd() / "claire-demo"
    destination.mkdir(exist_ok=True)
    with tarfile.open(archives[0], "r:gz") as archive:
        archive.extractall(destination, filter="data")
    ROOT = find_root()
    if ROOT is None:
        ROOT = next((p.parent for p in destination.rglob("claire_demo") if (p / "__main__.py").exists()), None)
if ROOT is None:
    raise RuntimeError("Place this notebook with the unpacked pilot snapshot")
if INSTALL_DEPENDENCIES:
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], check=True)
sys.path.insert(0, str(ROOT))
from claire_demo.build_notebook import snapshot_baseline, compare_snapshot_manifest, prepare_live_root, write_colab_receipt
# Keep this in memory before validate overwrites manifest.json after reconstruction.
SNAPSHOT_ROOT = ROOT
BASELINE_MANIFEST = snapshot_baseline(ROOT) if MODE == "snapshot" else None
LIVE_ROOT = None
COMPLETED_PARTS = ["I", "II"]
COMPLETED_STAGES = []
import pandas as pd
import pyarrow.parquet as pq
from IPython.display import display, Markdown, HTML

def report(name):
    path = ROOT / "reports" / (name + ".json")
    return json.loads(path.read_text()) if path.exists() else {"status": "not available"}

def run_stage(stage, *arguments):
    result = subprocess.run([sys.executable, "-m", "claire_demo", "--root", str(ROOT), stage, *arguments],
                            cwd=ROOT, text=True, capture_output=True)
    if result.returncode:
        print(result.stdout[-6000:])
        print(result.stderr[-2000:])
        raise RuntimeError(f"{stage} failed; inspect the saved reports before proceeding")
    COMPLETED_STAGES.append(stage)
    print(f"{stage}: completed")

def compact_report(value, max_items=12):
    if isinstance(value, dict):
        items=list(value.items())
        kept={key:compact_report(item,max_items) for key,item in items[:max_items] if key not in {"input_hashes","raw_files"}}
        omitted=len(items)-len(kept)
        if omitted: kept["omitted_entries_see_full_json"]=omitted
        return kept
    if isinstance(value,list):
        return [compact_report(x,max_items) for x in value[:max_items]] + ([f"... {len(value)-max_items} further entries in full JSON"] if len(value)>max_items else [])
    return value

display(pd.DataFrame([{"package": name, "version": importlib.metadata.version(name)}
                      for name in ["pandas", "pyarrow", "nbformat", "nbclient"]]))
dictionary_data = json.loads((ROOT / "docs/data_dictionary.json").read_text())
dictionary = pd.DataFrame([dict(table=table, **field) for table, fields in dictionary_data.items() for field in fields])
display(dictionary)
""")
    md("""## III. Acquisition

Acquisition first tests free RPC capabilities, resolves the fixed UTC window to
block heights or slots, and then saves every transaction and receipt/metadata.
It never starts from a list of platform events or popular tokens. A skipped
Solana slot and a missing RPC response are different observations. Unsupported
transaction versions remain visible and must not be silently discarded.

`preflight`, `resolve_window`, `collect`, `crosscheck` and `transaction_probe`
are network stages. After collection, cross-source checks compare bounded
independent observations; the transaction probe instead compares selected
Solana `getTransaction` responses with the saved `getBlock` records from the
same provider. That is method consistency, not independent-source confirmation.
A failed preflight or incomplete collection stops the tutorial. The snapshot branch only
inspects the saved acquisition evidence. Successful collection is demonstrated
by the reports, not assumed from the existence of a folder.

Live mode first creates a fresh `live_runs/<UTC timestamp>/` beneath the supplied
project, copying only code, configuration, source definitions, vendor files,
documentation and requirements. It never reuses the snapshot's raw cache.
Re-running this acquisition cell resumes that same explicitly displayed live
run; re-running setup starts another fresh run. Snapshot mode performs no RPC calls.

**D2. Computational workflow.** Stage implementations live in `claire_demo/`;
`raw/` contains immutable evidence, `tables/base/` normalized records,
`tables/decoded/` interpreted facts and `tables/events/` replaceable event outputs.

```mermaid
{D2_MERMAID}
```
The editable source is `figures/D2.mmd`. Live recollection cannot guarantee
historical traces, arbitrary historical Solana account states, or unchanged
future endpoint availability. Those limitations are recorded separately.
""")
    code("""if MODE not in {"snapshot", "live"}:
    raise ValueError("MODE must be snapshot or live")
if MODE == "live":
    if LIVE_ROOT is None:
        LIVE_ROOT = prepare_live_root(SNAPSHOT_ROOT)
    ROOT = LIVE_ROOT
    sys.path.insert(0, str(ROOT))
    print("Live run directory:", ROOT.relative_to(SNAPSHOT_ROOT))
    for stage in ("preflight", "resolve_window", "collect", "crosscheck", "transaction_probe"):
        run_stage(stage)
else:
    if not (ROOT / "raw").is_dir() or not (ROOT / "reports/window.json").exists():
        raise RuntimeError("Snapshot raw records or window evidence are missing")
display(report("preflight"))
display(report("target_preflight"))
resolved = report("window")
display({k:v for k,v in resolved.items() if k != "chains"})
display(pd.DataFrame([{"chain":chain, "resolved":scope.get("resolved"),
                       "main_blocks":len(scope.get("main_blocks", [])),
                       "boundary_blocks":len(scope.get("boundary_blocks", [])),
                       "skipped_slots":len(scope.get("skipped_slots", [])),
                       "uncertain_slots":len(scope.get("uncertain_slots", []))}
                      for chain,scope in resolved.get("chains", {}).items()]))
display(report("collection"))
COMPLETED_PARTS.append("III")
""")
    md("""## IV. Inspect raw data

One saved file is an RPC response envelope. Raw evidence is not reduced to the
fields needed by today's event definitions. A transaction may contain many
instructions or logs, and those nested records remain associated with the same
transaction. The code inspects one real block from each chain and one
complete transaction in an expandable JSON panel. It does not fabricate an
example when data are absent. The summary field names orient the reader; the
expandable panel preserves all returned nested content.

Request times, method parameters, source IDs, errors and raw references are in
`provenance/request_log.jsonl`. Boundary guard blocks support interval validation
and do not enter the five-minute analytical population.
""")
    code("""window = report("window")
raw_examples = []
import html
for chain in ("solana", "bsc", "base"):
    heights = window.get("chains", {}).get(chain, {}).get("main_blocks", [])
    if not heights:
        raw_examples.append({"chain": chain, "status": "unknown: no resolved main blocks"})
        continue
    path = ROOT / "raw" / chain / "blocks" / f"{heights[0]}.json.gz"
    if not path.exists():
        raw_examples.append({"chain": chain, "status": "missing raw block"})
        continue
    with gzip.open(path, "rt") as handle:
        envelope = json.load(handle)
    block = envelope["result"]
    txs = block.get("transactions", [])
    raw_examples.append({"chain": chain, "relative_file": str(path.relative_to(ROOT)),
                         "block_keys": sorted(block), "transactions_in_block": len(txs),
                         "first_transaction_keys": sorted(txs[0]) if txs else [], "status": "observed"})
    if txs:
        example={"chain":chain,"block_height_or_slot":heights[0],"transaction":txs[0]}
        receipt_path=ROOT / "raw" / chain / "receipts" / f"{heights[0]}.json.gz"
        if chain != "solana" and receipt_path.exists():
            with gzip.open(receipt_path,"rt") as handle:
                receipt_envelope=json.load(handle)
            example["receipt"]=next((r for r in receipt_envelope.get("result",[]) if r.get("transactionHash")==txs[0].get("hash")),None)
        display(HTML("<details><summary>"+html.escape(chain+": complete transaction and native execution metadata")+"</summary><pre>"+html.escape(json.dumps(example,indent=2))+"</pre></details>"))
display(pd.DataFrame(raw_examples))
COMPLETED_PARTS.append("IV")
""")
    md("""## V. Processing

Provenance processing makes the acquisition request ledger queryable while
preserving failed requests and distinguishing a requested height from a
successfully resolved block. Normalization creates typed, chain-qualified records and raw JSON-pointer
references. It preserves exact amounts, transaction order, failures and unknown
versions. It does not deduplicate distinct blockchain operations merely because
their payloads match. Stable record IDs distinguish transaction, instruction and
log positions. Re-running from the same snapshot must preserve logical content.

Decoding uses pinned platform definitions and token instruction formats. A log
that resembles an ERC-20 Transfer but lacks standard verification stays a
candidate. Solana balance changes are balance observations, not automatically
transfers. The platform registry and decoding limitations are published with
the tables.

Two event definitions then mark the first **observed within this window** point
at which a token has at least one or three distinct successful trade
transactions. Those thresholds operate on the same fixed facts. They do not
identify lifetime first trades, launch success or platform effects. Event
derivation must leave raw and base files unchanged.

This cell actually rebuilds the processed layers. It can take time on a complete
five-minute snapshot. It performs no chain API requests.
The threshold demonstration writes threshold-one and threshold-three outputs in
turn, then restores the default pair in a `finally` block. A failed demonstration
therefore does not leave a single-threshold baseline behind.
""")
    code("""for stage in ("provenance", "normalize", "decode", "derive_events"):
    run_stage(stage)
display(compact_report(report("provenance_summary")))
display(compact_report(report("normalization")))
display(compact_report(report("decode")))
display(compact_report(report("events")))

# Change the event parameter on fixed evidence, then restore the default baseline.
threshold_examples=[]
try:
    for threshold in (1, 3):
        run_stage("derive_events", "--thresholds", str(threshold))
        result=report("events")
        threshold_examples.append({"threshold":threshold,"chains":result.get("chains"),
                                   "raw_base_unchanged":result.get("raw_base_unchanged")})
finally:
    run_stage("derive_events", "--thresholds", "1", "3")
assert report("events").get("thresholds")==[1,3], "Default event baseline was not restored"
display(threshold_examples)
COMPLETED_PARTS.append("V")
""")
    md("""## VI. Inspect processed data

Inspection follows each transformation. Row counts can increase when one
transaction becomes many instructions or logs; that is not duplication. The
dictionary and the tables below identify what one row means. Missing tables
are reported explicitly. The samples are for inspection only; they do not
truncate the released records. Every implemented base and decoded table, the
event table and typed provenance are included below. Counts use Parquet metadata;
only five rows per table are loaded for preview.

`objects` contains observations, rather than one globally unique row per object.
The same chain-qualified `object_id` can appear in several block partitions.
`observed_at` is the UTC block timestamp for that row's observation.
`first_seen_in_window` is the minimum non-null `observed_at` for the same
`object_id` across the complete main window, repeated on each of its rows. A
later observation therefore retains its own time and the earlier window-level
first-seen time. Neither field establishes lifetime creation or launch time.

The second example follows one normalized transaction's `raw_ref` back to the
actual saved JSON. It then uses the same transaction ID to inspect its account,
instruction/log, balance and decoded movement records within the same block
partition. A transaction can have many such rows or none. These row counts have
different units and must not be added as though they were independent trades.
""")
    code("""def parquet_sample(path, limit=5):
    path = Path(path)
    files = sorted(path.glob("*.parquet")) if path.is_dir() else ([path] if path.exists() else [])
    sample, total = [], 0
    for file in files:
        reader = pq.ParquetFile(file)
        total += reader.metadata.num_rows
        if len(sample) < limit:
            for batch in reader.iter_batches(batch_size=limit):
                sample.extend(batch.to_pylist()[:limit-len(sample)])
                if len(sample) >= limit:
                    break
    return total if files else None, pd.DataFrame(sample)

from claire_demo.schemas import SCHEMAS as BASE_SCHEMAS
from claire_demo.decode import SCHEMAS as DECODED_SCHEMAS
tables = ([f"tables/base/{name}" for name in BASE_SCHEMAS]
          + [f"tables/decoded/{name}" for name in DECODED_SCHEMAS]
          + ["tables/events/events.parquet", "provenance/requests.parquet"])
inventory = []
for table in tables:
    n, sample = parquet_sample(ROOT / table)
    inventory.append({"table": table, "rows": n, "availability": "observed" if n is not None else "unknown"})
    display(Markdown("**" + table + "**"))
    display(sample)
display(pd.DataFrame(inventory))

from claire_demo.validate import resolve_raw_ref
import pyarrow.compute as pc
import html

# Demonstration selection only: first row of the first nonempty tx partition.
selected_path = None
selected_tx = None
for partition in sorted((ROOT / "tables/base/transactions").glob("*.parquet")):
    reader = pq.ParquetFile(partition)
    if reader.metadata.num_rows:
        selected_path = partition
        selected_tx = next(reader.iter_batches(batch_size=1)).to_pylist()[0]
        break
if selected_tx is None:
    raise RuntimeError("No normalized transaction is available for the source-reference demonstration")
native_record = resolve_raw_ref(ROOT, selected_tx["raw_ref"])
display(pd.DataFrame([selected_tx]))
display(HTML("<details><summary>Actual raw JSON resolved from this transaction's raw_ref</summary><pre>"
             + html.escape(json.dumps(native_record, indent=2)) + "</pre></details>"))

def same_partition_matches(table, tx_id, limit=5):
    path=ROOT / table / selected_path.name
    if not path.exists():
        return None, pd.DataFrame(), "unknown: partition unavailable"
    reader=pq.ParquetFile(path)
    if "tx_id" not in reader.schema_arrow.names:
        return None, pd.DataFrame(), "unknown: no transaction-key field"
    count, sample=0, []
    for batch in reader.iter_batches(batch_size=4096):
        match=batch.filter(pc.equal(batch.column(batch.schema.get_field_index("tx_id")),tx_id))
        count += match.num_rows
        if len(sample)<limit:
            sample.extend(match.slice(0,limit-len(sample)).to_pylist())
    return count, pd.DataFrame(sample), "observed in same block partition"

related_tables=["tables/base/transaction_accounts", "tables/base/solana_instructions",
                "tables/base/evm_logs", "tables/base/balance_observations",
                "tables/decoded/asset_movements", "tables/decoded/platform_records"]
related_summary=[]
for table in related_tables:
    count, sample, status=same_partition_matches(table, selected_tx["tx_id"])
    related_summary.append({"table":table,"matching_rows":count,"status":status,
                            "partition":selected_path.name})
    display(Markdown("**Linked records: " + table + "**"))
    display(sample)
display(pd.DataFrame(related_summary))
COMPLETED_PARTS.append("VI")
""")
    md("""## VII. Descriptive reuse

The figures describe construction quality and demonstrate reusable views. They
do not test substantive causal or behavioral claims. Every figure has editable
Mermaid source and linked numerical CSV tables. Figures use Mermaid only;
source and tables remain usable offline. Rendering uses a local Mermaid bundle
only if one is included; no CDN is fetched by this tutorial.

- **F1:** coverage and data availability, with unknown distinct from zero.
- **F2:** ten 30-second transaction-count bins and execution status counts and fractions, including a
  documented view excluding identified vote/system records.
- **F3:** recognized atomic platform operations per minute, limited by registry and decoder coverage, with unknown and mechanism-not-applicable distinct from zero.
- **F4:** observed token transfer graphs and shared-address relations between
  token graphs, with shared-address counts and Jaccard similarity. Solana token
  accounts are not projected to owners. Verified roles are marked; shared
  infrastructure does not prove common users or ownership.
- **F5:** one-versus-three successful trade-transaction event definitions on
  unchanged inputs, plus attainment-time differences for tokens satisfying both.

Coverage checks run immediately before figure generation so F1 uses this run's
validation receipt. Part VIII interprets the same receipt without silently
promoting it to independent reproduction or publication acceptance.

Cross-chain same-address links are literal address-byte matches between BSC and
Base. They do not merge identities. Solana addresses are not matched by spelling
to EVM addresses. A five-minute interval is not a complete token lifecycle.
""")
    code("""run_stage("validate")
run_stage("visualize")
visuals = report("visualization")
for figure in visuals.get("figures", []):
    source = (ROOT / figure["source"]).read_text()
    display(Markdown(f"### {figure['id']}. {figure['title']}\\n\\n{figure['caption']}"))
    # Editable source is always visible, including without JavaScript or network.
    display(Markdown("```mermaid\\n" + source + "```"))
    for relative in figure["inputs"]:
        import csv
        with (ROOT / relative).open(newline="") as handle:
            row_count=max(0,sum(1 for _ in csv.reader(handle))-1)
        frame = pd.read_csv(ROOT / relative, nrows=20)
        display(Markdown(f"Numerical table: `{relative}` ({row_count:,} rows; first 20 shown)"))
        display(frame)

import html
html_sections = []
for figure in visuals.get("figures", []):
    source = (ROOT / figure["source"]).read_text()
    html_sections.append("<h3>" + html.escape(figure["id"]) + "</h3><pre class='mermaid'>" + html.escape(source) + "</pre>")
local_mermaid = ROOT / "vendor/mermaid.min.js"
renderer = ("<script>(function(){const define=undefined,exports=undefined,module=undefined;" + local_mermaid.read_text() + "})();mermaid.initialize({startOnLoad:false,securityLevel:'strict',maxTextSize:1000000,maxEdges:10000});mermaid.run({querySelector:'.mermaid'});</script>") if local_mermaid.exists() else "<p>Offline source view: no local Mermaid bundle is installed. Editable sources and numerical tables remain available.</p>"
display(HTML("".join(html_sections) + renderer))
COMPLETED_PARTS.append("VII")
""")
    md("""## VIII. Technical validation and handoff

Validation checks the fixed window, adjacent block ancestry, raw and normalized
transaction order, receipt correspondence, exact amount representation, and
raw-reference resolution. It reports actual checks, not a prefilled PASS.
Checksums establish file consistency; they do not independently prove a source
is correct. Independent source comparison, offline replay and Colab execution
have separate receipts.
The transaction-probe receipt tests agreement between two RPC methods at one
source. It is explicitly separate from independent cross-source corroboration.

The validation stage immediately before figure generation is mandatory. Failure
stops execution; the cell below inspects the same current receipt. The recorded
`snapshot_replay` and `colab_compatibility` fields must not be promoted to success
unless their separate tests actually ran. Local completion comes first; Colab
compatibility is tested afterward. Claire/Shilin cross-reproduction is still a
distinct author handoff, and is not inferred from automated tests.

Snapshot setup retained the supplied manifest before reconstruction. Below, every
raw-file hash and every processed-table semantic hash is compared with that
initial baseline. A mismatch stops the notebook. In a real Google Colab runtime,
completion of all prior parts, technical validation and this comparison writes
`reports/colab.json` with the actual runtime and package versions. Local execution
cannot write a Colab success receipt. Live mode records its new acquisition and
validation results separately; it does not claim uploaded-snapshot equality.

Reusable outputs: raw snapshot and provenance, base/decoded Parquet tables,
event definitions and event table, dictionary, Mermaid sources, numerical CSVs,
and reports. The off-chain and integration components can later link using
chain-qualified object IDs, explicit time scopes and documentary evidence.
They are not implemented or claimed in this notebook.
The reusable join contract is `config/handoff_interface.json`, explained in
`docs/handoff.md`; it keeps observation times and documentary evidence explicit.

Reference framing: [DIVE](https://www.nature.com/articles/s41597-026-07025-5)
for construction and validation documentation; [Multi-Chain Graphs of Graphs](https://proceedings.neurips.cc/paper_files/paper/2024/file/3205b048f9cc54b9f7963db0b0f52d53-Paper-Datasets_and_Benchmarks_Track.pdf)
for a methodological example of graph-based reuse. Their original inclusion
rules and research claims are not inherited by this pilot.
""")
    code("""validation = report("validation")
display(pd.DataFrame(validation.get("checks", [])))
display(validation.get("counts", {}))
assert validation.get("passed") is True, "Technical validation did not pass"
if MODE == "snapshot":
    snapshot_comparison = compare_snapshot_manifest(BASELINE_MANIFEST, json.loads((ROOT / "manifest.json").read_text()))
    display(snapshot_comparison)
    assert snapshot_comparison["passed"], "Rebuilt raw files or semantic tables differ from the initial snapshot manifest"
else:
    snapshot_comparison = {"passed":False, "status":"not_applicable_to_fresh_live_collection"}
colab_result = write_colab_receipt(ROOT, MODE, COMPLETED_PARTS, COMPLETED_STAGES, snapshot_comparison)
display(compact_report(colab_result))
for name in ("cross_source", "transaction_probe", "reproduction", "notebook_execution", "colab"):
    display(Markdown("**Separate receipt: " + name + "**"))
    display(compact_report(report(name)))
display(Markdown("The current notebook execution receipt can say running until the external executor finishes. This notebook does not recursively require its own completion receipt."))
display(Markdown("See `docs/limitations.md` and `docs/data_dictionary.md` for reuse boundaries."))
COMPLETED_PARTS.append("VIII")
""")
    from .visualize import method_diagrams
    for key,(_,source,_) in method_diagrams().items():
        path=root/"figures"/(key+".mmd")
        path.parent.mkdir(exist_ok=True)
        path.write_text(source)
        for cell in cells:
            if cell["cell_type"]=="markdown":
                cell["source"]=cell["source"].replace("{"+key+"_MERMAID}",path.read_text().strip())
    for i,cell in enumerate(cells):
        cell["id"]=hashlib.sha256((str(i)+cell["source"]).encode()).hexdigest()[:12]
    notebook=nbf.v4.new_notebook(cells=cells,metadata={"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.12"},"colab":{"provenance":[]},"claire_demo":{"component":"on-chain only","default_mode":"snapshot","parts":8}})
    target=root/"notebooks/Claire_Onchain_Tutorial.ipynb"
    target.parent.mkdir(parents=True,exist_ok=True)
    nbf.validate(notebook)
    nbf.write(notebook,target)
    return {"notebook":str(target.relative_to(root)),"cells":len(cells),"parts":8}


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=Path.cwd())
    print(json.dumps(run(parser.parse_args().root),indent=2))
