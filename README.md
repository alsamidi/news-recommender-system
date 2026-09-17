# TA News Recommendation System

Sistem Rekomendasi Berita Bahasa Indonesia berbasis **Content-Based + Collaborative Filtering (Hybrid)** untuk Tugas Akhir.

## Stack
- **NLP Indonesia**: Sastrawi (stemmer, stopword), IndoBERT (opsional)
- **Content-Based**: TF-IDF + Cosine Similarity (baseline), IndoBERT embeddings (SOTA)
- **Collaborative Filtering**: ALS (implicit feedback) via `implicit`
- **Hybrid**: Weighted combination (α·content + (1-α)·CF)
- **API**: FastAPI
- **Tracking**: MLflow
- **Eval**: Precision@K, Recall@K, MAP@K, NDCG@K, Coverage, Diversity

## Struktur Project
```
ta-news-rec/
├── configs/              # YAML configs (preprocessing, models, eval)
├── data/
│   ├── raw/              # Dataset mentah (CSV/JSONL/Parquet)
│   └── processed/        # Hasil preprocessing, interactions
├── models/               # Trained artifacts (.pkl, .npy)
├── notebooks/            # EDA, eksperimen, analisis error
├── src/
│   ├── preprocessing/    # Indonesian text preprocessing pipeline
│   ├── models/
│   │   ├── content_based/   # TF-IDF baseline
│   │   ├── collaborative/   # ALS implicit CF
│   │   └── hybrid/          # Weighted hybrid
│   ├── evaluation/       # Metrics: P@K, R@K, MAP@K, NDCG@K
│   └── api/              # FastAPI server
└── requirements.txt
```

## Quick Start

### 1. Activate Environment
```bash
cd /home/losbanditos/_code/ta-news-rec
source venv/bin/activate
```

### 2. Download Dataset (MIND small + xMIND small, Bahasa Indonesia)
```bash
# MIND small (EN + behaviors): https://msnews.github.io
# xMIND (terjemahan 14 bahasa, termasuk Indonesia): repo xMIND / HuggingFace
# Letakkan folder SEJAJAR repo root (bukan di data/raw), sesuai configs/*.yaml:
#   MINDsmall_train/  (news.tsv, behaviors.tsv)
#   MINDsmall_dev/    (news.tsv, behaviors.tsv)
#   xMINDsmall_train/ (news.tsv terjemahan Indonesia)
#   xMINDsmall_dev/   (news.tsv terjemahan Indonesia)
# Verifikasi sha256 terhadap data/DATASET_LOCK.md sebelum lanjut.
```

### 3. Run Preprocessing
```bash
# Bangun news_processed.parquet + interactions_{train,dev}.parquet
python -m src.preprocessing.build_locked
# Output: data/processed/news_processed.parquet,
#         data/processed/interactions_{train,dev}.parquet
```

### 4. Train Models (urutan wajib)
```bash
# 1. Content-based baseline
python -m src.models.content_based.train --config configs/tfidf_baseline.yaml

# 2. Collaborative filtering (butuh interactions data)
python -m src.models.collaborative.train --config configs/als.yaml

# 3. Hybrid (butuh model 1 & 2 sudah jadi)
python -m src.models.hybrid.train --config configs/hybrid.yaml
```

### 5. Evaluate
```bash
python -m src.evaluation.run --model hybrid --config configs/hybrid.yaml
```

### 6. Run API
```bash
uvicorn src.api.main:app --reload --port 8000
```

### 7. Test API
```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/recommend \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_123", "top_k": 5, "model": "hybrid"}'
```

## Konfigurasi Penting

### Temporal Split (WAJIB)
Split **file-based** sesuai DATASET_LOCK.md (bukan random):
train = file `*_train`, eval = file `*_dev`, cutoff `2019-11-15`.

### Indonesian Preprocessing
```yaml
stemmer: "sastrawi"
stopwords_path: "configs/stopwords_id.txt"
normalize_alay: true
alay_dict_path: "configs/alay_dict.csv"  # opsional
```

## Eksperimen & Logging
- Gunakan **MLflow** untuk tracking: `mlflow ui` di port 5000
- Commit per eksperimen: `git commit -m "exp: tfidf-ngram12-ndcg0.342"`

## Dataset (locked, lihat data/DATASET_LOCK.md)
| Split | Folder | Isi |
|-------|--------|-----|
| train | MINDsmall_train/ | news.tsv (EN + kategori) + behaviors.tsv (156.965 impressions, 50.000 users) |
| train | xMINDsmall_train/ | news.tsv terjemahan Indonesia, join via nid (51.282 news) |
| dev (eval) | MINDsmall_dev/ | news.tsv + behaviors.tsv (73.152 impressions, 50.000 users) |
| dev (eval) | xMINDsmall_dev/ | news.tsv terjemahan Indonesia (42.416 news) |

Train = file *_train, eval = file *_dev (temporal/file-based, bukan random split).

## Catatan untuk TA
1. **Baseline dulu**: TF-IDF + ALS → hybrid → baru coba IndoBERT
2. **Eval temporal only** — random split = data leakage = nilai jelek
3. **Cold-start**: test item/user baru terpisah
4. **Dokumentasikan semua hyperparameter** di configs/
5. **Error analysis**: simpan case study di notebooks/

## Troubleshooting
- **LightFM build error**: Sudah diganti weighted hybrid (no C extension)
- **Sastrawi not found**: `pip install sastrawi`
- **CUDA OOM**: Kurangi `batch_size` atau `max_features` di TF-IDF
- **Memory error**: Gunakan `polars` streaming atau chunked processing

## Next Steps
1. [ ] Download MINDsmall + xMINDsmall ke sejajar repo root, verifikasi sha256 (data/DATASET_LOCK.md)
2. [ ] Jalankan preprocessing: `python -m src.preprocessing.build_locked` → cek `data/processed/`
3. [ ] Train baseline → evaluasi → iterasi (lihat Quick Start langkah 4-5)
