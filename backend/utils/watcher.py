"""
Watchdog-based file watcher for IMAGE_DIR.

When a new image (or its sidecar JSON) is copied/moved into the watched
directory tree, it is immediately ingested into the database.
"""

import logging
import os
from pathlib import Path
from threading import Timer
from typing import Dict

from sqlmodel import Session
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

from database import engine
from utils.scanner import IMAGE_EXTENSIONS, scan_image_file

logger = logging.getLogger(__name__)

# Debounce delay in seconds — give file writes time to finish before ingesting.
DEBOUNCE_SECONDS = 2.0


class _DebounceHandler(FileSystemEventHandler):
    """Debounces rapid events for the same path before processing."""

    def __init__(self):
        super().__init__()
        self._timers: Dict[str, Timer] = {}

    def _schedule(self, path: str):
        if path in self._timers:
            self._timers[path].cancel()
        t = Timer(DEBOUNCE_SECONDS, self._process, args=[path])
        self._timers[path] = t
        t.start()

    def _process(self, path: str):
        self._timers.pop(path, None)
        p = Path(path)
        suffix = p.suffix.lower()

        # If a sidecar JSON arrived, process the corresponding image instead.
        if suffix == ".json":
            # Try both foo.json -> foo.png and foo.png.json -> foo.png
            candidates = [p.with_suffix(ext) for ext in IMAGE_EXTENSIONS]
            if p.stem.lower().endswith(tuple(IMAGE_EXTENSIONS)):
                candidates.insert(0, p.parent / p.stem)
            for candidate in candidates:
                if candidate.exists():
                    p = candidate
                    break
            else:
                return  # No matching image yet; it will trigger its own event.

        if p.suffix.lower() not in IMAGE_EXTENSIONS:
            return

        if not p.exists():
            return

        logger.info(f"Watcher: processing {p}")
        with Session(engine) as db:
            try:
                scan_image_file(db, p)
            except Exception as e:
                logger.error(f"Watcher: failed to process {p}: {e}")

    def on_created(self, event: FileSystemEvent):
        if not event.is_directory:
            self._schedule(os.fsdecode(event.src_path))

    def on_moved(self, event: FileSystemEvent):
        if not event.is_directory and hasattr(event, "dest_path"):
            self._schedule(os.fsdecode(event.dest_path))


def start_watcher(image_dir: str):
    """Start watching *image_dir* recursively. Returns the running Observer."""
    observer = Observer()
    handler = _DebounceHandler()
    observer.schedule(handler, path=image_dir, recursive=True)
    observer.start()
    logger.info(f"Watcher: watching {image_dir}")
    return observer


def stop_watcher(observer):
    observer.stop()
    observer.join()
