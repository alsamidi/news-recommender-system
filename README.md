# TA News Recommendation System

Sistem Rekomendasi Berita Bahasa Indonesia berbasis **Content-Based (TF-IDF) + Collaborative Filtering (ALS) + Hybrid terbobot** untuk Tugas Akhir.
Snapshot reprodusibel Day 5: dataset terkunci, preprocessing Indonesia, kedua model terlatih, evaluasi full-catalog + stratifikasi warm/cold selesai.

Proyek ini terdiri dari dua lapisan. Lapisan riset memuat dataset,
preprocessing, training, dan evaluasi, dan hasilnya sudah dibekukan. Lapisan
aplikasi web memuat akun, feed, histori bacaan, dan rekomendasi yang menyajikan
artefak beku tersebut.

## Tech Stack

**Lapisan riset**

| Bagian | Teknologi |
|--------|-----------|
| Bahasa | Python 3.12 |
| Data | pandas, polars, numpy, scipy, pyarrow (parquet) |
| Content-based | scikit-learn `TfidfVectorizer` (ngram 1–2, 50.000 fitur, cosine) |
| Collaborative | `implicit` — ALS (factors 128, alpha 40, 20 iterasi) |
| Preprocessing ID | Sastrawi (stemmer), stopwords kustom, normalisasi alay |
| Baseline pembanding | IndoBERT via `transformers` / `sentence-transformers` (evaluasi saja, tidak dipakai serving) |
| Konfigurasi | YAML (`configs/`) |
| Evaluasi | Implementasi metrik sendiri (`NDCG@k`, `MAP@k`, `hit@k`), seed 42 |

**Lapisan web**

| Bagian | Teknologi | Catatan |
|--------|-----------|---------|
| HTTP | FastAPI + Uvicorn | Satu proses, satu worker |
| Rendering | Jinja2 (server-side) | Tanpa framework JS, tanpa bundler |
| Styling | CSS dengan design token | Tanpa CDN, tanpa webfont unduhan; sistem font lokal |
| Database | SQLite (modul `sqlite3` bawaan) | Akun, sesi, histori interaksi |
| Akses model | `httpx.ASGITransport` | Memanggil API beku **in-process**, tanpa network hop |
| Auth | `hashlib.scrypt` + HMAC CSRF | Sesi disimpan sebagai hash token |
| Logo | SVG inline | Di-trace dari vektor, ikut `currentColor` |

Alur permintaan:

```
browser → web app (FastAPI, Jinja2)
            ├─ SQLite          akun, sesi, histori baca
            └─ API beku        in-process (ASGI), α = 0,4
                  └─ HybridRecommender → artefak .pkl / .npy / .parquet
```

Aplikasi web tidak menghitung skor sendiri dan tidak mengurutkan ulang hasil
rekomendasi. Keputusan ranking sepenuhnya milik lapisan riset yang sudah
dibekukan.

## Dataset

Pasangan resmi terkunci, lihat `data/DATASET_LOCK.md` (jangan dicampur dengan split/size lain):

| Split | Folder (sejajar repo root) | Isi |
|-------|----------------------------|-----|
| train | `MINDsmall_train/` | news.tsv EN + behaviors.tsv (156.965 impressions, 50.000 users) |
| train | `xMINDsmall_train/` | news.tsv terjemahan Indonesia (51.282 news), join via `nid` |
| dev (eval) | `MINDsmall_dev/` | news.tsv + behaviors.tsv (73.152 impressions, 50.000 users) |
| dev (eval) | `xMINDsmall_dev/` | news.tsv terjemahan Indonesia (42.416 news) |

Aturan split: **file-based temporal**, train = file `*_train`, eval = file `*_dev`, cutoff `2019-11-15`. Random split tidak dipakai karena menyebabkan leakage.
Overlap NID MIND↔xMIND 100%; coverage teks Indonesia untuk behavior 100%.
Sebagai konteks: 62,7% item relevan dev tidak pernah muncul di interaksi train, dan 88,1% user dev tidak punya train history (`models/error_coverage.json`).

## Preprocessing

Pipeline Indonesia (`configs/preprocessing.yaml`, `src/preprocessing/build_locked.py`):

- Stemmer Sastrawi (per kata-unik), stopwords `configs/stopwords_id.txt`, normalisasi alay opsional.
- Token: min 2 / max 50 karakter; angka dan tanda baca dibuang.
- Input teks: `title + abstract` xMIND (ID); `category/entities` di-join dari MIND via `nid`.
- Output: `data/processed/news_processed.parquet`, `data/processed/interactions_{train,dev}.parquet`.
- Leakage guard: vectorizer TF-IDF hanya di-fit di train; dev/full catalog hanya `transform()`.

## Models

| Komponen | Konfigurasi | Artifact |
|----------|-------------|----------|
| Content-Based TF-IDF | ngram 1–2, max 50.000 fitur, min_df 2, max_df 0.95, sublinear_tf, cosine (`configs/tfidf_baseline.yaml`) | `models/tfidf_baseline.pkl`, `tfidf_embeddings.npz`, `tfidf_vectorizer.pkl` |
| CF ALS implicit | factors 128, reg 0.01, alpha 40, 20 iterasi, min 5 interaksi/user, min 3/item (`configs/als.yaml`) | `models/als_model.pkl`, `als_user/item_factors.npy` (ruang ALS: 3.394 item) |
| Hybrid terbobot | skor = α·content + (1−α)·CF, min-max per user (`configs/hybrid.yaml`) | `models/weighted_hybrid.pkl` |

Catatan alpha: `configs/hybrid.yaml` final `content_weight: 0.4`, pemenang
protokol full-catalog Day 4/5 (Katalog 93.698 item, NDCG@10 0,00208; lihat
Evaluation). Nilai 0,8 berasal dari sweep lama pada ruang ALS saja dan tersisa
hanya sebagai catatan historis di `models/best_alpha.json` /
`weighted_hybrid.pkl`. Nilai itu tidak dipakai serving maupun angka laporan.

## Evaluation

Semua evaluasi memakai formula metrik frozen yang sama (`_metrics_at_ks`, min-max per user, top-k terurut) dengan seed 42.
Skor dinormalisasi min-max per user sebelum digabung. Kandidat train/session selalu di-mask (`-inf`).

### Restricted Catalog (Table A)

- Kandidat = ruang item ALS saja (3.394 item). Warm users, profil = mean TF-IDF item train.
- Item di luar ruang CF tidak pernah bisa direkomendasikan. Berguna untuk perbandingan, tetapi menyembunyikan cold-start item.
- Hasil (`models/full_catalog_tables.md`): condong ke content; α=1,0 (pure content) NDCG@10 tertinggi (0,00928; n=1.139).

### Full Catalog (Table B)

- Kandidat = seluruh katalog (93.698 item). TF-IDF `transform`-only (frozen). Pure CF (α=0) mengisi slot unknown dengan `-inf`; α>0 memberi slot unknown nilai 0 sehingga content tetap bisa me-ranking item non-ALS.
- Protokol: warm users, mask train history, sampel 2.000/2.858 eligible, K=5/10/20, sweep α 0,0–1,0.
- Hasil: α=0,4 memberi NDCG@10 tertinggi pada protokol full-catalog yang diuji (0,00208; MAP@10 0,00120; hit@10 0,0090; n=2.000). Pure content (α=1,0) turun ke 0,00007, yang menunjukkan item cold-start butuh sinyal CF.

### Warm/Cold Stratified Evaluation (Table C / Table D)

Bagian ini menjawab pertanyaan Bab IV: bagaimana perilaku sistem saat informasi user tersedia dan saat tidak tersedia.

**Warm (Table C): train history tersedia, sehingga ALS personalisasi dapat digunakan.**

- Protokol identik Table B: full catalog, mask train, profil mean TF-IDF train. Sampel 2.000/2.858 eligible.
- Hasil: α=0,4 memberi NDCG@10 tertinggi (0,00208), tetapi selisihnya terhadap pure CF (α=0; 0,00200) kecil. Pada user bersejarah, komponen collaborative filtering yang menentukan; content hanya memberi koreksi kecil di atasnya.

**Cold (Table D): train history tidak tersedia, sehingga user-factor ALS tidak tersedia. Session history dev dipakai dan pseudo-user dibuat dari item ALS yang muncul pada session.**

- Protokol: user tanpa interaksi train. Session-based leave-last-out dalam dev (klik diurut waktu; history = semua kecuali terakhir; relevant = klik terakhir). Profil TF-IDF dari history session; CF diproksi pseudo-user factor = mean ALS item-factors dari item session yang ada di ALS; fallback non-personalized = popularity train; full catalog, mask session. Sampel 2.000/22.703 session usable.
- Hasil: α=0,4 memberi NDCG@10 tertinggi (0,00921; MAP@10 0,00706; hit@10 0,0163) pada subset yang punya setidaknya satu item session di ruang ALS (n=1.164). Pure content pada n=2.000 penuh hanya 0,00139; popularity 0,00000.
- Keterbatasan: 836/2.000 session cold tidak punya item ALS, sehingga CF tidak dapat dibentuk untuk subset itu. Baris `hybrid_pseudo_cf` (α=0/0,4/0,8/1,0) hanya dievaluasi pada n=1.164 yang punya pseudo-CF; baris `content` dan `popularity` dievaluasi pada n=2.000 penuh. Karena itu baris-baris Table D tidak dapat dibandingkan langsung tanpa memperhatikan kolom n.

## Menjalankan Proyek

Ada empat cara menjalankan proyek ini. Pilih sesuai tujuannya. Semua perintah
di bawah sudah dijalankan di repo ini (Python 3.12, Linux x86_64).

### A. Menjalankan website (cara tercepat)

Butuh artefak model di `data/processed/` dan `models/`. Artefak ini
**gitignored** (± 386 MB), jadi clone baru belum bisa langsung jalan. Ambil
dari **GitHub Releases**:

```bash
# unduh salah satu arsip dari halaman Releases, lalu dari root repo:
tar -xf ta-news-rec-artifacts-serving-2026-10-21.tar.zst -C .
bash scripts/verify_artifacts.sh --serving
```

| Arsip | Ukuran | Isi |
|-------|--------|-----|
| `...-serving-*.tar.zst` | 62 MB | 7 file yang dibaca `web.app` — cukup untuk menjalankan situs |
| `...-full-*.tar.zst` | 333 MB | 11 file — perlu kalau ingin mengulang evaluasi IndoBERT |

Verifikasi jangan dilewati. Parquet yang terpotong atau pickle yang setengah
tertulis tidak menimbulkan error, tetapi mengubah hasil rekomendasi tanpa
ketahuan. Rincian per file: [`docs/ARTIFACTS.md`](docs/ARTIFACTS.md).

Kalau tidak ingin mengunduh, regenerasi lewat langkah **D** di bawah.

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements-serve.txt   # 13 paket, cukup untuk web

uvicorn web.app:app --app-dir src --port 8000
```

Buka <http://localhost:8000>. Halaman pertama adalah landing; daftar akun baru
atau masuk. Model dimuat saat startup (± 25 detik, ± 450 MB RAM), jadi
permintaan pertama menunggu sebentar.

Di browser, alurnya:

1. **Daftar** — isi nama, email, password (minimal 8 karakter).
2. **Beranda** — 10 kartu rekomendasi. Akun baru belum punya riwayat, jadi
   sistem memakai jalur *populer*; label di atas kartu menyebut sumbernya.
3. **Baca berita** — klik kartu mana pun. Berita yang terbuka tercatat sebagai
   interaksi.
4. **Histori** — semua yang pernah dibaca, terbaru di atas, waktu dalam WIB.
5. **Kembali ke Beranda** — begitu ada riwayat, label berubah menjadi
   *"Rekomendasi dari riwayat bacaanmu"* dan isinya mengikuti bacaan tadi.

Untuk Docker, lihat [Menjalankan lewat Docker](#b-menjalankan-lewat-docker).

### B. Menjalankan lewat Docker

Image sudah berisi dependensi dan artefak yang diperlukan. Selain Docker, tidak
ada yang perlu dipasang.

```bash
docker build -t goodnews:latest .
docker run -d --name goodnews-app -p 8000:8000 -v goodnews-data:/data goodnews:latest
```

Tag `:latest` ditulis eksplisit supaya perintah `docker run` di atas memakai
image yang baru dibangun. Tanpa tag, Docker tetap memberi `latest`, tetapi
kalau image-nya tidak ada ia akan mencoba menarik `goodnews` dari registry dan
gagal.

Buka <http://localhost:8000>.

- **`-v goodnews-data:/data`** menyimpan akun dan histori di named volume
  Docker, jadi bertahan saat container di-restart. Tanpa volume, database
  SQLite hilang setiap restart.
- **Bind mount `-v "$PWD/data:/data"` tidak dipakai** karena container berjalan
  sebagai user non-root (uid 10001), sedangkan `data/` milik user Anda. SQLite
  akan gagal dengan `attempt to write a readonly database`. Kalau memang perlu
  bind mount:

  ```bash
  mkdir -p data-docker && sudo chown 10001:10001 data-docker
  docker run -p 8000:8000 -v "$PWD/data-docker:/data" goodnews
  ```

- Model dimuat saat startup. Tunggu log menampilkan
  `Application startup complete` sebelum membuka browser (± 25 detik).
- Cek kesehatan: `curl localhost:8000/health` →
  `{"status":"ok","alpha":0.4,"catalog_size":93698,"als_items":3394}`.

Isi volume bisa diambil untuk backup:

```bash
docker cp goodnews-app:/data/web.db ./web.db.backup
```

Angka resource terukur (Docker, Linux x86_64):

| | |
|---|---|
| Ukuran image | 807 MB |
| Waktu start | ± 25 detik |
| RAM idle | 445–476 MiB |
| RAM, 24 sesi bersamaan | 481–498 MiB |

Dengan angka itu, 512 MB terlalu mepet dan 1 GB adalah kebutuhan sebenarnya.
Perbandingan platform gratis ada di [`docs/web/DEPLOYMENT.md`](docs/web/DEPLOYMENT.md).

### C. Menjalankan dengan persona / akun demo

Akun biasa memakai jalur *cold* (riwayat sesi) sampai user membaca beberapa
berita. Untuk demonstrasi, **persona** memberi hasil yang lebih meyakinkan:
akun lokal yang dipetakan ke satu `user_id` di dataset MIND yang punya faktor
ALS. Akun ini langsung memakai jalur *warm*, yaitu rekomendasi dari profil
dataset dan bukan dari riwayat kosong, sehingga label di beranda berbunyi
*"Rekomendasi berdasarkan profil dataset demo"*.

`user_id` berikut sudah diverifikasi ada di `user_map` ALS:
`U10022`, `U10045`, `U10062`, `U10103`.

**Persiapan (sekali).** Isi variabel lingkungan. Jangan commit nilainya:

```bash
export WEB_DEMO_PERSONA_USER_ID=U10022
export WEB_DEMO_PERSONA_EMAIL=demo@example.com
export WEB_DEMO_PERSONA_PASSWORD='pilih-password-yang-kuat'
```

**Membuat akunnya.** Perintah ini idempoten: dijalankan ulang hanya
memperbarui.

```bash
python -m src.web.seed_persona
# persona ready: user_id=1 email=demo@example.com dataset_user=U10022
```

Sebelum menulis apa pun, perintah ini memeriksa bahwa `user_id` tersebut punya
faktor ALS. Kalau tidak, ia berhenti.

**Masuk** ke <http://localhost:8000/login> dengan email dan password di atas.
Beranda menampilkan label persona dan 10 kartu dari profil dataset.

**Dengan Docker.** Variabel diberikan saat container dijalankan, lalu seed
dijalankan di dalam container:

```bash
docker run -d --name goodnews-app -p 8000:8000 -v goodnews-data:/data \
  -e WEB_DEMO_PERSONA_USER_ID=U10022 \
  -e WEB_DEMO_PERSONA_EMAIL=demo@example.com \
  -e WEB_DEMO_PERSONA_PASSWORD='pilih-password-yang-kuat' \
  goodnews

docker exec goodnews-app python -m src.web.seed_persona
```

Kalau seed dijalankan tanpa variabel, ia mencetak
`Persona seed skipped; missing: ...` dan keluar dengan kode 2.

### D. Reproduksi riset (lengkap)

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
# 5. Tes (termasuk paritas inference vs evaluator)
pytest
# 6. Serve API beku saja (tanpa web layer)
uvicorn src.api.main:app --port 8000
#    POST /recommend {"user_id": ...} (warm) atau {"history": [nid,...]} (cold)
#    GET /article/{nid}, GET /similar/{nid}, GET /health
# 7. Bukti serve satu command (pytest + API live: warm/cold/fallback/similar + UI)
bash scripts/smoke_demo.sh
```

Kontrak API beku: [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) +
[`docs/openapi.json`](docs/openapi.json).

### Memilih cara jalan

| Tujuan | Cara |
|--------|------|
| Mencoba aplikasi di mesin sendiri | **A** (uvicorn) |
| Membagikan ke orang lain / deploy | **B** (Docker) |
| Demo sidang dengan rekomendasi personal | **C** (persona) |
| Memeriksa angka & tabel skripsi | **D** (reproduksi riset) |

## Konfigurasi

Semua pengaturan dibaca dari environment. Default-nya ada di
`src/web/config.py`. Salin [`.env.example`](.env.example) menjadi `.env` untuk
pemakaian lokal.

| Variabel | Default | Fungsi |
|----------|---------|--------|
| `WEB_DB_PATH` | `data/web.db` | Lokasi SQLite (di image: `/data/web.db`) |
| `WEB_SESSION_TTL_DAYS` | `7` | Umur sesi login |
| `WEB_HISTORY_LIMIT` | `50` | Jumlah riwayat yang dikirim ke API |
| `WEB_FEED_LIMIT` | `10` | Kartu yang dirender di beranda |
| `WEB_REC_TOP_K` | `30` | `top_k` yang diminta ke API |
| `WEB_DEMO_PERSONA_USER_ID` / `_EMAIL` / `_PASSWORD` | — | Persona demo (lihat C) |
| `WEB_SECURE_COOKIES` | `0` | Set `1` di belakang HTTPS agar cookie `Secure` |
| `WEB_CSRF_SECRET` | acak per proses | Set nilai tetap untuk multi-worker/restart |

Detail keamanan dan batasannya: [`docs/web/SECURITY_NOTES.md`](docs/web/SECURITY_NOTES.md).

## Dokumentasi

| Dokumen | Isi |
|---------|-----|
| [`docs/web/PRD.md`](docs/web/PRD.md) | Kebutuhan produk, fitur, batasan |
| [`docs/web/ARCHITECTURE.md`](docs/web/ARCHITECTURE.md) | Struktur web layer, keputusan teknis |
| [`docs/web/DATA_MODEL.md`](docs/web/DATA_MODEL.md) | Skema SQLite |
| [`docs/web/DESIGN.md`](docs/web/DESIGN.md) | Token desain, komponen, aturan visual |
| [`docs/web/ACCEPTANCE_CRITERIA.md`](docs/web/ACCEPTANCE_CRITERIA.md) | Kriteria penerimaan + ID tes |
| [`docs/web/RECOMMENDATION_INTEGRATION.md`](docs/web/RECOMMENDATION_INTEGRATION.md) | Cara web memakai API beku |
| [`docs/web/SECURITY_NOTES.md`](docs/web/SECURITY_NOTES.md) | Kontrol keamanan, batasan, checklist deploy |
| [`docs/web/DEPLOYMENT.md`](docs/web/DEPLOYMENT.md) | Docker, resource terukur, opsi hosting gratis |
| [`docs/web/UX_FLOWS.md`](docs/web/UX_FLOWS.md) | Alur layar |
| [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) | Kontrak API beku v1.0.0 |
| [`docs/RESEARCH_FREEZE.md`](docs/RESEARCH_FREEZE.md) | Bukti pembekuan riset |
| [`data/DATASET_LOCK.md`](data/DATASET_LOCK.md) | Dataset terkunci + checksum |
| [`docs/ARTIFACTS.md`](docs/ARTIFACTS.md) | Artefak model: unduhan, checksum, cara regenerasi |


## Current Results

NDCG@10 (seed 42):

| Tabel | Setting | Terbaik | Angka |
|-------|---------|---------|-------|
| B | Full catalog, warm (n=2.000) | hybrid α=0,4 | 0,00208 (CF 0,00200; content 0,00007) |
| C | Warm stratified = protokol B (n=2.000) | hybrid α=0,4 | 0,00208 (CF 0,00200; content 0,00007) |
| D | Cold session LLO, pseudo-CF subset (n=1.164) | hybrid α=0,4 | 0,00921 (CF-proxy α=0: 0,00645; content n=2.000: 0,00139; popularity: 0,00000) |

Keterbatasan yang dibawa ke Bab IV: (1) skor absolutnya kecil karena task ini meranking 93.698 item dengan relevan tipis (median 1 per user); (2) 836 dari 2.000 session cold tidak punya item ALS sehingga tidak mendapat skor CF; (3) sweep α Day 5 pada Tabel C/D hanya di titik 0,0/0,4/0,8/1,0, sedangkan sweep rapat 0,0–1,0 hanya ada di Tabel A/B.

## Status

- [x] Dataset audit and lock
- [x] Indonesian preprocessing
- [x] TF-IDF content model
- [x] ALS collaborative filtering
- [x] Hybrid evaluation
- [x] Full-catalog evaluation
- [x] Warm/cold stratified evaluation
- [x] Final system/application layer (API v1.0.0 frozen)
- [x] Web application: akun, feed, artikel, histori, rekomendasi warm/cold
- [x] Desain web + design token (`docs/web/DESIGN.md`)
- [x] Kontrol keamanan untuk pemakaian publik (per-IP throttle, `Secure`, CSRF secret)
- [x] Containerization + panduan deploy (`docs/web/DEPLOYMENT.md`)
- [ ] Final thesis documentation
