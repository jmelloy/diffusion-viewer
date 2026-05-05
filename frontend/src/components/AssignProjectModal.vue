<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60" @click.self="$emit('close')">
    <div class="bg-gray-800 rounded-xl shadow-2xl w-full max-w-md p-6 mx-4">
      <h2 class="text-lg font-semibold text-white mb-4">Assign to Project</h2>

      <!-- Project name input with autocomplete -->
      <div class="mb-4 relative">
        <label class="block text-xs text-gray-400 mb-1">Project Name</label>
        <input
          v-model="projectInput"
          @input="onProjectInput"
          @keydown.down.prevent="moveSuggestion(1)"
          @keydown.up.prevent="moveSuggestion(-1)"
          @keydown.enter.prevent="selectSuggestion()"
          @keydown.escape="showSuggestions = false"
          placeholder="e.g. my-film, concept-art…"
          class="w-full bg-gray-700 border border-gray-600 text-white rounded px-3 py-2 text-sm focus:outline-none focus:border-purple-500"
          autocomplete="off"
        />
        <ul
          v-if="showSuggestions && filteredSuggestions.length"
          class="absolute z-10 left-0 right-0 bg-gray-700 border border-gray-600 rounded mt-1 max-h-40 overflow-y-auto shadow-lg"
        >
          <li
            v-for="(s, i) in filteredSuggestions"
            :key="s.slug"
            @click="selectSuggestion(s)"
            :class="[
              'px-3 py-2 text-sm cursor-pointer',
              i === activeSuggestion ? 'bg-purple-600 text-white' : 'text-gray-200 hover:bg-gray-600',
            ]"
          >
            {{ s.name }} <span class="text-gray-400 text-xs">({{ s.image_count }})</span>
          </li>
        </ul>
      </div>

      <!-- Role checkboxes -->
      <div class="mb-5">
        <label class="block text-xs text-gray-400 mb-2">Role(s)</label>
        <div class="grid grid-cols-2 gap-2">
          <label
            v-for="role in ROLES"
            :key="role.value"
            class="flex items-center gap-2 cursor-pointer"
          >
            <input
              type="checkbox"
              :value="role.value"
              v-model="selectedRoles"
              class="rounded accent-purple-500"
            />
            <span class="text-sm text-gray-200 flex items-center gap-1.5">
              <span :class="['inline-block w-2 h-2 rounded-full', role.dot]"></span>
              {{ role.label }}
            </span>
          </label>
        </div>
      </div>

      <!-- Current project assignments (for removal) -->
      <div v-if="currentProjects.length" class="mb-4">
        <label class="block text-xs text-gray-400 mb-2">Current Assignments</label>
        <div class="flex flex-wrap gap-1">
          <button
            v-for="p in currentProjects"
            :key="p"
            @click="removeFromProject(p)"
            class="bg-gray-700 hover:bg-red-800 text-gray-300 hover:text-white text-xs px-2 py-0.5 rounded transition-colors"
            title="Click to remove"
          >
            {{ p }} ×
          </button>
        </div>
      </div>

      <!-- Actions -->
      <div class="flex gap-2 justify-end">
        <button
          @click="$emit('close')"
          class="px-4 py-2 text-sm bg-gray-700 hover:bg-gray-600 text-white rounded transition-colors"
        >
          Cancel
        </button>
        <button
          @click="assign"
          :disabled="!projectInput.trim() || saving"
          class="px-4 py-2 text-sm bg-purple-600 hover:bg-purple-700 disabled:opacity-40 text-white rounded transition-colors"
        >
          {{ saving ? 'Saving…' : 'Assign' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useProjectsStore } from '../stores/projects.js'

const props = defineProps({
  imageId: { type: Number, required: true },
  imageTags: { type: Array, default: () => [] },
})

const emit = defineEmits(['close', 'assigned'])

const projectsStore = useProjectsStore()
const projectInput = ref('')
const selectedRoles = ref([])
const saving = ref(false)
const showSuggestions = ref(false)
const activeSuggestion = ref(-1)

const ROLES = [
  { value: 'character', label: 'Character', dot: 'bg-blue-400' },
  { value: 'scene', label: 'Scene', dot: 'bg-green-400' },
  { value: 'background', label: 'Background', dot: 'bg-yellow-400' },
  { value: 'prop', label: 'Prop', dot: 'bg-orange-400' },
  { value: 'concept', label: 'Concept', dot: 'bg-pink-400' },
  { value: 'reference', label: 'Reference', dot: 'bg-purple-400' },
  { value: 'other', label: 'Other', dot: 'bg-gray-400' },
]

onMounted(() => {
  projectsStore.fetchProjects()
})

const currentProjects = computed(() => {
  const slugs = new Set()
  for (const tag of props.imageTags) {
    const parts = tag.name.split(':')
    if (parts.length >= 2 && parts[0] === 'project') {
      slugs.add(parts[1])
    }
  }
  return [...slugs]
})

const filteredSuggestions = computed(() => {
  if (!projectInput.value.trim()) return projectsStore.projects
  const q = projectInput.value.toLowerCase()
  return projectsStore.projects.filter(
    (p) => p.slug.includes(q) || p.name.toLowerCase().includes(q)
  )
})

function onProjectInput() {
  showSuggestions.value = true
  activeSuggestion.value = -1
}

function moveSuggestion(dir) {
  const len = filteredSuggestions.value.length
  if (!len) return
  activeSuggestion.value = (activeSuggestion.value + dir + len) % len
}

function selectSuggestion(s) {
  if (s) {
    projectInput.value = s.slug
  } else if (activeSuggestion.value >= 0) {
    projectInput.value = filteredSuggestions.value[activeSuggestion.value]?.slug || projectInput.value
  }
  showSuggestions.value = false
  activeSuggestion.value = -1
}

async function assign() {
  const name = projectInput.value.trim()
  if (!name) return
  saving.value = true
  try {
    const updated = await projectsStore.assignProject(props.imageId, name, selectedRoles.value)
    emit('assigned', updated)
    emit('close')
  } catch (e) {
    console.error('assign failed', e)
  } finally {
    saving.value = false
  }
}

async function removeFromProject(slug) {
  if (!confirm(`Remove image from project "${slug}"?`)) return
  await projectsStore.removeProject(props.imageId, slug)
  emit('assigned')
}
</script>
