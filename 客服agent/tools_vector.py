"""工具函数 — 向量搜索版知识库（带类别过滤）"""
import os
import chromadb
import numpy as np

# 项目根目录（tools_vector.py 所在目录）
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ── 模型加载：BGE 优先，text2vec 兜底 ──────────────────────
_BGE_LOCAL = os.path.join(_PROJECT_ROOT, "models", "bge-large-zh-v1.5")
_TEXT2VEC_LOCAL = os.path.join(_PROJECT_ROOT, "models", "text2vec-base-chinese")

# 优先使用本地 BGE 模型（1024维，比 text2vec 更准）
if os.path.isdir(_BGE_LOCAL):
    _model_name = _BGE_LOCAL
    print(f"[向量模型] 使用 BGE (本地): {_BGE_LOCAL}")
elif os.path.isdir(_TEXT2VEC_LOCAL):
    _model_name = _TEXT2VEC_LOCAL
    print(f"[向量模型] 使用 text2vec (本地兜底): {_TEXT2VEC_LOCAL}")
else:
    _model_name = "BAAI/bge-large-zh-v1.5"
    print(f"[向量模型] 无本地模型，将从 HuggingFace 下载: {_model_name}")

from text2vec import SentenceModel
model = SentenceModel(_model_name)

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
    """从文件加载已批准的FAQ，支持 aliases 字段"""
    import json
    try:
        with open(APPROVED_FAQ_FILE, 'r', encoding='utf-8') as f:
            approved = json.load(f)
            result = []
            for a in approved:
                question = a['question']
                answer = a['answer']
                category = a.get('category', 'approved')
                images = a.get('images', [])
                aliases = a.get('aliases', [])  # 同义问题列表
                result.append((question, answer, category, images, aliases))
            return result
    except FileNotFoundError:
        return []


# 合并硬编码FAQ和已批准的FAQ
FAQ_DATA.extend(load_approved_faqs())

# 统一 FAQ_DATA 格式：全部补齐为 5 元组 (question, answer, category, images, aliases)
_normalized = []
for item in FAQ_DATA:
    if len(item) == 5:
        _normalized.append(item)
    elif len(item) == 4:
        q, a, c, img = item
        _normalized.append((q, a, c, img, []))
    elif len(item) == 3:
        q, a, c = item
        _normalized.append((q, a, c, [], []))
    else:
        _normalized.append(item)
FAQ_DATA.clear()
FAQ_DATA.extend(_normalized)


def init_knowledge_base():
    """初始化知识库：把 FAQ 的 问题+答案 拼接后转成向量存进数据库"""
    existing = collection.get()
    if existing['ids']:
        collection.delete(ids=existing['ids'])

    for i, item in enumerate(FAQ_DATA):
        if len(item) == 4:
            question, answer, category, images = item
        else:
            question, answer, category = item
            images = []

        if question and answer and category:
            # 拼接问题+答案一起向量化，利用答案中的详细信息提高召回率
            combined = f"{question} {answer}"
            vector = model.encode(combined).tolist()
            metadata = {"question": question, "category": category}
            if images:
                metadata["images"] = ",".join(images)
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


def keyword_search(query: str, top_k: int = 5) -> list[tuple[int, int]]:
    """关键词搜索：按连续2字子串匹配，返回 (索引, 命中数) 列表

    修复：直接在 FAQ 问题上做子串匹配，不依赖有 bug 的 KEYWORD_INDEX
    """
    if not query or len(query) < 2:
        return []

    # 提取所有2字连续子串
    query_bigrams = set()
    for i in range(len(query) - 1):
        query_bigrams.add(query[i:i+2])

    scores = []
    for faq_idx, item in enumerate(FAQ_DATA):
        question = item[0]
        if not question:
            continue
        hit_count = sum(1 for bg in query_bigrams if bg in question)
        if hit_count > 0:
            scores.append((faq_idx, hit_count))

    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:top_k]


def _pure_keyword_search(query: str, threshold_chars: int = 2) -> list[tuple[int, str]]:
    """纯关键词兜底搜索：检查 FAQ 问题中是否包含 query 中的关键子串
    返回 [(索引, 匹配到的子串), ...]"""
    if not query:
        return []
    # 提取2字以上的关键子串
    candidates = []
    for i in range(len(query)):
        for length in range(len(query) - i, 1, -1):
            substr = query[i:i+length]
            if length >= threshold_chars:
                for faq_idx, item in enumerate(FAQ_DATA):
                    q = item[0]
                    if q and substr in q:
                        candidates.append((faq_idx, substr))
    # 去重，保留最长匹配
    seen = set()
    result = []
    for idx, substr in sorted(candidates, key=lambda x: -len(x[1])):
        if idx not in seen:
            seen.add(idx)
            result.append((idx, substr))
    return result


def search_knowledge_base(query: str, intent: str = None, threshold: float = 0.5, return_reference: bool = False) -> tuple:
    """BGE 向量搜索 + 关键词兜底（双路独立评分，取最优）

    策略：
    1. BGE 向量搜索（索引的是 问题+答案）
    2. 关键词独立搜索（按最长匹配子串长度排序，过滤通用后缀）
    3. 两路各自取最佳，比较得分，取更优的
    4. 都没过阈值 → 返回参考文本给 LLM

    返回: (question, answer, reference_text, images)
    """
    # ── 过滤通用疑问后缀，提取核心关键词 ──
    COMMON_SUFFIXES = ["怎么办", "怎么处理", "如何解决", "怎么解决", "是什么", "怎么用", "为什么", "吗", "呢"]
    core_query = query
    for suffix in COMMON_SUFFIXES:
        if core_query.endswith(suffix):
            core_query = core_query[:-len(suffix)]
            break
    # 如果去掉后缀后太短，保留原 query
    if len(core_query) < 2:
        core_query = query

    # ── 关键词搜索：累计所有匹配子串的总长度（含 aliases）──
    kw_results = []  # (total_match_chars, faq_idx, best_substr)
    for i, item in enumerate(FAQ_DATA):
        faq_q = item[0]
        if not faq_q:
            continue
        aliases = item[4] if len(item) > 4 else []
        # 搜索文本：问题 + 所有 aliases
        search_texts = [faq_q] + aliases

        total_chars = 0
        best_substr = ""
        matched_ranges = []
        for length in range(len(core_query), 1, -1):
            for start in range(len(core_query) - length + 1):
                substr = core_query[start:start+length]
                end = start + length
                overlap = any(s <= start < e or s < end <= e for s, e in matched_ranges)
                if not overlap and any(substr in txt for txt in search_texts):
                    total_chars += length
                    matched_ranges.append((start, end))
                    if length > len(best_substr):
                        best_substr = substr
        if total_chars >= 2:
            kw_results.append((total_chars, i, best_substr))
    kw_results.sort(reverse=True)

    # ── BGE 向量搜索（问题+答案+aliases） ─────────────────
    query_vector = model.encode(query)
    vector_scores = []
    for i, item in enumerate(FAQ_DATA):
        faq_q = item[0]
        if not faq_q:
            continue
        aliases = item[4] if len(item) > 4 else []
        alias_text = " ".join(aliases)
        combined = f"{faq_q} {item[1]} {alias_text}"
        doc_vector = model.encode(combined)
        sim = np.dot(query_vector, doc_vector) / (np.linalg.norm(query_vector) * np.linalg.norm(doc_vector))
        vector_scores.append((sim, i))
    vector_scores.sort(reverse=True)

    # ── 两路各自取最佳，比较得分 ─────────────────────────
    best_kw_score = kw_results[0][0] if kw_results else 0  # 最长匹配字符数
    best_vec_sim = vector_scores[0][0] if vector_scores else 0  # 余弦相似度

    # 关键词得分归一化：4字匹配=0.8, 3字=0.6, 2字=0.4
    kw_normalized = best_kw_score * 0.2

    kw_winner = kw_results[0] if kw_results else None
    vec_winner = vector_scores[0] if vector_scores else None

    # 关键词赢了（关键词更可靠，因为字面匹配）
    if kw_winner and kw_normalized >= 0.4 and kw_normalized >= best_vec_sim:
        idx = kw_winner[1]
        item = FAQ_DATA[idx]
        question, answer = item[0], item[1]
        images = item[3] if len(item) > 3 else []
        ref_parts = [f"Q: {FAQ_DATA[idx2][0]} (关键词'{s}', len={sc})\nA: {FAQ_DATA[idx2][1]}" for sc, idx2, s in kw_results[:3]]
        ref_text = "\n\n".join(ref_parts)
        print(f"[关键词命中] '{question}' (核心词'{core_query}', 匹配'{kw_winner[2]}', kw={kw_normalized:.2f} vs vec={best_vec_sim:.3f})")
        return question, answer, ref_text if return_reference else "", images

    # 向量赢了
    if vec_winner and best_vec_sim >= threshold:
        idx = vec_winner[1]
        item = FAQ_DATA[idx]
        question, answer = item[0], item[1]
        images = item[3] if len(item) > 3 else []
        ref_parts = [f"Q: {FAQ_DATA[idx2][0]} (sim={s:.3f})\nA: {FAQ_DATA[idx2][1]}" for s, idx2 in vector_scores[:3]]
        ref_text = "\n\n".join(ref_parts)
        print(f"[BGE命中] '{question}' (sim={best_vec_sim:.3f} vs kw={kw_normalized:.2f})")
        return question, answer, ref_text if return_reference else "", images

    # ── 都没过阈值，返回参考文本给 LLM ──────────────────
    ref_parts = [f"Q: {FAQ_DATA[idx2][0]} (sim={s:.3f})\nA: {FAQ_DATA[idx2][1]}" for s, idx2 in vector_scores[:3]]
    ref_text = "\n\n".join(ref_parts) if ref_parts else ""
    print(f"[无匹配] kw={kw_normalized:.2f}, vec={best_vec_sim:.3f}，返回参考文本给 LLM")
    return None, None, ref_text if return_reference else "", []


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
