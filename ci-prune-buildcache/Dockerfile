FROM python:3.13-slim

WORKDIR /app/

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# TODO: switch to `develop` branch once PR is merged
RUN git clone --depth 1 --branch direct-pruning https://github.com/mvandenburgh/spack.git /opt/spack

# Install scripts
COPY entrypoint.sh ./
COPY fetch_keeplist.py ./

WORKDIR /work/

ENTRYPOINT [ "bash", "/app/entrypoint.sh"]
