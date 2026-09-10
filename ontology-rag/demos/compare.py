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


def _quote(text: str) -> str:
    """多行文本转 markdown 引用块。"""
    return "\n".join(f"> {ln}" if ln.strip() else ">" for ln in text.splitlines())


def render_md(rows, stats) -> str:
    out = [
        "# 四管道水平对比(Nova Store 伪造语料,真实 qwen-plus + text-embedding-v2)",
        "",
    ]
    for r in rows:
        out.append(f"## {r['id']} {r['question']}")
        out.append("")
        out.append(f"**埋坑**:{r['trap']}")
        out.append("")

        out.append(f"### original RAG —— 检索 top1:{r['orig_top'][0]} sim={r['orig_top'][1]:.3f}")
        out.append(_quote(r["orig"]))
        out.append(f"\n**{'✓ 答对' if r['orig_ok'] else '✗ 答错'}**")
        out.append("")

        out.append("### graph-rag —— 实体图 BFS 子图")
        out.append(_quote(r["graph"]))
        out.append(f"\n**{'✓ 答对' if r['graph_ok'] else '✗ 答错'}**")
        out.append("")

        out.append("### og-rag —— 超图事实命中")
        out.append(_quote(r["og"]))
        out.append(f"\n**{'✓ 答对' if r['og_ok'] else '✗ 答错'}**")
        out.append("")

        if r["guard"].verdict == "PASS":
            out.append("### 本体校验 —— PASS(未触发硬约束)")
            out.append("")
        else:
            out.append(
                f"### 本体校验 —— BLOCKED {r['guard'].rule['id']}:{r['guard'].message}"
            )
            out.append(_quote(f"拦截前的回答:{r['guard'].original_answer}"))
            out.append("")
            out.append(_quote(f"修订回答:{r['guard'].revised_answer}"))
            out.append(
                f"\n**{'✓ 修订后合规' if r['guard_ok'] else '✗ 修订仍不合规'}**"
            )
            out.append("")

    # ── 总览统计表(只放对错,干净)──────────────────────────────
    out.append("## 总览")
    out.append("")
    out.append("| 问题 | original RAG | graph-rag | og-rag | 本体校验 |")
    out.append("|---|---|---|---|---|")
    for r in rows:
        guard_cell = (
            "PASS"
            if r["guard"].verdict == "PASS"
            else f"拦截 {r['guard'].rule['id']} → {'✓' if r['guard_ok'] else '✗'}"
        )
        out.append(
            f"| {r['id']} {r['question']} | "
            f"{'✓' if r['orig_ok'] else '✗'} | "
            f"{'✓' if r['graph_ok'] else '✗'} | "
            f"{'✓' if r['og_ok'] else '✗'} | {guard_cell} |"
        )
    out += [
        "",
        f"| **正确率** | **{stats['original_ok']}/{len(rows)}** | "
        f"**{stats['graph_ok']}/{len(rows)}** | **{stats['og_ok']}/{len(rows)}** | "
        f"**拦截 {stats['blocked']} 条,修订后 {stats['revised_ok']}/{len(rows)} 合规** |",
        "",
    ]
    return "\n".join(out)


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