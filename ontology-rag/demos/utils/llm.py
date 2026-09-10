"""
真实 LLM client —— OpenAI 兼容 POST {base}/chat/completions。

- 模型: config.chat_model,默认 qwen-plus(可切 qwen-turbo / 其他)。
- LLM 回答按 (model, system, user) 哈希落盘缓存,首次真实调用,之后可离线复用。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import requests

from utils.config import DemoConfig

# 缓存落在 demos/.cache(utils 的上一级)
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
LLM_CACHE = CACHE_DIR / "llm.json"


def _load_cache() -> dict:
    if LLM_CACHE.exists():
        try:
            return json.loads(LLM_CACHE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    LLM_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def _key(model: str, system: str, user: str) -> str:
    blob = "\x1f".join([model, system, user]).encode()
    return hashlib.sha256(blob).hexdigest()[:20]


def chat(
    cfg: DemoConfig,
    system: str,
    user: str,
    temperature: float = 0.2,
    fresh: bool = False,
) -> str:
    k = _key(cfg.chat_model, system, user)
    cache = {} if fresh else _load_cache()
    if not fresh and k in cache:
        return cache[k]

    payload = {
        "model": cfg.chat_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    resp = requests.post(
        f"{cfg.chat_base_url}/chat/completions",
        headers={"Authorization": f"Bearer {cfg.chat_api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=cfg.timeout_ms / 1000,
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"].strip()

    cache[k] = text
    _save_cache(cache)
    return text