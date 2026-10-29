# Verify, inspect, and reproduce

Run the following from the repository root. All table operations use the Python standard library and run offline after cloning. The full input capsule is optional when reading or analyzing the released tables.

## 1. Inspect the complete table inventory

```bash
python3 pilots/shilin_v2/tools/data.py list
python3 pilots/shilin_v2/tools/data.py verify
```

`verify` checks each compressed file's size and SHA-256. For a complete check of original CSV bytes, logical row counts, and columns:

```bash
python3 pilots/shilin_v2/tools/data.py verify --deep
```

Each shard is an independently readable gzip CSV with a header. For example, read a shard with `pandas.read_csv(path, dtype=str, keep_default_na=False)` to preserve long integer identifiers and original missingness strings. Read only one logical alias of `registry` and `creation_events` when counting tokens.

## 2. Restore the original CSV paths and source tree

```bash
python3 pilots/shilin_v2/tools/data.py restore --output outputs/shilin_v2
```

The output directory must not already exist. Restoration verifies compressed inputs, reconstructs exact original CSV bytes, checks full-file hashes, and creates the destination only after successful completion. Allow approximately 7 GB for the restored source/data tree. Select smaller subsets when useful:

```bash
python3 pilots/shilin_v2/tools/data.py restore \
  --dataset legacy_7day_72h --output outputs/legacy_only
python3 pilots/shilin_v2/tools/data.py restore \
  --dataset p3_v6 --table registry --table context_daily \
  --output outputs/registry_and_context
```

This restores released tables; it does not regenerate the formal analysis from raw evidence. Frozen code under `source/` may require the complete input capsule for its upstream locks.

## 3. Run the small offline implementation checks

```bash
cd pilots/shilin_v2/source/1021/scientific-data-essential/code-7day-72h
python3 -B run_mvp.py --check
python3 -B -m unittest discover -s tests -v
```

From the repository root:

```bash
python3 -B pilots/shilin_v2/source/2026-10-27/registry_polymarket/p4/code/run_interface_tests.py \
  --output /tmp/test_outputs/shilin_v2_interface_new
```

Fixtures are synthetic implementation checks. They are separate from the real release and gallery. Slurm and gap-filling scripts preserve their original cluster assumptions; review paths before using them for a new collection.

## 4. Obtain complete frozen input evidence

GitHub's source ZIP does not include Release assets. Download the separate capsule using the Release page or GitHub CLI:

```bash
gh release download shilin-v2-20261029 \
  --repo Global-Nomad-Nexus/Web3AI4IO-SD-Template \
  --pattern 'inputs.tar.gz.part-*' --dir outputs/shilin_v2_assets
```

The capsule is distributed as three lossless binary parts to keep each upload manageable. `metadata/release_assets.json` records each part's size/SHA-256 and the original assembled capsule's size/SHA-256. The restoration tool verifies all parts, concatenates them in manifest order, and verifies the original complete capsule before use. The capsule preserves original relative paths, raw API bodies, normalized transactions/logs, QA/coverage evidence, legacy tables and frozen prerequisites. It does not recover missing legacy metadata HTTP bodies.

## 5. Restore and independently revalidate the sealed P4 delivery

```bash
python3 -B pilots/shilin_v2/tools/reproduction.py \
  --assets outputs/shilin_v2_assets --output outputs/shilin_v2_p4
```

This reconstructs the original 15 gzip files with their original compression settings, adds the verified capsule and exact sealed skeleton, and checks every archived P4 file hash. This step requires the same zlib implementation if gzip byte identity differs across platforms; the decompressed CSV hashes remain the portable data identity.

The original independent acceptance environment is **macOS arm64, Python 3.14.2**, with the capsule's locked ABI dependencies and `rsvg-convert 2.63.2`. Allow another 8–10 GB of temporary space for the acceptance run. Run:

```bash
python3 -B outputs/shilin_v2_p4/code/accept_delivery.py \
  --release outputs/shilin_v2_p4 --output /tmp/shilin_v2_acceptance_new
```

Acceptance denies network access and reads outside the extracted evidence/interpreter paths, includes negative controls, reconstructs formal tables from normalized native evidence, preserves six frozen market inputs, and checks tables, figures, counts and interface behavior. Source reports record the original completed acceptance; `metadata/verification.json` records the checks actually rerun while curating this branch.

Full P3 unit tests use the pinned ABI environment. First restore the source/data workspace with `tools/data.py restore`, then extract the input capsule into that workspace to provide the locked upstream evidence and `p2/vendor` dependencies. In the original Python 3.14.2 / macOS arm64 environment:

```bash
mkdir -p WORKSPACE/2026-10-27/registry_polymarket/p3/test_outputs
python3 -B -m unittest discover \
  -s WORKSPACE/2026-10-27/registry_polymarket/p3/tests -v
```

The old seven-day cohort remains `INCOMPLETE` because four chain transactions were unresolved. Replaying frozen summaries cannot fill those historical gaps. Real lifecycle integration remains `awaiting_integration`, the common cutoff remains unset, and Polymarket scalars remain `retrospective_demonstration_only`.
