"""
配置加载层 —— LLM / embedding 全部动态配置,不硬编码。

优先级(从高到低):
1. 专用环境变量:  DEMO_CHAT_BASE_URL / DEMO_CHAT_API_KEY / DEMO_CHAT_MODEL /
                    DEMO_EMBEDDING_MODEL
2. 通用环境变量:   DEFAULT_CHAT_BASE_URL / DEFAULT_CHAT_API_KEY / DEFAULT_CHAT_MODEL /
                    DEFAULT_EMBEDDING_MODEL        (与 shared-backend / cs-agent 同约定)
3. 兜底:           解析 <repo>/shared-backend/.env 里的 DEFAULT_CHAT_* 键
                   (默认路径可用 NEO_NOVA_BE_ENV 覆盖)

key 永远不进代码。demo 本身也从不打印完整 key。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DASH_SCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 探测 shared-backend 仓库位置:依次试相邻目录 / 常见路径
# (本文件位于 .../lyon/diagrams/ontology-rag/demos/,parent.parent 即 ~/lyon)
_CANDIDATE_BE_ENVS = [
    Path(os.environ["NEO_NOVA_BE_ENV"]).expanduser()
    if os.environ.get("NEO_NOVA_BE_ENV")
    else None,
    Path(__file__).resolve().parent.parent / "bkyz" / "shared-backend" / ".env",
    Path.home() / "lyon" / "bkyz" / "shared-backend" / ".env",
]


def _parse_env_file(path: Path) -> dict[str, str]:
    """极简 .env 解析:KEY=VALUE,忽略注释与空行,不做 shell 求值。"""
    out: dict[str, str] = {}
    if not path or not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key:
            out[key] = val
    return out


def _backend_env() -> dict[str, str]:
    for p in _CANDIDATE_BE_ENVS:
        if p and p.exists():
            return _parse_env_file(p)
    return {}


@dataclass
class DemoConfig:
    chat_base_url: str
    chat_api_key: str
    chat_model: str
    embedding_model: str
    embedding_dim: int = 1536  # text-embedding-v2
    timeout_ms: int = 30_000
    sources: list[str] = field(default_factory=list)  # 记录每个值来自哪一层

    @property
    def ready(self) -> bool:
        return bool(self.chat_api_key)

    def mask_key(self) -> str:
        k = self.chat_api_key
        if not k:
            return "<unset>"
        return f"{k[:6]}…{k[-4:]}(len {len(k)})"


def _first(*vals: str | None) -> str | None:
    for v in vals:
        if v:
            return v
    return None


def load_config() -> DemoConfig:
    be = _backend_env()

    def resolve(primary: str | None, generic: str | None, backend_key: str, default: str = "") -> tuple[str, str]:
        """返回 (值, 来源标签)。"""
        if primary:
            return primary, "env(DEMO_*)"
        if generic:
            return generic, "env(DEFAULT_*)"
        if be.get(backend_key):
            return be[backend_key], "shared-backend/.env"
        return default, "default"

    base, b_src = resolve(
        os.environ.get("DEMO_CHAT_BASE_URL"),
        os.environ.get("DEFAULT_CHAT_BASE_URL"),
        "DEFAULT_CHAT_BASE_URL",
        DEFAULT_DASH_SCOPE_BASE,
    )
    key, k_src = resolve(
        os.environ.get("DEMO_CHAT_API_KEY"),
        os.environ.get("DEFAULT_CHAT_API_KEY"),
        "DEFAULT_CHAT_API_KEY",
        "",
    )
    model, m_src = resolve(
        os.environ.get("DEMO_CHAT_MODEL"),
        os.environ.get("DEFAULT_CHAT_MODEL"),
        "DEFAULT_CHAT_MODEL",
        "qwen-plus",
    )
    emb, e_src = resolve(
        os.environ.get("DEMO_EMBEDDING_MODEL"),
        os.environ.get("DEFAULT_EMBEDDING_MODEL"),
        "DEFAULT_EMBEDDING_MODEL",
        "text-embedding-v2",
    )

    return DemoConfig(
        chat_base_url=base.rstrip("/"),
        chat_api_key=key,
        chat_model=model,
        embedding_model=emb,
        sources=["base:" + b_src, "key:" + k_src, "model:" + m_src, "embed:" + e_src],
    )


def describe() -> str:
    cfg = load_config()
    lines = [
        f"LLM base:      {cfg.chat_base_url}   [{cfg.sources[0]}]",
        f"LLM model:     {cfg.chat_model}      [{cfg.sources[2]}]",
        f"Embedding:     {cfg.embedding_model} [{cfg.sources[3]}]",
        f"API key:       {cfg.mask_key()}      [{cfg.sources[1]}]",
        f"LLM 可用:      {'是' if cfg.ready else '否 — 请设置 DEFAULT_CHAT_API_KEY'}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    sys.stdout.write(describe() + "\n")