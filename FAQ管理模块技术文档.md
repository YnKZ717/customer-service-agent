# FAQ 管理与问题沉淀机制 — 技术文档

## 一、概述

本文档描述 Neowow 智能客服 Agent 中的 **FAQ 管理** 和 **问题沉淀机制** 的设计与实现。

系统的核心目标是让知识库**越用越多、越用越准**：用户提出知识库中没有的问题时，系统自动记录为"待确认提案"，运营人员审核后将其加入知识库，下次同样的问题就能直接命中标准答案。

---

## 二、系统架构

### 2.1 数据流转

```
用户提问
    ↓
┌─────────────────────────────────┐
│  第一层：FAQ 知识库搜索           │
│  （关键词 + 向量混合搜索）         │
│  命中 → 直接返回标准答案           │
└──────────────┬──────────────────┘
               │ 未命中
               ↓
┌─────────────────────────────────┐
│  第二层：文档片段搜索（Chunk）     │
│  （从使用说明书中切块检索）         │
│  命中 → 片段作为参考传给大模型      │
└──────────────┬──────────────────┘
               │ 未命中
               ↓
┌─────────────────────────────────┐
│  第三层：大模型兜底回答            │
│  （三层 system prompt）           │
│  回答完成后 → 自动触发沉淀         │
└──────────────┬──────────────────┘
               │
               ↓
┌─────────────────────────────────┐
│  沉淀机制：问题 + 答案 → 待确认队列 │
│  运营人员审核 → 批准/拒绝          │
│  批准 → 写入 approved_faqs.json   │
│         → 重建向量索引             │
│         → 下次搜索直接命中          │
└─────────────────────────────────┘
```

### 2.2 核心文件

| 文件 | 职责 |
|------|------|
| `tools_vector.py` | FAQ 知识库 + 混合搜索 + 沉淀机制（核心） |
| `tools_chunk.py` | 文档切块 + 向量搜索 |
| `nodes.py` | Agent 节点逻辑（意图识别、知识库回答、大模型回复） |
| `graph.py` | LangGraph 状态机流程定义 |
| `streamlit_app.py` | Streamlit 前端（聊天页 + FAQ 管理后台） |
| `pending_faqs.json` | 待确认提案数据文件 |
| `approved_faqs.json` | 已批准的 FAQ 数据文件 |

---

## 三、FAQ 知识库

### 3.1 FAQ 数据来源

FAQ 数据有两个来源：

1. **硬编码 FAQ**（`FAQ_DATA`）：在 `tools_vector.py` 中手动维护的标准问答对
2. **已批准的 FAQ**（`approved_faqs.json`）：运营人员通过沉淀机制审核批准的问题

系统启动时自动合并两者：

```python
# 加载已批准的FAQ（从文件）
FAQ_DATA.extend(load_approved_faqs())
```

### 3.2 FAQ 数据结构

每条 FAQ 是一个三元组：

```python
(问题, 答案, 类别)
```

| 字段 | 说明 | 示例 |
|------|------|------|
| 问题 | 用户可能问的问题 | "怎么充值积分" |
| 答案 | 标准回答 | "点击右上角'加号'按钮..." |
| 类别 | 问题分类 | "billing" |

### 3.3 混合搜索机制

FAQ 搜索同时使用**关键词搜索**和**向量搜索**两条路径：

#### 关键词搜索（keyword_search）

- 提取用户问题的**连续2字子串（bigram）**
- 统计每个 FAQ 问题中命中的 bigram 数量
- 按命中数量排序，取 top-k 候选

```python
# "怎么充值" → bigrams: {"怎么", "么充", "充值"}
# 命中 FAQ "怎么充值积分"（包含"怎么"和"充值"）
```

#### 向量搜索（ChromaDB）

- 使用 `text2vec-base-chinese` 模型将文本转为向量
- 计算用户问题与 FAQ 的**余弦相似度**
- 阈值 0.8 以上视为精确匹配

#### 双路合并策略

| 来源 | 相似度阈值 | 说明 |
|------|-----------|------|
| 关键词命中 | ≥ 0.6 | 关键词匹配了，向量阈值放宽 |
| 向量命中 | ≥ 0.8 | 纯语义匹配，要求更高 |

---

## 四、文档切块（Chunk RAG）

### 4.1 切块方法

使用**按段落切块**，每块最多 300 字符。超长段落按句子边界强制切分。

```python
def chunk_by_paragraph(text: str, max_chars: int = 300) -> list[str]:
    # 按空行分段落
    paragraphs = text.strip().split('\n\n')
    # 超过 max_chars 的段落按句号切分
    ...
```

### 4.2 文档内容

当前 Chunk 知识库的内容来自 **Neowow Studio 使用说明书**，仅保留面向用户的操作说明部分，去除了技术架构描述等不面向用户的内容。

### 4.3 搜索流程

```
用户问题 → text2vec 向量化 → ChromaDB 搜索 → 计算余弦相似度 → 阈值 0.4 以上返回片段
```

搜索到的片段作为参考文本传给大模型，帮助大模型生成更准确的回答。

---

## 五、问题沉淀机制

### 5.1 核心设计思想

**知识库不可能覆盖所有问题。** 用户会提出各种各样的新问题，如果每次都走大模型，成本高且回答质量不稳定。

沉淀机制的核心思路：
1. 大模型回答新问题的同时，自动把问题和答案记录到待确认队列
2. 运营人员定期审核，批准质量好的问题加入知识库
3. 知识库越来越大，大模型调用越来越少，成本越来越低

### 5.2 沉淀流程

```
大模型回答问题
       ↓
  调用 save_pending_faq()
       ↓
  ① 检查是否已存在相同问题（去重）
       ↓
  ② 调用大模型提炼答案（50字以内简洁版）
       ↓
  ③ 写入 pending_faqs.json
       ↓
  运营人员审核
       ↓
  ④ 批准 → 写入 approved_faqs.json
           → 调用 init_knowledge_base() 重建向量索引
       ↓
   下次同样的问题 → 直接命中知识库
```

### 5.3 关键函数

#### save_pending_faq(question, answer, history)

- **触发时机**：大模型回答问题后自动调用
- **功能**：
  1. 去重检查：相同问题不重复记录
  2. 答案提炼：调用大模型将啰嗦的回答压缩为 50 字以内的简洁 FAQ 答案
  3. 写入 `pending_faqs.json`

#### refine_answer(question, raw_answer)

- **功能**：用大模型将原始回答提炼为简洁的 FAQ 格式答案
- **Prompt**："你是FAQ编辑。把客服回答提炼成简洁、准确的一句话答案（50字以内），去掉客套话和重复内容。"

#### approve_pending_faq(index)

- **功能**：
  1. 将提案写入 `approved_faqs.json`（持久化）
  2. 标记提案状态为 `approved`
  3. 重建向量索引（`init_knowledge_base()`）

#### reject_pending_faq(index)

- **功能**：标记提案状态为 `rejected`，不加入知识库

### 5.4 数据文件

#### pending_faqs.json

存储所有沉淀提案，每个提案结构：

```json
{
    "question": "怎么修改支付密码",
    "answer": "在Neowow官网或官方APP的安全设置中修改支付密码...",
    "original_answer": "您好！如需修改支付密码，请在账户中心...",
    "history": [["user", "..."], ["assistant", "..."]],
    "created_at": "2026-08-12 11:52",
    "status": "pending"
}
```

| 字段 | 说明 |
|------|------|
| question | 用户的问题 |
| answer | 提炼后的简洁答案 |
| original_answer | 大模型原始回答（供参考） |
| history | 对话上下文（最近2轮） |
| created_at | 记录时间 |
| status | pending / approved / rejected |

#### approved_faqs.json

存储已批准的 FAQ，系统启动时自动加载：

```json
[
    {
        "question": "API接口文档在哪看",
        "answer": "平台暂未开放API接口文档，如有需求请联系官方客服。",
        "category": "approved"
    }
]
```

### 5.5 管理后台（Streamlit）

FAQ 管理页面提供以下功能：

1. **待确认提案列表**：显示所有 pending 状态的提案
2. **逐条审核**：每条提案有"批准"和"拒绝"按钮
3. **查看原始回答**：可展开查看大模型的完整原始回答
4. **知识库浏览**：查看所有已入库的 FAQ

---

## 六、Agent 流程（LangGraph 状态机）

### 6.1 状态定义

```python
class AgentState(dict):
    user_input: str          # 当前用户输入
    intent: str              # 意图分类结果
    response: str            # 客服回复
    kb_found: bool           # FAQ知识库是否找到答案
    kb_reference: str        # FAQ知识库参考内容
    kb_category: str         # FAQ知识库匹配的分类
    chunk_found: bool        # Chunk文档片段是否找到
    chunk_reference: str     # Chunk文档片段参考内容
    history: list            # 对话历史
    ticket_id: str           # 工单号
    ticket_summary: str      # 工单摘要
```

### 6.2 流程节点

```
──────────┐
│ classify │ 意图识别（关键词匹配）
────┬─────┘
     │
     ├─ human ──→ handle_human ──→ END（转人工）
     │
     └─ 其他 ─→ answer_from_kb ─── kb_found=True → END（返回FAQ答案）
                                   │
                                   └─ kb_found=False → chunk_search
                                                          │
                                                          ├─ chunk_found=True → general_reply
                                                          │                     （带Chunk参考）
                                                          │
                                                          ─ chunk_found=False → general_reply
                                                                                 （纯大模型兜底）
                                                                                 → 触发沉淀
```

### 6.3 三层 System Prompt

大模型回复时使用动态组装的 system prompt：

```
第一层：人格（稳定层）
  → "你是 Neowow Studio 的智能客服助手。回答规则：..."

第二层：记忆（记忆层）
  → "对话历史（最近N轮）：..."

第三层：任务（任务层）
  → "FAQ参考：..."
  → "文档片段参考：..."
```

---

## 七、部署与运行

### 7.1 本地运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env，填入 DeepSeek API Key

# 3. 启动前端
streamlit run streamlit_app.py
```

### 7.2 环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| OPENAI_API_KEY | DeepSeek API 密钥 | sk-xxx |
| OPENAI_BASE_URL | API 地址 | https://api.deepseek.com/v1 |
| OPENAI_MODEL_NAME | 模型名称 | deepseek-chat |

### 7.3 依赖库

| 库 | 用途 |
|---|------|
| langgraph | Agent 状态机框架 |
| chromadb | 向量数据库 |
| text2vec | 中文文本向量化模型 |
| streamlit | 网页前端框架 |
| openai | 大模型 API 客户端 |
| python-dotenv | 环境变量管理 |

---

## 八、后续规划

### 8.1 权限控制（RBAC）

| 角色 | 权限 |
|------|------|
| 普通用户 | 只能使用客服聊天 |
| 运营人员 | 聊天 + FAQ管理后台 |
| 管理员 | 全部功能 |

阶段规划：原型不加 → 演示加简单登录 → 内网上线必须加 → 正式产品对接SSO

### 8.2 部署上线

- 部署到公司内网服务器
- 生成内网链接供全公司访问
- 嵌入 Neowow 网页右下角作为客服入口

### 8.3 功能增强

- 对接工单系统（转人工时自动通知运营）
- 对话数据持久化（MySQL/PostgreSQL）
- 用户满意度反馈
- 大模型调用成本统计
- FAQ 命中率统计

---

## 九、技术栈总览

| 组件 | 技术选型 | 说明 |
|------|---------|------|
| Agent 框架 | LangGraph | 状态机流程控制，节点+条件边 |
| 大模型 | DeepSeek (deepseek-chat) | 兜底回答 + 答案提炼 |
| 向量数据库 | ChromaDB | 本地向量存储与搜索 |
| 向量模型 | text2vec-base-chinese | 中文文本向量化 |
| 前端框架 | Streamlit | 网页聊天界面 + 管理后台 |
| 配置管理 | python-dotenv | API Key 管理 |
