# Integration contract

Both authors sign off on this design before collecting at scale. Use `configs/integration_contract.example.json` as the machine-readable companion. The demo uses one blockchain-like event per row solely to make the rules concrete; a real project may require a panel, graph, document set, or other unit.

| Decision | Author instruction | Demo behavior |
|---|---|---|
| Observation unit and denominator | Define one row, eligible population and exclusions before joining | One output per six processed events |
| Identifiers | Namespace chain, contract, organization, source and record IDs; record normalization and collisions | Fictional `demo-chain`, `demo:a`, `org-alpha` identifiers |
| Crosswalk semantics | Describe relationship, evidence, matching method, review status, validity interval and ambiguity handling | Five invented candidate/approved relationships; no identity inference |
| Time | Distinguish event, reference period, publication, retrieval and revision times; choose timezone and interval closure | UTC; link valid from inclusive to exclusive; publication and reference end no later than event |
| Cardinality | State allowed one/one-to-many relationships and aggregate explicitly; reconcile counts after every join | At most one approved active link and one chosen source record per event |
| Competing records | Decide revisions, priorities and ties using a documented policy | Latest available publication, then latest reference end; unresolved ties stop |
| Missingness | Distinguish no link, unreviewed link, no available record and missing measure | Separate statuses; empty numeric values stay missing |
| Evidence | Define independent review sample, adjudication, denominators, uncertainty and sensitivity | Only deterministic fixture checks; no empirical accuracy estimate |
| Release compatibility | Pin both component releases and linkage specification; validate hashes and schemas | Two hashed component manifests plus hashed crosswalk |

The demo is a retrospective reconstruction constrained by reported publication times. It does not prove a historical source was actually observable at that time: collection occurred later. For historical forecasting claims, archive contemporaneous versions or establish publication/revision provenance, and keep information used to develop the linkage rules outside evaluation periods where required.

The `no_crosswalk` status covers no eligible link in the validity interval, not proof that no relationship exists. `unreviewed_link` means candidate links exist but none is approved. The strict demo rejects multiple approved active links instead of silently multiplying observations. Project tasks with legitimate multiple relationships should implement and validate an explicit allocation or aggregation rule.

Publish integrated records together with unmatched and unused source records where permissions allow. Every derived field needs a dictionary entry and provenance rule. Evaluate linkage quality by source/time/relationship groups where scientifically meaningful, report the sampling strategy and uncertainty, and avoid interpreting a large matched fraction as high accuracy.
