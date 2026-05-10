import { defineStore } from 'pinia'
import axios from 'axios'

// Pinia store for the photosafe-aligned `/api/albums` endpoints.
// Coexists with `stores/projects.js` during the migration; the materializer
// on the backend keeps the two views in sync.
export const useAlbumsStore = defineStore('albums', {
  state: () => ({
    albums: [],
    loading: false,
    syncing: false,
  }),

  getters: {
    bySlug: (state) => Object.fromEntries(state.albums.map((a) => [a.slug, a])),
  },

  actions: {
    async fetchAlbums({ parentSlug = null, includeDeleted = false } = {}) {
      this.loading = true
      try {
        const params = {}
        if (parentSlug !== null) params.parent_slug = parentSlug
        if (includeDeleted) params.include_deleted = true
        const res = await axios.get('/api/albums', { params })
        this.albums = res.data
        return res.data
      } catch (e) {
        console.error('fetchAlbums failed', e)
        throw e
      } finally {
        this.loading = false
      }
    },

    async fetchAlbum(slug) {
      const res = await axios.get(`/api/albums/${encodeURIComponent(slug)}`)
      return res.data
    },

    async createAlbum({ name, slug = null, description = null, parentSlug = null }) {
      const body = { name }
      if (slug) body.slug = slug
      if (description) body.description = description
      if (parentSlug) body.parent_slug = parentSlug
      const res = await axios.post('/api/albums', body)
      await this.fetchAlbums()
      return res.data
    },

    async updateAlbum(slug, patch) {
      const res = await axios.patch(`/api/albums/${encodeURIComponent(slug)}`, patch)
      await this.fetchAlbums()
      return res.data
    },

    async deleteAlbum(slug) {
      const res = await axios.delete(`/api/albums/${encodeURIComponent(slug)}`)
      await this.fetchAlbums()
      return res.data
    },

    async linkPhotos(slug, imageIds) {
      const res = await axios.post(`/api/albums/${encodeURIComponent(slug)}/photos`, {
        image_ids: imageIds,
      })
      return res.data
    },

    async unlinkPhoto(slug, imageId) {
      const res = await axios.delete(
        `/api/albums/${encodeURIComponent(slug)}/photos/${imageId}`,
      )
      return res.data
    },

    async addRole(slug, role, value) {
      const res = await axios.post(`/api/albums/${encodeURIComponent(slug)}/roles`, {
        role,
        value,
      })
      return res.data
    },

    async removeRole(slug, roleId) {
      const res = await axios.delete(
        `/api/albums/${encodeURIComponent(slug)}/roles/${roleId}`,
      )
      return res.data
    },

    // Trigger the backend to materialize `project:<slug>[:role:value]` tags
    // into albums. Returns the materialization stats.
    async sync() {
      this.syncing = true
      try {
        const res = await axios.post('/api/albums/sync')
        await this.fetchAlbums()
        return res.data
      } finally {
        this.syncing = false
      }
    },
  },
})
