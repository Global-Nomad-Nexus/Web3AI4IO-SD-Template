#!/bin/bash
#SBATCH --job-name=pump-7day-smoke
#SBATCH --partition=common
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:20:00
#SBATCH --output=/work/so192/pumpfun-7day-72h/slurm/logs/%x-%j.out
#SBATCH --error=/work/so192/pumpfun-7day-72h/slurm/logs/%x-%j.err

set -euo pipefail
ROOT="/work/so192/scientific data/7day+72h"
cd "$ROOT"
echo "host $(hostname) python $("$ROOT/.venv/bin/python" -V) at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
"$ROOT/.venv/bin/python" -m unittest discover -s tests -q
"$ROOT/.venv/bin/python" - << 'PY'
import time
import urllib.request
from mvp.acquire_chain import Http3Opener, JsonRpcClient

def slot(label, func):
    started = time.perf_counter()
    try:
        result = func()
    except Exception as exc:
        print(f"FAIL {label} {exc.__class__.__name__}: {exc} seconds={time.perf_counter()-started:.1f}")
        return False
    print(f"OK {label} {result} seconds={time.perf_counter()-started:.2f}")
    return True

https = JsonRpcClient("https://solana-rpc.publicnode.com", timeout=15, max_attempts=1, min_interval=0)
ok = slot("publicnode-https", lambda: https.call("getSlot", [{"commitment": "finalized"}]).get("result"))
opener = Http3Opener()
req = urllib.request.Request(
    "https://solana-rpc.publicnode.com",
    data=b'{"jsonrpc":"2.0","id":1,"method":"getSlot","params":[{"commitment":"finalized"}]}',
    headers={"Content-Type": "application/json"},
    method="POST",
)
def http3():
    with opener.open(req, timeout=20) as body:
        return body.read().decode()[:120]
try:
    slot("publicnode-http3", http3)
finally:
    opener.close()
official = JsonRpcClient("https://api.mainnet-beta.solana.com", timeout=15, max_attempts=1, min_interval=0)
slot("official-https", lambda: official.call("getSlot", [{"commitment": "finalized"}]).get("result"))
raise SystemExit(0 if ok else 1)
PY
echo "smoke done $(date -u +%Y-%m-%dT%H:%M:%SZ)"
