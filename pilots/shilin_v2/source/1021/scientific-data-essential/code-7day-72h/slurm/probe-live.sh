#!/bin/bash
#SBATCH --job-name=pump-probe-live
#SBATCH --partition=common
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --output=/work/so192/pumpfun-7day-72h/slurm/logs/%x-%j.out
#SBATCH --error=/work/so192/pumpfun-7day-72h/slurm/logs/%x-%j.err

set -euo pipefail
ROOT="/work/so192/scientific data/7day+72h"
cd "$ROOT"
echo "host $(hostname) python $("$ROOT/.venv/bin/python" -V) at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
"$ROOT/.venv/bin/python" -u "$ROOT/probe_live.py"
echo "probe done $(date -u +%Y-%m-%dT%H:%M:%SZ)"
