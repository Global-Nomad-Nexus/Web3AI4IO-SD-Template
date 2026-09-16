"""Tiny real-Parquet/raw-reference fixture for the tutorial inspection cell."""
import gzip
import json
from pathlib import Path

import nbformat
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from IPython.display import HTML, Markdown

from claire_demo.build_notebook import run as build
from claire_demo.schemas import SCHEMAS
from claire_demo.decode import SCHEMAS as DECODED_SCHEMAS


def test_all_tables_preview_and_same_partition_join_are_bounded(tmp_path):
    build(tmp_path)
    raw=tmp_path/"raw/base/blocks/1.json.gz"
    raw.parent.mkdir(parents=True)
    tx={"hash":"0xone","input":"0x1234","nested":{"retained":True}}
    raw.write_bytes(gzip.compress(json.dumps({"result":{"transactions":[tx]}}).encode()))
    rows=[{"tx_id":"eip155:8453:tx:0xone","raw_ref":"raw/base/blocks/1.json.gz#/result/transactions/0"},
          {"tx_id":"eip155:8453:tx:0xtwo","raw_ref":"unused"}]
    parts={"tables/base/transactions":rows,
           "tables/base/transaction_accounts":[{"tx_id":rows[0]["tx_id"],"account_id":"a"},
                                               {"tx_id":rows[1]["tx_id"],"account_id":"b"},
                                               {"tx_id":rows[0]["tx_id"],"account_id":"c"}],
           "tables/decoded/asset_movements":[{"tx_id":rows[0]["tx_id"],"amount_raw":"1"},
                                             {"tx_id":rows[1]["tx_id"],"amount_raw":"999"}]}
    for relative,records in parts.items():
        path=tmp_path/relative/"base-1.parquet"
        path.parent.mkdir(parents=True)
        pq.write_table(pa.Table.from_pylist(records),path)
    notebook=nbformat.read(tmp_path/"notebooks/Claire_Onchain_Tutorial.ipynb",as_version=4)
    idx=next(i for i,c in enumerate(notebook.cells) if c.cell_type=="markdown" and c.source.startswith("## VI."))
    context={"ROOT":tmp_path,"Path":Path,"pd":pd,"pq":pq,"json":json,
             "display":lambda *args:None,"HTML":HTML,"Markdown":Markdown,"COMPLETED_PARTS":[]}
    exec(compile(notebook.cells[idx+1].source,"<bounded-inspection-fixture>","exec"),context)
    assert context["native_record"]==tx
    assert len(context["inventory"])==len(SCHEMAS)+len(DECODED_SCHEMAS)+2
    linked={row["table"]:row for row in context["related_summary"]}
    assert linked["tables/base/transaction_accounts"]["matching_rows"]==2
    assert linked["tables/decoded/asset_movements"]["matching_rows"]==1
    assert linked["tables/base/balance_observations"]["matching_rows"] is None
