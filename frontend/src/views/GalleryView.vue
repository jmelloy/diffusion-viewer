<template>
  <div class="flex h-[calc(100vh-57px)]">
    <!-- Left sidebar: filters (rating, dates, sort) -->
    <aside class="w-64 bg-gray-800 border-r border-gray-700 overflow-y-auto p-4 flex-shrink-0">
      <h2 class="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">Filters</h2>

      <!-- Rating filter -->
      <div class="mb-4">
        <label class="block text-xs text-gray-400 mb-1">Min Rating</label>
        <select
          v-model.number="store.minRating"
          @change="store.fetchImages(true)"
          class="w-full bg-gray-700 border border-gray-600 text-white rounded px-2 py-1 text-sm"
        >
          <option :value="-999">All (including unrated)</option>
          <option :value="0">Unrated &amp; above</option>
          <option :value="1">Thumbs up &amp; above</option>
          <option :value="2">★★+</option>
          <option :value="3">★★★+</option>
          <option :value="4">★★★★+</option>
          <option :value="5">★★★★★</option>
        </select>
      </div>

      <!-- Show hidden toggle -->
      <div class="mb-4 flex items-center gap-2">
        <input
          id="show-hidden"
          type="checkbox"
          v-model="store.showHidden"
          @change="store.fetchImages(true)"
          class="rounded"
        />
        <label for="show-hidden" class="text-sm text-gray-300">Show thumbs-down</label>
      </div>

      <!-- Date browser tree -->
      <div class="mb-4">
        <div class="flex items-center justify-between mb-2">
          <label class="block text-xs text-gray-400 uppercase tracking-wider">Browse by Date</label>
          <button
            v-if="selectedDay || selectedMonth"
            @click="clearDateFilter"
            class="text-xs text-purple-400 hover:text-purple-300"
          >
            Clear
          </button>
        </div>
        <div v-if="!store.availableDates.length" class="text-xs text-gray-500 italic">
          No dates available
        </div>
        <div v-else class="text-sm select-none">
          <div v-for="{ year, months } in dateTree" :key="year" class="mb-0.5">
            <!-- Year row -->
            <button
              @click="toggleYear(year)"
              class="flex items-center gap-1 w-full text-left text-gray-300 hover:text-white py-0.5 rounded hover:bg-gray-700 px-1"
            >
              <span class="text-gray-500 text-xs w-3 flex-shrink-0">{{ expandedYears.has(year) ? '▾' : '▸' }}</span>
              <span class="font-medium">{{ year }}</span>
            </button>
            <!-- Months -->
            <div v-if="expandedYears.has(year)" class="ml-3">
              <div v-for="{ month, days } in months" :key="month" class="mb-0.5">
                <!-- Month row: chevron toggles expand; rest selects the month range -->
                <div
                  :class="[
                    'flex items-center gap-1 w-full rounded px-1',
                    selectedMonth === `${year}-${month}`
                      ? 'bg-purple-700 text-white'
                      : 'text-gray-400 hover:bg-gray-700 hover:text-gray-200',
                  ]"
                >
                  <button
                    @click="toggleMonth(`${year}-${month}`)"
                    class="text-xs w-3 flex-shrink-0 text-gray-500 hover:text-gray-300 py-0.5"
                    :aria-label="expandedMonths.has(`${year}-${month}`) ? 'Collapse month' : 'Expand month'"
                  >{{ expandedMonths.has(`${year}-${month}`) ? '▾' : '▸' }}</button>
                  <button
                    @click="selectMonth(year, month)"
                    class="flex items-center gap-1 flex-1 text-left py-0.5"
                  >
                    <span>{{ monthName(month) }}</span>
                    <span :class="['ml-auto text-xs', selectedMonth === `${year}-${month}` ? 'text-purple-200' : 'text-gray-600']">{{ days.reduce((s, d) => s + d.count, 0) }}</span>
                  </button>
                </div>
                <!-- Days -->
                <div v-if="expandedMonths.has(`${year}-${month}`)" class="ml-3">
                  <button
                    v-for="d in days"
                    :key="d.date"
                    @click="selectDay(d.date)"
                    :class="[
                      'flex items-center justify-between w-full text-left px-1 py-0.5 rounded text-xs transition-colors',
                      selectedDay === d.date
                        ? 'bg-purple-700 text-white'
                        : 'text-gray-400 hover:bg-gray-700 hover:text-gray-200',
                    ]"
                  >
                    <span>{{ d.day }}</span>
                    <span :class="selectedDay === d.date ? 'text-purple-300' : 'text-gray-600'">{{ d.count }}</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Sort -->
      <div class="mb-4">
        <label class="block text-xs text-gray-400 mb-1">Sort By</label>
        <select
          v-model="store.sortBy"
          @change="store.fetchImages(true)"
          class="w-full bg-gray-700 border border-gray-600 text-white rounded px-2 py-1 text-sm mb-1"
        >
          <option value="date_taken">Date Taken</option>
          <option value="created_at">Date Added</option>
          <option value="rating">Rating</option>
          <option value="filename">Filename</option>
        </select>
        <select
          v-model="store.sortDir"
          @change="store.fetchImages(true)"
          class="w-full bg-gray-700 border border-gray-600 text-white rounded px-2 py-1 text-sm"
        >
          <option value="desc">Newest First</option>
          <option value="asc">Oldest First</option>
        </select>
      </div>

    </aside>

    <!-- Bulk assign-to-project modal -->
    <BulkProjectModal
      v-if="showBulkProjectModal"
      :image-ids="store.selectedImageIds"
      @close="showBulkProjectModal = false"
      @assigned="onBulkAssigned"
    />

    <!-- Gallery -->
    <main class="flex-1 overflow-y-auto p-4" ref="galleryEl">
      <!-- Loading / empty states -->
      <div v-if="store.loading && !store.images.length" class="flex items-center justify-center h-64">
        <div class="text-gray-400 text-lg">Loading…</div>
      </div>
      <div v-else-if="!store.images.length" class="flex flex-col items-center justify-center h-64 gap-4">
        <div class="text-6xl">🖼️</div>
        <p class="text-gray-400 text-lg">No images found.</p>
        <p class="text-gray-500 text-sm">Use "Scan Directory" to add images.</p>
      </div>

      <!-- Continuous grid with inline date headers -->
      <template v-else>
        <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 items-end">
          <div v-for="entry in imagesWithDateLabels" :key="entry.img.id" class="flex flex-col">
            <h3
              v-if="entry.dateLabel"
              class="text-xs font-semibold text-gray-400 mb-1 uppercase tracking-wider truncate"
              :title="entry.dateLabel"
            >
              {{ entry.dateLabel }}
            </h3>
            <ImageCard
              :image="entry.img"
              :selected="store.selectedImageIds.includes(entry.img.id)"
              @toggle-select="store.toggleImageSelection(entry.img.id)"
              @rate="(r) => store.rateImage(entry.img.id, r)"
            />
          </div>
        </div>

        <!-- Infinite-scroll sentinel + status -->
        <div ref="sentinelEl" aria-hidden="true" class="h-1"></div>
        <div class="flex justify-center mt-6 pb-8">
          <p v-if="store.loading" class="text-gray-500 text-sm">Loading more…</p>
          <p v-else-if="store.page >= store.pages" class="text-gray-500 text-sm">
            All {{ store.total }} images loaded
          </p>
        </div>
      </template>
    </main>

    <!-- Right sidebar: projects, tags, bulk actions -->
    <aside class="w-72 bg-gray-800 border-l border-gray-700 overflow-y-auto p-4 flex-shrink-0">
      <!-- Projects -->
      <div class="mb-4">
        <div class="flex items-center justify-between mb-2">
          <label class="block text-xs text-gray-400 uppercase tracking-wider">Projects</label>
          <div class="flex items-center gap-2">
            <button
              v-if="selectedProjectSlugs.length"
              @click="clearProjectFilters"
              class="text-xs text-purple-400 hover:text-purple-300"
            >
              Clear
            </button>
            <router-link to="/projects" class="text-xs text-purple-400 hover:text-purple-300">Manage</router-link>
          </div>
        </div>
        <div v-if="projectsStore.loading" class="text-xs text-gray-500 italic">Loading…</div>
        <div v-else-if="!projectsStore.projects.length" class="text-xs text-gray-500 italic">No projects yet</div>
        <div v-else class="text-sm select-none">
          <div
            v-for="entry in projectTreeFlat"
            :key="entry.key"
            :class="[
              'flex items-center gap-1 rounded px-1',
              entry.kind !== 'role' && isTagSelected(entry.tagName)
                ? 'bg-purple-700 text-white'
                : entry.kind === 'role'
                  ? 'text-gray-500'
                  : 'text-gray-300 hover:bg-gray-700 hover:text-white',
            ]"
            :style="{ paddingLeft: (entry.depth * 12 + 4) + 'px' }"
          >
            <button
              v-if="entry.hasChildren"
              @click="toggleProjectExpand(entry.key)"
              class="text-xs w-3 flex-shrink-0 text-gray-500 hover:text-gray-300 py-0.5"
              :aria-label="expandedProjects.has(entry.key) ? 'Collapse' : 'Expand'"
            >{{ entry.expanded ? '▾' : '▸' }}</button>
            <span v-else class="text-xs w-3 flex-shrink-0 text-gray-700">·</span>
            <!-- Role groups are headers, not tag filters (no real tag exists for "project:slug:role"). -->
            <div
              v-if="entry.kind === 'role'"
              class="flex items-center gap-1 flex-1 py-0.5 text-xs uppercase tracking-wider truncate"
            >
              <span class="truncate">{{ entry.label }}</span>
              <span class="ml-auto text-gray-600">{{ entry.count }}</span>
            </div>
            <button
              v-else
              @click="toggleTagFilter(entry.tagName)"
              class="flex items-center gap-1 flex-1 text-left py-0.5 truncate"
              :class="entry.kind === 'project' ? 'font-medium' : ''"
            >
              <span class="truncate">{{ entry.label }}</span>
              <span :class="['ml-auto text-xs flex-shrink-0', isTagSelected(entry.tagName) ? 'text-purple-200' : 'text-gray-500']">{{ entry.image_count }}</span>
            </button>
          </div>
        </div>
      </div>

      <!-- Tag filter -->
      <div class="mb-4">
        <label class="block text-xs text-gray-400 mb-1 flex items-center justify-between">
          <span>
            Filter by Tags
            <span class="text-gray-500">({{ visibleTagCount }} / {{ nonProjectTags.length }})</span>
          </span>
          <button
            @click="tagViewMode = tagViewMode === 'tree' ? 'flat' : 'tree'"
            class="text-gray-500 hover:text-gray-300 normal-case tracking-normal"
            :title="tagViewMode === 'tree' ? 'Switch to flat view' : 'Switch to tree view'"
          >
            {{ tagViewMode === 'tree' ? '🌳' : '☰' }}
          </button>
        </label>
        <input
          v-model="tagFilterQuery"
          type="text"
          placeholder="Search tags…"
          class="w-full bg-gray-700 border border-gray-600 text-white rounded px-2 py-1 text-sm mb-2"
        />
        <div class="max-h-64 overflow-y-auto">
          <!-- Flat view (or fallback when search is active) -->
          <div v-if="tagViewMode === 'flat' || tagFilterQuery" class="flex flex-wrap gap-1">
            <button
              v-for="tag in flatTags"
              :key="tag.id"
              @click="toggleTagFilter(tag.name)"
              :class="tagButtonClass(tag)"
            >
              {{ tag.name }} ({{ tag.image_count }})
            </button>
            <span v-if="!flatTags.length" class="text-xs text-gray-500 italic">No matching tags</span>
          </div>

          <!-- Tree view -->
          <div v-else class="space-y-1">
            <div v-for="group in tagTree" :key="group.parent ? group.parent.id : 'orphans'">
              <!-- Parent row (if there is one) -->
              <button
                v-if="group.parent"
                @click="toggleTagFilter(group.parent.name)"
                :class="[tagButtonClass(group.parent), 'font-semibold w-full text-left']"
              >
                {{ group.parent.name }} ({{ group.parent.image_count }})
              </button>
              <!-- Children indented -->
              <div :class="['flex flex-wrap gap-1', group.parent ? 'ml-3 mt-1' : '']">
                <button
                  v-for="tag in group.children"
                  :key="tag.id"
                  @click="toggleTagFilter(tag.name)"
                  :class="tagButtonClass(tag)"
                >
                  {{ tag.name }} ({{ tag.image_count }})
                </button>
              </div>
            </div>
            <span v-if="!tagTree.length" class="text-xs text-gray-500 italic">No tags yet</span>
          </div>
        </div>
      </div>

      <!-- Bulk actions -->
      <div v-if="store.selectedImageIds.length" class="mt-4 border-t border-gray-700 pt-4">
        <p class="text-xs text-gray-400 mb-2">{{ store.selectedImageIds.length }} selected</p>
        <div class="flex gap-1 mb-3">
          <button @click="store.selectAll()" class="text-xs bg-gray-700 hover:bg-gray-600 px-2 py-1 rounded">
            All
          </button>
          <button @click="store.clearSelection()" class="text-xs bg-gray-700 hover:bg-gray-600 px-2 py-1 rounded">
            None
          </button>
        </div>

        <!-- Add tags -->
        <input
          v-model="bulkTagInput"
          placeholder="tag1, tag2…"
          class="w-full bg-gray-700 border border-gray-600 text-white rounded px-2 py-1 text-xs mb-1"
          @keyup.enter="doBulkTag"
        />
        <button
          @click="doBulkTag"
          class="w-full bg-purple-600 hover:bg-purple-700 text-white rounded px-2 py-1 text-xs mb-3"
        >
          Bulk Tag
        </button>

        <!-- Remove tag -->
        <div v-if="selectedImagesTags.length" class="mb-3">
          <label class="block text-xs text-gray-400 mb-1">Remove Tag</label>
          <select
            v-model="bulkRemoveTagInput"
            class="w-full bg-gray-700 border border-gray-600 text-white rounded px-2 py-1 text-xs mb-1"
          >
            <option value="">— pick a tag —</option>
            <option v-for="tag in selectedImagesTags" :key="tag" :value="tag">{{ tag }}</option>
          </select>
          <button
            @click="doBulkRemoveTag"
            :disabled="!bulkRemoveTagInput"
            class="w-full bg-red-700 hover:bg-red-600 disabled:opacity-40 text-white rounded px-2 py-1 text-xs"
          >
            Remove Tag
          </button>
        </div>

        <!-- Assign to project -->
        <button
          @click="showBulkProjectModal = true"
          class="w-full bg-indigo-700 hover:bg-indigo-600 text-white rounded px-2 py-1 text-xs mb-2"
        >
          📁 Assign to Project
        </button>

        <!-- Thumbs down -->
        <button
          @click="doBulkThumbsDown"
          class="w-full bg-gray-700 hover:bg-gray-600 text-white rounded px-2 py-1 text-xs"
        >
          👎 Thumbs Down
        </button>
      </div>
    </aside>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useImagesStore } from '../stores/images.js'
import { useProjectsStore } from '../stores/projects.js'
import ImageCard from '../components/ImageCard.vue'
import BulkProjectModal from '../components/BulkProjectModal.vue'

const store = useImagesStore()
const projectsStore = useProjectsStore()
const bulkTagInput = ref('')
const tagFilterQuery = ref('')
const tagViewMode = ref('tree')   // 'tree' | 'flat'
const bulkRemoveTagInput = ref('')
const galleryEl = ref(null)
const sentinelEl = ref(null)
const showBulkProjectModal = ref(false)
let observer = null

// Date tree state — default current year + month expanded
const today = new Date()
const currentYear = today.getFullYear().toString()
const currentMonth = String(today.getMonth() + 1).padStart(2, '0')
const expandedYears = ref(new Set([currentYear]))
const expandedMonths = ref(new Set([`${currentYear}-${currentMonth}`]))
const selectedDay = ref(null)
const selectedMonth = ref(null)  // "YYYY-MM" when a whole month is selected

// Project tree expand state — a project's row collapses by default unless
// it (or one of its descendants) is selected as a filter.
const expandedProjects = ref(new Set())

function matchesQuery(tag, q) {
  if (!q) return true
  return tag.name.toLowerCase().includes(q)
}

// Hide project:* tags from the main tag list — they're managed through
// the project UI, not the tag filter.
const nonProjectTags = computed(() =>
  store.allTags.filter((t) => !t.name.startsWith('project:'))
)

// Flat view: filter, then pin selected, then sort by image count desc.
const flatTags = computed(() => {
  const q = tagFilterQuery.value.trim().toLowerCase()
  const selected = new Set(store.selectedTags)
  const pinned = []
  const rest = []
  for (const tag of nonProjectTags.value) {
    if (selected.has(tag.name)) {
      pinned.push(tag)
    } else if (matchesQuery(tag, q)) {
      rest.push(tag)
    }
  }
  rest.sort((a, b) => (b.image_count || 0) - (a.image_count || 0))
  return [...pinned, ...rest]
})

// Tree view: group children under their parent. Orphan tags (no parent and
// not pointed at by anyone) appear in a final unparented group.
const tagTree = computed(() => {
  const byId = new Map(nonProjectTags.value.map((t) => [t.id, t]))
  const groups = new Map()  // parent_id -> { parent, children: [] }
  const orphans = []

  for (const tag of nonProjectTags.value) {
    if (tag.parent_tag_id && byId.has(tag.parent_tag_id)) {
      const pid = tag.parent_tag_id
      if (!groups.has(pid)) {
        groups.set(pid, { parent: byId.get(pid), children: [] })
      }
      groups.get(pid).children.push(tag)
    }
  }

  // A tag is an orphan only if it isn't a parent in `groups` and has no parent of its own.
  for (const tag of nonProjectTags.value) {
    if (groups.has(tag.id)) continue          // is a parent → already represented
    if (tag.parent_tag_id) continue            // is a child → handled above
    orphans.push(tag)
  }

  const sortByCount = (a, b) => (b.image_count || 0) - (a.image_count || 0)

  const groupArr = [...groups.values()]
  for (const g of groupArr) g.children.sort(sortByCount)
  groupArr.sort((a, b) => (b.parent.image_count || 0) - (a.parent.image_count || 0))
  orphans.sort(sortByCount)

  if (orphans.length) groupArr.push({ parent: null, children: orphans })
  return groupArr
})

const visibleTagCount = computed(() => {
  if (tagViewMode.value === 'flat' || tagFilterQuery.value) return flatTags.value.length
  return tagTree.value.reduce((n, g) => n + g.children.length + (g.parent ? 1 : 0), 0)
})

function tagButtonClass(tag) {
  return [
    'px-2 py-0.5 rounded text-xs transition-colors',
    store.selectedTags.includes(tag.name)
      ? 'bg-purple-600 text-white'
      : 'bg-gray-700 text-gray-300 hover:bg-gray-600',
  ]
}

onMounted(() => {
  observer = new IntersectionObserver(
    async (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue
        if (store.loading || store.page >= store.pages) continue
        await store.fetchMoreImages()
        // Re-observe so a still-intersecting sentinel (short page, big viewport)
        // triggers another fetch instead of getting stuck.
        if (sentinelEl.value && observer) {
          observer.unobserve(sentinelEl.value)
          observer.observe(sentinelEl.value)
        }
      }
    },
    { root: galleryEl.value, rootMargin: '600px' },
  )

  store.fetchImages(true)
  store.fetchAllTags()
  store.fetchDates()
  projectsStore.fetchProjects()
})

watch(sentinelEl, (el, oldEl) => {
  if (oldEl) observer?.unobserve(oldEl)
  if (el) observer?.observe(el)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
})

async function onBulkAssigned() {
  showBulkProjectModal.value = false
  await projectsStore.fetchProjects()
}

// Build sorted year → month → days tree from flat date list. Use arrays
// (not plain objects) so iteration order is explicit — JS object key order
// puts unpadded numeric strings ("10","11","12") before zero-padded ones
// ("01"…"09"), which scrambled the month/day list.
const dateTree = computed(() => {
  const byYear = new Map()
  for (const { date, count } of store.availableDates) {
    const [year, month, day] = date.split('-')
    if (!byYear.has(year)) byYear.set(year, new Map())
    const byMonth = byYear.get(year)
    if (!byMonth.has(month)) byMonth.set(month, [])
    byMonth.get(month).push({ day, date, count })
  }
  const years = []
  for (const [year, byMonth] of byYear) {
    const months = []
    for (const [month, days] of byMonth) {
      days.sort((a, b) => b.day.localeCompare(a.day))
      months.push({ month, days })
    }
    months.sort((a, b) => b.month.localeCompare(a.month))
    years.push({ year, months })
  }
  years.sort((a, b) => b.year.localeCompare(a.year))
  return years
})

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
function monthName(mm) {
  return MONTH_NAMES[parseInt(mm) - 1] || mm
}

function toggleYear(year) {
  const next = new Set(expandedYears.value)
  if (next.has(year)) next.delete(year)
  else next.add(year)
  expandedYears.value = next
}

function toggleMonth(yearMonth) {
  const next = new Set(expandedMonths.value)
  if (next.has(yearMonth)) next.delete(yearMonth)
  else next.add(yearMonth)
  expandedMonths.value = next
}

function selectDay(date) {
  selectedDay.value = date
  selectedMonth.value = null
  store.dateFrom = date
  store.dateTo = date
  store.fetchImages(true)
}

function selectMonth(year, month) {
  // Date(year, month, 0) → last day of (month-1) in 0-indexed terms,
  // which equals the last day of `month` in our 1-indexed input.
  const lastDay = new Date(parseInt(year), parseInt(month), 0).getDate()
  selectedMonth.value = `${year}-${month}`
  selectedDay.value = null
  store.dateFrom = `${year}-${month}-01`
  store.dateTo = `${year}-${month}-${String(lastDay).padStart(2, '0')}`
  store.fetchImages(true)
}

function clearDateFilter() {
  selectedDay.value = null
  selectedMonth.value = null
  store.dateFrom = ''
  store.dateTo = ''
  store.fetchImages(true)
}

function toggleTagFilter(tagName) {
  const idx = store.selectedTags.indexOf(tagName)
  if (idx === -1) store.selectedTags.push(tagName)
  else store.selectedTags.splice(idx, 1)
  store.fetchImages(true)
}

// Project filtering rides on the same selectedTags pipeline — `project:<slug>`
// already includes descendants thanks to the recursive tag-descendant CTE in
// the backend, so a single tag filter covers the whole project subtree.
function projectTagName(slug) {
  return `project:${slug}`
}

function isTagSelected(tagName) {
  return store.selectedTags.includes(tagName)
}

function clearProjectFilters() {
  store.selectedTags = store.selectedTags.filter((t) => !t.startsWith('project:'))
  store.fetchImages(true)
}

function toggleProjectExpand(key) {
  const next = new Set(expandedProjects.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expandedProjects.value = next
}

const selectedProjectSlugs = computed(() =>
  store.selectedTags
    .filter((t) => t.startsWith('project:'))
    .map((t) => t.split(':')[1])
    .filter(Boolean),
)

// Per-project role buckets derived from `project:<slug>:<role>:<value>` tags.
// Role tags themselves don't exist as separate rows in the DB — only the
// leaf role:value tags do — so role nodes are virtual headers built here.
const projectRolesBySlug = computed(() => {
  const out = new Map()
  for (const tag of store.allTags) {
    if (!tag.name.startsWith('project:')) continue
    const parts = tag.name.split(':')
    if (parts.length < 4) continue
    const slug = parts[1]
    const role = parts[2]
    const value = parts.slice(3).join(':')
    if (!out.has(slug)) out.set(slug, new Map())
    const roles = out.get(slug)
    if (!roles.has(role)) roles.set(role, [])
    roles.get(role).push({ tagName: tag.name, label: value, image_count: tag.image_count || 0 })
  }
  for (const roles of out.values()) {
    for (const arr of roles.values()) arr.sort((a, b) => b.image_count - a.image_count)
  }
  return out
})

// Build project tree from parent_slug. A project whose parent_slug isn't
// present in the project list is treated as a root so nothing gets dropped.
const projectTree = computed(() => {
  const projects = projectsStore.projects
  const bySlug = new Map(projects.map((p) => [p.slug, { ...p, children: [] }]))
  const roots = []
  for (const node of bySlug.values()) {
    if (node.parent_slug && bySlug.has(node.parent_slug)) {
      bySlug.get(node.parent_slug).children.push(node)
    } else {
      roots.push(node)
    }
  }
  const sortFn = (a, b) => a.name.localeCompare(b.name)
  const sortAll = (nodes) => {
    nodes.sort(sortFn)
    for (const n of nodes) sortAll(n.children)
  }
  sortAll(roots)
  return roots
})

// Auto-expand ancestors of any selected project so the active filter stays
// visible even after the projects list refreshes.
const projectAncestors = computed(() => {
  const bySlug = new Map(projectsStore.projects.map((p) => [p.slug, p]))
  const ancestors = (slug) => {
    const out = []
    let cursor = bySlug.get(slug)
    while (cursor && cursor.parent_slug) {
      out.push(cursor.parent_slug)
      cursor = bySlug.get(cursor.parent_slug)
    }
    return out
  }
  const set = new Set()
  for (const slug of selectedProjectSlugs.value) {
    for (const a of ancestors(slug)) set.add(a)
  }
  return set
})

// Flatten the project tree into a single array of typed rows so the template
// can render projects, role headers, and role values uniformly.
//   kind === 'project' → top/sub-project, click filters by `project:<slug>`
//   kind === 'role'    → virtual header (no real tag), expand only
//   kind === 'value'   → leaf, click filters by full `project:<slug>:<role>:<value>` tag
const projectTreeFlat = computed(() => {
  const out = []
  const expanded = expandedProjects.value
  const forced = projectAncestors.value
  const rolesBySlug = projectRolesBySlug.value

  const walk = (nodes, depth) => {
    for (const n of nodes) {
      const projectKey = `p:${n.slug}`
      const roles = rolesBySlug.get(n.slug)
      const hasSubProjects = n.children.length > 0
      const hasRoles = roles && roles.size > 0
      const hasChildren = hasSubProjects || hasRoles
      const isExpanded = expanded.has(projectKey) || forced.has(n.slug)

      out.push({
        kind: 'project',
        key: projectKey,
        tagName: projectTagName(n.slug),
        label: n.name,
        image_count: n.image_count,
        depth,
        hasChildren,
        expanded: isExpanded,
      })

      if (!isExpanded) continue

      if (hasSubProjects) walk(n.children, depth + 1)

      if (hasRoles) {
        for (const [roleName, values] of roles) {
          const roleKey = `r:${n.slug}:${roleName}`
          const roleExpanded = expanded.has(roleKey)
          out.push({
            kind: 'role',
            key: roleKey,
            label: roleName,
            count: values.length,
            depth: depth + 1,
            hasChildren: true,
            expanded: roleExpanded,
          })
          if (!roleExpanded) continue
          for (const v of values) {
            out.push({
              kind: 'value',
              key: `v:${v.tagName}`,
              tagName: v.tagName,
              label: v.label,
              image_count: v.image_count,
              depth: depth + 2,
              hasChildren: false,
            })
          }
        }
      }
    }
  }
  walk(projectTree.value, 0)
  return out
})

async function doBulkTag() {
  const tags = bulkTagInput.value.split(',').map((t) => t.trim()).filter(Boolean)
  if (!tags.length) return
  await store.bulkTag(tags)
  bulkTagInput.value = ''
}

const selectedImagesTags = computed(() => {
  const names = new Set()
  for (const img of store.images) {
    if (store.selectedImageIds.includes(img.id)) {
      for (const tag of img.tags) names.add(tag.name)
    }
  }
  return [...names].sort()
})

async function doBulkRemoveTag() {
  const tag = bulkRemoveTagInput.value
  if (!tag) return
  const n = store.selectedImageIds.length
  if (!confirm(`Remove tag "${tag}" from ${n} selected image${n !== 1 ? 's' : ''}?`)) return
  await store.bulkRemoveTag(tag)
  bulkRemoveTagInput.value = ''
}

async function doBulkThumbsDown() {
  const n = store.selectedImageIds.length
  if (!confirm(`Mark ${n} image${n !== 1 ? 's' : ''} as thumbs-down? They will be hidden.`)) return
  await store.bulkRate(-1)
  store.clearSelection()
}

// Flat list with a dateLabel set on the first image of each new date run, so
// the grid flows continuously and dates render as headers above the boundary
// image rather than forcing a row break.
const imagesWithDateLabels = computed(() => {
  let lastDate = null
  return store.images.map((img) => {
    const date = img.date_taken ? img.date_taken.split('T')[0] : 'Unknown Date'
    const showLabel = date !== lastDate
    lastDate = date
    return { img, dateLabel: showLabel ? formatDate(date) : null }
  })
})

function formatDate(dateStr) {
  if (dateStr === 'Unknown Date') return dateStr
  try {
    return new Date(dateStr + 'T00:00:00').toLocaleDateString(undefined, {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    })
  } catch {
    return dateStr
  }
}
</script>
