# Stratified evaluation: warm vs cold users

seed=42, warm sampled=2000/2858 eligible, cold sampled=2000/22703 usable sessions

## Table C — Warm users (ada history train, full catalog)

| method | alpha | NDCG@10 | MAP@10 | hit@10 | cov@10 | n |
|---|---:|---:|---:|---:|---:|---:|
| cf | 0.0 | 0.00200 | 0.00117 | 0.0085 | 0.0121 | 2000 |
| content | 1.0 | 0.00007 | 0.00003 | 0.0005 | 0.0465 | 2000 |
| hybrid | 0.4 | 0.00208 | 0.00120 | 0.0090 | 0.0216 | 2000 |
| hybrid | 0.8 | 0.00032 | 0.00011 | 0.0020 | 0.0446 | 2000 |

## Table D — Cold users (tanpa history train, session leave-last-out)

| method | alpha | NDCG@10 | MAP@10 | hit@10 | cov@10 | n |
|---|---:|---:|---:|---:|---:|---:|
| content | 1.0 | 0.00139 | 0.00076 | 0.0035 | 0.0354 | 2000 |
| hybrid_pseudo_cf | 0.0 | 0.00645 | 0.00499 | 0.0112 | 0.0066 | 1164 |
| hybrid_pseudo_cf | 0.4 | 0.00921 | 0.00706 | 0.0163 | 0.0117 | 1164 |
| hybrid_pseudo_cf | 0.8 | 0.00382 | 0.00193 | 0.0103 | 0.0226 | 1164 |
| hybrid_pseudo_cf | 1.0 | 0.00214 | 0.00122 | 0.0052 | 0.0233 | 1164 |
| popularity | — | 0.00000 | 0.00000 | 0.0000 | 0.0001 | 2000 |

