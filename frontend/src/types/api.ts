// Response/request shapes for the diffusion-viewer backend.
// Manually maintained to mirror `backend/schemas.py`. When the photosafe
// merge happens these will be replaced by generated types from the OpenAPI
// schema.

export interface Tag {
  id: number
  name: string
  parent_tag_id?: number | null
  parent_name?: string | null
  path?: string | null
  image_count?: number
}

export interface Image {
  id: number
  uuid?: string
  filename: string
  filepath: string
  directory: string
  width?: number | null
  height?: number | null
  file_size?: number | null
  date_taken?: string | null
  created_at: string
  updated_at: string
  rating: number
  hidden: boolean
  deleted_at?: string | null
  sidecar_data?: string | null
  prompt?: string | null
  description?: string | null
  model?: string | null
  thumbnail_path?: string | null
  tags: Tag[]
}

export interface ImageListResponse {
  items: Image[]
  total: number
  page: number
  pages: number
}

// --- Projects (legacy `project:*` tag convention) -------------------------

export interface ProjectInfo {
  slug: string
  name: string
  image_count: number
  parent_slug?: string | null
}

// roles[role][value] -> list of images. roles[""][""] is the "unroled" bucket.
export type ProjectRoles = Record<string, Record<string, Image[]>>

export interface ProjectDetail extends ProjectInfo {
  children: ProjectInfo[]
  roles: ProjectRoles
}

// --- Albums (photosafe-aligned) -------------------------------------------

export interface AlbumRoleInfo {
  id: number
  role: string
  value: string
}

export interface AlbumInfo {
  id: number
  uuid: string
  slug: string
  name: string
  description?: string | null
  parent_album_id?: number | null
  parent_slug?: string | null
  image_count: number
  role_count: number
  deleted_at?: string | null
}

export interface AlbumDetail extends AlbumInfo {
  children: AlbumInfo[]
  roles: AlbumRoleInfo[]
  images: Image[]
}

export interface AlbumSyncStats {
  albums_created: number
  albums_updated: number
  roles_created: number
  photos_linked: number
}

// --- Scanner --------------------------------------------------------------

export interface ScanResult {
  scanned: number
  added: number
  updated: number
  with_sidecar: number
  albums_created?: number
  albums_updated?: number
  album_photos_linked?: number
}

export interface DateBucket {
  date: string
  count: number
}

// --- Filtering / sort -----------------------------------------------------

export type SortBy = 'date_taken' | 'created_at' | 'updated_at' | 'rating' | 'filename'
export type SortDir = 'asc' | 'desc'
