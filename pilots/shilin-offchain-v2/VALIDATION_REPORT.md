# Bounded off-chain evidence extension: measured validation

**Protocol frozen before new acquisition:** commit `92c2df1`. **Unchanged inputs:** Claire Hugging Face revision `8b29598a6565b67a8a943962dbf77f3d6b2559de` through Shilin v1's 116-event cohort and 57 fixed metadata snapshots. The 2026-09-14 12:00–12:05 UTC creation window did not change. This report concerns an additive Shilin v2 evidence extension, not a larger token cohort or a formal Data Descriptor release.

## Actual additional observations

| Observation | Prespecified denominator | Result |
| --- | ---: | --- |
| Second retrieval of distinct Pump metadata URIs | 57 | 57/57 HTTP 200 and parseable JSON objects; all 57 response SHA-256 values equal their v1 snapshots |
| Prespecified metadata field audit | 57 snapshots × 14 fields = 798 | 798 field-state rows; includes explicit absent, empty, null and type states |
| Metadata image declarations | 57 snapshots | 57 nonempty values, 56 distinct image URIs |
| Image requests | 56 distinct URIs | 56 attempted; 54 HTTP 200 image responses; 2 requests exceeded the fixed 2 MiB body limit and remain failures |
| `coin_community` declarations | 57 snapshots | 16 nonempty URL values; these are field declarations only |
| Literal name and symbol comparison | 61 Pump creation events | 61/61 exact name matches and 61/61 exact symbol matches between Claire's decoded event fields and the corresponding v1 metadata JSON |
| Existing URL-field semantic checks | 39 v1 declarations | 39 checked; 20 point to social posts rather than accounts, 3 have a field/target mismatch flag, 2 need redirect review, and 14 fit the expected target category |

All 54 saved image responses have an `image/*` content type and recognizable JPEG, PNG or WebP magic bytes: 27 JPEG, 12 PNG and 15 WebP. Thirty are single-block CIDv1 raw/sha2-256 responses whose CID digest matched the retrieved bytes. Six CIDv0 DAG-PB and eight other CIDv1 codec/hash cases were **not** cryptographically verified by this check; ten images have no applicable IPFS CID. The two oversized responses have no saved body and no media/CID verdict.

The 116-event v1 coverage remains **29 declaration observed, 32 no covered declaration in successfully retrieved JSON, 3 Four.meme access restricted here, and 52 Four.meme not attempted**. No BSC positive off-chain link was added. A 48-event review queue is ready for independent human annotation; **zero queue rows have been independently reviewed**. The flags above are not measured false matches, precision, recall or account-ownership findings.

## Checks and boundaries

The extension builder verified every locally retained v1 JSON body against both its v1 snapshot digest and public request receipt. It then verified every newly saved metadata and image body against its request digest before freezing the public tables. The public verifier passed file hashes, row counts, event/URI/snapshot keys, coverage denominators, time formats, v1 manifest pin, and the absence of raw local paths in released receipts. Run `python pilots/shilin-offchain-v2/verify_extension.py --release pilots/shilin-offchain-v2/release --v1-release pilots/shilin-offchain-v1/release` from the repository root.

The public release is about 104 KiB and contains factual field states, source URLs, request outcomes, hashes, and derived comparisons. About 12 MiB of local working cache, including third-party JSON and image bytes, was **not** added to Git because redistribution rights are unresolved. Seven image-serving hostnames appear in `release/image_source_rights.csv`; a gateway hostname does not identify the content owner. The two oversized images were not retried with a larger cap because the 2 MiB rule was fixed before collection.

This extension tests access and evidence integrity at a later retrieval time. It does not establish that a website, social account, image, or community existed at token creation or belonged to its creator. For formal publication, separately freeze a broader on-chain cohort with Claire, establish a second platform's accessible exact-ID off-chain source or narrow the title, obtain a rights-compatible archive/retrieval path, and complete independent human adjudication. Claire's submitted files and the original teaching notebooks were not changed; no fresh Claire reproduction was run for this extension.
