"""
DEMO 2 — OG-RAG(超图事实检索)。

流程: 问题 → 实体匹配超图(整条 hyperedge 命中)→ 事实进 prompt → LLM 生成。
关键差异: 向量检索按"相似度"给片段,丢条件细节;超图按"实体"给整条事实,
         条件(期数上限 / 活动价格限定 / 激活状态)跟着事实一起进上下文。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config import load_config
from llm import chat
from ontology_data import FACTS, match_facts

SYSTEM_PROMPT = (
    "你是 Nova Store 的客服助手。以下『事实』是经过校验的权威本体数据,"
    "每条事实中的『条件』必须原样遵守,回答时如实复述条件,不要自行放宽或简化。"
)


@dataclass
class OgRagResult:
    question: str
    facts: list[dict] = field(default_factory=list)
    answer: str = ""


def run_og_rag(question: str, fresh: bool = False, cfg=None) -> OgRagResult:
    cfg = cfg or load_config()
    facts = match_facts(question)  # 按实体命中整条 hyperedge
    if not facts:
        # 未命中任何超图事实(如控制组 Q5 支付方式)→ 回退到全部事实子集
        facts = FACTS

    def render(f: dict) -> str:
        cond = "; ".join(f"{k}={v}" for k, v in f["条件"].items())
        return f"[{f['id']}] 实体:{f['实体']} | 条件:{cond}"

    ctx = "\n".join(render(f) for f in facts)
    user = f"用户问题:{question}\n\n权威事实:\n{ctx}"
    answer = chat(cfg, SYSTEM_PROMPT, user, fresh=fresh)
    return OgRagResult(question=question, facts=facts, answer=answer)


if __name__ == "__main__":
    import argparse

    from questions import QUESTIONS, judgement

    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--qid", default="Q1")
    args = parser.parse_args()

    q = next(x for x in QUESTIONS if x["id"] == args.qid)
    cfg = load_config()
    r = run_og_rag(q["question"], fresh=args.fresh, cfg=cfg)
    print(f"问题: {q['question']}\n")
    for f in r.facts:
        cond = "; ".join(f"{k}={v}" for k, v in f["条件"].items())
        print(f"  [{f['id']}] {f['实体']} | {cond}")
    print(f"\n回答: {r.answer}\n")
    ok, why = judgement(args.qid, r.answer)
    print(f"判定: {'✓ 答对' if ok else '✗ 答错'} — {why}")