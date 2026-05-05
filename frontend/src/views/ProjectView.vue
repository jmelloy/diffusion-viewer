<template>
  <div class="min-h-screen bg-gray-900 p-6">
    <!-- Header -->
    <div class="flex items-center gap-4 mb-6">
      <router-link to="/" class="text-gray-400 hover:text-white transition-colors">← Gallery</router-link>
      <h1 class="text-2xl font-bold text-white capitalize">{{ project?.name ?? slug }}</h1>
      <span v-if="project" class="text-gray-400 text-sm">({{ project.image_count }} image{{ project.image_count !== 1 ? 's' : '' }})</span>
    </div>

    <div v-if="loading" class="flex items-center justify-center h-64">
      <p class="text-gray-400 text-lg">Loading…</p>
    </div>

    <div v-else-if="!project" class="flex items-center justify-center h-64">
      <p class="text-gray-400">Project not found.</p>
    </div>

    <template v-else>
      <!-- Role swimlanes -->
      <div v-for="role in ROLE_ORDER.filter(r => project.roles[r])" :key="role" class="mb-10">
        <div class="flex items-center gap-3 mb-3">
          <span :class="['w-3 h-3 rounded-full flex-shrink-0', ROLE_STYLES[role].dot]"></span>
          <h2 class="text-sm font-semibold text-gray-300 uppercase tracking-wider">
            {{ ROLE_STYLES[role].label }}
          </h2>
          <span class="text-xs text-gray-500">({{ project.roles[role].length }})</span>
        </div>
        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
          <div
            v-for="img in project.roles[role]"
            :key="img.id"
            class="relative group rounded-lg overflow-hidden bg-gray-800 cursor-pointer"
            @click="$router.push(`/image/${img.id}`)"
          >
            <div class="aspect-square overflow-hidden bg-gray-700">
              <img
                :src="`/api/images/${img.id}/thumbnail`"
                :alt="img.filename"
                class="w-full h-full object-cover transition-transform duration-200 group-hover:scale-105"
                loading="lazy"
                @error="onImgError"
              />
            </div>
            <!-- Role badge -->
            <span
              :class="['absolute top-1.5 right-1.5 text-xs px-1.5 py-0.5 rounded font-medium', ROLE_STYLES[role].badge]"
            >
              {{ ROLE_STYLES[role].label }}
            </span>
            <div class="p-2">
              <p class="text-xs text-gray-400 truncate" :title="img.filename">{{ img.filename }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Ungrouped fallback -->
      <div v-if="!hasAnyRoles" class="text-gray-500 text-sm italic">
        No images have been assigned roles in this project yet.
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'

const route = useRoute()
const slug = computed(() => route.params.slug)
const project = ref(null)
const loading = ref(false)

const ROLE_ORDER = ['character', 'scene', 'background', 'prop', 'concept', 'reference', 'other']

const ROLE_STYLES = {
  character: { label: 'Character', dot: 'bg-blue-400', badge: 'bg-blue-900/80 text-blue-300' },
  scene: { label: 'Scene', dot: 'bg-green-400', badge: 'bg-green-900/80 text-green-300' },
  background: { label: 'Background', dot: 'bg-yellow-400', badge: 'bg-yellow-900/80 text-yellow-300' },
  prop: { label: 'Prop', dot: 'bg-orange-400', badge: 'bg-orange-900/80 text-orange-300' },
  concept: { label: 'Concept', dot: 'bg-pink-400', badge: 'bg-pink-900/80 text-pink-300' },
  reference: { label: 'Reference', dot: 'bg-purple-400', badge: 'bg-purple-900/80 text-purple-300' },
  other: { label: 'Other', dot: 'bg-gray-400', badge: 'bg-gray-700/80 text-gray-300' },
}

const hasAnyRoles = computed(() => project.value && Object.keys(project.value.roles).length > 0)

async function loadProject() {
  loading.value = true
  project.value = null
  try {
    const res = await axios.get(`/api/projects/${slug.value}`)
    project.value = res.data
  } catch (e) {
    if (e.response?.status !== 404) console.error('loadProject failed', e)
  } finally {
    loading.value = false
  }
}

onMounted(loadProject)
watch(slug, loadProject)

function onImgError(e) {
  e.target.src = `data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='100' height='100'%3E%3Crect width='100' height='100' fill='%23374151'/%3E%3Ctext x='50%25' y='50%25' text-anchor='middle' dy='.3em' fill='%236b7280' font-size='12'%3ENo Image%3C/text%3E%3C/svg%3E`
}
</script>
