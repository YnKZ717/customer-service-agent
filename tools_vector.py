"""工具函数 — 向量搜索版知识库（带类别过滤）"""
import os
import chromadb
import numpy as np
from text2vec import SentenceModel

# 项目根目录（tools_vector.py 所在目录），用于构建绝对路径
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# 加载中文向量化模型（比英文模型对中文支持好很多）
model = SentenceModel('shibing624/text2vec-base-chinese')

# 创建向量数据库客户端
client = chromadb.Client()
collection = client.create_collection("faq_knowledge")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 硬编码 FAQ（基础类别定义）
# approved_faqs.json 中的内容会自动合并进来
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FAQ_DATA = [
    # 类别映射说明：
    # account          - 账户管理（注册、注销、换绑、监控日志）
    # billing          - 充值支付（积分、Credits、购买记录、用量明细）
    # codingplan       - 套餐服务（CodingPlan、会员权益）
    # agent_service    - 智能体使用（免费试用、使用智能体）
    # desktop          - 桌面客户端（安装、在线文档）
    # app_market       - 应用市场（浏览、购买、上传）
    # skill_market     - 技能市场（收藏、复制）
    # deploy_token     - 部署 Token（CI/CD 发布）
    # backup           - 数据备份（对话记录、云端备份）
    # complaint        - 投诉反馈
    # team             - 团队协作（邀请、加入）
    # export           - 作品导出
    # api              - API 接口
    # video_generation - 视频生成（参数、格式、故障排查）
    # image_generation - 图片生成（风格、分辨率、批量）
    # audio_processing - 音频处理（配音、音乐、转录）
    # project_management - 项目管理（工作流、权限）
]

# ── 加载已批准的FAQ（从文件）──────────────────────────
# 使用绝对路径，避免从不同目录运行时路径解析错误
APPROVED_FAQ_FILE = os.path.join(_PROJECT_ROOT, "approved_faqs.json")


def load_approved_faqs():
    """从文件加载已批准的FAQ"""
    import json
    try:
        with open(APPROVED_FAQ_FILE, 'r', encoding='utf-8') as f:
            approved = json.load(f)
            # 转成 FAQ_DATA 格式 (问题, 答案, 类别, 图片列表)
            return [(a['question'], a['answer'], a.get('category', 'approved'), a.get('images', [])) for a in approved]
    except FileNotFoundError:
        return []


# 合并硬编码FAQ和已批准的FAQ
FAQ_DATA.extend(load_approved_faqs())


def init_knowledge_base():
    """初始化知识库：把FAQ转成向量存进数据库"""
    existing = collection.get()
    if existing['ids']:
        collection.delete(ids=existing['ids'])

    for i, item in enumerate(FAQ_DATA):
        # 支持3元素和4元素元组（向后兼容）
        if len(item) == 4:
            question, answer, category, images = item
        else:
            question, answer, category = item
            images = []

        if question and answer and category:
            vector = model.encode(question).tolist()
            metadata = {"question": question, "category": category}
            if images:
                metadata["images"] = ",".join(images)  # ChromaDB 不支持 list，用逗号分隔
            collection.add(
                ids=[f"faq_{i}"],
                embeddings=[vector],
                documents=[answer],
                metadatas=[metadata]
            )
    print(f"知识库初始化完成，共 {len([f for f in FAQ_DATA if f[0]])} 条FAQ")


# ── 关键词索引（与向量搜索互补）──────────────────────────
KEYWORD_INDEX = {}
for i, item in enumerate(FAQ_DATA):
    question = item[0]
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
    for faq_idx, item in enumerate(FAQ_DATA):
        question = item[0]
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


def search_knowledge_base(query: str, intent: str = None, threshold: float = 0.55, return_reference: bool = False) -> tuple:
    """混合搜索：关键词 + 向量双路

    策略：
    1. 关键词搜索找候选（连续2字子串匹配）
    2. 向量搜索计算相似度
    3. 关键词命中的候选，向量相似度阈值降到0.6
    4. 向量命中的候选，阈值保持0.8

    返回: (question, answer, reference_text, images)
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
            item = FAQ_DATA[idx]
            q, a, c = item[0], item[1], item[2]
            images = item[3] if len(item) > 3 else []
            if q and q not in seen_questions:
                merged_results.append({"question": q, "answer": a, "source": "keyword", "images": images})
                seen_questions.add(q)

    # 再加向量命中的
    if vector_results.get('documents') and vector_results['documents'][0]:
        for i in range(min(5, len(vector_results['documents'][0]))):
            q = vector_results['metadatas'][0][i]['question']
            a = vector_results['documents'][0][i]
            # 从 FAQ_DATA 中找对应的 images
            images = []
            for item in FAQ_DATA:
                if item[0] == q:
                    images = item[3] if len(item) > 3 else []
                    break
            if q and q not in seen_questions:
                merged_results.append({"question": q, "answer": a, "source": "vector", "images": images})
                seen_questions.add(q)

    if not merged_results:
        return None, None, "", []

    # ── 计算向量相似度 ────────────────────────────────────
    # 重新向量化每个候选问题，计算与 query 的相似度
    similarities = {}
    for result in merged_results:
        doc_vector = model.encode(result['question'])
        sim = np.dot(query_vector, doc_vector) / (np.linalg.norm(query_vector) * np.linalg.norm(doc_vector))
        similarities[result['question']] = sim

    # ── 判断是否匹配 ───────────────────────────────────────
    # 关键词命中的，阈值降到0.6；向量命中的，阈值0.8
    best_match = None
    for result in merged_results:
        sim = similarities.get(result['question'], 0.0)
        required_sim = 0.65
        if sim >= required_sim:
            best_match = result
            break

    # ── 构建参考文本 ───────────────────────────────────────
    reference_parts = [f"Q: {r['question']}\nA: {r['answer']}" for r in merged_results[:3]]
    reference_text = "\n\n".join(reference_parts)

    if best_match:
        return best_match['question'], best_match['answer'], reference_text if return_reference else "", best_match.get('images', [])

    return None, None, reference_text if return_reference else "", []


# ─ 沉淀机制：自动 FAQ 系统 ──
# 使用绝对路径，避免从不同目录运行时路径解析错误
PENDING_FAQ_FILE = os.path.join(_PROJECT_ROOT, "pending_faqs.json")

# 敏感词列表（命中后标记人工优先）
SENSITIVE_KEYWORDS = ["投诉", "退费", "退款", "维权", "举报", "法律", "起诉", "欺诈", "骗子"]

# 自动批准阈值（被问≥N 次自动入库）
AUTO_APPROVE_THRESHOLD = 2


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


def is_sensitive(question: str) -> bool:
    """检测是否包含敏感词"""
    return any(kw in question for kw in SENSITIVE_KEYWORDS)


def find_similar_pending(question: str, pending: list, threshold: float = 0.7) -> int:
    """在 pending 列表中找相似问题，返回索引（-1 表示没找到）"""
    if not pending or not question:
        return -1

    # 向量化
    q_vector = model.encode(question)

    # 找最相似的
    best_idx = -1
    best_sim = 0

    for i, p in enumerate(pending):
        if p.get("status") in ["approved", "rejected"]:
            continue  # 跳过已处理的

        p_vector = model.encode(p["question"])
        sim = np.dot(q_vector, p_vector) / (np.linalg.norm(q_vector) * np.linalg.norm(p_vector))

        if sim > best_sim:
            best_sim = sim
            best_idx = i

    if best_sim >= threshold:
        return best_idx
    return -1


def load_pending_faqs() -> list:
    """加载待确认的 FAQ 提案"""
    import json
    try:
        with open(PENDING_FAQ_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save_pending_faq(question: str, llm_answer: str, history: list = None):
    """自动 FAQ 系统：智能去重 + 频次统计 + 自动批准"""
    import json
    from datetime import datetime

    # 读取现有队列
    pending = []
    try:
        with open(PENDING_FAQ_FILE, 'r', encoding='utf-8') as f:
            pending = json.load(f)
    except FileNotFoundError:
        pass

    # 1. 找相似问题（向量去重）
    similar_idx = find_similar_pending(question, pending, threshold=0.8)

    if similar_idx >= 0:
        # 相似问题已存在，计数 +1，更新答案
        pending[similar_idx]["count"] = pending[similar_idx].get("count", 1) + 1
        pending[similar_idx]["last_asked"] = datetime.now().strftime("%Y-%m-%d %H:%M")

        # 保留最新答案（更准确）
        refined_answer = refine_answer(question, llm_answer)
        pending[similar_idx]["answer"] = refined_answer
        pending[similar_idx]["original_answer"] = llm_answer

        print(f"[自动 FAQ] 相似问题合并：'{question}' → '{pending[similar_idx]['question']}' (计数：{pending[similar_idx]['count']})")

        # 2. 检查是否达到自动批准阈值
        if pending[similar_idx]["count"] >= AUTO_APPROVE_THRESHOLD:
            if not pending[similar_idx].get("auto_approved", False):
                # 自动批准
                pending[similar_idx]["status"] = "approved"
                pending[similar_idx]["auto_approved"] = True
                pending[similar_idx]["approved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

                # 添加到已批准文件
                approved = []
                try:
                    with open(APPROVED_FAQ_FILE, 'r', encoding='utf-8') as f:
                        approved = json.load(f)
                except FileNotFoundError:
                    pass

                approved.append({
                    "question": pending[similar_idx]["question"],
                    "answer": pending[similar_idx]["answer"],
                    "category": "auto_approved"
                })
                with open(APPROVED_FAQ_FILE, 'w', encoding='utf-8') as f:
                    json.dump(approved, f, ensure_ascii=False, indent=2)

                # 增量添加到向量索引
                new_id = f"faq_auto_{len(approved) - 1}"
                new_vector = model.encode(pending[similar_idx]["question"]).tolist()
                collection.add(
                    ids=[new_id],
                    embeddings=[new_vector],
                    documents=[pending[similar_idx]["answer"]],
                    metadatas=[{"question": pending[similar_idx]["question"], "category": "auto_approved"}]
                )

                FAQ_DATA.append((pending[similar_idx]["question"], pending[similar_idx]["answer"], "auto_approved"))

                print(f"[自动 FAQ] ✅ 自动批准：'{pending[similar_idx]['question']}' (被问{pending[similar_idx]['count']}次)")

        # 写回文件
        with open(PENDING_FAQ_FILE, 'w', encoding='utf-8') as f:
            json.dump(pending, f, ensure_ascii=False, indent=2)
        return

    # 3. 新问题，创建提案
    refined_answer = refine_answer(question, llm_answer)
    sensitive = is_sensitive(question)

    proposal = {
        "question": question,
        "answer": refined_answer,
        "original_answer": llm_answer,
        "count": 1,
        "first_asked": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "last_asked": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "history": history[-4:] if history else [],
        "status": "pending",
        "sensitive": sensitive,  # 敏感词标记
        "auto_approved": False,
    }

    # 敏感问题标记"人工优先"
    if sensitive:
        proposal["priority"] = "high"
        proposal["reason"] = "包含敏感词，建议人工审核"
        print(f"[自动 FAQ] ⚠️ 敏感问题：'{question}' → 标记人工优先")
    else:
        proposal["priority"] = "normal"

    pending.append(proposal)

    # 写回文件
    with open(PENDING_FAQ_FILE, 'w', encoding='utf-8') as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)

    print(f"[自动 FAQ]  新问题：'{question}' (计数：1)")


def approve_pending_faq(index: int) -> bool:
    """手动批准提案，持久化到文件并增量添加向量索引"""
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

    # 增量添加到向量索引
    new_id = f"faq_manual_{len(approved) - 1}"
    new_vector = model.encode(proposal['question']).tolist()
    collection.add(
        ids=[new_id],
        embeddings=[new_vector],
        documents=[proposal['answer']],
        metadatas=[{"question": proposal['question'], "category": "approved"}]
    )

    FAQ_DATA.append((proposal['question'], proposal['answer'], 'approved'))

    print(f"向量索引已增量更新，共 {len([f for f in FAQ_DATA if f[0]])} 条FAQ")
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
