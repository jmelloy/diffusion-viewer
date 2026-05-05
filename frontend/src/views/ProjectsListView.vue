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
    <div v-else class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
      <router-link
        v-for="p in store.projects"
        :key="p.slug"
        :to="`/projects/${p.slug}`"
        class="bg-gray-800 hover:bg-gray-700 rounded-xl p-5 transition-colors group"
      >
        <div class="text-2xl mb-2">📁</div>
        <h2 class="text-white font-semibold text-lg group-hover:text-purple-300 transition-colors capitalize">
          {{ p.name }}
        </h2>
        <p class="text-gray-400 text-sm mt-1">{{ p.image_count }} image{{ p.image_count !== 1 ? 's' : '' }}</p>
      </router-link>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useProjectsStore } from '../stores/projects.js'

const store = useProjectsStore()
onMounted(() => store.fetchProjects())
</script>
