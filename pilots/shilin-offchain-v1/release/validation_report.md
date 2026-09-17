# Shilin off-chain pilot: technical validation

Generated: 2026-09-17T05:39:53.383218+00:00

Overall machine-check status: **PASS**

Cohort: 116 creation events / 116 distinct chain-qualified tokens; Pump.fun 61, Four.meme 55, Clanker 0.
Requests: 94 attempts for 57 distinct URIs; 57 successful response snapshots; 39 extracted link declarations.

## Checks

| Check | Status | Evidence |
|---|---|---|
| unique_launch_ids | pass | 116 events |
| frozen_window_creation_counts | pass | {'four.meme': 55, 'pump.fun': 61} |
| unique_token_denominator | pass | 116 unique tokens |
| coverage_totality | pass | 116 coverage rows for 116 events |
| pump_uri_attempts | pass | 57/57 distinct Pump URIs attempted |
| response_sha256 | pass | 94 saved HTTP response bodies |
| linkage_foreign_keys | pass | candidate, evidence and snapshot references |
| declared_url_syntax | pass | 39 extracted nonempty URL fields |
| field_level_relation_semantics | pass | URL fields do not assert account ownership or project identity |
| cidv1_raw_integrity | pass | {'not_checked_cidv0_dagpb': 30, 'verified_cidv1_raw_sha256': 16, 'not_applicable': 11} |
| no_retrospective_time_leakage | pass | Every fetched metadata declaration is observed no earlier than retrieval and has unknown creation-time eligibility |
| no_unverified_bsc_links | pass | 0 BSC positive linkage assertions |
| sample_raw_event_redecode | pass | 3/3 deterministic event samples |

## Coverage states

| State | Events |
|---|---:|
| access_restricted_here | 3 |
| declaration_observed | 29 |
| no_declaration | 32 |
| not_attempted | 52 |

## URL target classes

| Class | Declarations |
|---|---:|
| other_web_url | 7 |
| platform_page | 1 |
| social_post | 21 |
| social_profile_or_path | 6 |
| telegram_path | 4 |

Website fields pointing to a social target: 2. These remain field-level declarations, not validated project websites.

## Limits and remaining review

- Four.meme API returned access restrictions in a bounded local probe; unprobed BSC events remain not attempted.
- Fetched metadata is a retrieval-time observation; historical website/account states are unknown.
- Raw third-party response redistribution has not been cleared; release includes hashes and factual extracted links.
- Independent coauthor reproduction and human double review require Claire's participation.
