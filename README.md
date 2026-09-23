# TA News Recommendation System

Sistem Rekomendasi Berita Bahasa Indonesia berbasis **Content-Based (TF-IDF) + Collaborative Filtering (ALS) + Hybrid terbobot** untuk Tugas Akhir.
Snapshot reprodusibel Day 5: dataset terkunci, preprocessing Indonesia, kedua model terlatih, evaluasi full-catalog + stratifikasi warm/cold selesai.

## Dataset

Pasangan resmi terkunci, lihat `data/DATASET_LOCK.md` (jangan dicampur dengan split/size lain):

| Split | Folder (sejajar repo root) | Isi |
|-------|----------------------------|-----|
| train | `MINDsmall_train/` | news.tsv EN + behaviors.tsv (156.965 impressions, 50.000 users) |
| train | `xMINDsmall_train/` | news.tsv terjemahan Indonesia (51.282 news), join via `nid` |
| dev (eval) | `MINDsmall_dev/` | news.tsv + behaviors.tsv (73.152 impressions, 50.000 users) |
| dev (eval) | `xMINDsmall_dev/` | news.tsv terjemahan Indonesia (42.416 news) |

Aturan split: **file-based temporal**, train = file `*_train`, eval = file `*_dev`, cutoff `2019-11-15`. Dilarang random split (leakage).
Overlap NID MIND↔xMIND 100%; coverage teks Indonesia untuk behavior 100%.
Konteks tambahan: 62,7% item relevan dev tidak pernah muncul di interaksi train; 88,1% user dev tidak punya train history (`models/error_coverage.json`).

## Preprocessing

Pipeline Indonesia (`configs/preprocessing.yaml`, `src/preprocessing/build_locked.py`):

- Stemmer Sastrawi (per kata-unik), stopwords `configs/stopwords_id.txt`, normalisasi alay opsional.
- Token: min 2 / max 50 karakter, buang angka dan tanda baca.
- Input teks: `title + abstract` xMIND (ID); `category/entities` di-join dari MIND via `nid`.
- Output: `data/processed/news_processed.parquet`, `data/processed/interactions_{train,dev}.parquet`.
- Leakage guard: vectorizer TF-IDF hanya di-fit di train; dev/full catalog hanya `transform()`.

## Models

| Komponen | Konfigurasi | Artifact |
|----------|-------------|----------|
| Content-Based TF-IDF | ngram 1–2, max 50.000 fitur, min_df 2, max_df 0.95, sublinear_tf, cosine (`configs/tfidf_baseline.yaml`) | `models/tfidf_baseline.pkl`, `tfidf_embeddings.npz`, `tfidf_vectorizer.pkl` |
| CF ALS implicit | factors 128, reg 0.01, alpha 40, 20 iterasi, min 5 interaksi/user, min 3/item (`configs/als.yaml`) | `models/als_model.pkl`, `als_user/item_factors.npy` (ruang ALS: 3.394 item) |
| Hybrid terbobot | skor = α·content + (1−α)·CF, min-max per user (`configs/hybrid.yaml`) | `models/weighted_hybrid.pkl` |

Catatan alpha: `configs/hybrid.yaml` mencatat `content_weight: 0.8` dari sweep lama (ruang ALS).
Pada protokol full-catalog Day 4/5 (Katalog 93.698 item) nilai tertinggi yang terukur adalah **α=0,4** (lihat Evaluation).

## Evaluation

Semua evaluasi memakai formula metrik frozen yang sama (`_metrics_at_ks`, min-max per user, top-k terurut), seed 42.
Skor dinormalisasi min-max per user sebelum digabung; kandidat train/session selalu di-mask (`-inf`).

### Restricted Catalog (Table A)

- Kandidat = ruang item ALS saja (3.394 item). Warm users, profil = mean TF-IDF item train.
- Efek: item di luar ruang CF tidak pernah bisa direkomendasikan — relevan untuk perbandingan, tetapi menyembunyikan cold-start item.
- Hasil (`models/full_catalog_tables.md`): condong ke content; α=1,0 (pure content) NDCG@10 tertinggi (0,00928; n=1.139).

### Full Catalog (Table B)

- Kandidat = seluruh katalog (93.698 item). TF-IDF `transform`-only (frozen). Pure CF (α=0) mengisi slot unknown dengan `-inf`; α>0 memberi slot unknown nilai 0 sehingga content tetap bisa me-ranking item non-ALS.
- Protokol: warm users, mask train history, sampel 2.000/2.858 eligible, K=5/10/20, sweep α 0,0–1,0.
- Hasil: **α=0,4 menghasilkan NDCG@10 tertinggi pada protokol full-catalog yang diuji** (0,00208; MAP@10 0,00120; hit@10 0,0090; n=2.000). Pure content (α=1,0) jatuh ke 0,00007 — bukti item cold-start butuh sinyal CF.

### Warm/Cold Stratified Evaluation (Table C / Table D)

Pertanyaan Bab IV: bagaimana perilaku sistem saat informasi user tersedia vs tidak tersedia.

**Warm (Table C): train history tersedia → ALS personalisasi dapat digunakan.**

- Protokol identik Table B: full catalog, mask train, profil mean TF-IDF train. Sampel 2.000/2.858 eligible.
- Hasil: **α=0,4 menghasilkan NDCG@10 tertinggi (0,00208)**, tetapi **selisih terhadap pure CF (α=0; 0,00200) relatif kecil**. Artinya: pada user bersejarah, komponen collaborative filtering memberikan kontribusi penting; content hanya memberi koreksi kecil di atasnya.

**Cold (Table D): train history tidak tersedia → user-factor ALS tidak tersedia → session history dev digunakan → pseudo-user dibuat dari item ALS yang muncul pada session.**

- Protokol: user tanpa interaksi train. Session-based leave-last-out dalam dev (klik diurut waktu; history = semua kecuali terakhir; relevant = klik terakhir). Profil TF-IDF dari history session; CF diproksi pseudo-user factor = mean ALS item-factors dari item session yang ada di ALS; fallback non-personalized = popularity train; full catalog, mask session. Sampel 2.000/22.703 session usable.
- Hasil: **α=0,4 menghasilkan NDCG@10 tertinggi (0,00921; MAP@10 0,00706; hit@10 0,0163) pada subset yang memiliki setidaknya satu item session di ruang ALS (n=1.164)**. Pure content pada n=2.000 penuh hanya 0,00139; popularity 0,00000.
- **Keterbatasan eksplisit: 836/2.000 session cold tidak memiliki item ALS, sehingga CF tidak dapat dibentuk untuk subset itu.** Baris `hybrid_pseudo_cf` (α=0/0,4/0,8/1,0) hanya dievaluasi pada n=1.164 yang memiliki pseudo-CF; baris `content` dan `popularity` dievaluasi pada n=2.000 penuh. Perbandingan antar-baris Table D karena itu **tidak dapat dibandingkan secara langsung** tanpa memperhatikan kolom n.

## Reproducibility

```bash
source venv/bin/activate

# 0. Dataset sejajar repo root (MINDsmall_train/dev, xMINDsmall_train/dev),
#    verifikasi sha256 terhadap data/DATASET_LOCK.md
# 1. Preprocessing
python -m src.preprocessing.build_locked
# 2. Train (urutan wajib)
python -m src.models.content_based.train --config configs/tfidf_baseline.yaml
python -m src.models.collaborative.train --config configs/als.yaml
python -m src.models.hybrid.train --config configs/hybrid.yaml
# 3. Evaluasi Day 4 (Table A + Table B)
python src/evaluation/full_catalog_eval.py
#    -> models/full_catalog_eval.json + models/full_catalog_tables.md
# 4. Evaluasi Day 5 (Table C + Table D)
python src/evaluation/stratified_eval.py
#    -> models/stratified_eval.json + models/stratified_tables.md
# 5. Tes
pytest
```

## Current Results

NDCG@10 (seed 42):

| Tabel | Setting | Terbaik | Angka |
|-------|---------|---------|-------|
| B | Full catalog, warm (n=2.000) | hybrid α=0,4 | 0,00208 (CF 0,00200; content 0,00007) |
| C | Warm stratified = protokol B (n=2.000) | hybrid α=0,4 | 0,00208 (CF 0,00200; content 0,00007) |
| D | Cold session LLO, pseudo-CF subset (n=1.164) | hybrid α=0,4 | 0,00921 (CF-proxy α=0: 0,00645; content n=2.000: 0,00139; popularity: 0,00000) |

Keterbatasan yang dibawa ke Bab IV: (1) skor absolut kecil — task ranking 93.698 item dengan relevan tipis (median 1/user); (2) 836/2.000 session cold tanpa item ALS tidak mendapat skor CF; (3) sweep α Day 5 pada Tabel C/D hanya di titik 0,0/0,4/0,8/1,0 (sweep rapat 0,0–1,0 hanya ada di Tabel A/B).

## Status

- [x] Dataset audit and lock
- [x] Indonesian preprocessing
- [x] TF-IDF content model
- [x] ALS collaborative filtering
- [x] Hybrid evaluation
- [x] Full-catalog evaluation
- [x] Warm/cold stratified evaluation
- [ ] Final system/application layer
- [ ] Final thesis documentation
