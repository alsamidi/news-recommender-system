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
