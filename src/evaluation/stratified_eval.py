"""Stratified evaluation: warm users vs cold users (Day 4+).

Pertanyaan yang dijawab (untuk Bab IV): dalam kondisi informasi user
tersedia vs tidak tersedia, perilaku sistem berubah bagaimana?

Tabel C (warm)  = user dengan >=1 interaksi train. Kandidat full catalog,
                  mask train, profil = mean TF-IDF item train (identik
                  protokol Table B di full_catalog_eval.py).
Tabel D (cold)  = user TANPA history train. Tidak ada user factor ALS ->
                  CF asli mustahil; protokol session-based leave-last-out
                  dalam dev: klik dev diurutkan waktu, history = semua
                  kecuali terakhir, relevant = klik terakhir. CF di-proxy
                  oleh pseudo-user (mean item factors item session yang
                  ada di ALS); popularity = fallback non-personalized.
                  Hybrid = alpha*content + (1-alpha)*cf_pseudo, full
                  catalog, mask session history.

Metric formulas, min-max per user, dan top-k selection diimpor verbatim
dari full_catalog_eval.py (frozen day-4 evaluator) agar parity terjaga.
"""
import numpy as np

try:  # dipanggil sebagai module (tests) atau sebagai script (python src/evaluation/...)
    from evaluation.full_catalog_eval import (
        _metrics_at_ks,
        _minmax,
        _topk_sorted,
        expand_cf_scores,
        load_all,
        precompute_user_scores,
        seeded_sample,
    )
except ImportError:
    from full_catalog_eval import (
        _metrics_at_ks,
        _minmax,
        _topk_sorted,
        expand_cf_scores,
        load_all,
        precompute_user_scores,
        seeded_sample,
    )

K_VALUES = [10]
WARM_ALPHAS = [0.0, 0.4, 0.8, 1.0]
COLD_ALPHAS = [0.0, 0.4, 0.8, 1.0]
SEED = 42
MAX_USERS = 2000


def split_session(nids_chronological: list):
    """Leave-last-out: (history, relevant). None jika <2 klik."""
    if len(nids_chronological) < 2:
        return None
    return nids_chronological[:-1], nids_chronological[-1]


def pseudo_user_factor(session_nids: list, item_map: dict, item_factors: np.ndarray):
    """Mean ALS item factors dari item session yang ada di ALS. None jika kosong."""
    rows = [item_map[n] for n in session_nids if n in item_map]
    if not rows:
        return None
    return item_factors[rows].mean(axis=0)


def popularity_full_vector(train_counts: dict, nid_to_full: dict, n_full: int) -> np.ndarray:
    """Vektor popularitas train di indeks full-catalog (item di luar katalog diabaikan)."""
    v = np.zeros(n_full, dtype=np.float64)
    for nid, c in train_counts.items():
        f = nid_to_full.get(nid)
        if f is not None:
            v[f] = c
    return v


def _aggregate(eval_users: list, per_user: dict, n_candidates: int) -> list:
    """Rata-ratakan metrik per user -> satu baris per method/alpha."""
    rows = []
    methods = sorted({k for method_map in per_user.values() for k in method_map})
    for method, alpha in methods:
        acc = {f"{m}@{k}": [] for m in ("precision", "recall", "map", "ndcg") for k in K_VALUES}
        rec_union, hit_users, n_eval = set(), 0, 0
        for uid in eval_users:
            m_alpha = per_user[uid].get((method, alpha))
            if m_alpha is None:
                continue
            rec, rel = m_alpha
            n_eval += 1
            rec10 = rec[:10]
            rec_union.update(rec10)
            if set(rec10) & rel:
                hit_users += 1
            for k_, v_ in _metrics_at_ks(rec, rel, K_VALUES).items():
                acc[k_].append(v_)
        row = {"method": method, "alpha": alpha, "n_eval": n_eval,
               "coverage@10": len(rec_union) / n_candidates,
               "distinct_items@10": len(rec_union),
               "hit_rate@10": (hit_users / n_eval) if n_eval else 0.0}
        for m_, vs_ in acc.items():
            row[m_] = float(np.mean(vs_)) if vs_ else 0.0
        rows.append(row)
    return rows


def sweep_warm(eval_users: list, data: dict, scores: dict) -> list:
    """Warm: full catalog, mask train. CF=alpha 0, content=alpha 1, hybrid di antaranya."""
    n_full = len(data["full_nids"])
    als_pos = data["als_full_pos"]
    train_full, dev_full = data["train_full"], data["dev_full"]
    kmax = 20
    per_user = {}
    for uid in eval_users:
        ti = train_full[uid]
        rel = dev_full[uid] - ti
        if not rel:
            continue
        c_norm, cf_norm = scores[uid]
        # unknown slot = 0.0 (bukan -inf): item di luar ALS masih bisa diranking
        # via content; hanya pure CF (alpha=0) yang mengisi -inf (lihat bawah).
        cf_full = np.zeros(n_full, dtype=np.float64)
        cf_full[als_pos] = cf_norm
        per_user[uid] = {}
        for alpha in WARM_ALPHAS:
            if alpha == 0.0:  # pure CF: unknown item -inf (identik Table B alpha 0)
                s = expand_cf_scores(cf_norm, als_pos, n_full, 0.0)
            else:
                s = alpha * c_norm + (1 - alpha) * cf_full
            s = s.copy()
            s[list(ti)] = -np.inf
            rec = _topk_sorted(s, kmax)
            per_user[uid][(METHOD_WARM_HYBRID if 0.0 < alpha < 1.0 else
                           METHOD_CF if alpha == 0.0 else METHOD_CONTENT, alpha)] = (rec, rel)
    return _aggregate(eval_users, per_user, n_full)


METHOD_CF = "cf"
METHOD_CONTENT = "content"
METHOD_WARM_HYBRID = "hybrid"
METHOD_POPULARITY = "popularity"
METHOD_COLD_HYBRID = "hybrid_pseudo_cf"


def sweep_cold(cold_sessions: dict, data: dict, pop_vec: np.ndarray) -> list:
    """Cold: session leave-last-out dalam dev. Return baris per method."""
    n_full = len(data["full_nids"])
    als_pos = data["als_full_pos"]
    item_map, itf = data["item_map"], data["item_factors"]
    full_tfidf = data["full_tfidf"]
    kmax = 20
    per_user = {}
    n_no_cf, n_no_pseudo = 0, 0
    for uid, (hist, rel_nid) in cold_sessions.items():
        hist = list(hist)
        if not hist or rel_nid not in data["nid_to_full"]:
            continue
        rel = {data["nid_to_full"][rel_nid]}
        ti = {data["nid_to_full"][n] for n in hist if n in data["nid_to_full"]}
        rel -= ti

        # Content: profil TF-IDF dari history session
        ti_sorted = sorted(ti)
        if not ti_sorted:
            continue
        prof = full_tfidf[ti_sorted].mean(axis=0)
        c_norm = _minmax(np.asarray(prof @ full_tfidf.T).ravel()).astype(np.float32)

        # CF proxy: pseudo-user factor (fallback popularity saat tak ada item ALS)
        pu = pseudo_user_factor(hist, item_map, itf)
        cf_full = None
        if pu is not None:
            cf_raw = pu @ itf.T
            cf_known = _minmax(cf_raw).astype(np.float32)
            # unknown slot = 0.0 (BUKAN -inf): item non-ALS tetap bisa diranking
            # via content; -inf hanya membuat hybrid cold = ALS-space saja.
            cf_full = np.zeros(n_full, dtype=np.float64)
            cf_full[als_pos] = cf_known
        else:
            n_no_pseudo += 1

        per_user[uid] = {}
        rec = _topk_sorted(_mask(pop_vec.copy(), ti), kmax)
        per_user[uid][(METHOD_POPULARITY, None)] = (rec, rel)

        rec = _topk_sorted(_mask(c_norm.astype(np.float64).copy(), ti), kmax)
        per_user[uid][(METHOD_CONTENT, 1.0)] = (rec, rel)

        for alpha in COLD_ALPHAS:
            if cf_full is None:
                n_no_cf += 1
                continue
            s = alpha * c_norm + (1 - alpha) * cf_full
            s = _mask(s, ti)
            per_user[uid][(METHOD_COLD_HYBRID, alpha)] = (_topk_sorted(s, kmax), rel)
    rows = _aggregate(list(cold_sessions), per_user, n_full)
    for r in rows:
        r["note"] = f"users_without_pseudo_cf={n_no_pseudo}"
    return rows


def _mask(s: np.ndarray, ti: set) -> np.ndarray:
    s = np.asarray(s, dtype=np.float64).copy()
    s[list(ti)] = -np.inf
    return s


def main():
    import json
    import pandas as pd

    print("loading...", flush=True)
    data = load_all()

    # ---- Warm (Table C) ----
    eligible = [u for u in data["train_full"]
                if u in data["dev_full"] and (data["dev_full"][u] - data["train_full"][u])]
    eval_users = seeded_sample(sorted(eligible), MAX_USERS, seed=SEED)
    print(f"warm eligible={len(eligible)}, sampled={len(eval_users)}", flush=True)
    scores = precompute_user_scores(eval_users, data)
    warm_rows = sweep_warm(eval_users, data, scores)
    for r in warm_rows:
        print(f"  C {r['method']:9s} a={str(r['alpha']):4s} ndcg@10={r['ndcg@10']:.5f} "
              f"map@10={r['map@10']:.5f} hit@10={r['hit_rate@10']:.4f} cov@10={r['coverage@10']:.4f}",
              flush=True)

    # ---- Cold (Table D): session leave-last-out dalam dev ----
    dv = pd.read_parquet("data/processed/interactions_dev.parquet")
    dev_all_users = set(dv["user_id"].unique())
    cold_ids = sorted(dev_all_users - set(data["user_map"]))
    print(f"cold users (no train history): {len(cold_ids)}", flush=True)
    dv_cold = dv[dv["user_id"].isin(cold_ids)].sort_values(["user_id", "time"])
    sessions = dv_cold.groupby("user_id")["nid"].apply(list).to_dict()
    cold_sessions = {}
    for uid, nids in sessions.items():
        sp = split_session(nids)
        if sp is not None:
            cold_sessions[uid] = sp
    print(f"cold sessions usable (>=2 klik dev): {len(cold_sessions)}", flush=True)
    cold_sample = seeded_sample(sorted(cold_sessions), MAX_USERS, seed=SEED)

    tr_counts = pd.read_parquet("data/processed/interactions_train.parquet")
    pop_vec = popularity_full_vector(
        tr_counts["nid"].value_counts().to_dict(), data["nid_to_full"], len(data["full_nids"]))
    cold_rows = sweep_cold({u: cold_sessions[u] for u in cold_sample}, data, pop_vec)
    for r in cold_rows:
        print(f"  D {r['method']:16s} a={str(r['alpha']):4s} ndcg@10={r['ndcg@10']:.5f} "
              f"map@10={r['map@10']:.5f} hit@10={r['hit_rate@10']:.4f} cov@10={r['coverage@10']:.4f}",
              flush=True)

    out = {
        "meta": {
            "seed": SEED, "max_users": MAX_USERS, "k_values": K_VALUES,
            "n_catalog_full": len(data["full_nids"]),
            "warm_protocol": "identik Table B full_catalog_eval: full catalog, mask train, profil mean TF-IDF train",
            "warm_sampled": len(eval_users), "warm_eligible": len(eligible),
            "cold_protocol": ("user tanpa interaksi train; session leave-last-out dalam dev "
                              "(klik diurut waktu, history = semua kecuali terakhir, relevant = terakhir); "
                              "profil TF-IDF dari history session; CF diproksi pseudo-user factor "
                              "(mean item factors ALS item session), fallback popularity; "
                              "hybrid = alpha*content + (1-alpha)*cf_pseudo, full catalog, mask session"),
            "cold_sampled": len(cold_sample),
            "cold_usable_sessions": len(cold_sessions),
            "leakage_guard": "vectorizer frozen; cold user tidak punya user factor ALS (tidak pernah lihat data train)",
        },
        "table_c_warm": warm_rows,
        "table_d_cold": cold_rows,
    }
    with open("models/stratified_eval.json", "w") as f:
        json.dump(out, f, indent=2)

    lines = ["# Stratified evaluation: warm vs cold users", "",
             f"seed={SEED}, warm sampled={len(eval_users)}/{len(eligible)} eligible, "
             f"cold sampled={len(cold_sample)}/{len(cold_sessions)} usable sessions", ""]
    for title, rows in (("Table C — Warm users (ada history train, full catalog)", warm_rows),
                        ("Table D — Cold users (tanpa history train, session leave-last-out)", cold_rows)):
        lines += [f"## {title}", "",
                  "| method | alpha | NDCG@10 | MAP@10 | hit@10 | cov@10 | n |",
                  "|---|---:|---:|---:|---:|---:|---:|"]
        for r in rows:
            lines.append(
                f"| {r['method']} | {r['alpha'] if r['alpha'] is not None else '—'} | "
                f"{r['ndcg@10']:.5f} | {r['map@10']:.5f} | {r['hit_rate@10']:.4f} | "
                f"{r['coverage@10']:.4f} | {r['n_eval']} |")
        lines.append("")
    with open("models/stratified_tables.md", "w") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote models/stratified_eval.json + models/stratified_tables.md", flush=True)


if __name__ == "__main__":
    main()
