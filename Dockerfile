FROM us.gcr.io/broad-dsp-gcr-public/terra-jupyter-base:1.0.0

USER root

RUN find /etc/apt/sources.list.d/ -type f -exec sed -i '/cloud.google.com\|nvidia\|gcsfuse/d' {} \; && \
    apt-get update && apt-get install -y \
    curl \
    gnupg \
    ca-certificates \
    lsb-release \
    software-properties-common \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
        gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg && \
    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
        sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
        tee /etc/apt/sources.list.d/nvidia-container-toolkit.list && \
    apt-get update && apt-get install -y nvidia-container-toolkit

RUN curl -fsSL https://ollama.com/install.sh | bash

USER jupyter
WORKDIR /home/jupyter
