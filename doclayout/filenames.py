"""Shared names for CLI exports and browser downloads."""

import re
from datetime import datetime, timezone
from pathlib import PurePosixPath, PureWindowsPath


def source_stem(source):
    """Return a bounded, Windows-safe stem for a source filename."""
    stem = PureWindowsPath(str(source)).stem
    stem = re.sub(r"[^\w.-]", "_", stem).strip(" .") or "document"
    # Leave room for timestamps, crop identifiers, and extensions on Windows.
    return stem[:140]


def export_basename(source):
    """Append a UTC timestamp to the sanitized source stem."""
    return f"{source_stem(source)}_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}"


def export_filename(base, name):
    """Apply an export basename while retaining subdirectories and suffixes."""
    if base is None:
        return name
    path = PurePosixPath(name)
    suffix = "" if path.stem == "document" else f"_{path.stem}"
    return str(path.with_name(f"{base}{suffix}{path.suffix}"))


def rename_images(text, images, base):
    """Rename image keys and generated Markdown or HTML references."""
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
    """Apply an export basename and image renames to a mutable result."""
    result["export_base"] = base
    result["markdown"], result["images"] = rename_images(
        result["markdown"], result["images"], base
    )
