# Modified for DocLayout; see NOTICE for a summary of changes.
"""Render serially, then extract at most three pages concurrently."""

import logging
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from typing import Annotated, cast

from doclayout.builders import BaseBuilder
from doclayout.builders.alignment import align_blocks
from doclayout.schema import BlockTypes
from doclayout.schema.document import Document
from doclayout.schema.extraction import PAGE_PROMPT, ExtractedPage
from doclayout.schema.groups.page import PageGroup
from doclayout.schema.layout import (
    PageLayout,
    SourceBinding,
    alignment_policy,
    given_layout,
)
from doclayout.schema.polygon import PolygonBox
from doclayout.schema.registry import get_block_class
from doclayout.services.layout import (
    LAYOUT_RUNTIME_ERRORS,
    MODEL_ID,
    MODEL_REVISION,
    LayoutError,
    LayoutInferenceError,
    LayoutResult,
    layout_fallback_message,
)

logger = logging.getLogger(__name__)


class DocumentBuilder(BaseBuilder):
    highres_image_dpi: Annotated[int, "Page extraction rendering DPI."] = 192
    page_concurrency: Annotated[int, "Concurrent page requests (1–3 per process)."] = 3

    def __init__(self, config=None):
        super().__init__(config)
        self.policy = alignment_policy(config)

    def __call__(self, provider, extraction_service, *, layout_service=None):
        if layout_service is None:
            from doclayout.models import create_layout_service

            layout_service = create_layout_service()
        if not 1 <= self.page_concurrency <= 3 or self.highres_image_dpi <= 0:
            raise ValueError("page_concurrency must be 1–3 and rendering DPI positive")
        pages = []
        ids = list(provider.page_range)
        rendered_images = []
        try:
            with ThreadPoolExecutor(max_workers=self.page_concurrency) as executor:
                for start in range(0, len(ids), self.page_concurrency):
                    batch = []
                    # PDFium is never called from executor threads.
                    for page_id in ids[start : start + self.page_concurrency]:
                        image = provider.get_images([page_id], self.highres_image_dpi)[
                            0
                        ]
                        rendered_images.append(image)
                        started = perf_counter()
                        layout_error = None
                        try:
                            layout = layout_service.predict(image)
                        except LAYOUT_RUNTIME_ERRORS as exc:
                            layout_error = exc
                        except LayoutError:
                            raise
                        except Exception:  # noqa: BLE001 - isolate optional native inference failures
                            layout_error = LayoutInferenceError(
                                "Layout inference failed."
                            )
                        if layout_error is not None:
                            logger.warning("%s", layout_fallback_message(layout_error))
                            layout = LayoutResult(
                                model_id=MODEL_ID,
                                revision=MODEL_REVISION,
                                actual_device="unavailable",
                                provider="unavailable",
                                elapsed_seconds=perf_counter() - started,
                                image_size=image.size,
                                regions=(),
                                fallback_reason=layout_fallback_message(layout_error),
                                error_code=type(layout_error).__name__,
                            )
                            prompt = PAGE_PROMPT
                        else:
                            prompt = PAGE_PROMPT + given_layout(layout, image.size)
                        page_class = cast(
                            type[PageGroup], get_block_class(BlockTypes.Page)
                        )
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
                                layout,
                                executor.submit(
                                    extraction_service,
                                    prompt,
                                    image,
                                    page,
                                    ExtractedPage,
                                ),
                            )
                        )
                    for page, layout, future in batch:
                        result = ExtractedPage.model_validate(future.result())
                        aligned = align_blocks(
                            result.blocks,
                            layout,
                            policy=None if layout.error_code else self.policy,
                        )
                        sources = []
                        for item, source_index in zip(
                            aligned.blocks, aligned.source_indices, strict=True
                        ):
                            block = page.add_block(
                                get_block_class(BlockTypes[item.block_type]),
                                PolygonBox.from_bbox(item.bbox).rescale(
                                    (1000, 1000), page.polygon.size
                                ),
                            )
                            setattr(block, "html", item.html)  # noqa: B010 - heterogeneous registry classes
                            block.text_extraction_method = "openai"
                            page.add_structure(block)
                            assert block.block_id is not None
                            sources.append(
                                SourceBinding(
                                    str(block.id),
                                    block.block_id,
                                    source_index,
                                    tuple(
                                        (point[0], point[1])
                                        for point in block.polygon.polygon
                                    ),
                                )
                            )
                        page.layout = PageLayout(
                            aligned,
                            tuple(sources),
                            tuple(
                                (point[0], point[1]) for point in page.polygon.polygon
                            ),
                        )
                        pages.append(page)
        except BaseException:
            # Executor exit waits for users of the images before closing them.
            for image in rendered_images:
                image.close()
            raise
        document_class = cast(type[Document], get_block_class(BlockTypes.Document))
        return document_class(filepath=provider.filepath, pages=pages)
