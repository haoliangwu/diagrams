"""
DEMO 2.5 — 简易 GraphRAG(自实现,不依赖 graphrag 库)。

流程: 实体-关系图(手工构造)→ 问题实体识别 → BFS 多跳展开子图 → 子图转文本
      → LLM 依据子图回答。

与文章第 2 章的呼应:
- 优点: 图把"跨段关联"聚合起来 —— original RAG 单段检索抓不住的多跳信息,
        图两跳就拿到了(Q1 期数上限、Q2 价格、Q3 激活状态都能答对)。
- 局限: 图表达"谁和谁相关",不表达"哪些满足条件"。数量限制、否定条件、
        阈值这类约束语义通常不在图上 —— Q4"每笔限用一张"子图里根本没有,
        BFS 拿到的是"订单可使用优惠券"这条暗示边,LLM 会顺着答错。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from utils.config import load_config
from utils.llm import chat

# ── 手工构造的知识图谱(节点 + 有向关系边)──────────────────────────────────
NODES: dict[str, str] = {
    "n_credit": "信用卡分期",
    "n_periods": "可选期数(3/6/9/12)",
    "n_max12": "12 期为上限",
    "n_min300": "单笔满 300 元",
    "n_x1": "Nova X1",
    "n_price5999": "官方价 5,999 元",
    "n_tradein": "以旧换新活动",
    "n_price88": "活动价 88 元起",
    "n_return": "退货",
    "n_unactivated": "未激活机器",
    "n_7days": "7 天无理由",
    "n_activated": "已激活机器",
    "n_exchange": "仅质量问题 15 天换新",
    "n_coupon": "优惠券",
    "n_shop_coupon": "店铺券",
    "n_platform_coupon": "平台券",
    "n_promo": "店铺券与平台券可叠加使用",
    "n_order": "订单",
    "n_installment": "分期订单",
    "n_store": "Nova Store",
    "n_bankcard": "银行卡",
    "n_alipay": "支付宝",
    "n_wechat": "微信支付",
    "n_cod": "货到付款",
}

# (src, 关系, dst)。注意:优惠券域没有"限用一张"节点 —— 规则型约束不在图上。
EDGES: list[tuple[str, str, str]] = [
    ("n_credit", "提供", "n_periods"),
    ("n_periods", "最长", "n_max12"),
    ("n_credit", "要求", "n_min300"),
    ("n_x1", "官方售价", "n_price5999"),
    ("n_x1", "参与", "n_tradein"),
    ("n_tradein", "活动价", "n_price88"),
    ("n_return", "适用于", "n_unactivated"),
    ("n_unactivated", "时限", "n_7days"),
    ("n_return", "不适用于", "n_activated"),
    ("n_activated", "仅限", "n_exchange"),
    ("n_coupon", "类型", "n_shop_coupon"),
    ("n_coupon", "类型", "n_platform_coupon"),
    # 规则型约束("每笔限用一张")没有被抽进图 —— 规则缺失是图检索常态;
    # 而促销话术"两种券可叠加"反而被抽成了断言节点,图忠实存下错误信息。
    ("n_coupon", "宣称", "n_promo"),
    ("n_order", "可使用", "n_coupon"),
    ("n_order", "不适用", "n_installment"),
    ("n_store", "支持", "n_bankcard"),
    ("n_store", "支持", "n_credit"),
    ("n_store", "支持", "n_alipay"),
    ("n_store", "支持", "n_wechat"),
    ("n_store", "支持", "n_cod"),
]

# 问题实体识别:关键词 → 起始节点
ENTITY_QUERY: list[tuple[str, list[str]]] = [
    ("分期", ["n_credit"]),
    ("信用卡", ["n_credit"]),
    ("nova x1", ["n_x1"]),
    ("86", ["n_x1"]),  # 容错:大小写/空格
    ("退货", ["n_return"]),
    ("退款", ["n_return"]),
    ("激活", ["n_activated", "n_unactivated"]),
    ("优惠券", ["n_coupon"]),
    ("券", ["n_coupon", "n_shop_coupon", "n_platform_coupon"]),
    ("订单", ["n_order"]),
    ("支付", ["n_store"]),
    ("付款", ["n_store"]),
]

BFS_DEPTH = 2
NODE_CAP = 12  # 子图节点上限 —— 体现"图给太多无用上下文"的局限

SYSTEM_PROMPT = (
    "你是 Nova Store 的客服助手。下面是知识图谱的一张子图(节点与有向关系),"
    "请根据子图中的关系直接回答用户问题:能就答「可以」,不能就答「不可以」,"
    "然后补充你依据的子图关系。不要引入子图之外的信息。"
)


@dataclass
class GraphRagResult:
    question: str
    subgraph_nodes: list[str] = field(default_factory=list)
    subgraph_edges: list[tuple[str, str, str]] = field(default_factory=list)
    answer: str = ""


def _start_nodes(question: str) -> list[str]:
    ql = question.lower().replace(" ", "")
    starts: list[str] = []
    for kw, nodes in ENTITY_QUERY:
        if kw.replace(" ", "") in ql:
            starts.extend(nodes)
    return list(dict.fromkeys(starts))  # 去重保序


def _bfs_subgraph(starts: list[str]) -> tuple[list[str], list[tuple[str, str, str]]]:
    if not starts:
        return [], []
    seen: set[str] = set(starts)
    frontier: list[str] = starts
    edges: list[tuple[str, str, str]] = []

    for _ in range(BFS_DEPTH):
        if len(seen) >= NODE_CAP:
            break
        nxt: list[str] = []
        for node in frontier:
            for src, rel, dst in EDGES:
                if src == node and dst not in seen and len(seen) < NODE_CAP:
                    seen.add(dst)
                    nxt.append(dst)
                if dst == node and src not in seen and len(seen) < NODE_CAP:
                    seen.add(src)
                    nxt.append(src)
        frontier = nxt
        if not frontier:
            break

    for src, rel, dst in EDGES:
        if src in seen and dst in seen:
            edges.append((src, rel, dst))
    ordered = [n for n in NODES if n in seen]
    return ordered, edges


def run_graph_rag(question: str, fresh: bool = False, cfg=None) -> GraphRagResult:
    cfg = cfg or load_config()
    starts = _start_nodes(question)
    nodes, edges = _bfs_subgraph(starts)

    lines = ["节点:"]
    lines += [f"  - {NODES[n]}" for n in nodes]
    lines.append("关系:")
    lines += [f"  - {NODES[s]} --{rel}--> {NODES[d]}" for s, rel, d in edges]
    sub_text = "\n".join(lines)

    user = f"用户问题:{question}\n\n子图:\n{sub_text}"
    answer = chat(cfg, SYSTEM_PROMPT, user, fresh=fresh)
    return GraphRagResult(question=question, subgraph_nodes=nodes, subgraph_edges=edges, answer=answer)


if __name__ == "__main__":
    import argparse

    from utils.questions import QUESTIONS, judgement

    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--qid", default="Q1")
    args = parser.parse_args()

    q = next(x for x in QUESTIONS if x["id"] == args.qid)
    cfg = load_config()
    r = run_graph_rag(q["question"], fresh=args.fresh, cfg=cfg)
    print(f"问题: {q['question']}\n")
    print("子图节点:", ", ".join(NODES[n] for n in r.subgraph_nodes))
    for s, rel, d in r.subgraph_edges:
        print(f"  {NODES[s]} --{rel}--> {NODES[d]}")
    print(f"\n回答: {r.answer}\n")
    ok, why = judgement(args.qid, r.answer)
    print(f"判定: {'✓ 答对' if ok else '✗ 答错'} — {why}")