# Modified for DocLayout; see NOTICE for a summary of changes.
from typing import Annotated, List

from pdftext.schema import Reference
from PIL import Image

from doclayout.providers import BaseProvider
from doclayout.schema.polygon import PolygonBox
from doclayout.security import check_file, check_pixels


class ImageProvider(BaseProvider):
    page_range: Annotated[
        List[int],
        "The range of pages to process.",
        "Default is None, which will process all pages.",
    ] = None

    image_count: int = 1

    def __init__(self, filepath: str, config=None):
        super().__init__(filepath, config)

        check_file(filepath)
        self.images = []
        image = Image.open(filepath)
        try:
            check_pixels(*image.size, source=True)
            if self.page_range is not None and list(self.page_range) != [0]:
                raise ValueError("Image page_range must be [0].")
            self.images.append(image)
        except BaseException:
            image.close()
            raise

        if self.page_range is None:
            self.page_range = range(self.image_count)

        self.page_bboxes = {
            i: [0, 0, self.images[i].size[0], self.images[i].size[1]]
            for i in self.page_range
        }

    def __len__(self):
        return self.image_count

    def get_images(self, idxs: List[int], dpi: int) -> List[Image.Image]:
        # Treat the native image as 96 dpi - higher dpi requests (OCR) get an
        # upscaled copy so small images stay legible for the model
        scale = dpi / 96
        for i in idxs:
            check_pixels(
                self.images[i].width * max(scale, 1),
                self.images[i].height * max(scale, 1),
            )
        if scale <= 1:
            return [self.images[i].copy() for i in idxs]
        return [
            self.images[i].resize(
                (
                    int(self.images[i].size[0] * scale),
                    int(self.images[i].size[1] * scale),
                ),
                Image.LANCZOS,
            )
            for i in idxs
        ]

    def get_page_bbox(self, idx: int) -> PolygonBox | None:
        bbox = self.page_bboxes[idx]
        if bbox:
            return PolygonBox.from_bbox(bbox)

    def get_page_refs(self, idx: int) -> List[Reference]:
        return []

    def close(self):
        for image in self.images:
            image.close()
        self.images.clear()
