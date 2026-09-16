# Claire component handoff

The machine-readable contract is [handoff_interface.json](../config/handoff_interface.json).
It points to the actual Parquet tables, dictionary, manifest and source evidence.
No off-chain collection or matching has been performed.

Use chain-qualified `object_id` to reference an observed object. EVM addresses
are normalized within their chain; Solana addresses retain case. An address is
not a person. `objects` contains observations across block partitions, so the
same ID can appear more than once. `observed_at` gives the time of each evidence
observation. `first_seen_in_window` repeats the minimum non-null `observed_at`
over all rows for the same ID. It is the first observation in this snapshot,
not the lifetime creation time.

To retrieve evidence, split `raw_ref` at `#`, open the gzip JSON file and follow
the JSON pointer. Join that file path to `provenance/requests.parquet.raw_path`
for acquisition time, source and checksum. Use `manifest.json` to identify this
exact data version. Collection time and chain observation time are different.

Token-account ownership is an evidenced relation with its observation time.
Same EVM address bytes across BSC and Base preserve two separate objects.
Future off-chain links need their own relation type, evidence and uncertainty;
the existing byte-equality links must not be relabeled as common ownership.

The event table is an optional research view. A later contributor may define
different events directly over the base and decoded records, without changing
these identifiers or recollecting the raw transactions. Shilin's collection,
cross-reproduction and joint integration remain separate work.
