# Why these data: design rationale and references

This note distinguishes our design decisions from claims established by cited sources. Documentation was checked on September 16, 2026 UTC; the actual decoder inputs are pinned in `config/platform_registry.json` in the code/data package. Repository default branches are explanatory references, not substitutes for the pinned materials used in the run.

## 1. Why Solana, BSC and Base?

This is a purposive engineering selection for launch-platform data, not a claim that these are the three largest chains. Official platform materials identify Pump/PumpSwap programs, Four.meme's BSC interfaces and Clanker's deployment interfaces [R4–R6]. These provide three concrete decoding targets without letting those targets determine raw collection.

| Selection | What it tests in the pilot | Evidence and boundary |
|---|---|---|
| Solana / Pump.fun and PumpSwap | Native instruction, account-role and execution-meta representation | Solana RPC exposes different record structures from EVM receipts [R4, R7]; source version mismatches remain unknown |
| BSC / Four.meme | An EVM launch-platform view, full transaction/receipt extraction and integer quantities | Platform documentation and BSC RPC documentation [R5, R8, R10]; no current market-share claim |
| Base / Clanker | A second EVM environment, native chain extensions, platform attribution and same-address-byte comparison | Clanker SDK and Base RPC documentation [R6, R9]; no inference that equal addresses imply equal controllers |

BSC/Base permit comparison under related transaction formats; Solana tests whether the common tables preserve a substantially different execution representation. The set supports multiple-chain collection and cautious links without forcing all records into an EVM model. TRON, Ethereum and other chains are outside this approved pilot, not judged unimportant or technically unsuitable. Adding them is a separate scope decision.

## 2. Why a shared five-minute whole-chain window?

**Our decision:** constrain volume rather than record detail. Collect all blocks and transactions in the same predeclared interval, including failed/vote/system transactions, before platform filtering. This reduces platform/event selection bias inside the window and makes boundaries auditable. It does not make the window statistically representative, synchronize distinct chains' consensus, or recover activity before/after the window.

The measured sample size is reported in [limitations](limitations.md), independently of the reference papers. Zero recognized launch/migration/Clanker trade observations can be legitimate outputs under a defined decoding scope; they are not reasons to replace the window.

## 3. Why these layers and fields?

| Retained layer / fields | Reuse question it enables | Error avoided |
|---|---|---|
| Full raw envelopes, request parameters, source/time/hash | Can someone reparse or audit the same evidence? | Irrecoverable field selection; treating checksums as independent chain validation |
| Blocks, parent links, times, slots/heights | Which records are in the declared population? | Silent boundary changes or skipped-slot/missing-response conflation |
| Transactions, status, fee, version, input | What was attempted and what executed? | Discarding failures; mistaking economic success for execution success |
| Receipts/logs, outer/inner instructions | What native record supports a decoded operation? | Treating a researcher event as an original record |
| Account roles and balance observations | Who signed/paid/appeared, and which balances were observed? | Equating an address with a person or a balance delta with a transfer |
| Exact amounts, assets, decimals and source pointers | Can amounts be recomputed without precision loss? | Floating-point authority and missing-unit assumptions |
| Object observations, `observed_at`, `first_seen_in_window` | When was each evidence item observed in this sample? | Backdating evidence or calling first observation a creation date |
| Decoder version/status/effect, platform registry | Which interpretation is supported, and by which definition? | Guessing unknown layouts or counting reverted operations as transfers |
| Independent event definitions and evidence IDs | Can another scholar choose different thresholds without recollection? | Freezing the research question into the collection population |
| Cross-chain links with relation/evidence/uncertainty | What kind of connection is actually evidenced? | Merging identities from equal address bytes or token names |

RPC fields are justified by the chain interfaces [R7–R10]. Selecting layers, event thresholds and linkage rules is our design choice. The fixed snapshot supplies reproducibility when free endpoints change. Ordinary receipts cannot recover arbitrary historical state; that coverage stays separately declared.

## 4. How the two assigned papers are used

**DIVE [R1].** We use its organization around construction, documented features, validation and reusable releases as a reporting reference. We do not use its vulnerability labels, dataset population, voting system or accuracy results as evidence for this pilot. Our checks must pass on our own records.

**Multi-Chain Graphs of Graphs [R2], §§3.2–3.3.** Section 3.2 uses explorer APIs to collect token transactions on Ethereum, Polygon and BSC, with token-size selection rules. We retain transaction provenance but deliberately use whole-chain RPC collection in a fixed interval instead of importing that token selection. Section 3.3 motivates token-local graphs and token-token overlap; our Jaccard example counts observed addresses, not verified shared people, and excludes mint/burn endpoints. Graphs are optional derived views, not the storage schema. Multiple chain datasets alone do not prove cross-chain flows.

**Current source check.** Etherscan's present documentation describes its V2 multichain API [R11]. The paper's historical explorer endpoints therefore cannot be copied as a current implementation guarantee. This pilot instead tests current Solana, BSC and Base RPC access, including exact historical-window receipts [R7–R10, R12]. Actual provider successes and failures are retained in the package.

## 5. Scientific Data alignment

The current guidelines distinguish dataset methods/records, technical validation and availability from substantive research results [R3]. Our two process diagrams explain construction; descriptive examples teach reuse in the notebook. They should not all be transferred into a manuscript as analytical results. Formal journal deposition, data/code availability links, licensing and author statements remain author tasks; this checkpoint package does not claim journal submission readiness or a deposited DOI.

## References

- **[R1]** Alsunaidi, S. J., Aljamaan, H. & Hammoudeh, M. (2026). *DIVE: A Multi-Label Smart Contract Vulnerability Dataset*. Scientific Data 13, 664. [doi:10.1038/s41597-026-07025-5](https://doi.org/10.1038/s41597-026-07025-5). Used for construction/documentation/validation presentation.
- **[R2]** Luo, B., Zhang, Z., Wang, Q. & He, B. (2024). *Multi-Chain Graphs of Graphs: A New Approach to Analyzing Blockchain Datasets*. NeurIPS, Datasets and Benchmarks Track. [Official paper, §§3.2–3.3](https://proceedings.neurips.cc/paper_files/paper/2024/file/3205b048f9cc54b9f7963db0b0f52d53-Paper-Datasets_and_Benchmarks_Track.pdf).
- **[R3]** Scientific Data. [Submission Guidelines](https://www.nature.com/sdata/submission-guidelines). Data Descriptor section structure and technical-validation scope; checked 2026-09-16.
- **[R4]** Pump.fun. [Official public program documentation](https://github.com/pump-fun/pump-public-docs). Actual snapshot uses revision `81091419e4457566469d4e2a27f64ed84d42419c` and the pinned pump/pump_amm IDLs.
- **[R5]** Four.meme. [Official integration repository](https://github.com/four-meme-community/four-meme-ai). Actual snapshot uses revision `c81f0eebbabec16998b2457f7e881e1b70b86420`; exact addresses and layout sources are in the registry.
- **[R6]** Clanker. [Official SDK](https://github.com/clanker-devco/clanker-sdk). Actual snapshot uses revision `4f4d2bbf41c7f10543559dc043c85f443a6d452e`; exact contract/ABI records are in the registry.
- **[R7]** Solana. [getBlock](https://solana.com/docs/rpc/http/getblock). Full block request parameters, transaction version and nullable block-time fields.
- **[R8]** BNB Chain. [BSC JSON-RPC endpoints](https://docs.bnbchain.org/bnb-smart-chain/developers/json_rpc/json-rpc-endpoint/). Source-access context; capabilities are tested, not assumed.
- **[R9]** Base. [RPC overview](https://docs.base.org/base-chain/api-reference/rpc-overview). Source-access context and RPC interface.
- **[R10]** Ethereum. [JSON-RPC API](https://ethereum.org/developers/docs/apis/json-rpc/). Transaction, receipt and quantity conventions; provider method support remains an empirical check.
- **[R11]** Etherscan. [Current API introduction](https://docs.etherscan.io/introduction). Checked as the current counterpart to the older explorer API collection route.
- **[R12]** Blockmachine. [Base RPC documentation](https://blockmachine.io/docs/base-rpc). Documentation for the free provider used after target-window checks.

The registry and acquisition receipts are the evidence for which versions/endpoints this run used. Citations to papers or current documentation do not certify our implementation or confer redistribution rights. Retain source licenses and provenance; no new blanket license is assigned to third-party materials by this package.
