# Reproducibility guide

## Teaching example

Supported pipeline runtime: Python 3.12, standard library only. Colab provides IPython for display; no third-party analysis libraries are used. A CPU runtime is sufficient. The bundled CSV inputs total only a few kilobytes. Runtime and memory for an empirical dataset remain unknown until measured; fill the run receipt rather than projecting these from the toy example.

Run `python3 scripts/run_demo.py --track all` from a clone. Use `--workdir /absolute/path/to/new-output` for an independent run. Each track is also runnable alone. All stages consume archived local inputs, verify source hashes and generate deterministic CSV/JSON outputs. Validation compares processed outputs and analysis/processing reports against `tests/reference/outputs.json`. No network request occurs after code retrieval.

The integration path deliberately acquires archived processed components and their manifests; it does not recollect or silently replace missing upstream data. To test the full source pipelines, run all three tracks. Every included datum is SYNTHETIC. Source canonicality flags and crosswalk review labels are fixtures, not independently verified real-world evidence.

## Adapting to the empirical project

1. Complete source metadata and the integration contract; retain this example separately.
2. Write bounded, resumable acquisition code with explicit endpoint, API/schema version, partitions, date/block bounds, filters, pagination, quota handling, retries and retrieval receipts. Never swallow failed partitions as empty data.
3. Archive permissible queried inputs and pin their manifest. Recollection from a changing API is a separate operation from reproducing an archived result.
4. Implement processing and validated output contracts; expose every parameter, exclusion, unit conversion and aggregation rule.
5. Create a justified reference using reviewed evidence. Freeze it; do not automatically bless whatever the current implementation produces.
6. Pin real dependencies and code commit, update all notebook links/configurations, run from fresh Colab and a second environment, and record outcomes using `templates/RUN_RECEIPT.md`.
7. Document bounded inspection versus complete reproduction, download size, memory, runtime, cost and non-deterministic tolerances. Retain failed runs and known unsupported environments.

## Troubleshooting

| Symptom | Action |
|---|---|
| Missing file | Check manifest revision and access; do not substitute a different release |
| Checksum mismatch | Stop, compare the named input with the release, and obtain the correct version |
| Schema mismatch | Check delimiter, encoding, source version and dictionary before changing code |
| Conflicting duplicate/tied record | Inspect and adjudicate the conflict; preserve its evidence |
| Multiple approved links | Revisit cardinality and validity intervals; do not drop rows arbitrarily |
| Reference mismatch | Compare input/code revisions and the named outputs; investigate before changing references |
| Colab runtime reset | Start a fresh run from Part I; Drive stores the notebook, not ephemeral runtime files |

Current verification evidence is in [validation_receipt.md](validation_receipt.md). Local notebook execution is distinct from execution inside the hosted Colab service.
