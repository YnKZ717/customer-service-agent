# Neowow 智能客服 Agent

基于 LangGraph 的 Neowow Studio 平台智能客服系统，支持 FAQ 知识库问答、文档片段检索和大模型兜底回答。

## 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 配置 API Key
```bash
# 复制配置文件
cp .env.example .env
# 编辑 .env，填入你的 DeepSeek API Key
```

### 3. 启动客服界面
```bash
streamlit run streamlit_app.py
```
浏览器自动打开 `http://localhost:8501`

## 功能特性

### 三层搜索架构
```
用户提问
  ↓
FAQ 知识库（关键词 + 向量混合搜索）
  ├─ 命中 → 直接返回标准答案
  └─ 未命中
       ↓
    文档片段搜索（Chunk RAG）
       ├─ 命中 → 片段作为参考，大模型生成回答
       └─ 未命中
            ↓
         大模型兜底（三层 system prompt）
```

### 问题沉淀机制
用户提出的问题如果知识库没有，系统会自动记录到待确认队列。运营人员可以在后台审核，批准后自动加入知识库并重建向量索引。

### 管理后台
- 查看待确认 FAQ 提案
- 一键批准/拒绝
- 查看现有知识库内容

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| Agent 框架 | LangGraph | 状态机流程控制 |
| 向量数据库 | ChromaDB | 本地向量存储与搜索 |
| 向量模型 | text2vec-base-chinese | 中文文本向量化 |
| 大模型 | DeepSeek (deepseek-chat) | 兜底回答与答案提炼 |
| 前端框架 | Streamlit | 网页聊天界面 + 管理后台 |
| 配置管理 | python-dotenv | API Key 管理 |

## 项目结构

```
客服agent/
├── streamlit_app.py    # Streamlit 前端（聊天 + 管理后台）
├── app.py              # Gradio 前端（备用）
├── main.py             # 命令行版本
├── graph.py            # LangGraph 状态机流程定义
── nodes.py            # 节点逻辑（意图识别、知识库、大模型）
├── tools_vector.py     # FAQ 知识库 + 混合搜索 + 沉淀机制
├── tools_chunk.py      # 文档切块 + 向量搜索
├── tools.py            # 关键词搜索（备用）
├── config.py           # 配置文件
├── .env.example        # 环境变量模板
├── requirements.txt    # 依赖列表
└── README.md           # 本文件
```

## 后续规划

- [ ] 部署到服务器（内网/公网）
- [ ] 对接工单系统（转人工）
- [ ] 用户满意度反馈
- [ ] 对话数据持久化（数据库）
- [ ] 调用成本统计

## 许可证

内部项目，仅限 Neowow 团队使用。
