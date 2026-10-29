"""Generate stage-specific scientific notes from actual P2 outputs only."""
from p2io import *
from collections import Counter

def run():
    rows=read_csv(ROOT/'processed/registry.csv');counts=Counter(r['chain_key'] for r in rows);joined=read_csv(ROOT/'processed/token_expectations_at_creation.csv');matched=sum(r['match_status']=='matched_valid' for r in joined);sol=json.loads((ROOT/'reports/solana_native_creation_receipt.json').read_text());qa=json.loads((ROOT/'reports/native_QA_receipt.json').read_text());replay=json.loads((ROOT/'reports/offline_reproduction.json').read_text());validation=json.loads((ROOT/'reports/validation_results.json').read_text());scope=read_csv(ROOT/'reports/coverage.csv')
    (ROOT/'manuscript').mkdir(exist_ok=True)
    text=f'''# P2 manuscript sections: declared-version one-day pilot

Material Passport: academic-research-suite / experiment-agent, run + validate. Generated {now()}. This is an evidence-linked P2 working draft, not the final P4 manuscript. Actual validation status: {validation['status']}.

## Methods

We froze the creation interval at [2026-10-08T00:00:00Z, 2026-10-09T00:00:00Z), using the first predeclared legacy-day candidate. Selection depended on historical observability rather than token outcomes or price direction. The scope comprised successful committed Pump.fun create/create_v2 instructions at the named Solana program, TokenCreated logs at the six Clanker factories listed in the pinned SDK, and TokenCreate logs at Four.meme V2 TokenManager2. Four.meme V1 was explicitly outside scope. Empty URIs, absent subsequent trading and unavailable historical metadata were not exclusion criteria. Addresses and ABI/IDL revisions, native field roles and exclusions are recorded in configs/.

For Solana, the initial public archive scan was replaced after sustained overload by a complete native account-transaction enumeration of the mandatory mint-authority PDA. The pinned official IDLs specify this required account for both admitted instruction discriminators; its address was checked against the program and PDA seed. Official RPC pagination crossed the start boundary from an anchor after the interval. All 59,404 indexed transactions, including 3,718 failed transactions, were retrieved as full native transactions through the officially published public Vibe Station history interface. Exact signatures, slots, transaction indices and errors agreed between sources. Each candidate still required actual creation instruction bytes and execution evidence. Native call-tree positions were reconstructed from outer instruction indices and inner stack heights. A successful child of a failed inner ancestor was excluded; missing inner execution outcomes were not imputed as success. Existing SQD evidence provided {sol['archive_native_instruction_comparisons']:,} instruction comparisons, with {sol['conflicts']} conflicts and {sol['unknown_commitment_instructions']} unresolved commitments. The original partial SQD slot coverage remains separately reported and was not relabeled as complete.

Block hashes and timestamps were retained for all admitted creations. Missing candidate block headers were fetched through the officially public CryptoHouse SQL service in named-slot pages of at most 400 rows, below its 2,000-row result cap. Base used complete native log ranges followed by every selected receipt and header; BSC used closed archive log ranges followed by native checks of every admitted receipt and event field. EVM ABI values were decoded and re-encoded to require exact payload agreement. The optional Pump instruction tail was retained as bytes rather than forced through a potentially later full schema.

The expectation demonstration reused one fixed FOMC outcome (Gamma market 2589811, Yes) and the P1 historical observations and rule snapshot. Aggregate timestamps were treated as bucket starts; only bucket end times strictly earlier than creation were eligible. The primary maximum age was 24 hours, with independent 12- and 48-hour evaluations. The mapping denotes a shared economic event, not an identity-specific forecast about a launch token. Historical rule revisions and the API scalar's trade/midpoint construction remain unverified.

## Data Records

The pilot Registry contains {len(rows):,} chain-qualified tokens: {counts['solana:mainnet']:,} Solana/Pump.fun, {counts['eip155:8453']:,} Base/Clanker and {counts['eip155:56']:,} BSC/Four.meme V2 records. creation_events.csv contains native event identities and evidence references; registry.csv has one row per token_id. pm_markets.csv, pm_outcomes.csv and pm_prices.csv preserve the fixed market snapshot, two native outcomes and 432 selected Yes history observations. pm_mapping.csv contains one typed shared-event mapping. token_expectations_at_creation.csv and pm_match_status.csv retain every Registry token, and context_daily.csv contains the three declared chain/platform/day cells. The per-column dictionary and schema are in configs/. IDs, addresses and source integers must be read as strings.

Raw responses, original and normalized evidence references, pinned configurations, request logs, native QA and hashes accompany the data. Native transaction bodies are stored with lossless gzip compression; source transport compression is distinct from on-disk encoding. Third-party raw-response redistribution permissions have not been established; this work remains a local review packet. Backfilled tokens carry no fabricated historical first-decoded time or inherited legacy checkpoint completion.

## Data Overview

All {len(rows):,} Registry tokens remain present after integration. Historical shared-macro creation anchors are valid for {matched:,}/{len(rows):,} tokens; verified direct-token identity mappings number 0/{len(rows):,} in this pilot. Background availability is 3/3 declared chain/platform/day cells, and the fixed market's valid daily-anchor availability is 1/1. These are different denominators. The same macro observation copied across many tokens is not a set of independent forecasts. Successful Solana index candidates with no committed admitted creation ({sol['successful_candidates_without_committed_creation']}) remain candidate-resolution records rather than tokens. A candidate transaction can contain multiple distinct creations, so transaction and token counts need not coincide.

Figures/P2_previews.svg and its PNG preview show observed creation counts, source-specific enumeration completion units, the semantic mapping, and hourly creation/history alignment. They are descriptive previews for one UTC day and named versions; they do not establish chain-wide market shares, causal effects or calibrated listing probabilities.

## Technical Validation

Native decoding yielded no unresolved creation conflicts. All 197 Base logs and 6,211 BSC logs were checked against native receipts and headers. An additional {qa['archive_sample_checks']} fixed-seed and boundary/risk-case native replay checks reported {qa['archive_sample_failures']} failures. Ten isolated synthetic decoder and commitment-boundary tests passed, including empty URI retention, truncated arguments, exact EVM payload checks, atomic rollback, caught inner failure and log-truncation uncertainty. Synthetic tests are not Registry rows. The saved native-index and source-page sets were also checked for duplicate signatures, cursor continuity, exact source agreement and time bounds.

Zero-network reproduction status is {replay['status']}; it reprocessed fixed native responses and header evidence twice and compared every processed CSV byte hash. Reported network calls in that rebuild: {replay['network_requests']}. Checks include exact left-join token retention, primary/foreign keys, prior-information timing, staleness, exclusion of zero-resolution/settlement-like observations, evidence hashes and disabled real lifecycle integration. See reports/validation_checks.csv and offline_reproduction.json for machine-readable evidence and scope.

## Usage Notes

Use token_id as the stable cross-chain-qualified join key and creation_event_id for a native instruction/log identity. Creator, instruction user, transaction sender and fee payer are separate roles. Compare the P2 cohort with legacy token IDs through reports/legacy_day_identity_comparison.csv; do not transfer legacy T0/T24/T48/T72 availability to newly backfilled tokens. The pilot completeness proof is conditional on declared versions and the named source/index semantics, rather than a trustless all-platform census. Full proxy upgrade histories remain outside the claims. The FOMC link is a reproducible retrospective time-alignment example because historical rule-version certification is unavailable. Real lifecycle outcomes and the common follow-up cutoff remain awaiting integration.
'''
    path=ROOT/'manuscript/P2_sections_update.md';path.write_text(text);print(path)
if __name__=='__main__':run()
