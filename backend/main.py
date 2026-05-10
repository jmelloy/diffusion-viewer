import logging
from contextlib import asynccontextmanager
from pathlib import Path
import os

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routers import albums, images, tags, projects
from utils.watcher import start_watcher, stop_watcher

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

BACKEND_DIR = Path(__file__).resolve().parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"


def run_migrations() -> None:
    """Apply Alembic migrations up to head."""
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")


thumbnails_dir = Path(os.environ.get("THUMBNAIL_DIR", "./thumbnails"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path("./thumbnails").mkdir(exist_ok=True)
    image_dir = os.environ.get("IMAGE_DIR")
    observer = None
    if image_dir:
        image_dir_path = Path(image_dir)
        image_dir_path.mkdir(parents=True, exist_ok=True)
        observer = start_watcher(image_dir)
    yield
    if observer:
        stop_watcher(observer)


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
app.include_router(albums.router)

# Serve thumbnails statically
thumbnails_dir.mkdir(exist_ok=True)
app.mount("/thumbnails", StaticFiles(directory=str(thumbnails_dir)), name="thumbnails")


@app.get("/api/health")
def health():
    return {"status": "ok"}
