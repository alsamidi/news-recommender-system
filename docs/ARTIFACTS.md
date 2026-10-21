# Model artifacts

The trained artifacts are **not in git**. They total 386 MB, and
`models/indobert_embeddings.npy` alone is 287.8 MB — above GitHub's 100 MB
per-file hard limit, which rejects the whole push, not just that file.

They are published as a **GitHub Release** instead. A clone gives you the code;
the release gives you the weights. Together they reproduce the frozen results.

## Download

Go to the repository's **Releases** page and take one of two archives:

| Archive | Size | Contains | Use when |
|---------|------|----------|----------|
| `ta-news-rec-artifacts-serving-*.tar.zst` | 62 MB | The 7 files `web.app` loads | Running or demoing the site |
| `ta-news-rec-artifacts-full-*.tar.zst` | 333 MB | All 11 files | Re-running the thesis evaluation, including the IndoBERT comparison |

```bash
# from the repository root of a fresh clone
tar -xf ta-news-rec-artifacts-serving-2026-10-21.tar.zst -C .
bash scripts/verify_artifacts.sh --serving
```

The archive stores paths relative to the repository root, so extracting in place
puts every file where the code expects it. Nothing else to configure.

If `zstd` is unavailable:

```bash
sudo apt install zstd     # or: brew install zstd
# alternatively use the .tar.gz archive when present
```

## Verify before running

```bash
bash scripts/verify_artifacts.sh            # all 11
bash scripts/verify_artifacts.sh --serving  # only what the web app needs
```

It compares every file against `docs/ARTIFACT_CHECKSUMS.txt` (sha256 + exact
byte count) and exits non-zero on a corrupt or missing file.

**Verify even if the download "looked fine".** A truncated parquet or a
half-written pickle does not raise an error — it silently changes the
recommendations. The checksum is the only thing that catches it, and a demo that
serves wrong results is worse than one that refuses to start.

## What each file is

### Serving (78.8 MB) — loaded by `web.app`

| File | Size | What it is |
|------|------|-----------|
| `data/processed/news_processed.parquet` | 30.1 MB | The 93,698-row catalog: `nid`, title, abstract, processed text, category, subcategory, split |
| `data/processed/interactions_train.parquet` | 2.3 MB | Train interactions (temporal split, cutoff 2019-11-15) |
| `data/processed/interactions_dev.parquet` | 1.1 MB | Dev interactions, used for evaluation and cold-session sampling |
| `models/tfidf_baseline.pkl` | 23.7 MB | Frozen TF-IDF vectorizer + train matrix. The vectorizer is **transform-only** at serve time; re-fitting would be leakage |
| `models/als_model.pkl` | 11.9 MB | ALS model: user map, item map, train matrix (3,394 items) |
| `models/als_user_factors.npy` | 8.0 MB | User factors, float32 |
| `models/als_item_factors.npy` | 1.7 MB | Item factors, float32 |

### Research (306.7 MB) — evaluation only, never loaded when serving

| File | Size | What it is |
|------|------|-----------|
| `models/indobert_embeddings.npy` | 287.8 MB | IndoBERT embeddings, L2-normalized, rows parallel to the parquet. The comparison baseline in `src/evaluation/indobert_eval.py` |
| `models/tfidf_embeddings.npz` | 16.9 MB | Cached TF-IDF embeddings used by `src/evaluation/alpha_sweep.py` |
| `models/tfidf_vectorizer.pkl` | 2.0 MB | Standalone vectorizer copy (the same object is inside `tfidf_baseline.pkl`) |
| `models/weighted_hybrid.pkl` | 418 B | Historical α=0.8 record from the ALS-only sweep. **Not used for serving** — see the alpha note in the README |

The serving/research split is not cosmetic: the Docker image ships only the
serving set, which is why it is 807 MB rather than carrying another 306 MB it
never opens.

## Regenerating instead of downloading

Everything here is reproducible from the locked dataset
(`data/DATASET_LOCK.md`). From the repository root, with the MIND/xMIND
directories in place:

```bash
python -m src.preprocessing.build_locked
python -m src.models.content_based.train --config configs/tfidf_baseline.yaml
python -m src.models.collaborative.train --config configs/als.yaml
python -m src.models.hybrid.train --config configs/hybrid.yaml
```

Regenerating may not reproduce the files **bit-for-bit** — `implicit`'s ALS uses
threaded computation, and library versions drift. The published checksums are
the authority for the numbers in the thesis. If you regenerate and the checksums
differ, the evaluation figures are the ones to trust only if they still match
`models/full_catalog_eval.json`.

## Rebuilding the archives

```bash
bash scripts/pack_artifacts.sh            # full   -> dist/*.tar.zst
bash scripts/pack_artifacts.sh --serving  # subset -> dist/*.tar.zst
```

The packer verifies the tree against the manifest first and refuses to build
from artifacts that do not match, so a published archive always corresponds to
the checksums in the repository.
