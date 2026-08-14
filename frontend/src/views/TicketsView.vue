<script setup lang="ts">
import { ref, onMounted } from 'vue'

const API_BASE = 'http://localhost:8001'

const token = localStorage.getItem('token')
const headers = {
  'Content-Type': 'application/json',
  'Authorization': `Bearer ${token}`,
}

interface Ticket {
  ticket_id: string
  question: string
  history: [string, string][]
  status: string
  created_at: string
  reply: string
  replied_at: string
}

const tickets = ref<Ticket[]>([])
const loading = ref(false)
const filterStatus = ref('')

// 工单回复
const replyText = ref('')
const replyTicketId = ref('')
const replying = ref(false)

const statusLabels: Record<string, string> = {
  pending: '待处理',
  in_progress: '处理中',
  resolved: '已解决',
  closed: '已关闭',
}

const statusColors: Record<string, string> = {
  pending: '#ff9800',
  in_progress: '#2196f3',
  resolved: '#4caf50',
  closed: '#9e9e9e',
}

async function loadData() {
  loading.value = true
  try {
    const url = filterStatus.value
      ? `${API_BASE}/api/tickets?status=${filterStatus.value}`
      : `${API_BASE}/api/tickets`
    const resp = await fetch(url, { headers })
    const data = await resp.json()
    tickets.value = data.items
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
}

function startReply(ticket: Ticket) {
  replyTicketId.value = ticket.ticket_id
  replyText.value = ''
}

async function submitReply() {
  if (!replyText.value.trim() || !replyTicketId.value) return

  replying.value = true
  try {
    const resp = await fetch(`${API_BASE}/api/tickets/${replyTicketId.value}/reply`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ reply: replyText.value }),
    })
    if (resp.ok) {
      replyText.value = ''
      replyTicketId.value = ''
      await loadData()
    } else {
      const err = await resp.json().catch(() => ({}))
      alert(err.detail || '回复失败')
    }
  } catch {
    alert('回复失败，请稍后再试')
  } finally {
    replying.value = false
  }
}

async function updateStatus(ticketId: string, status: string) {
  const resp = await fetch(`${API_BASE}/api/tickets/${ticketId}/status?status=${status}`, {
    method: 'POST',
    headers,
  })
  if (resp.ok) {
    await loadData()
  } else {
    const err = await resp.json().catch(() => ({}))
    alert(err.detail || '更新状态失败')
  }
}

function onFilterChange(e: Event) {
  filterStatus.value = (e.target as HTMLSelectElement).value
  loadData()
}

onMounted(() => {
  loadData()
})
</script>

<template>
  <div class="tickets-page">
    <h1 class="page-title"> 工单管理</h1>
    <p class="page-subtitle">查看和回复用户转人工的工单</p>

    <!-- 筛选 -->
    <div class="filter-bar">
      <label>状态筛选：</label>
      <select :value="filterStatus" @change="onFilterChange" class="filter-select">
        <option value="">全部</option>
        <option value="pending">待处理</option>
        <option value="in_progress">处理中</option>
        <option value="resolved">已解决</option>
        <option value="closed">已关闭</option>
      </select>
      <span class="ticket-count">共 {{ tickets.length }} 条</span>
    </div>

    <!-- 工单列表 -->
    <div v-if="tickets.length === 0" class="empty-state">
      暂无工单
    </div>

    <div v-for="ticket in tickets" :key="ticket.ticket_id" class="ticket-card">
      <div class="ticket-header">
        <span class="ticket-id">{{ ticket.ticket_id }}</span>
        <span class="ticket-status" :style="{ background: statusColors[ticket.status] }">
          {{ statusLabels[ticket.status] }}
        </span>
        <span class="ticket-time">{{ ticket.created_at }}</span>
      </div>

      <div class="ticket-question">{{ ticket.question }}</div>

      <!-- 对话历史 -->
      <div v-if="ticket.history && ticket.history.length > 0" class="ticket-history">
        <details>
          <summary>查看对话历史（{{ ticket.history.length / 2 }} 轮）</summary>
          <div class="history-list">
            <div
              v-for="(msg, idx) in ticket.history"
              :key="idx"
              :class="['history-item', msg[0]]"
            >
              <strong>{{ msg[0] === 'user' ? '用户：' : '客服：' }}</strong>
              {{ msg[1] }}
            </div>
          </div>
        </details>
      </div>

      <!-- 客服回复 -->
      <div v-if="ticket.reply" class="ticket-reply">
        <strong>客服回复：</strong>
        <p>{{ ticket.reply }}</p>
        <div class="reply-meta">回复时间：{{ ticket.replied_at }}</div>
      </div>

      <!-- 操作按钮 -->
      <div class="ticket-actions">
        <template v-if="!ticket.reply">
          <button
            v-if="replyTicketId !== ticket.ticket_id"
            @click="startReply(ticket)"
            class="btn-reply"
          >
            💬 回复
          </button>
          <div v-else class="reply-form">
            <textarea
              v-model="replyText"
              placeholder="输入回复内容..."
              class="reply-input"
            ></textarea>
            <div class="reply-buttons">
              <button @click="submitReply" :disabled="replying || !replyText.trim()" class="btn-submit">
                {{ replying ? '发送中...' : '提交回复' }}
              </button>
              <button @click="replyTicketId = ''" class="btn-cancel">取消</button>
            </div>
          </div>
        </template>

        <!-- 状态更新 -->
        <select
          :value="ticket.status"
          @change="updateStatus(ticket.ticket_id, ($event.target as HTMLSelectElement).value)"
          class="status-select"
        >
          <option value="pending">待处理</option>
          <option value="in_progress">处理中</option>
          <option value="resolved">已解决</option>
          <option value="closed">已关闭</option>
        </select>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tickets-page {
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
  margin-bottom: 24px;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  padding: 12px 16px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}

.filter-bar label {
  font-size: 14px;
  color: #555;
}

.filter-select {
  padding: 6px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
}

.filter-select:focus {
  outline: none;
  border-color: #4CAF50;
}

.ticket-count {
  margin-left: auto;
  font-size: 14px;
  color: #888;
}

.empty-state {
  background: #fff;
  padding: 48px;
  border-radius: 8px;
  text-align: center;
  color: #888;
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}

.ticket-card {
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}

.ticket-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.ticket-id {
  font-weight: 700;
  font-size: 16px;
  color: #333;
}

.ticket-status {
  padding: 4px 10px;
  border-radius: 12px;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}

.ticket-time {
  font-size: 12px;
  color: #999;
  margin-left: auto;
}

.ticket-question {
  font-size: 15px;
  line-height: 1.6;
  margin-bottom: 12px;
  padding: 12px;
  background: #f9f9f9;
  border-radius: 6px;
}

.ticket-history {
  margin-bottom: 12px;
}

.ticket-history summary {
  cursor: pointer;
  color: #4CAF50;
  font-size: 13px;
  margin-bottom: 8px;
}

.history-list {
  background: #f5f5f5;
  padding: 12px;
  border-radius: 6px;
  max-height: 200px;
  overflow-y: auto;
}

.history-item {
  margin-bottom: 8px;
  font-size: 13px;
  line-height: 1.5;
}

.history-item.user {
  color: #333;
}

.history-item.assistant {
  color: #666;
  padding-left: 16px;
}

.ticket-reply {
  background: #e8f5e9;
  border-left: 4px solid #4CAF50;
  padding: 12px;
  border-radius: 4px;
  margin-bottom: 12px;
}

.ticket-reply strong {
  color: #2e7d32;
  font-size: 13px;
}

.ticket-reply p {
  margin: 8px 0 0 0;
  font-size: 14px;
  line-height: 1.6;
  color: #333;
}

.reply-meta {
  font-size: 11px;
  color: #888;
  margin-top: 8px;
}

.ticket-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.btn-reply {
  padding: 6px 16px;
  background: #2196f3;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.btn-reply:hover {
  background: #1976d2;
}

.reply-form {
  width: 100%;
  margin-top: 12px;
}

.reply-input {
  width: 100%;
  min-height: 80px;
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
  resize: vertical;
  font-family: inherit;
}

.reply-input:focus {
  outline: none;
  border-color: #4CAF50;
}

.reply-buttons {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.btn-submit {
  padding: 6px 16px;
  background: #4CAF50;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.btn-submit:hover:not(:disabled) {
  background: #388E3C;
}

.btn-submit:disabled {
  background: #ccc;
  cursor: not-allowed;
}

.btn-cancel {
  padding: 6px 16px;
  background: #fff;
  color: #666;
  border: 1px solid #ddd;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.btn-cancel:hover {
  background: #f5f5f5;
}

.status-select {
  padding: 6px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  margin-left: auto;
}

.status-select:focus {
  outline: none;
  border-color: #4CAF50;
}
</style>
