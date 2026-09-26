# Modified for DocLayout; see NOTICE for a summary of changes.
import os
from typing import Literal

from dotenv import find_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Paths
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    OUTPUT_DIR: str = os.path.join(BASE_DIR, "conversion_results")
    FONT_DIR: str = os.path.join(BASE_DIR, "static", "fonts")
    ARTIFACT_URL: str = "https://models.datalab.to/artifacts"
    FONT_NAME: str = "GoNotoCurrent-Regular.ttf"
    FONT_PATH: str = os.path.join(FONT_DIR, FONT_NAME)
    LOGLEVEL: str = "INFO"

    # General
    OUTPUT_ENCODING: str = "utf-8"
    OUTPUT_IMAGE_FORMAT: str = "JPEG"

    # Operator policy; these settings are never accepted from HTTP requests.
    DOCLAYOUT_MAX_FILE_MIB: int = Field(default=200, gt=0)
    DOCLAYOUT_MAX_PAGES: int = Field(default=500, gt=0)
    DOCLAYOUT_MAX_ARCHIVE_MEMBERS: int = Field(default=10000, gt=0)
    DOCLAYOUT_MAX_EXPANDED_MIB: int = Field(default=1024, gt=0)
    DOCLAYOUT_MAX_SOURCE_PIXELS: int = Field(default=64000000, gt=0)
    DOCLAYOUT_MAX_RENDER_PIXELS: int = Field(default=16000000, gt=0)
    DOCLAYOUT_MAX_WORKSHEET_CELLS: int = Field(default=1000000, gt=0)
    DOCLAYOUT_MAX_RESOURCE_MIB: int = Field(default=64, gt=0)
    DOCLAYOUT_LAYOUT_DEVICE: Literal["auto", "cuda", "cpu"] = "auto"
    DOCLAYOUT_LAYOUT_CACHE_DIR: str = os.path.join(BASE_DIR, "cache", "pp-doclayoutv3")
    DOCLAYOUT_LAYOUT_MODEL_DIR: str | None = None
    DOCLAYOUT_LAYOUT_OFFLINE: bool = False

    class Config:
        env_file = find_dotenv("local.env")
        extra = "ignore"


settings = Settings()
