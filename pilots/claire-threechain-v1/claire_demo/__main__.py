"""Each stage can be rerun independently. Offline stages reject networking."""
import argparse
import importlib
import json
import platform
import resource
import socket
import time
from pathlib import Path
from .common import append_jsonl, utcnow, file_hashes, write_json

STAGES = ("preflight", "resolve_window", "collect", "crosscheck", "transaction_probe", "provenance", "normalize", "decode", "derive_events", "visualize", "validate", "replay", "reproduce", "build_notebook", "execute_notebook", "bundle")

def forbid_network(*args, **kwargs):
    raise RuntimeError("Network is disabled in snapshot processing and event derivation")

def run_stage(root, stage, thresholds=(1,3)):
    started, begin = utcnow(), time.monotonic()
    result, error = None, None
    try:
        if stage in ("preflight", "resolve_window", "collect"):
            from . import acquire
            result = getattr(acquire, stage)(root)
        elif stage in ("crosscheck","transaction_probe"):
            result=importlib.import_module("claire_demo."+stage).run(root)
        else:
            # Python audit hook also guards sockets opened by indirectly imported libraries.
            import sys
            def audit(event, args):
                if event in ("socket.connect", "socket.getaddrinfo", "socket.sendto"):
                    forbid_network()
            # A local notebook kernel uses local IPC; its processing subprocesses
            # enforce the same offline policy through their own CLI entry points.
            if stage != "execute_notebook": sys.addaudithook(audit)
            if stage == "replay":
                before=file_hashes(root,("raw",))
                result={s:run_stage(root,s) for s in ("provenance","normalize","decode","derive_events","validate","visualize")}
                if before != file_hashes(root,("raw",)): raise RuntimeError("Replay changed immutable raw files")
            else:
                module="events" if stage=="derive_events" else stage
                before=file_hashes(root) if stage in ("derive_events","visualize","validate") else None
                implementation=importlib.import_module("claire_demo."+module)
                result=implementation.run(root,thresholds=thresholds) if stage=="derive_events" else implementation.run(root)
                if before is not None and before != file_hashes(root): raise RuntimeError(f"{stage} changed raw/base files")
        if isinstance(result,dict) and any(result.get(k) is False for k in ("core_access","resolved","complete","passed")):
            raise RuntimeError(f"{stage} did not pass; inspect its saved report")
        return result
    except BaseException as exc:
        error={"type":type(exc).__name__,"message":str(exc)}
        raise
    finally:
        append_jsonl(root/"provenance/runs.jsonl",dict(stage=stage,started_at=started,completed_at=utcnow(),elapsed_seconds=time.monotonic()-begin,peak_rss_native=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,peak_rss_unit="bytes" if platform.system()=="Darwin" else "KiB",python=platform.python_version(),status="interrupted" if error and error["type"]=="KeyboardInterrupt" else "failed" if error else "completed",error=error))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path.cwd())
    parser.add_argument("stage",choices=STAGES)
    parser.add_argument("--thresholds",type=int,nargs="+",default=[1,3],help="Positive distinct-trade transaction thresholds; derive_events only")
    args=parser.parse_args()
    try:
        result=run_stage(args.root.resolve(),args.stage,tuple(args.thresholds))
        print(json.dumps(result,indent=2,default=str))
        if isinstance(result,dict) and any(result.get(k) is False for k in ("core_access","resolved","complete","passed")):
            raise SystemExit(2)
    except Exception as exc:
        print(json.dumps({"stage":args.stage,"status":"failed","error":str(exc)}))
        raise SystemExit(2)

if __name__=="__main__": main()
