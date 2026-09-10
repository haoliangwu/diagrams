# 四管道 RAG Demo(本体论 × RAG)

为文章《本体论:RAG 的最后一公里》第 8 章配套的四管道对比 demo:

1. **original-rag** — 朴素向量检索 top1 + LLM 生成(无校验)
2. **graph-rag** — 简易自实现 GraphRAG(实体-关系图 + BFS 多跳子图 + LLM)
3. **og-rag** — 简易自实现超图事实(hyperedge)命中 + LLM 生成
4. **本体校验** — 用预定义硬约束校验 RAG 输出,违规即 BLOCK 并修订

graph-rag 与 og-rag 均为**自实现简易版**(约百行),不依赖 graphrag / ograg2 库,
但流程(实体识别 → 图展开 → 事实命中 → LLM 生成)与真实实现同构。
语料是**伪造的**(Nova Store 客服知识库),embedding 与 LLM 流程**真实**
(DashScope OpenAI 兼容 API:text-embedding-v2 + qwen-plus)。

## 埋坑设定(为什么朴素 RAG 会翻车)

知识库是多源汇集的,混着**表面正确、实则错误的断言**(促销落地页 / 过期公告 /
第三方话术)。用户问法与这些错误断言词汇高度重叠,向量检索给高分——
"高相似 ≠ 答案正确"。真条款措辞更像八股,相似度反而低。

| 坑域 | 陷阱段(高相似,错) | 答案段(低相似,对) |
|---|---|---|
| 分期 | "最长可申请三十六期" | 十二期为上限 |
| 价格 | "限时特惠 88 元起" | 官方 5,999 元 |
| 退货 | "激活也能 7 天退" | 激活后不退回 |
| 优惠券 | "店铺券平台券一起用" | 每笔核销一张 |

控制组 Q5(支付方式)语料直接覆盖,所有管道都应答对。

## 四管道表现(教学叙事)

| 问题 | original | graph-rag | og-rag | guard |
|---|---|---|---|---|
| Q1 分期最长几期 | ✗ 三十六期 | ✓ 12 期 | ✓ | BLOCK R1 → 修订 |
| Q2 只要 88 元? | ✗ 是 88 元起 | ✓ 活动价 | ✓ | BLOCK R2 → 修订 |
| Q3 激活能退货? | ✗ 可以退 | ✓ 不可以 | ✓ | BLOCK R3 → 修订 |
| Q4 两券并用? | ✗ 可以一起用 | ✗ 可以(图上宣称) | ✓ 不可以 | BLOCK R4 → 修订 |
| Q5 支付方式 | ✓ | ✓ | ✓ | PASS |
| **得分** | **1/5** | **4/5** | **5/5** | 拦 4 条,修订后 **5/5** |

渐进式防线:向量检索踩坑(1/5)→ 加图,多跳关联救回三题但仍缺约束语义(4/5)
→ 超图把条件绑死在事实里(5/5)→ 本体校验确定性兜底(拦截所有错误断言)。

graph-rag 在 Q4 翻车的原因(对应文章第 2 章):
图忠实存下促销断言"店铺券与平台券可叠加使用",而"每笔限用一张"是
**规则,没有被抽进图**(规则缺失是图检索常态)。图知道谁和谁相关,
不知道哪些满足条件。

## 运行

```bash
python3 compare.py           # 缓存结果(快速、可复现,首次运行会真实调 API)
python3 compare.py --fresh   # 强制全部重新真实调用
python3 compare.py --detail  # 逐题展开(含埋坑说明与修订全文)
python3 compare.py --md compare_results.md   # 导出 Markdown 表格

# 单管道单题:
python3 rag_original.py --qid Q1
python3 graph_rag.py --qid Q4
python3 og_rag.py --qid Q3
python3 ontology_guard.py --qid Q4
```

## 配置(动态)

读取顺序:先专用环境变量,再通用变量,最后兜底解析 `shared-backend/.env`:

| 优先 | 环境变量 | 默认 |
|---|---|---|
| 1 | `DEMO_CHAT_BASE_URL` / `DEMO_CHAT_API_KEY` / `DEMO_CHAT_MODEL` / `DEMO_EMBEDDING_MODEL` | — |
| 2 | `DEFAULT_CHAT_BASE_URL` / `DEFAULT_CHAT_API_KEY` / `DEFAULT_CHAT_MODEL` / `DEFAULT_EMBEDDING_MODEL` | — |
| 3 | `shared-backend/.env`(路径可用 `NEO_NOVA_BE_ENV` 覆盖) | qwen-plus / text-embedding-v2 |

改模型示例:

```bash
export DEMO_CHAT_MODEL=qwen-turbo
python3 compare.py --fresh   # 换模型后 --fresh 重新真实调用
```

key 不进代码、不写进任何 demo 文件;可用 `python3 config.py` 查看解析结果
(key 只显示前 6 后 4 字符)。

## 结果缓存

`./.cache/embeddings.json`(按语料哈希)与 `./.cache/llm.json`(按 prompt 哈希)。
首次运行真实调用后离线复用,演示可复现、不重复烧钱。

## 与文章章节的对照

| Demo | 文章章节 | 关键机制 |
|---|---|---|
| original-rag | 第 1 章"向量检索不足" | 高相似检索 ≠ 答案正确(0.77 vs 0.41 的格局) |
| graph-rag | 第 2 章"GraphRAG 不够" | 多跳子图聚合关联,但规则型约束不在图上 |
| og-rag | 第 4 章"OG-RAG 超图" | 整条 hyperedge 命中,条件跟着事实走 |
| 本体校验 | 第 5 章"校验 guardrail" | 预定义规则(≈SHACL 形状)校验输出,违规 BLOCK |
| compare | 全章对比 | 同一问题集四管道对照 |

## 实现说明(简易自实现)

- `graph_rag.py` — 手工知识图谱(节点 + 有向边),实体识别 → BFS 两跳展开子图
  (节点上限 12)→ 子图转文本 → LLM。图的"错误断言"来自促销页话术被抽成节点,
  规则缺失是翻车根源。
- `og_rag.py` — 超图事实(fact dict 绑定 ≥3 节点),实体命中整条事实,
  条件(期数上限/活动价限定/激活状态)跟着事实进上下文。
- `ontology_guard.py` — 确定性规则校验(类 SHACL 形状),模式匹配违规断言
  (支持中文数字),违规 BLOCK 并让 LLM 按约束重答,修订合规性再校验一遍。