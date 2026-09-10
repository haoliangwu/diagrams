"""
真实 embedding client —— OpenAI 兼容 POST {base}/embeddings。

- 模型: config.embedding_model,默认 text-embedding-v2(1536 维)。
- 语料固定,embedding 结果落盘缓存(.cache/embeddings.json,按语料内容哈希键控),
  首次运行真实调用 DashScope,之后离线复用 —— 流程真实、演示可复现。
- 维度以 API 实际返回为准(config.embedding_dim 只是默认)。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import requests

from config import DemoConfig

CACHE_DIR = Path(__file__).resolve().parent / ".cache"
EMBED_CACHE = CACHE_DIR / "embeddings.json"


def _corpus_hash(texts: list[str]) -> str:
    blob = "\x1f".join(texts).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def _load_cache() -> dict:
    if EMBED_CACHE.exists():
        try:
            return json.loads(EMBED_CACHE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    EMBED_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def embed_texts(cfg: DemoConfig, texts: list[str], fresh: bool = False) -> np.ndarray:
    """批量 embed,返回 (n, dim) 数组。fresh=True 时绕过缓存真实调用。"""
    key = _corpus_hash(texts)
    cache = {} if fresh else _load_cache()

    if not fresh and key in cache:
        arr = np.asarray(cache[key], dtype=np.float32)
        return arr

    resp = requests.post(
        f"{cfg.chat_base_url}/embeddings",
        headers={"Authorization": f"Bearer {cfg.chat_api_key}", "Content-Type": "application/json"},
        json={"model": cfg.embedding_model, "input": texts},
        timeout=cfg.timeout_ms / 1000,
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    data = sorted(data, key=lambda d: d["index"])  # OpenAI 允许乱序返回
    arr = np.asarray([d["embedding"] for d in data], dtype=np.float32)
    if arr.shape[0] != len(texts):
        raise RuntimeError(f"embedding 返回 {arr.shape[0]} 条,期望 {len(texts)}")

    cache[key] = arr.tolist()
    _save_cache(cache)
    return arr


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))