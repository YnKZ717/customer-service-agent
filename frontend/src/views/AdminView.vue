<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

const API_BASE = 'http://192.168.10.209:8001'
const API_KEY = 'neowow-dev-2026'
const headers = { 'Content-Type': 'application/json', 'X-API-Key': API_KEY }

// 分类定义
const CATEGORIES = [
  { key: 'all', name: '全部', icon: '📋' },
  { key: 'account', name: '账户管理', icon: '' },
  { key: 'billing', name: '充值支付', icon: '💰' },
  { key: 'codingplan', name: '套餐服务', icon: '📦' },
  { key: 'agent_service', name: '智能体使用', icon: '🤖' },
  { key: 'desktop', name: '桌面客户端', icon: '💻' },
  { key: 'app_market', name: '应用市场', icon: '️' },
  { key: 'skill_market', name: '技能市场', icon: '🎯' },
  { key: 'deploy_token', name: '部署 Token', icon: '' },
  { key: 'backup', name: '数据备份', icon: '☁️' },
  { key: 'complaint', name: '投诉反馈', icon: '' },
  { key: 'team', name: '团队协作', icon: '👥' },
  { key: 'export', name: '作品导出', icon: '' },
  { key: 'api', name: 'API 接口', icon: '' },
  { key: 'video_generation', name: '视频生成', icon: '🎬' },
  { key: 'image_generation', name: '图片生成', icon: '🖼️' },
  { key: 'audio_processing', name: '音频处理', icon: '🎵' },
  { key: 'project_management', name: '项目管理', icon: '📁' },
  { key: 'task_status', name: '任务状态', icon: '⏳' },
  { key: 'troubleshoot', name: '故障排查', icon: '🔧' },
]

interface FaqItem {
  id: number
  question: string
  answer: string
  category: string
}

const faqItems = ref<FaqItem[]>([])
const pendingItems = ref<any[]>([])
const loading = ref(false)
const activeCategory = ref('all')
const showAddForm = ref(false)
const editingItem = ref<FaqItem | null>(null)

// 新增/编辑表单
const formData = ref({ question: '', answer: '', category: 'account' })

// 按分类过滤
const filteredFaqs = computed(() => {
  if (activeCategory.value === 'all') return faqItems.value
  return faqItems.value.filter(f => f.category === activeCategory.value)
})

// 各分类数量
const categoryCounts = computed(() => {
  const counts: Record<string, number> = { all: faqItems.value.length }
  for (const f of faqItems.value) {
    counts[f.category] = (counts[f.category] || 0) + 1
  }
  return counts
})

async function loadData() {
  loading.value = true
  try {
    const faqResp = await fetch(`${API_BASE}/api/faqs`, { headers })
    const faqData = await faqResp.json()
    faqItems.value = faqData.items.map((item: any, idx: number) => ({
      ...item,
      id: idx
    }))

    const pendingResp = await fetch(`${API_BASE}/api/pending`, { headers })
    const pendingData = await pendingResp.json()
    pendingItems.value = pendingData.items
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
}

function openAddForm() {
  formData.value = { question: '', answer: '', category: 'account' }
  showAddForm.value = true
  editingItem.value = null
}

function openEditForm(item: FaqItem) {
  formData.value = { question: item.question, answer: item.answer, category: item.category }
  editingItem.value = item
  showAddForm.value = true
}

async function saveForm() {
  if (!formData.value.question.trim() || !formData.value.answer.trim()) return

  if (editingItem.value) {
    // 编辑现有 FAQ
    try {
      const resp = await fetch(`${API_BASE}/api/faqs/${editingItem.value.id}`, {
        method: 'PUT',
        headers,
        body: JSON.stringify(formData.value),
      })
      if (resp.ok) {
        showAddForm.value = false
        editingItem.value = null
        await loadData()
      }
    } catch {
      alert('更新失败')
    }
  } else {
    // 新增 FAQ
    try {
      const resp = await fetch(`${API_BASE}/api/faqs`, {
        method: 'POST',
        headers,
        body: JSON.stringify(formData.value),
      })
      if (resp.ok) {
        showAddForm.value = false
        await loadData()
      }
    } catch {
      alert('添加失败')
    }
  }
}

async function deleteFaq(id: number) {
  if (!confirm('确定要删除这条 FAQ 吗？')) return

  try {
    const resp = await fetch(`${API_BASE}/api/faqs/${id}`, { method: 'DELETE', headers })
    if (resp.ok) {
      await loadData()
    }
  } catch {
    alert('删除失败')
  }
}

function getCategoryName(key: string): string {
  const cat = CATEGORIES.find(c => c.key === key)
  return cat ? `${cat.icon} ${cat.name}` : key
}

onMounted(() => {
  loadData()
})
</script>

<template>
  <div class="admin-page">
    <h1 class="page-title">📋 FAQ 管理</h1>
    <p class="page-subtitle">管理知识库 FAQ，支持分类查看、增删改查</p>

    <!-- 分类标签 -->
    <div class="category-tabs">
      <button
        v-for="cat in CATEGORIES"
        :key="cat.key"
        :class="['tab', { active: activeCategory === cat.key }]"
        @click="activeCategory = cat.key"
      >
        {{ cat.icon }} {{ cat.name }}
        <span class="tab-count">{{ categoryCounts[cat.key] || 0 }}</span>
      </button>
    </div>

    <!-- 操作栏 -->
    <div class="action-bar">
      <div class="filter-info">
        当前显示：<strong>{{ filteredFaqs.length }}</strong> 条 FAQ
      </div>
      <button @click="openAddForm" class="btn-add">➕ 新增 FAQ</button>
    </div>

    <!-- FAQ 列表 -->
    <div v-if="loading" class="loading">加载中...</div>

    <div v-else class="faq-list">
      <div v-for="item in filteredFaqs" :key="item.id" class="faq-card">
        <div class="faq-header">
          <span class="faq-category">{{ getCategoryName(item.category) }}</span>
          <div class="faq-actions">
            <button @click="openEditForm(item)" class="btn-edit">✏️ 编辑</button>
            <button @click="deleteFaq(item.id)" class="btn-delete">️ 删除</button>
          </div>
        </div>
        <div class="faq-question">{{ item.question }}</div>
        <div class="faq-answer">{{ item.answer }}</div>
      </div>

      <div v-if="filteredFaqs.length === 0" class="empty-state">
        该分类下暂无 FAQ
      </div>
    </div>

    <!-- 新增/编辑弹窗 -->
    <div v-if="showAddForm" class="modal-overlay" @click.self="showAddForm = false">
      <div class="modal">
        <h3>{{ editingItem ? '编辑 FAQ' : '新增 FAQ' }}</h3>

        <div class="form-group">
          <label>问题</label>
          <input v-model="formData.question" placeholder="输入问题..." class="form-input" />
        </div>

        <div class="form-group">
          <label>答案</label>
          <textarea v-model="formData.answer" placeholder="输入答案..." class="form-textarea"></textarea>
        </div>

        <div class="form-group">
          <label>分类</label>
          <select v-model="formData.category" class="form-select">
            <option v-for="cat in CATEGORIES.filter(c => c.key !== 'all')" :key="cat.key" :value="cat.key">
              {{ cat.icon }} {{ cat.name }}
            </option>
          </select>
        </div>

        <div class="modal-actions">
          <button @click="showAddForm = false" class="btn-cancel">取消</button>
          <button @click="saveForm" :disabled="!formData.question.trim() || !formData.answer.trim()" class="btn-save">
            保存
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.admin-page {
  max-width: 1200px;
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

/* 分类标签 */
.category-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
  flex-wrap: wrap;
  padding-bottom: 16px;
  border-bottom: 2px solid #eee;
}

.tab {
  padding: 8px 14px;
  border: 1px solid #ddd;
  border-radius: 20px;
  background: #fff;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 6px;
}

.tab:hover {
  background: #f5f5f5;
  border-color: #4CAF50;
}

.tab.active {
  background: #4CAF50;
  color: #fff;
  border-color: #4CAF50;
}

.tab-count {
  background: rgba(0,0,0,0.1);
  padding: 2px 6px;
  border-radius: 10px;
  font-size: 11px;
}

.tab.active .tab-count {
  background: rgba(255,255,255,0.3);
}

/* 操作栏 */
.action-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.filter-info {
  font-size: 14px;
  color: #666;
}

.btn-add {
  padding: 10px 20px;
  background: #4CAF50;
  color: #fff;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  transition: background 0.2s;
}

.btn-add:hover {
  background: #388E3C;
}

/* FAQ 列表 */
.faq-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.faq-card {
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  transition: box-shadow 0.2s;
}

.faq-card:hover {
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}

.faq-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.faq-category {
  font-size: 12px;
  color: #4CAF50;
  font-weight: 600;
  padding: 4px 10px;
  background: #e8f5e9;
  border-radius: 12px;
}

.faq-actions {
  display: flex;
  gap: 8px;
}

.btn-edit, .btn-delete {
  padding: 4px 10px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: opacity 0.2s;
}

.btn-edit {
  background: #e3f2fd;
  color: #1976d2;
}

.btn-delete {
  background: #ffebee;
  color: #c62828;
}

.btn-edit:hover, .btn-delete:hover {
  opacity: 0.8;
}

.faq-question {
  font-weight: 600;
  font-size: 15px;
  margin-bottom: 8px;
  color: #333;
}

.faq-answer {
  color: #666;
  font-size: 14px;
  line-height: 1.6;
}

/* 弹窗 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  width: 90%;
  max-width: 500px;
  max-height: 80vh;
  overflow-y: auto;
}

.modal h3 {
  margin-bottom: 20px;
  font-size: 18px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 6px;
  color: #333;
}

.form-input, .form-textarea, .form-select {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 14px;
  font-family: inherit;
  transition: border-color 0.2s;
}

.form-input:focus, .form-textarea:focus, .form-select:focus {
  outline: none;
  border-color: #4CAF50;
}

.form-textarea {
  min-height: 100px;
  resize: vertical;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
}

.btn-cancel, .btn-save {
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  transition: opacity 0.2s;
}

.btn-cancel {
  background: #f5f5f5;
  color: #666;
}

.btn-save {
  background: #4CAF50;
  color: #fff;
  font-weight: 600;
}

.btn-save:disabled {
  background: #ccc;
  cursor: not-allowed;
}

.btn-cancel:hover, .btn-save:hover:not(:disabled) {
  opacity: 0.85;
}

.loading, .empty-state {
  text-align: center;
  padding: 48px;
  color: #888;
  background: #fff;
  border-radius: 12px;
}
</style>
