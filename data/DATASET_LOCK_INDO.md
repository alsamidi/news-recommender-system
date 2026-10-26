# DATASET LOCK KORPUS INDO — ta-news-rec (drafted 2026-10-27)

Korpus AKTIF untuk fase 2 penelitian + lapisan web.
Status **draft**: penanggalan cutoff & arsitektur artefak terkunci setelah tahap
generator dijalankan (kolom "TBC" dicatat eksplisit; jangan menebak).
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
  `src/preprocessing/build_corpus_indo.py` dan tercantum di keluarannya; jangan
  menampilkan tag portal mentah sebagai kategori (PRD §10.3 v1.1).

## Identitas artikel
- `nid` = `'I' + sha1(url).hexdigest()[:10]` — deterministik dari URL,
  bebas tabrakan dengan format MIND (`N...`), kontrak API tidak berubah.
- Saat build: **hard assert keunikan global `nid`** — tabrakan = build gagal
  keras, bukan warning. Bawa hasil assert (jumlah artikel, jumlah nid unik)
  ke output preproses untuk dibandingkan dengan angka lock ini.

## Interaksi
- Tidak ada interaksi nyata pada korpus. Interaksi dibangkitkan oleh
  **generator akun dummy** (pipeline penelitian), event `view` saja, satu
  model perilaku yang terdokumentasi + tervalidasi statistiknya
  (power-law popularitas, cakupan kategori).
- Arsitektur keluaran generator: `interactions_train.parquet` korpus-indo
  (path final tbc saat generator v1: TBC-GENERATOR-V1).
- Feed populer, persona warm, dan evaluasi CF semuanya bersumber dari
  interaksi simulasi ini (PRD v1.1 §18).

## Split
- File/aturan: temporal berbasis tanggal artikel untuk katalog, dan temporal
  untuk interaksi simulasi — **jangan random split** (asas sama dengan lock MIND).
- Cutoff final: TBC-GENERATOR-V1 (dicatat di sini setelah generator jalan; angka
  evaluasi apa pun sebelum cutoff terkunci dilarang masuk laporan).

## Aturan campur
- Larangan campur: MIND split/join/jumlah NID tidak boleh dipakai untuk
  korpus ini dan sebaliknya. `data/DATASET_LOCK.md` tetap memaku riset v1.
- Indikator angka korpus aktif: 80.472 mentah / 67.381 unik / 3 sumber.
- Angka evaluasi korpus v1 (MIND) tetap beku di `docs/metrics_source_of_truth.md`
  dan TIDAK banding-argumen langsung dengan angka korpus baru (protokol beda).
