<script setup lang="ts">
import { ref, nextTick } from 'vue'

const API_BASE = 'http://localhost:8001'

// 从 localStorage 获取 Token
const token = localStorage.getItem('token')
const headers = {
  'Content-Type': 'application/json',
  'Authorization': `Bearer ${token}`,
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  isTicket?: boolean
  ticketId?: string
  id?: string  // 唯一 ID，用于反馈
  rated?: boolean  // 是否已评价
  images?: string[]  // FAQ 命中的截图
}

// ── localStorage 持久化 ──
const STORAGE_KEY = 'neowow_chat_history'

function loadChatHistory(): Message[] {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      return JSON.parse(saved)
    }
  } catch {
    // ignore
  }
  return [
    { role: 'assistant', content: '你好！我是 Neowow Studio 的智能客服助手。你可以问我关于账号、充值、CodingPlan 套餐、智能体使用等问题。' }
  ]
}

function saveChatHistory(msgs: Message[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(msgs.slice(-50)))
  } catch {
    // ignore
  }
}

const messages = ref<Message[]>(loadChatHistory())
const chatHistory = ref<[string, string][]>([])
const userInput = ref('')
const loading = ref(false)
const faqCount = ref(0)
const pendingCount = ref(0)
const chatContainer = ref<HTMLElement | null>(null)
const apiCalls = ref(0)
const kbHitRate = ref(0)

const quickQuestions = ['怎么充值积分', 'CodingPlan 是什么', '怎么使用智能体', '我要投诉']

// 监听消息变化，自动保存
import { watch } from 'vue'
watch(messages, (newMsgs) => {
  saveChatHistory(newMsgs)
}, { deep: true })

// 监听输入，自动滚动
watch(userInput, () => {
  nextTick(() => scrollToBottom())
})

// 页面加载时自动滚动到底部
watch(
  () => messages.value.length,
  () => {
    nextTick(() => scrollToBottom())
  },
  { immediate: true }
)

async function sendMessage(text: string) {
  if (!text.trim() || loading.value) return

  const userMsg: Message = { role: 'user', content: text, id: `msg-${Date.now()}` }
  messages.value.push(userMsg)
  userInput.value = ''
  loading.value = true

  try {
    const resp = await fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({ user_input: text, history: chatHistory.value }),
    })
    const data = await resp.json()
    const replyMsg: Message = {
      role: 'assistant',
      content: data.response,
      id: `msg-${Date.now()}-reply`,
    }
    if (data.kb_images && data.kb_images.length > 0) {
      replyMsg.images = data.kb_images
    }
    messages.value.push(replyMsg)
    chatHistory.value.push(['user', text])
    chatHistory.value.push(['assistant', data.response])

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

async function transferToHuman() {
  if (loading.value) return

  const lastMessage = chatHistory.value.length > 0
    ? chatHistory.value[chatHistory.value.length - 2][1]
    : '用户需要人工客服帮助'

  loading.value = true

  try {
    const resp = await fetch(`${API_BASE}/api/tickets`, {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({
        user_input: lastMessage,
        history: chatHistory.value,
      }),
    })

    if (resp.ok) {
      const data = await resp.json()
      messages.value.push({
        role: 'assistant',
        content: data.message,
        isTicket: true,
        ticketId: data.ticket_id,
        id: `msg-${Date.now()}-ticket`,
      })
    } else {
      messages.value.push({
        role: 'assistant',
        content: '创建工单失败，请稍后再试。',
        id: `msg-${Date.now()}-error`,
      })
    }
  } catch (err) {
    messages.value.push({
      role: 'assistant',
      content: '服务暂时不可用，请稍后再试。',
      id: `msg-${Date.now()}-error`,
    })
  } finally {
    loading.value = false
    nextTick(() => scrollToBottom())
  }
}

function scrollToBottom() {
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

async function refreshStats() {
  try {
    const faqResp = await fetch(`${API_BASE}/api/faqs`, { headers })
    const faqData = await faqResp.json()
    faqCount.value = faqData.total

    const pendingResp = await fetch(`${API_BASE}/api/pending`, { headers })
    const pendingData = await pendingResp.json()
    pendingCount.value = pendingData.total

    const statsResp = await fetch(`${API_BASE}/api/stats`, { headers })
    const statsData = await statsResp.json()
    apiCalls.value = statsData.total_calls || 0
    kbHitRate.value = statsData.kb_hit_rate || 0
  } catch {
    // ignore
  }
}

refreshStats()

async function submitFeedback(msg: Message, rating: number) {
  try {
    await fetch(`${API_BASE}/api/feedback`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        message_id: msg.id || '',
        rating,
      }),
    })
    msg.rated = true
  } catch {
    // ignore
  }
}

// 图片预览
const previewImage = ref('')
function openImagePreview(img: string) {
  previewImage.value = `/faq-images/${img}`
}
function closeImagePreview() {
  previewImage.value = ''
}
</script>

<template>
  <div class="chat-page" role="main" aria-label="客服对话页面">
    <h1 class="page-title"> Neowow Studio 智能客服</h1>
    <p class="page-subtitle">我是 Neowow 平台的智能客服助手，有什么可以帮你的？</p>

    <!-- 快捷按钮 -->
    <div class="quick-buttons" role="group" aria-label="快捷问题">
      <button v-for="q in quickQuestions" :key="q" @click="handleQuickQuestion(q)" class="quick-btn" :aria-label="q">
        {{ q }}
      </button>
      <button @click="transferToHuman" class="quick-btn human-btn" :disabled="loading" aria-label="转人工客服">
        🎧 转人工客服
      </button>
    </div>

    <!-- 聊天区域 -->
    <div class="chat-container" ref="chatContainer" role="log" aria-label="对话记录" aria-live="polite">
      <div v-for="(msg, i) in messages" :key="i" :class="['message', msg.role, { 'ticket-message': msg.isTicket }]">
        <div class="message-avatar">{{ msg.role === 'user' ? '👤' : '🤖' }}</div>
        <div class="message-content">
          <div class="message-bubble">
            <p>{{ msg.content }}</p>
            <p v-if="msg.ticketId" class="ticket-id">工单号：{{ msg.ticketId }}</p>
          </div>
          <!-- FAQ 截图 -->
          <div v-if="msg.images && msg.images.length" class="faq-images">
            <img
              v-for="(img, idx) in msg.images"
              :key="idx"
              :src="`/faq-images/${img}`"
              :alt="'操作指引 ' + (idx + 1)"
              class="faq-image"
              @click="openImagePreview(img)"
            />
          </div>
          <!-- 反馈按钮（仅助手消息） -->
          <div v-if="msg.role === 'assistant' && !msg.isTicket" class="feedback-buttons">
            <button
              v-if="!msg.rated"
              @click="submitFeedback(msg, 5)"
              class="feedback-btn"
              title="有帮助"
            >
              👍
            </button>
            <button
              v-if="!msg.rated"
              @click="submitFeedback(msg, 1)"
              class="feedback-btn"
              title="没帮助"
            >
              👎
            </button>
            <span v-else class="feedback-thanks">感谢反馈 ✓</span>
          </div>
        </div>
      </div>
      <div v-if="loading" class="message assistant">
        <div class="message-avatar"></div>
        <div class="message-bubble thinking">
          <span class="dot"></span><span class="dot"></span><span class="dot"></span>
        </div>
      </div>
    </div>

    <!-- 输入区域 -->
    <form class="input-area" role="form" aria-label="输入问题" @submit.prevent="sendMessage(userInput)">
      <label for="chat-input" class="sr-only">输入你的问题</label>
      <input
        id="chat-input"
        v-model="userInput"
        @keyup.enter="sendMessage(userInput)"
        placeholder="输入你的问题..."
        class="chat-input"
        :disabled="loading"
        aria-label="输入你的问题"
      />
      <button type="submit" @click="sendMessage(userInput)" :disabled="loading || !userInput.trim()" class="send-btn" aria-label="发送消息">
        发送
      </button>
    </form>

    <!-- 底部统计 -->
    <div class="stats-bar" role="status" aria-label="统计信息">
      <div class="stat">FAQ 数量：<strong>{{ faqCount }}</strong></div>
      <div class="stat">待确认提案：<strong>{{ pendingCount }}</strong></div>
      <div class="stat">API 调用：<strong>{{ apiCalls }}</strong></div>
      <div class="stat">知识库命中率：<strong>{{ kbHitRate }}%</strong></div>
      <div class="stat">对话轮次：<strong>{{ chatHistory.length / 2 }}</strong></div>
    </div>

    <!-- 图片预览弹窗 -->
    <div v-if="previewImage" class="image-preview-overlay" @click="closeImagePreview">
      <div class="image-preview-content" @click.stop>
        <img :src="previewImage" alt="预览" class="preview-img" />
        <button class="preview-close" @click="closeImagePreview">✕</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 屏幕阅读器专用 */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

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
  max-width: 100%;
  overflow-x: auto;
}

.quick-btn {
  padding: 8px 16px;
  border: 1px solid #ddd;
  border-radius: 20px;
  background: #fff;
  cursor: pointer;
  font-size: 14px;
  white-space: nowrap;
  transition: all 0.2s;
}

.quick-btn:hover {
  background: #4CAF50;
  color: #fff;
  border-color: #4CAF50;
}

.human-btn {
  background: #fff3e0;
  border-color: #ff9800;
  color: #e65100;
}

.human-btn:hover:not(:disabled) {
  background: #ff9800;
  color: #fff;
}

.human-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
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

.message.user .message-content {
  align-items: flex-end;
}

.message-avatar {
  font-size: 28px;
  flex-shrink: 0;
}

.message-bubble {
  max-width: 100%;
  padding: 12px 16px;
  border-radius: 16px;
  font-size: 15px;
  line-height: 1.6;
  word-break: break-word;
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

.ticket-message .message-bubble {
  background: #fff3e0;
  border: 1px solid #ff9800;
}

.ticket-id {
  font-size: 12px;
  color: #e65100;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #ffcc80;
}

/* 反馈按钮 */
.message-content {
  display: flex;
  flex-direction: column;
  max-width: 70%;
}

.message.user .message-content {
  align-items: flex-end;
}

.feedback-buttons {
  display: flex;
  gap: 6px;
  margin-top: 6px;
  align-items: center;
}

.feedback-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 18px;
  padding: 4px 8px;
  border-radius: 4px;
  transition: background 0.2s;
  opacity: 0.6;
}

.feedback-btn:hover {
  background: #f0f0f0;
  opacity: 1;
}

.feedback-thanks {
  font-size: 12px;
  color: #4CAF50;
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

/* FAQ 截图 */
.faq-images {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.faq-image {
  max-width: 200px;
  max-height: 150px;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  object-fit: cover;
}

.faq-image:hover {
  transform: scale(1.05);
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

/* 图片预览弹窗 */
.image-preview-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0,0,0,0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.image-preview-content {
  position: relative;
  max-width: 90vw;
  max-height: 90vh;
}

.preview-img {
  max-width: 90vw;
  max-height: 85vh;
  border-radius: 8px;
  object-fit: contain;
}

.preview-close {
  position: absolute;
  top: -12px;
  right: -12px;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #fff;
  border: none;
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 8px rgba(0,0,0,0.2);
  transition: background 0.2s;
}

.preview-close:hover {
  background: #f5f5f5;
}
</style>
