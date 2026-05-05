FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY sampler.py .

# Non-root. NVML is read-only and works fine without root; the GPU
# device files are accessible because Docker's nvidia runtime opens
# them with permissive group ownership.
RUN useradd -m -u 1003 sampler \
    && chown -R sampler:sampler /app
USER sampler

ENTRYPOINT ["python", "-u", "sampler.py"]
