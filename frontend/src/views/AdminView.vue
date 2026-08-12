<script setup lang="ts">
import { ref, onMounted } from 'vue'

const API_BASE = 'http://192.168.10.209:8001'

interface PendingItem {
  question: string
  answer: string
  original_answer?: string
  created_at: string
  status: string
  _realIndex: number
}

interface FaqItem {
  index: number
  question: string
  answer: string
  category: string
}

const pendingItems = ref<PendingItem[]>([])
const faqItems = ref<FaqItem[]>([])
const loading = ref(false)

async function loadData() {
  loading.value = true
  try {
    const pendingResp = await fetch(`${API_BASE}/api/pending`)
    const pendingData = await pendingResp.json()
    pendingItems.value = pendingData.items

    const faqResp = await fetch(`${API_BASE}/api/faqs`)
    const faqData = await faqResp.json()
    faqItems.value = faqData.items
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
}

async function approve(index: number) {
  const resp = await fetch(`${API_BASE}/api/approve/${index}`, { method: 'POST' })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}))
    alert(err.detail || '批准失败')
    return
  }
  await loadData()
}

async function reject(index: number) {
  const resp = await fetch(`${API_BASE}/api/reject/${index}`, { method: 'POST' })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}))
    alert(err.detail || '拒绝失败')
    return
  }
  await loadData()
}

onMounted(() => {
  loadData()
})
</script>

<template>
  <div class="admin-page">
    <h1 class="page-title">📋 FAQ 管理</h1>
    <p class="page-subtitle">审核用户提出的新问题，批准后会加入知识库</p>

    <!-- 待确认提案 -->
    <section class="section">
      <h2 class="section-title">待确认提案（{{ pendingItems.length }} 条）</h2>

      <div v-if="pendingItems.length === 0" class="empty-state">
        暂无待确认的 FAQ 提案
      </div>

      <div v-for="(item, i) in pendingItems" :key="i" class="proposal-card">
        <div class="proposal-question">{{ item.question }}</div>
        <div class="proposal-answer">{{ item.answer }}</div>
        <div class="proposal-meta">{{ item.created_at }}</div>

        <div v-if="item.original_answer && item.original_answer !== item.answer" class="original-toggle">
          <details>
            <summary>查看原始回答</summary>
            <p>{{ item.original_answer }}</p>
          </details>
        </div>

        <div class="proposal-actions">
          <button @click="approve(item._realIndex)" class="btn-approve">✅ 批准</button>
          <button @click="reject(item._realIndex)" class="btn-reject">❌ 拒绝</button>
        </div>
      </div>
    </section>

    <!-- 知识库 FAQ -->
    <section class="section">
      <h2 class="section-title">📚 知识库 FAQ（{{ faqItems.length }} 条）</h2>

      <div v-for="item in faqItems" :key="item.index" class="faq-item">
        <details>
          <summary><span class="faq-category">[{{ item.category }}]</span> {{ item.question }}</summary>
          <p class="faq-answer">{{ item.answer }}</p>
        </details>
      </div>
    </section>
  </div>
</template>

<style scoped>
.admin-page {
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

.section {
  margin-bottom: 32px;
}

.section-title {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 2px solid #4CAF50;
}

.empty-state {
  background: #f5f5f5;
  padding: 24px;
  border-radius: 8px;
  text-align: center;
  color: #888;
}

.proposal-card {
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}

.proposal-question {
  font-weight: 600;
  font-size: 16px;
  margin-bottom: 8px;
}

.proposal-answer {
  color: #555;
  line-height: 1.6;
  margin-bottom: 8px;
}

.proposal-meta {
  font-size: 12px;
  color: #999;
  margin-bottom: 12px;
}

.original-toggle summary {
  cursor: pointer;
  color: #4CAF50;
  font-size: 13px;
}

.original-toggle p {
  margin-top: 8px;
  padding: 8px 12px;
  background: #f9f9f9;
  border-radius: 4px;
  font-size: 13px;
  color: #666;
}

.proposal-actions {
  display: flex;
  gap: 8px;
}

.btn-approve, .btn-reject {
  padding: 6px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: opacity 0.2s;
}

.btn-approve {
  background: #4CAF50;
  color: #fff;
}

.btn-reject {
  background: #f44336;
  color: #fff;
}

.btn-approve:hover, .btn-reject:hover {
  opacity: 0.85;
}

.faq-item {
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 8px;
}

.faq-item summary {
  cursor: pointer;
  font-weight: 500;
}

.faq-category {
  color: #4CAF50;
  font-size: 12px;
  font-weight: 600;
  margin-right: 4px;
}

.faq-answer {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #eee;
  color: #555;
  line-height: 1.6;
  font-size: 14px;
}
</style>
