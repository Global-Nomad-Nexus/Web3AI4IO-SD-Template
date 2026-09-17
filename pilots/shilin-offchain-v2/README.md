# Shilin off-chain evidence extension, version 2

This additive release strengthens Shilin's five-minute pilot using the **same 116 creation events** selected from Claire's unchanged frozen data. It does not enlarge the token cohort. The [protocol](EXTENSION_PROTOCOL.md) was committed before the new requests; the [validation report](VALIDATION_REPORT.md) gives measured results and limits, and the [dictionary](DATA_DICTIONARY.md) defines each released table.

The [eight-part editable extension tutorial](Offchain_Extension_Tutorial.ipynb) inspects the published observations, intermediate field states, coverage, and measured checks. Its seven code cells completed without errors in a fresh local kernel using the current checkout; this is an author-side tutorial check, not Claire's independent review.

## New data

The public [release](release) contains seven Parquet tables, a host-level image rights register, `validation.json`, and a file-hash manifest. It records 57 second metadata requests, a 798-row audit of 14 fields in 57 fixed JSON snapshots, literal name/symbol checks for all 61 Pump events, 56 image-resource requests, semantic flags on all 39 v1 URL declarations, unchanged event coverage for all 116 creation records, and a pending human review queue. Raw third-party JSON and image bytes stay in a local cache pending source-specific redistribution decisions.

## Pipeline

1. `prepare_extension.py` reads v1's fixed Parquet tables and the locally retained v1 request log and raw bytes. It verifies response hashes, audits every prespecified field, compares literal creation name/symbol values, and writes the complete image URI queue.
2. `collect_metadata.py` from Shilin v1 re-requests every one of the 57 metadata URIs once in the extension's separate local working directory, under the frozen protocol.
3. `collect_images.py` requests every one of the 56 distinct declared image URIs once with a 2 MiB response limit and records every attempt.
4. `freeze_extension.py` verifies local bodies, emits a rights-limited public release, and hashes every published file. `verify_extension.py` checks that release using only public v1 and v2 files.

From the repository root, verify the published extension with:

```bash
python pilots/shilin-offchain-v2/verify_extension.py \
  --release pilots/shilin-offchain-v2/release \
  --v1-release pilots/shilin-offchain-v1/release
```

This public verification is not an independent reconstruction of third-party raw bytes. Rebuilding extraction from raw JSON requires the separately held, rights-limited working cache or a later live re-fetch, whose result may differ. The extension does not claim ownership, historical website availability, cross-chain positive linkage, or an independently annotated gold standard.
