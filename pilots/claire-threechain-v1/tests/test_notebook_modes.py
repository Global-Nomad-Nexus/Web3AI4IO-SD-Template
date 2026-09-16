"""Bounded notebook-mode checks; no full tutorial, network or Colab execution."""
import json
from pathlib import Path

import nbformat
import pytest

from claire_demo import build_notebook as tutorial


def manifest():
    return {"acceptance":"passed","window":{"start":"a","end":"b"},
            "raw_files":{"raw/base/1.json.gz":"original"},
            "semantic_tables":{"tables/base/transactions":{"sha256":"rows","rows":2}}}


def test_baseline_is_retained_before_manifest_is_replaced(tmp_path):
    original=manifest()
    path=tmp_path/"manifest.json"
    path.write_text(json.dumps(original))
    baseline=tutorial.snapshot_baseline(tmp_path)
    assert tutorial.compare_snapshot_manifest(baseline,original)["passed"]
    rebuilt=manifest()
    rebuilt["raw_files"]["raw/base/1.json.gz"]="changed"
    rebuilt["semantic_tables"]["tables/base/transactions"]["rows"]=3
    path.write_text(json.dumps(rebuilt))
    result=tutorial.compare_snapshot_manifest(baseline,json.loads(path.read_text()))
    assert result["passed"] is False
    assert result["raw_files"]["changed_entries"]==1
    assert result["semantic_tables"]["changed_entries"]==1
    assert baseline["raw_files"]==original["raw_files"]


def test_snapshot_requires_usable_baseline(tmp_path):
    (tmp_path/"manifest.json").write_text(json.dumps({"acceptance":"failed"}))
    with pytest.raises(RuntimeError,match="passed manifest"):
        tutorial.snapshot_baseline(tmp_path)


def test_live_directory_has_implementation_but_no_snapshot_cache(tmp_path):
    contents={"claire_demo/__main__.py":"# test fixture", "config/rpc.json":"{}",
              "sources/example.json":"{}", "vendor/mermaid.min.js":"fixture",
              "docs/example.md":"fixture", "requirements.txt":"nbformat",
              "raw/cache.json":"snapshot", "reports/collection.json":"snapshot",
              "tables/base/transactions/fixture.parquet":"snapshot", "manifest.json":"snapshot"}
    for relative,content in contents.items():
        path=tmp_path/relative
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(content)
    first=tutorial.prepare_live_root(tmp_path)
    second=tutorial.prepare_live_root(tmp_path)
    assert first!=second and first.parent==tmp_path/"live_runs"
    for relative in contents:
        copied=relative.split("/")[0] in {"claire_demo","config","sources","vendor","docs","requirements.txt"}
        assert (first/relative).exists() is copied
        assert (tmp_path/relative).read_text()==contents[relative]


def test_local_execution_cannot_issue_colab_receipt(tmp_path,monkeypatch):
    monkeypatch.setenv("CLAIRE_NOTEBOOK_EXECUTOR","local")
    assert tutorial.is_real_colab() is False
    result=tutorial.write_colab_receipt(tmp_path,"snapshot",list("1234567"),[],{"passed":True})
    assert result["status"]=="not_written"
    assert not (tmp_path/"reports/colab.json").exists()


def test_failed_prerequisite_cannot_issue_colab_receipt(tmp_path,monkeypatch):
    # Model the environment gate only; no successful receipt is forged locally.
    monkeypatch.setattr(tutorial,"is_real_colab",lambda:True)
    (tmp_path/"reports").mkdir()
    (tmp_path/"reports/validation.json").write_text('{"passed":true}')
    (tmp_path/"reports/events.json").write_text('{"thresholds":[1,3]}')
    for parts,stages,comparison in [([],[],{"passed":True}),
            (["I","II","III","IV","V","VI","VII"],
             ["provenance","normalize","decode","derive_events","validate","visualize"],{"passed":False})]:
        with pytest.raises(RuntimeError,match="Colab receipt requires"):
            tutorial.write_colab_receipt(tmp_path,"snapshot",parts,stages,comparison)
    assert not (tmp_path/"reports/colab.json").exists()


def test_generated_cells_have_valid_syntax_and_snapshot_network_guard(tmp_path):
    tutorial.run(tmp_path)
    notebook=nbformat.read(tmp_path/"notebooks/Claire_Onchain_Tutorial.ipynb",as_version=4)
    for cell in notebook.cells:
        if cell.cell_type=="code":
            compile(cell.source,"<generated-notebook>","exec")
    setup=next(c.source for c in notebook.cells if c.cell_type=="code" and "BASELINE_MANIFEST =" in c.source)
    assert "snapshot_baseline(ROOT) if MODE == \"snapshot\"" in setup
    acquisition=next(c.source for c in notebook.cells if c.cell_type=="code" and "LIVE_ROOT = prepare_live_root" in c.source)
    context={"MODE":"snapshot","ROOT":tmp_path,"report":lambda _: {},
             "display":lambda *args: None,"pd":__import__("pandas"),"COMPLETED_PARTS":[],
             "run_stage":lambda *args: pytest.fail("Snapshot acquisition must not call network stages")}
    (tmp_path/"raw").mkdir()
    (tmp_path/"reports").mkdir()
    (tmp_path/"reports/window.json").write_text("{}")
    exec(compile(acquisition,"<snapshot-acquisition>","exec"),context)
    assert context["COMPLETED_PARTS"]==["III"]
