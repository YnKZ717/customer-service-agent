# 智能客服 Agent 交接文档

## 项目概述

基于 LangGraph + FastAPI + Vue3 构建的多轮对话客服系统，服务于 Neowow Studio（AIGC 内容创作平台）。

**核心价值：**
- FAQ 知识库混合搜索（关键词 + 向量）
- 9 种故障排查流程（多轮引导）
- 双 Agent 协作（主生成 + 副评估）
- 多模态图片识别
- A/B 测试框架

---

## 系统架构

```
用户提问
  ↓
意图识别（classify_intent）
  ↓
  ├─ 转人工 → handle_human → 创建工单 → 结束
  ├─ 故障排查 → troubleshoot（多轮引导）→ 结束
  └─ 其他 → answer_from_kb（查 FAQ）
              ↓
           找到？─ Yes → 结束
              ↓ No
           chunk_search（查文档片段）
              ↓
           general_reply（大模型兜底）
              ↓
           evaluate_response（副 Agent 评估）
              ↓
           结束
```

---

## 核心文件说明

| 文件 | 作用 |
|------|------|
| `backend/main.py` | FastAPI 服务入口，所有 API 接口 |
| `graph.py` | LangGraph 工作流定义，路由逻辑 |
| `nodes.py` | 各节点实现（意图/知识库/大模型/评估） |
| `troubleshoot_flows.py` | 9 种排查流程决策树 |
| `tools_vector.py` | 知识库搜索（向量 + 关键词） |
| `ab_test.py` | A/B 测试模块 |

---

## 部署方式

### 后端
```bash
cd 客服agent/backend
pip install -r ../requirements.txt
python main.py
# 访问 http://localhost:8001
```

### 前端
```bash
cd 客服agent/frontend
npm install
npm run dev
# 访问 http://localhost:5173
```

### 模型配置
编辑 `.env` 文件：
```
OPENAI_API_KEY=你的密钥
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL_NAME=deepseek-chat
```

支持任何 OpenAI 兼容接口（DeepSeek/阿里云/OpenAI/Ollama）。

---

## 功能模块

### 1. 意图识别（classify_intent）
- 关键词匹配：`INTENT_KEYWORDS` 字典
- 优先级：排查流程 > 常规关键词 > 通用
- 修改意图关键词：编辑 `nodes.py` 的 `INTENT_KEYWORDS`

### 2. 知识库管理（FAQ）
- 存储：`approved_faqs.json`（已批准）+ `pending_faqs.json`（待审核）
- 搜索：向量相似度 + 关键词匹配双路
- 新增问题自动记录到 pending，高频问题自动通过
- 前端管理：AdminView.vue（增删改查）
- **删除操作会持久化到文件**

### 3. 故障排查（troubleshoot）
- 9 种流程：超分/支付/技能同步/画布崩溃/视频失败等
- 多轮引导：每轮根据用户回答匹配分支
- 工具调用：TaskID 查询、积分余额、会员状态
- 流程定义：`troubleshoot_flows.py`
- **新增流程：** 在 `TROUBLESHOOT_FLOWS` 字典添加

### 4. 双 Agent 协作
- 主 Agent：生成回答
- 副 Agent：评估准确性/完整性/语气/安全
- 评估阈值：任一维度<3 触发修正，安全<4 强制修正
- 只在无知识库参考时才评估（避免重复检查）

### 5. 多模态图片
- 前端上传：ChatView.vue（📎 按钮）
- 压缩策略：>1MB 自动缩到 1024px，JPEG 80% 质量
- 模型识别：qwen3.7-plus（支持视觉）
- 传递链路：前端 base64 → API → AgentState → 多模态消息

### 6. 数据看板
- 指标卡片：总问答量/命中率/降级次数/满意度
- 图表：每日趋势/KB vs LLM/满意度分布/A/B 测试
- 访问权限：admin 角色可见
- 数据源：`stats.json` + `feedback.json` + `ab_experiment.json`

### 7. A/B 测试
- 策略：A（知识库优先）/ B（大模型优先）/ C（混合）
- 分配：随机均匀分配
- 记录：`ab_experiment.json`
- 看板展示：调用次数 + 平均评分双轴图

---

## 常见操作

### 新增 FAQ
1. 前端 AdminView 点击"新增 FAQ"
2. 或：用户提问未命中 → 自动记录到 pending → 审核通过

### 新增排查流程
1. 编辑 `troubleshoot_flows.py`
2. 在 `TROUBLESHOOT_FLOWS` 添加新流程
3. 定义步骤和分支

### 更换模型
1. 编辑 `.env`
2. 修改 `OPENAI_BASE_URL` 和 `OPENAI_MODEL_NAME`
3. 重启后端

### 查看日志
```bash
# 实时日志
tail -f backend/logs/server.log

# 最新 20 条
powershell -Command "Get-ChildItem logs\*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content -Encoding UTF8 | Select-Object -Last 20"
```

---

## 注意事项

1. **stats.json 兼容性** — 新增统计字段时用 `setdefault()` 初始化，避免旧数据 KeyError
2. **AgentState 字段同步** — 节点返回新字段时，必须在 `graph.py` 的 `AgentState` 声明
3. **f-string 引号** — 避免 `f"""...{dict['key']}..."""` 嵌套，改用变量提取
4. **前端变量名** — 同一作用域不要有同名 `const` 和 `let`
5. **表单事件** — 按钮用 `type="button"`，避免 `type="submit"` 导致回车刷新

---

## 测试账号

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 管理员 | admin | admin123 |
| 客服 | support | support123 |
| 普通用户 | user | user123 |

---

## 后续建议

1. **扩展排查流程** — 根据实际用户问题补充新场景
2. **A/B 测试数据积累** — 等用户量上来后分析策略效果
3. **国际化** — 代码已有 i18n 模块，可加英文支持
4. **接入真实 API** — 积分/会员接口从 Mock 换成真实服务

---

**文档版本：** 2026-08-20  
**作者：** 实习生  
**联系方式：** （留给下一个人）
