# Sumber Kebenaran Metrik (Thesis Audit — Day 5 final)

Aturan: **setiap angka yang masuk laporan (Word) wajib berasal dari file di bawah.**
Dilarang menyalin angka dari ingatan, chat, atau file turunan tanpa cek ulang ke JSON sumber.
File `*_tables.md` hanya bacaan manusia (di-generate); **sumber resmi = file JSON**.

## Peta file → tabel

| Tabel | Sumber resmi (angka) | Generator (kode) | Bacaan manusia |
|-------|----------------------|------------------|----------------|
| A — restricted catalog | `models/full_catalog_eval.json` → `table_a_restricted` | `src/evaluation/full_catalog_eval.py` (`sweep_table_a`) | `models/full_catalog_tables.md` |
| B — full catalog | `models/full_catalog_eval.json` → `table_b_full_catalog` | `src/evaluation/full_catalog_eval.py` (`sweep_table_b`) | `models/full_catalog_tables.md` |
| C — warm | `models/stratified_eval.json` → `table_c_warm` | `src/evaluation/stratified_eval.py` (`sweep_warm`) | `models/stratified_tables.md` |
| D — cold | `models/stratified_eval.json` → `table_d_cold` | `src/evaluation/stratified_eval.py` (`sweep_cold`) | `models/stratified_tables.md` |
| Konteks dataset sulit | `models/error_coverage.json` → `full` | `src/evaluation/error_coverage.py` | — |
| Ukuran dataset / sha / cutoff | `data/DATASET_LOCK.md` | `src/preprocessing/build_locked.py` | — |

Protokol bersama: seed 42, metrik frozen identik (`_metrics_at_ks`, min-max per user, top-k terurut),
kandidat train/session selalu di-mask. Status verifikasi: seluruh baris `*_tables.md` cocok dengan
JSON (cek per seksi), `2000 − 1164 = 836` konsisten, `pytest` 12 passed.

## Nilai yang diloloskan ke laporan (NDCG@10)

### Table A — restricted (ruang item ALS, 3.394 item; n=1.139; `table_a_restricted`)

| α | NDCG@10 | Pointer baris |
|---|---------|---------------|
| 0,0 (pure CF) | 0,00536 | `alpha == 0.0` |
| 0,4 | 0,00559 | `alpha == 0.4` |
| 1,0 (pure content) | **0,00928** (tertinggi A) | `alpha == 1.0` |

### Table B — full catalog (93.698 item; n=2.000/2.858 eligible; `table_b_full_catalog`)

| α | NDCG@10 | MAP@10 | hit@10 | Pointer baris |
|---|---------|--------|--------|---------------|
| 0,0 (pure CF) | 0,00200 | 0,00117 | 0,0085 | `alpha == 0.0` |
| 0,4 (hybrid) | **0,00208** (tertinggi B) | 0,00120 | 0,0090 | `alpha == 0.4` |
| 1,0 (pure content) | 0,00007 | 0,00003 | 0,0005 | `alpha == 1.0` |

### Table C — warm (protokol = B; n=2.000; `table_c_warm`)

| method / α | NDCG@10 | Pointer baris |
|------------|---------|---------------|
| cf / 0,0 | 0,00200 | `method == cf` |
| hybrid / 0,4 | **0,00208** (tertinggi C) | `method == hybrid, alpha == 0.4` |
| content / 1,0 | 0,00007 | `method == content` |

### Table D — cold (session leave-last-out; `table_d_cold`)

| method / α | NDCG@10 | MAP@10 | hit@10 | n | Pointer baris |
|------------|---------|--------|--------|---|---------------|
| content / 1,0 | 0,00139 | 0,00076 | 0,0035 | 2000 | `method == content` |
| hybrid_pseudo_cf / 0,0 (CF-proxy saja) | 0,00645 | 0,00499 | 0,0112 | 1164 | `alpha == 0.0` |
| hybrid_pseudo_cf / 0,4 | **0,00921** (tertinggi D, subset) | 0,00706 | 0,0163 | 1164 | `alpha == 0.4` |
| hybrid_pseudo_cf / 1,0 (content saja, subset) | 0,00214 | 0,00122 | 0,0052 | 1164 | `alpha == 1.0` |
| popularity | 0,00000 | 0,00000 | 0,0000 | 2000 | `method == popularity` |

Perbandingan langsung yang sah di Table D: empat baris `hybrid_pseudo_cf`
(α=0 / 0,4 / 0,8 / 1,0) berbagi n=1.164 — α=1,0 di subset ini adalah content-only
pembanding yang sepadan untuk α=0,4. Baris `content`/`popularity` (n=2.000)
tidak dapat dibandingkan secara langsung tanpa memperhatikan kolom n.

### Konteks (sitasi pendamping, bukan klaim utama)

- 62,7% item relevan dev tidak muncul di interaksi train
  (`error_coverage.json` → `full.pct_dev_relevant_items_unseen_in_train_interactions` = 0,62703…).
- 88,1% user dev tanpa train history
  (`error_coverage.json` → `full.pct_dev_users_without_train_history` = 0,88114).
- Katalog 93.698 vs ruang ALS 3.394
  (`full_catalog_eval.json` → `meta.n_catalog_full`, `meta.n_als_items`).
- Sampel: warm 2.000/2.858 eligible; cold 2.000/22.703 session usable
  (`stratified_eval.json` → `meta`).
- 836/2.000 session cold tanpa item ALS
  (`stratified_eval.json` → `table_d_cold[].note = users_without_pseudo_cf=836`; 2000−1164=836).

## Cerita hasil yang dikunci (menjawab RQ)

RQ: *Apakah kombinasi content-based + collaborative filtering membantu dibanding
masing-masing metode sendiri, dan bagaimana performanya ketika kondisi katalog/user berbeda?*

- **Table A (restricted, kondisi terbatas): TIDAK.** Pure content (α=1,0; 0,00928)
  mengalahkan semua campuran; skor cenderung menurun saat bobot CF ditambah
  (tren turun dari α=1,0: 0,00928 ke α=0,0: 0,00536, dengan fluktuasi kecil
  di α=0,1–0,3). Dalam ruang kecil di mana semua item punya
  sinyal CF, profil TF-IDF user sudah cukup. Ruang ini menyembunyikan cold-start
  item, sehingga kesimpulan A tidak dapat digeneralisasi ke katalog penuh.
- **Table B (full catalog, realistis dan jauh lebih sulit): YA.** Hybrid α=0,4
  (0,00208) > pure CF (0,00200) > pure content (0,00007). Skor absolut jatuh
  dibanding A (katalog ~27× lebih besar, relevan tipis median 1/user, 62,7%
  relevan tak terlihat di train). Content saja kolaps; CF membawa sinyal utama;
  campuran memberi puncak.
- **Table C (warm, user punya history): YA, tetapi kecil.** Hybrid 0,4 (0,00208)
  vs pure CF (0,00200, +4% relatif). Dengan history, personalisasi ALS sudah
  kuat; content hanya koreksi kecil.
- **Table D (cold, tanpa history): YA, dan besar.** Pada subset yang dapat
  dibentuk pseudo-CF (n=1.164, perbandingan langsung): hybrid 0,4 (0,00921) >
  CF-proxy saja (0,00645) > content saja subset (0,00214). Tanpa history, sinyal
  content/session menjadi penting dan campuran menang. Batas klaim: 836/2.000
  session tanpa item ALS tidak mendapat skor CF.

Kalimat tesis satu baris: *hybrid membantu pada katalog penuh dalam kedua kondisi
user; keunggulannya kecil saat history kaya (warm) dan besar saat history absen
(cold) — dengan klaim cold berlaku pada subset yang memiliki item ALS.*

## Caveat wajib di Bab IV

1. Skor absolut kecil — wajar untuk ranking 93.698 item dengan relevan tipis.
2. 836/2.000 session cold tanpa item ALS tidak mendapat skor CF.
3. Sweep α rapat (0,0–1,0 step 0,1) hanya ada di Tabel A/B; Tabel C/D hanya di
   titik 0,0/0,4/0,8/1,0.
4. Serving memakai α=0,4 dari `configs/hybrid.yaml` (`content_weight`, selaras
   Table B Day 4/5). `models/best_alpha.json` / `models/weighted_hybrid.pkl`
   (α=0,8) adalah catatan historis sweep ruang-ALS saja, tidak dipakai serving.
   Paritas serving vs evaluator dibuktikan `tests/test_hybrid_inference.py`.
   Perbedaan serving yang disengaja dan terdokumentasi di
   `src/models/hybrid/infer.py`: mask per-nid (already-liked filtering) dan
   dedupe presentasi (katalog menumpuk baris train+dev, 28.460 nid ganda).
