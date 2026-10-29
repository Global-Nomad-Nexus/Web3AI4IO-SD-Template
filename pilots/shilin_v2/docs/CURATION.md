# What this branch preserves

The `shilin_v2` branch is a curated publication of Shilin's two completed engineering stages: the original seven-day Pump.fun metadata cohort with 72-hour follow-up, and the later three-chain Registry / Polymarket experiment. Original collection files remain unchanged on the author's machine.

| Material | Where it is stored | Selection rationale |
|---|---|---|
| Original seven-day / 72-hour release | `data/legacy_7day_72h/` | All six original CSV tables; no row sampling |
| P3 v6 formal release | `data/p3_v6/` | All 15 logical tables; no row sampling |
| Registry / creation events | One physical table, two manifest entries | Their original CSV hashes and byte lengths are identical; restore recreates both filenames |
| Legacy collector, fixtures, tests, Slurm scripts | `source/1021/scientific-data-essential/` | Preserve the actual implementation and deployment context |
| P0/P1, P2, P3 and P4 source | `source/2026-10-27/registry_polymarket/` | Preserve acquisition, decoding, mappings, validation, interface, and packaging code |
| Frozen protocol, dictionaries, QA and final receipts | `source/` and `metadata/` | Keep small current evidence readily browsable |
| Five-panel gallery and source CSVs | P4 `figures/` | Keep the complete figure evidence rather than decorative screenshots |
| Complete input evidence capsule | GitHub Release: numbered lossless `inputs.tar.gz.part-*` parts | Preserve raw API responses, normalized native evidence, prerequisite tables and exact ABI dependencies without expanding thousands of large evidence files in Git |
| Exact P4 acceptance skeleton | `reproduction/p4_sealed/` | Retain the sealed code/configuration/manifest for independent offline reconstruction |

CSV shards use gzip, a repeated header, and complete CSV records. Quoted multiline fields are kept within a shard. Concatenating decompressed shards directly would repeat headers; use `tools/data.py restore`. The tool removes only repeated headers and verifies the original full-file SHA-256. Source CSV bytes, integer strings, Unicode, missingness codes and row ordering are preserved.

The branch omits local caches, `.DS_Store`, Python bytecode, temporary outputs, interrupted-run logs, old v1–v5 derived tables, repeated delivery archives, and duplicate copies of formal tables. Relevant upstream evidence remains in the input capsule. Platform-specific vendored dependencies are kept inside that capsule for the locked acceptance environment; dependency locks remain visible in source. Draft research directions and duplicate PDF versions of Markdown reports are excluded.

`source/` is an archival source tree. Its historical READMEs describe the original local directory and may link to files available only after restoring data or obtaining the input capsule. Start with this branch's current README and `docs/REPRODUCE.md`. The original relative directory geometry is preserved so frozen code and evidence references can be restored faithfully.

The inherited repository template and earlier pilots remain in their original directories and history. They are separate from `pilots/shilin_v2/`; synthetic teaching fixtures never enter this release's real-data tables.

The P4 source-rights register records the review status at the time of its local delivery. This GitHub publication does not silently rewrite those historical facts or confer a new third-party data license. See the current `DATA_RIGHTS.md`.
