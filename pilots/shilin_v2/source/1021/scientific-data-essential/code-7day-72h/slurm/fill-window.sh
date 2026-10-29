#!/bin/bash
#SBATCH --job-name=pump-window-fill
#SBATCH --partition=common
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=60-00:00:00
#SBATCH --output=/work/so192/pumpfun-7day-72h/slurm/logs/%x-%j.out
#SBATCH --error=/work/so192/pumpfun-7day-72h/slurm/logs/%x-%j.err

set -euo pipefail
ROOT="/work/so192/scientific data/7day+72h"
cd "$ROOT"
echo "host $(hostname) start $(date -u +%Y-%m-%dT%H:%M:%SZ)"
"$ROOT/.venv/bin/python" -u fill_gap.py scan
"$ROOT/.venv/bin/python" -u fill_gap.py observe
"$ROOT/.venv/bin/python" -u fill_gap.py merge
echo "done $(date -u +%Y-%m-%dT%H:%M:%SZ)"
