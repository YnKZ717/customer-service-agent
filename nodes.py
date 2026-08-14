"""节点定义 — 客服Agent的每个处理步骤"""
from tools_vector import search_knowledge_base, save_pending_faq
from tools_chunk import search_chunks
from ticket_utils import create_ticket, transfer_to_human
from openai import OpenAI
from config import LLM_CONFIG, FALLBACK_MODELS
from i18n import t

# 初始化大模型客户端（主模型）
client = OpenAI(
    api_key=LLM_CONFIG["api_key"],
    base_url=LLM_CONFIG["base_url"],
)

# 初始化备用模型客户端
fallback_clients = []
for fm in FALLBACK_MODELS:
    if fm["api_key"] and fm["base_url"]:
        fallback_clients.append(OpenAI(api_key=fm["api_key"], base_url=fm["base_url"]))


# ── 意图关键词映射（与知识库对齐）──────────────────────────
INTENT_KEYWORDS = {
    # 账户相关
    "account":      ["注册", "登录", "账号", "密码", "注销", "换绑"],

    # 计费相关
    "billing":      ["充值", "积分", "付费", "支付", "扫码", "余额", "套餐"],

    # 套餐服务
    "codingplan":   ["CodingPlan", "套餐", "额度", "Credits", "会员", "权益", "VIP"],

    # 智能体使用
    "agent_service":["智能体", "对话", "创作", "云端服务", "试用"],

    # 桌面客户端
    "desktop":      ["客户端", "桌面", "下载", "安装"],

    # 应用市场
    "app_market":   ["应用市场", "购买应用", "上传应用", "预览"],

    # 技能市场
    "skill_market": ["技能市场", "技能", "同步", "收藏"],

    # 部署 Token
    "deploy_token": ["部署Token", "CI/CD", "发布"],

    # 数据备份
    "backup":       ["备份", "数据", "记录", "云端"],

    # 投诉反馈
    "complaint":    ["投诉", "不满意", "差评"],

    # 转人工
    "human":        ["人工", "转人工", "客服"],

    # 故障排查
    "troubleshoot": ["失败", "报错", "错误", "不行", "有问题", "异常", "卡住", "没反应",
                    "生成失败", "无法生成", "不能用", "坏了"],

    # 任务状态查询
    "task_status":  ["任务", "进度", "好了吗", "完成了吗", "还要多久", "状态"],

    # 操作指导
    "howto":        ["怎么用", "怎么做", "如何使用", "教程", "指南", "步骤"],
}

# ── 三层 system prompt 组装 ──
SYSTEM_PROMPT_STABLE = """你是 Neowow Studio 的智能客服助手。Neowow 是一站式智能创意内容生产与协作平台。

## 回答风格
- 简洁、专业、直接
- 不要过度热情，不要加"哈""呢""啦"等语气词
- 不要加 emoji，除非用户先用了

## 回答规则
1. 优先用知识库内容回答，确保准确
2. 知识库没有的，用你的理解回答
3. 完全不知道的问题，诚实说"这个我暂时无法确认，建议查阅官方文档或联系人工客服"
4. 涉及充值、账号安全等敏感操作，提醒用户通过官方渠道

## 能力边界
- 能回答：Neowow 平台功能、套餐、操作指南、常见问题
- 不能回答：第三方平台（如火山引擎/抖音）的具体技术问题
- 不要说"这不归我管"，给出替代方案

## 禁止行为
- 不要说"我们不提供XX服务"
- 不要说"建议您联系XX官方"
- 不要编造平台没有的功能"""

SYSTEM_PROMPT_MEMORY_TEMPLATE = """对话历史（最近{count}轮）：
{history}
（根据历史判断用户是老用户还是新用户，保持回答连贯性）"""

SYSTEM_PROMPT_TASK_TEMPLATE = """知识库参考（可能相关，但不一定完全匹配）：
{kb_context}
（如果以上内容与用户问题相关，优先参考；如果无关，忽略）"""


def build_system_prompt(history: list, kb_context: str = None) -> str:
    """动态组装三层 system prompt"""
    layers = [SYSTEM_PROMPT_STABLE]

    # 记忆层：用户历史
    if history:
        recent = history[-6:]  # 最近3轮
        history_text = "\n".join([
            f"  {'用户' if r == 'user' else '客服'}：{c}"
            for r, c in recent
        ])
        memory_layer = SYSTEM_PROMPT_MEMORY_TEMPLATE.format(
            count=len(recent),
            history=history_text
        )
        layers.append(memory_layer)

    # 任务层：知识库参考
    if kb_context:
        task_layer = SYSTEM_PROMPT_TASK_TEMPLATE.format(kb_context=kb_context)
        layers.append(task_layer)

    return "\n\n".join(layers)


def classify_intent(state: dict) -> dict:
    """节点1：意图识别 — 判断用户问题类型"""
    user_input = state["user_input"]

    for intent, keywords in INTENT_KEYWORDS.items():
        if any(k in user_input for k in keywords):
            return {"intent": intent, "user_input": user_input}

    # 没匹配到任何关键词 → 通用问题
    return {"intent": "general", "user_input": user_input}


def answer_from_kb(state: dict) -> dict:
    """节点2：知识库回答 — 先查知识库，不管意图是什么"""
    query = state.get("user_input", "")

    if not query or not isinstance(query, str):
        return {"kb_found": False, "intent": state.get("intent", "general"), "kb_reference": ""}

    # 查知识库，获取精确匹配和相关参考
    question, answer, reference = search_knowledge_base(query, threshold=0.65, return_reference=True)

    if answer is None:
        # 知识库里没有精确匹配，但可能有相关参考
        return {
            "kb_found": False,
            "intent": state["intent"],
            "user_input": state["user_input"],
            "kb_reference": reference,  # 传给大模型作为参考
        }

    return {
        "response": answer,
        "intent": state["intent"],
        "kb_category": question or "未匹配",
        "kb_found": True,
        "kb_reference": "",
    }


def chunk_search_node(state: dict) -> dict:
    """节点3：Chunk搜索 — FAQ没找到时，搜文档片段"""
    query = state.get("user_input", "")

    if not query or not isinstance(query, str):
        return {"chunk_found": False, "intent": state.get("intent", "general"), "chunk_reference": ""}

    # 搜索chunk片段
    chunks = search_chunks(query, top_k=2, threshold=0.5)

    if chunks:
        # 把片段拼成参考文本
        chunk_text = "\n\n".join([f"[文档片段{i+1}]：{c}" for i, c in enumerate(chunks)])
        return {
            "chunk_found": True,
            "chunk_reference": chunk_text,
            "intent": state["intent"],
        }
    else:
        return {
            "chunk_found": False,
            "chunk_reference": "",
            "intent": state["intent"],
        }


def handle_human(state: dict) -> dict:
    """节点3：转人工 — 创建真实工单"""
    user_input = state["user_input"]
    history = state.get("history", [])

    ticket = create_ticket(user_input, history)
    return {
        "response": t("ticket_created", ticket_id=ticket['ticket_id']),
        "ticket_id": ticket['ticket_id'],
        "intent": state["intent"],
    }


def troubleshoot(state: dict) -> dict:
    """故障排查节点 — 多轮引导用户解决问题"""
    user_input = state["user_input"]
    history = state.get("history", [])

    # 构建故障排查的 system prompt
    troubleshoot_prompt = """你是 Neowow 平台的技术支持。用户遇到了问题，通过多轮对话引导他们排查。

## 排查风格
- 简洁、专业、清晰
- 不要过度热情，不要用"哈""呢""啦"等语气词
- 不要加 emoji，除非用户先用了
- 每次只问 1-2 个问题
- 用编号列表给排查步骤

## 排查流程
1. 先确认问题类型（视频/图片/音频/账户/其他）
2. 了解具体情况（错误提示、任务 ID、操作步骤）
3. 给出针对性的排查建议（最多 3 条）
4. 如果问题仍未解决，主动建议转人工客服

## 注意
- 不要说"请提供详细信息"
- 不要推卸责任，给出实际建议
"""

    # 构建消息
    messages = [{"role": "system", "content": troubleshoot_prompt}]

    # 添加最近 4 轮对话历史（故障排查需要更多上下文）
    for role, content in history[-8:]:
        messages.append({"role": "user" if role == "user" else "assistant", "content": content})

    messages.append({"role": "user", "content": user_input})

    reply = None

    # 主模型调用（失败自动重试 1 次）
    for attempt in range(2):
        try:
            if attempt == 1:
                print("[自动重试] 主模型第 2 次尝试...")
            response = client.chat.completions.create(
                model=LLM_CONFIG["model_name"],
                messages=messages,
                max_tokens=600,
                temperature=0.5,
            )
            reply = response.choices[0].message.content
            break
        except Exception as e:
            print(f"[模型降级] 主模型第{attempt+1}次失败：{str(e)[:60]}")
            if attempt == 0:
                continue

    # 主模型彻底失败，尝试备用模型
    if reply is None:
        print("[模型降级] 主模型重试失败，切换备用模型...")
        for i, fb_client in enumerate(fallback_clients):
            fm = FALLBACK_MODELS[i]
            try:
                print(f"[模型降级] 切换到备用模型 {fm['model_name']}...")
                response = fb_client.chat.completions.create(
                    model=fm["model_name"],
                    messages=messages,
                    max_tokens=600,
                    temperature=0.5,
                )
                reply = response.choices[0].message.content
                print("[模型降级] 备用模型成功")
                break
            except Exception as e2:
                print(f"[模型降级] 备用模型 {i+1} 也失败：{str(e2)[:50]}")
                continue

    if reply is None:
        reply = "抱歉，系统暂时繁忙，请稍后再试。如需紧急帮助，请输入'转人工'。"

    return {
        "response": reply,
        "intent": "troubleshoot",
    }


def general_reply(state: dict) -> dict:
    """节点5：通用回复 — 大模型兜底，使用三层 system prompt"""
    user_input = state["user_input"]
    history = state.get("history", [])
    kb_reference = state.get("kb_reference", "")
    chunk_reference = state.get("chunk_reference", "")

    # 合并参考内容
    all_reference = ""
    if kb_reference:
        all_reference += "【FAQ参考】\n" + kb_reference + "\n\n"
    if chunk_reference:
        all_reference += "【文档片段参考】\n" + chunk_reference

    # 组装三层 system prompt
    system_prompt = build_system_prompt(history, all_reference if all_reference else None)

    # 构建消息
    messages = [{"role": "system", "content": system_prompt}]
    for role, content in history[-6:]:
        messages.append({"role": "user" if role == "user" else "assistant", "content": content})
    messages.append({"role": "user", "content": user_input})

    reply = None

    # 主模型调用（失败自动重试 1 次）
    for attempt in range(2):
        try:
            if attempt == 1:
                print("[自动重试] 主模型第 2 次尝试...")
            response = client.chat.completions.create(
                model=LLM_CONFIG["model_name"],
                messages=messages,
                max_tokens=500,
                temperature=0.7,
            )
            reply = response.choices[0].message.content
            break
        except Exception as e:
            print(f"[模型降级] 主模型第{attempt+1}次失败：{str(e)[:60]}")
            if attempt == 0:
                continue  # 重试一次

    # 主模型彻底失败，尝试备用模型
    if reply is None:
        print("[模型降级] 主模型重试失败，切换备用模型...")
        for i, fb_client in enumerate(fallback_clients):
            fm = FALLBACK_MODELS[i]
            try:
                print(f"[模型降级] 切换到备用模型 {fm['model_name']}...")
                response = fb_client.chat.completions.create(
                    model=fm["model_name"],
                    messages=messages,
                    max_tokens=500,
                    temperature=0.7,
                )
                reply = response.choices[0].message.content
                print("[模型降级] 备用模型成功")
                break
            except Exception as e2:
                print(f"[模型降级] 备用模型 {i+1} 也失败：{str(e2)[:50]}")
                continue

    if reply is None:
        reply = t("service_unavailable")

    # 沉淀：新问题自动记录（只沉淀有实质内容的回答）
    if reply and not reply.startswith("系统暂时繁忙") and not reply.startswith("Service temporarily") and not reply.startswith("抱歉"):
        save_pending_faq(user_input, reply, history)

    return {"response": reply, "intent": "general"}
