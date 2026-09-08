# Requirements and evidence crosswalk

Checked 2026-09-08. Recheck the linked official pages for the actual submission year. This file distinguishes venue guidance from the teaching decisions used here. The educational NeurIPS-like peer form supplied by the supervisor is a classroom aid, not an official review form.

## Scientific Data

Source: [Submission guidelines](https://www.nature.com/sdata/submission-guidelines), sections on manuscript preparation, data deposit, and authorship. The journal asks that data creation methods and exact inputs be documented, data records described, technical quality supported, and data/code access provided. It expects writing understandable across disciplines. Multiple first authors can be identified with the footnote **“These authors contributed equally”**. A manuscript template is optional. Data must be reviewable at first submission and deposited in an appropriate public repository from the second round onward, subject to applicable policy.

| Evidence topic | Author artifact in this template |
|---|---|
| Reconstruct acquisition and processing | Track README, source manifest, executable stages, processing receipt |
| Explain files and variables | Data README, dictionary, field provenance, file inventory |
| Support technical quality | `templates/VALIDATION_PLAN.md` with actual evidence and independent review |
| Provide accessible data and code | Versioned release manifest, tested links, manuscript availability statements |
| Document equal contribution | `docs/contributions.md` with named, evidenced roles |

## NeurIPS dataset contributions

Source: [NeurIPS 2026 Evaluations & Datasets hosting guidance](https://neurips.cc/Conferences/2026/EvaluationsDatasetsHosting), especially metadata, responsible AI, validation, and submission sections. Dataset contributions require reviewer access and validated Croissant metadata, including minimal responsible-AI information. The guidance addresses limitations, biases, sensitive information, use cases, social impact, synthetic content, source datasets, and generation activities. Larger datasets need an inspection sample under the stated hosting rules. Accepted datasets must be public by camera-ready. These hosting provisions do not establish scientific fit for the track; consult the [2026 call for contributions](https://neurips.cc/Conferences/2026/CallForEvaluationsDatasets).

| Evidence topic | Author artifact and check |
|---|---|
| Data access and version | Release manifest and anonymous-session download test |
| Metadata and discoverability | Generate Croissant from the real hosted files; archive validator report |
| Responsible use | `templates/RAI_WORKSHEET.md`; transfer answers into Croissant |
| Distinct component resources | On-chain, off-chain, integration configurations; component metadata and crosswalk |
| Scientific contribution | Explain the relevant AI/ML evaluation purpose with evidence if submitting to NeurIPS |

## NeurIPS paper checklist

Source: [Official checklist](https://neurips.cc/public/guides/PaperChecklist). Answers should be supported by concrete evidence about claims, limitations, reproducibility, experimental details, statistical uncertainty, compute, licenses, ethics and relevant human-participant procedures. Answer in the context of the actual study; explain non-applicable items. Do not mark a field complete because a placeholder file exists.

| Topic | Evidence to record |
|---|---|
| Claims and limits | Exact paper location, supporting output, counterexample or limit |
| Reproduction and compute | Command, code SHA, data revision, environment, elapsed time, memory, failures |
| Empirical validation | Sampling design, denominator, independent labels, uncertainty and thresholds |
| Rights and affected parties | Source-specific license, permission basis, access decisions, linkage risk |

## Teaching choices in this repository

The three notebooks, eight-part layout, folder names, coauthor cross-reproduction, SHA-256 manifests, event-level synthetic join, age sensitivity example, and worksheet formats are our implementation choices. They are not prescribed verbatim by either venue. The actual integration unit and real scientific validation design must be agreed by the students and supervisor. Code execution, JSON syntax checks and a valid dataset card cannot certify scientific quality.
