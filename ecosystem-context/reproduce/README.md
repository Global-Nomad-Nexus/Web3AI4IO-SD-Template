# Offline reproduction

Use Python 3.11 or newer with the standard library and an IANA time-zone database
containing `America/New_York`. Linux and macOS normally provide this database;
on systems without it, install the Python `tzdata` package before running.

From the `ecosystem-context/` directory after extracting both companion archives:

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
the calculations used here. The full module occupies under 10 MB and needs only a
small fraction of a typical desktop's memory.
