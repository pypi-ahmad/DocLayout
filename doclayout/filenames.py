"""Shared names for CLI exports and browser downloads."""

import re
from datetime import datetime, timezone
from pathlib import PurePosixPath, PureWindowsPath


def source_stem(source):
    stem = PureWindowsPath(str(source)).stem
    stem = re.sub(r"[^\w.-]", "_", stem).strip(" .") or "document"
    # Leave room for timestamps, crop identifiers, and extensions on Windows.
    return stem[:140]


def export_basename(source):
    return f"{source_stem(source)}_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}"


def export_filename(base, name):
    if base is None:
        return name
    path = PurePosixPath(name)
    suffix = "" if path.stem == "document" else f"_{path.stem}"
    return str(path.with_name(f"{base}{suffix}{path.suffix}"))


def rename_images(text, images, base):
    renamed = {}
    for name, image in images.items():
        new = export_filename(base, name)
        # Update generated Markdown destinations and HTML src attributes only.
        text = text.replace(f"]({name})", f"]({new})")
        for quote in ('"', "'"):
            text = text.replace(f"src={quote}{name}{quote}", f"src={quote}{new}{quote}")
        renamed[new] = image
    return text, renamed


def name_result(result, base):
    result["export_base"] = base
    result["markdown"], result["images"] = rename_images(
        result["markdown"], result["images"], base
    )
