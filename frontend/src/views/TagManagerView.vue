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

    <div class="text-xs text-gray-500 mb-2 flex items-center gap-3">
      <span>{{ filteredTags.length }} of {{ store.allTags.length }} tags</span>
      <span v-if="selectedIds.size">· {{ selectedIds.size }} selected</span>
    </div>

    <!-- Bulk action bar -->
    <div
      v-if="selectedIds.size"
      class="sticky top-0 z-10 mb-3 bg-gray-800 border border-gray-700 rounded-lg p-3 flex flex-wrap items-center gap-3 shadow-lg"
    >
      <span class="text-sm text-white font-medium">{{ selectedIds.size }} selected</span>

      <div class="flex items-center gap-1">
        <select
          v-model="bulkParentId"
          :disabled="bulkBusy"
          class="bg-gray-700 border border-gray-600 text-white rounded px-2 py-1 text-xs"
        >
          <option value="">Set parent: — none —</option>
          <option
            v-for="opt in bulkParentOptions"
            :key="opt.id"
            :value="opt.id"
          >
            {{ opt.name }}
          </option>
        </select>
        <button
          @click="bulkSetParent"
          :disabled="bulkBusy"
          class="bg-blue-700 hover:bg-blue-600 disabled:opacity-40 text-white px-2 py-1 rounded text-xs"
        >
          Apply parent
        </button>
      </div>

      <div class="flex items-center gap-1">
        <select
          v-model="bulkMergeTargetId"
          :disabled="bulkBusy"
          class="bg-gray-700 border border-gray-600 text-white rounded px-2 py-1 text-xs"
        >
          <option value="">Merge into…</option>
          <option
            v-for="opt in bulkMergeTargetOptions"
            :key="opt.id"
            :value="opt.id"
          >
            {{ opt.name }}
          </option>
        </select>
        <button
          @click="bulkMerge"
          :disabled="!bulkMergeTargetId || bulkBusy"
          class="bg-indigo-700 hover:bg-indigo-600 disabled:opacity-40 text-white px-2 py-1 rounded text-xs"
        >
          Merge selected
        </button>
      </div>

      <button
        @click="bulkDelete"
        :disabled="bulkBusy"
        class="bg-red-700 hover:bg-red-600 disabled:opacity-40 text-white px-2 py-1 rounded text-xs"
      >
        Delete selected
      </button>

      <button
        @click="clearSelection"
        :disabled="bulkBusy"
        class="ml-auto text-gray-300 hover:text-white text-xs underline"
      >
        Clear
      </button>
    </div>

    <div class="overflow-x-auto border border-gray-700 rounded-lg">
      <table class="w-full text-sm">
        <thead class="bg-gray-800 text-gray-400 uppercase text-xs">
          <tr>
            <th class="px-3 py-2 w-8">
              <input
                type="checkbox"
                :checked="allVisibleSelected"
                :indeterminate.prop="someVisibleSelected"
                @change="toggleSelectAllVisible"
                aria-label="Select all visible tags"
              />
            </th>
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
            <td colspan="7" class="px-3 py-6 text-center text-gray-500 italic">
              No matching tags
            </td>
          </tr>
          <tr
            v-for="tag in filteredTags"
            :key="tag.id"
            class="border-t border-gray-700 hover:bg-gray-800/40"
            :class="{ 'bg-gray-800/60': selectedIds.has(tag.id) }"
          >
            <td class="px-3 py-2">
              <input
                type="checkbox"
                :checked="selectedIds.has(tag.id)"
                @change="toggleSelect(tag.id)"
                :aria-label="`Select ${tag.name}`"
              />
            </td>
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

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import axios, { AxiosError } from 'axios'
import { useImagesStore } from '../stores/images'
import type { Tag } from '../types/api'

type SortKey = 'count_desc' | 'count_asc' | 'name' | 'parent'

const store = useImagesStore()

const filterQuery = ref('')
const sortKey = ref<SortKey>('count_desc')
const busyId = ref<number | null>(null)
const message = ref('')
const messageError = ref(false)
const recomputing = ref(false)
const mergeTargets = reactive<Record<number, number | string>>({})

const selectedIds = ref<Set<number>>(new Set())
const bulkBusy = ref(false)
const bulkParentId = ref<string>('')
const bulkMergeTargetId = ref<string>('')

function errMessage(e: unknown): string {
  if (axios.isAxiosError(e)) {
    const detail = (e as AxiosError<{ detail?: string }>).response?.data?.detail
    if (detail) return detail
  }
  return (e as Error)?.message ?? 'Unknown error'
}

onMounted(() => {
  if (!store.allTags.length) store.fetchAllTags()
})

function setMessage(text: string, isError = false): void {
  message.value = text
  messageError.value = isError
  if (text) {
    setTimeout(() => {
      if (message.value === text) message.value = ''
    }, 4000)
  }
}

const tagsById = computed<Map<number, Tag>>(() => {
  const m = new Map<number, Tag>()
  for (const t of store.allTags) m.set(t.id, t)
  return m
})

function descendantIds(tagId: number): Set<number> {
  const result = new Set<number>([tagId])
  const stack: number[] = [tagId]
  while (stack.length) {
    const id = stack.pop() as number
    for (const t of store.allTags) {
      if (t.parent_tag_id === id && !result.has(t.id)) {
        result.add(t.id)
        stack.push(t.id)
      }
    }
  }
  return result
}

const filteredTags = computed<Tag[]>(() => {
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

const allVisibleSelected = computed(() => {
  return filteredTags.value.length > 0 &&
    filteredTags.value.every((t) => selectedIds.value.has(t.id))
})

const someVisibleSelected = computed(() => {
  const sel = filteredTags.value.filter((t) => selectedIds.value.has(t.id)).length
  return sel > 0 && sel < filteredTags.value.length
})

function toggleSelect(id: number): void {
  const next = new Set(selectedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedIds.value = next
}

function toggleSelectAllVisible(): void {
  const next = new Set(selectedIds.value)
  if (allVisibleSelected.value) {
    for (const t of filteredTags.value) next.delete(t.id)
  } else {
    for (const t of filteredTags.value) next.add(t.id)
  }
  selectedIds.value = next
}

function clearSelection(): void {
  selectedIds.value = new Set()
  bulkParentId.value = ''
  bulkMergeTargetId.value = ''
}

const bulkParentOptions = computed<Tag[]>(() => {
  const blocked = new Set<number>()
  for (const id of selectedIds.value) {
    for (const d of descendantIds(id)) blocked.add(d)
  }
  return store.allTags
    .filter((t) => !blocked.has(t.id))
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name))
})

const bulkMergeTargetOptions = computed<Tag[]>(() => {
  return store.allTags
    .filter((t) => !selectedIds.value.has(t.id))
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name))
})

function parentOptionsFor(tag: Tag): Tag[] {
  const blocked = descendantIds(tag.id)
  return store.allTags
    .filter((t) => !blocked.has(t.id))
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name))
}

function mergeOptionsFor(tag: Tag): Tag[] {
  return store.allTags
    .filter((t) => t.id !== tag.id)
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name))
}

async function onParentChange(tag: Tag, event: Event): Promise<void> {
  const raw = (event.target as HTMLSelectElement).value
  const newParent = raw === '' ? null : Number(raw)
  if (newParent === (tag.parent_tag_id ?? null)) return
  busyId.value = tag.id
  try {
    await axios.put(`/api/tags/${tag.id}/parent`, { parent_tag_id: newParent })
    await store.fetchAllTags()
    setMessage(`Updated parent for "${tag.name}"`)
  } catch (e) {
    setMessage(errMessage(e), true)
  } finally {
    busyId.value = null
  }
}

async function deleteTag(tag: Tag): Promise<void> {
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
    setMessage(errMessage(e), true)
  } finally {
    busyId.value = null
  }
}

async function mergeTag(tag: Tag): Promise<void> {
  const targetId = Number(mergeTargets[tag.id])
  if (!targetId) return
  const target = tagsById.value.get(targetId)
  if (!target) return
  if (
    !confirm(
      `Merge "${tag.name}" into "${target.name}"? "${tag.name}" will be deleted and its images + children moved to "${target.name}".`,
    )
  ) {
    return
  }
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
    setMessage(errMessage(e), true)
  } finally {
    busyId.value = null
  }
}

async function bulkDelete(): Promise<void> {
  const ids = [...selectedIds.value]
  if (!ids.length) return
  const totalImages = ids.reduce(
    (n, id) => n + (tagsById.value.get(id)?.image_count || 0),
    0,
  )
  const msg = totalImages
    ? `Delete ${ids.length} tag${ids.length !== 1 ? 's' : ''}? They will be removed from ${totalImages} image association${totalImages !== 1 ? 's' : ''}.`
    : `Delete ${ids.length} tag${ids.length !== 1 ? 's' : ''}?`
  if (!confirm(msg)) return
  bulkBusy.value = true
  try {
    const res = await axios.post<{ deleted: number }>('/api/tags/bulk-delete', {
      tag_ids: ids,
    })
    await store.fetchAllTags()
    clearSelection()
    setMessage(`Deleted ${res.data.deleted} tag${res.data.deleted !== 1 ? 's' : ''}`)
  } catch (e) {
    setMessage(errMessage(e), true)
  } finally {
    bulkBusy.value = false
  }
}

async function bulkSetParent(): Promise<void> {
  const ids = [...selectedIds.value]
  if (!ids.length) return
  const raw = bulkParentId.value
  const parentId = raw === '' ? null : Number(raw)
  const parentName =
    parentId === null
      ? '— none —'
      : (tagsById.value.get(parentId)?.name ?? `#${parentId}`)
  if (!confirm(`Set parent of ${ids.length} tag${ids.length !== 1 ? 's' : ''} to "${parentName}"?`)) {
    return
  }
  bulkBusy.value = true
  try {
    const res = await axios.post<{ updated: number }>('/api/tags/bulk-parent', {
      tag_ids: ids,
      parent_tag_id: parentId,
    })
    await store.fetchAllTags()
    setMessage(`Updated parent on ${res.data.updated} tag${res.data.updated !== 1 ? 's' : ''}`)
  } catch (e) {
    setMessage(errMessage(e), true)
  } finally {
    bulkBusy.value = false
  }
}

async function bulkMerge(): Promise<void> {
  const ids = [...selectedIds.value]
  const targetId = Number(bulkMergeTargetId.value)
  if (!ids.length || !targetId) return
  const target = tagsById.value.get(targetId)
  if (!target) return
  if (
    !confirm(
      `Merge ${ids.length} tag${ids.length !== 1 ? 's' : ''} into "${target.name}"? Selected tags will be deleted and their images + children moved to "${target.name}".`,
    )
  ) {
    return
  }
  bulkBusy.value = true
  try {
    const res = await axios.post<{ merged: number }>('/api/tags/bulk-merge', {
      source_tag_ids: ids,
      target_tag_id: targetId,
    })
    await store.fetchAllTags()
    clearSelection()
    setMessage(
      `Merged ${res.data.merged} tag${res.data.merged !== 1 ? 's' : ''} into "${target.name}"`,
    )
  } catch (e) {
    setMessage(errMessage(e), true)
  } finally {
    bulkBusy.value = false
  }
}

async function recomputeParents(): Promise<void> {
  recomputing.value = true
  try {
    const res = await axios.post<{
      curated_children_parented?: number
      subsumption_parented?: number
    }>('/api/tags/recompute-parents')
    await store.fetchAllTags()
    const stats = res.data
    setMessage(
      `Recomputed: ${stats.curated_children_parented ?? 0} curated, ${stats.subsumption_parented ?? 0} via subsumption`,
    )
  } catch (e) {
    setMessage(errMessage(e), true)
  } finally {
    recomputing.value = false
  }
}
</script>
