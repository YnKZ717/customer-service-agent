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
  isGreeting?: boolean  // 是否开场白（不显示反馈）
  hoveredRating?: number  // 悬停评分（临时）
  images?: string[]  // FAQ 命中的截图
  uploadedImages?: string[]  // 用户上传的图片预览 URL
  isTroubleshooting?: boolean  // 是否在排查流程中
  troubleshootStep?: number    // 当前排查步骤
  timestamp?: Date  // 消息时间
}

// ── 每次打开都初始化新对话 ──
function loadChatHistory(): Message[] {
  return [
    { role: 'assistant', content: '你好！我是 Neowow Studio 的智能客服助手。你可以问我关于账号、充值、会员套餐、视频生成、图片生成等问题，我会尽力帮你解决。', isGreeting: true }
  ]
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
const pendingImages = ref<{ base64: string; preview: string }[]>([])
const fileInputRef = ref<HTMLInputElement | null>(null)

const quickQuestions = ['怎么充值积分', 'CodingPlan 是什么', '怎么使用智能体', '我要投诉']

import { watch } from 'vue'

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

// ── 图片上传相关 ──
const MAX_IMAGE_SIZE = 1 * 1024 * 1024  // 1MB
const MAX_DIMENSION = 1024  // 最大边长

function triggerFileInput() {
  fileInputRef.value?.click()
}

/** 压缩图片：超过 1MB 或尺寸超过 1024px 时自动压缩 */
function compressImage(file: File): Promise<{ base64: string; preview: string }> {
  return new Promise((resolve, reject) => {
    // 如果文件小于 1MB，直接返回
    if (file.size <= MAX_IMAGE_SIZE) {
      const reader = new FileReader()
      reader.onload = () => {
        const result = reader.result as string
        resolve({
          base64: result.split(',')[1],
          preview: result,
        })
      }
      reader.onerror = reject
      reader.readAsDataURL(file)
      return
    }

    // 需要压缩：用 canvas 缩放
    const img = new Image()
    img.onload = () => {
      let { width, height } = img
      // 计算缩放比例
      if (width > height && width > MAX_DIMENSION) {
        height = (height * MAX_DIMENSION) / width
        width = MAX_DIMENSION
      } else if (height > MAX_DIMENSION) {
        width = (width * MAX_DIMENSION) / height
        height = MAX_DIMENSION
      }

      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      const ctx = canvas.getContext('2d')
      if (!ctx) return reject(new Error('无法获取 canvas 上下文'))
      ctx.drawImage(img, 0, 0, width, height)

      // 用 JPEG 格式压缩（质量 0.8）
      const compressed = canvas.toDataURL('image/jpeg', 0.8)
      resolve({
        base64: compressed.split(',')[1],
        preview: compressed,
      })
    }
    img.onerror = reject
    img.src = URL.createObjectURL(file)
  })
}

async function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  const files = input.files
  if (!files) return

  for (const file of Array.from(files)) {
    if (!file.type.startsWith('image/')) continue
    try {
      const { base64, preview } = await compressImage(file)
      pendingImages.value.push({ base64, preview })
    } catch (err) {
      console.error('图片压缩失败:', err)
    }
  }
  // 清空 input，允许重复选择同一文件
  input.value = ''
}

function removeImage(index: number) {
  pendingImages.value.splice(index, 1)
}

async function sendMessage(text: string) {
  if ((!text.trim() && pendingImages.value.length === 0) || loading.value) return

  // 收集图片 base64
  const images = pendingImages.value.map(img => img.base64)
  const uploadedPreviews = pendingImages.value.map(img => img.preview)

  // 添加用户消息（带图片）
  const userMsg: Message = {
    role: 'user',
    content: text || '请看看这张图片',
    id: `msg-${Date.now()}`,
    timestamp: new Date(),
    uploadedImages: uploadedPreviews.length > 0 ? uploadedPreviews : undefined,
  }
  messages.value.push(userMsg)
  userInput.value = ''
  pendingImages.value = []
  loading.value = true

  // 立即创建空回复（显示机器人头像 + 思考中动画）
  const replyId = `msg-${Date.now()}-reply`
  const replyIndex = messages.value.length
  messages.value.push({
    role: 'assistant',
    content: '',
    id: replyId,
    timestamp: new Date(),
  })

  try {
    const resp = await fetch(`${API_BASE}/api/chat/stream`, {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({ user_input: text, history: chatHistory.value, images }),
    })

    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`)
    }

    const reader = resp.body?.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let fullResponse = ''
    let isTroubleshooting = false
    let troubleshootStep = 0
    let faqImages: string[] = []
    let modelUsed = ''

    while (true) {
      const { done, value } = await reader!.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6).trim()

          if (data === '[DONE]') {
            continue
          }

          try {
            const parsed = JSON.parse(data)

            // 第一条是元数据
            if (parsed.intent !== undefined && fullResponse === '') {
              if (parsed.kb_images && parsed.kb_images.length > 0) {
                faqImages = parsed.kb_images
              }
              if (parsed.is_troubleshooting) {
                isTroubleshooting = true
                troubleshootStep = parsed.troubleshoot_step
              }
              if (parsed.model_used) {
                modelUsed = parsed.model_used
              }
              continue
            }

            // 后续是逐字内容
            if (parsed.chunk) {
              fullResponse += parsed.chunk
              // 直接修改数组元素触发 Vue 响应式
              messages.value[replyIndex] = {
                role: 'assistant',
                content: fullResponse,
                id: replyId,
                timestamp: messages.value[replyIndex].timestamp,
                images: faqImages.length > 0 ? faqImages : undefined,
                isTroubleshooting,
                troubleshootStep: isTroubleshooting ? troubleshootStep : undefined,
                modelUsed: modelUsed || undefined,
              }
              // 每 5 个字符滚动一次
              if (fullResponse.length % 5 === 0) {
                scrollToBottom()
              }
            }
          } catch {
            // 忽略解析错误
          }
        }
      }
    }

    // 添加到历史记录
    chatHistory.value.push(['user', text])
    const historyContent = isTroubleshooting
      ? ` 故障排查中（第${troubleshootStep + 1}步）\n${fullResponse}`
      : fullResponse
    chatHistory.value.push(['assistant', historyContent])

    refreshStats()
  } catch (err) {
    // 更新错误信息
    messages.value[replyIndex] = {
      ...messages.value[replyIndex],
      content: '抱歉，服务暂时不可用，请稍后再试。',
    }
  } finally {
    loading.value = false
    nextTick(() => scrollToBottom())
  }
}

function handleQuickQuestion(q: string) {
  sendMessage(q)
}

function formatTime(date: Date): string {
  const d = new Date(date)
  const hours = d.getHours().toString().padStart(2, '0')
  const minutes = d.getMinutes().toString().padStart(2, '0')
  return `${hours}:${minutes}`
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
            <!-- 用户上传的图片 -->
            <div v-if="msg.uploadedImages && msg.uploadedImages.length" class="uploaded-images">
              <img
                v-for="(img, idx) in msg.uploadedImages"
                :key="idx"
                :src="img"
                :alt="'上传图片 ' + (idx + 1)"
                class="uploaded-image"
                @click="previewImage = img"
              />
            </div>
            <p v-if="msg.content">{{ msg.content }}</p>
            <!-- 思考中动画（仅在内容为空且是助手消息时显示） -->
            <div v-else-if="msg.role === 'assistant'" class="thinking-dots">
              <span class="dot"></span><span class="dot"></span><span class="dot"></span>
              <span class="thinking-text">思考中...</span>
            </div>
            <p v-if="msg.ticketId" class="ticket-id">工单号：{{ msg.ticketId }}</p>
            <p v-if="msg.timestamp" class="message-time">{{ formatTime(msg.timestamp) }}</p>
            <span v-if="msg.modelUsed" class="model-badge">{{ msg.modelUsed }}</span>
          </div>
          <!-- 排查状态指示器 -->
          <div v-if="msg.isTroubleshooting" class="troubleshoot-badge">
            🔍 故障排查中（第{{ (msg.troubleshootStep || 0) + 1 }}步）
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
          <!-- 反馈按钮（仅助手消息，且非开场白） -->
          <div v-if="msg.role === 'assistant' && !msg.isTicket && !msg.isGreeting" class="feedback-buttons">
            <template v-if="!msg.rated">
              <button
                v-for="star in 5"
                :key="star"
                @click="submitFeedback(msg, star)"
                class="star-btn"
                :class="{ active: (msg.hoveredRating || 0) >= star }"
                @mouseenter="msg.hoveredRating = star"
                @mouseleave="msg.hoveredRating = 0"
                :title="star + ' 星'"
              >
                ★
              </button>
            </template>
            <span v-else class="feedback-thanks">感谢反馈 ✓</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 输入区域 -->
    <form class="input-area" role="form" aria-label="输入问题" @submit.prevent>
      <label for="chat-input" class="sr-only">输入你的问题</label>
      <!-- 隐藏的文件选择器 -->
      <input
        ref="fileInputRef"
        type="file"
        accept="image/*"
        multiple
        class="hidden-file-input"
        @change="handleFileSelect"
      />
      <!-- 图片上传按钮 -->
      <button type="button" @click="triggerFileInput" class="upload-btn" :disabled="loading" title="上传图片" aria-label="上传图片">📎</button>
      <input
        id="chat-input"
        v-model="userInput"
        @keyup.enter="sendMessage(userInput)"
        placeholder="输入你的问题..."
        class="chat-input"
        :disabled="loading"
        aria-label="输入你的问题"
      />
      <button type="button" @click="sendMessage(userInput)" :disabled="loading || (!userInput.trim() && pendingImages.length === 0)" class="send-btn" aria-label="发送消息">
        发送
      </button>
    </form>

    <!-- 待发送图片预览 -->
    <div v-if="pendingImages.length > 0" class="pending-images-preview">
      <div v-for="(img, idx) in pendingImages" :key="idx" class="pending-image-item">
        <img :src="img.preview" :alt="'待发送图片 ' + (idx + 1)" class="pending-image-thumb" />
        <button type="button" @click="removeImage(idx)" class="remove-image-btn" aria-label="移除图片">✕</button>
      </div>
    </div>

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
  max-width: 1000px;
  margin: 0 auto;
  height: calc(100vh - 48px);
  display: flex;
  flex-direction: column;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  margin-bottom: 4px;
  flex-shrink: 0;
}

.page-subtitle {
  color: #888;
  font-size: 14px;
  margin-bottom: 16px;
  flex-shrink: 0;
}

.quick-buttons {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  flex-wrap: wrap;
  max-width: 100%;
  overflow-x: auto;
  flex-shrink: 0;
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
  flex: 1;
  min-height: 0;
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

.message-time {
  font-size: 11px;
  color: #999;
  margin-top: 6px;
  text-align: right;
}

.message.user .message-time {
  color: rgba(255,255,255,0.7);
}

.model-badge {
  display: inline-block;
  font-size: 10px;
  color: #888;
  background: #f0f0f0;
  padding: 2px 6px;
  border-radius: 8px;
  margin-top: 6px;
  font-family: monospace;
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
  gap: 4px;
  margin-top: 6px;
  align-items: center;
}

.star-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 20px;
  color: #ddd;
  padding: 2px 4px;
  transition: color 0.15s, transform 0.15s;
}

.star-btn:hover,
.star-btn.active {
  color: #FFC107;
  transform: scale(1.15);
}

.feedback-thanks {
  font-size: 12px;
  color: #4CAF50;
}

/* 排查状态指示器 */
.troubleshoot-badge {
  font-size: 11px;
  color: #ff9800;
  background: #fff3e0;
  border: 1px solid #ffcc80;
  padding: 3px 10px;
  border-radius: 12px;
  display: inline-block;
  margin-top: 6px;
  width: fit-content;
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

.thinking-dots {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 0;
}

.thinking-text {
  margin-left: 8px;
  font-size: 13px;
  color: #999;
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

/* 隐藏文件选择器 */
.hidden-file-input {
  display: none;
}

/* 图片上传按钮 */
.upload-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  min-width: 40px;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 22px;
  color: #666;
  border-radius: 50%;
  transition: background 0.2s, color 0.2s;
  flex-shrink: 0;
  padding: 0;
  line-height: 1;
}

.upload-btn:hover:not(:disabled) {
  background: #f0f0f0;
  color: #4CAF50;
}

.upload-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 待发送图片预览 */
.pending-images-preview {
  display: flex;
  gap: 8px;
  padding: 8px 0;
  flex-wrap: wrap;
}

.pending-image-item {
  position: relative;
  width: 80px;
  height: 80px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #e0e0e0;
}

.pending-image-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.remove-image-btn {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: rgba(0,0,0,0.6);
  color: #fff;
  border: none;
  font-size: 11px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  padding: 0;
}

.remove-image-btn:hover {
  background: rgba(229, 57, 53, 0.9);
}

/* 用户上传的图片（在消息气泡中） */
.uploaded-images {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.uploaded-image {
  max-width: 200px;
  max-height: 150px;
  border-radius: 8px;
  border: 1px solid #e0e0e0;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  object-fit: cover;
}

.uploaded-image:hover {
  transform: scale(1.05);
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}
</style>
