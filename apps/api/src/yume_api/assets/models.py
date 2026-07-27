from typing import Literal

from pydantic import BaseModel, Field


class Size(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class Anchor(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class UiManifest(BaseModel):
    image: str
    atlas: str
    nine_slice: dict[str, tuple[int, int, int, int]] = Field(default_factory=dict)


class PackManifest(BaseModel):
    schema_version: Literal[1]
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str
    tile: Size
    character: Size
    map: str
    atlas: str
    anchors: dict[str, Anchor]
    animations: dict[str, list[int]]
    ui: UiManifest | None = None
