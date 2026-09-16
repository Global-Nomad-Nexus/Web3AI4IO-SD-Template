"""Package the locally accepted tutorial for a subsequent Colab compatibility run."""
from pathlib import Path
import tarfile
from .common import load_json, write_json, sha256, utcnow, file_hashes, implementation_hashes

def run(root):
    root=Path(root)
    for name in ("validation","reproduction","notebook_execution"):
        if not load_json(root/f"reports/{name}.json").get("passed"):
            raise RuntimeError(f"Local {name} must pass before packaging a complete demo")
    accepted=load_json(root/"reports/reproduction.json")
    for name,current in (("implementation_hashes",lambda:implementation_hashes(root)),("raw_hashes",lambda:file_hashes(root,("raw",))),
                         ("processed_file_hashes",lambda:file_hashes(root,("tables",))),
                         ("provenance_table_sha256",lambda:sha256(root/"provenance/requests.parquet"))):
        if accepted.get(name)!=current():
            raise RuntimeError(f"{name} changed since local reproduction; rerun the affected validation")
    notebook=load_json(root/"reports/notebook_execution.json")
    for path_key,hash_key in (("notebook","source_sha256"),("executed_notebook","executed_notebook_sha256")):
        if sha256(root/notebook[path_key])!=notebook.get(hash_key):
            raise RuntimeError(f"{path_key} changed since local notebook execution")
    folders=("claire_demo","config","sources","raw","provenance","tables","docs","notebooks","figures","reports","vendor","tests")
    standalone=("README.md","requirements.txt","requirements-local.lock.txt","manifest.json")
    paths=[p for name in folders for p in sorted((root/name).rglob("*")) if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith((".tmp",".stdout.log"))]
    paths += [root/name for name in standalone if (root/name).exists()]
    archives=[]
    for filename,include_processed in (("claire-demo.tar.gz",True),("claire-snapshot.tar.gz",False)):
        output=root/"release"/filename
        output.parent.mkdir(exist_ok=True)
        temp=output.with_suffix(".tmp")
        included=[]
        with tarfile.open(temp,"w:gz",compresslevel=1) as archive:
            for p in paths:
                relative=p.relative_to(root)
                if not include_processed and (relative.parts[0]=="tables" or p.name.endswith(".executed.ipynb")):
                    continue
                if p.is_symlink(): raise RuntimeError(f"Unexpected symlink: {relative}")
                archive.add(p,arcname=str(relative),recursive=False)
                included.append(str(relative))
        temp.replace(output)
        archives.append({"path":str(output.relative_to(root)),"sha256":sha256(output),"bytes":output.stat().st_size,
                         "file_count":len(included),"processed_tables_included":include_processed})
    report={"created_at":utcnow(),"archives":archives,"colab_upload":"release/claire-snapshot.tar.gz",
            "colab_status":"ready_to_test;not_yet_accepted","publication_status":"local_only"}
    write_json(root/"reports/bundle.json",report)
    return report
