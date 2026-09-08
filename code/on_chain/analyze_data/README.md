# on_chain / analyze_data

Show bounded data understanding/reuse examples with named denominators and limits.

Run from the repository root:

```bash
python3 code/on_chain/analyze_data/run.py --workdir outputs/demo
```

Run stages in order: query_data → process_data → analyze_data → technical_validation. The implementation is [shared/pipeline.py](../../shared/pipeline.py); [run.py](run.py) is the track entry point. Inputs and outputs are described in the [track data guide](../../../data/on_chain/README.md) and [result index](../../../metadata/result_index.json). The default is an offline synthetic example, not live research acquisition.

## Author inputs

Specify real chains/network IDs, contract inclusion criteria, block/date bounds, node/indexer/explorer and API versions, finality/reorganization policy, logs versus transactions, ABI/decoding version and units. Preserve chain-specific address rules; addresses do not establish real-world identity.

Complete the [CODE_README worksheet](../../../templates/CODE_README.md) with exact source documentation URLs, input/output files and schemas, parameters, rationale, errors, expected output evidence and measured compute. Link the matching notebook part and [official venue crosswalk](../../../docs/requirements.md). A working script is insufficient evidence for scientific validity; add the [validation plan](../../../templates/VALIDATION_PLAN.md).
