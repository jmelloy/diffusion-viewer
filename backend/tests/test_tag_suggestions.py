"""Integration tests for GET /api/images/tag-suggestions."""
import sys
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

# Make backend importable when pytest is run from the backend/ directory or repo root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import models
from database import get_db
from main import app


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as c:
        yield c, engine
    app.dependency_overrides.clear()


def _make_image(filename: str) -> models.Image:
    return models.Image(
        filename=filename,
        filepath=f"/{filename}",
        directory="/",
    )


def test_empty_image_ids(client):
    c, _ = client
    res = c.get("/api/images/tag-suggestions", params={"image_ids": []})
    # Required param with no values → no image_ids in the request → 422
    assert res.status_code == 422
    errors = res.json()["detail"]
    assert any("image_ids" in str(e) for e in errors)


def test_unknown_image_ids_returns_empty(client):
    c, _ = client
    res = c.get("/api/images/tag-suggestions?image_ids=9999")
    assert res.status_code == 200
    assert res.json() == []


def test_suggestions_from_cluster(client):
    """Tags from cluster siblings are returned, sorted by frequency, excluding existing tags."""
    c, engine = client
    with Session(engine) as db:
        project_tag = models.Tag(name="project:myproject")
        tag_a = models.Tag(name="character:alice")
        tag_b = models.Tag(name="style:watercolor")
        tag_c = models.Tag(name="setting:forest")
        db.add_all([project_tag, tag_a, tag_b, tag_c])
        db.flush()

        img1 = _make_image("img1.png")  # selected
        img2 = _make_image("img2.png")  # cluster sibling
        img3 = _make_image("img3.png")  # cluster sibling
        img4 = _make_image("img4.png")  # not in cluster
        db.add_all([img1, img2, img3, img4])
        db.flush()

        # img1 is selected; already has tag_a and the project tag
        img1.tags = [project_tag, tag_a]
        # img2 and img3 share the same project (cluster) as img1
        img2.tags = [project_tag, tag_b, tag_c]
        img3.tags = [project_tag, tag_b]
        # img4 is outside the cluster
        img4.tags = [tag_c]
        db.commit()

        selected_id = img1.id

    res = c.get(f"/api/images/tag-suggestions?image_ids={selected_id}")
    assert res.status_code == 200
    data = res.json()

    names = [s["name"] for s in data]
    # tag_b appears on 2 siblings → should come first
    assert names[0] == "style:watercolor"
    # tag_c appears on 1 sibling (img2); img4 is outside cluster → count=1
    assert "setting:forest" in names
    # tag_a is already on img1 → must not appear
    assert "character:alice" not in names
    # project tags must not appear
    assert all(not n.startswith("project:") for n in names)


def test_no_cluster_falls_back_to_global(client):
    """When selected images have no project tags, return most common tags from all other images."""
    c, engine = client
    with Session(engine) as db:
        tag_x = models.Tag(name="theme:scifi")
        tag_y = models.Tag(name="theme:fantasy")
        db.add_all([tag_x, tag_y])
        db.flush()

        img_sel = _make_image("selected.png")
        img_a = _make_image("other_a.png")
        img_b = _make_image("other_b.png")
        img_c = _make_image("other_c.png")
        db.add_all([img_sel, img_a, img_b, img_c])
        db.flush()

        # Selected image has no project tag
        img_sel.tags = []
        # tag_x appears on 2 images, tag_y on 1
        img_a.tags = [tag_x, tag_y]
        img_b.tags = [tag_x]
        img_c.tags = [tag_y]
        db.commit()

        selected_id = img_sel.id

    res = c.get(f"/api/images/tag-suggestions?image_ids={selected_id}")
    assert res.status_code == 200
    data = res.json()
    names = [s["name"] for s in data]
    assert "theme:scifi" in names
    assert "theme:fantasy" in names
    # theme:scifi should rank higher (frequency 2 vs 1)
    assert names.index("theme:scifi") < names.index("theme:fantasy")


def test_multiple_selected_images(client):
    """Tags from the union of clusters are merged and re-ranked."""
    c, engine = client
    with Session(engine) as db:
        proj1 = models.Tag(name="project:alpha")
        proj2 = models.Tag(name="project:beta")
        tag_shared = models.Tag(name="mood:dark")
        tag_only_alpha = models.Tag(name="style:noir")
        db.add_all([proj1, proj2, tag_shared, tag_only_alpha])
        db.flush()

        img1 = _make_image("sel1.png")
        img2 = _make_image("sel2.png")
        sib1 = _make_image("sib1.png")  # in alpha cluster
        sib2 = _make_image("sib2.png")  # in beta cluster
        db.add_all([img1, img2, sib1, sib2])
        db.flush()

        img1.tags = [proj1]
        img2.tags = [proj2]
        sib1.tags = [proj1, tag_shared, tag_only_alpha]
        sib2.tags = [proj2, tag_shared]
        db.commit()

        ids = [img1.id, img2.id]

    res = c.get("/api/images/tag-suggestions", params={"image_ids": ids})
    assert res.status_code == 200
    data = res.json()
    names = [s["name"] for s in data]
    # mood:dark appears in both clusters → highest frequency
    assert names[0] == "mood:dark"
    assert "style:noir" in names
    assert all(not n.startswith("project:") for n in names)


def test_hidden_and_deleted_siblings_excluded(client):
    """Tags on hidden or soft-deleted cluster siblings must not appear in suggestions."""
    from datetime import datetime

    c, engine = client
    with Session(engine) as db:
        project_tag = models.Tag(name="project:myproject")
        tag_visible = models.Tag(name="mood:happy")
        tag_hidden = models.Tag(name="mood:grim")
        tag_deleted = models.Tag(name="mood:eerie")
        db.add_all([project_tag, tag_visible, tag_hidden, tag_deleted])
        db.flush()

        img_sel = _make_image("selected.png")
        img_visible = _make_image("visible_sibling.png")
        img_hidden = _make_image("hidden_sibling.png")
        img_deleted = _make_image("deleted_sibling.png")
        db.add_all([img_sel, img_visible, img_hidden, img_deleted])
        db.flush()

        img_sel.tags = [project_tag]
        img_visible.tags = [project_tag, tag_visible]
        img_hidden.tags = [project_tag, tag_hidden]
        img_hidden.hidden = True
        img_deleted.tags = [project_tag, tag_deleted]
        img_deleted.deleted_at = datetime(2024, 1, 1)
        db.commit()

        selected_id = img_sel.id

    res = c.get(f"/api/images/tag-suggestions?image_ids={selected_id}")
    assert res.status_code == 200
    names = [s["name"] for s in res.json()]
    assert "mood:happy" in names
    assert "mood:grim" not in names
    assert "mood:eerie" not in names
