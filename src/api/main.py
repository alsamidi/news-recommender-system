"""Recommendation API over frozen full-catalog hybrid inference (contract v1.0.0).

Serving stack: HybridRecommender (src/models/hybrid/infer.py), alpha fixed at
the serving value from configs/hybrid.yaml (final 0.4, Table B winner).
No retraining at serve time. No per-request alpha override: served results
always match the evaluated configuration.
"""
from contextlib import asynccontextmanager
from pathlib import Path
import sys
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # src/

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from models.hybrid.infer import HybridRecommender, UnknownUserError

templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent / "templates"))

rec: HybridRecommender | None = None
demo_presets: dict | None = None


def resolve_presets(data: dict) -> dict:
    """Deterministic demo fixtures from frozen artifacts (P3.2).

    Same selection rule as scripts/smoke_demo.sh: first eligible warm user,
    first usable cold session (with pseudo-CF), first catalog nids outside
    ALS space (content-only fallback case).
    """
    import pandas as pd

    elig = sorted(u for u in data["train_full"]
                  if u in data["dev_full"] and (data["dev_full"][u] - data["train_full"][u]))
    dv = pd.read_parquet("data/processed/interactions_dev.parquet")
    dv = dv.sort_values(["user_id", "time"])
    cold = dv[~dv["user_id"].isin(set(data["user_map"]))]
    sess = next(nids[:-1] for _, g in cold.groupby("user_id")
                for nids in [g["nid"].tolist()]
                if len(nids) >= 2 and nids[-1] in data["nid_to_full"]
                and any(n in data["item_map"] for n in nids[:-1]))
    noals = [n for n in data["full_nids"] if n not in data["item_map"]][:3]
    return {"warm_user": elig[0], "cold_session": sess, "fallback_session": noals}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global rec, demo_presets
    rec = HybridRecommender.load()
    demo_presets = resolve_presets(rec._d)
    yield
    rec = None
    demo_presets = None


app = FastAPI(title="TA News Recommendation API", version="1.0.0",
              lifespan=lifespan)


class RecommendRequest(BaseModel):
    user_id: Optional[str] = None
    history: Optional[List[str]] = None  # session nids (cold: no train history)
    top_k: int = Field(default=10, ge=1, le=100)
    model: str = "hybrid"


class ArticleResponse(BaseModel):
    nid: str
    title: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    score: float


class RecommendResponse(BaseModel):
    recommendations: List[ArticleResponse]
    model_used: str
    alpha: float
    mode: str  # "warm" | "cold-session"


class HealthResponse(BaseModel):
    status: str
    alpha: float
    catalog_size: int
    als_items: int


class SimilarResponse(BaseModel):
    nid: str
    similar: List[ArticleResponse]


class ArticleDetailResponse(BaseModel):
    nid: str
    title: Optional[str] = None
    abstract: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None


def get_rec() -> HybridRecommender:
    if rec is None:
        raise HTTPException(503, "recommender not loaded")
    return rec


@app.get("/health", response_model=HealthResponse)
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
    if req.user_id and req.history:
        raise HTTPException(400, "pass exactly one of user_id (warm) or history (cold session)")
    try:
        if req.user_id:
            out = r.recommend_user(req.user_id, top_k=req.top_k)
            mode = "warm"
        elif req.history:
            out = r.recommend_session(req.history, top_k=req.top_k)
            mode = "cold-session"
        else:
            raise HTTPException(400, "pass user_id (warm) or history nids (cold session)")
    except UnknownUserError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RecommendResponse(
        recommendations=[ArticleResponse(**a) for a in out],
        model_used="hybrid", alpha=r.alpha, mode=mode)


@app.get("/similar/{nid}", response_model=SimilarResponse)
async def similar(nid: str, top_k: int = Query(default=10, ge=1, le=100)):
    r = get_rec()
    try:
        return {"nid": nid, "similar": r.similar(nid, top_k=top_k)}
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.get("/article/{nid}", response_model=ArticleDetailResponse)
async def article(nid: str):
    r = get_rec()
    try:
        return r.article(nid)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def demo_ui(request: Request):
    """Demo viewer (P3.2). Explicitly outside the versioned API contract:
    thin page over /recommend, presets injected from frozen artifacts."""
    r = get_rec()
    if demo_presets is None:
        raise HTTPException(503, "demo presets not resolved")
    import json
    return templates.TemplateResponse(request, "demo.html", {
        "alpha": r.alpha,
        "catalog_size": len(r._d["full_nids"]),
        "presets": demo_presets,
        "presets_json": json.dumps(demo_presets),
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
