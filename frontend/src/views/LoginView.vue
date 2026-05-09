<template>
  <div class="min-h-[calc(100vh-64px)] flex items-center justify-center px-4 py-12">
    <div class="w-full max-w-md bg-gray-800 rounded-xl p-8 shadow-2xl">
      <h1 class="text-2xl font-bold text-white mb-2">Sign in</h1>
      <p class="text-sm text-gray-400 mb-6">Welcome back to Diffusion Viewer.</p>

      <form @submit.prevent="submit" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-1">Username</label>
          <input
            v-model="username"
            type="text"
            autocomplete="username"
            required
            class="w-full bg-gray-700 border border-gray-600 text-white rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-1">Password</label>
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
            class="w-full bg-gray-700 border border-gray-600 text-white rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
        </div>

        <div v-if="auth.error" class="text-sm text-red-400">
          {{ auth.error }}
        </div>

        <button
          type="submit"
          :disabled="auth.loading"
          class="w-full bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50 transition-colors"
        >
          {{ auth.loading ? 'Signing in…' : 'Sign in' }}
        </button>
      </form>

      <p class="mt-6 text-sm text-gray-400 text-center">
        No account?
        <router-link to="/register" class="text-purple-400 hover:text-purple-300">Create one</router-link>
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const username = ref('')
const password = ref('')

async function submit() {
  const ok = await auth.login(username.value.trim(), password.value)
  if (ok) {
    const next = typeof route.query.next === 'string' ? route.query.next : '/'
    router.replace(next)
  }
}
</script>
