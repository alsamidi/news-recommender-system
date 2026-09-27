"""Recommendation API over frozen full-catalog hybrid inference.

Serving stack: HybridRecommender (src/models/hybrid/infer.py), alpha from
configs/hybrid.yaml (final 0.4, Table B winner). No retraining at serve time.
"""
from pathlib import Path
import sys
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # src/

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from models.hybrid.infer import HybridRecommender, UnknownUserError

app = FastAPI(title="TA News Recommendation API", version="0.2.0")

rec: HybridRecommender | None = None


class RecommendRequest(BaseModel):
    user_id: Optional[str] = None
    history: Optional[List[str]] = None  # session nids (cold: no train history)
    top_k: int = Field(default=10, ge=1, le=100)
    model: str = "hybrid"
    alpha: Optional[float] = None


class ArticleResponse(BaseModel):
    nid: str
    title: Optional[str] = None
    category: Optional[str] = None
    score: float


class RecommendResponse(BaseModel):
    recommendations: List[ArticleResponse]
    model_used: str
    alpha: float
    mode: str  # "warm" | "cold-session"


def get_rec() -> HybridRecommender:
    if rec is None:
        raise HTTPException(503, "recommender not loaded")
    return rec


@app.on_event("startup")
async def startup():
    global rec
    rec = HybridRecommender.load()


@app.get("/health")
async def health():
    r = get_rec()
    return {"status": "ok", "alpha": r.alpha,
            "catalog_size": len(r._d["full_nids"]),
            "als_items": len(r._d["item_map"])}


@app.post("/recommend", response_model=RecommendResponse)
async def recommend(req: RecommendRequest):
    r = get_rec()
    if req.model != "hybrid":
        raise HTTPException(400, "only model='hybrid' is served")
    try:
        if req.user_id:
            out = r.recommend_user(req.user_id, top_k=req.top_k, alpha=req.alpha)
            mode = "warm"
        elif req.history:
            out = r.recommend_session(req.history, top_k=req.top_k, alpha=req.alpha)
            mode = "cold-session"
        else:
            raise HTTPException(400, "pass user_id (warm) or history nids (cold session)")
    except UnknownUserError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    alpha = req.alpha if req.alpha is not None else r.alpha
    return RecommendResponse(
        recommendations=[ArticleResponse(**a) for a in out],
        model_used="hybrid", alpha=float(alpha), mode=mode)


@app.get("/similar/{nid}")
async def similar(nid: str, top_k: int = 10):
    r = get_rec()
    try:
        return {"nid": nid, "similar": r.similar(nid, top_k=top_k)}
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.get("/article/{nid}")
async def article(nid: str):
    r = get_rec()
    try:
        return r.article(nid)
    except KeyError as e:
        raise HTTPException(404, str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
