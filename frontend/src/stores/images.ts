import { defineStore } from 'pinia'
import axios from 'axios'
import type {
  DateBucket,
  Image,
  ImageListResponse,
  ScanResult,
  SortBy,
  SortDir,
  Tag,
} from '../types/api'

// FastAPI's List[str] query params expect repeated keys (tags=a&tags=b),
// not the bracketed form (tags[]=a&tags[]=b) that axios produces by default.
const listParams = { paramsSerializer: { indexes: null } } as const

interface ImagesState {
  images: Image[]
  total: number
  page: number
  pages: number
  loading: boolean
  searchQuery: string
  selectedTags: string[]
  showHidden: boolean
  dateFrom: string
  dateTo: string
  minRating: number
  sortBy: SortBy
  sortDir: SortDir
  selectedImageIds: number[]
  allTags: Tag[]
  availableDates: DateBucket[]
}

interface ListParams {
  page: number
  limit: number
  sort_by: SortBy
  sort_dir: SortDir
  show_hidden: boolean
  min_rating: number
  q?: string
  tags?: string[]
  date_from?: string
  date_to?: string
}

function buildListParams(state: ImagesState, page: number): ListParams {
  const params: ListParams = {
    page,
    limit: 100,
    sort_by: state.sortBy,
    sort_dir: state.sortDir,
    show_hidden: state.showHidden,
    min_rating: state.minRating,
  }
  if (state.searchQuery) params.q = state.searchQuery
  if (state.selectedTags.length) params.tags = state.selectedTags
  if (state.dateFrom) params.date_from = state.dateFrom
  if (state.dateTo) params.date_to = state.dateTo
  return params
}

export const useImagesStore = defineStore('images', {
  state: (): ImagesState => ({
    images: [],
    total: 0,
    page: 1,
    pages: 1,
    loading: false,
    searchQuery: '',
    selectedTags: [],
    showHidden: false,
    dateFrom: '',
    dateTo: '',
    minRating: -999,
    sortBy: 'date_taken',
    sortDir: 'desc',
    selectedImageIds: [],
    allTags: [],
    availableDates: [],
  }),

  actions: {
    async fetchImages(resetPage = false): Promise<void> {
      if (resetPage) this.page = 1
      this.loading = true
      try {
        const params = buildListParams(this.$state, this.page)
        const res = await axios.get<ImageListResponse>('/api/images', {
          params,
          ...listParams,
        })
        this.images = res.data.items
        this.total = res.data.total
        this.page = res.data.page
        this.pages = res.data.pages

        // After a filter/view reset, drop any selected ids that aren't part of
        // the new result set — the user can no longer see them, so keeping
        // them selected silently is confusing.
        if (resetPage && this.selectedImageIds.length) {
          const visible = new Set(this.images.map((i) => i.id))
          this.selectedImageIds = this.selectedImageIds.filter((id) => visible.has(id))
        }
      } catch (e) {
        console.error('fetchImages failed', e)
      } finally {
        this.loading = false
      }
    },

    async fetchMoreImages(): Promise<void> {
      if (this.page >= this.pages) return
      this.loading = true
      try {
        const params = buildListParams(this.$state, this.page + 1)
        const res = await axios.get<ImageListResponse>('/api/images', {
          params,
          ...listParams,
        })
        this.images = [...this.images, ...res.data.items]
        this.page = res.data.page
        this.pages = res.data.pages
      } catch (e) {
        console.error('fetchMoreImages failed', e)
      } finally {
        this.loading = false
      }
    },

    async rateImage(imageId: number, rating: number): Promise<void> {
      await axios.put(`/api/images/${imageId}/rating`, { rating })
      const img = this.images.find((i) => i.id === imageId)
      if (img) {
        img.rating = rating
        img.hidden = rating === -1
        if (rating === -1 && !this.showHidden) {
          this.images = this.images.filter((i) => i.id !== imageId)
        }
      }
    },

    async addTags(imageId: number, tagNames: string[]): Promise<Image> {
      const res = await axios.post<Image>(`/api/images/${imageId}/tags`, {
        tag_names: tagNames,
      })
      const img = this.images.find((i) => i.id === imageId)
      if (img) img.tags = res.data.tags
      await this.fetchAllTags()
      return res.data
    },

    async removeTag(imageId: number, tagName: string): Promise<Image> {
      const res = await axios.delete<Image>(
        `/api/images/${imageId}/tags/${encodeURIComponent(tagName)}`,
      )
      const img = this.images.find((i) => i.id === imageId)
      if (img) img.tags = res.data.tags
      return res.data
    },

    async bulkTag(tagNames: string[]): Promise<void> {
      if (!this.selectedImageIds.length || !tagNames.length) return
      await axios.post('/api/images/bulk-tag', {
        image_ids: this.selectedImageIds,
        tag_names: tagNames,
      })
      await this.fetchImages()
      await this.fetchAllTags()
    },

    async bulkRemoveTag(tagName: string): Promise<void> {
      if (!this.selectedImageIds.length || !tagName) return
      await axios.post('/api/images/bulk-remove-tag', {
        image_ids: this.selectedImageIds,
        tag_name: tagName,
      })
      await this.fetchImages()
      await this.fetchAllTags()
    },

    async bulkRate(rating: number): Promise<void> {
      if (!this.selectedImageIds.length) return
      await axios.post('/api/images/bulk-rating', {
        image_ids: this.selectedImageIds,
        rating,
      })
      await this.fetchImages()
    },

    async scanDirectory(directory: string): Promise<ScanResult> {
      const res = await axios.post<ScanResult>('/api/images/scan', { directory })
      await this.fetchImages(true)
      await this.fetchAllTags()
      return res.data
    },

    async fetchAllTags(): Promise<void> {
      const res = await axios.get<Tag[]>('/api/tags')
      this.allTags = res.data
    },

    async fetchDates(): Promise<void> {
      const res = await axios.get<DateBucket[]>('/api/images/dates')
      this.availableDates = res.data
    },

    toggleImageSelection(id: number): void {
      const idx = this.selectedImageIds.indexOf(id)
      if (idx === -1) this.selectedImageIds.push(id)
      else this.selectedImageIds.splice(idx, 1)
    },

    clearSelection(): void {
      this.selectedImageIds = []
    },

    selectAll(): void {
      this.selectedImageIds = this.images.map((i) => i.id)
    },
  },
})
