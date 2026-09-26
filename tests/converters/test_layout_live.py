"""Opt-in synthetic smoke checks, not alignment calibration or accuracy benchmarks."""

import json
import subprocess
import sys
from dataclasses import asdict

import pytest
from PIL import Image, ImageDraw, ImageFont

from doclayout.converters.pdf import PdfConverter
from doclayout.models import create_model_dict, shutdown_models
from doclayout.renderers.chunk import ChunkRenderer
from doclayout.renderers.json import JSONRenderer
from doclayout.renderers.markdown import MarkdownRenderer
from doclayout.renderers.ocr_json import OCRJSONRenderer
from doclayout.schema.layout import source_blocks
from doclayout.services.layout import CPU_PROVIDER, CUDA_PROVIDER, LayoutService
from doclayout.ui.exports import annotations


@pytest.fixture
def synthetic_page(tmp_path):
    if sys.platform != "win32":
        pytest.skip("Native Windows smoke fixture uses the installed Arial font")
    image = Image.new("RGB", (1224, 1584), "white")
    draw = ImageDraw.Draw(image)
    title = ImageFont.truetype("arial.ttf", 44)
    body = ImageFont.truetype("arial.ttf", 24)
    draw.text((100, 100), "Amberstone field report", font=title, fill="black")
    draw.multiline_text(
        (100, 260),
        "Birchgate orchard\n\nThe team counted twenty apples.\n"
        "The fruit was packed in wooden\nboxes and stored in a cool room.\n"
        "Every box carries a blue label.\nDelivery is planned for Monday.",
        font=body,
        fill="black",
        spacing=15,
    )
    draw.multiline_text(
        (670, 260),
        "Cedarvale garden\n\nThe team planted twelve trees.\n"
        "Each tree received fresh water\nand a small protective fence.\n"
        "The next inspection is Friday.\nAll records are kept on paper.",
        font=body,
        fill="black",
        spacing=15,
    )
    draw.line((100, 1100, 1100, 1100), fill="black", width=3)
    for x, top in [(200, 950), (450, 850), (700, 730)]:
        draw.rectangle((x, top, x + 140, 1100), fill="steelblue")
    path = tmp_path / "synthetic-layout.pdf"
    image.save(path, "PDF", resolution=192)
    yield path, image
    image.close()


@pytest.mark.integration
def test_live_cpu_conversion(synthetic_page, tmp_path, monkeypatch):
    path, _ = synthetic_page
    models = create_model_dict()
    models["layout_service"] = LayoutService("cpu")
    predict = models["layout_service"].predict

    def record_layout(image):
        result = predict(image)
        (tmp_path / "layout.json").write_text(
            json.dumps(asdict(result), indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "cpu_provider": result.provider,
                    "layout_seconds": result.elapsed_seconds,
                    "regions": len(result.regions),
                }
            )
        )
        return result

    monkeypatch.setattr(models["layout_service"], "predict", record_layout)
    # Existing synthetic contract values, deliberately not production defaults.
    config = {
        "page_range": [0],
        "use_llm": False,
        "max_retries": 0,
        "keep_pageheader_in_output": True,
        "keep_pagefooter_in_output": True,
        "alignment_policy": {
            "min_iou": 0.6,
            "min_score": 0.5,
            "min_containment": 0.8,
            "min_area_ratio": 0.25,
            "max_center_distance": 0.4,
        },
    }
    try:
        ready = models["layout_service"].prepare()
        document = PdfConverter(models, config=config).build_document(str(path))
        markdown = MarkdownRenderer(config)(document)
        outputs = [
            JSONRenderer(config)(document),
            ChunkRenderer(config)(document),
            OCRJSONRenderer(config)(document),
        ]
        metadata = markdown.metadata["layout"][0]
        print(
            json.dumps(
                {
                    "cpu_preparation": asdict(ready),
                    "counts": metadata["counts"],
                    "inference_seconds": metadata["model"]["elapsed_seconds"],
                }
            )
        )
        (tmp_path / "result.md").write_text(markdown.markdown, encoding="utf-8")
        (tmp_path / "metadata.json").write_text(
            json.dumps(markdown.metadata, indent=2), encoding="utf-8"
        )
        assert metadata["model"]["provider"] == CPU_PROVIDER
        assert all(output.metadata["layout"][0] == metadata for output in outputs)
        for word in ("Amberstone", "Birchgate", "Cedarvale"):
            assert markdown.markdown.count(word) == 1
        assert metadata["counts"]["matched"] > 0
        page = document.pages[0]
        assert page.layout is not None
        leaves = {str(block.id): block for block in source_blocks(page)}
        drawn = annotations(document, config)
        (tmp_path / "annotated.pdf").write_bytes(drawn["pdf"])
        drawn["pages"][1].save(tmp_path / "annotated.png")
        for source in page.layout.sources:
            match = page.layout.alignment.sol[source.sol_index]
            if match.status != "matched":
                continue
            leaf = leaves[source.id]
            region = next(
                r
                for r in page.layout.alignment.layout.regions
                if r.order_index == match.region_order
            )
            box = leaf.polygon.rescale(
                page.polygon.size, page.layout.alignment.layout.image_size
            ).bbox
            assert box == pytest.approx(region.bbox)
            x, y = int(box[0]), int(box[1])
            assert drawn["pages"][1].getpixel((x, y)) == (220, 30, 30)
    finally:
        shutdown_models(models)


@pytest.mark.integration
def test_live_gpu_layout(synthetic_page):
    # This test exercises local layout only; no second billable Sol call.
    # Probe in a child: preloading here would mask the service's own DLL loading.
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import ctypes, os, sys
from pathlib import Path
handles = []
for name in ('cudart64_13.dll', 'cublasLt64_13.dll', 'cublas64_13.dll', 'cudnn64_9.dll'):
    paths = (Path(d) / name for d in os.environ.get('PATH', '').split(os.pathsep) if d)
    path = next((p for p in paths if p.is_file()), None)
    try:
        if path is None:
            raise FileNotFoundError()
        handles.append(ctypes.WinDLL(str(path)))
    except OSError as exc:
        print(f'GPU unavailable: {name}, {type(exc).__name__}')
        sys.exit(1)
count = ctypes.c_int()
code = handles[0].cudaGetDeviceCount(ctypes.byref(count))
if code != 0 or count.value < 1:
    print(f'GPU unavailable: cudaGetDeviceCount status {code}, devices {count.value}')
    sys.exit(1)
""",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if probe.returncode:
        pytest.skip(probe.stdout.strip() or "GPU preflight process failed")
    _, image = synthetic_page
    service = LayoutService("auto")
    ready = service.prepare()
    result = service.predict(image)
    print(
        json.dumps(
            {
                "gpu_preparation": asdict(ready),
                "provider": result.provider,
                "device": result.actual_device,
                "inference_seconds": result.elapsed_seconds,
                "regions": len(result.regions),
                "fallback_reason": result.fallback_reason,
            }
        )
    )
    assert result.provider in (CPU_PROVIDER, CUDA_PROVIDER)
    assert result.regions
    if result.provider == CPU_PROVIDER:
        assert result.fallback_reason
