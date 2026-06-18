from __future__ import annotations

import os
from dataclasses import asdict

from fastapi import FastAPI

from nihaixia_core.retrieval import search_with_info
from nihaixia_core.text import classify_domain

app = FastAPI(title="Ni Haixia System API", version="0.1.0")


@app.get("/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/search")
def search_sources(payload: dict) -> dict:
    question = str(payload.get("question") or "")
    domain = str(payload.get("domain") or "auto")
    top_k = int(payload.get("top_k") or 5)
    mode = str(payload.get("mode") or "auto")
    db = os.getenv("NIHAIXIA_DB", "data/nihaixia.sqlite")
    results, info = search_with_info(question, db, domain=domain, top_k=top_k, mode=mode)
    return {"retrieval": info, "results": [asdict(item) for item in results]}


@app.post("/v1/classify")
def classify(payload: dict) -> dict:
    return {"domain": classify_domain(str(payload.get("question") or ""))}
