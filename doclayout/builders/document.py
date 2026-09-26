# Modified for DocLayout; see NOTICE for a summary of changes.
"""Render serially, then extract at most three pages concurrently."""

import logging
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from typing import Annotated, cast

from doclayout import layout
from doclayout.builders import BaseBuilder
from doclayout.schema import BlockTypes
from doclayout.schema.document import Document
from doclayout.schema.extraction import PAGE_PROMPT, ExtractedPage
from doclayout.schema.groups.page import PageGroup
from doclayout.schema.layout import (
    LayoutAudit,
    PageLayoutRuntime,
    PageRegions,
    SourceRegion,
)
from doclayout.schema.polygon import PolygonBox
from doclayout.schema.registry import get_block_class


class DocumentBuilder(BaseBuilder):
    highres_image_dpi: Annotated[int, "Page extraction rendering DPI."] = 192
    page_concurrency: Annotated[int, "Concurrent page requests (1–3 per process)."] = 3

    def __call__(self, provider, extraction_service, layout_engine=None):
        if not 1 <= self.page_concurrency <= 3 or self.highres_image_dpi <= 0:
            raise ValueError("page_concurrency must be 1–3 and rendering DPI positive")
        pages = []
        ids = list(provider.page_range)
        rendered_images = []
        engine = layout_engine or layout.get_layout_engine()
        audit = LayoutAudit(
            manifest=layout.pipeline_manifest(
                {"highres_image_dpi": self.highres_image_dpi}
            )
        )

        def extract(image, page):
            started = perf_counter()
            try:
                analysis = engine.analyze(image)
            except Exception:  # noqa: BLE001 - V3 alone is optional; Sol errors still propagate
                analysis = layout.sol_fallback_analysis(
                    image, "inference", (perf_counter() - started) * 1000
                )
            prompt = (
                layout.extraction_prompt(PAGE_PROMPT, analysis)
                if analysis.status == "available"
                else PAGE_PROMPT
            )
            if analysis.status == "sol_fallback":
                logging.getLogger(__name__).warning(
                    "V3 unavailable on page %s; using Sol content, geometry and order.",
                    page.page_id,
                )
            result = extraction_service(prompt, image, page, ExtractedPage)
            return result, analysis

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
                                executor.submit(
                                    extract,
                                    image,
                                    page,
                                ),
                            )
                        )
                    for page, future in batch:
                        response, analysis = future.result()
                        assert page.page_id is not None
                        regions = PageRegions(
                            page_id=page.page_id,
                            image_size=analysis.image_size,
                            provider=analysis.provider,
                            candidate_count=analysis.candidate_count,
                            filtered_count=analysis.filtered_count,
                            regions=analysis.regions,
                            warnings=analysis.warnings,
                        )
                        result = ExtractedPage.model_validate(response)
                        boxes, provenance, order = layout.reconcile(
                            result, regions, page.polygon.bbox
                        )
                        audit.pages.append(regions)
                        matched = sum(p.status == "matched" for p in provenance)
                        if analysis.status == "sol_fallback":
                            for record in provenance:
                                record.issues.append("layout_unavailable")
                        audit.page_runtime[page.page_id] = PageLayoutRuntime(
                            model_id=analysis.model_id,
                            model_revision=analysis.model_revision,
                            actual_device=analysis.actual_device,
                            provider=analysis.provider,
                            elapsed_ms=analysis.elapsed_ms,
                            status=analysis.status,
                            failure_stage=analysis.failure_stage,
                            order_key_source=analysis.order_key_source,
                            observed_rank_source=analysis.observed_rank_source,
                            retained_region_count=len(regions.regions),
                            prior_region_count=sum(r.eligible for r in regions.regions),
                            matched_count=matched,
                            sol_only_count=len(provenance) - matched,
                            unmatched_v3_count=len(regions.regions) - matched,
                        )
                        for ordinal, item in enumerate(result.blocks):
                            block = page.add_block(
                                get_block_class(BlockTypes[item.block_type]),
                                PolygonBox.from_bbox(boxes[ordinal]),
                            )
                            setattr(block, "html", item.html)  # noqa: B010 - concrete subclasses own html
                            block.text_extraction_method = "openai"
                            block.layout = provenance[ordinal]
                            block.layout.sources = [
                                SourceRegion(
                                    block_id=str(block.id),
                                    page_id=regions.page_id,
                                    bbox=block.polygon.bbox.copy(),
                                    region_row=block.layout.region_row,
                                )
                            ]
                            page.add_structure(block)
                        assert page.children is not None
                        page.structure = [page.children[index].id for index in order]
                        pages.append(page)
        except BaseException:
            # Executor exit waits for users of the images before closing them.
            for image in rendered_images:
                image.close()
            raise
        document_class = cast(type[Document], get_block_class(BlockTypes.Document))
        return document_class(filepath=provider.filepath, pages=pages, layout=audit)
