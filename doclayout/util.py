# Modified for DocLayout; see NOTICE for a summary of changes.
import inspect
import os
import re
from importlib import import_module
from typing import Annotated, List

import numpy as np
import requests
from pydantic import BaseModel

from doclayout.settings import settings


def strings_to_classes(items: List[str]) -> List[type]:
    classes = []
    for item in items:
        module_name, class_name = item.rsplit(".", 1)
        module = import_module(module_name)
        classes.append(getattr(module, class_name))
    return classes


def classes_to_strings(items: List[type]) -> List[str]:
    for item in items:
        if not inspect.isclass(item):
            raise ValueError(f"Item {item} is not a class")

    return [f"{item.__module__}.{item.__name__}" for item in items]


def verify_config_keys(obj):
    annotations = inspect.get_annotations(obj.__class__)

    none_vals = ""
    for attr_name, annotation in annotations.items():
        if isinstance(annotation, type(Annotated[str, ""])):
            value = getattr(obj, attr_name)
            if value is None:
                none_vals += f"{attr_name}, "

    assert len(none_vals) == 0, (
        f"In order to use {obj.__class__.__name__}, you must set the configuration values `{none_vals}`."
    )


def assign_config(cls, config: BaseModel | dict | None):
    cls_name = cls.__class__.__name__
    if config is None:
        return
    elif isinstance(config, BaseModel):
        dict_config = config.dict()
    elif isinstance(config, dict):
        dict_config = config
    else:
        raise ValueError("config must be a dict or a pydantic BaseModel")

    for k in dict_config:
        if hasattr(cls, k):
            setattr(cls, k, dict_config[k])
    for k in dict_config:
        if cls_name not in k:
            continue
        # Enables using class-specific keys, like "MarkdownRenderer_remove_blocks"
        split_k = k.removeprefix(cls_name + "_")

        if hasattr(cls, split_k):
            setattr(cls, split_k, dict_config[k])


def parse_range_str(range_str: str) -> List[int]:
    from doclayout.security import DocumentLimitError

    if not isinstance(range_str, str) or not range_str or len(range_str) > 4096:
        raise ValueError("Invalid page range.")
    pages = set()
    for part in range_str.split(","):
        match = re.fullmatch(r"\s*([0-9]{1,9})(?:-([0-9]{1,9}))?\s*", part)
        if match is None:
            raise ValueError("Invalid page range.")
        start = int(match[1])
        end = int(match[2]) if match[2] is not None else start
        if end < start:
            raise ValueError("Invalid page range.")
        if end - start + 1 > settings.DOCLAYOUT_MAX_PAGES:
            raise DocumentLimitError("Too many selected pages.")
        pages.update(range(start, end + 1))
        if len(pages) > settings.DOCLAYOUT_MAX_PAGES:
            raise DocumentLimitError("Too many selected pages.")
    return sorted(pages)


def matrix_intersection_area(
    boxes1: List[List[float]], boxes2: List[List[float]]
) -> np.ndarray:
    if len(boxes1) == 0 or len(boxes2) == 0:
        return np.zeros((len(boxes1), len(boxes2)))

    boxes1 = np.array(boxes1)
    boxes2 = np.array(boxes2)

    boxes1 = boxes1[:, np.newaxis, :]  # Shape: (N, 1, 4)
    boxes2 = boxes2[np.newaxis, :, :]  # Shape: (1, M, 4)

    min_x = np.maximum(boxes1[..., 0], boxes2[..., 0])  # Shape: (N, M)
    min_y = np.maximum(boxes1[..., 1], boxes2[..., 1])
    max_x = np.minimum(boxes1[..., 2], boxes2[..., 2])
    max_y = np.minimum(boxes1[..., 3], boxes2[..., 3])

    width = np.maximum(0, max_x - min_x)
    height = np.maximum(0, max_y - min_y)

    return width * height  # Shape: (N, M)


def download_font():
    if not os.path.exists(settings.FONT_PATH):
        import tempfile
        import time

        from doclayout.security import DocumentLimitError, MIB

        os.makedirs(os.path.dirname(settings.FONT_PATH), exist_ok=True)
        font_dl_path = f"{settings.ARTIFACT_URL}/{settings.FONT_NAME}"
        temp_path = None
        deadline = time.monotonic() + 60
        try:
            with requests.get(font_dl_path, stream=True, timeout=(5, 10)) as r:
                r.raise_for_status()
                with tempfile.NamedTemporaryFile(
                    dir=os.path.dirname(settings.FONT_PATH), delete=False
                ) as f:
                    temp_path = f.name
                    size = 0
                    for chunk in r.iter_content(chunk_size=8192):
                        size += len(chunk)
                        if size > settings.DOCLAYOUT_MAX_RESOURCE_MIB * MIB:
                            raise DocumentLimitError("Font exceeds the size limit.")
                        if time.monotonic() > deadline:
                            raise TimeoutError("Font download timed out.")
                        f.write(chunk)
            os.replace(temp_path, settings.FONT_PATH)
        finally:
            if temp_path is not None and os.path.exists(temp_path):
                os.unlink(temp_path)


# Modification of unwrap_math from surya.recognition
MATH_SYMBOLS = ["^", "_", "\\", "{", "}"]
MATH_TAG_PATTERN = re.compile(r"<math\b[^>]*>.*?</math>", re.DOTALL)
LATEX_ESCAPES = {
    r"\%": "%",
    r"\$": "$",
    r"\_": "_",
    r"\&": "&",
    r"\#": "#",
    r"\‰": "‰",
}


def normalize_latex_escapes(s: str) -> str:
    for k, v in LATEX_ESCAPES.items():
        s = s.replace(k, v)
    return s


def unwrap_math(text: str, math_symbols: List[str] = MATH_SYMBOLS) -> str:
    """Unwrap a single <math>...</math> block if it's not really math."""
    if MATH_TAG_PATTERN.match(text):
        # Remove tags
        inner = re.sub(r"^\s*<math\b[^>]*>|</math>\s*$", "", text, flags=re.DOTALL)

        # Strip a single leading/trailing \\ plus surrounding whitespace
        inner_stripped = re.sub(r"^\s*\\\\\s*|\s*\\\\\s*$", "", inner)

        # Unwrap \text{...}
        unwrapped = re.sub(r"\\text[a-zA-Z]*\s*\{(.*?)\}", r"\1", inner_stripped)

        # Normalize escapes
        normalized = normalize_latex_escapes(unwrapped)

        # If no math symbols remain → unwrap fully
        if not any(symb in normalized for symb in math_symbols):
            return normalized.strip()

    # Otherwise, return as-is
    return text
