import { createRouter, createWebHistory } from 'vue-router'
import GalleryView from '../views/GalleryView.vue'
import DetailView from '../views/DetailView.vue'
import ProjectView from '../views/ProjectView.vue'
import ProjectsListView from '../views/ProjectsListView.vue'
import TagManagerView from '../views/TagManagerView.vue'
import LoginView from '../views/LoginView.vue'
import RegisterView from '../views/RegisterView.vue'
import { useAuthStore } from '../stores/auth.js'

const routes = [
  { path: '/', component: GalleryView, meta: { requiresAuth: true } },
  { path: '/image/:id', component: DetailView, meta: { requiresAuth: true } },
  { path: '/projects', component: ProjectsListView, meta: { requiresAuth: true } },
  { path: '/projects/:slug', component: ProjectView, meta: { requiresAuth: true } },
  { path: '/tags', component: TagManagerView, meta: { requiresAuth: true } },
  { path: '/login', component: LoginView, meta: { guestOnly: true } },
  { path: '/register', component: RegisterView, meta: { guestOnly: true } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.init()

  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { path: '/login', query: { next: to.fullPath } }
  }
  if (to.meta.guestOnly && auth.isAuthenticated) {
    return { path: '/' }
  }
  return true
})

export default router
