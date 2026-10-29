"""Sumber notebooks/eval_metrik_fokus.ipynb: laporan dua metrik fokus.

Notebook dirakit nbformat supaya sumbernya bisa direview sebagai teks biasa.
Jalankan:  python notebooks/build_eval_fokus_notebook.py
"""
from pathlib import Path

import nbformat as nbf

nb = nbf.v4.new_notebook()
md = nbf.v4.new_markdown_cell
code = nbf.v4.new_code_cell

cells = []

cells.append(md('''\
# Evaluasi fokus: NDCG@10 dan F1@10

Laporan ini menyempitkan evaluasi korpus indo ke dua metrik saja:

- **NDCG@10** sebagai metrik primer.
- **F1@10** sebagai pendamping.

Empat sistem dibandingkan: popularity, CBF, ALS, dan hybrid alpha 0,8 (konfigurasi
yang dilayani web).

Kenapa NDCG@10 jadi metrik primer:

1. Ia memperhitungkan urutan, dan feed berita memang punya urutan. Metrik
   berbasis himpunan (precision, recall) tidak membedakan hit di posisi 1 dan
   posisi 10.
2. Ia metrik yang sudah dipakai memilih alpha di evaluasi resmi, jadi angka
   barunya tidak perlu dijelaskan dari nol.
3. Ia standar di literatur sistem rekomendasi, sehingga angkanya bisa
   dibandingkan dengan penelitian lain.

Kenapa F1@10 sebagai pendamping: ia menyeimbangkan precision dan recall pada
cutoff yang sama, sehingga satu sistem tidak bisa tampak unggul hanya karena
menumpuk item populer di posisi atas.

Notebook ini TIDAK mengubah protokol resmi. Ia menghitung ulang dari artefak
beku dan memvalidasi ulang hasilnya ke `models/indo_eval.json`. Angka serving
tetap seperti sekarang.'''))

cells.append(code('''\
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

REPO = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.phase2 import config
from src.phase2.evaluate import ALPHA_GRID
from src.phase2.run_eval import (BASE_SHAPE, EFFECTIVE_SINCE, SEEDS, S_GRID,
                                 effective_catalog)
from src.phase2.generator import generate_interactions
from src.phase2.split import draft_q80, split_catalog, split_interactions
from src.phase2.train_als import build_csr, fit_als
from src.phase2.evaluate import (als_ranker, build_tfidf, cbf_ranker, minmax,
                                 popularity_ranker, rank_topk)
from notebooks.metrics_ext import METRICS

K = 10
SERVING_ALPHA = 0.8
SYSTEMS = ["popularity", "cbf", "als", f"hybrid_a{SERVING_ALPHA}"]
OUT_JSON = REPO / "docs/evidence/phase2/metric_focus.json"
OUT_MD = REPO / "docs/evidence/phase2/metric_focus.md"
LOCKED = json.loads((REPO / "models/indo_eval.json").read_text())
CACHE = Path("/tmp/eval_fokus_results.json")
# Cache bersama dengan notebook lima metrik: skema tiap titik sama.
SHARED_CACHE = Path("/tmp/eval_metrik_results.json")

print("metrik dilaporkan:", ["ndcg", "f1"], "| K =", K)
print("sistem:", SYSTEMS)'''))

cells.append(md('''\
## 1. Protokol

Sama dengan evaluasi resmi, tanpa perubahan:

- Kandidat: seluruh katalog dev, tanpa sampled negatives. Setiap item dinilai
  oleh setiap sistem; hanya 10 teratas yang dievaluasi.
- Relevan: item dev yang benar-benar dibaca akun itu sendiri.
- Sembilan titik sensitivitas: seed generator 1, 2, 3 dikali eksponen power-law
  0,9, 1,1, 1,3. Setiap titik 600 akun, jadi semua sel punya n yang sama dan
  aman dibandingkan.
- Fungsi peringkat diimpor dari `src/phase2/evaluate.py`, bukan ditulis ulang,
  sehingga sistem yang diukur identik dengan sistem yang dievaluasi resmi.

Lima metrik dihitung, tapi hanya dua yang dilaporkan. Precision dan recall
dihitung khusus untuk menguji klaim di bagian akhir.'''))

cells.append(code('''\
def load_cache(path):
    # Kunci JSON berupa string; kembalikan ke int supaya seragam.
    raw = json.loads(path.read_text())
    for point in raw:
        for sysd in point["systems"].values():
            for metric in sysd:
                sysd[metric] = {int(k): v for k, v in sysd[metric].items()}
    return raw


def compute_points(verbose=True):
    catalog = pd.read_parquet(REPO / config.CATALOG_OUT)
    eff = effective_catalog(catalog)
    out = []
    for gen_seed in SEEDS:
        for s in S_GRID:
            t0 = time.time()
            cfg = config.GeneratorConfig(
                n_accounts=BASE_SHAPE["n_accounts"],
                reads_per_account=BASE_SHAPE["reads_per_account"],
                powerlaw_s=s, recency_days=BASE_SHAPE["recency_days"],
                category_drift=BASE_SHAPE["category_drift"], seed=gen_seed)
            inter = generate_interactions(
                eff[["nid", "category", "source", "published_at"]], cfg)
            cutoff = draft_q80(inter)
            train_i, dev_i = split_interactions(inter, cutoff)
            train_c, _ = split_catalog(catalog, cutoff)
            csr, uidx, iidx = build_csr(train_i)
            model = fit_als(csr)

            relevant = dev_i.groupby("dummy_user_id")["nid"].apply(set).to_dict()
            dev_items = sorted(catalog["nid"].unique())
            accounts = sorted(set(dev_i["dummy_user_id"]))

            _, mat = build_tfidf(train_c, catalog)
            row_of = {n: i for i, n in enumerate(catalog["nid"])}
            als_fn = als_ranker(model, uidx, iidx, dev_items)
            cbf_fn = cbf_ranker(mat, row_of, train_i, dev_items)
            als_m = {a: minmax(als_fn(a)) for a in accounts}
            cbf_m = {a: minmax(cbf_fn(a)) for a in accounts}

            rankers = {
                "popularity": rank_topk(
                    popularity_ranker(train_i, dev_items), dev_items, accounts, K),
                "cbf": rank_topk(cbf_fn, dev_items, accounts, K),
                "als": rank_topk(als_fn, dev_items, accounts, K),
            }
            for alpha in ALPHA_GRID:
                def hyb(a, alpha=alpha):
                    return alpha * als_m[a] + (1 - alpha) * cbf_m[a]
                rankers[f"hybrid_a{alpha}"] = rank_topk(hyb, dev_items, accounts, K)

            per_sys = {}
            for name, ranking in rankers.items():
                acc = {m: [] for m in METRICS}
                for a in accounts:
                    rel = relevant.get(a, set())
                    for m, fn in METRICS.items():
                        acc[m].append(fn(ranking[a], rel, K))
                per_sys[name] = {m: float(np.mean(v)) for m, v in acc.items()}

            out.append({"seed": gen_seed, "s": s, "cutoff_draft": str(cutoff),
                        "train_events": int(len(train_i)),
                        "dev_events": int(len(dev_i)),
                        "n_accounts": len(accounts), "systems": per_sys})
            if verbose:
                print(f"seed={gen_seed} s={s}: {time.time()-t0:6.1f}s  "
                      f"ndcg@10 popularity={per_sys['popularity']['ndcg']:.6f}")
    return out


if CACHE.exists():
    results = load_cache(CACHE)
    print(f"cache: {len(results)} titik dari {CACHE}")
elif SHARED_CACHE.exists():
    results = load_cache(SHARED_CACHE)
    print(f"cache bersama: {len(results)} titik dari {SHARED_CACHE}")
else:
    print("menghitung 9 titik dari artefak beku (~11 menit)")
    results = compute_points()
    CACHE.write_text(json.dumps(results))

print("titik:", [(r["seed"], r["s"]) for r in results])
print("akun per titik:", {r["n_accounts"] for r in results})'''))

cells.append(md('''\
## 2. Validasi silang

NDCG@10 notebook harus sama persis dengan angka terkunci di
`models/indo_eval.json` untuk keempat sistem di sembilan titik. Toleransi 1e-9.
Sel berikut melempar error kalau ada satu nilai yang berbeda, jadi eksekusi yang
lolos berarti angkanya benar-benar hasil hitung ulang protokol yang sama, bukan
angka baru yang tidak bisa dipertanggungjawabkan.'''))

cells.append(code('''\
TOL = 1e-9
checked, failures = 0, []
for res in results:
    locked_point = next(p for p in LOCKED["per_point"]
                        if p["seed"] == res["seed"]
                        and abs(p["s"] - res["s"]) < 1e-12)
    for sys_name in SYSTEMS:
        mine = res["systems"][sys_name]["ndcg"]
        theirs = locked_point["ndcg@10"][sys_name]
        checked += 1
        if abs(mine - theirs) > TOL:
            failures.append((res["seed"], res["s"], sys_name, mine, theirs))

print(f"dicek: {checked} nilai NDCG@10 (9 titik x 4 sistem)")
if failures:
    for f in failures:
        print("  BEDA seed=%s s=%s %s: notebook=%.10f terkunci=%.10f" % f)
    raise AssertionError(f"{len(failures)} nilai tidak cocok dengan indo_eval.json")
print("cocok semua pada toleransi 1e-9: protokol notebook = protokol resmi")

f1_locked = {r["seed"]: set() for r in results}
print("cek F1 juga tersedia untuk 4 sistem:",
      all(set(SYSTEMS) <= set(r["systems"].keys()) for r in results))'''))

cells.append(md('''\
## 3. Hasil: NDCG@10 dan F1@10

Setiap angka adalah rata-rata atas 600 akun di satu titik. Tabel di bawah
meringkas mean dan rentang (min sampai max) atas sembilan titik.'''))

cells.append(code('''\
rows = []
for sys_name in SYSTEMS:
    for metric, key in (("ndcg@10", "ndcg"), ("f1@10", "f1")):
        vals = [r["systems"][sys_name][key] for r in results]
        rows.append({"system": sys_name, "metric": metric, "k": K,
                     "mean": float(np.mean(vals)),
                     "min": float(np.min(vals)),
                     "max": float(np.max(vals))})

focus = pd.DataFrame(rows).sort_values(["metric", "mean"], ascending=[True, False])
focus.to_json(OUT_JSON, orient="records", indent=2)

for metric in ("ndcg@10", "f1@10"):
    print(f"=== {metric} (mean 9 titik, n=600 per titik) ===")
    sub = focus[focus.metric == metric]
    for _, r in sub.iterrows():
        print(f"  {r['system']:11} {r['mean']:.6f}   rentang [{r['min']:.6f}, {r['max']:.6f}]")
    print()

print("JSON ->", OUT_JSON)'''))

cells.append(md('''\
## 4. Apakah F1 menambah informasi

Klaim yang perlu diuji, bukan diasumsikan: F1 baru berguna kalau presisi dan
recall bertukar prioritas antar sistem. Kalau rasio presisi terhadap recall
hampir sama untuk semua sistem, maka F1 hanya kelipatan dari recall, dan
urutannya pasti identik dengan urutan precision maupun recall.

Sel berikut menghitung rasio itu dari angka yang baru saja dihitung.'''))

cells.append(code('''\
print(f"{'sistem':11} {'P@10':>9} {'R@10':>9} {'F1@10':>9} {'P/R':>7}")
ratios = []
for sys_name in SYSTEMS:
    p = float(np.mean([r["systems"][sys_name]["precision"] for r in results]))
    rec = float(np.mean([r["systems"][sys_name]["recall"] for r in results]))
    f = float(np.mean([r["systems"][sys_name]["f1"] for r in results]))
    ratios.append(p / rec)
    print(f"{sys_name:11} {p:9.6f} {rec:9.6f} {f:9.6f} {p/rec:7.2f}")

spread = (max(ratios) - min(ratios)) / min(ratios) * 100
print(f"\\nsebaran rasio P/R antar sistem: {spread:.1f}%")
order_ndcg = [r["system"] for _, r in
              focus[focus.metric == "ndcg@10"].sort_values("mean", ascending=False).iterrows()]
print("urutan NDCG@10 :", order_ndcg)
print("urutan F1@10   :", [r["system"] for _, r in
      focus[focus.metric == "f1@10"].sort_values("mean", ascending=False).iterrows()])
print("\\ncatatan: urutan F1 mengikuti precision dan recall karena rasio P/R antar")
print("sistem hampir seragam, jadi F1 di sini menguatkan dan bukan informasi baru.")'''))

cells.append(md('''\
## 5. Grafik

Dua panel: NDCG@10 dan F1@10 pada K=10, dengan rentang antar titik sebagai
batang error.'''))

cells.append(code('''\
order = ["popularity", "als", f"hybrid_a{SERVING_ALPHA}", "cbf"]
colors = {"popularity": "#c0392b", "als": "#1b61c9",
          f"hybrid_a{SERVING_ALPHA}": "#2c3e50", "cbf": "#7f8c8d"}

fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
for ax, metric in zip(axes, ("ndcg@10", "f1@10")):
    sub = focus[focus.metric == metric].set_index("system").loc[order]
    means = sub["mean"].to_numpy()
    lo = means - sub["min"].to_numpy()
    hi = sub["max"].to_numpy() - means
    ax.bar(range(len(order)), means, color=[colors[s] for s in order],
           yerr=[lo, hi], capsize=4)
    ax.set_title(f"{metric} (mean dan rentang, 9 titik)")
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(["popularity", "als", "hybrid 0.8", "cbf"])
    ax.grid(axis="y", alpha=0.3)

plt.tight_layout()
plt.savefig(REPO / "docs/evidence/phase2/metric_focus.png", dpi=120,
            bbox_inches="tight")
plt.show()
print("grafik -> docs/evidence/phase2/metric_focus.png")'''))

cells.append(md('''\
## 6. Menulis ringkasan markdown

Isi ringkasan dibangkitkan dari angka di atas, jadi tabel di dokumen selalu
sama dengan tabel di notebook.'''))

cells.append(code('''\
def fmt(metric, sys_name):
    r = focus[(focus.metric == metric) & (focus.system == sys_name)].iloc[0]
    return f"{r['mean']:.6f} [{r['min']:.6f}, {r['max']:.6f}]"


ndcg_order = [r["system"] for _, r in
              focus[focus.metric == "ndcg@10"].sort_values("mean", ascending=False).iterrows()]
f1_order = [r["system"] for _, r in
            focus[focus.metric == "f1@10"].sort_values("mean", ascending=False).iterrows()]

lines = []
lines.append("# Evaluasi fokus korpus indo: NDCG@10 dan F1@10")
lines.append("")
lines.append("Empat sistem, sembilan titik sensitivitas, n=600 akun per titik.")
lines.append("Angka dihitung dengan fungsi peringkat dari `src/phase2/evaluate.py`")
lines.append("dan divalidasi silang ke `models/indo_eval.json` pada toleransi 1e-9.")
lines.append("")
lines.append("## Hasil")
lines.append("")
lines.append("| Sistem | NDCG@10 | F1@10 |")
lines.append("|---|---|---|")
for s in ndcg_order:
    lines.append(f"| {s} | {fmt('ndcg@10', s)} | {fmt('f1@10', s)} |")
lines.append("")
lines.append("Urutan NDC@10: " + " > ".join(ndcg_order) + ".")
lines.append("Urutan F1@10: " + " > ".join(f1_order) + ".")
lines.append("")
lines.append("## Kenapa NDCG@10 dan F1@10")
lines.append("")
lines.append("NDCG@10 dipakai sebagai metrik primer karena peka urutan, sudah menjadi")
lines.append("dasar pemilihan alpha di evaluasi resmi, dan standar di literatur sistem")
lines.append("rekomendasi. F1@10 dipakai sebagai pendamping karena menyeimbangkan")
lines.append("precision dan recall pada cutoff yang sama, sehingga sistem tidak tampak")
lines.append("unggul hanya karena menumpuk item populer di posisi atas.")
lines.append("")
lines.append("## Batas kejujuran: F1 di sini menguatkan, bukan menambah")
lines.append("")
lines.append(f"Rasio precision terhadap recall pada K=10 adalah "
             + ", ".join(f"{s} {p/r:.2f}" for s, p, r in
                         [(s,
                           float(np.mean([x['systems'][s]['precision'] for x in results])),
                           float(np.mean([x['systems'][s]['recall'] for x in results])))
                          for s in SYSTEMS]) + ".")
lines.append(f"Sebarannya hanya {spread:.1f}% antar sistem, jadi F1@10 praktis")
lines.append("kelipatan dari recall: urutannya identik dengan urutan precision dan")
lines.append("recall. F1 dilaporkan karena familiar bagi pembaca, bukan karena membawa")
lines.append("informasi ketiga.")
lines.append("")
lines.append("## Batas klaim")
lines.append("")
lines.append("Interaksi korpus ini simulasi view-only, dan proses popularitasnya")
lines.append("didefinisikan oleh generator yang sama. Karena itu popularity berperan")
lines.append("sebagai batas atas, bukan bukti bahwa sistem lain gagal. Protokol resmi")
lines.append("tetap tiga metrik; laporan ini tidak mengubahnya.")

OUT_MD.write_text("\\n".join(lines) + "\\n")
print("markdown ->", OUT_MD)
print()
print("\\n".join(lines[:14]))'''))

cells.append(md('''\
## Reproduksi

```bash
source venv/bin/activate
jupyter nbconvert --to notebook --execute notebooks/eval_metrik_fokus.ipynb --inplace
python -m pytest tests/phase2/test_metric_focus.py -q
```

Sekitar 11 menit kalau cache kosong, di bawah satu menit kalau cache sembilan
titik masih ada di `/tmp`.'''))

nb["cells"] = cells
nb["metadata"] = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "version": "3.12.0"},
}
out = Path(__file__).parent / "eval_metrik_fokus.ipynb"
nbf.write(nb, out)
print("wrote", out, f"({len(cells)} cells)")
