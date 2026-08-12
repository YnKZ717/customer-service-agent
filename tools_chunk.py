"""工具函数 — 文档切块版知识库（Chunk RAG）"""
import chromadb
import numpy as np
from text2vec import SentenceModel

# 复用 FAQ 的向量模型（保证向量空间一致）
model = SentenceModel('shibing624/text2vec-base-chinese')

# 创建独立的 chunk 向量数据库客户端
chunk_client = chromadb.Client()
chunk_collection = chunk_client.create_collection("chunk_knowledge")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Neowow Studio 使用说明书（仅面向用户的操作说明）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NEOWOW_MANUAL = """
Neowow Studio是一站式智能创意内容生产与协作平台，由"网页端云平台"与"桌面客户端"两部分组成。桌面客户端不提供独立注册，必须使用网页端账号登录。客户端调用LLM模型的额度由网页端订阅的CodingPlan套餐提供。网页端订阅的技能自动同步至客户端调用。客户端产生的对话与配置数据备份至云端，可在网页端查看与恢复。

网页端（https://app.neowow.studio）提供用户注册登录、账户与积分管理、CodingPlan套餐订阅、智能体云端服务、应用市场与技能市场等功能。用户既可在网页端直接使用，也可一键下载桌面客户端。

在浏览器中访问系统首页地址 https://app.neowow.studio 即可进入平台首页。首页右上角提供"登录"入口，点击后跳转至登录授权页面，用户通过账号完成登录授权后即可使用平台全部功能。

登录后，用户可在用户中心完成充值、账户信息查看、部署Token管理及安全监控日志查询等操作。

积分充值：在首页点击右上角的"加号"按钮，系统弹出充值窗口。用户选择充值金额后，点击"生成二维码"，手机扫描二维码完成在线支付，支付成功后积分自动充值到账户。

账户中心：在首页点击右上角的用户头像，弹出菜单包含账户中心、部署Token、监控日志等入口。点击"账户中心"可查看账号资料、积分余额、会员等级及可用模型等信息。

部署Token：点击菜单中的"部署Token"进入管理界面，点击"生成Token"即可创建。部署Token用于在无浏览器环境（如CI/CD流水线）中部署与发布应用。

监控日志：点击菜单中的"监控日志"，跳转至安全与监控日志界面，可查看账号的安全记录与操作监控日志。

智能体是平台的核心服务模块，提供云端服务器、CodingPlan套餐订阅、积分计量与桌面客户端下载等功能。在平台导航中点击"智能体"可进入智能体功能界面。

云端服务器试用：点击"免费试用"可领取云端服务器试用资格，领取后即可使用云端数据备份功能，将对话与配置数据备份至云端，并可下载历史聊天记录。

CodingPlan套餐订阅：点击"查看套餐"进入套餐选择界面，展示各档套餐的额度与价格信息。点击"订阅"后可选择使用现金或积分购买CodingPlan套餐，购买后获得对应的模型调用额度。

购买CodingPlan后，用户可在账户中心查看Credits（积分额度）的使用情况以及当前可用的模型列表。点击"用量明细"可查看详细的模型调用流水记录，包括每次调用的消耗情况。

桌面客户端下载：在智能体界面向下滑动找到桌面客户端下载入口，下载安装包后解压，双击桌面图标自动完成环境检测与安装。安装后使用网页端账号登录即可。桌面客户端的模型调用额度和会员权益均来自网页端的订阅与充值，未开通CodingPlan时仅能使用免费体验额度。

应用市场提供应用的浏览、购买、预览、分享、留言与上传等功能。进入应用市场可浏览各类应用并购买。点击某个应用可查看详细介绍，点击"在线预览"无需安装即可在线体验，点击"分享"可将应用分享给他人。在应用详情页可查看其他用户的留言评价，也可自行输入留言参与互动。点击"购买记录"可查看已购买的全部应用。点击"上传应用"可从本地选择文件上传发布。

技能市场提供智能体技能的浏览、订阅、收藏、查看、复制、评论与发布等功能。进入技能市场可查看各类技能，点击"订阅"即可订阅，订阅后技能同步到用户的智能体中。点击技能卡片右上角的五角星可收藏技能。点击技能可查看具体说明与功能介绍，在详情页可复制技能内容。在技能详情页下方可查看已有评论并发表评论。点击"发布技能"可从本地上传自己编写的技能发布到市场。

桌面客户端提供"帮助"入口，点击"帮助"打开帮助菜单，点击"在线文档"可跳转至网页端的开发者指南，查阅详细的使用与开发文档。
"""


def chunk_by_paragraph(text: str, max_chars: int = 300) -> list[str]:
    """按段落切块，超过max_chars的段落强制按句子切分"""
    # 先按空行分段落
    paragraphs = [p.strip() for p in text.strip().split('\n\n') if p.strip()]

    chunks = []
    for para in paragraphs:
        if len(para) <= max_chars:
            chunks.append(para)
        else:
            # 超长段落按句号切分，尽量保持句子完整
            sentences = para.replace('。', '。\n').replace('！', '！\n').replace('？', '？\n').split('\n')
            current_chunk = ""
            for sent in sentences:
                sent = sent.strip()
                if not sent:
                    continue
                if len(current_chunk) + len(sent) <= max_chars:
                    current_chunk += sent
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = sent
            if current_chunk:
                chunks.append(current_chunk)

    return chunks


def init_chunk_knowledge():
    """初始化chunk知识库：切块 + 向量化 + 存入ChromaDB"""
    # 清空旧数据
    existing = chunk_collection.get()
    if existing['ids']:
        chunk_collection.delete(ids=existing['ids'])

    chunks = chunk_by_paragraph(NEOWOW_MANUAL, max_chars=300)

    for i, chunk in enumerate(chunks):
        vector = model.encode(chunk).tolist()
        chunk_collection.add(
            ids=[f"chunk_{i}"],
            embeddings=[vector],
            documents=[chunk],
            metadatas=[{"chunk_id": i, "source": "neowow_manual"}]
        )

    print(f"Chunk知识库初始化完成，共 {len(chunks)} 个片段")


def search_chunks(query: str, top_k: int = 2, threshold: float = 0.4) -> list[str]:
    """搜索最相关的chunk片段

    Returns:
        匹配的片段列表（空列表表示没找到）
    """
    query_vector = model.encode(query).tolist()

    results = chunk_collection.query(
        query_embeddings=[query_vector],
        n_results=top_k,
        include=['distances', 'documents', 'embeddings'],
    )

    if not results['documents'] or not results['documents'][0]:
        return []

    matched = []
    for i in range(min(top_k, len(results['documents'][0]))):
        doc = results['documents'][0][i]
        distance = results['distances'][0][i]

        # 计算余弦相似度
        query_vec = np.array(query_vector)
        doc_vec = np.array(results['embeddings'][0][i])
        similarity = np.dot(query_vec, doc_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(doc_vec))

        if similarity >= threshold:
            matched.append(doc)

    return matched


# 初始化
init_chunk_knowledge()
