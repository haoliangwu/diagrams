"""
水平对比 —— 四管道跑同一问题集,输出对照表。

用法:
    python3 compare.py                  # 用缓存结果(快速,不调 API)
    python3 compare.py --fresh          # 强制全部真实调用
    python3 compare.py --md out.md      # 另存 Markdown 表格

判定口径与 questions.judgement 完全一致;guard 用"拦截数 + 修订合规性"评估。
管道顺序(对应文章章节): original RAG(1) → graph-rag(2) → og-rag(4) → 本体校验(5)。
"""

from __future__ import annotations

import argparse

from config import load_config, describe
from graph_rag import run_graph_rag
from og_rag import run_og_rag
from ontology_guard import run_guard
from questions import QUESTIONS, judgement
from rag_original import run_rag

HEADERS = ["问题", "original RAG", "graph-rag", "og-rag", "本体校验"]


def run_all(fresh: bool = False):
    cfg = load_config()
    rows = []
    stats = {"original_ok": 0, "graph_ok": 0, "og_ok": 0, "blocked": 0, "revised_ok": 0}

    for q in QUESTIONS:
        qid, question = q["id"], q["question"]

        orig = run_rag(question, fresh=fresh, cfg=cfg)
        orig_ok, orig_why = judgement(qid, orig.answer)

        graph = run_graph_rag(question, fresh=fresh, cfg=cfg)
        graph_ok, graph_why = judgement(qid, graph.answer)

        og = run_og_rag(question, fresh=fresh, cfg=cfg)
        og_ok, og_why = judgement(qid, og.answer)

        guard = run_guard(qid, orig.answer, fresh=fresh, cfg=cfg)
        if guard.verdict == "PASS":
            guard_ok = True
        else:
            guard_ok = guard.revised_ok  # 修订合规 = 不再违反该规则

        stats["original_ok"] += orig_ok
        stats["graph_ok"] += graph_ok
        stats["og_ok"] += og_ok
        stats["blocked"] += guard.verdict == "BLOCKED"
        stats["revised_ok"] += guard_ok

        rows.append(
            {
                "id": qid,
                "question": question,
                "trap": q["trap"],
                "orig_top": (orig.hits[0]["id"], orig.hits[0]["score"]) if orig.hits else ("-", 0),
                "orig": orig.answer,
                "orig_ok": orig_ok,
                "graph": graph.answer,
                "graph_ok": graph_ok,
                "og": og.answer,
                "og_ok": og_ok,
                "guard": guard,
                "guard_ok": guard_ok,
            }
        )
    return rows, stats


def render_text(rows, stats) -> str:
    line = f"{'问题':<6} {'original':<10} {'graph':<7} {'og-rag':<7} {'guard':<15}"
    out = [line, "-" * len(line)]
    for r in rows:
        g = "PASS" if r["guard"].verdict == "PASS" else f"BLOCK({r['guard'].rule['id']})"
        out.append(
            f"{r['id']:<6} {'✓' if r['orig_ok'] else '✗':<10} "
            f"{'✓' if r['graph_ok'] else '✗':<7} {'✓' if r['og_ok'] else '✗':<7} "
            f"{g:<15}  {r['question']}"
        )
    out.append("")
    out.append(
        f"original RAG {stats['original_ok']}/{len(rows)}  |  graph-rag {stats['graph_ok']}/{len(rows)}  |  "
        f"og-rag {stats['og_ok']}/{len(rows)}  |  guard 拦截 {stats['blocked']} 条,修订后 {stats['revised_ok']}/{len(rows)} 正确"
    )
    return "\n".join(out)


def render_md(rows, stats) -> str:
    lines = [
        "## 四管道水平对比(Nova Store 伪造语料,真实 qwen-plus + text-embedding-v2)",
        "",
        "| 问题 | original RAG(检索 top1) | graph-rag(BFS 子图) | og-rag(超图事实) | 本体校验(guard) |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        top = f"{r['orig_top'][0]} sim={r['orig_top'][1]:.3f}"
        ok1 = "✓" if r["orig_ok"] else "✗"
        ok2 = "✓" if r["graph_ok"] else "✗"
        ok3 = "✓" if r["og_ok"] else "✗"
        if r["guard"].verdict == "PASS":
            g = "PASS"
        else:
            g = f"BLOCKED {r['guard'].rule['id']} → {r['guard'].revised_answer[:24]}…"
        lines.append(
            f"| **{r['id']}** {r['question']} | {ok1} {top}<br>“{r['orig'][:36]}…” | "
            f"{ok2}<br>“{r['graph'][:36]}…” | {ok3}<br>“{r['og'][:36]}…” | {g} |"
        )
    lines += [
        "",
        f"**汇总**:original RAG {stats['original_ok']}/{len(rows)} 正确;"
        f"graph-rag {stats['graph_ok']}/{len(rows)} 正确(图能聚合多跳关联,"
        f"但规则型约束不在图上 → 仍会翻车);og-rag {stats['og_ok']}/{len(rows)} 正确;"
        f"guard 拦截 {stats['blocked']} 条错误断言,修订后 {stats['revised_ok']}/{len(rows)} 正确。",
    ]
    return "\n".join(lines)


def render_detail(rows) -> str:
    """逐题展开版(含 trap 说明与 guard 修订全文),控制台打印用。"""
    out = []
    for r in rows:
        out.append(f"\n{'=' * 64}\n{r['id']} | {r['question']}\n埋坑: {r['trap']}")
        out.append(f"\n[original RAG] top1={r['orig_top'][0]} sim={r['orig_top'][1]:.4f}")
        out.append(f"  回答: {r['orig']}  →  {'✓' if r['orig_ok'] else '✗'}")
        out.append(f"\n[graph-rag]\n  回答: {r['graph']}  →  {'✓' if r['graph_ok'] else '✗'}")
        out.append(f"\n[og-rag]\n  回答: {r['og']}  →  {'✓' if r['og_ok'] else '✗'}")
        if r["guard"].verdict == "PASS":
            out.append(f"\n[本体校验] PASS(未触发硬约束)")
        else:
            out.append(
                f"\n[本体校验] BLOCKED {r['guard'].rule['id']}: {r['guard'].message}"
                f"\n  修订回答: {r['guard'].revised_answer}  →  {'✓' if r['guard_ok'] else '✗'}"
            )
    return "\n".join(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--md", default="", help="输出 Markdown 文件路径")
    parser.add_argument("--detail", action="store_true", help="逐题展开细节")
    args = parser.parse_args()

    print("配置:\n" + describe() + "\n")
    rows, stats = run_all(fresh=args.fresh)
    if args.detail:
        print(render_detail(rows))
    print(render_text(rows, stats))
    if args.md:
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(render_md(rows, stats))
        print(f"\n对比表已写入: {args.md}")