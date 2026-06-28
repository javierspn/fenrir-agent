# One-shot benchmark-loader image (T031). Downloads + partitions math datasets into
# benchmark_tasks (FR-016). Run via: docker compose --profile bootstrap run benchmark-loader
# Base image digest is pinned by renovate (renovate.json docker rule).
FROM python:3.12-slim

WORKDIR /app

# Install the fenrir package (provides settings + db) and the loader's deps.
COPY pyproject.toml requirements-dev.txt ./
COPY fenrir/ ./fenrir/
COPY benchmark_loader/ ./benchmark_loader/
COPY infra/ ./infra/
RUN pip install --no-cache-dir .

# Apply migrations (idempotent) then load+partition benchmarks.
CMD ["sh", "-c", "python -m fenrir.db migrate && python -m benchmark_loader.load"]
