"""工具函数 — 向量搜索版知识库（带类别过滤）"""
import chromadb
import numpy as np
from text2vec import SentenceModel

# 加载中文向量化模型（比英文模型对中文支持好很多）
model = SentenceModel('shibing624/text2vec-base-chinese')

# 创建向量数据库客户端
client = chromadb.Client()
collection = client.create_collection("faq_knowledge")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 你的任务：
# 1. 把每条FAQ的类别填对（account/billing/codingplan等）
# 2. 在第12、13条填你自己想的FAQ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FAQ_DATA = [
    # (问题, 答案, 类别)
    # 第1条：注册登录
    ("怎么注册账号", "访问Neowow官网 https://app.neowow.studio，点击右上角'登录'按钮，使用账号完成登录授权。注册成功后即可使用平台功能。", "account"),

    # 第2条：积分充值
    ("怎么充值积分", "点击右上角'加号'按钮，选择充值金额，点击'生成二维码'，手机扫码支付即可。积分到账后可用于购买套餐和调用模型。", "billing"),

    # 第2.1条：充值变体
    ("我要充值", "点击右上角'加号'按钮，选择充值金额，点击'生成二维码'，手机扫码支付即可。积分到账后可用于购买套餐和调用模型。", "billing"),

    # 第3条：CodingPlan套餐
    ("CodingPlan是什么", "CodingPlan是智能体套餐，提供模型调用额度。购买后可在账户中心查看Credits使用情况，支持现金或积分购买。", "codingplan"),

    # 第4条：智能体服务
    ("怎么使用智能体", "进入'智能体'模块，可领取云端服务器试用资格，或订阅CodingPlan套餐。购买后即可与智能体对话创作。", "agent_service"),

    # 第5条：桌面客户端
    ("桌面客户端怎么安装", "在智能体界面下载客户端，解压后双击图标自动安装。使用网页端账号登录，模型额度来自网页端订阅。", "desktop"),

    # 第6条：应用市场
    ("应用市场怎么用", "进入应用市场可浏览、购买、预览应用。点击'在线预览'无需安装即可体验。也可上传自己开发的应用。", "app_market"),

    # 第7条：技能市场
    ("技能市场在哪", "技能市场提供各类创作技能，可在网页端和桌面客户端使用。网页端订阅的技能自动同步至客户端。", "skill_market"),

    # 第8条：部署Token
    ("部署Token怎么获取", "点击用户头像→'部署Token'→'生成Token'。用于在CI/CD流水线中部署发布应用，无需浏览器环境。", "deploy_token"),

    # 第9条：数据备份
    ("对话记录会丢失吗", "不会。客户端产生的对话与配置数据自动备份至云端，可在网页端查看与恢复，保障数据安全。", "backup"),

    # 第10条：会员权益
    ("会员有什么权益", "会员享受：智能体云端服务、CodingPlan套餐额度、应用市场特权、技能同步、云端数据备份等。详情见智能体界面。", "membership"),

    # 第11条：投诉
    ("我要投诉", "非常抱歉给您带来不好的体验。请详细描述您遇到的问题，我们会尽快处理。如需人工客服，请输入'转人工'。", "complaint"),

    # 第12条：注销账户
    ("怎么注销账户", "如需注销账户，请在账户中心提交注销申请，或联系人工客服处理。注销后数据将无法恢复，请谨慎操作。", "account"),
]

# ── 加载已批准的FAQ（从文件）──────────────────────────
APPROVED_FAQ_FILE = "approved_faqs.json"


def load_approved_faqs():
    """从文件加载已批准的FAQ"""
    import json
    try:
        with open(APPROVED_FAQ_FILE, 'r', encoding='utf-8') as f:
            approved = json.load(f)
            # 转成 FAQ_DATA 格式 (问题, 答案, 类别)
            return [(a['question'], a['answer'], a.get('category', 'approved')) for a in approved]
    except FileNotFoundError:
        return []


# 合并硬编码FAQ和已批准的FAQ
FAQ_DATA.extend(load_approved_faqs())


def init_knowledge_base():
    """初始化知识库：把FAQ转成向量存进数据库"""
    existing = collection.get()
    if existing['ids']:
        collection.delete(ids=existing['ids'])

    for i, (question, answer, category) in enumerate(FAQ_DATA):
        if question and answer and category:
            vector = model.encode(question).tolist()
            collection.add(
                ids=[f"faq_{i}"],
                embeddings=[vector],
                documents=[answer],
                metadatas=[{"question": question, "category": category}]
            )
    print(f"知识库初始化完成，共 {len([f for f in FAQ_DATA if f[0]])} 条FAQ")


# ── 关键词索引（与向量搜索互补）──────────────────────────
KEYWORD_INDEX = {}
for i, (question, answer, category) in enumerate(FAQ_DATA):
    for char in question:
        if char not in KEYWORD_INDEX:
            KEYWORD_INDEX[char] = []
        KEYWORD_INDEX[char].append(i)


def keyword_search(query: str, top_k: int = 3) -> list[int]:
    """关键词搜索：查找连续2字以上子串匹配的FAQ

    避免"你是谁"匹配"CodingPlan是什么"这种误匹配
    """
    if not query or len(query) < 2:
        return []

    # 提取所有2字连续子串
    query_bigrams = set()
    for i in range(len(query) - 1):
        query_bigrams.add(query[i:i+2])

    # 统计每个FAQ命中的bigram数量
    scores = {}
    for faq_idx, (question, _, _) in enumerate(FAQ_DATA):
        if not question:
            continue
        hit_count = 0
        for bigram in query_bigrams:
            if bigram in question:
                hit_count += 1
        if hit_count > 0:
            scores[faq_idx] = hit_count

    # 按分数排序，至少命中1个bigram
    sorted_indices = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [idx for idx, score in sorted_indices[:top_k] if score >= 1]


def search_knowledge_base(query: str, intent: str = None, threshold: float = 0.8, return_reference: bool = False) -> tuple[str, str, str]:
    """混合搜索：关键词 + 向量双路

    策略：
    1. 关键词搜索找候选（连续2字子串匹配）
    2. 向量搜索计算相似度
    3. 关键词命中的候选，向量相似度阈值降到0.6
    4. 向量命中的候选，阈值保持0.8
    """
    query_vector = model.encode(query)

    # ─ 向量搜索（取top5，给关键词更多候选）────────────────
    vector_results = collection.query(
        query_embeddings=[query_vector.tolist()],
        n_results=5,
        include=['distances', 'documents', 'metadatas', 'embeddings'],
    )

    # ─ 关键词搜索（连续2字子串）────────────────────────────
    keyword_indices = keyword_search(query, top_k=5)

    # ── 合并结果（去重）────────────────────────────────────
    seen_questions = set()
    merged_results = []

    # 先加关键词命中的（标记来源）
    for idx in keyword_indices:
        if idx < len(FAQ_DATA):
            q, a, c = FAQ_DATA[idx]
            if q and q not in seen_questions:
                merged_results.append({"question": q, "answer": a, "source": "keyword"})
                seen_questions.add(q)

    # 再加向量命中的
    if vector_results.get('documents') and vector_results['documents'][0]:
        for i in range(min(5, len(vector_results['documents'][0]))):
            q = vector_results['metadatas'][0][i]['question']
            a = vector_results['documents'][0][i]
            if q and q not in seen_questions:
                merged_results.append({"question": q, "answer": a, "source": "vector"})
                seen_questions.add(q)

    if not merged_results:
        return None, None, ""

    # ── 计算向量相似度 ─────────────────────────────────────
    similarities = {}
    if vector_results.get('embeddings') and len(vector_results['embeddings'][0]) > 0:
        for i, result in enumerate(merged_results):
            if i < len(vector_results['embeddings'][0]):
                doc_vector = np.array(vector_results['embeddings'][0][i])
                sim = np.dot(query_vector, doc_vector) / (np.linalg.norm(query_vector) * np.linalg.norm(doc_vector))
                similarities[result['question']] = sim
            else:
                similarities[result['question']] = 0.0

    # ── 判断是否匹配 ───────────────────────────────────────
    # 关键词命中的，阈值降到0.6；向量命中的，阈值0.8
    best_match = None
    for result in merged_results:
        sim = similarities.get(result['question'], 0.0)
        required_sim = 0.6 if result['source'] == 'keyword' else 0.8
        if sim >= required_sim:
            best_match = result
            break

    # ── 构建参考文本 ───────────────────────────────────────
    reference_parts = [f"Q: {r['question']}\nA: {r['answer']}" for r in merged_results[:3]]
    reference_text = "\n\n".join(reference_parts)

    if best_match:
        return best_match['question'], best_match['answer'], reference_text if return_reference else ""

    return None, None, reference_text if return_reference else ""


# ─ 沉淀机制：未匹配的问题记录到待确认队列 ──
PENDING_FAQ_FILE = "pending_faqs.json"


def refine_answer(question: str, raw_answer: str) -> str:
    """用大模型把啰嗦的答案提炼成简洁FAQ格式"""
    from openai import OpenAI
    from config import LLM_CONFIG

    client = OpenAI(
        api_key=LLM_CONFIG["api_key"],
        base_url=LLM_CONFIG["base_url"],
    )

    messages = [
        {"role": "system", "content": "你是FAQ编辑。把客服回答提炼成简洁、准确的一句话答案（50字以内），去掉客套话和重复内容。"},
        {"role": "user", "content": f"问题：{question}\n原始回答：{raw_answer}\n\n请提炼成一句话答案："}
    ]

    try:
        response = client.chat.completions.create(
            model=LLM_CONFIG["model_name"],
            messages=messages,
            max_tokens=100,
            temperature=0.3,
        )
        refined = response.choices[0].message.content.strip()
        # 去掉可能的引号
        if refined.startswith('"') and refined.endswith('"'):
            refined = refined[1:-1]
        return refined
    except Exception as e:
        print(f"[提炼失败] {e}")
        return raw_answer  # 失败就用原始答案


def save_pending_faq(question: str, llm_answer: str, history: list = None):
    """保存未匹配的问题到待确认队列（自动提炼答案）"""
    import json
    from datetime import datetime

    # 读取现有队列
    pending = []
    try:
        with open(PENDING_FAQ_FILE, 'r', encoding='utf-8') as f:
            pending = json.load(f)
    except FileNotFoundError:
        pass

    # 检查是否已存在相同问题
    for p in pending:
        if p['question'] == question:
            print(f"[沉淀] 问题已存在，跳过：{question}")
            return

    # 提炼答案
    refined_answer = refine_answer(question, llm_answer)

    # 添加新提案
    proposal = {
        "question": question,
        "answer": refined_answer,
        "original_answer": llm_answer,  # 保留原始答案供参考
        "history": history[-4:] if history else [],  # 最近2轮上下文
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "status": "pending",  # pending / approved / rejected
    }
    pending.append(proposal)

    # 写回文件
    with open(PENDING_FAQ_FILE, 'w', encoding='utf-8') as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)

    print(f"[沉淀] 新问题已记录：{question}")


def load_pending_faqs() -> list:
    """加载待确认的 FAQ 提案"""
    import json
    try:
        with open(PENDING_FAQ_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def approve_pending_faq(index: int) -> bool:
    """批准提案，持久化到文件并重建向量索引"""
    import json
    pending = load_pending_faqs()
    if index < 0 or index >= len(pending):
        return False

    proposal = pending[index]
    if proposal['status'] == 'approved':
        print(f"该提案已批准")
        return False

    # 保存到已批准文件
    approved = []
    try:
        with open(APPROVED_FAQ_FILE, 'r', encoding='utf-8') as f:
            approved = json.load(f)
    except FileNotFoundError:
        pass

    approved.append({
        "question": proposal['question'],
        "answer": proposal['answer'],
        "category": 'approved'
    })
    with open(APPROVED_FAQ_FILE, 'w', encoding='utf-8') as f:
        json.dump(approved, f, ensure_ascii=False, indent=2)

    # 标记为已批准
    proposal['status'] = 'approved'
    with open(PENDING_FAQ_FILE, 'w', encoding='utf-8') as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)

    print(f"已批准：{proposal['question']}")

    # 重建向量索引
    init_knowledge_base()
    print(f"向量索引已重建，共 {len([f for f in FAQ_DATA if f[0]])} 条FAQ")
    return True


def reject_pending_faq(index: int) -> bool:
    """拒绝提案"""
    import json
    pending = load_pending_faqs()
    if index < 0 or index >= len(pending):
        return False

    proposal = pending[index]
    if proposal['status'] == 'rejected':
        print(f"该提案已拒绝")
        return False

    proposal['status'] = 'rejected'
    with open(PENDING_FAQ_FILE, 'w', encoding='utf-8') as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)

    print(f"已拒绝：{proposal['question']}")
    return True


def transfer_to_human(user_input: str, history: list) -> dict:
    """转接人工客服，生成工单信息"""
    ticket_id = f"TK-{hash(user_input) % 10000:04d}"
    summary = user_input[:50]
    return {
        "response": f"已为您转接人工客服，工单号：{ticket_id}。客服将尽快与您联系。",
        "ticket_id": ticket_id,
        "ticket_summary": summary,
    }


# 初始化知识库
init_knowledge_base()
