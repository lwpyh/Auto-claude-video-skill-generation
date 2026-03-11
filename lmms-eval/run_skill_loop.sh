#!/bin/bash
#SBATCH -p sae
#SBATCH -A pilot_sae_gpu
#SBATCH -t 08:00:00
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-gpu=8
#SBATCH --mem-per-cpu=12G
#SBATCH --job-name=skill_loop

set -e
module load miniforge/24.7.1
module load gcc/12.2.0
module load cuda/12.4.0-gcc-12.2.0

PYTHON="/data/home/acw652/.conda/envs/verl-tool-env/bin/python"
LMMS_DIR="/data/DERI-Gong/jh015/lmms-eval"

export HF_HOME="/data/home/acw652/.cache/huggingface"
export TRANSFORMERS_OFFLINE=1
export CUDA_VISIBLE_DEVICES=0

cd "$LMMS_DIR"
$PYTHON -m pip install -e . -q --no-deps 2>&1 | tail -1

echo "=== Skill Discovery Loop | $(date) ==="

$PYTHON -m skill_learning.loop \
    --n         100 \
    --max_iters 3

echo "=== Done | $(date) ==="
