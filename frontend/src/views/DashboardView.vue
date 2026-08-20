<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Line, Bar } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler
)

const API_BASE = 'http://localhost:8001'
const token = localStorage.getItem('token')
const headers = {
  'Content-Type': 'application/json',
  'Authorization': `Bearer ${token}`,
}

// ─ 数据 ─────────────────────────────────────────────
interface DashboardData {
  summary: {
    total_calls: number
    kb_hits: number
    llm_calls: number
    tickets_created: number
    troubleshoot_count: number
    fallback_count: number
    kb_hit_rate: number
    total_days: number
  }
  daily_trend: {
    date: string
    calls: number
    kb: number
    llm: number
    troubleshoot: number
    fallback: number
    hit_rate: number
  }[]
  feedback_stats: {
    total: number
    average: number
    distribution: Record<number, number>
  }
}

const data = ref<DashboardData | null>(null)
const loading = ref(true)

// ── 指标卡片 ──────────────────────────────────────────
const cards = ref([
  { label: '总问答量', value: 0, icon: '💬', color: '#4CAF50' },
  { label: '知识库命中率', value: '0%', icon: '', color: '#2196F3' },
  { label: '模型降级', value: 0, icon: '️', color: '#FF5722' },
  { label: '满意度', value: '0', icon: '⭐', color: '#9C27B0' },
])

// ─ 图表1：每日问答量趋势 ──────────────────────────────
const trendChartOptions = ref({
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: true, position: 'top' as const },
    title: { display: false },
  },
  scales: {
    y: { beginAtZero: true, title: { display: true, text: '次数' } },
    x: { title: { display: true, text: '日期' } },
  },
})

const trendChartData = ref({
  labels: [] as string[],
  datasets: [
    {
      label: '知识库回答',
      data: [] as number[],
      borderColor: '#4CAF50',
      backgroundColor: 'rgba(76, 175, 80, 0.1)',
      fill: true,
      tension: 0.4,
    },
    {
      label: 'LLM 回答',
      data: [] as number[],
      borderColor: '#2196F3',
      backgroundColor: 'rgba(33, 150, 243, 0.1)',
      fill: true,
      tension: 0.4,
    },
    {
      label: '总调用',
      data: [] as number[],
      borderColor: '#FF9800',
      backgroundColor: 'rgba(255, 152, 0, 0.05)',
      fill: true,
      tension: 0.4,
      borderDash: [5, 5],
    },
  ],
})

// ── 图表2：知识命中率 vs LLM 调用（堆叠柱状图） ─────────
const kbChartOptions = ref({
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: true, position: 'top' as const },
    title: { display: false },
  },
  scales: {
    x: { stacked: true, title: { display: true, text: '日期' } },
    y: { stacked: true, beginAtZero: true, title: { display: true, text: '次数' } },
  },
})

const kbChartData = ref({
  labels: [] as string[],
  datasets: [
    {
      label: '知识库',
      data: [] as number[],
      backgroundColor: '#4CAF50',
    },
    {
      label: 'LLM',
      data: [] as number[],
      backgroundColor: '#2196F3',
    },
  ],
})

// ── 图表3：满意度分布 ─────────────────────────────────
const feedbackChartOptions = ref({
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    title: { display: false },
  },
  scales: {
    y: { beginAtZero: true, title: { display: true, text: '次数' } },
    x: { title: { display: true, text: '评分' } },
  },
})

const feedbackChartData = ref({
  labels: ['⭐ 1星', '⭐⭐ 2星', '⭐⭐⭐ 3星', '⭐⭐⭐⭐ 4星', '⭐⭐⭐⭐⭐ 5星'],
  datasets: [
    {
      label: '评分分布',
      data: [0, 0, 0, 0, 0] as number[],
      backgroundColor: ['#f44336', '#FF9800', '#FFC107', '#8BC34A', '#4CAF50'],
    },
  ],
})

// ── 加载数据 ──────────────────────────────────────────
async function loadData() {
  loading.value = true
  try {
    const resp = await fetch(`${API_BASE}/api/stats/dashboard`, { headers })
    const json = await resp.json()
    data.value = json

    // 更新指标卡片
    cards.value[0].value = json.summary.total_calls
    cards.value[1].value = json.summary.kb_hit_rate + '%'
    cards.value[2].value = json.summary.fallback_count
    cards.value[3].value = json.feedback_stats.average > 0 ? json.feedback_stats.average.toFixed(1) : '—'

    // 更新图表1：每日趋势
    trendChartData.value.labels = json.daily_trend.map((d: any) => d.date.slice(5)) // 只显示 MM-DD
    trendChartData.value.datasets[0].data = json.daily_trend.map((d: any) => d.kb)
    trendChartData.value.datasets[1].data = json.daily_trend.map((d: any) => d.llm)
    trendChartData.value.datasets[2].data = json.daily_trend.map((d: any) => d.calls)

    // 更新图表2：KB vs LLM
    kbChartData.value.labels = json.daily_trend.map((d: any) => d.date.slice(5))
    kbChartData.value.datasets[0].data = json.daily_trend.map((d: any) => d.kb)
    kbChartData.value.datasets[1].data = json.daily_trend.map((d: any) => d.llm)

    // 更新图表3：满意度
    const dist = json.feedback_stats.distribution
    feedbackChartData.value.datasets[0].data = [
      dist[1] || 0,
      dist[2] || 0,
      dist[3] || 0,
      dist[4] || 0,
      dist[5] || 0,
    ]
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadData()
})
</script>

<template>
  <div class="dashboard-page">
    <h1 class="page-title">📊 数据看板</h1>
    <p class="page-subtitle">客服系统运营数据概览</p>

    <div v-if="loading" class="loading">加载中...</div>

    <template v-else-if="data">
      <!-- 指标卡片 -->
      <div class="metric-cards">
        <div v-for="card in cards" :key="card.label" class="metric-card" :style="{ borderTopColor: card.color }">
          <div class="metric-icon" :style="{ background: card.color + '15', color: card.color }">
            {{ card.icon }}
          </div>
          <div class="metric-info">
            <div class="metric-label">{{ card.label }}</div>
            <div class="metric-value" :style="{ color: card.color }">{{ card.value }}</div>
          </div>
        </div>
      </div>

      <!-- 图表区 -->
      <div class="charts-row">
        <!-- 图表1：每日问答量趋势 -->
        <div class="chart-card">
          <h3 class="chart-title">📈 每日问答量趋势</h3>
          <div class="chart-container">
            <Line :data="trendChartData" :options="trendChartOptions" />
          </div>
        </div>

        <!-- 图表2：KB vs LLM -->
        <div class="chart-card">
          <h3 class="chart-title">📊 知识库 vs LLM 调用分布</h3>
          <div class="chart-container">
            <Bar :data="kbChartData" :options="kbChartOptions" />
          </div>
        </div>
      </div>

      <!-- 图表3：满意度分布 -->
      <div class="charts-row single">
        <div class="chart-card">
          <h3 class="chart-title">⭐ 用户满意度分布</h3>
          <div class="chart-container small">
            <Bar :data="feedbackChartData" :options="feedbackChartOptions" />
          </div>
          <div class="feedback-summary" v-if="data.feedback_stats.total > 0">
            共 {{ data.feedback_stats.total }} 条反馈，平均 {{ data.feedback_stats.average.toFixed(1) }} 分
          </div>
          <div class="feedback-summary" v-else>
            暂无反馈数据
          </div>
        </div>
      </div>

      <!-- 每日明细表 -->
      <div class="charts-row single">
        <div class="chart-card">
          <h3 class="chart-title">📋 每日明细</h3>
          <table class="detail-table">
            <thead>
              <tr>
                <th>日期</th>
                <th>总调用</th>
                <th>知识库</th>
                <th>LLM</th>
                <th>排查</th>
                <th>命中率</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="day in data.daily_trend" :key="day.date">
                <td>{{ day.date }}</td>
                <td>{{ day.calls }}</td>
                <td class="text-kb">{{ day.kb }}</td>
                <td class="text-llm">{{ day.llm }}</td>
                <td>{{ day.troubleshoot }}</td>
                <td>
                  <span class="hit-rate" :class="{ high: day.hit_rate >= 50, low: day.hit_rate < 30 }">
                    {{ day.hit_rate }}%
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.dashboard-page {
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

.loading {
  text-align: center;
  padding: 48px;
  color: #888;
  background: #fff;
  border-radius: 12px;
}

/* ─ 指标卡片 ── */
.metric-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.metric-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  border-top: 4px solid;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  display: flex;
  align-items: center;
  gap: 16px;
}

.metric-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
}

.metric-label {
  font-size: 13px;
  color: #888;
  margin-bottom: 4px;
}

.metric-value {
  font-size: 24px;
  font-weight: 700;
}

/* ── 图表区 ── */
.charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}

.charts-row.single {
  grid-template-columns: 1fr;
}

.chart-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.chart-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
  color: #333;
}

.chart-container {
  height: 280px;
}

.chart-container.small {
  height: 200px;
}

/* ── 满意度摘要 ── */
.feedback-summary {
  text-align: center;
  margin-top: 12px;
  font-size: 13px;
  color: #888;
}

/* ─ 明细表 ── */
.detail-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.detail-table th {
  background: #f5f5f5;
  padding: 10px 12px;
  text-align: left;
  font-weight: 600;
  color: #555;
  border-bottom: 2px solid #e0e0e0;
}

.detail-table td {
  padding: 10px 12px;
  border-bottom: 1px solid #f0f0f0;
}

.detail-table tbody tr:hover {
  background: #f9f9f9;
}

.text-kb {
  color: #4CAF50;
  font-weight: 600;
}

.text-llm {
  color: #2196F3;
  font-weight: 600;
}

.hit-rate {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 600;
}

.hit-rate.high {
  background: #e8f5e9;
  color: #2e7d32;
}

.hit-rate.low {
  background: #fff3e0;
  color: #e65100;
}

/* ── 响应式 ── */
@media (max-width: 900px) {
  .metric-cards {
    grid-template-columns: repeat(2, 1fr);
  }
  .charts-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 600px) {
  .metric-cards {
    grid-template-columns: 1fr;
  }
}
</style>
