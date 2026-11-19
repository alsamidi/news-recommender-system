# TA News Recommendation System

Sistem rekomendasi berita berbahasa Indonesia: content-based TF-IDF, collaborative
filtering ALS, dan hybrid terbobot, dengan aplikasi web di atasnya.

Dataset yang dipakai **korpus portal Indonesia**: Detik, Tempo, dan Kompas,
Juli 2024 - Oktober 2025. Interaksinya simulasi `view` dari 600 akun dummy.
Dataset MIND/xMINDsmall dari riset v1 **tidak dipakai lagi** — tidak untuk
training, tidak untuk evaluasi, tidak untuk serving. Catatan riset v1 tetap
tersimpan sebagai arsip akademik di `docs/` dan `data/DATASET_LOCK.md`, tetapi
bukan bagian dari sistem yang berjalan.

| | Korpus indo (aktif) |
|---|---|
| Sumber | Detik, Tempo, Kompas (Juli 2024 - Oktober 2025) |
| Ukuran katalog | 67.381 artikel unik |
| Interaksi | simulasi, 600 akun dummy, 72.034 view |
| Alpha serving | 0,8 (`configs/indo_serving.yaml`) |
| Angka | `models/indo_eval.json` |
| Lock | `data/DATASET_LOCK_INDO.md` |

Tidak ada era korpus kedua yang dilayani. Seluruh rute web, API, evaluasi, dan
artefak model membaca korpus indo.

---

## Menjalankan

Butuh Python 3.12 dan artefak yang tidak ikut git: parquet katalog sekitar
257 MB, parquet interaksi di bawah 1 MB, dan model ALS 7,1 MB. Artefak
dibangun ulang lewat pipeline di bagian berikut.

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt        # riset + web
# atau, kalau hanya ingin menjalankan situs:
pip install -r requirements-serve.txt  # 13 paket

uvicorn web.app:app --app-dir src --port 8000
```

Buka <http://localhost:8000>. Startup sekitar 20 detik karena memuat TF-IDF
67.381 dokumen dan faktor ALS. Cek kesiapan:

```bash
curl localhost:8000/health
# {"status":"ok","alpha":0.8,"catalog_size":67381,"als_items":13881}
```

`--app-dir src` wajib. Tanpa itu `web.*`, `api.*`, dan `models.*` tidak
terselesaikan.

### Verifikasi

```bash
python -m pytest -q                 # 318 passed
bash scripts/audit_freeze.sh        # RESEARCH FREEZE AUDIT PASSED
bash scripts/verify_artifacts.sh    # checksum artefak arsip v1
bash scripts/smoke_web.sh           # ALL WEB SMOKE CHECKS PASSED
```

`smoke_web.sh` memakai database sekali pakai di `/tmp`, jadi `data/web.db`
tidak tersentuh.

---

## Pipeline korpus indo (fase 2)

Kode ada di `src/phase2/`, sengaja terpisah dari paket riset v1 yang beku
(`src/preprocessing`, `src/models`, `src/evaluation`).

| Tahap | Perintah | Luaran |
|---|---|---|
| Katalog | `python -m src.phase2.build_corpus_indo --workers 10` | `data/processed/indo/catalog.parquet` |
| Peta tautan | `python -m src.phase2.build_links` | `data/processed/indo/source_links.parquet` (3,2 MB) |
| Interaksi simulasi | `python -m src.phase2.run_generator` | `interactions.parquet` + laporan Gate B |
| Split temporal | `python -m src.phase2.split` | `*_train` / `*_dev` + cutoff |
| ALS | `python -m src.phase2.train_als` | `models/indo_als_model.pkl` |
| Evaluasi | `python -m src.phase2.run_eval` | `docs/evidence/phase2/sensitivity_matrix.json` |
| Ringkasan | `python -m src.phase2.write_eval` | `models/indo_eval.json` |

Waktu terukur: build katalog didominasi stemming, sekitar 3.396 detik dengan 10
worker (total 3.422 detik). Satu titik evaluasi sekitar 80 detik; sembilan titik
sekitar 12 menit. Generator dan pelatihan ALS masing-masing di bawah 10 detik.

Angka yang dipakai:

| Tahap | Hasil |
|---|---|
| Baris mentah → artikel unik | 80.472 → 67.381 (dedup per URL, duplikat 100% identik) |
| Kategori | 19 label, diturunkan dari seksi URL, cakupan 100% |
| Kosakata | 150.424 kata unik → 149.771 setelah stemming |
| Interaksi simulasi | 600 akun, 72.034 event view, seed 42 |
| Gate B | 82,7% item ≥ 1 view; 54,0% ≥ 3 view; 100% akun ≥ 10 bacaan |
| Katalog efektif | 17.584 item (terbit ≥ 2025-09-01) |
| Split | cutoff q80 `2025-09-18 06:05:20 UTC`; train 57.627 / dev 14.407 event |
| ALS | 600 × 13.881, nnz 57.292; cakupan faktor item 78,9% |

Detail lengkap beserta sha256 tiap artefak ada di
[`data/DATASET_LOCK_INDO.md`](data/DATASET_LOCK_INDO.md).

---

## Evaluasi

Protokol: peringkat penuh katalog dev per akun, tanpa sampled negatives;
relevan = item dev yang benar-benar dibaca akun itu; **enam metrik per
sistem** — NDCG@10, AP@10, MAP@10 (nama lain AP pada satu daftar
peringkat), Precision@10, Recall@10, F1@10. Sensitivitas diuji di 9 titik
(seed 1-3 x eksponen power-law 0,9/1,1/1,3), masing-masing 600 akun.

Rata-rata atas 9 titik (`models/indo_eval.json`):

| Sistem | NDCG@10 | MAP@10 | P@10 | R@10 | F1@10 |
|---|---|---|---|---|---|
| Popularity | 0,010595 | 0,003325 | 0,010093 | 0,004244 | 0,005826 |
| ALS | 0,005755 | 0,001849 | 0,005296 | 0,002279 | 0,003099 |
| Hybrid α=0,8 | 0,002975 | 0,000830 | 0,003130 | 0,001316 | 0,001814 |
| CBF | 0,001112 | 0,000322 | 0,001130 | 0,000495 | 0,000668 |

AP@10 = MAP@10; keduanya dilaporkan agar nama yang dipakai naskah
tersedia langsung. Precision memakai penyebut `len(top-k)`; F1 adalah
harmonik Precision dan Recall pada cutoff yang sama (0 bila tak ada hit).

Alpha 0,8 menang di grid resmi (α ∈ {0,2; 0,4; 0,6; 0,8}) menurut rata-rata
NDCG@10 dan dipakai untuk serving lewat `configs/indo_serving.yaml`. Lapisan
web tidak pernah mengirim atau menimpa alpha.

**Sapuan lanjutan (2026-10-29, lihat `data/DATASET_LOCK_INDO.md`):** grid 0,8
bukan konfigurasi tertinggi terukur — ALS murni (α=1,0) pada 64 faktor
mencapai 0,006216, dan 64 faktor mengalahkan 128 faktor (0,006216 vs
0,005755). Nilai yang dilayani **sengaja tidak diubah**: α=1,0 mematikan jalur
konten sehingga 21,1% item efektif tanpa faktor ALS kehilangan panggung;
menggantinya menuntut keputusan produk berbasis cakupan katalog, bukan
sekadar NDCG.

Caveat yang harus dibaca bersama angka ini:

1. Interaksi adalah simulasi view-only. Generator mendefinisikan proses
   popularitas, jadi popularity berperan sebagai batas atas, bukan bukti bahwa
   sistem lain kalah.
2. Skala absolut kecil karena katalog dev berisi puluhan ribu item dengan
   sekitar 24 item relevan per akun. Yang bermakna adalah perbandingan antar
   sistem pada protokol yang sama.
3. Sisa 21,1% item efektif tidak punya faktor ALS dan hanya dilayani lewat
   jalur content-based.

### Notebook perbandingan metrik

`notebooks/eval_metrik.ipynb` membandingkan empat sistem dengan lima metrik
(Precision@K, Recall@K, F1@K, MAP@K, NDCG@K) pada K ∈ {5, 10, 20}.

```bash
jupyter nbconvert --to notebook --execute notebooks/eval_metrik.ipynb --inplace
```

Sekitar 11 menit. Metriknya diimpor dari `src/phase2/evaluate.py` — satu
implementasi untuk notebook dan angka resmi, jadi keduanya tidak bisa
menyimpang. Notebook memvalidasi silang 189 nilai terhadap
`models/indo_eval.json` pada toleransi 1e-9. Hasilnya tersimpan di
`docs/evidence/phase2/metric_comparison.json` dan `metric_comparison.png`.

Varian sempit: `notebooks/eval_metrik_fokus.ipynb` (NDCG@10 + F1@10 saja).

### Workbook perhitungan manual

`docs/evidence/phase2/Perhitungan_Manual_Rekomendasi_Hybrid_CBF_ALS.xlsx`
menurunkan jalur yang dilayani sel demi sel: token → TF → IDF → TF-IDF →
kosinus → peringkat CBF → skor ALS → min-max → blend alpha → kartu yang
dirender → enam metrik. Dibangun ulang oleh
`scripts/build_manual_workbook.py`. 13 sheet, 10.589 sel formula, tanpa angka
hasil yang ditulis tangan.

Sheet `12_Cek_Naskah` menghitung ulang rata-rata 9 titik untuk enam metrik x
tujuh sistem (42 blok) dan membandingkannya dengan `metric_comparison.json`;
seluruh blok melaporkan "cocok". Bukti verifikasi: berkas di-recalc dengan
LibreOffice headless, 0 sel error dan 0 selisih pada 8.825 sel numerik.

Batas yang tertulis di sheet `Petunjuk`: TF-IDF di-fit pada 12 dokumen sampel
(produksi 67.381), min-max atas 12 kandidat (produksi 17.584 per akun), dan K
evaluasi diturunkan ke 5 karena hanya ada 9 kandidat.

---

## Aplikasi web

`src/web/`, FastAPI dengan Jinja2 server-side dan SQLite. Satu proses, satu
worker.

| Rute | Isi |
|---|---|
| `/` | feed 12 kartu |
| `/berita/{nid}` | detail, satu event `view` per halaman tampil |
| `/histori` | riwayat bacaan, waktu dalam WIB |
| `/onboarding/topik` | pilih topik, sekali per akun, maksimal 5 |
| `/register`, `/login` | akun |

Urutan keputusan feed: riwayat → topik → popularitas. Pilihan topik hanya
menyaring daftar popularitas beku; tidak ada panggilan model di jalur itu.
Fitur persona dihapus pada v1.3, jadi `/login/persona` dan perintah
`seed_persona` sudah tidak ada.

Lapisan web tidak menghitung skor dan tidak mengurutkan ulang hasil. Semua
permintaan rekomendasi lewat `POST /recommend` pada API yang sama, dijalankan
in-process lewat `httpx.ASGITransport`.

Kontrak API beku: [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) dan
[`docs/openapi.json`](docs/openapi.json).

---

## Konfigurasi

Variabel dibaca dari environment. `.env` tidak dimuat otomatis, karena tidak
ada `load_dotenv` di repo ini, jadi variabel harus diekspor di shell.

| Variabel | Default | Fungsi |
|---|---|---|
| `WEB_DB_PATH` | `data/web.db` | Lokasi SQLite |
| `WEB_SESSION_TTL_DAYS` | `7` | Umur sesi |
| `WEB_HISTORY_LIMIT` | `50` | Riwayat yang dikirim ke API |
| `WEB_FEED_LIMIT` | `12` | Kartu yang dirender |
| `WEB_REC_TOP_K` | `30` | `top_k` yang diminta ke API |
| `WEB_SECURE_COOKIES` | `0` | Set `1` di belakang HTTPS |
| `WEB_CSRF_SECRET` | acak per proses | Set nilai tetap untuk multi-worker |

`WEB_REC_TOP_K` harus ≥ `WEB_FEED_LIMIT`; kombinasi yang tidak masuk akal
membuat aplikasi gagal start dengan pesan jelas.

---

## Artefak

Yang tidak masuk git: parquet katalog dan interaksi, model ALS, serta CSV
mentah. Yang masuk git hanya sha256-nya, tercatat di dokumen lock.

| Artefak | Ukuran | Checksum |
|---|---|---|
| `data/processed/indo/catalog.parquet` | 128 MB | `DATASET_LOCK_INDO.md` |
| `data/processed/indo/catalog_{train,dev}.parquet` | 103 / 26 MB | idem |
| `data/processed/indo/interactions*.parquet` | < 1 MB | idem |
| `models/indo_als_model.pkl` | 7,1 MB | idem |
| `data/processed/indo/source_links.parquet` | 3,2 MB | turunan, tidak dikunci |
| `data/raw/final_merge_dataset.csv` | 216 MB | idem |

`data/processed/indo/source_links.parquet` adalah turunan 3,2 MB dari kolom
`Link` CSV mentah (nid → URL). File inilah yang dibaca halaman detail dan ikut
ke dalam image Docker. CSV mentah 207 MB tidak diperlukan saat runtime; tanpa
keduanya aplikasi tetap jalan, hanya tautan portal yang tidak muncul.

---

## Dokumentasi

| Dokumen | Isi |
|---|---|
| [`data/DATASET_LOCK_INDO.md`](data/DATASET_LOCK_INDO.md) | Korpus aktif: angka, aturan, sha256, gate |
| [`docs/web/PRD_Web_Rekomendasi_Berita.md`](docs/web/PRD_Web_Rekomendasi_Berita.md) | PRD aktif |
| [`docs/web/ACCEPTANCE_CRITERIA.md`](docs/web/ACCEPTANCE_CRITERIA.md) | Kriteria penerimaan + ID tes |
| [`docs/web/ARCHITECTURE.md`](docs/web/ARCHITECTURE.md) | Struktur web layer |
| [`docs/web/DATA_MODEL.md`](docs/web/DATA_MODEL.md) | Skema SQLite |
| [`docs/web/DESIGN.md`](docs/web/DESIGN.md) | Token desain |
| [`docs/web/SECURITY_NOTES.md`](docs/web/SECURITY_NOTES.md) | Kontrol keamanan |
| [`docs/web/DEPLOYMENT.md`](docs/web/DEPLOYMENT.md) | Docker dan opsi hosting |

`docs/web/RUNBOOK.md` masih menyebut `seed_persona` dan pembacaan `.env`; dua
hal itu tidak berlaku lagi. Angka resource Docker di `docs/web/DEPLOYMENT.md`
diukur sebelum korpus indo dilayani.

### Docker

Image memuat artefak korpus indo (katalog, interaksi train/dev, model ALS, dan
peta tautan sumber 3,2 MB) dan melayani alpha 0,8.

```bash
docker build -t goodnews:latest .
docker run -d --name goodnews-app -p 8000:8000 -v goodnews-data:/data goodnews:latest
curl localhost:8000/health
# {"status":"ok","alpha":0.8,"catalog_size":67381,"als_items":13881}
```

Tanpa `-v`, database SQLite hilang setiap container di-restart.

---

## Status

- [x] Web layer: akun, feed, artikel, histori
- [x] Korpus indo: katalog, generator interaksi, split, ALS, evaluasi
- [x] Enam metrik evaluasi resmi (NDCG, AP/MAP, Precision, Recall, F1 @10)
- [x] Sapuan faktor & alpha diperbaiki; temuan konfigurasi belum optimal tercatat
- [x] Workbook perhitungan manual 13 sheet, terverifikasi recalc
- [x] Serving korpus indo (alpha 0,8)
- [x] Onboarding topik untuk pengguna tanpa riwayat (maksimal 5 topik)
- [x] Notebook perbandingan lima metrik (K = 5/10/20)
- [ ] Keputusan produk: ganti konfigurasi yang dilayani (faktor/alpha) atau tetap
- [ ] Final thesis documentation
