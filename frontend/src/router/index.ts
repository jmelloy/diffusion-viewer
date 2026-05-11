import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import GalleryView from '../views/GalleryView.vue'
import DetailView from '../views/DetailView.vue'
import ProjectView from '../views/ProjectView.vue'
import ProjectsListView from '../views/ProjectsListView.vue'
import AlbumView from '../views/AlbumView.vue'
import AlbumsListView from '../views/AlbumsListView.vue'
import TagManagerView from '../views/TagManagerView.vue'

const routes: RouteRecordRaw[] = [
  { path: '/', component: GalleryView },
  { path: '/image/:id', component: DetailView },
  { path: '/projects', component: ProjectsListView },
  { path: '/projects/:slug', component: ProjectView },
  { path: '/albums', component: AlbumsListView },
  { path: '/albums/:slug', component: AlbumView },
  { path: '/tags', component: TagManagerView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
