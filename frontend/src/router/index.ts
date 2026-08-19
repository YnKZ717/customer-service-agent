import { createRouter, createWebHistory } from 'vue-router'
import LoginView from '../views/LoginView.vue'
import ChatView from '../views/ChatView.vue'
import AdminView from '../views/AdminView.vue'
import TicketsView from '../views/TicketsView.vue'
import DashboardView from '../views/DashboardView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: '/chat' },
    { path: '/login', name: 'login', component: LoginView },
    { path: '/chat', name: 'chat', component: ChatView, meta: { requiresAuth: true } },
    { path: '/dashboard', name: 'dashboard', component: DashboardView, meta: { requiresAuth: true, roles: ['admin'] } },
    { path: '/admin', name: 'admin', component: AdminView, meta: { requiresAuth: true, roles: ['admin'] } },
    { path: '/tickets', name: 'tickets', component: TicketsView, meta: { requiresAuth: true, roles: ['admin', 'support'] } },
  ],
})

// 路由守卫
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  const userStr = localStorage.getItem('user')
  const user = userStr ? JSON.parse(userStr) : null

  // 需要登录的页面
  if (to.meta.requiresAuth) {
    if (!token || !user) {
      // 未登录，跳转登录页
      next({ path: '/login', query: { redirect: to.fullPath } })
      return
    }

    // 检查角色权限
    if (to.meta.roles && !to.meta.roles.includes(user.role)) {
      // 权限不足，跳转首页
      next({ path: '/chat' })
      return
    }

    next()
  } else {
    // 不需要登录的页面（如登录页）
    // 如果已登录且访问登录页，跳转到首页
    if (to.path === '/login' && token) {
      next({ path: '/chat' })
      return
    }
    next()
  }
})

export default router
