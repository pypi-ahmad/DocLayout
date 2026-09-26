# Modified for DocLayout; see NOTICE for a summary of changes.
from pydantic import BaseModel

from doclayout.renderers import BaseRenderer
from doclayout.schema.layout import visible_source_blocks


class OCRJSONLineOutput(BaseModel):
    id: str
    block_type: str
    html: str
    polygon: list[list[float]]
    bbox: list[float]


class OCRJSONPageOutput(BaseModel):
    id: str
    block_type: str
    polygon: list[list[float]]
    bbox: list[float]
    children: list[OCRJSONLineOutput]


class OCRJSONOutput(BaseModel):
    children: list[OCRJSONPageOutput]
    block_type: str = "Document"
    metadata: dict | None = None


class OCRJSONRenderer(BaseRenderer):
    """Return aligned source blocks and rectangle-derived polygons, not character boxes."""

    def __call__(self, document):
        pages = []
        for page in document.pages:
            blocks = []
            for block in visible_source_blocks(page, self.block_config):
                blocks.append(
                    OCRJSONLineOutput(
                        id=str(block.id),
                        block_type=str(block.block_type),
                        html=getattr(block, "html", "") or "",
                        polygon=block.polygon.polygon,
                        bbox=block.polygon.bbox,
                    )
                )
            pages.append(
                OCRJSONPageOutput(
                    id=str(page.id),
                    block_type=str(page.block_type),
                    polygon=page.polygon.polygon,
                    bbox=page.polygon.bbox,
                    children=blocks,
                )
            )
        return OCRJSONOutput(
            children=pages, metadata=self.generate_document_metadata(document, None)
        )
