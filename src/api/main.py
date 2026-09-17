"""
FastAPI Server for News Recommendation
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import pickle
import json
import numpy as np
from pathlib import Path
from sklearn.metrics.pairwise import cosine_similarity


app = FastAPI(title="TA News Recommendation API", version="0.1.0")


class RecommendRequest(BaseModel):
    user_id: Optional[str] = None
    article_id: Optional[str] = None
    top_k: int = 10
    model: str = "hybrid"  # tfidf, als, hybrid


class ArticleResponse(BaseModel):
    article_id: str
    score: float
    title: Optional[str] = None
    category: Optional[str] = None


class RecommendResponse(BaseModel):
    recommendations: List[ArticleResponse]
    model_used: str


models = {}


def load_models():
    model_dir = Path("models")
    if not model_dir.exists():
        return

    # Load TF-IDF
    tfidf_path = model_dir / "tfidf_baseline.pkl"
    if tfidf_path.exists():
        with open(tfidf_path, "rb") as f:
            models["tfidf"] = pickle.load(f)
        models["tfidf_embeddings"] = np.load(model_dir / "tfidf_embeddings.npy")

    # Load ALS
    als_path = model_dir / "als_model.pkl"
    if als_path.exists():
        with open(als_path, "rb") as f:
            models["als"] = pickle.load(f)
        models["als_user_factors"] = np.load(model_dir / "als_user_factors.npy")
        models["als_item_factors"] = np.load(model_dir / "als_item_factors.npy")

    # Load Hybrid
    hybrid_path = model_dir / "weighted_hybrid.pkl"
    if hybrid_path.exists():
        with open(hybrid_path, "rb") as f:
            models["hybrid"] = pickle.load(f)


@app.on_event("startup")
async def startup():
    load_models()


@app.get("/health")
async def health():
    return {"status": "ok", "models_loaded": list(models.keys())}


@app.post("/recommend", response_model=RecommendResponse)
async def recommend(req: RecommendRequest):
    if req.model not in models:
        raise HTTPException(400, f"Model '{req.model}' not loaded. Available: {list(models.keys())}")

    recommendations = []

    if req.model == "tfidf" and req.article_id:
        # Content-based: similar articles
        artifact = models["tfidf"]
        vectorizer = artifact["vectorizer"]
        train_matrix = artifact["train_matrix"]
        embeddings = models["tfidf_embeddings"]
        item_map = artifact.get("item_map", {})
        inv_item_map = {v: k for k, v in item_map.items()}

        if req.article_id not in item_map:
            raise HTTPException(404, f"Article {req.article_id} not found")

        idx = item_map[req.article_id]
        query_emb = embeddings[idx:idx+1]
        sims = cosine_similarity(query_emb, embeddings)[0]
        top_indices = np.argsort(-sims)[1:req.top_k+1]  # exclude self

        for idx in top_indices:
            recommendations.append(ArticleResponse(
                article_id=inv_item_map.get(idx, str(idx)),
                score=float(sims[idx])
            ))

    elif req.model == "als" and req.user_id:
        artifact = models["als"]
        model = artifact["model"]
        user_map = artifact["user_map"]
        item_map = artifact["item_map"]
        inv_item_map = {v: k for k, v in item_map.items()}

        if req.user_id not in user_map:
            raise HTTPException(404, f"User {req.user_id} not found")

        u_idx = user_map[req.user_id]
        rec_ids, scores = model.recommend(u_idx, None, N=req.top_k)
        for idx, score in zip(rec_ids, scores):
            recommendations.append(ArticleResponse(
                article_id=inv_item_map.get(idx, str(idx)),
                score=float(score)
            ))

    elif req.model == "hybrid" and req.user_id:
        artifact = models["hybrid"]
        alpha = artifact["content_weight"]

        # Load component models
        tfidf_artifact = models["tfidf"]
        als_artifact = models["als"]

        user_map = als_artifact["user_map"]
        item_map = als_artifact["item_map"]
        inv_item_map = {v: k for k, v in item_map.items()}

        if req.user_id not in user_map:
            raise HTTPException(404, f"User {req.user_id} not found")

        u_idx = user_map[req.user_id]

        # CF scores
        user_factors = models["als_user_factors"]
        item_factors = models["als_item_factors"]
        cf_scores = user_factors[u_idx] @ item_factors.T

        # Content scores (simplified: use item factors as proxy)
        # In practice, would need user's historical items to compute content boost
        hybrid_scores = (1 - alpha) * cf_scores  # content component requires history

        top_indices = np.argsort(-hybrid_scores)[:req.top_k]

        for idx in top_indices:
            recommendations.append(ArticleResponse(
                article_id=inv_item_map.get(idx, str(idx)),
                score=float(hybrid_scores[idx])
            ))

    return RecommendResponse(recommendations=recommendations, model_used=req.model)


@app.get("/similar/{article_id}")
async def similar_articles(article_id: str, top_k: int = 10):
    """Content-based similar articles using TF-IDF"""
    if "tfidf" not in models:
        raise HTTPException(503, "TF-IDF model not loaded")

    artifact = models["tfidf"]
    item_map = artifact.get("item_map", {})
    inv_item_map = {v: k for k, v in item_map.items()}
    embeddings = models["tfidf_embeddings"]

    if article_id not in item_map:
        raise HTTPException(404, f"Article {article_id} not found")

    idx = item_map[article_id]
    query_emb = embeddings[idx:idx+1]
    sims = cosine_similarity(query_emb, embeddings)[0]
    top_indices = np.argsort(-sims)[1:top_k+1]

    similar = []
    for idx in top_indices:
        similar.append({
            "article_id": inv_item_map.get(idx, str(idx)),
            "score": float(sims[idx])
        })

    return {"article_id": article_id, "similar": similar}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)