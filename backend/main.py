import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from sqlalchemy import inspect, text

from database import engine, Base
from routers import images, tags, projects


def _migrate_schema():
    """Lightweight idempotent migrations for SQLite. Run once on startup."""
    inspector = inspect(engine)
    if "tags" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("tags")}
    if "parent_tag_id" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE tags ADD COLUMN parent_tag_id INTEGER REFERENCES tags(id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tags_parent_tag_id ON tags(parent_tag_id)"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create DB tables on startup
    Base.metadata.create_all(bind=engine)
    _migrate_schema()
    # Ensure thumbnails directory exists
    Path("./thumbnails").mkdir(exist_ok=True)
    yield


app = FastAPI(title="Diffusion Viewer API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(images.router)
app.include_router(tags.router)
app.include_router(projects.router)

# Serve thumbnails statically
thumbnails_dir = Path("./thumbnails")
thumbnails_dir.mkdir(exist_ok=True)
app.mount("/thumbnails", StaticFiles(directory=str(thumbnails_dir)), name="thumbnails")


@app.get("/api/health")
def health():
    return {"status": "ok"}
