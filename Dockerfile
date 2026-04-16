# ---- Base image ----
# Replace with a Bosch-approved base image if required.
FROM python:3.11-slim-bookworm

LABEL maintainer="SIT Signal Analysis Team"
LABEL description="Data Analyzer Agent – automated SIT signal analysis"

# System deps (minimal)
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY config/ ./config/

# Placeholder: MATLAB Runtime installation
# The MATLAB Runtime is large (~2 GB) and is typically installed on the host
# or provided as a sidecar service.  Uncomment and adapt if needed.
# RUN mkdir -p /opt/matlab && \
#     wget -q <MATLAB_RUNTIME_URL> -O /tmp/mcr.zip && \
#     unzip /tmp/mcr.zip -d /opt/matlab && \
#     rm /tmp/mcr.zip

# Entry point
ENTRYPOINT ["python", "-m", "src.main"]
CMD ["--help"]
