import { defineStore } from 'pinia'
import axios from 'axios'

export const useProjectsStore = defineStore('projects', {
  state: () => ({
    projects: [],
    loading: false,
  }),

  actions: {
    async fetchProjects() {
      this.loading = true
      try {
        const res = await axios.get('/api/projects')
        this.projects = res.data
      } catch (e) {
        console.error('fetchProjects failed', e)
      } finally {
        this.loading = false
      }
    },

    async assignProject(imageId, project, roles) {
      const res = await axios.post(`/api/images/${imageId}/project`, { project, roles })
      await this.fetchProjects()
      return res.data
    },

    async removeProject(imageId, project, roles = null) {
      const body = roles ? { project, roles } : { project }
      const res = await axios.delete(`/api/images/${imageId}/project`, { data: body })
      await this.fetchProjects()
      return res.data
    },
  },
})
