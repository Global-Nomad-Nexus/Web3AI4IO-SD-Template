"""Bounded executor checks; these never execute the real acquisition tutorial."""
import json
import sys
from pathlib import Path

import nbformat
import pytest
from nbclient.exceptions import CellExecutionError

from claire_demo import execute_notebook as executor
from claire_demo.common import write_json


def make_baseline(root):
    (root/"notebooks").mkdir()
    cells=[nbformat.v4.new_markdown_cell(f"## {i}. Fixture") for i in range(8)]
    cells.append(nbformat.v4.new_code_cell("print('bounded fixture')"))
    nb=nbformat.v4.new_notebook(cells=cells)
    nbformat.write(nb,root/"notebooks/Claire_Onchain_Tutorial.ipynb")
    write_json(root/"reports/events.json",{"status":"completed","thresholds":[1,3]})
    write_json(root/"reports/validation.json",{"passed":True,"scope":"bounded executor test fixture only"})
    (root/"tables/events").mkdir(parents=True)
    (root/"tables/events/events.parquet").write_bytes(b"opaque baseline fixture")
    (root/"raw").mkdir()
    (root/"raw/fixture.json").write_text('{"immutable":true}')


def test_failed_cell_restores_events_and_preserves_failed_receipt(tmp_path,monkeypatch):
    make_baseline(tmp_path)
    def fail(notebook,root,runtime,timeout=7200):
        write_json(root/"reports/events.json",{"status":"completed","thresholds":[3]})
        (root/"tables/events/events.parquet").write_bytes(b"temporary threshold three")
        notebook.cells[-1].execution_count=1
        notebook.cells[-1].outputs=[nbformat.v4.new_output("error",ename="ValueError",evalue="fixture failure",traceback=["fixture failure"])]
        raise ValueError("fixture failure")
    monkeypatch.setattr(executor,"_execute_in_kernel",fail)
    with pytest.raises(RuntimeError,match="execution failed"):
        executor.run(tmp_path)
    receipt=json.loads((tmp_path/"reports/notebook_execution.json").read_text())
    assert receipt["passed"] is False and receipt["status"]=="failed"
    assert receipt["event_thresholds_after"]==[1,3]
    assert receipt["raw_base_unchanged"] is True
    assert receipt["event_baseline_unchanged"] is True
    assert (tmp_path/"tables/events/events.parquet").read_bytes()==b"opaque baseline fixture"
    partial=nbformat.read(tmp_path/"notebooks/Claire_Onchain_Tutorial.executed.ipynb",as_version=4)
    assert partial.cells[-1].outputs[0].output_type=="error"
    assert not list((tmp_path/"reports").glob("notebook-runtime-*"))


def test_protected_raw_change_cannot_pass(tmp_path,monkeypatch):
    make_baseline(tmp_path)
    def mutate(notebook,root,runtime,timeout=7200):
        (root/"raw/fixture.json").write_text('{"immutable":false}')
        notebook.cells[-1].execution_count=1
    monkeypatch.setattr(executor,"_execute_in_kernel",mutate)
    with pytest.raises(RuntimeError,match="execution failed"):
        executor.run(tmp_path)
    receipt=json.loads((tmp_path/"reports/notebook_execution.json").read_text())
    assert receipt["raw_base_unchanged"] is False
    assert receipt["passed"] is False


def test_success_requires_every_code_cell(tmp_path,monkeypatch):
    make_baseline(tmp_path)
    def no_execution(notebook,root,runtime,timeout=7200):
        return notebook
    monkeypatch.setattr(executor,"_execute_in_kernel",no_execution)
    with pytest.raises(RuntimeError,match="execution failed"):
        executor.run(tmp_path)
    receipt=json.loads((tmp_path/"reports/notebook_execution.json").read_text())
    assert receipt["executed_code_cells"]==0
    assert receipt["expected_code_cells"]==1
    assert receipt["passed"] is False


def test_real_tiny_kernel_uses_current_python_and_stops_on_error(tmp_path):
    runtime=tmp_path/"runtime-test"
    runtime.mkdir()
    notebook=nbformat.v4.new_notebook(cells=[
        nbformat.v4.new_code_cell("import sys,os,json; print(json.dumps({'python':sys.executable,'mode':os.environ['CLAIRE_DEMO_MODE'],'ipython':os.environ['IPYTHONDIR']}))"),
        nbformat.v4.new_code_cell("raise ValueError('intentional bounded test')"),
        nbformat.v4.new_code_cell("raise AssertionError('this cell must not execute')")])
    with pytest.raises(CellExecutionError,match="intentional bounded test"):
        executor._execute_in_kernel(notebook,tmp_path,runtime,timeout=30)
    observed=json.loads("".join(o.get("text","") for o in notebook.cells[0].outputs if o.output_type=="stream"))
    assert observed["python"]==sys.executable
    assert observed["mode"]=="snapshot"
    assert Path(observed["ipython"]).is_relative_to(runtime)
    assert notebook.cells[1].outputs[-1].output_type=="error"
    assert notebook.cells[2].execution_count is None
