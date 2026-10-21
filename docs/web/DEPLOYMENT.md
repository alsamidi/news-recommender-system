# Deploying the demo

The web app is a FastAPI service with a frozen recommender loaded in-process.
It needs **no database server**: accounts, sessions and reading history live in
SQLite at `WEB_DB_PATH`.

Measured facts (Docker on Linux x86_64, this image):

| | |
|---|---|
| Image size | **804 MB** (excluding the 306 MB of artifacts serving never reads) |
| Cold start | **~25 s** (parquet + pickles + TF-IDF transform) |
| Idle memory | **445-476 MiB** across four cold starts |
| Memory, 24 concurrent sessions | **481-498 MiB**, no OOM |
| Serving dependencies | 13 packages (no torch/transformers) |

The single most important number: **~500 MiB peak against a 512 MB ceiling.**
That fits, but with under 3% headroom — inside the noise of a single cold
start. A 512 MB tier is therefore "it ran in testing", not "it will stay up".
Treat **1 GB as the real requirement** and 512 MB as an experiment.

An earlier single measurement of 405 MiB idle did not reproduce (four later
runs: 445, 454, 454, 476). The lower figure came from a run whose allocator
had not yet grown; use the range, not the best case.

## Build and run

```bash
docker build -t goodnews:latest .
docker run -d --name goodnews-app -p 8000:8000 -v goodnews-data:/data goodnews:latest
```

`WEB_DB_PATH` defaults to `/data/web.db` inside the image. Mount a volume there
or every restart loses accounts and history.

Use a **named volume**, not a bind mount to `./data`. The container runs as
uid 10001, so a host directory owned by your user is not writable and SQLite
fails at startup with `attempt to write a readonly database`. If a bind mount
is required, `chown 10001:10001` the directory first.

Optional demo persona (a dataset user that has ALS factors, so the warm path
is exercised instead of the cold fallback):

```bash
docker run -p 8000:8000 -v "$PWD/data:/data" \
  -e WEB_DEMO_PERSONA_USER_ID=<dataset user id with ALS factors> \
  -e WEB_DEMO_PERSONA_EMAIL=demo@example.com \
  -e WEB_DEMO_PERSONA_PASSWORD=<a password you choose> \
  goodnews
docker exec <container> python -m src.web.seed_persona   # idempotent
```

Never commit those values. `WEB_DEMO_PERSONA_PASSWORD` is deliberately
unset by default so no credential sits in the source tree.

## Why the image is 804 MB and not 6 GB

`requirements.txt` is the research stack: torch, transformers,
sentence-transformers, mlflow, jupyterlab, psycopg2. None of it is imported on
the serving path. `requirements-serve.txt` pins only what a real cold start
plus a static import scan of `src/web`, `src/api` and `src/models` actually
needs.

Two artefacts are excluded on purpose:

- `models/indobert_embeddings.npy` (288 MB) — an evaluated comparison baseline,
  never loaded by `HybridRecommender.load()`.
- `models/tfidf_embeddings.npz` and `models/tfidf_vectorizer.pkl` (19 MB) —
  the vectorizer is already inside `tfidf_baseline.pkl`, and the embedding
  dump is a research output.

Excluding them also makes the served model unambiguous: the image contains
exactly the artefacts the frozen evaluation describes.

## Platform notes

Free tiers change often; verify before relying on any row.

| Option | Fits? | Why |
|---|---|---|
| **Oracle Cloud Always Free** (ARM Ampere A1) | ✅ best fit | 2 OCPU / 12 GB, always-on, no spin-down. The only option that never sleeps and has room to spare. Requires a card for identity verification, and ARM means the build must run on arm64 or be multi-arch. |
| **Hugging Face Spaces** (Docker, free CPU) | ✅ | 2 vCPU / 16 GB. A Docker Space works, but Spaces expect an HTTP app on a given port and add a repo-based deploy flow. Its public URL is a good fit for a thesis demo. Spaces on free CPU sleep after inactivity. |
| **Render Free** | ❌ | 512 MB / 0.1 CPU against a measured ~500 MiB peak — no margin. It also spins down after 15 min idle, and the free tier's filesystem is ephemeral, so the SQLite file is destroyed on every spin-down: accounts and history vanish between visits. Free Postgres would fix the data loss but expires after 30 days. |
| **Koyeb Free** | ❌ | 512 MB / 0.1 vCPU, one free service. Same memory ceiling as Render with no margin. Card may be required. |
| **Fly.io** | ❌ | Free tier retired for new accounts; now pay-as-you-go (~$2.19/mo for 256 MB, more for 512 MB+). |
| **Railway** | ❌ free | $5 trial credit, card required. Cheap but not free. |
| **Vercel / Netlify** | ❌ | Serverless with cold starts and no persistent filesystem; a 405 MiB in-process model does not fit. |

### Recommendation for a thesis demo

**Hugging Face Spaces (Docker, free CPU)** — 2 vCPU / 16 GB, so the ~500 MiB
model is a non-issue, the build runs in their infrastructure, and the URL is
stable enough to cite in a document. It sleeps on idle, so the first visit
after a quiet period takes a cold start.

**Oracle Cloud Always Free** if it must never sleep: 2 OCPU / 12 GB, always on.
More setup (arm64 image, your own TLS/reverse proxy) and Oracle now requires a
card for identity verification.

Both avoid the trap that disqualifies the 512 MB PaaS tiers here: ephemeral
storage destroying the SQLite file.

Avoid Render's free tier for this project specifically: the spin-down discards
the SQLite file, so a reviewer opening the link gets an empty database and the
demo resets between visits. That is a worse outcome than a sleeping Space.

## If you must fit a smaller host

In order of effect:

1. Keep `MALLOC_ARENA_MAX=2` (already set). Without it, idle is 471 MiB.
2. Do not add workers. `--workers 1` is deliberate.
3. Move the parquet read earlier and drop the frame after building lists —
   the pyarrow buffers are what push RSS up, not the model.
4. As a last resort, convert `full_tfidf` to `float32` (it is float64 today)
   to halve its 39 MB, and drop `abstract`/`title` from the DataFrame read if
   the detail page is served from a second, smaller lookup.

## Health check

`GET /health` returns the serving proof:

```json
{"status":"ok","alpha":0.4,"catalog_size":93698,"als_items":3394}
```

Point the platform's health check here. It responds only after the model has
finished loading, so a passing check means the service can actually recommend.

## Rebuilding after a code change

The image is built from the working tree, so a rebuild after a fix is
`docker build -t goodnews:latest .`. Two things are worth checking rather than
assuming:

1. **The build is fast when it should not be.** A rebuild that finishes in a
   few seconds is usually just re-tagging a cached layer. Confirm the change
   is inside:

   ```bash
   docker run --rm --entrypoint python goodnews \
     -c "import sys; sys.path.insert(0,'/app/src'); print('ok')"
   docker exec <container> grep -c '<the symbol you added>' /app/src/<path>
   ```

2. **Cache-bypass the browser.** Static assets are served with normal HTTP
   caching, so a verification screenshot can show the previous CSS. Reload
   with the cache disabled before concluding a layout fix did not work.
