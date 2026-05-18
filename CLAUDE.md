# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Diffusion Viewer is a photo browser and asset management tool for AI-generated images (Stable Diffusion, ComfyUI, Midjourney, DALL·E, etc.). It parses sidecar metadata, generates thumbnails, manages hierarchical tags, and organizes images into albums/projects.

## Commands

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload          # Dev server at :8000, Swagger at /docs
alembic upgrade head               # Run migrations
```

### Frontend

```bash
cd frontend
npm install
npm run dev           # Dev server at :5173 (proxies /api and /thumbnails to :8000)
npm run type-check    # TypeScript check (no emit)
npm run build         # Output to frontend/dist/
```

### Docker (full stack)

```bash
docker compose up --build                               # Production stack
docker compose --profile dev up frontend-dev backend    # With Vite dev server
```

### Key environment variables

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | postgresql+psycopg2://diffusion:diffusion@postgres:5432/diffusion_viewer | DB connection |
| `IMAGE_DIR` | `/images` | Source image directory |
| `THUMBNAIL_DIR` | `./thumbnails` | Generated thumbnails |

## Architecture

### Stack

- **Backend**: FastAPI + SQLModel (SQLAlchemy 2.0) + PostgreSQL, Python 3.12
- **Frontend**: Vue 3 + Vite + TypeScript (strict) + Pinia + Tailwind CSS
- **Migrations**: Alembic (`backend/alembic/versions/`)

### Backend layout

```
backend/
├── main.py            # App factory, CORS, static mount for thumbnails
├── database.py        # Engine + session factory
├── models.py          # ORM models
├── schemas.py         # Pydantic v2 request/response shapes
├── routers/           # images.py, tags.py, albums.py, projects.py
└── utils/
    ├── importer/      # ORM-free sidecar parsing + thumbnail generation
    ├── scanner.py     # DB wrapper around importer pipeline
    ├── tfidf.py       # TF-IDF auto-tagging
    ├── albums.py      # project:* tag → Album materialization
    ├── hierarchy.py   # Tag tree recomputation
    └── watcher.py     # Watchdog filesystem monitor
```

### Data model highlights

- **Image**: uuid (stable across re-imports), filepath, rating (-1 to 6), soft-delete via `deleted_at`, `sidecar_data` (raw JSON text for ILIKE search) + `sidecar` (JSONB for queries), prompt, model
- **Tag**: self-referencing hierarchy via `parent_tag_id`
- **Album** / **AlbumRole**: albums have typed role triples (e.g. `character="Scarlett"` in project "Cluedo")
- Legacy `project:<slug>[:role:value]` tags are auto-materialized into Albums on scan (idempotent, via `utils/albums.py`)

### Sidecar format detection

The importer (`utils/importer/`) auto-detects three formats:
- **Generic**: `{ "prompt": "...", "model": "...", "date": "ISO8601" }`
- **A1111**: `{ "parameters": "text prompt\nNegative: ...\nSteps: ..." }`
- **ComfyUI**: nested node graph with `CLIPTextEncode` inputs

### Frontend layout

```
frontend/src/
├── router/index.ts    # Routes: /, /image/:id, /projects/:slug, /albums/:slug, /tags
├── stores/            # Pinia stores: images, albums, projects
├── views/             # GalleryView, DetailView, ProjectsListView, AlbumView, TagManagerView
└── components/        # ImageCard, RatingWidget, etc.
```

Frontend proxies `/api` and `/thumbnails` to the backend via Vite config. Axios uses `paramsSerializer: { indexes: null }` for FastAPI's repeated-key query params (e.g. `tags=a&tags=b`).

### ORM-free importer convention

`backend/utils/importer/` is intentionally kept free of SQLModel/SQLAlchemy so it can be reused or extracted. Business logic for sidecar parsing and thumbnail generation lives here; `scanner.py` is the thin DB wrapper on top.

## Scripts

`/scripts/` contains standalone utilities (Civitai, Leonardo, Invoke AI importers, sidecar converters, auto-organize). They use the importer utilities directly and have their own `requirements.txt`. See `scripts/README.md`.
