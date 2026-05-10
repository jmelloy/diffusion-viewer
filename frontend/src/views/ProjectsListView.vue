<template>
  <div class="min-h-screen bg-gray-900 p-6">
    <div class="flex items-center gap-4 mb-6">
      <router-link to="/" class="text-gray-400 hover:text-white transition-colors">← Gallery</router-link>
      <h1 class="text-2xl font-bold text-white">Projects</h1>
    </div>

    <div v-if="store.loading" class="text-gray-400">Loading…</div>
    <div v-else-if="!store.projects.length" class="text-gray-500 italic">
      No projects yet. Assign images to a project from the image detail view or use bulk actions.
    </div>
    <div v-else class="space-y-1">
      <ProjectNode
        v-for="p in roots"
        :key="p.slug"
        :node="p"
        :children-by-parent="childrenByParent"
        :depth="0"
      />
    </div>
  </div>
</template>

<script setup>
import { onMounted, computed } from 'vue'
import { useProjectsStore } from '../stores/projects'
import ProjectNode from '../components/ProjectNode.vue'

const store = useProjectsStore()
onMounted(() => store.fetchProjects())

const childrenByParent = computed(() => {
  const map = {}
  for (const p of store.projects) {
    const key = p.parent_slug || ''
    if (!map[key]) map[key] = []
    map[key].push(p)
  }
  for (const arr of Object.values(map)) arr.sort((a, b) => a.slug.localeCompare(b.slug))
  return map
})

const roots = computed(() => childrenByParent.value[''] || [])
</script>
