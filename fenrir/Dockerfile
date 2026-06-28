# Image for the cognitive loop + the fenrir:8080/llm proxy (002, T005).
# Includes the docker CLI so runner.py can spawn ephemeral `--network none` sandboxes
# via the mounted /var/run/docker.sock.
FROM python:3.12-slim

# docker CLI only (to spawn sandboxes via the mounted host /var/run/docker.sock).
# The static binary is deterministic; the Debian docker.io package doesn't reliably
# place the CLI on PATH in slim images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.5.1.tgz \
       | tar -xz -C /usr/local/bin --strip-components=1 docker/docker \
    && apt-get purge -y curl && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* \
    && docker --version

WORKDIR /app
COPY pyproject.toml ./
COPY fenrir ./fenrir
RUN pip install --no-cache-dir .

# Default: bring up the proxy. The loop is run on demand (`python -m fenrir.core --run N`).
CMD ["uvicorn", "fenrir.llm.proxy:app", "--host", "0.0.0.0", "--port", "8080"]
