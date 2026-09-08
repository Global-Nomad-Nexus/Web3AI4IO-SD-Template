# integration / process_data

Transform acquired inputs using explicit rules and emit a processing ledger.

Run from the repository root:

```bash
python3 code/integration/process_data/run.py --workdir outputs/demo
```

Run stages in order: query_data → process_data → analyze_data → technical_validation. The implementation is [shared/pipeline.py](../../shared/pipeline.py); [run.py](run.py) is the track entry point. Inputs and outputs are described in the [track data guide](../../../data/integration/README.md) and [result index](../../../metadata/result_index.json). The default is an offline synthetic example, not live research acquisition.

## Author inputs

Pin both component releases and the linkage table. Define unit, join keys, relationship evidence, temporal alignment, cardinality, conflicts, unmatched selection and sensitivity. Assess linkage accuracy independently from match coverage.

Complete the [CODE_README worksheet](../../../templates/CODE_README.md) with exact source documentation URLs, input/output files and schemas, parameters, rationale, errors, expected output evidence and measured compute. Link the matching notebook part and [official venue crosswalk](../../../docs/requirements.md). A working script is insufficient evidence for scientific validity; add the [validation plan](../../../templates/VALIDATION_PLAN.md).
