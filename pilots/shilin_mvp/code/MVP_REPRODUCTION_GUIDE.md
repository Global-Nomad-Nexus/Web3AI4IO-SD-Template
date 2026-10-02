# MVP reproduction guide

1. Use Python 3.11+ and clone/copy this `code` directory.
2. Run `python -m unittest discover -s tests -v`.
3. Run `python run_mvp.py --mode fixture --output output/reproduction-1`.
4. Compare `mvp_release/release_manifest.json`, `validation_results.json`, row counts and response hashes with the supplied run. The fixture path is `archived_replay`; hashes should match.
5. For a real rerun, use only a source-register endpoint, retain all receipts, and label the result `live_rerun_only`. A live rerun is procedurally reproducible, not a byte-for-byte replay guarantee.

Every file has a stable schema. The release contains no third-party raw response body; local `run/response_bodies.jsonl` is an execution artifact used to construct field observations.

