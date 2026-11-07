# Offline reproduction

Use Python 3.11 or newer with the standard library and an IANA time-zone database
containing `America/New_York`. Linux and macOS normally provide this database;
on systems without it, install the Python `tzdata` package before running.

From the `ecosystem-context/` directory, rebuild the 27 CSV tables:

```sh
python3 reproduce/code/reproduce.py --data data --output /tmp/ecosystem-context-rebuilt
```

Choose an output directory that does not already exist. The command verifies the
frozen-input hashes and reference-data hashes, rebuilds 27 tables, and compares
all rows and fields. It writes `verification.json` alongside the rebuilt tables.
The reference data and inputs remain unchanged. No network requests are made.

Expected result: `status=Verified`, `tables=27`, `inputs_verified=493`.
Twenty-six CSVs reproduce byte-for-byte. RPC estimates match at a relative tolerance
of `1e-12` and absolute tolerance of `1e-9`, accommodating floating-point formatting.
The comparison also requires exact row counts, columns, identifiers and timestamps.

[Reproduction map](../metadata/reproduction.csv) identifies the input and operation
for each table. Provider parsers use frozen source records. Derived tables are
recalculated from those inputs. Authored news, mechanism and source-history tables
are exported from frozen curated records; their factual interpretation comes from
the cited sources and the documented curation procedure.

The RPC workflow begins with the fixed sample selection and count summaries.
It recomputes hourly estimates from 12,000 block summaries. Retrieving full blocks
or repeating the original sampling-frame construction is a separate acquisition step.

[Acquisition guide](ACQUISITION.md) describes the original source routes and the
conditions for acquiring another snapshot. [Methods](../metadata/METHODS.md) define
the calculations used here. The CSV workflow uses the standard library.

## Second-level market tables

Use Python 3.12 with the pinned packages. From the module directory:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r reproduce/requirements-second.txt
.venv/bin/python reproduce/code/release_second_reproduce.py --data data --output /tmp/ecosystem-second-rebuilt
```

The command verifies 132 frozen input files (66 ZIPs and their checksums),
rebuilds all three Parquet tables and requires byte-identical output. It checks
all 1,584 hourly aggregate controls and NumPy rolling-statistic controls across
daily boundaries. Expected result: `status=Verified`, `tables=3`,
`inputs_verified=132`. The JSON receipt is `verification-second.json`.
Reconstruction makes no network requests; installing packages requires access
to a package index. Processing is bounded to one day in memory, with a 2 GiB
process guard and a 1 GiB available-memory floor. Allow about 400 MB of scratch
disk plus the installed environment.

## AWS-derived second-level tables

The 2.49 GB of selected AWS projections are not bundled, so the two offline commands above
do not rebuild these three tables. `aws-evidence/` records S3 keys, ETags, column
projections, daily validations and independent checks. `aws-evidence/recompute.json`
records the offline recomputation that gave identical output hashes. `code/build_aws_*.py`
acquire and rebuild the tables from the public AWS bucket; they expect the project layout
`<chain>/layer2/` and are supplied for inspection and re-acquisition.
