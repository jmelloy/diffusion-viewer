<template>
  <div>
    <router-link
      :to="`/projects/${node.slug}`"
      :style="{ paddingLeft: `${12 + depth * 20}px` }"
      class="flex items-center gap-3 py-2 pr-3 rounded hover:bg-gray-800 transition-colors"
    >
      <span class="text-base">{{ kids.length ? '📂' : '📁' }}</span>
      <span class="flex-1 text-white hover:text-purple-300 capitalize font-medium">
        {{ node.name }}
      </span>
      <span class="text-gray-400 text-sm">
        {{ node.image_count }} image{{ node.image_count !== 1 ? 's' : '' }}
      </span>
    </router-link>
    <ProjectNode
      v-for="k in kids"
      :key="k.slug"
      :node="k"
      :children-by-parent="childrenByParent"
      :depth="depth + 1"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  node: { type: Object, required: true },
  childrenByParent: { type: Object, required: true },
  depth: { type: Number, default: 0 },
})

const kids = computed(() => props.childrenByParent[props.node.slug] || [])
</script>
