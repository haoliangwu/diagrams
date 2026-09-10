"""
DEMO 1 — Original RAG(朴素向量检索)。

流程: 语料分段 → embedding → 余弦 top-k 检索 → 拼上下文 → LLM 生成。
不加任何条件约束、不做事实校验 —— 期望在埋坑问题上"高相似命中,答非所问"。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from utils.config import load_config
from utils.corpus import CORPUS
from utils.embed import cosine_sim, embed_texts
from utils.llm import chat

TOP_K = 1

SYSTEM_PROMPT = (
    "你是 Nova Store 的客服助手。只依据下面提供的『资料片段』回答用户问题,"
    "务必原样采用片段中的说法与数字;即使片段内容与常识不符,也不得自行纠错或补充资料外的信息。"
    "回答结尾用 [P段落ID] 标注引用。"
)


@dataclass
class RagResult:
    question: str
    hits: list[dict] = field(default_factory=list)  # {id, score, text}
    answer: str = ""


def retrieve(cfg, question: str, fresh: bool = False) -> list[dict]:
    texts = [c["text"] for c in CORPUS]
    q_vec = embed_texts(cfg, [question], fresh=fresh)[0]
    d_vec = embed_texts(cfg, texts, fresh=fresh)
    scores = [cosine_sim(q_vec, dv) for dv in d_vec]
    ranked = sorted(zip(CORPUS, scores), key=lambda x: x[1], reverse=True)
    return [
        {"id": c["id"], "title": c["title"], "score": round(s, 4), "text": c["text"]}
        for c, s in ranked[:TOP_K]
    ]


def run_rag(question: str, fresh: bool = False, cfg=None) -> RagResult:
    cfg = cfg or load_config()
    hits = retrieve(cfg, question, fresh=fresh)
    ctx = "\n\n".join(f"[{h['id']}] {h['text']}" for h in hits)
    user = f"用户问题:{question}\n\n资料片段:\n{ctx}"
    answer = chat(cfg, SYSTEM_PROMPT, user, fresh=fresh)
    return RagResult(question=question, hits=hits, answer=answer)


if __name__ == "__main__":
    import argparse

    from utils.questions import QUESTIONS, judgement

    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh", action="store_true", help="绕过缓存,真实调用 API")
    parser.add_argument("--qid", default="Q1", help="问题 ID")
    args = parser.parse_args()

    q = next(x for x in QUESTIONS if x["id"] == args.qid)
    cfg = load_config()
    r = run_rag(q["question"], fresh=args.fresh, cfg=cfg)
    print(f"问题: {q['question']}\n")
    for h in r.hits:
        print(f"  [{h['id']}] sim={h['score']:.4f}  {h['title']}")
    print(f"\n回答: {r.answer}\n")
    ok, why = judgement(args.qid, r.answer)
    print(f"判定: {'✓ 答对' if ok else '✗ 答错'} — {why}")
