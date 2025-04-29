# meta-disco
This README provides instructions to set up and run the terra-jupyter-ollama Docker container on an interactive GPU node.

## Terra Jupyter Ollama Setup

This README provides instructions to set up and run the terra-jupyter-ollama Docker container on an interactive GPU node managed by the SLURM workload manager.

**1. Start an Interactive Node**

Use srun to start an interactive session with access to GPUs and sufficient resources:
```bash
srun --ntasks=1 \
	--cpus-per-task=32 \
	--mem=128G \
	--gres=gpu:2 \
	--partition=gpu \
	--nodelist=phoenix-00 \
	--time=10:00:00 \
	--pty bash
```

**2. Build the Docker Container**

Once on the interactive node, build the Docker image:
```bash
docker build -t terra-jupyter-ollama .
```

**3. Run the Docker Container**

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

**4. SSH Tunnel to Phoenix**

To access the JupyterLab and Ollama services from your local machine, set up an SSH tunnel:

```bash
ssh -N -L 8889:localhost:8889 \
          -L 11434:localhost:11434 \
          -J genomics-institute@mustard.prism genomics-institute@phoenix-00
```

Once connected, you can open:

http://localhost:8889/notebooks/ for JupyterLab

http://localhost:11434 for Ollama

**5. Ollama Example: NHGRI AnVIL Title Summarizer**

This Ollama model summarizes the number of files associated with each unique datasets.title entry from a .tsv file exported from the NHGRI AnVIL platform.

Create the model from the Modelfile
```
$ ollama create nhgri-anvil-titles -f Modelfile
```
Run the model on NHGRI data table TSV file:
```
>>> ollama run nhgri-anvil-titles "$(cat findability-funk/anvil-manifest-3a7b7cb2-10be-5eb2-9c74-28f2662904ee.40bc3110-e5b2-5c64-92d2-99d0f02b28ed.tsv)" please summarize the datasets
... .title counts
Here is the summary of unique title counts:

Title: 1000 Genomes Project
Title: Alzheimer's Disease Neuroimaging Initiative (ADNI)
Title: Cancer Genome Atlas (TCGA)
Title: ClinVar
Title: Database of Genomic Variants (DGV)
Title: Encyclopedia of DNA Elements (ENCODE)
Title: Gene Expression Omnibus (GEO)
Title: Genotype-Tissue Expression (GTEx)
Title: International HapMap Project
Title: National Center for Biotechnology Information (NCBI) ClinVar
Title: The Cancer Genome Atlas (TCGA)

There are 10 unique titles.
```
