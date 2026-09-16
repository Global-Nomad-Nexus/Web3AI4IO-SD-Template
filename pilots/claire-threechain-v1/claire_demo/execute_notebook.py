"""Execute the local tutorial with an isolated current-interpreter kernelspec.

No kernel is installed globally. A failed cell preserves the partially executed
notebook and a failed receipt. Existing default event outputs are protected
across the tutorial's temporary threshold-one/threshold-three demonstrations.
"""
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile
import time
import traceback

import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpecManager

from .common import file_hashes, load_json, sha256, write_json


def _versions():
    result={"python":platform.python_version()}
    for name in ("nbclient","nbformat","jupyter_client","ipykernel","pandas","pyarrow"):
        try: result[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: result[name]="not_installed"
    return result


def _create_runtime(runtime, root):
    runtime=Path(runtime)
    name="claire-local-isolated"
    kernels=runtime/"kernels"
    spec=kernels/name
    spec.mkdir(parents=True)
    argv=[sys.executable,"-m","ipykernel_launcher","-f","{connection_file}"]
    write_json(spec/"kernel.json",{"argv":argv,"display_name":"Claire isolated current Python","language":"python"})
    env=dict(os.environ)
    for var,subdir in (("JUPYTER_CONFIG_DIR","config"),("JUPYTER_DATA_DIR","data"),
                       ("JUPYTER_RUNTIME_DIR","runtime"),("IPYTHONDIR","ipython"),("XDG_CACHE_HOME","cache")):
        directory=runtime/subdir
        directory.mkdir()
        env[var]=str(directory)
    env.update(PYTHONPATH=str(root),PYTHONDONTWRITEBYTECODE="1",CLAIRE_DEMO_MODE="snapshot",
               CLAIRE_NOTEBOOK_EXECUTOR="local")
    manager=KernelSpecManager(kernel_dirs=[str(kernels)],ensure_native_kernel=False,
                              data_dir=str(runtime/"data"))
    km=KernelManager(kernel_name=name,kernel_spec_manager=manager,
                     connection_file=str(runtime/"runtime/connection.json"))
    return name,env,km


def _execute_in_kernel(notebook, root, runtime, timeout=7200):
    """Small independently testable kernel runner; mutates notebook with outputs."""
    name,env,manager=_create_runtime(runtime,root)
    client=NotebookClient(notebook,km=manager,kernel_name=name,timeout=timeout,
                           allow_errors=False,record_timing=True,resources={"metadata":{"path":str(root)}})
    # NotebookClient owns and shuts down its kernel even when a cell raises.
    client.execute(cwd=str(root),env=env,cleanup_kc=True)
    return notebook


def _redact(value, root):
    """Keep released outputs portable without changing scientific content."""
    if isinstance(value,str): return value.replace(str(root),"<PILOT_ROOT>")
    if isinstance(value,list): return [_redact(x,root) for x in value]
    if isinstance(value,dict): return {k:_redact(v,root) for k,v in value.items()}
    return value


def _event_files(root):
    files=list((root/"tables/events").glob("*.parquet"))
    receipt=root/"reports/events.json"
    if receipt.exists(): files.append(receipt)
    return sorted(files)


def run(root):
    root=Path(root).resolve()
    start=time.monotonic()
    receipt={"status":"running","passed":False,"started_at":datetime.now(timezone.utc).isoformat(),
             "environment":"local","versions":_versions(),"kernel":"temporary kernelspec using current sys.executable",
             "mode":"snapshot","notebook":"notebooks/Claire_Onchain_Tutorial.ipynb",
             "executed_notebook":"notebooks/Claire_Onchain_Tutorial.executed.ipynb",
             "global_configuration_changed":False,"colab_status":"not_tested_by_this_command"}
    write_json(root/"reports/notebook_execution.json",receipt)
    notebook=None
    before=None
    backups={}
    error=None
    try:
        source=root/receipt["notebook"]
        notebook=nbformat.read(source,as_version=4)
        nbformat.validate(notebook)
        receipt["source_sha256"]=sha256(source)
        parts=[c.source.splitlines()[0] for c in notebook.cells if c.cell_type=="markdown" and c.source.startswith("## ")]
        if len(parts)!=8:
            raise ValueError("Expected the approved eight-part tutorial")
        validation_path=root/"reports/validation.json"
        if not validation_path.exists() or load_json(validation_path).get("passed") is not True:
            raise ValueError("Complete local collection, processing and technical validation before executing the full tutorial")
        baseline=load_json(root/"reports/events.json")
        if baseline.get("status")!="completed" or baseline.get("thresholds")!=[1,3]:
            raise ValueError("Execute the complete default threshold-(1,3) pipeline before notebook acceptance")
        if not (root/"tables/events/events.parquet").exists():
            raise ValueError("Default event table is missing")
        before=file_hashes(root,("raw","tables/base"))
        receipt["baseline_event_thresholds"]=baseline["thresholds"]
        receipt["protected_raw_base_files"]=len(before)
        # Runtime and event backups are task-local and removed after the run.
        with tempfile.TemporaryDirectory(prefix="notebook-runtime-",dir=root/"reports") as directory:
            runtime=Path(directory)
            backup_dir=runtime/"event-backups"
            backup_dir.mkdir()
            for i,path in enumerate(_event_files(root)):
                backup=backup_dir/str(i)
                shutil.copy2(path,backup)
                backups[str(path.relative_to(root))]={"path":backup,"sha256":sha256(path)}
            try:
                _execute_in_kernel(notebook,root,runtime)
                current=load_json(root/"reports/events.json")
                if current.get("thresholds")!=[1,3]:
                    raise RuntimeError("Notebook did not restore default event thresholds (1,3)")
                if any(o.output_type=="error" for c in notebook.cells if c.cell_type=="code" for o in c.get("outputs",[])):
                    raise RuntimeError("An executed notebook cell contains an error output")
            finally:
                restored=[]
                for relative,backup in backups.items():
                    target=root/relative
                    if not target.exists() or sha256(target)!=backup["sha256"]:
                        target.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copy2(backup["path"],target)
                        restored.append(relative)
                receipt["restored_event_baseline_files"]=restored
                receipt["event_baseline_unchanged"]=all((root/r).exists() and sha256(root/r)==v["sha256"] for r,v in backups.items())
        receipt["raw_base_unchanged"]=before==file_hashes(root,("raw","tables/base"))
        if not receipt["raw_base_unchanged"]:
            raise RuntimeError("Notebook processing changed a protected raw/base baseline file")
        receipt["event_thresholds_after"]=load_json(root/"reports/events.json").get("thresholds")
        receipt["executed_code_cells"]=sum(c.cell_type=="code" and c.execution_count is not None for c in notebook.cells)
        receipt["expected_code_cells"]=sum(c.cell_type=="code" for c in notebook.cells)
        if receipt["executed_code_cells"]!=receipt["expected_code_cells"]:
            raise RuntimeError("Not all notebook code cells executed")
        receipt.update(status="completed",passed=True)
    except Exception as exc:
        error=exc
        receipt.update(status="failed",passed=False,error={"type":type(exc).__name__,"message":str(exc),
                       "traceback":traceback.format_exc()[-12000:]})
        if before is not None:
            receipt["raw_base_unchanged"]=before==file_hashes(root,("raw","tables/base"))
        if (root/"reports/events.json").exists():
            receipt["event_thresholds_after"]=load_json(root/"reports/events.json").get("thresholds")
    finally:
        receipt["elapsed_seconds"]=round(time.monotonic()-start,3)
        receipt["completed_at"]=datetime.now(timezone.utc).isoformat()
        if notebook is not None:
            # Save partial outputs even after a failed cell. Source notebook stays editable and unchanged.
            notebook=nbformat.from_dict(_redact(notebook,root))
            target=root/receipt["executed_notebook"]
            target.parent.mkdir(parents=True,exist_ok=True)
            try:
                nbformat.write(notebook,target)
                receipt["executed_notebook_sha256"]=sha256(target)
            except Exception as save_error:
                receipt.update(status="failed",passed=False,output_save_error={"type":type(save_error).__name__,"message":str(save_error)})
                error=error or save_error
        write_json(root/"reports/notebook_execution.json",_redact(receipt,root))
    if error is not None:
        raise RuntimeError("Local notebook execution failed; inspect reports/notebook_execution.json") from error
    return receipt
