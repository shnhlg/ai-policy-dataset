FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2
ENV PYTHONUTF8=1 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY viewer/*.py viewer/*.jsonl ./viewer/
COPY viewer/static/ ./viewer/static/
COPY scripts/docker_serve.py scripts/prepare_runtime.py scripts/verify_restore.py scripts/test_runtime.py scripts/benchmark_viewer.py scripts/normalize_csv_headers.py ./scripts/
COPY tests/ ./tests/
COPY dataset_manifest.json ./
RUN useradd --uid 10001 --create-home policy && mkdir /runtime && chown policy:policy /runtime
USER policy
EXPOSE 8765
CMD ["python", "scripts/docker_serve.py", "--host", "0.0.0.0", "--port", "8765"]
