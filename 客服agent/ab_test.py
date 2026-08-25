"""A/B 测试模块 — 对比不同回答策略的效果"""
import random
import json
import os
from datetime import datetime

# 策略定义
STRATEGIES = {
    "A": {
        "name": "知识库优先",
        "description": "优先使用知识库回答，找不到再用大模型",
        "temperature": 0.3,  # 更保守
        "max_tokens": 300,
    },
    "B": {
        "name": "大模型优先",
        "description": "直接用大模型回答，参考知识库内容",
        "temperature": 0.7,  # 更灵活
        "max_tokens": 500,
    },
    "C": {
        "name": "混合策略",
        "description": "知识库 + 大模型结合，综合回答",
        "temperature": 0.5,
        "max_tokens": 400,
    },
}

# 用户分组（基于 session 或 IP）
_user_groups = {}

# 实验数据
EXPERIMENT_FILE = "ab_experiment.json"


def assign_user(user_id: str) -> str:
    """给用户分配策略组"""
    if user_id not in _user_groups:
        # 均匀随机分配
        _user_groups[user_id] = random.choice(list(STRATEGIES.keys()))
    return _user_groups[user_id]


def get_strategy(user_id: str) -> dict:
    """获取用户的策略配置"""
    group = assign_user(user_id)
    return {
        "group": group,
        **STRATEGIES[group],
    }


def record_experiment(user_id: str, strategy: str, question: str, answer: str, rating: int = None):
    """记录实验数据"""
    data = {
        "user_id": user_id,
        "strategy": strategy,
        "question": question,
        "answer": answer,
        "rating": rating,
        "timestamp": datetime.now().isoformat(),
    }

    # 追加到文件
    experiments = []
    try:
        with open(EXPERIMENT_FILE, 'r', encoding='utf-8') as f:
            experiments = json.load(f)
    except FileNotFoundError:
        pass

    experiments.append(data)
    with open(EXPERIMENT_FILE, 'w', encoding='utf-8') as f:
        json.dump(experiments, f, ensure_ascii=False, indent=2)


def get_experiment_results() -> dict:
    """获取实验结果统计"""
    try:
        with open(EXPERIMENT_FILE, 'r', encoding='utf-8') as f:
            experiments = json.load(f)
    except FileNotFoundError:
        return {"total": 0, "by_strategy": {}}

    # 按策略分组统计
    by_strategy = {}
    for exp in experiments:
        strategy = exp["strategy"]
        if strategy not in by_strategy:
            by_strategy[strategy] = {
                "count": 0,
                "ratings": [],
                "avg_rating": 0,
            }
        by_strategy[strategy]["count"] += 1
        if exp.get("rating"):
            by_strategy[strategy]["ratings"].append(exp["rating"])

    # 计算平均分
    for strategy in by_strategy:
        ratings = by_strategy[strategy]["ratings"]
        if ratings:
            by_strategy[strategy]["avg_rating"] = round(sum(ratings) / len(ratings), 2)

    return {
        "total": len(experiments),
        "by_strategy": by_strategy,
    }
