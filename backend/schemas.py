from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel


class TagBase(BaseModel):
    name: str


class TagCreate(TagBase):
    pass


class Tag(TagBase):
    id: int
    image_count: Optional[int] = 0
    parent_tag_id: Optional[int] = None
    parent_name: Optional[str] = None
    path: Optional[str] = None

    model_config = {"from_attributes": True}


class TagParentUpdate(BaseModel):
    parent_tag_id: Optional[int] = None


class TagMergeRequest(BaseModel):
    source_tag_id: int
    target_tag_id: int


class TagBulkDeleteRequest(BaseModel):
    tag_ids: List[int]


class TagBulkParentRequest(BaseModel):
    tag_ids: List[int]
    parent_tag_id: Optional[int] = None


class TagBulkMergeRequest(BaseModel):
    source_tag_ids: List[int]
    target_tag_id: int


class ImageBase(BaseModel):
    filename: str
    filepath: str
    directory: str
    width: Optional[int] = None
    height: Optional[int] = None
    file_size: Optional[int] = None
    date_taken: Optional[datetime] = None
    rating: int = 0
    hidden: bool = False
    prompt: Optional[str] = None
    description: Optional[str] = None
    model: Optional[str] = None
    thumbnail_path: Optional[str] = None


class ImageCreate(ImageBase):
    sidecar_data: Optional[str] = None


class Image(ImageBase):
    id: int
    created_at: datetime
    updated_at: datetime
    tags: List[Tag] = []
    sidecar_data: Optional[str] = None

    model_config = {"from_attributes": True}


class ImageListResponse(BaseModel):
    items: List[Image]
    total: int
    page: int
    pages: int


class RatingUpdate(BaseModel):
    rating: int


class ScanRequest(BaseModel):
    directory: Optional[str] = None


class BulkTagRequest(BaseModel):
    image_ids: List[int]
    tag_names: List[str]


class BulkRemoveTagRequest(BaseModel):
    image_ids: List[int]
    tag_name: str


class BulkRatingRequest(BaseModel):
    image_ids: List[int]
    rating: int


class TagsAddRequest(BaseModel):
    tag_names: List[str]


class SearchParams(BaseModel):
    q: Optional[str] = None
    tags: Optional[List[str]] = []
    min_rating: int = -999
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    show_hidden: bool = False


class ProjectInfo(BaseModel):
    slug: str
    name: str
    image_count: int
    parent_slug: Optional[str] = None


class ProjectDetail(BaseModel):
    slug: str
    name: str
    image_count: int
    parent_slug: Optional[str] = None
    children: List[ProjectInfo] = []
    # roles[role][value] = list of images, plus roles[""][""] for unroled images
    roles: Dict[str, Dict[str, List[Image]]]


class ProjectAssignRequest(BaseModel):
    project: str
    # role -> value(s); e.g. {"character": "miss scarlett", "scene": "kitchen"}
    # Pass {} to add only the project tag with no role.
    roles: Dict[str, List[str]] = {}


class ProjectRemoveRequest(BaseModel):
    project: str
    # Same shape as assign. Omit to remove the project entirely (and all its role tags).
    roles: Optional[Dict[str, List[str]]] = None
