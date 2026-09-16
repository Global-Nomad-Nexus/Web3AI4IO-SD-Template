"""Fresh local snapshot replay and event-definition invariance evidence."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from .common import file_hashes, load_json, write_json, utcnow, implementation_hashes, sha256
from .validate import semantic_hash

def run(root):
    root=Path(root)
    validation=load_json(root/"reports/validation.json")
    if not validation.get("passed"):
        raise RuntimeError("Complete local data validation before snapshot reproduction")
    baseline=load_json(root/"manifest.json")["semantic_tables"]
    raw_before=file_hashes(root,("raw",))
    report={"started_at":utcnow(),"environment":"fresh_local_directory","python":sys.version,"stages":[],"passed":False,
            "implementation_hashes":implementation_hashes(root),"raw_hashes":raw_before,"semantic_tables":baseline,
            "processed_file_hashes":file_hashes(root,("tables",)),"provenance_table_sha256":sha256(root/"provenance/requests.parquet")}
    with tempfile.TemporaryDirectory(prefix="claire-snapshot-replay-") as directory:
        fresh=Path(directory)
        for name in ("claire_demo","config","sources","raw","provenance","reports","vendor"):
            if (root/name).exists():
                shutil.copytree(root/name,fresh/name,ignore=shutil.ignore_patterns("__pycache__","*.stdout.log","*.tmp"))
        # Existing processed outputs are deliberately not copied.
        for stage in ("provenance","normalize","decode","derive_events","validate","visualize"):
            completed=subprocess.run([sys.executable,"-m","claire_demo","--root",str(fresh),stage],cwd=fresh,capture_output=True,text=True)
            report["stages"].append({"stage":stage,"returncode":completed.returncode})
            if completed.returncode:
                report["error"]={"stage":stage,"stdout_tail":completed.stdout[-4000:],"stderr_tail":completed.stderr[-2000:]}
                write_json(root/"reports/reproduction.json",report)
                return report
        replay=load_json(fresh/"manifest.json")["semantic_tables"]
        report["semantic_tables_equal"]=baseline==replay
        report["table_differences"]={key:{"baseline":baseline.get(key),"replay":replay.get(key)} for key in sorted(set(baseline)|set(replay)) if baseline.get(key)!=replay.get(key)}
        inputs=file_hashes(fresh)
        event_variants=[]
        for threshold in (1,3):
            completed=subprocess.run([sys.executable,"-m","claire_demo","--root",str(fresh),"derive_events","--thresholds",str(threshold)],cwd=fresh,capture_output=True,text=True)
            if completed.returncode: raise RuntimeError(completed.stdout[-2000:])
            actual=load_json(fresh/"reports/events.json").get("thresholds")
            event_variants.append({"threshold":threshold,"reported_thresholds":actual,"threshold_applied":actual==[threshold],"content":semantic_hash(fresh/"tables/events/events.parquet"),"raw_base_unchanged":file_hashes(fresh)==inputs})
        report["event_redefinition"]=event_variants
        report["original_raw_unchanged"]=file_hashes(root,("raw",))==raw_before
        report["implementation_unchanged"]=implementation_hashes(root)==report["implementation_hashes"]
        report["passed"]=report["semantic_tables_equal"] and report["original_raw_unchanged"] and report["implementation_unchanged"] and all(v["raw_base_unchanged"] and v["threshold_applied"] for v in event_variants)
    report["completed_at"]=utcnow()
    report["colab_compatibility"]="separate subsequent check"
    write_json(root/"reports/reproduction.json",report)
    return report
