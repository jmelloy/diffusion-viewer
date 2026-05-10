# diffusion-viewer ↔ photosafe: comparison and combination plan

A side-by-side look at this repo (`jmelloy/diffusion-viewer`) and
[`jmelloy/photosafe`](https://github.com/jmelloy/photosafe), and a concrete plan
for merging the two into a single product.

## TL;DR

Both apps are FastAPI + Vue 3 + Postgres photo galleries built by the same
author. They have heavily overlapping foundations but diverge in domain:

- **photosafe** is a general-purpose, multi-user photo library with auth, S3,
  iCloud/macOS sync, an iOS client, and a background task system.
- **diffusion-viewer** is a single-user AI-image browser with sidecar parsing
  (A1111 / ComfyUI / generic), TF-IDF auto-tagging, hierarchical tags, and a
  "projects" abstraction layered on top of tags.

The recommended path is **adopt photosafe as the base** and merge
diffusion-viewer in as an *AI-image module*: extend the `Photo` model with
prompt/model/sidecar fields, port the sidecar scanners and TF-IDF organizer as
import/task commands, and add hierarchical tags + the `project:*` view on top
of photosafe's existing `keywords` array.

---

## 1. Stack comparison

| Layer            | diffusion-viewer                                   | photosafe                                          |
|------------------|----------------------------------------------------|----------------------------------------------------|
| Backend          | FastAPI, SQLModel/SQLAlchemy 2, Alembic            | FastAPI, SQLAlchemy, Alembic, pyproject/uv         |
| Database         | Postgres 16                                        | Postgres 16                                        |
| Frontend         | Vue 3 + **JavaScript** + Vite + Tailwind + Pinia   | Vue 3 + **TypeScript** + Vite (no Tailwind)        |
| Auth             | None — single user                                 | JWT (access + refresh) + Personal Access Tokens + Apple OAuth |
| Storage          | Local filesystem only, served via FastAPI          | Local filesystem **or** S3 (chosen via `Photo.url`) |
| Mobile           | —                                                  | Native Swift iOS app (`iosapp/`)                   |
| Background work  | `watchdog` directory watcher                       | Generic Task system (`TASK_SYSTEM.md`)             |
| CLI              | Loose Python scripts in `scripts/`                 | Structured `photosafe` CLI (Typer/Click style)     |
| Tests            | None checked in                                    | `tests/unit` + `tests/integration`, `pytest.ini`, `run_tests.sh` |
| Containerization | `docker-compose.yml` (postgres + backend + frontend + frontend-dev) | `docker-compose.yml` + `.override.example` + `cli` profile + `test-db` profile |

**Assessment:** photosafe has the more mature delivery story (auth, S3, tests,
TS, CLI, mobile, override file). diffusion-viewer has a more sophisticated
*content* pipeline for AI imagery.

---

## 2. Domain model comparison

### diffusion-viewer

```
images(id, filename, filepath UNIQUE, directory, width, height, file_size,
       date_taken, created_at, updated_at, rating(-1..5), hidden,
       sidecar_data TEXT, prompt TEXT, description TEXT, model, thumbnail_path)

tags(id, name UNIQUE, parent_tag_id → tags.id ON DELETE SET NULL)
image_tags(image_id, tag_id)  -- M2M
```

Notable:
- Integer PK, file path is the natural key.
- `parent_tag_id` gives a **hierarchy** (recursive CTE used in filtering).
- "Projects" are not a table — they are a **convention on tag names**:
  `project:<slug>` and `project:<slug>:<role>:<value>` (see
  `backend/routers/projects.py`).
- `rating` doubles as a soft-delete signal (-1 = hide).

### photosafe

```
users, personal_access_tokens, apple_credentials, apple_auth_sessions
libraries
photos(uuid PK, owner→users, exif JSONB, faces JSONB, place JSONB,
       keywords[], labels[], albums[], persons[], deleted_at, ...)
versions          -- per-photo edits/derivatives
search_data
albums  ←M2M→  album_photos
tasks
place_summaries
```

Notable:
- UUID PKs throughout (good for sync/mobile).
- `keywords`, `labels`, `albums`, `persons` are **Postgres array columns**,
  filled by the macOS Photos importer.
- `deleted_at` for soft delete (separate from rating).
- `Photo.url` is a computed property that prefers the S3 path over local —
  callers should never assemble file URLs themselves.

### Mapping

| Concept            | diffusion-viewer            | photosafe                                | Merge target                            |
|--------------------|-----------------------------|------------------------------------------|------------------------------------------|
| Photo identity     | `id` (int) + `filepath`     | `uuid`                                    | UUID + `filepath` UNIQUE (keep both)     |
| Owner              | n/a                         | `user_id`                                 | `user_id` nullable during migration      |
| Soft delete        | `rating == -1` / `hidden`   | `deleted_at`                              | `deleted_at`; keep `rating` semantically as -1..5 only |
| Rating             | `rating` int                | (none)                                    | Keep `rating` (1–5 + thumbs)             |
| Keywords / tags    | `tags` table + hierarchy    | `keywords[]` (flat array)                 | Both: array on Photo for fast filter, normalized `tags` table for hierarchy/UI |
| Albums             | (tag convention)            | `albums` table M2M                        | photosafe albums; map old `project:*` tags into albums during import |
| AI prompt/model    | columns on `images`         | (none)                                    | Add `prompt`, `model`, `sidecar` JSONB to `photos` |
| EXIF / place / faces | (none)                    | JSONB columns                             | Keep                                     |
| Versions           | (none)                      | `versions` table                          | Keep                                     |

The main schema work is: **add `prompt`, `model`, `sidecar JSONB` to
`photos`**, and **add a normalized `tags` table with `parent_tag_id`** alongside
the existing `keywords[]` array.

---

## 3. API surface comparison

| Capability                  | diffusion-viewer                                  | photosafe                                          |
|-----------------------------|---------------------------------------------------|-----------------------------------------------------|
| List with filters           | `GET /api/images` (`q`, `tags`, `min_rating`, `date_from/to`, `sort_by`) | `GET /api/photos/` (`albums`, `keywords`, `dates`, `photo_types`, `location`) |
| Filter facets               | `GET /api/tags`                                   | `GET /api/photos/filters/`                          |
| Date grouping               | client-side                                       | `GET /api/photos/blocks` (year/month/day)           |
| Detail                      | `GET /api/images/{id}`                            | `GET /api/photos/{uuid}/`                           |
| Original file               | `GET /api/images/{id}/file`                       | `Photo.url` (S3 or `/uploads/...`)                  |
| Thumbnails                  | `GET /api/images/{id}/thumbnail`, `/thumbnails/*` | served from `/uploads`                              |
| Update                      | `PUT /api/images/{id}/rating`, tags endpoints      | `PATCH /api/photos/{uuid}/`                         |
| Bulk                        | `POST /api/images/bulk-tag`                       | `POST /api/photos/batch/`                           |
| Upload                      | (scan from disk)                                  | `POST /api/photos/upload`                           |
| Scan / import               | `POST /api/images/scan`                           | CLI only                                            |
| Auth                        | —                                                 | `POST /api/auth/{register,login,refresh}`, `/me`, tokens |

The photosafe API is the more general one. The diffusion-viewer-specific bits
to preserve are: scan-from-disk endpoint, rating widget, hierarchical tag CRUD,
projects routes.

---

## 4. Frontend comparison

Both use Vue 3 + Vite + Pinia-or-equivalent. Components map roughly 1:1:

| diffusion-viewer (`frontend/src`) | photosafe equivalent |
|-----------------------------------|----------------------|
| `views/GalleryView.vue`           | photo grid view      |
| `views/DetailView.vue`            | photo detail view    |
| `views/ProjectsListView.vue`, `ProjectView.vue` | albums views |
| `views/TagManagerView.vue`        | (no equivalent — diffusion-only) |
| `components/ImageCard.vue`        | photo card           |
| `components/RatingWidget.vue`     | (no equivalent)      |
| `components/TagManager.vue`       | keyword editor       |
| `components/SearchBar.vue`        | search bar           |
| `components/AssignProjectModal.vue`, `BulkProjectModal.vue` | album assign UI |
| `components/RolesEditor.vue`      | (diffusion-only — `project:*:role:value` editor) |
| `stores/images.js`, `stores/projects.js` | API stores     |

Differences worth flagging:
- diffusion-viewer is **JS**, photosafe is **TS**. Merging means converting
  ported components to TS.
- diffusion-viewer uses **Tailwind**; photosafe does not. Either bring Tailwind
  into photosafe or restyle the ported components.

---

## 5. Combination strategy

### Recommended: photosafe as base, add an "AI image" module

Photosafe wins on the harder-to-add capabilities (auth, multi-user, S3, iOS,
tests, sync), so absorb diffusion-viewer's content pipeline into it rather than
the other way round.

#### Phase 0 — discovery (1–2 days)

- Snapshot both schemas; produce a single ER diagram with the fields above.
- Run photosafe's tests locally; confirm the import/scan pipeline path
  (`backend/cli/import_commands.py`) is the right hook for diffusion content.
- Decide policy questions in §6 before writing migrations.

#### Phase 1 — schema additions (Alembic migration in photosafe)

1. `photos`: add `prompt TEXT`, `model TEXT`, `sidecar JSONB`,
   `rating SMALLINT DEFAULT 0` (–1..5).
2. New `tags(id, name UNIQUE, parent_tag_id NULLABLE FK→tags ON DELETE SET NULL)`
   and `photo_tags(photo_id UUID, tag_id INT, PRIMARY KEY(photo_id, tag_id))`.
3. Keep `photos.keywords[]` — it stays the fast-path filter; `tags` is the
   normalized hierarchy used by the tag-manager UI and recursive filters.

#### Phase 2 — port the scanner

Port `backend/utils/scanner.py` and `backend/utils/tfidf.py` into
`photosafe/backend/app/importers/diffusion.py` (or as a new
`photosafe import diffusion <dir>` CLI subcommand). The scanner should:

- Walk a directory, find `<image>.json` sidecars (A1111, ComfyUI, generic).
- Create `Photo` rows owned by the importing user.
- Populate `prompt`, `model`, `sidecar`, `date_taken` (from sidecar, falling
  back to mtime).
- Generate the existing 400 px JPEG thumbnail.
- Run TF-IDF auto-tagging into both `keywords[]` and the `tags` table.

The `watchdog`-based watcher becomes a `photosafe watch <dir>` CLI command, or
a Task in photosafe's task system.

#### Phase 3 — port projects

In diffusion-viewer "projects" are a tag-name convention
(`project:<slug>:<role>:<value>`). In photosafe there are real `albums`. The
merge path:

1. During import, materialize each `project:<slug>` tag as an `Album`.
2. Keep the `project:<slug>:<role>:<value>` tags as **album metadata** (a
   `roles JSONB` column on `albums`, or a separate `album_roles` table).
3. Port `routers/projects.py` to a thin `routers/albums_extras.py` that exposes
   the role editor.

This gets us to one canonical "collection" concept (albums) without losing
diffusion-viewer's roles/scenes UI.

#### Phase 4 — frontend merge

1. Convert ported Vue components from JS → TS, using `<script setup lang="ts">`
   to match photosafe conventions.
2. Add Tailwind to photosafe's frontend (or restyle the four diffusion-only
   components: `RatingWidget`, `TagManager`, `RolesEditor`, the project
   modals). Tailwind is the lower-effort option.
3. Add diffusion-only views behind feature flags or a route prefix
   (`/ai/...`) so the general gallery stays clean.

#### Phase 5 — cutover

- Write a one-off migration script (`scripts/diffusion_to_photosafe.py`) that
  pumps an existing diffusion-viewer SQLite/Postgres DB into photosafe under a
  designated user. There's prior art in
  `scripts/sqlite_to_postgres.py` already.
- Decommission this repo, or keep it as a thin "diffusion importer" wrapper
  that talks to a photosafe instance over its API.

### Alternative A — diffusion-viewer as base

Add JWT auth + a `users` table here, then back-port photosafe's S3 storage and
albums. Pros: simpler immediate codebase. Cons: re-implements auth, mobile
client, sync, and the task system that already exist in photosafe. Not
recommended.

### Alternative B — shared core package

Extract a `photolib-core` Python package (models, scanner, thumbnails) consumed
by both apps. Pros: keeps the apps focused. Cons: highest engineering cost,
and there's no actual third consumer that justifies the extra package
boundary. Skip unless a third app appears.

---

## 6. Open questions to resolve before coding

1. **Photo identity.** Switch diffusion's int IDs to UUIDs at import time, or
   keep both? (Recommend: UUID is the canonical PK; old int IDs become
   `legacy_id` for a release.)
2. **Soft delete semantics.** Map `rating == -1` and `hidden == true` to
   `deleted_at`, or keep `rating` and `hidden` independent of deletion?
   (Recommend: rating stays a rating; `hidden` becomes `deleted_at`.)
3. **Tag vs keyword duality.** Are `tags.name` and `photos.keywords[]` always
   kept in sync, or is `keywords[]` the unprocessed import payload and `tags`
   the curated set?
4. **Per-user vs global tags.** photosafe is multi-user; diffusion-viewer
   tags are global. Scope `tags` per-user, per-library, or global?
5. **Project roles representation.** JSONB on `albums`, or a separate
   `album_roles(album_id, role, value)` table? The latter is easier to query
   but adds joins.
6. **Sidecar storage.** Keep raw sidecar JSON in `photos.sidecar` JSONB, or
   only keep the structured fields and drop the raw blob? (Recommend: keep
   both — the raw blob is small and useful for re-parsing later.)
7. **Frontend styling.** Adopt Tailwind in photosafe, or restyle ported
   components? Affects how much of `frontend/src/components` we can lift
   verbatim.

---

## 7. Quick wins worth doing either way

These improve diffusion-viewer even if the merge slips:

- Pull `pytest` + a couple of integration tests over from photosafe; the
  routers are easy to test and have none today.
- Adopt photosafe's `pyproject.toml` + `uv` setup; drop `requirements.txt`.
- Convert the `frontend` to TS to ease a future port.
- Add `deleted_at` alongside `hidden` so the soft-delete model lines up with
  photosafe ahead of time.
