# Technical validation plan and evidence

Complete separately for on-chain, off-chain and integration, then reconcile shared claims. Software checks and scientific checks answer different questions. See [requirements](../docs/requirements.md).

| Claim or risk | Sampling/independent reference | Metric and denominator | Threshold and justification, fixed before assessment | Uncertainty or sensitivity | Evidence path and result | Lead/reviewer/status |
|---|---|---|---|---|---|---|
| AUTHOR INPUT | AUTHOR INPUT | AUTHOR INPUT | AUTHOR INPUT | AUTHOR INPUT | NOT YET RUN | AUTHOR INPUT |

On-chain: consider completeness of declared block ranges, failed queries, canonicality/finality and reorg policy, decoding correctness, token decimals/units, duplicate identities, and independently checked records. State what an explorer or provider cannot guarantee.

Off-chain: consider sampling frame, source stability, missing pages/languages, extraction accuracy, annotation instructions, independently labeled samples, agreement/adjudication, revisions, and measurement validity.

Integration: assess false matches and missed eligible matches separately from coverage, with a justified sample and reference. Record reviewers, blinded/independent judgments where appropriate, disagreement resolution, uncertainty, group/time breakdowns, cardinality, time leakage, unmatched selection and alternative matching/time policies. Do not treat confidence scores as calibrated probabilities without evidence.

State which reuse tasks have evidence and which remain unvalidated. Where prediction is included, separate entities and time appropriately across train/validation/test data, prevent linkage/feature leakage, and report justified baselines. A successful join does not identify a causal effect.
