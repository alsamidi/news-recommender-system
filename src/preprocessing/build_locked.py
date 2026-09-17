"""Build locked dataset: news_processed.parquet + interactions.parquet.

Reads (per DATASET_LOCK.md):
  MINDsmall_{train,dev}/behaviors.tsv  -> interactions (klik impression label=1)
  MINDsmall_{train,dev}/news.tsv       -> category/subcategory via nid
  xMINDsmall_{train,dev}/news.tsv      -> title/abstract Indonesia via nid
Writes:
  data/processed/news_processed.parquet   (nid, title, abstract, processed_text, category, split)
  data/processed/interactions_train.parquet (user_id, nid, weight, time)
  data/processed/interactions_dev.parquet   (same, eval only)
"""
import signal
import yaml
from multiprocessing import Pool
from pathlib import Path
import pandas as pd

from src.preprocessing.run import IndonesianPreprocessor

BASE = Path(__file__).resolve().parents[2]
MIND_COLS = ["nid", "category", "subcategory", "title_en", "abstract_en",
             "url", "title_entities", "abstract_entities"]
STEM_TIMEOUT = 0.3  # detik per kata. Kata Indonesia valid selesai <0.2 dtk;
# yang lewat dari ini = nama asing/garbage yang hasil akhirnya pun kata asli
# (terverifikasi: joanie->joanie, phoenix->phoenix, chengdu->chengdu).

_PREP = None


class _StemTimeout(Exception):
    pass


def _alarm_handler(signum, frame):
    raise _StemTimeout()


def _init_prep(stopwords_path: str, alay_dict_path: str, min_len: int,
               max_len: int, rm_num: bool, rm_punct: bool):
    global _PREP
    _PREP = IndonesianPreprocessor(
        stopwords_path=stopwords_path, alay_dict_path=alay_dict_path,
        min_token_len=min_len, max_token_len=max_len,
        remove_numbers=rm_num, remove_punct=rm_punct,
    )


def _process_one(text: str) -> str:
    return _PREP.process(text)


def _clean_only(text: str) -> str:
    return _PREP.clean_text(text)


def _stem_word(word: str) -> str:
    signal.signal(signal.SIGALRM, _alarm_handler)
    signal.setitimer(signal.ITIMER_REAL, STEM_TIMEOUT)
    try:
        return _PREP.stem(word)
    except _StemTimeout:
        return word  # token patologis: biarkan apa adanya (nanti terfilter bila >50 char)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def load_news(split: str) -> pd.DataFrame:
    x = pd.read_csv(BASE / f"xMINDsmall_{split}/news.tsv", sep="\t")
    m = pd.read_csv(BASE / f"MINDsmall_{split}/news.tsv", sep="\t",
                    header=None, names=MIND_COLS, usecols=["nid", "category", "subcategory"])
    df = x.merge(m, on="nid", how="left")
    df["split"] = split
    return df


def build_interactions(split: str) -> pd.DataFrame:
    b = pd.read_csv(BASE / f"MINDsmall_{split}/behaviors.tsv", sep="\t",
                    header=None, names=["imp", "user_id", "time", "hist", "impr"])
    rows = []
    for _, r in b.iterrows():
        t = pd.to_datetime(r["time"])
        for tok in str(r["impr"]).split():
            nid, label = tok.rsplit("-", 1)
            if label == "1":
                rows.append((r["user_id"], nid, t))
    df = pd.DataFrame(rows, columns=["user_id", "nid", "time"])
    df = df.groupby(["user_id", "nid"], as_index=False).agg(
        weight=("nid", "size"), time=("time", "min"))
    return df


def main():
    cfg = yaml.safe_load(open(BASE / "configs/preprocessing.yaml"))
    news = pd.concat([load_news("train"), load_news("dev")], ignore_index=True)
    raw = (news["title"].fillna("") + " " + news["abstract"].fillna("")).str.strip()
    n_workers = cfg.get("num_workers", 8)
    args = (str(BASE / cfg.get("stopwords_path", "")), str(BASE / cfg.get("alay_dict_path", "")),
            cfg.get("min_token_length", 2), cfg.get("max_token_length", 50),
            cfg.get("remove_numbers", True), cfg.get("remove_punctuation", True))
    # Fase 1: clean (paralel) — regex per dokumen
    with Pool(n_workers, initializer=_init_prep, initargs=args) as pool:
        cleaned = pool.map(_clean_only, raw.tolist(), chunksize=500)
    # Fase 2: stem tiap kata unik sekali (paralel), bukan ulang per dokumen
    vocab = sorted({w for t in cleaned for w in t.split()})
    print(f"vocab unik: {len(vocab)} kata", flush=True)
    # Hanya kata murni (huruf saja, <=50 char) yang di-stem; sisanya (angka,
    # simbol, campuran) dilewatkan apa adanya — sama dengan hasil timeout guard,
    # tapi instan. Kata murni = jalur cepat Sastrawi.
    import re as _re
    _alpha = _re.compile(r"^[a-z]+$")
    max_len = cfg.get("max_token_length", 50)
    to_stem = [w for w in vocab if _alpha.match(w) and len(w) <= max_len]
    to_stem_set = set(to_stem)
    stem_map = {w: w for w in vocab if w not in to_stem_set}
    print(f"perlu stem: {len(to_stem)}, lewat langsung: {len(stem_map)}", flush=True)
    stemmed_list = [None] * len(to_stem)
    import random as _random
    order = list(range(len(to_stem)))
    _random.Random(42).shuffle(order)  # sebar kata lambat merata, cegah head stall
    shuffled = [to_stem[i] for i in order]
    stemmed_shuffled = [None] * len(to_stem)
    with Pool(n_workers, initializer=_init_prep, initargs=args) as pool:
        done = 0
        for i, s in enumerate(pool.imap(_stem_word, shuffled, chunksize=200)):
            stemmed_shuffled[i] = s
            done += 1
            if done % 5000 == 0:
                print(f"stemmed {done}/{len(to_stem)}", flush=True)
    for i, idx in enumerate(order):
        stemmed_list[idx] = stemmed_shuffled[i]
    stem_map.update(dict(zip(to_stem, stemmed_list)))
    print("stem selesai, rakit dokumen...", flush=True)
    # Fase 3: rakit per dokumen (cepat, operasi string saja)
    main_prep = IndonesianPreprocessor(
        stopwords_path=args[0], alay_dict_path=args[1], min_token_len=args[2],
        max_token_len=args[3], remove_numbers=args[4], remove_punct=args[5])
    out_texts = []
    for t in cleaned:
        s = " ".join(stem_map[w] for w in t.split())
        s = main_prep.remove_stopwords(s)
        toks = main_prep.filter_tokens(main_prep.tokenize(s))
        out_texts.append(" ".join(toks))
    news["processed_text"] = out_texts
    out = BASE / "data/processed"
    out.mkdir(parents=True, exist_ok=True)
    news[["nid", "title", "abstract", "processed_text",
          "category", "subcategory", "split"]].to_parquet(out / "news_processed.parquet", index=False)
    print(f"news_processed: {len(news)} rows "
          f"(train={(news['split'] == 'train').sum()}, dev={(news['split'] == 'dev').sum()})")

    for split in ["train", "dev"]:
        inter = build_interactions(split)
        inter.to_parquet(out / f"interactions_{split}.parquet", index=False)
        print(f"interactions_{split}: {len(inter)} pairs, "
              f"users={inter['user_id'].nunique()}, items={inter['nid'].nunique()}")


if __name__ == "__main__":
    main()
