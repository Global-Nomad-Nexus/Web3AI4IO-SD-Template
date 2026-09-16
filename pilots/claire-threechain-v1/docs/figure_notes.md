# Figure content and reproducibility

All diagrams and figures use **Mermaid**. Run
`python -m claire_demo --root . visualize` to regenerate `.mmd`, descriptive
Markdown, optional browser HTML and numerical CSV files. The generator is
`claire_demo/visualize.py`. Run final validation before the final visualization
pass so F1 consumes the latest coverage receipt. No paid rendering API or
external icon assets are used.

| ID | Question answered | Evidence and output |
|---|---|---|
| D1 | How do activities become observations? | Method diagram; explicitly separates raw records and interpreted events |
| D2 | How is the snapshot transformed and checked? | Method diagram tied to CLI stages and folder boundaries |
| F1 | What was retrieved, and what remains unavailable? | Resolved scope, raw/normalized block counts, last technical-validation coverage receipt |
| F2 | What transaction records occur in each 30-second bin? | Ten bins, status counts and fractions, separate exclusion of identified vote/system transactions |
| F3 | Which platform facts were recognized in each minute? | Atomic operations grouped by chain, platform, minute, effect and decode status; mechanism N/A and unknown remain explicit |
| F4 | How can token observations support graph reuse? | Bounded local graph, verified node roles, shared-address GoG with union and Jaccard, all selected-scope edges in CSV; Solana has no owner projection |
| F5 | How do two event definitions alter outputs? | Thresholds one and three, plus per-token attainment delays for tokens meeting both definitions |

Mermaid flowcharts carry real counts and relations. F1 is a coverage diagram
with its complete numerical table, not a Mermaid heatmap. There is no claim
that Mermaid supports a heatmap or a scientific plotting backend. Graph
selection affects only the reuse example, never the raw sampling population.

Unknown evidence is printed as **unknown**, not converted to zero. A literal
zero in an output table means zero observations under the named decoded scope
or known denominator. It is not an inference about unobserved real activity.

`reports/visualization.json` records figure IDs, input CSVs, source hashes,
captions and generation metadata. `figures/index.md` is the portable entry
point; `figures/index.html` uses a local Mermaid bundle if supplied and otherwise
shows editable source. It never loads a CDN automatically.
Full numerical tables remain usable without JavaScript or internet access.
The bundled renderer is Mermaid 10.9.3, under MIT; its pinned source URL and
SHA-256 are in `vendor/manifest.json`, with license in
`vendor/mermaid-LICENSE.txt`. The one-pass renderer check is separate from data
acceptance and applies only to the source hashes listed in its receipt.
