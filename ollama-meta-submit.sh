#!/bin/bash
#SBATCH --job-name=anvil_ai_ollama
#SBATCH --output=logs/anvil_ai_ollama_%A_%a.out
#SBATCH --error=logs/anvil_ai_ollama_%A_%a.err
#SBATCH --array=[0-146]%15             # One for each line in JSONL
#SBATCH --time=00:30:00
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --partition=medium
#SBATCH --nodelist=phoenix-10  # 👈 ensures it runs on the Ollama host

python3 ollama-llama3.2-AnVIL-agent.py $SLURM_ARRAY_TASK_ID
