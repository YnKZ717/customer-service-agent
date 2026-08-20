# 智能客服 Agent

个人学习练手项目，基于 LangGraph + FastAPI + Vue3 构建的多轮对话客服系统。

## 功能特性

### 核心对话
- **智能对话** — FAQ 知识库混合搜索（关键词 + 向量）+ 大模型兜底回答
- **多轮引导式故障排查** — 9 种排查流程（超分/支付/技能/画布等）+ LLM 引导追问
- **Tool Call** — 排查中自动调用工具查询任务状态、积分余额、会员信息
- **双 Agent 协作** — 主 Agent 生成，副 Agent 评估并自动修正（准确性/完整性/语气/安全）
- **自动 FAQ 沉淀** — 新问题自动记录，相似度去重，高频问题自动通过
- **工单管理** — 创建/回复/分页/搜索/删除
- **自动识别误伤** — 检测平台误伤并引导人工复核
- **多模态图片上传** — 用户可上传图片，模型识别截图内容后回答
- **五星评分** — 用户对每次回答进行 1-5 星评价

### 数据看板
- **指标卡片** — 总问答量、知识库命中率、模型降级次数、满意度
- **每日趋势图** — 知识库 vs LLM 调用量折线图
- **堆叠柱状图** — 知识库 vs LLM 每日分布
- **满意度分布** — 1-5 星评分柱状图
- **A/B 测试对比** — 策略分组调用次数 + 平均评分双轴图
- **每日明细表** — 调用/知识库/LLM/排查/命中率一览

### 管理功能
- **FAQ 管理** — 增删改查，删除持久化到文件
- **工单管理** — 全生命周期管理
- **管理员看板** — admin 角色可见数据看板

### 稳定性
- **模型降级** — 主模型失败自动切换备用模型，降级事件自动记录
- **图片压缩** — 超过 1MB 自动压缩到 1024px
- **多模型支持** — DeepSeek / 阿里云 DashScope / OpenAI / Ollama

## 技术栈

| 层面 | 技术 |
|------|------|
| 后端 | Python 3.12, FastAPI, LangGraph |
| 前端 | Vue3, TypeScript, Vite, Chart.js |
| 向量库 | ChromaDB, text2vec-base-chinese |
| 大模型 | OpenAI 兼容接口（DeepSeek/阿里云 DashScope/OpenAI/Ollama 等，支持多模型降级） |
| 认证 | JWT (PyJWT) |

## 项目结构

```
客服agent/
├── backend/
│   └── main.py              # FastAPI 服务入口
├── frontend/
│   └── src/views/
│       ├── ChatView.vue      # 对话界面（含图片上传 + 五星评分）
│       ├── TicketsView.vue   # 工单管理
│       ├── AdminView.vue     # FAQ 管理
│       └── DashboardView.vue # 数据看板（admin 可见）
├── graph.py                  # LangGraph 工作流定义
├── nodes.py                  # 各节点逻辑（含主副 Agent）
├── troubleshoot_flows.py     # 排查流程决策树（9 种场景）
├── tools_vector.py           # 知识库搜索（关键词 + 向量）
├── tools_chunk.py            # Chunk 文档片段搜索
├── mock_tools.py             # 模拟工具（任务/积分/会员查询）
├── ab_test.py                # A/B 测试模块
├── agent_logger.py           # 结构化日志
├── ticket_utils.py           # 工单工具
├── auth.py                   # JWT 认证
├── config.py                 # 模型配置
└── approved_faqs.json        # 知识库
```

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 18+

### 安装

```bash
# 后端依赖
cd 客服agent/backend
pip install -r ../requirements.txt

# 前端依赖
cd ../frontend
npm install

# 配置 API Key（复制模板并填入你的 Key）
cp ../.env.example ../.env
# 编辑 .env 文件，填入你的 API 密钥
```

### API 配置

`.env` 文件支持任何兼容 OpenAI 格式的服务：

| 服务商 | BASE_URL | MODEL |
|--------|----------|-------|
| DeepSeek | https://api.deepseek.com/v1 | deepseek-chat |
| OpenAI | https://api.openai.com/v1 | gpt-4o |
| 本地 Ollama | http://localhost:11434/v1 | llama3 |
| 阿里云 DashScope | https://dashscope.aliyuncs.com/compatible-mode/v1 | qwen3.7-plus |

编辑 `.env` 文件，填入对应的 API Key 和 BASE_URL 即可。

### 启动

```bash
# 终端 1：后端
cd backend
python main.py
# 访问 http://localhost:8001

# 终端 2：前端
cd frontend
npm run dev
# 访问 http://localhost:5173
```

### 登录

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 管理员 | admin | admin123 |
| 客服 | support | support123 |
| 普通用户 | user | user123 |

### 打开项目文件夹并启动 CMD

**Windows 用户（推荐）：**

1. 打开文件资源管理器，进入项目文件夹 `客服agent/`
2. 在地址栏输入 `cmd` 按回车，会直接在该目录打开命令提示符
3. 或者：在文件夹空白处按住 `Shift` + 右键，选择「在此处打开命令窗口」

打开 CMD 后，按顺序执行：

```cmd
:: 启动后端（终端 1）
cd backend
python main.py

:: 另开一个 CMD，启动前端（终端 2）
cd frontend
npm run dev
```

**启动成功后：**
- 后端：http://localhost:8001 （API 服务）
- 前端：http://localhost:5173 （Web 界面）

在浏览器打开 http://localhost:5173 ，用上面的账号密码登录即可体验。

## 测试与评估

```bash
# 运行测试（17 条用例）
python test_agent.py

# LLM 自动修复
python auto_fix.py

# 一键闭环（测试→修复→重启→再测）
python run_loop.py
```

## 日志

### 两种查看方式

**方式一：后端终端（实时）**

后端运行时的终端窗口会实时打印主副 Agent 的工作状态：

```
[主Agent] kb_answer | 问题：怎么充值积分...
[主Agent] 知识库命中：充值方式
[主Agent] 回答：Neowow 提供支付宝/微信/银行卡...

[主Agent] general_reply | 问题：今天天气怎么样...
[主Agent] 回答：关于天气情况...
[副Agent] FIXED | 问题：今天天气怎么样...
[副Agent] 修正：我无法获取实时的天气信息...
```

**方式二：日志文件（历史记录）**

日志文件保存在 `logs/` 目录，JSON 格式，包含主副 Agent 每一步操作：

```cmd
powershell -Command "Get-ChildItem logs\*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content -Encoding UTF8 | Select-Object -Last 20"
```

这条命令的意思是：
1. 找到 `logs/` 下所有 `.log` 文件
2. 按修改时间降序排列，取最新的一个
3. 以 UTF8 编码读取内容
4. 显示最后 20 行

日志类型：
- `intent` — 意图识别
- `kb_lookup` — 知识库查询
- `kb_answer` — 知识库回答
- `general_reply` — 大模型兜底回复
- `evaluate` — 副 Agent 评估结果（PASS/FIXED）
- `flow_start` — 排查流程开始
- `tool_call` — 工具调用
- `branch` — 分支匹配
- `response` — 排查回复
