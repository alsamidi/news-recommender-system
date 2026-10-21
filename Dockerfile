# Serving image for the goodnews web app (FastAPI + frozen hybrid recommender).
#
# Only the serving surface is installed. The research stack (torch,
# transformers, sentence-transformers, mlflow, jupyterlab) is not imported by
# `web.app` or by `HybridRecommender.load()` — measured by watching sys.modules
# across a real cold start: numpy, scipy, sklearn, pandas, pyarrow, implicit,
# pyyaml, fastapi, uvicorn, jinja2, python-multipart. Dropping the rest takes
# the image from a ~6 GB venv to a few hundred MB.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MALLOC_ARENA_MAX=2

WORKDIR /app

# libgomp1: implicit's C extension links against the OpenMP runtime, which
# python:3.12-slim does not ship (ImportError: libgomp.so.1 at import time).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first so a source edit does not invalidate the install layer.
COPY requirements-serve.txt ./requirements-serve.txt
RUN pip install --no-cache-dir -r requirements-serve.txt

# ---------------------------------------------------------------------------
# Artifacts. Only what `load_all()` opens is copied. The repository also holds
# 287 MB of IndoBERT embeddings, a 17 MB TF-IDF embedding dump and a duplicate
# vectorizer that serving never reads; excluding them keeps the image small and
# makes the served model unambiguous.
# ---------------------------------------------------------------------------
COPY configs/hybrid.yaml configs/als.yaml ./configs/
COPY data/processed/news_processed.parquet \
     data/processed/interactions_dev.parquet \
     data/processed/interactions_train.parquet ./data/processed/
COPY models/als_model.pkl \
     models/als_user_factors.npy \
     models/als_item_factors.npy \
     models/tfidf_baseline.pkl ./models/
COPY models/full_catalog_eval.json models/stratified_eval.json ./models/

COPY src/ ./src/

# The app resolves artifacts and config relative to the repository root, so it
# must run from /app. WEB_DB_PATH defaults to data/web.db inside the image;
# mount a volume there to keep accounts and history across restarts.
ENV WEB_DB_PATH=/data/web.db \
    WEB_ARTIFACT_CONFIG=configs/hybrid.yaml

RUN mkdir -p /data && useradd --create-home --uid 10001 app \
    && chown -R app:app /data /app
USER app

EXPOSE 8000

# Single worker on purpose: each worker loads its own copy of the model. Two
# workers roughly double the footprint and exceed a 512 MB tier.
#
# Memory (measured in this image, Docker on Linux x86_64):
#   idle, MALLOC_ARENA_MAX=2      405 MiB
#   24 concurrent sessions        431 MiB
#   idle without the tuning       471 MiB
# The tuning matters: glibc gives each thread its own arena, and the default
# cap lets a threaded ASGI server hold reclaimed pages. Two arenas were enough
# for this workload and left ~80 MiB of headroom on a 512 MB tier.
CMD ["python", "-m", "uvicorn", "web.app:app", \
     "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1"]
