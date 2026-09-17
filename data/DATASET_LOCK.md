# DATASET LOCK — ta-news-rec (locked 2026-09-16)

Pasangan resmi, jangan dicampur dengan split/size lain.

## Pasangan train
- MINDsmall_train (EN + behaviors): news=51.282, behaviors=156.965, users=50.000
  - behaviors.tsv sha256:a424547c8fa17c9ea4879c2110221c2b2f2709f4f7615ede0b0d8e4765158658
  - news.tsv      sha256:cd49d7da275e9c405f627d75a0de9d4ec6ad43ff8a8db5d23a447591676e09d6
- xMINDsmall_train (ID): news=51.282
  - news.tsv      sha256:4bfa467172f16eb69c1d5e40da48ccbf79e4b43c7d6e5dc926ad0c63e8560b0f

## Pasangan dev
- MINDsmall_dev (EN + behaviors): news=42.416, behaviors=73.152, users=50.000
  - behaviors.tsv sha256:b6c460e33b1a8693252ded6e626da7d3ccf78920eea2ec11889020bb7d8443ef
  - news.tsv      sha256:e5d144667558c449d16084fe6bfa01940c2f5d5785ea9f9110292bc3b94eb822
- xMINDsmall_dev (ID): news=42.416
  - news.tsv      sha256:834f4c0732d0d9845dce16d1d15a7d507ff8a4b9b92e77024da5dc5488b78

## Hasil verifikasi
- Overlap NID MIND↔xMIND: 100% (train dan dev)
- Coverage NID behavior→teks Indonesia: 100%, hilang=0 (train dan dev)
- CTR dev impressions: 0.041 (111.383 klik / 2.740.998 tampil)
- Split temporal alami: train < 2019-11-15, dev = 2019-11-15 (file-based, jangan random split)

## Catatan stemming
- Sastrawi per kata-unik (53.082 kata), timeout 0,3 dtk/kata; token non-huruf
  dilewatkan tanpa stem. Token berafiks kompleks yang lolos: 2.175/2.883.286
  (0,075%) — negligible untuk baseline TF-IDF.

## Aturan
- Train hanya dari *_train, evaluasi hanya di *_dev.
- Join key = nid. Teks ID dari xMIND, kategori/entities dari MIND news.tsv.
- File large (MINDlarge_train, xMINDlarge_dev) bukan bagian lock ini.
