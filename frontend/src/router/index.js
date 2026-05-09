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
  { path: '/', component: GalleryView },
  { path: '/image/:id', component: DetailView },
  { path: '/projects', component: ProjectsListView },
  { path: '/projects/:slug', component: ProjectView },
  { path: '/tags', component: TagManagerView },
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

  if (to.meta.guestOnly && auth.isAuthenticated) {
    return { path: '/' }
  }
  return true
})

export default router
