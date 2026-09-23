# Modified for DocLayout; see NOTICE for a summary of changes.
"""Render serially, then extract at most three pages concurrently."""

from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, cast

from doclayout.builders import BaseBuilder
from doclayout.schema import BlockTypes
from doclayout.schema.document import Document
from doclayout.schema.extraction import PAGE_PROMPT, ExtractedPage
from doclayout.schema.groups.page import PageGroup
from doclayout.schema.polygon import PolygonBox
from doclayout.schema.registry import get_block_class


class DocumentBuilder(BaseBuilder):
    highres_image_dpi: Annotated[int, "Page extraction rendering DPI."] = 192
    page_concurrency: Annotated[int, "Concurrent page requests (1–3 per process)."] = 3

    def __call__(self, provider, extraction_service):
        if not 1 <= self.page_concurrency <= 3 or self.highres_image_dpi <= 0:
            raise ValueError("page_concurrency must be 1–3 and rendering DPI positive")
        pages = []
        ids = list(provider.page_range)
        with ThreadPoolExecutor(max_workers=self.page_concurrency) as executor:
            for start in range(0, len(ids), self.page_concurrency):
                batch = []
                # PDFium is never called from executor threads.
                for page_id in ids[start : start + self.page_concurrency]:
                    image = provider.get_images([page_id], self.highres_image_dpi)[0]
                    page_class = cast(type[PageGroup], get_block_class(BlockTypes.Page))
                    page = page_class(
                        page_id=page_id,
                        polygon=provider.get_page_bbox(page_id),
                        lowres_image=image,
                        highres_image=image,
                        children=[],
                        structure=[],
                        refs=provider.get_page_refs(page_id),
                        text_extraction_method="openai",
                    )
                    batch.append(
                        (
                            page,
                            executor.submit(
                                extraction_service,
                                PAGE_PROMPT,
                                image,
                                page,
                                ExtractedPage,
                            ),
                        )
                    )
                for page, future in batch:
                    result = ExtractedPage.model_validate(future.result())
                    for item in result.blocks:
                        block = page.add_block(
                            get_block_class(BlockTypes[item.block_type]),
                            PolygonBox.from_bbox(item.bbox).rescale(
                                (1000, 1000), page.polygon.size
                            ),
                        )
                        setattr(block, "html", item.html)
                        block.text_extraction_method = "openai"
                        page.add_structure(block)
                    pages.append(page)
        document_class = cast(type[Document], get_block_class(BlockTypes.Document))
        return document_class(filepath=provider.filepath, pages=pages)
