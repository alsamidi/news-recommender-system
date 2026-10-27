# Addendum PRD v1.2 (DRAFT) — Pemilihan Topik untuk Feed Awal User Tanpa Riwayat

**Versi:** addendum yang dilebur menjadi PRD v1.2
**Tanggal:** 27 Oktober 2026
**Status:** **DISETUJUI owner 2026-10-27** (persetujuan produk oleh pemilik
Tugas Akhir pada sesi kerja; persetujuan pembimbing akademik atas PRD v1.1
tetap terpisah dan sudah tercatat). Isinya dilebur ke
`PRD_Web_Rekomendasi_Berita.md` v1.2 dan **6** dokumen pendamping diselaraskan
(daftar di §8). Implementasi di `feat/web-mvp`, branch turunan
`feat/dataset-indo-news`.
**Dokumen induk:** `PRD_Web_Rekomendasi_Berita.md` v1.1 (disetujui 2026-10-27)
**Korek atas:** keputusan PRD v1.0 §5.2/§18 "tidak ada pilih topik" dibatalkan
secara **terbatas dan terukur** oleh addendum ini — hanya untuk user tanpa
riwayat, hanya sebagai seleksi kandidat, tanpa menyentuh model dan kontrak API.

---

## 1. Latar dan Justifikasi (fakta)

Dua fakta yang sebelumnya membuat fitur topik dipotong kini berubah:

1. **Alasan data-lawas sudah tidak berlaku.** PRD v1.0 memotong onboarding
   topik karena "preferensi topik belum tentu ada pemetaannya secara valid di
   dataset" (lihat juga `DATA_MODEL.md` §2.2: era MIND, 3 dari 5 chip topik
   Figma tidak punya padanan `category`). Di korpus aktif, `category` adalah
   hasil pemetaan seksi URL dengan cakupan terukur **100%** baris dan peta
   deterministik terdokumentasi (`data/DATASET_LOCK_INDO.md`) — pemetaan
   valid sudah terukur, bukan asumsi.
2. **Lubang pengalaman yang benar-benar ada.** Saat ini user tanpa riwayat
   hanya mendapat "Berita populer" — sinyal nol personal, dan sumbernya
   interaksi **simulasi** akun dummy (bukan perilaku nyata). Preferensi topik
   merupakan **satu-satunya sinyal yang benar-benar berasal dari user** pada
   detik-0. Fitur ini juga mengembalikan janji proposal prasidang ("fallback
   pilih topik untuk cold start") ke dalam produk tanpa mengubah judul TA.

Tag: faktanya terukur; klaim kebermanfaatan UX bersifat rencana (tag
assumption), diuji lewat demo/UAT, bukan lewat metrik offline beku.

## 2. Cakupan Fitur (keputusan yang dimintakan persetujuan)

| # | Keputusan | Pilihan yang diusulkan |
|---|-----------|------------------------|
| C1 | Siapa yang terdampak | Hanya **user biasa dengan 0 event `view`**. Persona dan user ber-riwayat 100% tidak terdampak. |
| C2 | Wajib atau opsional | Opsional dan skippable; screen onboarding muncul **sekali tepat setelah registrasi**, tombol "Lewati" selalu ada. Tidak ada halaman edit preferensi di draf ini. |
| C3 | Efek pada rekomendasi | **Seleksi kandidat, bukan skoring.** Tidak ada panggilan `POST /recommend` baru, tidak ada α baru, tidak ada skor baru, tidak ada re-ranking di web. |
| C4 | Sumber peringkat | List popularitas beku yang sudah ada (dihitung sekali di startup) — feed topik adalah **irisan (slice) per kategori** dari list yang sama, tanpa ranking baru. |
| C5 | Interaksi vs preferensi | Preferensi topik disimpan sebagai **data profil** (`user_topics`), bukan event; aturan "interaksi = `view` saja" (v1.1 §18) tetap; preferensi tidak pernah masuk pipeline riset/ALS. |
| C6 | Handover | Begitu user punya ≥1 `view`, feed kembali ke jalur prioritas v1.1 (persona → history → populer). Preferensi jadi inersia (disimpan, tidak dipakai). |
| C7 | Label UI | Feed topik berlabel **"Populer di topik pilihanmu"** — jujur bahwa ini popularitas terbatas, bukan keluaran model; larangan klaim personalisasi model tetap. |

## 3. Pisau Ukur Set Topik (terukur 2026-10-27, probe read-only atas
`data/processed/indo/catalog.parquet` + `interactions_train.parquet`)

Katalog efektif serving = band `published_at >= 2025-09-01` (17.584 item — angka
lulus pengecekan sama dengan lock). Kolom `seen` = item ber-≥1 view train
(kandidat feed), `pool3` = item ber-≥3 view.

| Kategori | band | seen (≥1 view) | pool3 (≥3 view) | Ditawarkan? |
|---|---|---|---|---|
| Berita | 4.862 | 3.530 | 1.773 | Tidak — label catch-all, ≈ tanpa personalisasi |
| Politik | 2.339 | 1.845 | 1.068 | ✅ |
| Hukum | 2.063 | 1.676 | 984 | ✅ |
| Ekonomi | 1.822 | 1.427 | 851 | ✅ |
| Info Tempo | 1.228 | 1.018 | 635 | Tidak — bucket layanan editorial, bukan minat |
| Multimedia | 1.196 | 974 | 637 | ✅ |
| Olahraga | 860 | 725 | 459 | ✅ |
| Hiburan | 834 | 691 | 452 | ✅ |
| Internasional | 778 | 634 | 399 | ✅ |
| Lingkungan | 420 | 356 | 233 | ✅ |
| Teroka | 413 | 334 | 223 | ✅ |
| Tekno-Sains | 395 | 348 | 233 | ✅ |
| Kolom | 174 | 152 | 107 | ✅ |
| Cek Fakta | 90 | 80 | 54 | ✅ |
| Bersponsor | 76 | 60 | 44 | Tidak — konten sponsor |
| Otomotif | 25 | 23 | 12 | Tidak — pool di bawah ambang |
| Investigasi | 9 | 8 | 5 | Tidak — pool di bawah ambang |
| Pemilu | 0 | 0 | 0 | Tidak — **kosong di band efektif** |
| Ramadan | 0 | 0 | 0 | Tidak — **kosong di band efektif** |

**Aturan tawar-topik (deterministik, terukur):** chip onboarding = label
kataset dengan `seen ≥ 50` **minus** label `{Bersponsor, Info Tempo, Berita}`.
Hasilnya **12 chip**: Politik, Hukum, Ekonomi, Multimedia, Olahraga, Hiburan,
Internasional, Lingkungan, Teroka, Tekno-Sains, Kolom, Cek Fakta — urutan
kanonik mengikuti tabel §3 (band size menurun); daftar prosa versi draf
menukar Tekno-Sains dengan Lingkungan/Teroka, dan tabel terukur yang menang.
Aturan ini hidup sebagai konstanta ber-dokumentasi di `src/web/`, bukan angka
hardcode di template. Angka ini akan bergeser hanya jika korpus di-lock ulang.

## 4. Algoritma Feed Topik (definisi eksak untuk coding agent)

Dengan `m` = topik terpilih (1 ≤ m ≤ 3), urutan topik = **urutan kanonik chip
§3** yang tersimpan di `user_topics.position` (bukan urutan klik — lihat §5);
`P_L` = list popularitas beku yang difilter label `L`; riwayat = seluruh `nid`
yang pernah dibuka (aturan v1.1 §8.3 tidak berubah):

1. **Kuota per topik:** `q = ceil(10 / m)`.
2. **Ambil awal:** dari tiap `P_L` ambil `q` teratas; sisipkan round-robin
   (`P_1[0], P_2[0], …, P_1[1], …`) hingga ≥10 kandidat.
3. **Isi ulang:** jika hasil kurang dari 10 (pool topik habis / tersaring
   riwayat), isi dari list popularitas global beku berurutan (skip yang sudah
   masuk/sudah dibaca). Isian global dilerui: tampil normal, tanpa label khusus.
4. **Gerbang keluaran sama dengan v1.1:** filter seluruh riwayat → dedup
   `nid` → pertahankan urutan irisan → maksimal 10 kartu.
5. **Larangan:** tidak memanggil `/recommend`, tidak membentuk skor, tidak
   mengurutkan ulang satu pun list popularitas; satu-satunya operasi baru
   adalah irisan dan interleave deterministik dari list yang sudah beku.

Kedalaman pool terjamin: chip terkecil (Cek Fakta) ber-pool3 54 item —
jauh di atas kuota maksimum 10 setelah filter riwayat user baru (0 item).

### 4.1 Mengapa batas 3 topik (jawaban untuk pertanyaan penguji)

Batas `m <= 3` bukan angka bulat yang dipilih tanpa dasar: ia ditentukan oleh
**interaksi antara ukuran feed dan kuota `q = ceil(10/m)`**, dan bisa
dipertanggungjawabkan dengan membalik pertanyaannya — apa yang terjadi kalau
batasnya dilonggarkan? Diukur pada list popularitas beku yang sama
(`slice_by_topic`, katalog efektif 17.584 item):

| `m` | `q = ceil(10/m)` | Kartu per topik (urutan kanonik) | Kartu terpakai |
|---|---|---|---|
| 1 | 10 | 10 | 10 |
| 2 | 5 | 5, 5 | 10 |
| **3** | **4** | **4, 3, 3** | **10** |
| 4 | 3 | 3, 3, 2, 2 | 10 |
| 5 | 2 | 2, 2, 2, 2, 2 | 10 |
| 6 | 2 | 2, 2, 2, 2, 1, 1 | 10 |
| 10 | 1 | 10 topik × 1 kartu | 10 |
| 11 | 1 | 10 topik × 1 kartu, **1 topik × 0 kartu** | 10 |
| 12 | 1 | 10 topik × 1 kartu, **2 topik × 0 kartu** | 10 |

Tiga alasan, semuanya terukur:

1. **Feed hanya 10 kartu (PRD §18).** Setiap topik tambahan mengurangi kuota
   per topik. Pada `m = 3` tiap topik masih mendapat 3–4 kartu (topik terkuat
   = 40% feed) — cukup untuk menunjukkan topik itu hadir. Pada `m = 4` porsi
   turun ke 30%, dan pada `m >= 5` tiap topik tinggal 1–2 kartu (20%): feed
   menjadi mosaik rata, preferensi keenam hanya menggeser satu kartu, dan label
   "Populer di topik pilihanmu" makin lemah karena tidak ada topik yang
   benar-benar mewarnai hasil.
2. **Di atas 10 topik, preferensi mulai kosong secara struktural.** Dengan
   `q = 1` dan feed 10 kartu, `m = 11` menyisakan 1 topik tanpa satu kartu pun,
   `m = 12` menyisakan 2. User memilih topik lalu tidak melihatnya sama sekali —
   itu janji yang dilanggar oleh desainnya sendiri.
3. **Sinyalnya segera menjadi inersia (C6), jadi friksi harus kecil.**
   Onboarding muncul sekali dan langsung diambil alih jalur riwayat setelah
   satu `view`. Menambah chip hanya menambah friksi untuk sinyal yang berhenti
   dipakai begitu user membaca satu berita. Tiga dari dua belas chip (25%)
   masih menyatakan preferensi tanpa menyalin hampir seluruh taksonomi.

Konsekuensi yang harus disebut jujur: batas ini adalah **keputusan desain
produk, bukan hasil optimasi**. Kami tidak mengukur bahwa 3 lebih baik daripada
2 atau 4 terhadap kepuasan pengguna — tidak ada data user nyata untuk itu
(interaksi korpus adalah simulasi). Yang bisa dipertanggungjawabkan adalah
batas atas: mulai `m = 5` preferensi tambahan berhenti berpengaruh, dan mulai
`m = 11` ada topik yang tidak terwakili sama sekali. Angka 3 dipilih karena
berada di bawah kedua ambang itu dengan margin, sekaligus memberi user ruang
menyatakan lebih dari satu minat.

## 5. Skema Database (SQLite `data/web.db`)

Tabel baru `user_topics` (menghidupkan nama yang di v1.0/v1.1 sengaja
absen — `DATA_MODEL.md` §3.4 dan PRD §9.4 dicabut terbatas oleh addendum ini):

| Kolom | Tipe | Aturan |
|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT |
| `user_id` | INTEGER | FK ke `users.id` ON DELETE CASCADE |
| `label` | TEXT | Harus anggota set 12 chip §3; divalidasi di server |
| `position` | INTEGER | 1..m, **urutan kanonik chip §3** (dipakai determinisme) |
| `created_at` | TEXT | UTC ISO-8601 |

Batasan: `UNIQUE (user_id, label)`; maksimal **3** baris per user; dibaca
server-side dari sesi (identitas dari sesi, bukan parameter); form post pakai
CSRF (v1.1 §11). Skema idempoten via `CREATE TABLE IF NOT EXISTS` di jalur
migrasi yang sama. Kolom/volume: <100 user demo, <100 KB — tanpa service baru.
Indeks: `UNIQUE (user_id, label)` sudah mencakup pola baca per user.

**Koreksi implementasi (diputuskan saat eksekusi, 2026-10-27):**

1. **`position` = urutan kanonik, bukan urutan klik.** Form multi-checkbox HTML
   mengirim nilai dalam urutan DOM, bukan urutan klik — "urutan pilihan user"
   tidak dapat direkam tanpa JavaScript. Menyimpan urutan yang berbeda dari
   yang dikirim browser akan membuat feed nondeterministik. Konsekuensi yang
   diterima: himpunan chip yang sama berperilaku sama, apa pun urutan kliknya,
   dan AC-58 berlaku apa adanya (tanpa kualifikasi "urutan pilihan sama").
2. **Kolom penanda `users.topics_prompted_at TEXT NULL`.** Tanpa kolom ini,
   "sudah menekan Lewati" dan "belum pernah ditanya" sama-sama terlihat sebagai
   nol baris `user_topics`, sehingga janji "muncul sekali" (C2) tidak bisa
   dipenuhi. Kolom ditambahkan lewat `ALTER TABLE` idempoten yang dijaga
   `PRAGMA table_info` — `CREATE TABLE IF NOT EXISTS` tidak berpengaruh pada
   tabel `users` yang sudah ada di `data/web.db`.
3. **m = 0 berarti Lewati.** `ceil(10/m)` tidak terdefinisi untuk m = 0, maka
   form tanpa chip tidak menulis preferensi apa pun (hanya penanda).
4. **Desain chip memakai token yang ada**: radius `{rounded.sm}` (DESIGN.md
   tidak punya token chip; `{rounded.pill}` pricing-only, `{rounded.full}`
   untuk tombol ikon), border `{colors.muted}` (14,6:1; `hairline` 1,36:1
   gagal WCAG 1.4.11), state terpilih memakai `surface-soft` + ring ink (coral
   berarti error, D25), target sentuh terukur 45px, focus ring pada label, dan
   kelas CSS `.topic-chip` (bukan `topic-filter-*`).

## 6. Alur UX (ringkas; detail screen masuk UX_FLOWS saat dilebur)

1. Registrasi valid (FR-02 tetap) → screen onboarding opsional:
   "Pilih sampai 3 topik yang kamu sukai" + 12 chip + tombol "Lewati".
2. Lewati → langsung "Berita populer" (perilaku v1.1 persis).
3. Pilih → simpan → feed **"Populer di topik pilihanmu"**.
4. Buka artikel → `view` tercatat → feed berikutnya memakai jalur history
   (v1.1 §6.2) — preferensi tidak lagi mempengaruhi apa pun.
5. Placeholder copy (§10.2-mentah portal dilarang; label dari kataset, bukan tag):
   - Subjudul onboarding: "Pilihanmu hanya dipakai untuk feed awal. Rekomendasi
     dari riwayat bacaanmu akan aktif setelah kamu membuka berita."
   - Empty-state topik (semua kandidat tersaring riwayat): jatuh ke isi ulang
     global; feed tidak pernah kosong bila katalog tersedia.

## 7. Acceptance Criteria tambahan (namespace `PRD-AC`, lanjutan 55+)

- **PRD-AC-55 [P0]** Feed topik hanya dirender untuk user biasa dengan 0
  `view`; persona dan user ber-riwayat tidak pernah menerima feed topik.
- **PRD-AC-56 [P0]** Setiap item feed topik berkategori termasuk topik
  terpilih, atau berasal dari isi ulang global saat kuota habis; label feed
  berbeda dari "Berita populer".
- **PRD-AC-57 [P0]** Feed topik tidak menambah panggilan `POST /recommend`
  dan tidak mengirim/mengubah α; diturunkan murni dari list popularitas beku.
- **PRD-AC-58 [P0]** Dua user dengan himpunan topik sama mendapat urutan feed
  identik (determinisme round-robin + `position` kanonik), setelah filter
  riwayat masing-masing. Urutan klik tidak memengaruhi hasil.
- **PRD-AC-59 [P1]** Chip hanya 12 label §3; `Pemilu`, `Ramadan`, `Otomotif`,
  `Investigasi`, `Bersponsor`, dan tag portal mentah tidak pernah tampil.
- **PRD-AC-60 [P1]** Form onboarding menerima maksimal 3 chip, menolak label
  di luar set, memakai CSRF, dan bisa di-skip tanpa efek samping.
- **PRD-AC-61 [P2]** Tabel `user_topics` tidak dibaca/ditulis pipeline riset;
  perubahan hanya di `src/web/` + migrasi idempoten.
- **PRD-AC-62 [P1]** Smoke test user baru diperluas: register → (opsional)
  pilih topik → feed topik berlabel → buka detail → `view` → feed berikutnya
  via jalur history.

Pemetaan `TEST-AC-xxx` di `ACCEPTANCE_CRITERIA.md` melanjutkan dari **259**
( bukan 123+ ): 123–258 sudah terpakai — 120–122 demo, 123+ MIND-era UI,
dan 250–258 dari addendum §L. Aturan dual-namespace tetap berlaku.

## 8. Dokumen pendamping yang diselaraskan SETELAH persetujuan (6 dokumen)

1. `PRD_Web_Rekomendasi_Berita.md` → v1.2: §0 revisi, §5.2 dicabut satu butir
   (`Pemilihan topik/onboarding minat wajib maupun opsional` → hanya "wajib"
   yang tetap dilarang), FR-05 ditambah varian topik, §6.1 alur, §9.4, §16
   copy, §18 baris keputusan, §19 larangan kode.
2. `DATA_MODEL.md` §3.4: pindahkan `user_topics` dari "deliberately absent"
   ke skema §3.3bis (tabel baru), tambah keputusan bernomor.
3. `UX_FLOWS.md`: new flow onboarding terukur (12 chip, skip, handover).
4. `RECOMMENDATION_INTEGRATION.md` §4/§5: slot feed topik di prioritas
   routing (persona → history → **populer-di-topik** → populer), penegasan
   tanpa-skor dan tanpa-panggilan-API.
5. `ACCEPTANCE_CRITERIA.md`: `TEST-AC-259+` untuk PRD-AC-55…62 (§7 —
   123–258 sudah terpakai). **Selesai 2026-10-27**: §M + id di
   `tests/web/test_topics.py`.
6. `AGENTS.md` §6.5 baris Scope, agar rulebook tidak kontradiksi dengan PRD.

## 9. Risiko dan Mitigasi (tambahan atas PRD v1.1 §17)

| Risiko | Mitigasi |
|---|---|
| User menyangka feed topik = keluaran model AI | Label "Populer di topik pilihanmu" + copy onboarding eksplisit; larangan klaim model tetap |
| Pool topik sempit repetitif | Isi ulang global §4; `seen ≥ 50` sebagai gerbang tawar chip |
| Preferensi disalahartikan sebagai input model | C5: profil, bukan event; tidak pernah masuk pipeline riset; AC-57 |
| Re-ranking diam-diam di web melanggar §8.1 v1.1 | Deklarasi eksplisit: satu-satunya operasi = irisan + interleave deterministik; panitia uji AC-58 |
| Topik terus mempengaruhi feed setelah user punya riwayat | C6 handover keras; AC-55 |
| Scope creep ke halaman edit preferensi/search kategori | C2: tidak ada halaman edit di draf ini; search/filter kategori tetap out-of-scope v1.1 |

## 10. Keputusan yang akan mengunci addendum saat disetujui (ringkas untuk
pembimbing)

1. Pilih-topik opsional, sekali di onboarding, tanpa halaman edit.
2. Hanya user 0-view; handover keras ke jalur history.
3. Seleksi kandidat dari list popularitas beku; tanpa skor/baru ranking baru;
   tanpa sentuh kontrak/α/artefak.
4. 12 chip dari aturan terukur §3.
5. Kuota `ceil(10/m)` + isi ulang global.
6. Tabel `user_topics` (3 baris maks/user, `position` kanonik) +
   `users.topics_prompted_at` sebagai penanda "onboarding sudah ditampilkan".

Jika semua disetujui, #8 dikerjakan (dilebur PRD v1.2), baru implementasi
di `feat/web-mvp` turunan dari `feat/dataset-indo-news` setelah phase-2 merge.
