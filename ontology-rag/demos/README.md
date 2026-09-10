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

## 目录结构

```
demos/
├── rag_original.py        # demo 1:朴素向量检索 top1 + LLM
├── graph_rag.py           # demo 2:实体图 BFS 子图 + LLM
├── og_rag.py              # demo 3:超图事实命中 + LLM
├── ontology_guard.py      # demo 4:硬约束校验 + 修订
├── compare.py             # 对比器:同一问题集跑四管道,输出总览
├── compare_results.md     # 生成的结果文档(逐题段落 + 总览表)
├── utils/                 # 基础设施(共享)
│   ├── config.py          #   动态配置(env → demos/.env)
│   ├── llm.py             #   OpenAI 兼容 chat client(带缓存)
│   ├── embed.py           #   embedding client(带缓存)
│   ├── corpus.py          #   伪造语料(埋坑设计)
│   ├── questions.py       #   问题集 + 标准答案判定
│   └── ontology_data.py   #   超图事实(ABox)+ 约束规则(RULE 层)
├── .env                   # 本仓库配置(不入库):base/model/key/embedding
└── .cache/                # 真实 API 结果缓存(可离线复现,不入库可选)
```

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

## 实验设定(三个声明,写作第八章时请保留)

**① 权威事实层 = 人工治理的结果态。**
og-rag 的超图事实与 graph-rag 的知识图谱都是手工构造的——它们模拟的是真实管线中
"抽取 → 人工审查 → 入库"**之后**的权威事实层(对文章判定五问里的"权威源头")。
demo 刻意不建模抽取与审查环节本身:抽取正是错误的主要来源之一,如果让本体管道也走过
自动抽取,错误会混进来,反而说不清差异。所以原始 RAG 的错误让检索自由暴露(真实发生),
本体管道直接输入治理后的结果态(真实世界同样如此)。要做端到端对比,应另加一条
"LLM 自动抽取 ABox(带噪声)"管道。

**② original RAG 禁纠错 = 控制变量。**
`rag_original.py` 的 system prompt 要求模型"原样采用片段说法,即使与常识不符也不得
自行纠错"。这是刻意隔离:把"检索命中了什么"与"模型会不会碰巧纠错"分开,单独暴露检索层缺陷。
若不锁,部分模型会凭常识兜住(实测 qwen-plus 在开放 prompt 下 5/5 全对)——那会掩盖
"向量检索命中错误断言"这个真实缺陷。graph-rag / og-rag 未加此约束,三者行为差异来自
输入结构,而非 prompt。

**③ guard 修订双口径评估。**
规则合规(修订不再触发硬约束)≠ 回答正确。compare 对每条修订同时打两个分:
『合』= guard 自证合规(不再违反硬约束);
『对』= 标准答案命中(与前三列同一套 `judgement`,独立仲裁)。
表格中两信号并列显示,互不掩盖。当前 5 题修订恰好双口径全过。

**样本声明**:5 题(4 坑 + 1 控制)是教学最小集,演示架构差异可以,
不构成统计显著性,结论不可外推。

## 四管道表现(教学叙事)

| 问题 | original | graph-rag | og-rag | guard(合·对) |
|---|---|---|---|---|
| Q1 分期最长几期 | ✗ 三十六期 | ✓ 12 期 | ✓ | 拦截 R1 → 合✓·对✓ |
| Q2 只要 88 元? | ✗ 是 88 元起 | ✓ 活动价 | ✓ | 拦截 R2 → 合✓·对✓ |
| Q3 激活能退货? | ✗ 可以退 | ✓ 不可以 | ✓ | 拦截 R3 → 合✓·对✓ |
| Q4 两券并用? | ✗ 可以一起用 | ✗ 可以(图上宣称) | ✓ 不可以 | 拦截 R4 → 合✓·对✓ |
| Q5 支付方式 | ✓ | ✓ | ✓ | PASS |
| **得分** | **1/5** | **4/5** | **5/5** | 拦 4 条,修订后双口径 **5/5** |

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

每个 repo 自带 `demos/.env`(不入库,部署时自填);读取顺序:

| 优先 | 环境变量 / 文件 | 默认 |
|---|---|---|
| 1 | `DEMO_CHAT_BASE_URL` / `DEMO_CHAT_API_KEY` / `DEMO_CHAT_MODEL` / `DEMO_EMBEDDING_MODEL` | — |
| 2 | `DEFAULT_CHAT_BASE_URL` / `DEFAULT_CHAT_API_KEY` / `DEFAULT_CHAT_MODEL` / `DEFAULT_EMBEDDING_MODEL` | — |
| 3 | `demos/.env`(本仓库自带配置) | qwen-plus / text-embedding-v2 |

`.env` 内容示例(外部 repo = dashscope,内部 repo = 内网网关,各自填各自的):

```bash
DEFAULT_CHAT_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DEFAULT_CHAT_API_KEY=sk-***
DEFAULT_CHAT_MODEL=qwen-plus
DEFAULT_EMBEDDING_MODEL=text-embedding-v2
```

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