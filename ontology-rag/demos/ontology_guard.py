"""
DEMO 3 — 本体校验(RAG 输出过闸)。

流程: original RAG 的检索结果与回答 → 用 RULE 层硬约束校验(类 SHACL 形状校验)
      → 违规则 BLOCK 并给出修订回答。

与文章第 8 章的对照:
  RAG 检索片段/LLM 回答  ≈  RDF 图(要校验的数据)
  规则 R1..R4            ≈  预定义的 SHACL 形状(约束本身)
  本文件校验逻辑          ≈  SHACL Validator(形状 -> 数据)

校验是确定性的(不靠 LLM 自觉):模式匹配违规断言,命中即拦截。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from config import load_config
from llm import chat
from ontology_data import RULES

# 问题 id -> 应校验的规则 id(控制组 Q5 无约束)
QUESTION_RULE: dict[str, str] = {"Q1": "R1", "Q2": "R2", "Q3": "R3", "Q4": "R4", "Q5": ""}


_CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _cn_to_int(s: str) -> int:
    """'三十六'→36,'十二'→12,'十'→10,'三'→3。"""
    s = s.strip()
    if "十" in s:
        head, _, tail = s.partition("十")
        tens = _CN_DIGITS.get(head, 1) if head else 1
        ones = _CN_DIGITS.get(tail, 0) if tail else 0
        return tens * 10 + ones
    return _CN_DIGITS.get(s, 0)


def _extract_periods(a: str) -> list[int]:
    nums: list[int] = []
    for m in re.finditer(r"(\d{1,2}|[一二三四五六七八九十]+)\s*期", a):
        tok = m.group(1)
        nums.append(int(tok) if tok.isdigit() else _cn_to_int(tok))
    return nums


def _violated(rule: dict, answer: str) -> bool:
    a = answer.lower()
    rid = rule["id"]

    if rid == "R1":  # 期数 <= 12(阿拉伯与中文数字都拦)
        for n in _extract_periods(a):
            if n > 12:
                return True
        return False

    if rid == "R2":  # 88 元必须带活动限定
        if "88" in a:
            qualified = any(w in a for w in ["以旧换新", "活动", "旧机", "回收", "折后"])
            return not qualified
        return False

    if rid == "R3":  # 激活后可退?必须否定 + 未激活限定
        neg = any(w in a for w in ["不能", "不行", "不支持", "无法", "只换不修"])
        if not neg and any(w in a for w in ["可以退", "能退", "可退", "支持退货", "可以退货"]):
            return True
        return False

    if rid == "R4":  # 每笔限用一张:只拦"肯定式叠加/共用",豁免"不可叠加"等否定表述
        a_tmp = re.sub(r"(不|不能|不可|不允许|无法)[\s]*(叠加|一起|同时)[\s]*(用|使用)?", "", a)
        return bool(
            re.search(r"一起(用|使用)|同时(用|使用)|叠加|两张|2\s*张|多张", a_tmp)
        )

    return False


@dataclass
class GuardResult:
    question: str
    rule: dict | None
    original_answer: str
    verdict: str  # PASS | BLOCKED
    message: str = ""
    revised_answer: str = ""
    revised_ok: bool = True  # 修订后是否不再触发该规则(确定性校验)


def _revise(cfg, rule: dict, question: str, bad_answer: str, fresh: bool) -> str:
    system = (
        "你是 Nova Store 客服助手。用户问:{q}\n\n"
        "你之前的回答违反了一条业务硬约束,必须重新回答:\n"
        "【约束】{msg}\n"
        "若问题属于'能不能/是多少/对不对'的疑问句,请先用『不能/不是/不可以』开门见山,"
        "再给出符合约束的简洁答案。"
    ).format(q=question, msg=rule["message"])
    user = f"之前错误的回答:{bad_answer}"
    return chat(cfg, system, user, fresh=fresh)


def run_guard(question_id: str, original_answer: str, fresh: bool = False, cfg=None) -> GuardResult:
    cfg = cfg or load_config()
    rule_id = QUESTION_RULE.get(question_id, "")
    rule = next((r for r in RULES if r["id"] == rule_id), None)

    if rule is None or not _violated(rule, original_answer):
        return GuardResult(
            question=question_id,
            rule=rule,
            original_answer=original_answer,
            verdict="PASS",
        )

    revised = _revise(cfg, rule, _question_text(question_id), original_answer, fresh)
    return GuardResult(
        question=question_id,
        rule=rule,
        original_answer=original_answer,
        verdict="BLOCKED",
        message=rule["message"],
        revised_answer=revised,
        revised_ok=not _violated(rule, revised),  # 修订合规 = 不再违反硬约束
    )


def _question_text(question_id: str) -> str:
    from questions import QUESTIONS

    return next(q["question"] for q in QUESTIONS if q["id"] == question_id)


if __name__ == "__main__":
    import argparse

    from questions import QUESTIONS

    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--qid", default="Q1")
    parser.add_argument("--answer", default="", help="手工喂给校验器的回答(缺省跑 original RAG 得到)")
    args = parser.parse_args()

    cfg = load_config()
    answer = args.answer
    if not answer:
        from rag_original import run_rag

        q = next(x for x in QUESTIONS if x["id"] == args.qid)
        answer = run_rag(q["question"], fresh=args.fresh, cfg=cfg).answer

    g = run_guard(args.qid, answer, fresh=args.fresh, cfg=cfg)
    print(f"问题: {_question_text(args.qid)}")
    print(f"原始回答: {g.original_answer}")
    print(f"校验结论: {g.verdict}")
    if g.verdict == "BLOCKED":
        print(f"违反规则: {g.rule['id']} — {g.message}")
        print(f"修订回答: {g.revised_answer}")
    else:
        print("(未触发任何硬约束)")