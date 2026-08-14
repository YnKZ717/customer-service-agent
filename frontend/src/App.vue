<script setup lang="ts">
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { ref } from 'vue'

const router = useRouter()

// 获取当前用户
const user = ref<any>(null)

// 每次路由变化时重新读取用户信息
router.afterEach(() => {
  const userStr = localStorage.getItem('user')
  if (userStr) {
    user.value = JSON.parse(userStr)
  } else {
    user.value = null
  }
})

// 初始化时读取一次
const userStr = localStorage.getItem('user')
if (userStr) {
  user.value = JSON.parse(userStr)
}

function handleLogout() {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  user.value = null
  router.push('/login')
}

// 根据角色显示导航
const showAdmin = () => user.value?.role === 'admin'
const showTickets = () => user.value?.role === 'admin' || user.value?.role === 'support'
</script>

<template>
  <div class="app-layout">
    <!-- 侧边栏 -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <h2>🤖 Neowow 客服</h2>
        <div v-if="user" class="user-info">
          <span class="user-name">{{ user.name }}</span>
          <span class="user-role" :class="'role-' + user.role">
            {{ user.role === 'admin' ? '管理员' : user.role === 'support' ? '客服' : '用户' }}
          </span>
        </div>
      </div>

      <nav>
        <RouterLink to="/chat" class="nav-item">💬 客服对话</RouterLink>
        <RouterLink v-if="showTickets()" to="/tickets" class="nav-item"> 工单管理</RouterLink>
        <RouterLink v-if="showAdmin()" to="/admin" class="nav-item">📋 FAQ 管理</RouterLink>
      </nav>

      <div class="logout-section">
        <button @click="handleLogout" class="logout-btn">退出登录</button>
      </div>
    </aside>

    <!-- 主内容区 -->
    <main class="main-content">
      <RouterView />
    </main>
  </div>
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: #f0f2f5;
  color: #333;
}

.app-layout {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  width: 220px;
  background: #1a1a2e;
  color: #fff;
  padding: 20px 0;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  padding: 0 20px 20px;
  border-bottom: 1px solid rgba(255,255,255,0.1);
  margin-bottom: 10px;
}

.sidebar-header h2 {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 12px;
}

.user-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.user-name {
  font-size: 14px;
  font-weight: 500;
}

.user-role {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  display: inline-block;
  width: fit-content;
}

.role-admin {
  background: #4CAF50;
  color: #fff;
}

.role-support {
  background: #2196F3;
  color: #fff;
}

.role-user {
  background: #9E9E9E;
  color: #fff;
}

nav {
  flex: 1;
}

.nav-item {
  display: block;
  padding: 12px 20px;
  color: rgba(255,255,255,0.7);
  text-decoration: none;
  font-size: 15px;
  transition: all 0.2s;
}

.nav-item:hover {
  background: rgba(255,255,255,0.1);
  color: #fff;
}

.nav-item.router-link-active {
  background: rgba(255,255,255,0.15);
  color: #fff;
  border-left: 3px solid #4CAF50;
}

.logout-section {
  padding: 20px;
  border-top: 1px solid rgba(255,255,255,0.1);
}

.logout-btn {
  width: 100%;
  padding: 10px;
  background: rgba(255,255,255,0.1);
  color: #fff;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  transition: background 0.2s;
}

.logout-btn:hover {
  background: rgba(255,255,255,0.2);
}

.main-content {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
}
</style>
