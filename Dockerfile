# Base Terra Jupyter image
FROM us.gcr.io/broad-dsp-gcr-public/terra-jupyter-base:latest

# -------------------------
# System setup (as root)
# -------------------------
USER root

# Toolchain + build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake ninja-build git pkg-config \
    curl ca-certificates gnupg lsb-release software-properties-common \
    libcurl4-openssl-dev ccache wget jq \
    && rm -rf /var/lib/apt/lists/*

# -------------------------
# CUDA Toolkit (for GPU builds)
# -------------------------
RUN wget -q https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb && \
    dpkg -i cuda-keyring_1.1-1_all.deb && \
    rm -f cuda-keyring_1.1-1_all.deb && \
    apt-get update && \
    apt-get install -y --no-install-recommends nvidia-utils-525 cuda-toolkit-12-4 && \
    rm -rf /var/lib/apt/lists/*

ENV CUDA_HOME=/usr/local/cuda
ENV PATH=$CUDA_HOME/bin:$PATH
ENV LD_LIBRARY_PATH=$CUDA_HOME/lib64:$LD_LIBRARY_PATH

# -------------------------
# Build llama.cpp
# -------------------------
ENV LLAMA_PREFIX=/opt/llama.cpp
RUN git clone --depth 1 https://github.com/ggml-org/llama.cpp ${LLAMA_PREFIX}

# CPU-only build
RUN cmake -S ${LLAMA_PREFIX} -B ${LLAMA_PREFIX}/build-cpu \
      -DCMAKE_BUILD_TYPE=Release \
      -DBUILD_SHARED_LIBS=OFF \
      -DLLAMA_CURL=ON -DGGML_CUDA=OFF && \
    cmake --build ${LLAMA_PREFIX}/build-cpu -j

# CUDA build (Ampere+Ada archs as example; adjust if needed)
ENV CMAKE_CUDA_ARCHITECTURES="86;89"
RUN cmake -S ${LLAMA_PREFIX} -B ${LLAMA_PREFIX}/build-cuda \
      -DCMAKE_BUILD_TYPE=Release \
      -DBUILD_SHARED_LIBS=OFF \
      -DLLAMA_CURL=ON -DGGML_CUDA=ON \
      -DCMAKE_CUDA_ARCHITECTURES="${CMAKE_CUDA_ARCHITECTURES}" && \
    cmake --build ${LLAMA_PREFIX}/build-cuda -j

# Make binaries easy to find
RUN ln -sf ${LLAMA_PREFIX}/build-cpu/bin /usr/local/llama-cpu && \
    ln -sf ${LLAMA_PREFIX}/build-cuda/bin /usr/local/llama-cuda || true

# -------------------------
# Ollama (optional)
# -------------------------
RUN curl -fsSL https://ollama.com/install.sh | sh || true

# -------------------------
# Conda/Jupyter setup
# -------------------------
RUN mkdir -p /home/jupyter/.conda && \
    chown -R jupyter:jupyter /home/jupyter/.conda

USER jupyter
WORKDIR /home/jupyter

RUN conda config --add pkgs_dirs /home/jupyter/.conda/pkgs && \
    conda config --add envs_dirs /home/jupyter/.conda/envs && \
    conda config --set auto_activate_base false

COPY --chown=jupyter:jupyter environment.yaml /home/jupyter/environment.yaml

# --- FIX: ensure conda notices cache is writable ---
USER root
RUN mkdir -p /home/jupyter/.cache/conda/notices && \
    chown -R jupyter:jupyter /home/jupyter/.cache
USER jupyter
# ---------------------------------------------------

RUN conda env create -f environment.yaml

# Torch GPU wheels (cu118)
RUN conda run -n metadisco pip install \
      torch==2.2.0+cu118 torchvision==0.17.0+cu118 torchaudio==2.2.0+cu118 \
      --index-url https://download.pytorch.org/whl/cu118

RUN conda run -n metadisco conda install -y numpy
RUN conda run -n metadisco python -m ipykernel install --user \
      --name metadisco --display-name "meta-disco"
