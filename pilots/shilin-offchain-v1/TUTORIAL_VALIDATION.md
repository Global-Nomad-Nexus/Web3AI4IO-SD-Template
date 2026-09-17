# Tutorial execution receipt — 17 September 2026

This receipt separates the original collection, fixed-snapshot replay, a current live request and coauthor review. Times are UTC. The immutable code/data input for both new notebooks is Git commit `1fec501de1de09d9cc2b9c69ce350338a40af889`; Claire's input is Hugging Face revision `8b29598a6565b67a8a943962dbf77f3d6b2559de`.

| Check | Actual outcome |
|---|---|
| Original acquisition | 61 Pump.fun creation event URIs, 57 distinct URIs; 94 HTTP attempts, including 37 HTTP 429 and 57 HTTP 200; 57 JSON objects parsed. Three spaced Four.meme exact-address probes returned HTTP 403. |
| Source-side machine validation | All 13 checks passed, including 94 response-body hashes, 3/3 sampled raw Pump event re-decodes, keys, coverage, time flags and CIDv1 raw digest checks. See `release/validation_report.md`. |
| Public release verifier | Passed file sizes/hashes, Parquet row counts, cohort/coverage keys, assertion/evidence keys and temporal flags. The public release contains 116 creation events, 57 snapshots, 39 URL-field declarations and 100 typed assertions. |
| Off-chain notebook, local clean kernel | All seven code cells completed. A fresh request to the exact Morfik CID returned HTTP 200, 520 bytes, SHA-256 `fc0335b4457430e4e681a258940b922466b67cb6edecd7cd7128dc5ca8661cc9`, identical to the fixed response digest. |
| Integration notebook, local clean kernel | All seven code cells completed; a 116-row left join retained 29 `declaration_observed`, 32 `no_declaration`, 3 `access_restricted_here`, and 52 `not_attempted` event states. |
| Pinned remote checkout | Both new notebooks completed again with no local repository override. Setup downloaded the full GitHub archive for the immutable input commit and verified all release file hashes. The off-chain live CID request again returned HTTP 200 with the same digest. |

Execution used Python 3.13, PyArrow 25.0.1, nbclient 0.11.0 and nbformat 5.11.1 on 17 September 2026. The notebooks are committed without saved outputs to remain editable and small; local executed copies are retained in the author's working archive. The fixed release does not contain raw third-party JSON bodies because redistribution is not yet cleared. Thus an offline reader can reproduce the released tables and join, while an independent raw parse requires live re-fetch or separately authorized bytes.

Claire's independent execution of the off-chain notebook and joint human review of the integration notebook are **pending**. Software checks do not establish that a URL was controlled by the token creator or existed at creation time.
