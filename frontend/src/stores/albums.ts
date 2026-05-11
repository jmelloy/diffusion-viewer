import { defineStore } from 'pinia'
import axios from 'axios'
import type {
  AlbumDetail,
  AlbumInfo,
  AlbumRoleInfo,
  AlbumSyncStats,
} from '../types/api'

// Pinia store for the photosafe-aligned `/api/albums` endpoints.
// Coexists with `stores/projects.ts` during the migration; the materializer
// on the backend keeps the two views in sync.

interface AlbumsState {
  albums: AlbumInfo[]
  loading: boolean
  syncing: boolean
}

interface FetchAlbumsOpts {
  parentSlug?: string | null
  includeDeleted?: boolean
}

interface CreateAlbumOpts {
  name: string
  slug?: string | null
  description?: string | null
  parentSlug?: string | null
}

interface UpdateAlbumPatch {
  name?: string
  description?: string | null
  parent_slug?: string | null
}

export const useAlbumsStore = defineStore('albums', {
  state: (): AlbumsState => ({
    albums: [],
    loading: false,
    syncing: false,
  }),

  getters: {
    bySlug: (state): Record<string, AlbumInfo> =>
      Object.fromEntries(state.albums.map((a) => [a.slug, a])),
  },

  actions: {
    async fetchAlbums({ parentSlug = null, includeDeleted = false }: FetchAlbumsOpts = {}): Promise<AlbumInfo[]> {
      this.loading = true
      try {
        const params: Record<string, string | boolean> = {}
        if (parentSlug !== null) params.parent_slug = parentSlug
        if (includeDeleted) params.include_deleted = true
        const res = await axios.get<AlbumInfo[]>('/api/albums', { params })
        this.albums = res.data
        return res.data
      } catch (e) {
        console.error('fetchAlbums failed', e)
        throw e
      } finally {
        this.loading = false
      }
    },

    async fetchAlbum(slug: string): Promise<AlbumDetail> {
      const res = await axios.get<AlbumDetail>(
        `/api/albums/${encodeURIComponent(slug)}`,
      )
      return res.data
    },

    async createAlbum({
      name,
      slug = null,
      description = null,
      parentSlug = null,
    }: CreateAlbumOpts): Promise<AlbumInfo> {
      const body: Record<string, string | null> = { name }
      if (slug) body.slug = slug
      if (description) body.description = description
      if (parentSlug) body.parent_slug = parentSlug
      const res = await axios.post<AlbumInfo>('/api/albums', body)
      await this.fetchAlbums()
      return res.data
    },

    async updateAlbum(slug: string, patch: UpdateAlbumPatch): Promise<AlbumInfo> {
      const res = await axios.patch<AlbumInfo>(
        `/api/albums/${encodeURIComponent(slug)}`,
        patch,
      )
      await this.fetchAlbums()
      return res.data
    },

    async deleteAlbum(slug: string): Promise<AlbumInfo> {
      const res = await axios.delete<AlbumInfo>(
        `/api/albums/${encodeURIComponent(slug)}`,
      )
      await this.fetchAlbums()
      return res.data
    },

    async linkPhotos(slug: string, imageIds: number[]): Promise<AlbumInfo> {
      const res = await axios.post<AlbumInfo>(
        `/api/albums/${encodeURIComponent(slug)}/photos`,
        { image_ids: imageIds },
      )
      return res.data
    },

    async unlinkPhoto(slug: string, imageId: number): Promise<AlbumInfo> {
      const res = await axios.delete<AlbumInfo>(
        `/api/albums/${encodeURIComponent(slug)}/photos/${imageId}`,
      )
      return res.data
    },

    async addRole(slug: string, role: string, value: string): Promise<AlbumRoleInfo> {
      const res = await axios.post<AlbumRoleInfo>(
        `/api/albums/${encodeURIComponent(slug)}/roles`,
        { role, value },
      )
      return res.data
    },

    async removeRole(slug: string, roleId: number): Promise<AlbumInfo> {
      const res = await axios.delete<AlbumInfo>(
        `/api/albums/${encodeURIComponent(slug)}/roles/${roleId}`,
      )
      return res.data
    },

    // Trigger the backend to materialize `project:<slug>[:role:value]` tags
    // into albums. Returns the materialization stats.
    async sync(): Promise<AlbumSyncStats> {
      this.syncing = true
      try {
        const res = await axios.post<AlbumSyncStats>('/api/albums/sync')
        await this.fetchAlbums()
        return res.data
      } finally {
        this.syncing = false
      }
    },
  },
})
