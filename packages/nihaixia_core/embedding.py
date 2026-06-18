from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from math import sqrt
from typing import Any

from .env import load_default_env


@dataclass(frozen=True, slots=True)
class EmbeddingConfig:
    provider: str
    base_url: str
    api_key: str
    model: str
    dim: int | None = None


def load_embedding_config() -> EmbeddingConfig:
    load_default_env()
    dim_raw = os.getenv("EMBEDDING_DIM", "").strip()
    return EmbeddingConfig(
        provider=os.getenv("EMBEDDING_PROVIDER", "").strip() or "openai_compatible",
        base_url=os.getenv("EMBEDDING_BASE_URL", "").strip(),
        api_key=os.getenv("EMBEDDING_API_KEY", "").strip(),
        model=os.getenv("EMBEDDING_MODEL", "").strip(),
        dim=int(dim_raw) if dim_raw.isdigit() else None,
    )


def is_configured(config: EmbeddingConfig | None = None) -> bool:
    config = config or load_embedding_config()
    return bool(config.base_url and config.api_key and config.model)


def embed_texts(texts: list[str], config: EmbeddingConfig | None = None) -> list[list[float]]:
    config = config or load_embedding_config()
    if not is_configured(config):
        raise RuntimeError("Embedding API is not configured.")
    if config.provider != "openai_compatible":
        raise RuntimeError(f"Unsupported embedding provider: {config.provider}")

    endpoint, payload_data = build_embedding_request(texts, config)
    payload = json.dumps(payload_data, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = safe_error_detail(exc.read().decode("utf-8", errors="replace"), config)
        raise RuntimeError(f"Embedding request failed: HTTP {exc.code} {detail}") from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Embedding request failed: {type(exc).__name__}") from exc

    items = normalize_embedding_items(data)
    ordered = sorted(items, key=lambda item: int(item.get("index", 0)) if isinstance(item, dict) else 0)
    vectors: list[list[float]] = []
    for item in ordered:
        embedding = item.get("embedding") if isinstance(item, dict) else None
        if not isinstance(embedding, list):
            raise RuntimeError("Embedding response item missing embedding.")
        vectors.append(postprocess_vector([float(value) for value in embedding], config))
    return vectors


def build_embedding_request(texts: list[str], config: EmbeddingConfig) -> tuple[str, dict[str, Any]]:
    base_url = config.base_url.rstrip("/")
    if "vision" in config.model:
        payload: dict[str, Any] = {
            "model": config.model,
            "input": [{"type": "text", "text": text} for text in texts],
            "encoding_format": "float",
        }
        if config.dim in {1024, 2048}:
            payload["dimensions"] = config.dim
        return base_url + "/embeddings/multimodal", payload

    return base_url + "/embeddings", {
        "model": config.model,
        "input": texts,
        "encoding_format": "float",
    }


def normalize_embedding_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    items = data.get("data")
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    if isinstance(items, dict):
        return [{"index": 0, "embedding": items.get("embedding")}]
    raise RuntimeError("Embedding response missing data.")


def sanitize_config_for_report(config: EmbeddingConfig | None = None) -> dict[str, Any]:
    config = config or load_embedding_config()
    return {
        "provider": config.provider,
        "base_url": config.base_url,
        "model": config.model,
        "configured": is_configured(config),
        "has_api_key": bool(config.api_key),
        "dim": config.dim,
    }


def safe_error_detail(text: str, config: EmbeddingConfig, limit: int = 500) -> str:
    detail = " ".join(text.split())
    if config.api_key:
        detail = detail.replace(config.api_key, "[REDACTED]")
    return detail[:limit]


def postprocess_vector(vector: list[float], config: EmbeddingConfig) -> list[float]:
    if config.dim:
        vector = vector[: config.dim]
    norm = sqrt(sum(value * value for value in vector))
    if not norm:
        return vector
    return [value / norm for value in vector]


def supports_batch_embeddings(config: EmbeddingConfig) -> bool:
    return "vision" not in config.model
