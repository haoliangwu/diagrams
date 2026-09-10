"""
问题集与标准答案 —— 三道管道共用,compare.py 据此判定对错。

每题结构:
- id / 用户问题 / 答案关键点(权威答案,供判定)
- trap: 埋坑类型说明(展示给读者)
- verdict 判定函数: 用"关键子串"判断一条回答是否符合标准答案。
"""

from __future__ import annotations

QUESTIONS: list[dict] = [
    {
        "id": "Q1",
        "question": "信用卡分期最长可以分多少期?",
        "keywords": ["12", "十二", "12 期", "不超过 12"],
        "answer_brief": "最长 12 期(且单笔满 300 元)",
        "trap": "检索会命中'分期付款宣传页'(三十六期,高相似),真条款在'分期办理细则'(低相似)",
    },
    {
        "id": "Q2",
        "question": "Nova X1 只要 88 元吗?",
        "keywords": ["5,999", "5999", "五千九百九十九", "不是", "不止", "并非"],
        "answer_brief": "不是,88 元是以旧换新活动折后价,官方起售价 5,999 元",
        "trap": "检索会命中'限时特惠 88 元起'(高相似),真价格在'建议零售价'段",
    },
    {
        "id": "Q3",
        "question": "手机激活之后还能退货吗?",
        "keywords": ["不能", "不可以", "不行", "不支持", "无法", "只换不修"],
        "answer_brief": "不能无理由退货,仅质量问题 15 天内换新",
        "trap": "检索会命中'退货服务说明'(可以退),条件在'激活状态'段",
    },
    {
        "id": "Q4",
        "question": "店铺券和平台券能一起用吗?",
        "keywords": ["不能", "不可以", "不行", "限用一张", "一张"],
        "answer_brief": "不能,两种券都属于优惠券,每笔订单限用一张",
        "trap": "图上'店铺券/平台券 → 优惠券 → 订单可使用',多跳聚合会推断'都能用';限制在'券使用细则'段",
    },
    {
        "id": "Q5",
        "question": "Nova Store 支持哪些支付方式?",
        "keywords": ["银行卡", "信用卡", "分期", "支付宝", "微信", "货到付款"],
        "answer_brief": "银行卡 / 信用卡分期 / 支付宝 / 微信 / 货到付款",
        "trap": "控制组 —— 语料直接覆盖,所有管道都应答对",
    },
]


def judgement(question_id: str, answer: str) -> tuple[bool, str]:
    """返回 (是否答对, 要点命中/缺失说明)。"""
    q = next(x for x in QUESTIONS if x["id"] == question_id)
    text = (answer or "").lower()
    hits = [k for k in q["keywords"] if k.lower() in text]
    if q["id"] == "Q3":
        # 激活后可不可以退:必须同时出现否定词(不能/不可以/不支持……)。
        ok = any(k in text for k in ["不能", "不可以", "不行", "不支持", "无法", "只换不修"])
        return ok, f"否定词命中: {hits or '无'}"
    if q["id"] == "Q4":
        ok = any(k in text for k in ["不能", "不可以", "不行", "限用一张", "一张"])
        return ok, f"限制词命中: {hits or '无'}"
    if q["id"] == "Q1":
        ok = any(k in text for k in ["12", "十二"])
        return ok, f"期数命中: {hits or '无'}"
    if q["id"] == "Q2":
        price_ok = any(k in text for k in ["5,999", "5999", "五千九百九十九"])
        neg_88 = "88" in text and any(k in text for k in ["不是", "不止", "并非"])
        return price_ok or neg_88, f"价格/否定命中: {hits or '无'}"
    # Q5 控制组:命中 3 个及以上支付方式关键词即对
    required = ["银行卡", "信用卡", "支付宝", "微信", "货到付款"]
    n = sum(1 for k in required if k in text)
    return n >= 4, f"支付方式命中 {n}/5: {hits or '无'}"