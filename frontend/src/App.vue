<template>
  <div class="min-h-screen bg-gray-900">
    <!-- Top Navigation -->
    <nav class="bg-gray-800 border-b border-gray-700 px-4 py-3 flex items-center gap-4 sticky top-0 z-50">
      <router-link to="/" class="text-xl font-bold text-purple-400 whitespace-nowrap">
        🎨 Diffusion Viewer
      </router-link>
      <div class="flex-1">
        <SearchBar />
      </div>
      <router-link
        to="/tags"
        class="text-sm text-gray-300 hover:text-white px-3 py-2 rounded-lg hover:bg-gray-700 transition-colors whitespace-nowrap"
      >
        🏷️ Tags
      </router-link>
      <button
        @click="showScanModal = true"
        class="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap"
      >
        📂 Scan Directory
      </button>

      <!-- Auth area -->
      <div v-if="auth.isAuthenticated" class="relative" ref="userMenuRef">
        <button
          @click="userMenuOpen = !userMenuOpen"
          class="flex items-center gap-2 px-2 py-1 rounded-lg hover:bg-gray-700 transition-colors"
          :title="auth.user?.username"
        >
          <span
            class="w-8 h-8 rounded-full bg-purple-600 flex items-center justify-center text-sm font-bold text-white uppercase"
          >
            {{ initial }}
          </span>
          <span class="text-sm text-gray-200 hidden sm:inline">{{ auth.user?.username }}</span>
        </button>

        <div
          v-if="userMenuOpen"
          class="absolute right-0 mt-2 w-48 bg-gray-800 border border-gray-700 rounded-lg shadow-xl py-1 z-50"
        >
          <div class="px-4 py-2 border-b border-gray-700">
            <div class="text-sm font-medium text-white truncate">{{ auth.user?.username }}</div>
            <div v-if="auth.user?.email" class="text-xs text-gray-400 truncate">
              {{ auth.user.email }}
            </div>
          </div>
          <button
            @click="logout"
            class="block w-full text-left px-4 py-2 text-sm text-gray-200 hover:bg-gray-700"
          >
            Sign out
          </button>
        </div>
      </div>
      <div v-else class="flex items-center gap-2">
        <router-link
          to="/login"
          class="text-sm text-gray-300 hover:text-white px-3 py-2 rounded-lg hover:bg-gray-700 transition-colors whitespace-nowrap"
        >
          Sign in
        </router-link>
        <router-link
          to="/register"
          class="text-sm bg-gray-700 hover:bg-gray-600 text-white px-3 py-2 rounded-lg transition-colors whitespace-nowrap"
        >
          Sign up
        </router-link>
      </div>
    </nav>

    <!-- Scan Modal -->
    <div
      v-if="showScanModal"
      class="fixed inset-0 bg-black/70 flex items-center justify-center z-50"
      @click.self="showScanModal = false"
    >
      <div class="bg-gray-800 rounded-xl p-6 w-full max-w-md shadow-2xl">
        <h2 class="text-lg font-bold mb-4 text-white">Scan Image Directory</h2>
        <input
          v-model="scanDirectory"
          type="text"
          placeholder="/path/to/your/images"
          class="w-full bg-gray-700 border border-gray-600 text-white rounded-lg px-3 py-2 mb-3 focus:outline-none focus:ring-2 focus:ring-purple-500"
          @keyup.enter="doScan"
        />
        <div v-if="scanResult" class="text-sm mb-3" :class="scanError ? 'text-red-400' : 'text-green-400'">
          {{ scanResult }}
        </div>
        <div class="flex gap-2 justify-end">
          <button
            @click="showScanModal = false"
            class="px-4 py-2 rounded-lg bg-gray-600 hover:bg-gray-500 text-sm transition-colors"
          >
            Close
          </button>
          <button
            @click="doScan"
            :disabled="scanning"
            class="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-700 text-sm font-medium disabled:opacity-50 transition-colors"
          >
            {{ scanning ? 'Scanning…' : 'Scan' }}
          </button>
        </div>
      </div>
    </div>

    <router-view />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import SearchBar from './components/SearchBar.vue'
import { useImagesStore } from './stores/images.js'
import { useAuthStore } from './stores/auth.js'

const store = useImagesStore()
const auth = useAuthStore()
const router = useRouter()

const showScanModal = ref(false)
const scanDirectory = ref('')
const scanning = ref(false)
const scanResult = ref('')
const scanError = ref(false)

const userMenuOpen = ref(false)
const userMenuRef = ref(null)

const initial = computed(() => (auth.user?.username || '?').charAt(0))

function handleClickOutside(e) {
  if (userMenuOpen.value && userMenuRef.value && !userMenuRef.value.contains(e.target)) {
    userMenuOpen.value = false
  }
}

onMounted(() => {
  auth.init()
  document.addEventListener('click', handleClickOutside)
})
onBeforeUnmount(() => document.removeEventListener('click', handleClickOutside))

function logout() {
  auth.logout()
  userMenuOpen.value = false
  router.push('/login')
}

async function doScan() {
  if (!scanDirectory.value.trim()) return
  scanning.value = true
  scanResult.value = ''
  scanError.value = false
  try {
    const result = await store.scanDirectory(scanDirectory.value.trim())
    const sidecars = result.with_sidecar ?? 0
    scanResult.value = `✅ Scanned: ${result.scanned}, Added: ${result.added}, Updated: ${result.updated}, Sidecars: ${sidecars}`
  } catch (e) {
    scanError.value = true
    scanResult.value = '❌ ' + (e.response?.data?.detail || e.message)
  } finally {
    scanning.value = false
  }
}
</script>
