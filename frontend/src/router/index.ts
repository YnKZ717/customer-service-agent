import { createRouter, createWebHistory } from 'vue-router'
import ChatView from '../views/ChatView.vue'
import AdminView from '../views/AdminView.vue'
import TicketsView from '../views/TicketsView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: '/chat' },
    { path: '/chat', name: 'chat', component: ChatView },
    { path: '/admin', name: 'admin', component: AdminView },
    { path: '/tickets', name: 'tickets', component: TicketsView },
  ],
})

export default router
