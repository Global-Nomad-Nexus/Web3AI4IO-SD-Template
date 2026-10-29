#!/bin/bash
#SBATCH --job-name=pump-7day-72h
#SBATCH --partition=common
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=128G
#SBATCH --time=14-00:00:00
#SBATCH --output=/work/so192/pumpfun-7day-72h/slurm/logs/%x-%j.out
#SBATCH --error=/work/so192/pumpfun-7day-72h/slurm/logs/%x-%j.err

# Frozen window 2026-10-08T00:00:00Z through 2026-10-15T00:00:00Z, then 72h follow-up.
# The process must be running before 2026-10-08T00:05:00Z. It waits until the
# window opens and does not scan early. Submit with:
#   sbatch "/work/so192/scientific data/7day+72h/slurm/collect-7day-72h.sh"
# If run_status.json says INCOMPLETE, submit this same script again.

set -euo pipefail
ROOT="/work/so192/scientific data/7day+72h"
cd "$ROOT"
mkdir -p "$ROOT/slurm/logs" "$ROOT/.tools"

ensure_python() {
  local py="$ROOT/.venv/bin/python"
  if [[ -x "$py" ]] && "$py" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)'; then
    if "$py" -c 'import curl_cffi' >/dev/null 2>&1; then
      return
    fi
  fi
  rm -rf "$ROOT/.venv"
  if [[ ! -x "$ROOT/.tools/uv/uv" ]]; then
    curl -LsSf https://astral.sh/uv/install.sh -o "$ROOT/.tools/uv-install.sh"
    UV_UNMANAGED_INSTALL="$ROOT/.tools/uv" sh "$ROOT/.tools/uv-install.sh"
  fi
  export UV_PYTHON_INSTALL_DIR="$ROOT/.tools/python"
  "$ROOT/.tools/uv/uv" --no-config --no-cache venv --python 3.12 --managed-python "$ROOT/.venv"
  "$ROOT/.tools/uv/uv" --no-config --no-cache pip install --python "$ROOT/.venv/bin/python" -r "$ROOT/requirements.txt"
}

ensure_python
echo "job ${SLURM_JOB_ID:-local} host $(hostname) python $("$ROOT/.venv/bin/python" -V) start $(date -u +%Y-%m-%dT%H:%M:%SZ)"
"$ROOT/.venv/bin/python" -u run_mvp.py --check
"$ROOT/.venv/bin/python" -u run_mvp.py --mode rpc
echo "end $(date -u +%Y-%m-%dT%H:%M:%SZ)"
