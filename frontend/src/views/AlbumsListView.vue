<template>
  <div class="min-h-screen bg-gray-900 p-6">
    <div class="flex items-center gap-4 mb-6">
      <router-link to="/" class="text-gray-400 hover:text-white transition-colors">← Gallery</router-link>
      <h1 class="text-2xl font-bold text-white">Albums</h1>
      <span class="text-xs text-gray-500 uppercase tracking-wider">new</span>
      <div class="flex-1" />
      <button
        @click="onSync"
        :disabled="store.syncing"
        class="text-xs text-gray-400 hover:text-white border border-gray-700 rounded px-2 py-1 disabled:opacity-50"
        title="Materialize project:* tags into albums"
      >
        {{ store.syncing ? 'Syncing…' : '↻ Sync from project tags' }}
      </button>
    </div>

    <div v-if="syncResult" class="text-xs text-gray-400 mb-4">
      Sync: created {{ syncResult.albums_created }}, updated {{ syncResult.albums_updated }},
      roles +{{ syncResult.roles_created }}, photos linked +{{ syncResult.photos_linked }}
    </div>

    <div v-if="store.loading" class="text-gray-400">Loading…</div>
    <div v-else-if="!store.albums.length" class="text-gray-500 italic">
      No albums yet. Tag some images with <code class="text-gray-400">project:&lt;slug&gt;</code>
      and click “Sync from project tags”, or create one via the API.
    </div>
    <div v-else class="space-y-1">
      <ProjectNode
        v-for="a in roots"
        :key="a.slug"
        :node="a"
        :children-by-parent="childrenByParent"
        :depth="0"
        base-path="/albums"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useAlbumsStore } from '../stores/albums'
import ProjectNode from '../components/ProjectNode.vue'
import type { AlbumInfo, AlbumSyncStats } from '../types/api'

const store = useAlbumsStore()
const syncResult = ref<AlbumSyncStats | null>(null)

onMounted(() => store.fetchAlbums())

const childrenByParent = computed<Record<string, AlbumInfo[]>>(() => {
  const map: Record<string, AlbumInfo[]> = {}
  for (const a of store.albums) {
    const key = a.parent_slug || ''
    if (!map[key]) map[key] = []
    map[key].push(a)
  }
  for (const arr of Object.values(map)) arr.sort((a, b) => a.slug.localeCompare(b.slug))
  return map
})

const roots = computed<AlbumInfo[]>(() => childrenByParent.value[''] || [])

async function onSync(): Promise<void> {
  syncResult.value = null
  try {
    syncResult.value = await store.sync()
  } catch (e) {
    console.error('sync failed', e)
  }
}
</script>
