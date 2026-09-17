"""Build an eight-part editable tutorial over Shilin's pinned v2 release."""

from pathlib import Path

import nbformat as nbf


ROOT = Path(__file__).resolve().parents[2]
COMMIT = "0655881"
BASE = f"https://github.com/Global-Nomad-Nexus/Web3AI4IO-SD-Template/blob/{COMMIT}/pilots/shilin-offchain-v2"


def md(value):
    return nbf.v4.new_markdown_cell(value.strip())


def code(value):
    return nbf.v4.new_code_cell(value.strip())


def part(number, title, body):
    return md(f'<a id="part-{number}"></a>\n## Part {number} — {title}\n\n{body}')


def build():
    cells = [
        md(f'''# Shilin's off-chain evidence extension

**Scope:** Claire's fixed 116 creation events, with more off-chain observations and technical checks. **Lead:** Shilin. **Independent coauthor review:** pending. This supplement leaves Claire's work and Shilin v1 unchanged.

[Protocol]({BASE}/EXTENSION_PROTOCOL.md) · [Measured results]({BASE}/VALIDATION_REPORT.md) · [Dictionary]({BASE}/DATA_DICTIONARY.md) · [Code and tables]({BASE}). Run all eight parts in order in a fresh CPU runtime.'''),
        part(1, "Question and navigation", '''A chain event can declare a metadata URI. A later request to that URI can return JSON; the JSON can declare an image, website or social URL. We record each observation and its time so that another researcher can inspect the connection. A retrieved URL is not proof of creator ownership or creation-time availability.

1. [Overview](#part-1)  2. [Sources](#part-2)  3. [Acquisition](#part-3)  4. [Inspect source records](#part-4)  5. [Processing](#part-5)  6. [Inspect linked data](#part-6)  7. [Descriptive example](#part-7)  8. [Validation and reuse](#part-8).'''),
        part(2, "Sources, units and diagram", f'''Claire's [unchanged release](https://huggingface.co/datasets/global-nomad-nexus/claire-threechain-v1/tree/8b29598a6565b67a8a943962dbf77f3d6b2559de) covers 2026-09-14 12:00–12:05 UTC. Shilin v1 selected 116 eligible creation events: 61 Pump.fun, 55 Four.meme, and zero recognized Clanker creations. V2 uses all 57 distinct Pump JSON snapshots, including those without website fields. The unit may be an event, response, field, image URI or request; each table in the [dictionary]({BASE}/DATA_DICTIONARY.md) says which.

<img src="https://raw.githubusercontent.com/Global-Nomad-Nexus/Web3AI4IO-SD-Template/{COMMIT}/pilots/shilin-offchain-v1/figures/pipeline.svg" width="900" alt="Source-to-linkage pipeline" />

```mermaid
flowchart LR
 A[Claire creation event] --> B[Declared metadata URI]
 B --> C[Shilin v1 JSON snapshot]
 B --> D[Second metadata request]
 C --> E[Field audit]
 C --> F[Declared image URI]
 F --> G[Image request and digest]
 E --> H[Review flags and coverage]
 D --> H
 G --> H
```

Each arrow is a recorded source or processing step. Chain event time and off-chain retrieval time are different.'''),
        code(f'''import os, sys, json, tarfile, tempfile, urllib.request
from pathlib import Path
from collections import Counter
try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "pyarrow>=23,<26"])
    import pyarrow as pa
    import pyarrow.parquet as pq

COMMIT = "{COMMIT}"
local = os.environ.get("PILOT_LOCAL_REPO")
if local:
    ROOT = Path(local).expanduser().resolve()
    print("Using local author checkout:", ROOT)
else:
    url = f"https://codeload.github.com/Global-Nomad-Nexus/Web3AI4IO-SD-Template/tar.gz/{{COMMIT}}"
    request = urllib.request.Request(url, headers={{"User-Agent": "shilin-offchain-v2-colab/1.0"}})
    body = urllib.request.urlopen(request, timeout=90).read()
    temp = Path(tempfile.mkdtemp(prefix="shilin-v2-"))
    archive = temp / "input.tar.gz"
    archive.write_bytes(body)
    with tarfile.open(archive, "r:gz") as tar:
        prefix = tar.getnames()[0].split("/")[0]
        tar.extractall(temp, filter="data")
    ROOT = temp / prefix
V1 = ROOT / "pilots/shilin-offchain-v1/release"
V2 = ROOT / "pilots/shilin-offchain-v2/release"
sys.path.insert(0, str(ROOT / "pilots/shilin-offchain-v2"))
from verify_extension import verify
result = verify(V2, V1)
assert result["passed"], result
print("Fixed public release verified; PyArrow", pa.__version__)'''),
        part(3, "Acquire and preserve source observations", f'''The [prespecified protocol]({BASE}/EXTENSION_PROTOCOL.md) requested every one of the 57 metadata URIs a second time and every distinct image URI in their fixed JSON, once each. The [collector]({BASE}/collect_images.py) logged exact URL, UTC, status, redirects, media type, byte count and SHA-256; image responses were capped at 2 MiB. Third-party response bodies remain local until redistribution rights are settled. The cells below inspect **fixed real request receipts** and do not silently replace them with today's response.'''),
        code('''metadata = pq.read_table(V2 / "metadata_refetch.parquet").to_pylist()
images = pq.read_table(V2 / "image_acquisition.parquet").to_pylist()
print("Metadata requests:", len(metadata), dict(Counter(r["status"] for r in metadata)))
print("Image requests:", len(images), dict(Counter(r["status"] for r in images)))
print("Example metadata receipt:", {k:metadata[0][k] for k in ("original_uri","retrieved_at_utc","status_code","raw_sha256","same_bytes_as_v1")})
assert len(metadata)==57 and len(images)==56'''),
        part(4, "Inspect field observations", '''The 57 v1 JSON snapshots each have 14 prespecified field rows, even if the field is absent. `nonempty`, `empty`, `null`, `absent`, and `other_type` are distinct states. `showName` is often Boolean, so `other_type` is not automatically an error. Only specified URL values are in the public rights-limited table.'''),
        code('''fields = pq.read_table(V2 / "metadata_field_audit.parquet").to_pylist()
for field in ("image","coin_community","website","twitter","telegram","description"):
    rows=[r for r in fields if r["field_name"]==field]
    print(field, dict(Counter(r["field_state"] for r in rows)))
print("Second retrieval same bytes:", sum(r["same_bytes_as_v1"] is True for r in metadata), "/", len(metadata))
assert len(fields)==798'''),
        part(5, "Process and check linkage meaning", f'''The [audit code]({BASE}/prepare_extension.py) verified every locally saved v1 JSON body against its public hash before extraction. It compared metadata names and symbols with Claire's exact URI-linked creation fields. The [freeze code]({BASE}/freeze_extension.py) checked image media type and file signature, and verified single-block CIDv1 raw hashes where possible. A `twitter` field pointing to a post is a post URL, not a verified account. A `website` field pointing to a social page is retained but flagged for review.'''),
        code('''event_checks = pq.read_table(V2 / "event_metadata_checks.parquet").to_pylist()
url_checks = pq.read_table(V2 / "url_semantic_checks.parquet").to_pylist()
print("Name matches:", sum(r["name_exact_match"] is True for r in event_checks), "/", len(event_checks))
print("Symbol matches:", sum(r["symbol_exact_match"] is True for r in event_checks), "/", len(event_checks))
print("URL semantic states:", dict(Counter(r["semantic_state"] for r in url_checks)))
print("Image signatures:", dict(Counter(str(r["media_magic"]) for r in images)))
print("Image CID checks:", dict(Counter(str(r["cid_integrity_status"]) for r in images)))
assert len(event_checks)==61 and len(url_checks)==39'''),
        part(6, "Inspect linked data and uncertainty", '''All 116 creation events remain in the coverage table. The 55 Four.meme events have no new off-chain source in this extension; their v1 access states remain visible. Image acquisition failures remain failures. The human review queue contains pending cases and is not a completed gold standard.'''),
        code('''coverage = pq.read_table(V2 / "event_extension_coverage.parquet").to_pylist()
queue = pq.read_table(V2 / "human_review_queue.parquet").to_pylist()
print("Events by platform:", dict(Counter(r["platform_id"] for r in coverage)))
print("V1 linkage coverage:", dict(Counter(r["v1_coverage_state"] for r in coverage)))
print("V2 image states:", dict(Counter(r["image_acquisition_state"] for r in coverage)))
print("Review queue:", len(queue), dict(Counter(r["selection_stratum"] for r in queue)))
assert len(coverage)==116 and all(r["review_status"]=="pending_independent_human_review" for r in queue)'''),
        part(7, "Small descriptive example", '''Count source outcomes while keeping every event in the denominator. These are observations from one five-minute cohort, not estimates of all token launches or effects of social presence. [EX-Graph](https://proceedings.iclr.cc/paper_files/paper/2024/hash/ba29e3f830d039c3f1fa0b4dfcf19c54-Abstract-Conference.html) already links Ethereum and X; our proposed difference is the evidence and time record. [Multi-Chain Graphs of Graphs](https://proceedings.neurips.cc/paper_files/paper/2024/hash/3205b048f9cc54b9f7963db0b0f52d53-Abstract-Datasets_and_Benchmarks_Track.html) motivates explicit chain-specific denominators.'''),
        code('''for platform in sorted({r["platform_id"] for r in coverage}):
    rows=[r for r in coverage if r["platform_id"]==platform]
    print(platform, {"events":len(rows), "metadata":dict(Counter(r["metadata_refetch_state"] for r in rows)), "image":dict(Counter(r["image_acquisition_state"] for r in rows))})
assert sum(r["status"]=="response_saved" for r in images)==54'''),
        part(8, "Validation, rights and handoff", f'''Run the public verifier again. The [measured report]({BASE}/VALIDATION_REPORT.md) records 57 stable JSON responses, 54 obtainable image responses, two over the 2 MiB cap, and a 48-event human-review queue with **zero completed independent reviews**. The [rights register]({BASE}/release/image_source_rights.csv) covers seven image-serving hosts; raw JSON and image bytes have not been cleared for redistribution. This extension does not prove identity or historical website availability. [DIVE](https://www.nature.com/articles/s41597-026-07025-5) is a model for dataset documentation and technical validation; its actual subject is smart-contract vulnerabilities. A formal Data Descriptor still requires a broader frozen cohort, source rights and independent adjudication.'''),
        code('''final = verify(V2, V1)
validation = json.loads((V2 / "validation.json").read_text())
print("Checks passed:", sum(final["checks"].values()), "/", len(final["checks"]))
print("Measured release summary:", json.dumps(validation, indent=2))
assert final["passed"] and validation["human_review_completed"]==0'''),
    ]
    notebook = nbf.v4.new_notebook(cells=cells, metadata={
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
    })
    nbf.validate(notebook)
    return notebook


if __name__ == "__main__":
    path = ROOT / "pilots/shilin-offchain-v2/Offchain_Extension_Tutorial.ipynb"
    nbf.write(build(), path)
    print(path)
