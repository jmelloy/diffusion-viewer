import { defineStore } from 'pinia'
import axios from 'axios'
import type { Image, ProjectDetail, ProjectInfo } from '../types/api'

interface ProjectsState {
  projects: ProjectInfo[]
  loading: boolean
}

type RoleAssignments = Record<string, string[]>

export const useProjectsStore = defineStore('projects', {
  state: (): ProjectsState => ({
    projects: [],
    loading: false,
  }),

  actions: {
    async fetchProjects(): Promise<void> {
      this.loading = true
      try {
        const res = await axios.get<ProjectInfo[]>('/api/projects')
        this.projects = res.data
      } catch (e) {
        console.error('fetchProjects failed', e)
      } finally {
        this.loading = false
      }
    },

    async assignProject(
      imageId: number,
      project: string,
      roles: RoleAssignments,
    ): Promise<Image> {
      const res = await axios.post<Image>(`/api/images/${imageId}/project`, {
        project,
        roles,
      })
      await this.fetchProjects()
      return res.data
    },

    async removeProject(
      imageId: number,
      project: string,
      roles: RoleAssignments | null = null,
    ): Promise<Image> {
      const body: { project: string; roles?: RoleAssignments } = { project }
      if (roles) body.roles = roles
      const res = await axios.delete<Image>(`/api/images/${imageId}/project`, {
        data: body,
      })
      await this.fetchProjects()
      return res.data
    },

    async fetchProject(slug: string): Promise<ProjectDetail> {
      const res = await axios.get<ProjectDetail>(`/api/projects/${slug}`)
      return res.data
    },
  },
})
