# Serving image for the goodnews web app (FastAPI + hybrid recommender).
#
# Only the serving surface is installed. The research stack (torch,
# transformers, sentence-transformers, mlflow, jupyterlab) is not imported by
# `web.app` or by the recommender loader — measured by watching sys.modules
# across a real cold start: numpy, scipy, sklearn, pandas, pyarrow, implicit,
# pyyaml, fastapi, uvicorn, jinja2, python-multipart. Dropping the rest takes
# the image from a ~6 GB venv to a few hundred MB.
#
# Era: the image serves the ACTIVE indo corpus (configs/indo_serving.yaml,
# alpha 0.8, 67,381 items) and keeps the frozen MIND catalog untouched. The
# era switch stays available: `-e SERVING_ERA=mind` with MIND artifacts
# mounted will serve the frozen v1 path instead.

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
# Artifacts, indo era. Exactly what `IndoHybridRecommender` opens plus what the
# web services read at startup:
#
#   catalog.parquet               serving scores + article metadata
#   catalog_train.parquet         TF-IDF fit (train only, never refit on full)
#   interactions_train.parquet    ALS id orders, popularity, train history
#   interactions_dev.parquet      dataset reader counts, demo presets
#   indo_als_model.pkl            factors (user_factors/item_factors inside)
#
# Deliberately NOT copied:
#   catalog_dev.parquet           written by the split, never read at runtime
#   indo_als_{user,item}_factors  duplicates of the factors inside the pickle
#   indo_eval.json                evaluation record, not a serving input
#   data/raw/final_merge_dataset.csv (207 MB)
#                                 only the Link column is needed; it is
#                                 pre-derived into source_links.parquet above
#   data/processed/news_processed.parquet and MIND models
#                                 era MIND only, not read while SERVING_ERA is
#                                 unset (the default)
# ---------------------------------------------------------------------------
COPY configs/indo_serving.yaml ./configs/
COPY data/processed/indo/catalog.parquet \
     data/processed/indo/catalog_train.parquet \
     data/processed/indo/interactions_train.parquet \
     data/processed/indo/interactions_dev.parquet ./data/processed/indo/
# Portal links for the detail page: the derived 3.2 MB table, not the 207 MB
# raw CSV. Rebuild with `python -m src.phase2.build_links` if the corpus is
# relocked. Without it the page still renders, only without the source link.
COPY data/processed/indo/source_links.parquet ./data/processed/indo/
COPY models/indo_als_model.pkl ./models/

COPY src/ ./src/

# The app resolves artifacts and config relative to the repository root, so it
# must run from /app. WEB_DB_PATH defaults to data/web.db inside the image;
# mount a volume there to keep accounts and history across restarts.
#
# WEB_ARTIFACT_CONFIG is still set because src/web/config.py reads it; the indo
# loader ignores it and resolves configs/indo_serving.yaml on its own.
ENV WEB_DB_PATH=/data/web.db \
    WEB_ARTIFACT_CONFIG=configs/indo_serving.yaml

RUN mkdir -p /data && useradd --create-home --uid 10001 app \
    && chown -R app:app /data /app
USER app

EXPOSE 8000

# Single worker on purpose: each worker loads its own copy of the model. The
# indo path transforms the full 67,381-document catalog through TF-IDF at
# startup, which costs ~20 s and holds a sparse matrix of ~9.2 M non-zeros.
#
# Memory note (MALLOC_ARENA_MAX=2): glibc gives each thread its own arena and
# the default cap lets a threaded ASGI server hold reclaimed pages. Two arenas
# keep the idle footprint near 400 MiB; the numbers recorded in
# docs/web/DEPLOYMENT.md are MIND-era measurements and will differ here.
CMD ["python", "-m", "uvicorn", "web.app:app", \
     "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1"]
