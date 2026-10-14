"""Encode 93.698 news -> IndoBERT embeddings (Eksperimen 2).

Input  : data/processed/news_processed.parquet (row order dipertahankan)
Teks   : title + abstract MENTAH (bukan processed_text; stemming merusak subword)
Model  : firqaaa/indo-sentence-bert-base (IndoBERT sentence-transformers, mean pooling bawaan)
Output : models/indobert_embeddings.npy (float32, L2-normalized, baris sejajar parquet)
         models/indobert_meta.json (nama model, dim, count, verifikasi norm)
Resume : checkpoint partial tiap chunk -> aman untuk run CPU panjang.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

MODEL_NAME = "firqaaa/indo-sentence-bert-base"
CHUNK = 4096


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--model", default=MODEL_NAME)
    args = ap.parse_args()

    from sentence_transformers import SentenceTransformer

    df = pd.read_parquet("data/processed/news_processed.parquet").reset_index(drop=True)
    texts = (df["title"].fillna("") + " " + df["abstract"].fillna("")).str.strip().tolist()
    assert len(texts) == len(df) and all(t for t in texts), "ada teks kosong"
    print(f"news: {len(texts)}, model: {args.model}")

    model = SentenceTransformer(args.model, device="cpu")
    dim = model.get_sentence_embedding_dimension()
    print(f"dim: {dim}")

    ckpt = Path("models/indobert_embeddings.partial.npy")
    done = 0
    if ckpt.exists():
        done = int(np.load(str(ckpt), mmap_mode="r").shape[0])
        print(f"resume dari checkpoint: {done}/{len(texts)}")

    out = np.zeros((len(texts), dim), dtype=np.float32)
    if done:
        out[:done] = np.load(str(ckpt))
    for s in range(done, len(texts), CHUNK):
        e = s + min(CHUNK, len(texts) - s)
        emb = model.encode(
            texts[s:e], batch_size=args.batch_size, show_progress_bar=True,
            convert_to_numpy=True, normalize_embeddings=True,
        ).astype(np.float32)
        out[s:e] = emb
        np.save(str(ckpt), out[:e])  # checkpoint progresif
        print(f"chunk {s}:{e} tersimpan", flush=True)

    assert out.shape == (len(texts), dim)
    norms = np.linalg.norm(out, axis=1)
    print(f"norm mean={norms.mean():.4f} min={norms.min():.4f} max={norms.max():.4f}")
    assert np.allclose(norms, 1.0, atol=1e-3), "embedding tidak ternormalisasi"

    np.save("models/indobert_embeddings.npy", out)
    ckpt.unlink(missing_ok=True)
    meta = {"model": args.model, "n_news": len(texts), "dim": int(dim),
            "dtype": "float32", "l2_normalized": True,
            "row_order": "sejajar data/processed/news_processed.parquet (reset_index)",
            "text_source": "title + abstract MENTAH (bukan processed_text)",
            "size_MB": round(out.nbytes / 1e6, 1)}
    Path("models/indobert_meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
