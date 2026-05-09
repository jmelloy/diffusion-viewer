import { defineStore } from 'pinia'
import axios from 'axios'

const TOKEN_KEY = 'diffusion_viewer_token'

function readToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

function writeToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* ignore */
  }
}

function applyAuthHeader(token) {
  if (token) {
    axios.defaults.headers.common['Authorization'] = `Bearer ${token}`
  } else {
    delete axios.defaults.headers.common['Authorization']
  }
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: readToken(),
    user: null,
    loading: false,
    error: '',
    initialized: false,
  }),

  getters: {
    isAuthenticated: (state) => !!state.token && !!state.user,
  },

  actions: {
    async init() {
      if (this.initialized) return
      applyAuthHeader(this.token)
      if (this.token) {
        try {
          await this.fetchMe()
        } catch {
          this.clearAuth()
        }
      }
      this.initialized = true
    },

    setAuth(token, user) {
      this.token = token
      this.user = user
      this.error = ''
      writeToken(token)
      applyAuthHeader(token)
    },

    clearAuth() {
      this.token = ''
      this.user = null
      writeToken('')
      applyAuthHeader('')
    },

    async login(username, password) {
      this.loading = true
      this.error = ''
      try {
        const res = await axios.post('/api/auth/login', { username, password })
        this.setAuth(res.data.access_token, res.data.user)
        return true
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || 'Login failed'
        return false
      } finally {
        this.loading = false
      }
    },

    async register(username, password, email) {
      this.loading = true
      this.error = ''
      try {
        const body = { username, password }
        if (email) body.email = email
        const res = await axios.post('/api/auth/register', body)
        this.setAuth(res.data.access_token, res.data.user)
        return true
      } catch (e) {
        this.error = e.response?.data?.detail || e.message || 'Registration failed'
        return false
      } finally {
        this.loading = false
      }
    },

    async fetchMe() {
      const res = await axios.get('/api/auth/me')
      this.user = res.data
      return res.data
    },

    logout() {
      this.clearAuth()
    },
  },
})

// Global response interceptor: if a token expires (401), drop the auth state
// and bounce to /login (unless we're already on a guest page).
axios.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const url = error.config?.url || ''
      // Don't loop on auth endpoints — let the caller surface the error.
      if (!url.startsWith('/api/auth/')) {
        const token = readToken()
        if (token) {
          writeToken('')
          applyAuthHeader('')
        }
        if (typeof window !== 'undefined') {
          const path = window.location.pathname
          if (path !== '/login' && path !== '/register') {
            const next = path + window.location.search
            window.location.assign(`/login?next=${encodeURIComponent(next)}`)
          }
        }
      }
    }
    return Promise.reject(error)
  },
)
