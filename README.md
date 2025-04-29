# meta-disco

## Setup

1. Start an Interactive Node
Use srun to start an interactive session with access to GPUs and sufficient resources:
```bash
srun --ntasks=1 \
	--cpus-per-task=32 \
	--mem=128G \
	--gres=gpu:2 \
	--partition=gpu \
	--time=10:00:00 \
	--pty bash
```

2. Build the Docker Container
Once on the interactive node, build the Docker image:
```bash
docker build -t terra-jupyter-ollama .
```

3. Run the Docker Container
After building the image, run the container with GPU access, mounted volumes, and port forwarding:
```bash
docker run -it --rm \
  --gpus all \
  -p 8889:8889 -p 11434:11434 \
  -v /private/groups:/home/jupyter/work \
  --entrypoint bash \
  terra-jupyter-ollama \
  -c "ollama serve & jupyter lab --ip=0.0.0.0 --port=8889 --NotebookApp.use_redirect_file=False --NotebookApp.notebook_dir=/home/jupyter/work --allow-root"
```

NOTE: When running the container, please make the mounted volume readable and writeable by the container. 

