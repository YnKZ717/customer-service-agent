<script setup lang="ts">
import { ref, reactive, nextTick } from 'vue'

const API_BASE = 'http://192.168.10.209:8001'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

const messages = ref<Message[]>([
  { role: 'assistant', content: '你好！我是 Neowow Studio 的智能客服助手。你可以问我关于账号、充值、CodingPlan套餐、智能体使用等问题。' }
])

const chatHistory = ref<[string, string][]>([])
const userInput = ref('')
const loading = ref(false)
const faqCount = ref(0)
const pendingCount = ref(0)
const chatContainer = ref<HTMLElement | null>(null)

const quickQuestions = ['怎么充值积分', 'CodingPlan是什么', '怎么使用智能体', '我要投诉']

async function sendMessage(text: string) {
  if (!text.trim() || loading.value) return

  messages.value.push({ role: 'user', content: text })
  userInput.value = ''
  loading.value = true

  try {
    const resp = await fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_input: text, history: chatHistory.value }),
    })
    const data = await resp.json()
    messages.value.push({ role: 'assistant', content: data.response })
    chatHistory.value.push(['user', text])
    chatHistory.value.push(['assistant', data.response])

    // 更新统计（后台获取）
    refreshStats()
  } catch (err) {
    messages.value.push({ role: 'assistant', content: '抱歉，服务暂时不可用，请稍后再试。' })
  } finally {
    loading.value = false
    nextTick(() => scrollToBottom())
  }
}

function handleQuickQuestion(q: string) {
  sendMessage(q)
}

function scrollToBottom() {
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

async function refreshStats() {
  try {
    const faqResp = await fetch(`${API_BASE}/api/faqs`)
    const faqData = await faqResp.json()
    faqCount.value = faqData.total

    const pendingResp = await fetch(`${API_BASE}/api/pending`)
    const pendingData = await pendingResp.json()
    pendingCount.value = pendingData.total
  } catch {
    // ignore
  }
}

// 初始化统计
refreshStats()
</script>

<template>
  <div class="chat-page">
    <h1 class="page-title"> Neowow Studio 智能客服</h1>
    <p class="page-subtitle">我是 Neowow 平台的智能客服助手，有什么可以帮你的？</p>

    <!-- 快捷按钮 -->
    <div class="quick-buttons">
      <button v-for="q in quickQuestions" :key="q" @click="handleQuickQuestion(q)" class="quick-btn">
        {{ q }}
      </button>
    </div>

    <!-- 聊天区域 -->
    <div class="chat-container" ref="chatContainer">
      <div v-for="(msg, i) in messages" :key="i" :class="['message', msg.role]">
        <div class="message-avatar">{{ msg.role === 'user' ? '👤' : '🤖' }}</div>
        <div class="message-bubble">
          <p>{{ msg.content }}</p>
        </div>
      </div>
      <div v-if="loading" class="message assistant">
        <div class="message-avatar">🤖</div>
        <div class="message-bubble thinking">
          <span class="dot"></span><span class="dot"></span><span class="dot"></span>
        </div>
      </div>
    </div>

    <!-- 输入区域 -->
    <div class="input-area">
      <input
        v-model="userInput"
        @keyup.enter="sendMessage(userInput)"
        placeholder="输入你的问题..."
        class="chat-input"
        :disabled="loading"
      />
      <button @click="sendMessage(userInput)" :disabled="loading || !userInput.trim()" class="send-btn">
        发送
      </button>
    </div>

    <!-- 底部统计 -->
    <div class="stats-bar">
      <div class="stat">FAQ数量: <strong>{{ faqCount }}</strong></div>
      <div class="stat">待确认提案: <strong>{{ pendingCount }}</strong></div>
      <div class="stat">对话轮次: <strong>{{ chatHistory.length / 2 }}</strong></div>
    </div>
  </div>
</template>

<style scoped>
.chat-page {
  max-width: 900px;
  margin: 0 auto;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  margin-bottom: 4px;
}

.page-subtitle {
  color: #888;
  font-size: 14px;
  margin-bottom: 16px;
}

.quick-buttons {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.quick-btn {
  padding: 8px 16px;
  border: 1px solid #ddd;
  border-radius: 20px;
  background: #fff;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.quick-btn:hover {
  background: #4CAF50;
  color: #fff;
  border-color: #4CAF50;
}

.chat-container {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  min-height: 400px;
  max-height: 500px;
  overflow-y: auto;
  margin-bottom: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.message {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  align-items: flex-start;
}

.message.user {
  flex-direction: row-reverse;
}

.message-avatar {
  font-size: 28px;
  flex-shrink: 0;
}

.message-bubble {
  max-width: 70%;
  padding: 12px 16px;
  border-radius: 16px;
  font-size: 15px;
  line-height: 1.6;
}

.message.user .message-bubble {
  background: #4CAF50;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.message.assistant .message-bubble {
  background: #f5f5f5;
  color: #333;
  border-bottom-left-radius: 4px;
}

.thinking {
  display: flex;
  gap: 4px;
  padding: 12px 20px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #999;
  animation: bounce 1.4s infinite ease-in-out;
}

.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

.input-area {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}

.chat-input {
  flex: 1;
  padding: 12px 16px;
  border: 1px solid #ddd;
  border-radius: 24px;
  font-size: 15px;
  outline: none;
  transition: border-color 0.2s;
}

.chat-input:focus {
  border-color: #4CAF50;
}

.send-btn {
  padding: 12px 24px;
  background: #4CAF50;
  color: #fff;
  border: none;
  border-radius: 24px;
  font-size: 15px;
  cursor: pointer;
  transition: background 0.2s;
  white-space: nowrap;
}

.send-btn:hover:not(:disabled) {
  background: #388E3C;
}

.send-btn:disabled {
  background: #ccc;
  cursor: not-allowed;
}

.stats-bar {
  display: flex;
  gap: 24px;
  padding: 12px 0;
  border-top: 1px solid #eee;
  font-size: 14px;
  color: #666;
}

.stats-bar strong {
  color: #333;
}
</style>
