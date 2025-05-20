#!/bin/bash

# Activate the environment
conda activate myenv || { echo "❌ Failed to activate conda environment"; exit 1; }

# Pull the Ollama model
ollama pull llama3.2

# Register the Jupyter kernel
python -m ipykernel install --user --name myenv --display-name "meta-disco"