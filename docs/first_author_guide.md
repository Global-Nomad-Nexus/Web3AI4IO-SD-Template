# First-author instructions

You are developing two source contributions and one shared integrated resource. Start by describing the intended users and observations in ordinary language. Do not assume a contract is an organization, that a public record is safe to redistribute, or that two timestamps mean the same thing.

## 1. Agree the design together

Complete `configs/project.example.json` and `configs/integration_contract.example.json`. Decide the scientific scope, each dataset's unit of observation, time boundaries, included sources, identifiers, data access, and supported reuse questions. Explain what each component contributes independently and what integration adds. Put unresolved decisions in an issue with an owner and evidence needed; do not fill unknown facts with guesses.

## 2. Build the source contributions in parallel

Student A owns on-chain acquisition, decoding, processing, dictionary, validation and tutorial. Student B owns off-chain acquisition, extraction, processing, dictionary, validation and tutorial. Both agree output schemas before large collection. Preserve source-specific identifiers, raw values, units and missingness; export a release manifest with files, sizes, row counts, checksums, license and revision.

For each stage, complete its README before requesting review. Replace AUTHOR INPUT prompts with exact values, commands, explanations and artifact locations. Every figure or numerical statement should be traceable through `metadata/result_index.json` to input bytes and code.

## 3. Integrate jointly

Use the agreed identifiers and time policy. Version the crosswalk and record evidence, relationship type, matching method, review decisions, confidence calibration if used, validity intervals, and unresolved candidates. Report linkage coverage separately from correctness. Preserve all intended observations and explain any exclusion. Estimate error using independent review of a documented sample; code checks alone are insufficient.

## 4. Write for a reader with no subject background

In every notebook explain the question, each new term, the input and output, why a step is needed, the expected shape, and how to diagnose failure. Link the exact GitHub code, source documentation and dictionary. Run the example before replacing it. After adapting to research data, run the whole notebook from a fresh runtime and repeat using an independently downloaded archived dataset.

## 5. Review one another's work

Student B reproduces the on-chain notebook; Student A reproduces the off-chain notebook. Both reproduce integration, preferably with a third reader from another discipline. Use `templates/REPRODUCTION_REVIEW.md`: state what is supported, what is unclear, and the exact revision needed. Record commit, input revision, output hashes, environment and failures, including unsuccessful runs. Compare scientific outputs using justified tolerances where byte equality is inappropriate.

## 6. Submit a synchronized internal draft

Provide the manuscript link, repository commit, immutable data release, three notebook links and downloads, validation evidence, contribution record, and a short unresolved-issues list. The paper, README, dictionaries, manifests and notebooks must use the same population, dates, exclusions, units and counts. Agree project-specific deadlines with the supervisor; dates from another project are not prefilled here.

Before a public empirical release, complete the source rights/access decisions, suitable data deposit, venue checklist, source-specific technical validation, and fresh-session accessibility tests. See [requirements](requirements.md), [governance](governance.md), and [paper instructions](../paper/README.md).
