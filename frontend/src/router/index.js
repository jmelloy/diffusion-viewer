import { createRouter, createWebHistory } from 'vue-router'
import GalleryView from '../views/GalleryView.vue'
import DetailView from '../views/DetailView.vue'
import ProjectView from '../views/ProjectView.vue'
import ProjectsListView from '../views/ProjectsListView.vue'

const routes = [
  { path: '/', component: GalleryView },
  { path: '/image/:id', component: DetailView },
  { path: '/projects', component: ProjectsListView },
  { path: '/projects/:slug', component: ProjectView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
