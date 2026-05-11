<template>
  <div class="space-y-2">
    <div
      v-for="(row, i) in rows"
      :key="i"
      class="flex gap-2 items-center"
    >
      <input
        v-model="row.role"
        :list="`roles-${uid}`"
        placeholder="role (e.g. suspect)"
        class="flex-1 bg-gray-700 border border-gray-600 text-white rounded px-2 py-1 text-sm focus:outline-none focus:border-purple-500"
      />
      <input
        v-model="row.value"
        :list="`values-${uid}-${row.role || 'any'}`"
        placeholder="value (e.g. miss scarlett)"
        class="flex-1 bg-gray-700 border border-gray-600 text-white rounded px-2 py-1 text-sm focus:outline-none focus:border-purple-500"
      />
      <button
        @click="rows.splice(i, 1)"
        class="text-gray-400 hover:text-red-400 text-sm w-6 flex-shrink-0"
        title="Remove"
      >
        ×
      </button>
    </div>
    <button
      @click="rows.push({ role: '', value: '' })"
      class="text-xs text-purple-400 hover:text-purple-300"
    >
      + Add role
    </button>

    <!-- Datalists for autocomplete -->
    <datalist :id="`roles-${uid}`">
      <option v-for="r in availableRoles" :key="r" :value="r" />
    </datalist>
    <datalist
      v-for="(values, role) in projectShape"
      :key="role"
      :id="`values-${uid}-${role}`"
    >
      <option v-for="v in values" :key="v" :value="v" />
    </datalist>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import axios from 'axios'
import type { ProjectDetail } from '../types/api'

type RoleMap = Record<string, string[]>
interface Row {
  role: string
  value: string
}

const props = withDefaults(
  defineProps<{
    modelValue?: RoleMap
    projectSlug?: string
  }>(),
  {
    modelValue: () => ({}),
    projectSlug: '',
  },
)

const emit = defineEmits<{
  (e: 'update:modelValue', value: RoleMap): void
}>()

const uid = Math.random().toString(36).slice(2, 9)
const rows = ref<Row[]>([])
const projectShape = ref<Record<string, string[]>>({})

const availableRoles = computed<string[]>(() => Object.keys(projectShape.value))

function hydrate(value: RoleMap | undefined): void {
  rows.value = []
  for (const [role, values] of Object.entries(value || {})) {
    for (const v of values) rows.value.push({ role, value: v })
  }
  if (!rows.value.length) rows.value.push({ role: '', value: '' })
}
hydrate(props.modelValue)

watch(
  rows,
  (curr) => {
    const out: RoleMap = {}
    for (const { role, value } of curr) {
      const r = role.trim().toLowerCase()
      const v = value.trim().toLowerCase()
      if (!r || !v) continue
      if (!out[r]) out[r] = []
      if (!out[r].includes(v)) out[r].push(v)
    }
    emit('update:modelValue', out)
  },
  { deep: true },
)

async function loadShape(slug: string): Promise<void> {
  if (!slug) {
    projectShape.value = {}
    return
  }
  try {
    const res = await axios.get<ProjectDetail>(`/api/projects/${slug}`)
    const shape: Record<string, string[]> = {}
    for (const [role, values] of Object.entries(res.data.roles || {})) {
      if (!role) continue
      shape[role] = Object.keys(values).filter(Boolean)
    }
    projectShape.value = shape
  } catch {
    projectShape.value = {}
  }
}

watch(() => props.projectSlug, loadShape, { immediate: true })
</script>
