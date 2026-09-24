# Modified for DocLayout; see NOTICE for a summary of changes.
from typing import List, Optional

from pdftext.schema import Reference
from PIL import Image
from pydantic import BaseModel

from doclayout.logger import configure_logging
from doclayout.schema.polygon import PolygonBox
from doclayout.settings import settings
from doclayout.util import assign_config

configure_logging()


class BaseProvider:
    def __init__(self, filepath: str, config: Optional[BaseModel | dict] = None):
        assign_config(self, config)
        self.filepath = filepath

    def __len__(self):
        pass

    def get_images(self, idxs: List[int], dpi: int) -> List[Image.Image]:
        pass

    def get_page_bbox(self, idx: int) -> PolygonBox | None:
        pass

    def get_page_refs(self, idx: int) -> List[Reference]:
        pass

    def __enter__(self):
        return self

    def close(self):
        pass

    def __exit__(self, *_):
        self.close()

    @staticmethod
    def get_font_css():
        import base64
        from pathlib import Path

        from doclayout.security import embedded_resource, DocumentLimitError, MIB
        from doclayout.util import download_font

        download_font()
        from weasyprint import CSS
        from weasyprint.text.fonts import FontConfiguration

        font_config = FontConfiguration()
        with Path(settings.FONT_PATH).open("rb") as font:
            data = font.read(settings.DOCLAYOUT_MAX_RESOURCE_MIB * MIB + 1)
        if len(data) > settings.DOCLAYOUT_MAX_RESOURCE_MIB * MIB:
            raise DocumentLimitError("Font exceeds the size limit.")
        font_uri = "data:font/ttf;base64," + base64.b64encode(data).decode("ascii")
        css = CSS(
            string=f"""
            @font-face {{
                font-family: GoNotoCurrent-Regular;
                src: url({font_uri});
                font-display: swap;
            }}
            body {{
                font-family: {settings.FONT_NAME.split(".")[0]}, sans-serif;
                font-variant-ligatures: none;
                font-feature-settings: "liga" 0;
                text-rendering: optimizeLegibility;
            }}
            """,
            font_config=font_config,
            url_fetcher=embedded_resource,
        )
        return css
