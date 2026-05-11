<template>
  <div class="min-h-screen bg-gray-900 p-6" v-if="image">
    <!-- Back + Navigation -->
    <div class="flex items-center gap-4 mb-6">
      <router-link to="/" class="text-gray-400 hover:text-white transition-colors">← Gallery</router-link>
      <div class="flex gap-2 ml-auto">
        <button
          @click="navigate(-1)"
          :disabled="!prevId"
          class="bg-gray-700 hover:bg-gray-600 disabled:opacity-40 text-white px-3 py-1.5 rounded text-sm transition-colors"
        >
          ← Prev
        </button>
        <button
          @click="navigate(1)"
          :disabled="!nextId"
          class="bg-gray-700 hover:bg-gray-600 disabled:opacity-40 text-white px-3 py-1.5 rounded text-sm transition-colors"
        >
          Next →
        </button>
      </div>
    </div>

    <div class="flex flex-col lg:flex-row gap-6">
      <!-- Image display -->
      <div class="flex-1 flex items-start justify-center">
        <img
          :src="`/api/images/${image.id}/file`"
          :alt="image.filename"
          class="max-w-full max-h-[80vh] object-contain rounded-lg shadow-2xl"
        />
      </div>

      <!-- Info panel -->
      <aside class="w-full lg:w-80 flex-shrink-0 space-y-4">
        <!-- Rating -->
        <div class="bg-gray-800 rounded-xl p-4">
          <h3 class="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">Rating</h3>
          <RatingWidget :image-id="image.id" :rating="image.rating" @rate="handleRate" size="lg" />
        </div>

        <!-- Tags -->
        <div class="bg-gray-800 rounded-xl p-4">
          <h3 class="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">Tags</h3>
          <TagManager :image-id="image.id" :tags="image.tags" @updated="refreshImage" />
        </div>

        <!-- Projects -->
        <div class="bg-gray-800 rounded-xl p-4">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-semibold text-gray-400 uppercase tracking-wider">Projects</h3>
            <button
              @click="showProjectModal = true"
              class="text-xs bg-indigo-700 hover:bg-indigo-600 text-white px-2 py-0.5 rounded transition-colors"
            >
              + Assign
            </button>
          </div>
          <div v-if="imageProjects.length" class="flex flex-wrap gap-1">
            <router-link
              v-for="p in imageProjects"
              :key="p.slug"
              :to="`/projects/${p.slug}`"
              class="bg-indigo-900/60 hover:bg-indigo-800/80 text-indigo-300 text-xs px-2 py-0.5 rounded transition-colors"
            >
              📁 {{ p.name }}
              <span v-if="p.roles.length" class="ml-1 text-indigo-400">
                ({{ p.roles.join(', ') }})
              </span>
            </router-link>
          </div>
          <p v-else class="text-xs text-gray-500 italic">Not assigned to any project</p>
        </div>

        <!-- Metadata -->
        <div class="bg-gray-800 rounded-xl p-4">
          <h3 class="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">Metadata</h3>
          <dl class="space-y-1 text-sm">
            <div class="flex justify-between gap-2">
              <dt class="text-gray-400">Filename</dt>
              <dd class="text-white text-right truncate max-w-[180px]" :title="image.filename">{{ image.filename }}</dd>
            </div>
            <div v-if="image.date_taken" class="flex justify-between">
              <dt class="text-gray-400">Date</dt>
              <dd class="text-white">{{ formatDate(image.date_taken) }}</dd>
            </div>
            <div v-if="image.width" class="flex justify-between">
              <dt class="text-gray-400">Dimensions</dt>
              <dd class="text-white">{{ image.width }} × {{ image.height }}</dd>
            </div>
            <div v-if="image.file_size" class="flex justify-between">
              <dt class="text-gray-400">File Size</dt>
              <dd class="text-white">{{ formatSize(image.file_size) }}</dd>
            </div>
            <div v-if="image.model" class="flex justify-between gap-2">
              <dt class="text-gray-400">Model</dt>
              <dd class="text-white text-right truncate max-w-[180px]" :title="image.model">{{ image.model }}</dd>
            </div>
          </dl>
        </div>

        <!-- Prompt / Description -->
        <div v-if="image.prompt || image.description" class="bg-gray-800 rounded-xl p-4">
          <h3 class="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">Prompt / Description</h3>
          <div v-if="image.prompt">
            <p class="text-xs text-gray-400 mb-1">Prompt</p>
            <p class="text-sm text-gray-200 whitespace-pre-wrap break-words">{{ image.prompt }}</p>
          </div>
          <div v-if="image.description" class="mt-3">
            <p class="text-xs text-gray-400 mb-1">Description</p>
            <p class="text-sm text-gray-200 whitespace-pre-wrap break-words">{{ image.description }}</p>
          </div>
        </div>

        <!-- Raw Sidecar JSON -->
        <div v-if="image.sidecar_data" class="bg-gray-800 rounded-xl p-4">
          <button
            @click="showSidecar = !showSidecar"
            class="text-sm font-semibold text-gray-400 uppercase tracking-wider w-full text-left flex justify-between items-center"
          >
            <span>Sidecar JSON</span>
            <span>{{ showSidecar ? '▲' : '▼' }}</span>
          </button>
          <pre
            v-if="showSidecar"
            class="mt-3 text-xs text-gray-300 overflow-x-auto bg-gray-900 rounded p-2 max-h-64 overflow-y-auto"
          >{{ parsedSidecar }}</pre>
        </div>

        <!-- Directory -->
        <div class="bg-gray-800 rounded-xl p-4">
          <p class="text-xs text-gray-400 truncate" :title="image.filepath">{{ image.filepath }}</p>
        </div>
      </aside>
    </div>
  </div>
  <div v-else class="flex items-center justify-center h-64">
    <p class="text-gray-400">{{ loading ? 'Loading…' : 'Image not found' }}</p>
  </div>

  <!-- Assign to project modal -->
  <AssignProjectModal
    v-if="showProjectModal && image"
    :image-id="image.id"
    :image-tags="image.tags"
    @close="showProjectModal = false"
    @assigned="onProjectAssigned"
  />
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import { useImagesStore } from '../stores/images'
import RatingWidget from '../components/RatingWidget.vue'
import TagManager from '../components/TagManager.vue'
import AssignProjectModal from '../components/AssignProjectModal.vue'
import type { Image } from '../types/api'

interface ProjectChip {
  slug: string
  name: string
  roles: string[]
}

const route = useRoute()
const router = useRouter()
const store = useImagesStore()
const image = ref<Image | null>(null)
const loading = ref(false)
const showSidecar = ref(false)
const showProjectModal = ref(false)

const imageProjects = computed<ProjectChip[]>(() => {
  if (!image.value?.tags) return []
  const projects: Record<string, ProjectChip> = {}
  for (const tag of image.value.tags) {
    const parts = tag.name.split(':')
    if (parts[0] !== 'project') continue
    const slug = parts[1]
    if (!slug) continue
    if (!projects[slug]) {
      projects[slug] = {
        slug,
        name: slug.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
        roles: [],
      }
    }
    if (parts[2]) projects[slug].roles.push(parts[2])
  }
  return Object.values(projects)
})

async function onProjectAssigned(updatedImage?: Image): Promise<void> {
  if (updatedImage) image.value = updatedImage
  else await refreshImage()
}

async function loadImage(): Promise<void> {
  loading.value = true
  try {
    const res = await axios.get<Image>(`/api/images/${route.params.id}`)
    image.value = res.data
  } catch {
    image.value = null
  } finally {
    loading.value = false
  }
}

async function refreshImage(): Promise<void> {
  await loadImage()
}

onMounted(loadImage)
watch(() => route.params.id, loadImage)

async function handleRate(rating: number): Promise<void> {
  if (!image.value) return
  await store.rateImage(image.value.id, rating)
  image.value.rating = rating
  image.value.hidden = rating === -1
}

const currentIndex = computed<number>(() =>
  store.images.findIndex((i) => i.id === image.value?.id),
)
const prevId = computed<number | null>(() =>
  currentIndex.value > 0 ? store.images[currentIndex.value - 1].id : null,
)
const nextId = computed<number | null>(() =>
  currentIndex.value >= 0 && currentIndex.value < store.images.length - 1
    ? store.images[currentIndex.value + 1].id
    : null,
)

function navigate(dir: -1 | 1): void {
  const id = dir === -1 ? prevId.value : nextId.value
  if (id) router.push(`/image/${id}`)
}

const parsedSidecar = computed<string>(() => {
  const raw = image.value?.sidecar_data
  if (!raw) return ''
  try {
    return JSON.stringify(JSON.parse(raw), null, 2)
  } catch {
    return raw
  }
})

function formatDate(dt: string | null | undefined): string {
  if (!dt) return ''
  return new Date(dt).toLocaleString()
}

function formatSize(bytes: number | null | undefined): string {
  if (bytes == null) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
</script>
