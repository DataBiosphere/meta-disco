

cd /private/groups/patenlab/apblair/findability-funk
srun --ntasks=1 \
	--cpus-per-task=32 \
	--mem=128G \
	--gres=gpu:2 \
	--partition=gpu \
	--time=10:00:00 \
	--pty bash

docker build -t terra-jupyter-ollama .

# chmod -R a+rwx /private/groups/patenlab/apblair/findability-funk
docker run -it --rm \
  --gpus all \
  -p 8889:8889 -p 11434:11434 \
  -v /private/groups/patenlab/apblair:/home/jupyter/work \
  --entrypoint bash \
  terra-jupyter-ollama \
  -c "ollama serve & jupyter lab --ip=0.0.0.0 --port=8889 --NotebookApp.use_redirect_file=False --NotebookApp.notebook_dir=/home/jupyter/work --allow-root"

# in a seperate terminal run
ssh -N -L 8889:localhost:8889 \
          -L 11434:localhost:11434 \
          -J apblair@mustard.prism apblair@phoenix-00

# http://localhost:8889/notebooks/lab/workspaces