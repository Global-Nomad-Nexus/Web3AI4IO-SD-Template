"""Build the two editable real-data Colabs from a pinned, small public release."""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf


ROOT = Path(__file__).resolve().parents[2]
COMMIT = "1fec501de1de09d9cc2b9c69ce350338a40af889"
BASE = f"https://github.com/Global-Nomad-Nexus/Web3AI4IO-SD-Template/blob/{COMMIT}/pilots/shilin-offchain-v1"
RAW = f"https://raw.githubusercontent.com/Global-Nomad-Nexus/Web3AI4IO-SD-Template/{COMMIT}/pilots/shilin-offchain-v1"
HF = "https://huggingface.co/datasets/global-nomad-nexus/claire-threechain-v1/tree/8b29598a6565b67a8a943962dbf77f3d6b2559de"


def md(value: str):
    return nbf.v4.new_markdown_cell(value.strip())


def code(value: str):
    return nbf.v4.new_code_cell(value.strip())


SETUP = f'''
import os, sys, json, hashlib, tarfile, tempfile, urllib.request
from collections import Counter
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq

CODE_COMMIT = "{COMMIT}"
EXPECTED_ARROW = "25.0.1"
if pa.__version__ != EXPECTED_ARROW:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", f"pyarrow=={{EXPECTED_ARROW}}"])
    print("Restart the runtime, then run from the first cell to use the pinned PyArrow version.")
    raise SystemExit(0)

local = os.environ.get("PILOT_LOCAL_REPO")
if local:
    ROOT = Path(local).expanduser().resolve()
    print("Local test checkout:", ROOT)
else:
    url = f"https://codeload.github.com/Global-Nomad-Nexus/Web3AI4IO-SD-Template/tar.gz/{{CODE_COMMIT}}"
    request = urllib.request.Request(url, headers={{"User-Agent": "shilin-offchain-pilot-colab/1.0"}})
    body = urllib.request.urlopen(request, timeout=90).read()
    tmp = Path(tempfile.mkdtemp(prefix="shilin-pilot-"))
    archive = tmp / "repo.tar.gz"
    archive.write_bytes(body)
    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
        prefix = names[0].split("/")[0]
        tar.extractall(tmp, filter="data")
    ROOT = tmp / prefix
    print("Downloaded pinned code and release:", CODE_COMMIT)

PILOT = ROOT / "pilots" / "shilin-offchain-v1"
RELEASE = PILOT / "release"
sys.path.insert(0, str(PILOT))
from verify_release import verify
verification = verify(RELEASE)
assert verification["passed"], verification
manifest = json.loads((RELEASE / "release_manifest.json").read_text())
print("Fixed release verified:", verification)
print("PyArrow:", pa.__version__)
print("Claire input revision:", manifest["claire_hf_revision"])
'''


def part(title: str, number: int, body: str):
    return md(f'<a id="part-{number}"></a>\n## Part {number} — {title}\n\n{body}')


def make_offchain():
    cells = [
        md(f'''# Off-chain pilot: public token metadata and evidence-level linkage

**Lead:** Shilin. **Independent coauthor reproduction:** Claire, pending. **Pilot date:** 17 September 2026 UTC. This editable Colab uses real Pump.fun creation URIs from Claire's pinned on-chain data and a bounded live metadata request. It also replays a fixed, rights-limited output snapshot so results remain inspectable if a gateway changes. Start with a fresh CPU runtime and run in order.

[Proposal and editable Mermaid diagrams]({BASE}/PROPOSAL.md) · [Data dictionary]({BASE}/DATA_DICTIONARY.md) · [Code]({BASE}) · [Fixed release]({BASE}/release) · [Claire source]({HF}). The complete source receipts, method, and actual validation are in the linked release. The fixed release excludes third-party response bodies because redistribution rights have not been cleared.'''),
        part('Overview and navigation', 1, '''A blockchain creation record may contain a metadata URI. A URI is a pointer, not the metadata itself. We request the exact URI, preserve the response time and hash, parse named JSON fields, then make field-level assertions tied to both the chain event and retrieved response. A website or social link is a declaration in that response, not proof of account ownership or presence at creation time.

1. [Overview](#part-1)  2. [Sources and dictionary](#part-2)  3. [Acquisition](#part-3)  4. [Inspect acquired records](#part-4)  5. [Processing](#part-5)  6. [Inspect processed records](#part-6)  7. [Descriptive reuse](#part-7)  8. [Validation and handoff](#part-8).

Run each code cell after reading its preceding explanation. The fixed snapshot is approximately 250 KB, requires no login or GPU, and is suitable for a fresh Colab. Live gateway access can vary; the notebook reports that result separately.'''),
        part('Sources, metadata and data dictionary', 2, f'''**Sampling frame.** Claire's immutable three-chain snapshot covers 2026-09-14 12:00:00 ≤ block time < 12:05:00 UTC. We select committed, decoded, nonempty-object creation records, yielding 116 events: 61 Pump.fun on Solana, 55 Four.meme on BSC, and zero recognized Clanker creations on Base. Events and distinct chain-qualified tokens are both counted; this is a five-minute engineering pilot, not a representative launch sample.

**Access.** Pump.fun creation events supply exact metadata URIs. Original URIs often use `https://ipfs.io/ipfs/<CID>`; the collection tried that gateway and then `https://gateway.pinata.cloud/ipfs/<CID>` on HTTP 429. The live cell requests one exact CID through Pinata with a declared 30-second timeout. [Collection code]({BASE}/collect_metadata.py) preserves attempts, response status, retrieval UTC, byte count and SHA-256. Four.meme's documented exact-address endpoint `https://four.meme/meme-api/v1/private/token/get/v2?address=<contract>` returned HTTP 403 in three spaced probes; those requests and 52 unprobed BSC events remain visible. No API key is used.

**Units and key fields.** `onchain_launch_cohort`: creation event, `launch_record_id` primary key, `object_id` chain-qualified token, `chain_event_time_utc`, `metadata_uri_declared`. `offchain_snapshots`: one successful response per URI, `snapshot_id`, `retrieved_at_utc`, `raw_sha256`, `parse_status`. `offchain_declarations`: one JSON field URL, `snapshot_id`, `field_name`, `json_pointer`, `target_class`. `coverage_ledger`: one row per event including failures. Full types, null semantics, keys and rights are in the [dictionary]({BASE}/DATA_DICTIONARY.md) and [rights register]({BASE}/rights_sources.csv). Source revision and hashes are in `release_manifest.json`.

**Diagram.** <img src="{RAW}/figures/dgp.svg" width="900" alt="Editable data generating process diagram" />

```mermaid
flowchart LR
 A[Creator enters token details] --> B[Launch platform]
 B --> C[On-chain creation event]
 B -. may declare .-> D[Metadata URI]
 D --> E[Retrieved JSON response]
 E --> F[Website or social URL field]
 C --> G[Evidence-backed assertion]
 F --> G
```

The solid arrows are recorded activities or evidence paths; the dotted arrow is contingent. Chain time and retrieval time are different observations. This Mermaid source and the full editable diagram in the proposal can be changed by both authors.'''),
        code(SETUP),
        part('Query or acquire real data', 3, f'''The original acquisition processed **57 distinct URIs in 94 HTTP attempts**. It saved local response bytes and a request ledger; this public release keeps hashes, request metadata and extracted factual fields. The cell below makes a fresh real HTTP request for one CIDv1 item from the cohort. It prints current status, size, SHA-256 and three covered fields. A changed response or failed gateway is evidence about **today's** access, not a reason to rewrite the fixed 17 September snapshot. [Acquisition code]({BASE}/collect_metadata.py).'''),
        code('''from urllib.error import HTTPError, URLError
from datetime import datetime, timezone
LIVE_URL = "https://gateway.pinata.cloud/ipfs/bafkreih4am23irlugdsonanclckaxerem23hznxn5tl424ji3rokqzq4ze"
live_result = {"url": LIVE_URL, "checked_at_utc": datetime.now(timezone.utc).isoformat()}
try:
    request = urllib.request.Request(LIVE_URL, headers={"User-Agent": "shilin-offchain-pilot-colab/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read(2_000_001)
        live_result.update(status=response.status, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        if len(raw) > 2_000_000: raise ValueError("Live response exceeds 2 MB guard")
        document = json.loads(raw)
        live_result["covered_fields"] = {key: document.get(key) for key in ("website", "twitter", "telegram")}
except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
    live_result["error"] = str(exc)
print(json.dumps(live_result, indent=2))
assert live_result.get("status") == 200 or "error" in live_result'''),
        part('Inspect acquired records', 4, '''Read the fixed request receipt and cohort before any link analysis. The original 94 attempts include failed first-gateway responses; 57 distinct URI response snapshots succeeded. HTTP failures are not missing records in the denominator and do not imply no online presence. Compare the live one-row result above to the fixed snapshot only as a current re-fetch check.'''),
        code('''from collections import Counter
requests = [json.loads(line) for line in (RELEASE / "offchain_requests.jsonl").read_text().splitlines() if line]
cohort = pq.read_table(RELEASE / "onchain_launch_cohort.parquet").to_pylist()
snapshots = pq.read_table(RELEASE / "offchain_snapshots.parquet").to_pylist()
print("Creation events by platform:", dict(Counter(x["platform_id"] for x in cohort)))
print("HTTP attempts/status:", len(requests), dict(Counter(str(x.get("status_code")) for x in requests)))
print("Successful parsed response snapshots:", len(snapshots), dict(Counter(x["parse_status"] for x in snapshots)))
print("First cohort record:", {k:cohort[0].get(k) for k in ("launch_record_id","object_id","chain_event_time_utc","metadata_uri_declared")})
print("First response:", {k:snapshots[0][k] for k in ("snapshot_id","retrieved_at_utc","raw_sha256","parse_status")})
frozen_example = next(x for x in snapshots if x["snapshot_id"] == "snap:f5b91dff52b0588cd2795b4e")
print("Same bytes as 17 Sep snapshot?", live_result.get("sha256") == frozen_example["raw_sha256"] if "sha256" in live_result else "live fetch unavailable")'''),
        part('Process data and document decisions', 5, f'''[Processing code]({BASE}/process_linkage.py) parses JSON objects, reads only nonempty `website`, `twitter`, and `telegram` URL fields, normalizes URLs, classifies targets, and attaches each value to an exact response snapshot and on-chain URI assertion. A social post in a `website` field retains the field label and receives `target_class=social_post`; it is never promoted to a verified website. Duplicate creation records are removed by deterministic event key in [cohort code]({BASE}/build_cohort.py); shared URIs produce one response snapshot but retain their event-level joins. No fuzzy name or ticker match is accepted.

<img src="{RAW}/figures/pipeline.svg" width="1000" alt="Editable acquisition and processing pipeline" />

```mermaid
flowchart LR
 A[Claire pinned decoded records] --> B[Creation cohort]
 B --> C[Exact URI requests]
 C --> D[Receipt and response hash]
 D --> E[JSON field extraction]
 E --> F[Candidate + evidence + assertion]
 F --> G[Coverage and validation]
```

Each stage's input, output, filter and check is in the [proposal stage map]({BASE}/PROPOSAL.md). Raw bytes remain local pending source rights review; public fixed tables permit integration replay, while live re-fetch permits a current parsing demonstration.'''),
        code('''declarations = pq.read_table(RELEASE / "offchain_declarations.parquet").to_pylist()
evidence = pq.read_table(RELEASE / "linkage_evidence.parquet").to_pylist()
assertions = pq.read_table(RELEASE / "linkage_assertions.parquet").to_pylist()
coverage = pq.read_table(RELEASE / "coverage_ledger.parquet").to_pylist()
print("Declaration fields:", dict(Counter(x["field_name"] for x in declarations)))
print("URL target classes:", dict(Counter(x["target_class"] for x in declarations)))
print("Coverage states:", dict(Counter(x["coverage_state"] for x in coverage)))
print("Evidence and assertions:", len(evidence), len(assertions))
assert len(coverage)==len(cohort)==116
assert sum(x["coverage_state"]=="declaration_observed" for x in coverage)==29'''),
        part('Inspect processed evidence', 6, '''Follow one actual assertion across the event, response and JSON pointer. The on-chain event fixes the token and declared URI at creation. The later response provides the field value. It does **not** prove the destination page was live at creation. The manually reviewed case and a misleading website-field example are recorded in `REVIEW_EXAMPLES.md`.'''),
        code('''case = next(x for x in assertions if x["assertion_id"] == "assert:136781253019bac2c496113b")
case_evidence = [x for x in evidence if x["evidence_id"] in case["evidence_ids"]]
case_snapshot = next(x for x in snapshots if x["snapshot_id"] == "snap:f5b91dff52b0588cd2795b4e")
print("Assertion:", {k:case[k] for k in ("object_id","relation_type","right_value","chain_event_time_utc","first_verified_at_utc","as_of_eligibility")})
print("Evidence:", [{k:x[k] for k in ("evidence_kind","raw_ref","snapshot_id","field_pointer")} for x in case_evidence])
print("Snapshot:", {k:case_snapshot[k] for k in ("original_uri","retrieved_at_utc","raw_sha256","cid_integrity_status")})
misleading = next(x for x in assertions if x["assertion_id"] == "assert:b7f1d653c3ab85ec9143ae43")
print("Field/target mismatch:", misleading["relation_type"], misleading["right_value"])
assert case["as_of_eligibility"] == misleading["as_of_eligibility"] == "unknown"'''),
        part('Small descriptive example and reuse', 7, '''The unit below is an eligible creation event. Report how many have at least one covered link field in a retrieved JSON object, while keeping all 116 events in the denominator. This is **source coverage**, not a measure of project quality, adoption, identity or token success. The five-minute window and source access conditions limit generalization.

The [DIVE Data Descriptor](https://doi.org/10.1038/s41597-026-07025-5) informs documentation and measured technical validation; [Multi-Chain Graphs of Graphs](https://proceedings.neurips.cc/paper_files/paper/2024/file/3205b048f9cc54b9f7963db0b0f52d53-Paper-Datasets_and_Benchmarks_Track.pdf) §3.2 motivates explicit chain-specific sampling and source provenance. Their methods and time spans are not claimed as our pilot results.'''),
        code('''by_platform = {}
for platform in sorted({x["platform_id"] for x in coverage}):
    rows = [x for x in coverage if x["platform_id"] == platform]
    by_platform[platform] = {"events": len(rows), "declared_field_events": sum(x["coverage_state"] == "declaration_observed" for x in rows), "states": dict(Counter(x["coverage_state"] for x in rows))}
print(json.dumps(by_platform, indent=2))
print("Overall observed field declarations:", sum(x["coverage_state"] == "declaration_observed" for x in coverage), "/", len(coverage))
assert by_platform["pump.fun"]["declared_field_events"] == 29'''),
        part('Technical validation and coauthor handoff', 8, f'''Run the public fixed-release verifier below. The original source-side validation checks response hashes against saved local bytes, three sampled raw Pump event re-decodes, foreign keys, denominator, CIDv1 raw SHA-256, and time rules; its measured report is [here]({BASE}/release/validation_report.md). This public verification checks published file hashes, row counts, keys and temporal flags. The fixed release has 57 JSON snapshots, 39 URL field declarations and 100 evidence-backed assertions. CIDv0 DAG-PB content was not cryptographically verified, and BSC API access was restricted here.

**Coauthor review requested:** Claire should run this notebook in a fresh runtime, inspect at least one raw event-to-URI path and one field-to-response path, record runtime/version and any disagreement, then send corrections before a coordinated submission. This execution alone is not that independent review. A formal Data Descriptor also needs a larger justified cohort, durable archive/rights decision and further validation.'''),
        code('''result = verify(RELEASE)
print(json.dumps(result, indent=2))
source_validation = json.loads((RELEASE / "validation.json").read_text())
print("Source-side validation:", source_validation.get("overall_status", source_validation.get("passed")))
assert result["passed"] and result["cohort_events"] == 116
print("Completed fixed-snapshot off-chain tutorial. Record live_result separately in any review receipt.")'''),
    ]
    return cells


def make_integration():
    cells = [
        md(f'''# Integration pilot: creation events, metadata declarations, uncertainty

**Joint responsibility:** Claire and Shilin. **Independent joint review:** pending. This editable Colab joins Claire's pinned real on-chain records to Shilin's real off-chain pilot through exact event IDs and evidence. It starts from a fixed public snapshot in a fresh CPU runtime; it preserves unmatched and access-restricted events.

[Integration proposal and diagrams]({BASE}/PROPOSAL.md) · [Shilin code/data]({BASE}) · [Claire pinned input]({HF}) · [Dictionary]({BASE}/DATA_DICTIONARY.md). This is an engineering checkpoint for a possible *Scientific Data* descriptor, not a population estimate.'''),
        part('Overview and navigation', 1, '''The integration unit is one committed decoded token creation event, identified by `launch_record_id`. Each event is retained, even if no off-chain request was possible. A linked URL is an observed declaration with two evidence paths: the creation event supplied a URI, and a later response contained the URL field. We do not infer ownership or creation-time site state.

1. [Overview](#part-1)  2. [Component releases](#part-2)  3. [Acquire fixed inputs](#part-3)  4. [Inspect compatibility](#part-4)  5. [Join and validate](#part-5)  6. [Inspect links and unknowns](#part-6)  7. [Descriptive reuse](#part-7)  8. [Technical validation and handoff](#part-8).'''),
        part('Two real component releases and the linkage contract', 2, f'''Claire's versioned [on-chain release]({HF}) provides three-chain raw and decoded observations for **2026-09-14 12:00:00–12:05:00 UTC**. The event-level selection implemented by [build_cohort.py]({BASE}/build_cohort.py) gives 61 Pump.fun and 55 Four.meme committed creations, with zero recognized Clanker creations. `creation_source_record_id`, `creation_raw_ref`, decoder version and Claire revision remain in the cohort. Shilin's [fixed release]({BASE}/release) contains response snapshots, declarations, exact candidates, evidence, typed assertions and a total coverage ledger.

**Join contract:** `launch_record_id` joins cohort to coverage and candidates; `object_id` is a chain-qualified token; `candidate_id` joins to evidence and assertion; `snapshot_id` joins declarations to the retrieved response. Exact on-chain URI is accepted as a direct declaration. A JSON field URL is accepted only as a claim in that response. Similar names and symbols never auto-link. `chain_event_time_utc` dates creation; `retrieved_at_utc` dates our observation; source-claimed publication dates are not verified and are not silently substituted. `as_of_eligibility=unknown` on response-derived links prevents retrospective leakage.

<img src="{RAW}/figures/dgp.svg" width="900" alt="Data generating process diagram" />

```mermaid
flowchart LR
 A[Creator/platform] --> B[Chain creation event]
 A -. contingent .-> C[Metadata URI and JSON]
 B --> D[Creation cohort]
 C --> E[Timed response snapshot]
 D --> F[Exact evidence-backed assertion]
 E --> F
```

The dotted path can fail or change over time. Full editable captions and stage descriptions are in the proposal.'''),
        code(SETUP),
        part('Acquire the fixed, versioned inputs', 3, '''The setup downloads an immutable GitHub commit, verifies every release file size and SHA-256 against `release_manifest.json`, then reads seven Parquet tables. The source collection itself used real HTTP requests and Claire's pinned Parquet; this notebook deliberately starts from the released snapshot so a future reader can reproduce the join after websites change. A current live request is demonstrated in the companion off-chain notebook.'''),
        code('''TABLES = {name: pq.read_table(RELEASE / (name + ".parquet")).to_pylist() for name in ("onchain_launch_cohort","offchain_snapshots","offchain_declarations","linkage_candidates","linkage_evidence","linkage_assertions","coverage_ledger")}
print("Rows by table:", {name:len(rows) for name,rows in TABLES.items()})
print("Pinned Claire revision:", manifest["claire_hf_revision"])
print("Sample creation source:", {k:TABLES["onchain_launch_cohort"][0][k] for k in ("launch_record_id","object_id","creation_raw_ref","chain_event_time_utc")})'''),
        part('Inspect compatibility and record counts', 4, '''Before joining, inspect units, uniqueness, source revision and missing keys. `launch_record_id` is an event key, not a token symbol. Four.meme has no exact metadata URI in the decoded event; three exact-address API probes returned 403 and 52 remain unattempted. Pump.fun has 61 event URIs but 57 distinct URI values. The difference is deduplication of requests, not disappearance of events.'''),
        code('''cohort = TABLES["onchain_launch_cohort"]
coverage = TABLES["coverage_ledger"]
assert len(cohort) == len(coverage) == 116
assert len({x["launch_record_id"] for x in cohort}) == 116
assert {x["launch_record_id"] for x in coverage} == {x["launch_record_id"] for x in cohort}
assert {x["claire_hf_revision"] for x in cohort} == {manifest["claire_hf_revision"]}
print("By platform:", dict(Counter(x["platform_id"] for x in cohort)))
print("Unique tokens:", len({x["object_id"] for x in cohort}))
print("Coverage:", dict(Counter(x["coverage_state"] for x in coverage)))
print("Nonempty/distinct metadata URIs:", sum(bool(x["metadata_uri_declared"]) for x in cohort), len({x["metadata_uri_declared"] for x in cohort if x["metadata_uri_declared"]}))'''),
        part('Process the exact join and preserve uncertainty', 5, f'''The left join keeps all 116 cohort events. Assertions are one-to-many: a token can have its on-chain URI assertion and several JSON field URL assertions. We therefore do not count assertion rows as tokens. The [processing implementation]({BASE}/process_linkage.py) creates candidates and evidence and the [validation code]({BASE}/validate_pilot.py) checks foreign keys and time. The diagram can be edited in the [proposal]({BASE}/PROPOSAL.md).

<img src="{RAW}/figures/pipeline.svg" width="1000" alt="Integration pipeline" />

```mermaid
flowchart LR
 A[Claire creation cohort] --> C[Exact event URI]
 B[Shilin response snapshots] --> D[JSON field URLs]
 C --> E[Candidate and evidence]
 D --> E
 E --> F[Typed assertions]
 F --> G[116-row coverage ledger]
```

Any URI failure, absent field, 403, or unattempted BSC address stays separate. A `no_declaration` label means no covered URL field in a successful JSON response; it does not imply no online presence.'''),
        code('''by_id = {x["launch_record_id"]:x for x in coverage}
joined = [{**x, "coverage_state":by_id[x["launch_record_id"]]["coverage_state"], "snapshot_id":by_id[x["launch_record_id"]]["snapshot_id"]} for x in cohort]
assert len(joined) == 116 and len({x["launch_record_id"] for x in joined}) == 116
assert sum(x["coverage_state"]=="declaration_observed" for x in joined)==29
assert sum(x["coverage_state"]=="no_declaration" for x in joined)==32
assert sum(x["coverage_state"]=="access_restricted_here" for x in joined)==3
assert sum(x["coverage_state"]=="not_attempted" for x in joined)==52
print("Joined event rows:", len(joined), "state counts:", dict(Counter(x["coverage_state"] for x in joined)))'''),
        part('Inspect positive, unmatched and time-uncertain cases', 6, '''The Morfik case has an exact on-chain URI and a later JSON `/website` value. Another JSON places an X post URL in a `website` field, so the released type remains `declares_website_field_url` with `target_class=social_post`. A third successful JSON has no covered URL field. Three Four.meme exact-address probes are `access_restricted_here`; 52 have `not_attempted`. No BSC positive link is fabricated. [Manual spot review](''' + BASE + '''/REVIEW_EXAMPLES.md).'''),
        code('''assertions = TABLES["linkage_assertions"]
evidence = TABLES["linkage_evidence"]
declarations = TABLES["offchain_declarations"]
examples = {kind:next(x for x in joined if x["coverage_state"]==kind) for kind in ("declaration_observed","no_declaration","access_restricted_here","not_attempted")}
for kind,row in examples.items():
    print(kind, row["launch_record_id"], row["object_id"], "snapshot", row["snapshot_id"])
morfik = next(x for x in assertions if x["assertion_id"] == "assert:136781253019bac2c496113b")
print("Morfik evidence:", morfik["right_value"], morfik["evidence_ids"], morfik["as_of_eligibility"])
print("Morfik evidence types:", [(x["evidence_kind"],x["field_pointer"]) for x in evidence if x["evidence_id"] in morfik["evidence_ids"]])
print("Website-field social posts:", sum(x["field_name"]=="website" and x["target_class"]=="social_post" for x in declarations))
assert all(x["as_of_eligibility"]=="unknown" for x in assertions if x["relation_type"]!="declares_metadata_uri")'''),
        part('Descriptive example for research reuse', 7, '''The following table counts event-level coverage by chain/platform. It is useful for understanding where this pilot has link evidence and where a source blocks access. It is not a success rate or statement about the projects. The 39 declaration rows come from 29 Pump.fun token events; 100 assertion rows include 61 direct URI assertions. Keep denominators and units explicit.

[DIVE](https://doi.org/10.1038/s41597-026-07025-5) models transparent data construction and technical validation; [Multi-Chain Graphs of Graphs](https://proceedings.neurips.cc/paper_files/paper/2024/file/3205b048f9cc54b9f7963db0b0f52d53-Paper-Datasets_and_Benchmarks_Track.pdf) §3.2 motivates a clear chain-specific frame. Our five-minute slice cannot stand in for their longer histories.'''),
        code('''summary = {}
for platform in sorted({x["platform_id"] for x in joined}):
    rows = [x for x in joined if x["platform_id"]==platform]
    summary[platform] = {"creation_events":len(rows), "coverage_states":dict(Counter(x["coverage_state"] for x in rows))}
print(json.dumps(summary, indent=2))
print("Field URL declarations:", len(declarations), "typed assertions:", len(assertions))
assert len(declarations)==39 and len(assertions)==100'''),
        part('Validation, interpretation and handoff', 8, f'''The fixed verifier checks every public file hash and row count, event and coverage keys, evidence foreign keys and temporal flags. Original source-side checks also rehash 94 local HTTP response bodies and re-decode three Claire raw Pump events; the [actual report]({BASE}/release/validation_report.md) records 13 passing checks. The released raw response bytes are withheld pending redistribution review, so offline readers can verify the released join but must re-fetch live metadata for an independent parse. Current source data can change. CIDv0 DAG-PB content was not cryptographically checked. Independent Claire review and joint notebook execution must be recorded by both authors before telling the supervisor that cross-reproduction is complete.

The larger *Scientific Data* Data Descriptor still needs a justified publication cohort, source-rights resolution, archival identifier and broader technical validation. This pilot establishes a bounded, inspectable workflow.'''),
        code('''result = verify(RELEASE)
print(json.dumps(result, indent=2))
assert result["passed"] and result["coverage_states"] == {"access_restricted_here":3,"not_attempted":52,"no_declaration":32,"declaration_observed":29}
print("Completed fixed-snapshot integration tutorial; coauthor review remains a separate recorded step.")'''),
    ]
    return cells


def save(path: Path, cells):
    notebook = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python"}})
    nbf.validate(notebook)
    nbf.write(notebook, path)
    print(path, len(cells), "cells")


if __name__ == "__main__":
    save(ROOT / "notebooks/02_Off_Chain_Tutorial.ipynb", make_offchain())
    save(ROOT / "notebooks/03_Integration_Tutorial.ipynb", make_integration())
