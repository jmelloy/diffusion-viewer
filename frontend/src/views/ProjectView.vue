<template>
  <div class="flex h-[calc(100vh-57px)] bg-gray-900">
    <!-- Sidebar -->
    <aside class="w-64 bg-gray-800 border-r border-gray-700 overflow-y-auto p-4 flex-shrink-0">
      <div class="text-xs text-gray-400 mb-2">
        <router-link to="/projects" class="hover:text-white">All projects</router-link>
        <template v-if="project?.parent_slug">
          <span class="mx-1">/</span>
          <router-link :to="`/projects/${project.parent_slug}`" class="hover:text-white capitalize">
            {{ project.parent_slug }}
          </router-link>
        </template>
      </div>
      <h2 class="text-lg font-bold text-white mb-4 capitalize">{{ project?.name ?? slug }}</h2>

      <!-- Sub-projects -->
      <div v-if="project?.children?.length" class="mb-5">
        <div class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Sub-projects</div>
        <ul class="space-y-0.5">
          <li v-for="c in project.children" :key="c.slug">
            <router-link
              :to="`/projects/${c.slug}`"
              class="flex items-center justify-between text-sm text-gray-300 hover:bg-gray-700 px-2 py-1 rounded"
            >
              <span class="truncate capitalize">📁 {{ c.name }}</span>
              <span class="text-xs text-gray-500 ml-2">{{ c.image_count }}</span>
            </router-link>
          </li>
        </ul>
      </div>

      <button
        v-if="activeRole || activeValue"
        @click="clearFilter"
        class="w-full text-xs text-purple-400 hover:text-purple-300 mb-3 text-left"
      >
        ← Clear filter
      </button>

      <div v-if="!project" class="text-sm text-gray-500 italic">Loading…</div>

      <div v-for="role in roleNames" :key="role" class="mb-5">
        <div class="flex items-center justify-between mb-1.5">
          <button
            @click="toggleRole(role)"
            :class="[
              'text-xs font-semibold uppercase tracking-wider',
              activeRole === role && !activeValue ? 'text-white' : 'text-gray-400 hover:text-white'
            ]"
          >
            {{ role || 'Unroled' }}
          </button>
          <span class="text-xs text-gray-500">{{ roleTotal(role) }}</span>
        </div>
        <ul class="space-y-0.5">
          <li v-for="[value, imgs] in sortedValues(role)" :key="value">
            <button
              @click="setFilter(role, value)"
              :class="[
                'flex items-center justify-between w-full text-left text-sm px-2 py-1 rounded',
                activeRole === role && activeValue === value
                  ? 'bg-purple-900/50 text-white'
                  : 'text-gray-300 hover:bg-gray-700'
              ]"
            >
              <span class="truncate">{{ value || '(unspecified)' }}</span>
              <span class="text-xs text-gray-500 ml-2">{{ imgs.length }}</span>
            </button>
          </li>
        </ul>
      </div>
    </aside>

    <!-- Main -->
    <div class="flex-1 overflow-y-auto p-6">
      <div v-if="loading" class="flex items-center justify-center h-64">
        <p class="text-gray-400 text-lg">Loading…</p>
      </div>

      <div v-else-if="!project" class="flex items-center justify-center h-64">
        <p class="text-gray-400">Project not found.</p>
      </div>

      <template v-else>
        <!-- Header -->
        <div class="flex items-center gap-3 mb-6">
          <h1 class="text-2xl font-bold text-white">
            <span v-if="activeRole">
              <span class="text-gray-500 capitalize">{{ activeRole }}:</span>
              <span class="ml-2">{{ activeValue || '(unspecified)' }}</span>
            </span>
            <span v-else class="capitalize">{{ project.name }}</span>
          </h1>
          <span class="text-gray-400 text-sm">
            ({{ filteredImages.length }} image{{ filteredImages.length !== 1 ? 's' : '' }})
          </span>
        </div>

        <!-- Filtered: flat grid -->
        <div v-if="activeRole" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
          <ImageThumb v-for="img in filteredImages" :key="img.id" :img="img" />
        </div>

        <!-- Unfiltered: swimlanes -->
        <template v-else>
          <div v-for="role in roleNames" :key="role" class="mb-10">
            <h2 class="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-3">
              {{ role || 'Unroled' }}
              <span class="text-xs text-gray-500 ml-2 normal-case font-normal">
                {{ roleTotal(role) }} images
              </span>
            </h2>
            <div v-for="[value, imgs] in sortedValues(role)" :key="value" class="mb-5">
              <button
                @click="setFilter(role, value)"
                class="text-xs text-gray-400 hover:text-white mb-2"
              >
                {{ value || '(unspecified)' }} ({{ imgs.length }}) →
              </button>
              <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8 gap-2">
                <ImageThumb v-for="img in imgs.slice(0, 8)" :key="img.id" :img="img" />
              </div>
            </div>
          </div>
        </template>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, h, defineComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import type { Image, ProjectDetail } from '../types/api'

const route = useRoute()
const router = useRouter()
const slug = computed<string>(() => String(route.params.slug ?? ''))
const project = ref<ProjectDetail | null>(null)
const loading = ref(false)

const activeRole = computed<string>(() => String(route.query.role ?? ''))
const activeValue = computed<string>(() => String(route.query.value ?? ''))

const ROLE_ORDER = [
  'suspect', 'weapon', 'room', 'character', 'scene', 'background', 'prop', 'concept', 'reference', '',
] as const

const roleNames = computed<string[]>(() => {
  if (!project.value) return []
  const present = Object.keys(project.value.roles)
  const known = (ROLE_ORDER as readonly string[]).filter((r) => present.includes(r))
  const extras = present.filter((r) => !(ROLE_ORDER as readonly string[]).includes(r)).sort()
  return [...known, ...extras]
})

function roleTotal(role: string): number {
  if (!project.value) return 0
  const values = project.value.roles[role] || {}
  return Object.values(values).reduce((sum, imgs) => sum + imgs.length, 0)
}

function sortedValues(role: string): [string, Image[]][] {
  if (!project.value) return []
  const values = project.value.roles[role] || {}
  return Object.entries(values).sort((a, b) => b[1].length - a[1].length)
}

const filteredImages = computed<Image[]>(() => {
  if (!project.value || !activeRole.value) return []
  const values = project.value.roles[activeRole.value] || {}
  if (activeValue.value) return values[activeValue.value] || []
  return Object.values(values).flat()
})

function setFilter(role: string, value: string): void {
  router.replace({ query: { role, value } })
}

function toggleRole(role: string): void {
  if (activeRole.value === role && !activeValue.value) clearFilter()
  else router.replace({ query: { role, value: '' } })
}

function clearFilter(): void {
  router.replace({ query: {} })
}

async function loadProject(): Promise<void> {
  loading.value = true
  project.value = null
  try {
    const res = await axios.get<ProjectDetail>(`/api/projects/${slug.value}`)
    project.value = res.data
  } catch (e) {
    if (axios.isAxiosError(e) && e.response?.status === 404) return
    console.error('loadProject failed', e)
  } finally {
    loading.value = false
  }
}

onMounted(loadProject)
watch(slug, loadProject)

const ImageThumb = defineComponent({
  props: { img: { type: Object as () => Image, required: true } },
  setup(props) {
    const onErr = (e: Event): void => {
      const target = e.target as HTMLImageElement
      target.src = `data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='100' height='100'%3E%3Crect width='100' height='100' fill='%23374151'/%3E%3C/svg%3E`
    }
    return () =>
      h(
        'div',
        {
          class: 'group rounded-lg overflow-hidden bg-gray-800 cursor-pointer aspect-square',
          onClick: () => router.push(`/image/${props.img.id}`),
        },
        [
          h('img', {
            src: `/api/images/${props.img.id}/thumbnail`,
            alt: props.img.filename,
            loading: 'lazy',
            class: 'w-full h-full object-cover transition-transform duration-200 group-hover:scale-105',
            onError: onErr,
          }),
        ],
      )
  },
})
</script>
