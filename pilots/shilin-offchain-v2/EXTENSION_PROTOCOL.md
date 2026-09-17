# Shilin off-chain evidence extension: prespecified bounded protocol

**Frozen input.** Claire's unchanged Hugging Face revision `8b29598a6565b67a8a943962dbf77f3d6b2559de`; Shilin v1's 116-event cohort, 57 successful metadata snapshots, and release manifest. The cohort remains the complete set of committed, decoded, nonempty-object creation events in 2026-09-14 12:00:00–12:05:00 UTC. This extension adds observations to that cohort; it does not add tokens or extend the on-chain time window.

**Why this extension.** The local `Web3AI4IO_OFFCHAIN_LINKAGE_LITERATURE_REVIEW.md` prioritizes source provenance, time separation, missingness, and rights-aware release. Claire's handoff fixes chain-qualified identifiers and raw event pointers. V1 already records URL-field declarations and every event's coverage state. This extension adds source observations and checks that are still missing without selecting tokens based on whether their metadata has appealing links.

## Prespecified acquisition and extraction

1. Re-request **all 57 distinct Pump.fun metadata URIs**, once each, in lexical URI order. Use the same exact URI, with the documented alternate public IPFS gateway for `ipfs.io` URIs. Save a UTC request receipt, status, redirect path, response byte count, SHA-256, and raw body locally. Stop a source run after two consecutive HTTP 429 responses; preserve not-attempted items in the denominator. A second retrieval checks present access and byte stability. It does **not** establish what the metadata contained at launch time; most IPFS CIDs are content-addressed, so an unchanged response is not evidence of a changing platform profile.
2. From **all 57 v1 metadata JSON objects**, inspect the prespecified fields `name`, `symbol`, `description`, `image`, `createdOn`, `showName`, `website`, `twitter`, `telegram`, `external_url`, `discord`, `github`, `coin_community`, and `video`. Record field presence, type, nonempty status, and JSON pointer. Release URL values only for the previously covered outbound-link fields plus `image` and `coin_community`; do not release third-party prose, image bytes, or full JSON without a source-rights decision. A `coin_community` value is a field declaration, not verified project identity.
3. Request **every distinct nonempty `image` URI** from those 57 fixed JSON objects, once each in lexical order. Limit each response to 2 MiB and keep binary bytes local. Public records include the declared URI, request/status/redirect receipt, retrieval UTC, media type, byte count, and SHA-256. A successful request proves only that bytes were obtainable at retrieval time, not copyright, image identity, or creation-time availability. Stop after two consecutive HTTP 429 responses and retain unattempted entries.
4. Do not retry Four.meme's 55 events in bulk. Its exact-address API and one exact-address public page both returned HTTP 403 here. Leave them in the v1 coverage ledger; revisit only after a documented authorized, exact-ID source becomes feasible. Do not infer absence of off-chain metadata from 403.

## Prespecified validation

- Verify all v1 raw response bytes against their recorded SHA-256 before extracting new fields.
- Require one field-audit row for each prespecified field in each of the 57 parseable snapshots, including absent fields; distinguish missing, null, empty and wrong type.
- For every one of the 61 Pump creation events, compare metadata `name` and `symbol` with Claire's decoded creation fields using exact strings, reporting both matches and mismatches; do not rewrite Claire's fields or assume a mismatch is fraud.
- Require one acquisition outcome for each of the distinct declared image URIs and one second-retrieval outcome for each of the 57 metadata URIs. Check response digests, foreign keys, event/URI/snapshot denominators, and UTC ordering. Report access failures and drift explicitly.
- Preserve each v1 URL assertion and coverage status. New image/community observations form separate typed tables; they do not turn a URL into an ownership claim or a creation-time fact.
- Produce a stratified human-review queue spanning positive URL fields, no-declaration Pump events, Four.meme access restrictions, field/target mismatches, and any new metadata/chain mismatch. A second reviewer and adjudication remain future work; do not report precision or recall without a gold sample.

## Release and decision boundary

Put all new code, documentation, and public derived tables under `pilots/shilin-offchain-v2/`. Keep raw third-party response bodies in the local ignored cache. Pin v1 and Claire inputs by revision and hash; give this extension its own manifest and validation report. Leave Claire's files, the original teaching notebooks, and v1's frozen tables unchanged.

This is a stronger **five-minute bounded pilot**, not the formal Data Descriptor cohort. After 19 September, freeze a separate `publication_cohort_spec.yaml` with Claire before selecting additional on-chain windows. The publication claim stays single-platform until a second platform has actual, validated off-chain links. The review's EX-Graph precedent prevents a blanket “first on-chain/off-chain dataset” claim; the DIVE DOI must be cited under its correct smart-contract-vulnerability title.
