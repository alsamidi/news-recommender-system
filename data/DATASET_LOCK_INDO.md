# DATASET LOCK KORPUS INDO — ta-news-rec (drafted 2026-10-27)

Korpus AKTIF untuk fase 2 penelitian + lapisan web.
Status: katalog (Gerbang A), interaksi generator (Gerbang B), split temporal,
dan ALS (Gerbang C) **terkunci 2026-10-27**; angka evaluasi menyusul setelah
harness (lihat bagian evaluasi). PRD v1.1 disetujui pembimbing 2026-10-27.
Jangan dicampur dengan lock MIND (`data/DATASET_LOCK.md`) — itu korpus riset
versi 1 yang sudah beku.

## Sumber mentah
- File: `data/raw/final_merge_dataset.csv` (1 file CSV)
- sha256: 1fdab8112d69449768035f70eca6c6e90ca139f85644b7cb17648af77a111d8f
- Ukuran: 216.449.647 bytes
- Asal: Kaggle `sh1zuka/indonesia-news-dataset-2024` — "Indonesia News Dataset (2025)",
  penulis Yosia, DOI 10.34740/kaggle/ds/5673686, lisensi CC BY-NC 4.0 (edukasional).
- Didapat: unduhan manual 2026-10-27.
- Rentang konten: Juli 2024 – Oktober 2025 (2025 = 56.412 baris, 2024 = 24.060,
  0% di luar rentang). Catatan: deskripsi halaman Kaggle menyebut "January 2024";
  data aktual dimulai Juli 2024.

## Skema mentah (10 kolom, terukur)
'| Judul, Waktu, Link, Content, tag1, tag2, tag3, tag4, tag5, source |'
- Baris mentah: 80.472; sumber: kompas 35.449, tempo 25.633, detik 19.390.
- Duplikat URL: 6.691 URL muncul 2–4x (19.782 baris terlibat) — **100% identik
  konten + tanggal** (re-scrape); deduplikasi by URL aman tanpa arbitrase.
- Katalog unik: **67.381 artikel**.
- Komentar tanggal: 3 gaya format portal; parser bulan-Indonesia terbukti
  mem-parse 100% baris (probe 2026-10-27).
- Komentar konten: kosong 0,01%; median 2.225 chars (p5 1.028, p95 4.365);
  boilerplate portal (mis. "Baca berita dengan sedikit iklan" di tempo) wajib
  distrip pada preproses.
- Tag1–tag5: keyword portal (entitas/kejadian/wilayah), null 3%/3,6%/11%/29%/56%.
  **Bukan taksonomi kategori** — tidak dipakai sebagai kategori; boleh dipakai
  sebagai fitur sekunder memungkinkan, bukan bagian lock.

## Kategori (turunan, bukan mentah)
- Sumber: seksi URL (tempo: `/politik/`, `/ekonomi/`, ...; detik: subdomain
  `news.detik.com`, ...; kompas: subdomain sebelum `.kompas.com` karena URL
  kanonik berbentuk `kompas.com/read/...`).
- Cakupan terukur: seksi ter-extract 100% baris (probe 2026-10-27).
- Pemetaan sekksi-URL → label kategori akhir diterministik oleh
  `src/phase2/build_corpus_indo.py` dan tercantum di keluarannya; jangan
  menampilkan tag portal mentah sebagai kategori (PRD §10.3 v1.1).

## Identitas artikel
- `nid` = `'I' + sha1(url).hexdigest()[:10]` — deterministik dari URL,
  bebas tabrakan dengan format MIND (`N...`), kontrak API tidak berubah.
- Saat build: **hard assert keunikan global `nid`** — tabrakan = build gagal
  keras, bukan warning. Bawa hasil assert (jumlah artikel, jumlah nid unik)
  ke output preproses untuk dibandingkan dengan angka lock ini.

## Katalog (Gerbang A — terkunci 2026-10-27)
- Builder: `python -m src.phase2.build_corpus_indo` (`src/phase2/`, beku-set
  research v1 tidak disentuh; rules stemming replika v1 — Sastrawi per
  kata-unik, timeout 0,3 dtk, stopwords `configs/stopwords_id.txt`, tanpa
  kamus alay).
- File katalog: `data/processed/indo/catalog.parquet` (gitignored; hash di
  bawah adalah identitasnya).
- sha256: `971c4db2853735b4c7627d0e119a8624bc6d1cd95121f61ee72066ade5836bca`
- Kolom: `nid, title, content, processed_text, category, source,
  published_at, split` — `split="unsplit"` semua baris (cutoff nanti dari
  interaksi, Gerbang setelah generator).
- Angka terukur build (assert keras lulus): 80.472 mentah → 67.381 unik
  (== angka lock), nid unik 67.381, tabrakan 0. Per sumber: kompas 35.275,
  tempo 25.580, detik 6.526. — Catatan detik: 19.390 baris mentah menyusut
  jadi 6.526 URL unik (pola re-scrape; total dupl. URL 6.691 group).
- `published_at`: tz-aware UTC dari parser Waktu (via keputusan ±7h di
  docstring parser; kompas tanpa jam = midnight).
- Kategori: turunan seksi URL 100% tercakup (unknown = build gagal keras).
  Peta final `SECTION_TO_LABEL` (sumber: build summary JSON
  `docs/evidence/phase2/build_summary.json`; tempo→12 label, detik→7,
  kompas→1 label "Berita"):
  - tempo: politik→Politik; hukum→Hukum; ekonomi→Ekonomi; internasional,
    dw, bbc-world, abc-australia, internasional-utama→Internasional;
    sepakbola, hno, bola, olahraga→Olahraga; hiburan, gaya-hidup, musik,
    seleb→Hiburan; teroka→Teroka; sains, digital, tekno→Tekno-Sains;
    lingkungan→Lingkungan; kolom, tokoh, wawancara→Kolom;
    cekfakta→Cek Fakta; info-tempo, arsip, newsletter, data,
    prelude→Info Tempo; foto, video, infografik, detiktv,
    infografis→Multimedia; investigasi→Investigasi; otomotif→Otomotif;
    ramadan, ramadhan→Ramadan.
  - detik: berita→Berita; pilkada, pemilu→Pemilu; dw, bbc-world,
    abc-australia, internasional-utama→Internasional; kolom→Kolom;
    detiktv, infografis→Multimedia; adv-nhl-detikcom, bangun-indonesia,
    melindungi-tuah-marwah→Bersponsor. — **Batasan sumber (bukan bug):**
    semua URL detik bertumpu pada satu subdomain `news.detik.com`; seksi
    diambil dari segmen path channel.
  - kompas: subdomain nasional, megapolitan, regional→Berita;
    internasional→Internasional (1 artikel).
- Distribusi kategori terukur: Berita 40.468, Politik 4.928, Ekonomi 3.736,
  Hukum 3.697, Multimedia 2.330, Internasional 2.225, Info Tempo 2.168,
  Hiburan 1.998, Olahraga 1.877, Tekno-Sains 969, Teroka 884, Lingkungan
  793, Pemilu 475, Kolom 349, Bersponsor 265, Cek Fakta 166, Otomotif 34,
  Ramadan 10, Investigasi 9.

## Interaksi
- Tidak ada interaksi nyata pada korpus. Interaksi dibangkitkan oleh
  **generator akun dummy** (pipeline penelitian), event `view` saja, satu
  model perilaku yang terdokumentasi + tervalidasi statistiknya
  (power-law popularitas, cakupan kategori).
- **GERBANG B — terkunci 2026-10-27.** File interaksi:
  `data/processed/indo/interactions.parquet` (gitignored),
  sha256: `9175c6bab6e2fef2546aba0edd8ea88042ed3b897fea538084167f58b5715a56`.
  Kolom: `dummy_user_id, nid, event="view", occurred_at` (tz-aware UTC).
- Parameter final (GeneratorConfig, semua flag CLI
  `python -m src.phase2.run_generator`): n_accounts=600,
  reads_per_account=(60, 180), powerlaw_s=1.1, recency_days=180,
  category_drift=0.2, seed=42. 72.034 event total.
- **Aturan katalog efektif** (67.381 item tidak capai densitas dengan N
  masuk akal — diukur: full catalog butuh ~10x akun): filter tanggal
  `published_at >= 2025-09-01` → **17.584 item** (band 10–20k rencana);
  tanpa filter kategori. Aturan TERCATAT di sini, bukan silent filtering.
- Profil akun: Dirichlet tilt (alpha=0.3) dikali base rate katalog
  (availability), dinormalisasi — akun terkonsentrasi, populasi mengikuti
  komposisi katalog. Keputusan terukur: Dirichlet idiosinkratik murni
  menghasilkan campuran populasi ~seragam (~0,058/17 kategori) yang tidak
  bisa dibandingkan dengan availability katalog.
- Gate B lulus (terukur, `docs/evidence/phase2/gate_b_report.json`):
  item ≥1 view **82,7%** (target ≥60%), item ≥3 views **54,0%** (≥30%),
  akun ≥10 bacaan **100%**; power-law exponent 0,743 (R² 0,783).
  Percobaan: n=300 → 58,7%/19,2% (gagal); n=600 → lulus.
- Feed populer, persona warm, dan evaluasi CF semuanya bersumber dari
  interaksi simulasi ini (PRD v1.1 §18).

## Split
- File/aturan: temporal berbasis tanggal artikel untuk katalog, dan temporal
  untuk interaksi simulasi — **jangan random split** (asas sama dengan lock MIND).
- **GERBANG SPLIT — terkunci 2026-10-27 (setelah Gate C lulus).** Cutoff =
  kuantil-80 waktu event: **2025-09-18 06:05:20.102251571+00:00**
  (`src/phase2/split.py::draft_q80`, interpolasi linear atas occurred_at).
  Dev events terukur 14.407 (≥ 200 — stabil untuk evaluasi; tidak perlu
  menaikkan kuantil).
- Interaksi: `interactions_train.parquet` 57.627 event
  (sha256 `6841aa30eb1c0c71c5a94302d957c92056473d440319941aa9e1c96ecb56e416`),
  `interactions_dev.parquet` 14.407 event (sha256
  `0f5b0643d8afd2099f654987bc60b1d751d30c6fe3b31393080286842e1a390d`) —
  keduanya gitignored di `data/processed/indo/`.
- Katalog split: `catalog_train.parquet` 55.194 artikel (published ≤ cutoff,
  sha256 `6f7499dee4d9482d6e979f6f753faf58e4c2d0f3eee439d6796df752f10527df`),
  `catalog_dev.parquet` 12.187 artikel (setelahnya, sha256
  `27027761d3f915a16d3ef20fbd0d8727b51aff967d180b9ae56d12416fc269bb`).
  Artikel tanpa interaksi tetap di katalog TF-IDF (train UNTUK fit vectorizer,
  full catalog untuk transform); **tidak pernah masuk CF sebagai item**
  (item CF = item ber-faktor dari matriks train saja).
- **Aturan beku pasca-cutoff:** setelah commit Gerbang Split ini, parameter
  generator TIDAK BOLEH diubah tanpa me-reset seluruh evaluasi (angka
  evaluasi apa pun yang dihitung dengan parameter lain dilarang masuk
  laporan). Alur terkunci: Gate B (n=600, seed=42, rule 2025-09-01) →
  cutoff q80 → ALS (factors=128, reg=0.01, iter=20, alpha=40, seed=42).

## ALS (Gerbang C — terkunci 2026-10-27)
- Matriks: CSR dummy_user × nid dari **interaksi TRAIN saja**; konfidensi
  c = 1 + 40·r (r = jumlah view per pasangan — berat 1/view standar, alpha
  40 default v1 tidak diubah tanpa catat). Bentuk terukur 600 × 13.881,
  nnz 57.292.
- Model: `implicit.als.AlternatingLeastSquares` factors=128,
  regularization=0.01, iterations=20, random_state=42 (default riset v1;
  param MIND di `configs/als.yaml` TIDAK disentuh — fase-2 params hidup di
  `src/phase2/train_als.py` dan di sini).
- Artefak (gitignored, identitas via sha256):
  - `models/indo_als_model.pkl` — `5188465f1f975093a166f5f2ad96f5828a8f19e2ab2a4fee69000ea5a0c711dc`
  - `models/indo_als_user_factors.npy` — `8ad68981822a4e15b6406a253d2d942de42f9728e2c45a39ec2c5c15ba15fec2`
  - `models/indo_als_item_factors.npy` — `da515ef5f1b1d3486d226e283a2021f6860a63d9acf08a76d4ff7d0c1345518c`
- Gate C terukur (`docs/evidence/phase2/gate_c_report.json`): cakupan faktor
  item **78,9%** dari 17.584 item katalog efektif (13.881 item punya faktor;
  target ≥60% — lulus, tanpa iterasi balik ke Task 8); cakupan akun **100%**
  (600/600).
- Catatan jujur: sisa 21,1% item efektif tanpa faktor = item efektif yang
  tidak kebagian view di TRAIN (cold-start ALS); mereka tetap tervalidasi
  lewat jalur CBF/popularity dan tidak pernah dipaksa punya faktor.

## Aturan campur
- Larangan campur: MIND split/join/jumlah NID tidak boleh dipakai untuk
  korpus ini dan sebaliknya. `data/DATASET_LOCK.md` tetap memaku riset v1.
- Indikator angka korpus aktif: 80.472 mentah / 67.381 unik / 3 sumber.
- Angka evaluasi korpus v1 (MIND) tetap beku di `docs/metrics_source_of_truth.md`
  dan TIDAK banding-argumen langsung dengan angka korpus baru (protokol beda).
