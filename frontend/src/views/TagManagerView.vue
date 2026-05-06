<template>
  <div class="p-6 max-w-5xl mx-auto text-gray-200">
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-2xl font-bold text-white">Tag Manager</h1>
      <button
        @click="recomputeParents"
        :disabled="recomputing"
        class="bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-sm px-3 py-1.5 rounded-lg transition-colors"
        title="Run curated + subsumption hierarchy rules"
      >
        {{ recomputing ? 'Recomputing…' : 'Recompute parents' }}
      </button>
    </div>

    <div v-if="message" class="mb-4 text-sm" :class="messageError ? 'text-red-400' : 'text-green-400'">
      {{ message }}
    </div>

    <div class="flex flex-col sm:flex-row gap-3 mb-4">
      <input
        v-model="filterQuery"
        type="text"
        placeholder="Search tags by name…"
        class="flex-1 bg-gray-700 border border-gray-600 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
      />
      <select
        v-model="sortKey"
        class="bg-gray-700 border border-gray-600 text-white rounded-lg px-3 py-2 text-sm"
      >
        <option value="name">Sort: name</option>
        <option value="count_desc">Sort: most images</option>
        <option value="count_asc">Sort: fewest images</option>
        <option value="parent">Sort: parent</option>
      </select>
    </div>

    <div class="text-xs text-gray-500 mb-2">
      {{ filteredTags.length }} of {{ store.allTags.length }} tags
    </div>

    <div class="overflow-x-auto border border-gray-700 rounded-lg">
      <table class="w-full text-sm">
        <thead class="bg-gray-800 text-gray-400 uppercase text-xs">
          <tr>
            <th class="px-3 py-2 text-left">Tag</th>
            <th class="px-3 py-2 text-left">Parent</th>
            <th class="px-3 py-2 text-right">Images</th>
            <th class="px-3 py-2 text-left">Set parent</th>
            <th class="px-3 py-2 text-left">Merge into</th>
            <th class="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!filteredTags.length">
            <td colspan="6" class="px-3 py-6 text-center text-gray-500 italic">
              No matching tags
            </td>
          </tr>
          <tr
            v-for="tag in filteredTags"
            :key="tag.id"
            class="border-t border-gray-700 hover:bg-gray-800/40"
          >
            <td class="px-3 py-2">
              <div class="font-medium text-white">{{ tag.name }}</div>
              <div v-if="tag.path && tag.path !== tag.name" class="text-xs text-gray-500">
                {{ tag.path }}
              </div>
            </td>
            <td class="px-3 py-2 text-gray-400">
              {{ tag.parent_name || '—' }}
            </td>
            <td class="px-3 py-2 text-right text-gray-300">
              {{ tag.image_count }}
            </td>

            <!-- Set parent -->
            <td class="px-3 py-2">
              <select
                :value="tag.parent_tag_id ?? ''"
                @change="onParentChange(tag, $event)"
                :disabled="busyId === tag.id"
                class="bg-gray-700 border border-gray-600 text-white rounded px-2 py-1 text-xs max-w-[14rem]"
              >
                <option value="">— none —</option>
                <option
                  v-for="opt in parentOptionsFor(tag)"
                  :key="opt.id"
                  :value="opt.id"
                >
                  {{ opt.name }}
                </option>
              </select>
            </td>

            <!-- Merge target -->
            <td class="px-3 py-2">
              <div class="flex items-center gap-1">
                <select
                  v-model="mergeTargets[tag.id]"
                  :disabled="busyId === tag.id"
                  class="bg-gray-700 border border-gray-600 text-white rounded px-2 py-1 text-xs max-w-[12rem]"
                >
                  <option value="">— pick target —</option>
                  <option
                    v-for="opt in mergeOptionsFor(tag)"
                    :key="opt.id"
                    :value="opt.id"
                  >
                    {{ opt.name }}
                  </option>
                </select>
                <button
                  @click="mergeTag(tag)"
                  :disabled="!mergeTargets[tag.id] || busyId === tag.id"
                  class="bg-indigo-700 hover:bg-indigo-600 disabled:opacity-40 text-white px-2 py-1 rounded text-xs"
                >
                  Merge
                </button>
              </div>
            </td>

            <!-- Delete -->
            <td class="px-3 py-2 text-right">
              <button
                @click="deleteTag(tag)"
                :disabled="busyId === tag.id"
                class="bg-red-700 hover:bg-red-600 disabled:opacity-40 text-white px-2 py-1 rounded text-xs"
              >
                Delete
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import axios from 'axios'
import { useImagesStore } from '../stores/images.js'

const store = useImagesStore()

const filterQuery = ref('')
const sortKey = ref('count_desc')
const busyId = ref(null)
const message = ref('')
const messageError = ref(false)
const recomputing = ref(false)
const mergeTargets = reactive({})

onMounted(() => {
  if (!store.allTags.length) store.fetchAllTags()
})

function setMessage(text, isError = false) {
  message.value = text
  messageError.value = isError
  if (text) setTimeout(() => { if (message.value === text) message.value = '' }, 4000)
}

const tagsById = computed(() => {
  const m = new Map()
  for (const t of store.allTags) m.set(t.id, t)
  return m
})

// Returns the set of descendant tag ids (including the tag itself), used to
// prevent cycles when picking a parent or merge target.
function descendantIds(tagId) {
  const result = new Set([tagId])
  const stack = [tagId]
  while (stack.length) {
    const id = stack.pop()
    for (const t of store.allTags) {
      if (t.parent_tag_id === id && !result.has(t.id)) {
        result.add(t.id)
        stack.push(t.id)
      }
    }
  }
  return result
}

const filteredTags = computed(() => {
  const q = filterQuery.value.trim().toLowerCase()
  let list = store.allTags
  if (q) list = list.filter((t) => t.name.toLowerCase().includes(q))
  const sorted = [...list]
  if (sortKey.value === 'name') {
    sorted.sort((a, b) => a.name.localeCompare(b.name))
  } else if (sortKey.value === 'count_asc') {
    sorted.sort((a, b) => (a.image_count || 0) - (b.image_count || 0))
  } else if (sortKey.value === 'parent') {
    sorted.sort((a, b) => {
      const ap = a.parent_name || ''
      const bp = b.parent_name || ''
      return ap.localeCompare(bp) || a.name.localeCompare(b.name)
    })
  } else {
    sorted.sort((a, b) => (b.image_count || 0) - (a.image_count || 0))
  }
  return sorted
})

function parentOptionsFor(tag) {
  const blocked = descendantIds(tag.id)
  return store.allTags
    .filter((t) => !blocked.has(t.id))
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name))
}

function mergeOptionsFor(tag) {
  return store.allTags
    .filter((t) => t.id !== tag.id)
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name))
}

async function onParentChange(tag, event) {
  const raw = event.target.value
  const newParent = raw === '' ? null : Number(raw)
  if (newParent === (tag.parent_tag_id ?? null)) return
  busyId.value = tag.id
  try {
    await axios.put(`/api/tags/${tag.id}/parent`, { parent_tag_id: newParent })
    await store.fetchAllTags()
    setMessage(`Updated parent for "${tag.name}"`)
  } catch (e) {
    setMessage(e.response?.data?.detail || e.message, true)
  } finally {
    busyId.value = null
  }
}

async function deleteTag(tag) {
  const n = tag.image_count || 0
  const msg = n
    ? `Delete tag "${tag.name}"? It will be removed from ${n} image${n !== 1 ? 's' : ''}.`
    : `Delete tag "${tag.name}"?`
  if (!confirm(msg)) return
  busyId.value = tag.id
  try {
    await axios.delete(`/api/tags/${tag.id}`)
    await store.fetchAllTags()
    setMessage(`Deleted "${tag.name}"`)
  } catch (e) {
    setMessage(e.response?.data?.detail || e.message, true)
  } finally {
    busyId.value = null
  }
}

async function mergeTag(tag) {
  const targetId = Number(mergeTargets[tag.id])
  if (!targetId) return
  const target = tagsById.value.get(targetId)
  if (!target) return
  if (!confirm(`Merge "${tag.name}" into "${target.name}"? "${tag.name}" will be deleted and its images + children moved to "${target.name}".`)) return
  busyId.value = tag.id
  try {
    await axios.post('/api/tags/merge', {
      source_tag_id: tag.id,
      target_tag_id: targetId,
    })
    delete mergeTargets[tag.id]
    await store.fetchAllTags()
    setMessage(`Merged "${tag.name}" into "${target.name}"`)
  } catch (e) {
    setMessage(e.response?.data?.detail || e.message, true)
  } finally {
    busyId.value = null
  }
}

async function recomputeParents() {
  recomputing.value = true
  try {
    const res = await axios.post('/api/tags/recompute-parents')
    await store.fetchAllTags()
    const stats = res.data
    setMessage(
      `Recomputed: ${stats.curated_children_parented ?? 0} curated, ${stats.subsumption_parented ?? 0} via subsumption`
    )
  } catch (e) {
    setMessage(e.response?.data?.detail || e.message, true)
  } finally {
    recomputing.value = false
  }
}
</script>
