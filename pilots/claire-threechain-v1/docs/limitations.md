# Interpretation and reuse boundaries

1. **Completeness is bounded.** The target is all finalized transaction RPC
   records inside the fixed five-minute block-time window, plus receipts/meta.
   It is not all chain history, all execution traces or the complete chain state.
   Actual coverage is in `reports/coverage.csv` and `reports/validation.json`.
2. **Time is imperfect.** EVM and Solana block times are not transaction submission
   times. Solana block time is estimated and may be null. Boundary blocks and
   uncertain slots require explicit handling. Five minutes do not establish
   lifecycle completion or lifetime first activity.
3. **Sources have limitations.** A free endpoint can expose recent blocks while
   lacking old receipts, traces or historical state. An observed endpoint error
   is not zero blockchain activity. A capability test is not proof of interval
   coverage. Provider changes and retrieval dates are recorded.
4. **Native records have different meanings.** Solana instruction and log-message
   counts are not comparable to EVM emitted-log counts as a common activity
   measure. Gas and compute units are different quantities. Returned arrays may
   omit metadata or encounter format versions the parser does not recognize.
5. **Balance changes are not transfer edges.** Fees, account creation/closure and
   other effects alter balances. EVM receipts do not include every internal
   native-currency movement. Candidate fungible Transfer logs require separate
   standard evidence; non-fungible and undecodable records are not relabeled.
6. **Decoded absence is not population absence.** A pinned decoder can recognize
   only supported layouts. Platform historical version bounds can be unknown.
   Factory records do not automatically attribute later trades in external pools.
   Clanker trade counts in particular require independently evidenced pool
   attribution. Zero decoded records does not prove no platform activity.
7. **Address links are not identity links.** Same-address-byte relations between
   BSC and Base preserve two chain-qualified objects. Shared graph participants
   can be routers, pools, custody or other infrastructure. They do not prove
   shared people, common control or cross-chain fund movement.
8. **Graph displays are bounded examples.** Each chain's local example selects one
   platform-related token by eligible committed movement count, breaking ties by
   token ID. Its displayed nodes are the first 30 ranked by incident movement
   count then address ID. Each chain's GoG uses at most ten platform-related
   tokens and their complete observed address sets. Full CSV edge tables for the
   selected assets are preserved; these display choices do not alter collection.
9. **Event thresholds are choices.** Thresholds one and three use distinct
   successful trade transactions, not addresses or duplicate event/log records.
   They mark observed window attainment, not launch success or a lifetime first
   trade. Unmatched, uncommitted and unknown-subject/time records are excluded
   from qualification and counted separately.
10. **Acceptance is scoped.** Passing local integrity checks is different from
    independent source confirmation, fresh offline replay, Colab compatibility,
    coauthor cross-reproduction and publication. Each needs its own evidence.
    Off-chain data and integration are outside Claire's current component.

No diagrams or numerical graphics require an external rendering service.
Mermaid source and CSV tables are authoritative editable outputs. The optional
HTML renderer uses a local Mermaid bundle only if supplied; it never loads a
CDN automatically. Computation and snapshot replay remain offline. Without a
renderer, the source and numbers still remain visible.

## Runtime measurements

Execution receipts retain measured elapsed time and native peak-RSS units.
Manifest and archive byte counts measure stored files and transferable packages.
HTTP wire bytes, including compression and retry overhead, were not instrumented
in this collection and remain unknown; raw file size is not a network-traffic
measurement.
