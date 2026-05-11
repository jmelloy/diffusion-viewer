<template>
  <div class="flex h-[calc(100vh-57px)] bg-gray-900">
    <!-- Sidebar -->
    <aside class="w-64 bg-gray-800 border-r border-gray-700 overflow-y-auto p-4 flex-shrink-0">
      <div class="text-xs text-gray-400 mb-2">
        <router-link to="/albums" class="hover:text-white">All albums</router-link>
        <template v-if="album?.parent_slug">
          <span class="mx-1">/</span>
          <router-link :to="`/albums/${album.parent_slug}`" class="hover:text-white capitalize">
            {{ album.parent_slug }}
          </router-link>
        </template>
      </div>

      <h2 class="text-lg font-bold text-white mb-1 capitalize">
        {{ album?.name ?? slug }}
      </h2>
      <p v-if="album?.description" class="text-xs text-gray-400 mb-4">{{ album.description }}</p>
      <p v-else class="mb-4" />

      <!-- Sub-albums -->
      <div v-if="album?.children?.length" class="mb-5">
        <div class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">
          Sub-albums
        </div>
        <ul class="space-y-0.5">
          <li v-for="c in album.children" :key="c.slug">
            <router-link
              :to="`/albums/${c.slug}`"
              class="flex items-center justify-between text-sm text-gray-300 hover:bg-gray-700 px-2 py-1 rounded"
            >
              <span class="truncate capitalize">📁 {{ c.name }}</span>
              <span class="text-xs text-gray-500 ml-2">{{ c.image_count }}</span>
            </router-link>
          </li>
        </ul>
      </div>

      <!-- Roles (album-level metadata) -->
      <div v-if="rolesByName.length" class="mb-5">
        <div class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">
          Roles
        </div>
        <div v-for="group in rolesByName" :key="group.role" class="mb-3">
          <div class="text-[10px] text-gray-500 uppercase tracking-wider mb-1">
            {{ group.role }}
          </div>
          <div class="flex flex-wrap gap-1">
            <span
              v-for="r in group.values"
              :key="r.id"
              class="inline-flex items-center gap-1 text-xs bg-gray-700 text-gray-200 px-2 py-0.5 rounded"
              :title="`role=${group.role} value=${r.value}`"
            >
              {{ r.value }}
              <button
                @click="onRemoveRole(r.id)"
                class="text-gray-400 hover:text-red-400 leading-none"
                title="Remove role"
              >×</button>
            </span>
          </div>
        </div>
      </div>

      <div v-if="!album && !loading" class="text-sm text-gray-500 italic">
        Album not found.
      </div>
    </aside>

    <!-- Main -->
    <div class="flex-1 overflow-y-auto p-6">
      <div v-if="loading" class="flex items-center justify-center h-64">
        <p class="text-gray-400 text-lg">Loading…</p>
      </div>

      <template v-else-if="album">
        <div class="flex items-center gap-3 mb-6">
          <h1 class="text-2xl font-bold text-white capitalize">{{ album.name }}</h1>
          <span class="text-gray-400 text-sm">
            ({{ album.images.length }} image{{ album.images.length !== 1 ? 's' : '' }})
          </span>
        </div>

        <div
          v-if="album.images.length"
          class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3"
        >
          <ImageThumb v-for="img in album.images" :key="img.id" :img="img" />
        </div>
        <div v-else class="text-gray-500 italic">No images in this album yet.</div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, h, defineComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import { useAlbumsStore } from '../stores/albums'
import type { AlbumDetail, AlbumRoleInfo, Image } from '../types/api'

interface RoleGroup {
  role: string
  values: AlbumRoleInfo[]
}

const route = useRoute()
const router = useRouter()
const store = useAlbumsStore()
const slug = computed<string>(() => String(route.params.slug ?? ''))
const album = ref<AlbumDetail | null>(null)
const loading = ref(false)

const ROLE_ORDER = [
  'suspect', 'weapon', 'room', 'character', 'scene', 'background', 'prop', 'concept', 'reference',
] as const

const rolesByName = computed<RoleGroup[]>(() => {
  if (!album.value?.roles?.length) return []
  const grouped: Record<string, AlbumRoleInfo[]> = {}
  for (const r of album.value.roles) {
    if (!grouped[r.role]) grouped[r.role] = []
    grouped[r.role].push(r)
  }
  for (const arr of Object.values(grouped)) {
    arr.sort((a, b) => a.value.localeCompare(b.value))
  }
  const present = Object.keys(grouped)
  const known = (ROLE_ORDER as readonly string[]).filter((r) => present.includes(r))
  const extras = present.filter((r) => !(ROLE_ORDER as readonly string[]).includes(r)).sort()
  return [...known, ...extras].map((role) => ({ role, values: grouped[role] }))
})

async function loadAlbum(): Promise<void> {
  loading.value = true
  album.value = null
  try {
    album.value = await store.fetchAlbum(slug.value)
  } catch (e) {
    if (axios.isAxiosError(e) && e.response?.status === 404) return
    console.error('fetchAlbum failed', e)
  } finally {
    loading.value = false
  }
}

async function onRemoveRole(roleId: number): Promise<void> {
  try {
    await store.removeRole(slug.value, roleId)
    await loadAlbum()
  } catch (e) {
    console.error('removeRole failed', e)
  }
}

onMounted(loadAlbum)
watch(slug, loadAlbum)

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
