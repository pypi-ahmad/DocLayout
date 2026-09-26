"""Pinned PP-DocLayoutV3 inference and conservative Sol reconciliation."""

import atexit
import hashlib
import json
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from threading import Lock, RLock
from time import perf_counter
from uuid import uuid4

import numpy as np

from doclayout.schema.layout import (
    BlockLayout,
    LayoutAnalysis,
    LayoutRegion,
    PageRegions,
)
from doclayout.settings import settings

PIPELINE = "sol-layout-v3/v2"
PRIOR_VERSION = 1
EXECUTION_POLICY = "onnx-cuda-scatternd-cpu/v1"
FALLBACK_POLICY = "sol-on-layout-failure/v1"
REPO = "PaddlePaddle/PP-DocLayoutV3_onnx"
REVISION = "46bbdf188bb0a772c08aed74882ce7e51a8f1ea6"
HASHES = {
    "inference.onnx": "45bf71750b00739a41fc209f132eb104a4d6b5bb29483c9078164d8b87cf28ba",
    "inference.yml": "506fcfac13b3b546ae40d7886b44126420f392adb694e3f8bb6a6286a1f90fdc",
}
LABELS = (
    "abstract",
    "algorithm",
    "aside_text",
    "chart",
    "content",
    "display_formula",
    "doc_title",
    "figure_title",
    "footer",
    "footer_image",
    "footnote",
    "formula_number",
    "header",
    "header_image",
    "image",
    "inline_formula",
    "number",
    "paragraph_title",
    "reference",
    "reference_content",
    "seal",
    "table",
    "text",
    "vertical_text",
    "vision_footnote",
)
MAPPING = (
    "Text",
    None,
    "Text",
    "Figure",
    "TableOfContents",
    "Equation",
    "SectionHeader",
    "Caption",
    "PageFooter",
    "Picture",
    "Footnote",
    None,
    "PageHeader",
    "Picture",
    "Picture",
    None,
    None,
    "SectionHeader",
    None,
    "Bibliography",
    "Picture",
    "Table",
    "Text",
    "Text",
    None,
)
# Provisional matching policy, not calibrated accuracy/confidence guarantees.
SCORE = 0.5
IOU = 0.5
MARGIN = 0.10
CONTAINMENT = 0.8
EPSILON = 1e-6
OUTPUTS = ["fetch_name_0", "fetch_name_1", "fetch_name_2"]


class LayoutModelUnavailable(RuntimeError):
    """The layout engine could not run; conversion records explicit Sol fallback."""


# Existing conversion boundaries continue to catch the same exception type.
LayoutUnavailableError = LayoutModelUnavailable


def sol_fallback_analysis(image, stage, elapsed_ms=0):
    """Record unavailable layout without fabricated detections or device data.

    Args:
        image (PIL.Image.Image): Borrowed whole-page image; only its size is read.
        stage (str): Failure boundary, preparation or inference.
        elapsed_ms (float): Measured failed analysis time; zero when unmeasured.

    Returns:
        LayoutAnalysis: Explicit sol_fallback status, no regions, and null device
        and order sources. The model ID identifies the attempted backend.
    """
    return LayoutAnalysis(
        image_size=image.size,
        model_id=REPO,
        model_revision=REVISION,
        actual_device=None,
        provider="unavailable",
        elapsed_ms=elapsed_ms,
        candidate_count=0,
        filtered_count=0,
        regions=[],
        status="sol_fallback",
        failure_stage=stage,
        order_key_source=None,
        observed_rank_source=None,
        warnings=[f"V3 {stage} failed; using Sol content, geometry and order."],
    )


class SolFallbackEngine:
    """Conversion-local fallback after failed preparation; no repeated probes."""

    actual_device = None
    status = "Sol fallback · V3 unavailable"

    def prepare(self):
        """Already prepared for Sol-only operation; do not retry the failed engine."""

    def retry_failed(self):
        """Keep this conversion-local fallback; only the original engine can retry."""

    def analyze(self, image):
        """Return explicit preparation-failure provenance for the borrowed image."""
        return sol_fallback_analysis(image, "preparation")


def prepare_for_conversion(engine):
    """Prepare V3 or return a conversion-local Sol fallback engine.

    Args:
        engine (LayoutEngine): Cached or injected engine exposing prepare().

    Returns:
        LayoutEngine | SolFallbackEngine: The ready input engine, or a no-probe
        fallback after any preparation exception. Sol errors are outside this
        boundary and retain their normal failure behavior.
    """
    try:
        engine.prepare()
    except Exception:  # noqa: BLE001 - only the optional layout boundary; never expose backend text
        return SolFallbackEngine()
    return engine


def _dependency(name):
    """Import a runtime dependency without exposing native loader details."""
    try:
        return import_module(name)
    except (ImportError, OSError):
        raise LayoutModelUnavailable(
            f"Layout dependency {name!r} is unavailable. Run uv sync for this "
            "checkout and check the package's native runtime requirements."
        ) from None


def check_runtime_dependencies():
    """Check all required imports before attempting any model download."""
    for name in ("onnxruntime", "cv2", "huggingface_hub", "yaml"):
        _dependency(name)


def extraction_prompt(prompt: str, analysis: LayoutAnalysis) -> str:
    """Append rectangular layout hints without changing the response schema.

    Args:
        prompt: Packaged whole-page transcription instructions.
        analysis: Validated detections in rendered-image pixels.

    Returns:
        str: Instructions followed by compact, versioned layout data. Raw masks
        stay local; normalized coordinates are only a request representation.
    """
    width, height = analysis.image_size
    regions = [
        {
            "row": region.row,
            "class_id": region.class_id,
            "label": region.label,
            "score": region.score,
            "bbox": [
                value * 1000 / (width if index % 2 == 0 else height)
                for index, value in enumerate(region.bbox_px)
            ],
            "order_key": region.order_key,
            "block_type_hint": MAPPING[region.class_id],
        }
        for region in sorted(analysis.regions, key=lambda r: (r.order_key, r.row))
        if region.eligible
    ]
    prior = {
        "given_layout": {
            "version": PRIOR_VERSION,
            "coordinate_space": "full_page_normalized_0_1000",
            "geometry_type": "rectangle",
            "regions": regions,
        }
    }
    return (
        prompt.rstrip()
        + "\n\n"
        + json.dumps(prior, separators=(",", ":"), allow_nan=False)
    )


def pipeline_manifest(config=None):
    """Fingerprint semantics without loading weights or contacting the Hub.

    Args:
        config (dict | None): Effective converter settings.

    Returns:
        dict: Public provenance, excluding raw configuration or credentials.
    """
    from doclayout.schema.extraction import PAGE_PROMPT, ExtractedPage
    from doclayout.services.openai import SYSTEM_PROMPT

    def digest(value):
        return hashlib.sha256(value.encode()).hexdigest()

    packages = {}
    for name in ("onnxruntime-gpu", "onnxruntime", "numpy", "opencv-python-headless"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            pass
    manifest = {
        "pipeline": PIPELINE,
        "execution_policy": EXECUTION_POLICY,
        "fallback_policy": FALLBACK_POLICY,
        "given_layout_version": PRIOR_VERSION,
        "artifact": {"repo": REPO, "revision": REVISION, "sha256": HASHES},
        "mapping": dict(enumerate(MAPPING)),
        "thresholds": {
            "score_gt": SCORE,
            "iou_ge": IOU,
            "margin_ge": MARGIN,
            "containment_ge": CONTAINMENT,
            "tie_tolerance": EPSILON,
        },
        "packages": packages,
        "device_policy": settings.DOCLAYOUT_LAYOUT_DEVICE,
        "render_dpi": (config or {}).get("highres_image_dpi", 192),
        "prompts": {"page": digest(PAGE_PROMPT), "system": digest(SYSTEM_PROMPT)},
        "schema": digest(json.dumps(ExtractedPage.model_json_schema(), sort_keys=True)),
        "config_sha256": digest(json.dumps(config or {}, sort_keys=True, default=str)),
    }
    manifest["fingerprint"] = digest(json.dumps(manifest, sort_keys=True))
    return manifest


def model_files(cache_dir, offline, *, model_dir=None):
    """Resolve and verify the two pinned artifacts, using local files first.

    Args:
        cache_dir (Path): Hub cache under operator control.
        offline (bool): Prohibit network downloads.
        model_dir (Path | None): Exact artifact directory, overriding Hub cache.

    Returns:
        dict[str, Path]: Verified model and YAML paths.
    """
    yaml = _dependency("yaml")
    hub = _dependency("huggingface_hub")
    errors = _dependency("huggingface_hub.errors")

    def verify(path, filename):
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != HASHES[filename]:
            raise LayoutModelUnavailable(
                f"Layout checksum mismatch for {filename}. Repair the pinned cache."
            )

    try:
        paths = {}
        if model_dir is not None:
            if not str(model_dir).strip():
                raise LayoutModelUnavailable(
                    "Layout model directory must not be empty."
                )
            model_dir = Path(model_dir)
            if model_dir.exists() and not model_dir.is_dir():
                raise LayoutModelUnavailable(
                    "Layout model directory is not a directory."
                )
            # Verify existing overrides before downloading anything; never overwrite
            # an invalid supplied artifact or treat an incomplete directory as ready.
            for filename in HASHES:
                path = model_dir / filename
                if path.exists():
                    verify(path, filename)
                    paths[filename] = path
        for filename in HASHES:
            if filename in paths:
                continue
            if model_dir is not None:
                if offline:
                    raise LayoutModelUnavailable(
                        "Layout files missing offline. Populate the pinned model directory first."
                    )
                path = hub.hf_hub_download(
                    repo_id=REPO,
                    filename=filename,
                    revision=REVISION,
                    local_dir=model_dir,
                )
            else:
                try:
                    path = hub.hf_hub_download(
                        repo_id=REPO,
                        filename=filename,
                        revision=REVISION,
                        cache_dir=cache_dir,
                        local_files_only=True,
                    )
                except errors.LocalEntryNotFoundError:
                    if offline:
                        raise LayoutModelUnavailable(
                            "Layout files missing offline. Populate the pinned layout cache first."
                        ) from None
                    path = hub.hf_hub_download(
                        repo_id=REPO,
                        filename=filename,
                        revision=REVISION,
                        cache_dir=cache_dir,
                    )
            path = Path(path)
            verify(path, filename)
            paths[filename] = path
        config = yaml.safe_load(paths["inference.yml"].read_text(encoding="utf-8"))
        if not isinstance(config, dict) or config.get("label_list") != list(LABELS):
            raise LayoutModelUnavailable("Layout label contract changed.")
        return paths
    except LayoutModelUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - sanitize download/filesystem/parser errors
        raise LayoutModelUnavailable(
            f"Layout artifact preparation failed ({type(exc).__name__}). "
            "Check pinned files, directory permissions and network/offline settings."
        ) from None


def image_inputs(image):
    """Build a private RGB float32 tensor without changing the borrowed image."""
    import cv2

    width, height = image.size
    pixels = np.asarray(image.convert("RGB"))
    resized = cv2.resize(pixels, (800, 800), interpolation=cv2.INTER_CUBIC)
    return {
        "image": np.ascontiguousarray(
            resized.transpose(2, 0, 1)[None], dtype=np.float32
        )
        / 255,
        "im_shape": np.array([[800, 800]], dtype=np.float32),
        "scale_factor": np.array([[800 / height, 800 / width]], dtype=np.float32),
    }


def mask_rle(mask):
    """Encode a binary mask as zero-first, row-major run lengths."""
    flat = mask.reshape(-1)
    edges = np.flatnonzero(flat[1:] != flat[:-1]) + 1
    counts = np.diff(np.r_[0, edges, flat.size]).tolist()
    return ([0] if flat[0] else []) + counts


def decode_outputs(outputs, image_size, page_id, provider):
    """Validate tensors and retain confidence-filtered boxes and masks.

    Raises:
        LayoutUnavailableError: The pinned output contract is violated.
    """
    regions, count, filtered = _decode_regions(outputs, image_size)
    return PageRegions(
        page_id=page_id,
        image_size=image_size,
        provider=provider,
        candidate_count=count,
        filtered_count=filtered,
        regions=regions,
    )


def _decode_regions(outputs, image_size):
    if not isinstance(outputs, (list, tuple)) or len(outputs) != len(OUTPUTS):
        raise LayoutModelUnavailable("Layout output tensor contract changed.")
    boxes, counts, masks = outputs
    if not all(isinstance(value, np.ndarray) for value in outputs):
        raise LayoutModelUnavailable("Layout output tensor contract changed.")
    if (
        boxes.ndim != 2
        or boxes.shape[1] != 7
        or boxes.dtype != np.float32
        or counts.shape != (1,)
        or counts.dtype != np.int32
        or counts[0] != len(boxes)
        or masks.shape != (len(boxes), 200, 200)
        or masks.dtype != np.int32
        or not np.isfinite(boxes).all()
        or not np.isin(masks, [0, 1]).all()
        or np.any(boxes[:, 1] < 0)
        or np.any(boxes[:, 1] > 1)
        or np.any(boxes[:, 0] != np.floor(boxes[:, 0]))
        or np.any(boxes[:, 0] < 0)
        or np.any(boxes[:, 0] >= len(LABELS))
    ):
        raise LayoutUnavailableError("Layout output tensor contract changed.")
    width, height = image_size
    regions = []
    filtered = 0
    for row, box in enumerate(boxes):
        class_id, score, x0, y0, x1, y1, order = box.tolist()
        if score <= SCORE:
            filtered += 1
            continue
        clipped = [
            max(0.0, min(width, x0)),
            max(0.0, min(height, y0)),
            max(0.0, min(width, x1)),
            max(0.0, min(height, y1)),
        ]
        valid = clipped[0] < clipped[2] and clipped[1] < clipped[3]
        regions.append(
            LayoutRegion(
                row=row,
                class_id=int(class_id),
                label=LABELS[int(class_id)],
                score=score,
                raw_bbox_px=[x0, y0, x1, y1],
                bbox_px=clipped,
                order_key=order,
                mask_rle=mask_rle(masks[row]),
                eligible=valid,
                issues=[] if valid else ["degenerate_geometry"],
            )
        )
    for rank, region in enumerate(sorted(regions, key=lambda r: (r.order_key, r.row))):
        region.observed_rank = rank
    return regions, len(boxes), filtered


class LayoutEngine:
    """Lazy, process-shared batch-one inference with exercised CPU fallback."""

    def __init__(self, cache_dir=None, device=None, offline=None, *, model_dir=None):
        """Configure lazy inference without loading native dependencies or weights.

        Args:
            cache_dir (str | Path | None): Writable Hub/health-profile cache.
            device (str | None): auto, cuda, or cpu; defaults to process settings.
            offline (bool | None): Forbid missing-weight downloads when true.
            model_dir (str | Path | None): Exact artifact directory, overriding
                Hub resolution. None uses the configured override, if any.

        Raises:
            ValueError: The requested device policy is unsupported.
        """
        self.cache_dir = Path(cache_dir or settings.DOCLAYOUT_LAYOUT_CACHE_DIR)
        self.device = device or settings.DOCLAYOUT_LAYOUT_DEVICE
        self.offline = settings.DOCLAYOUT_LAYOUT_OFFLINE if offline is None else offline
        self.model_dir = (
            settings.DOCLAYOUT_LAYOUT_MODEL_DIR if model_dir is None else model_dir
        )
        if self.device not in {"auto", "cuda", "cpu"}:
            raise ValueError("DOCLAYOUT_LAYOUT_DEVICE must be auto, cuda or cpu")
        self._lock = RLock()
        self._session = None
        self._paths = None
        self._provider = ""
        self._error = None
        self._warnings = []
        self._status = "Not loaded"

    @property
    def status(self):
        """Return nonblocking, non-sensitive readiness text for the UI thread."""
        return self._status

    @property
    def actual_device(self):
        """Return the exercised device, or None when no session is ready."""
        if self._session is None:
            return None
        return "cuda" if self._provider == "CUDAExecutionProvider" else "cpu"

    def prepare(self) -> None:
        """Exercise the cached provider once, before accepting real conversion.

        The owned synthetic image is not a document page; its detections are
        discarded. The reentrant lock makes preparation and inference atomic
        across callers without duplicating the checked provider-selection path.

        Raises:
            LayoutModelUnavailable: Dependencies, artifacts or execution failed.
                Failure remains latched until an explicit retry.
        """
        from PIL import Image

        with self._lock:
            if self._error:
                raise LayoutModelUnavailable(self._error)
            if self._session is not None:
                return
            probe = Image.new("RGB", (800, 800), "white")
            try:
                self.analyze(probe)
            finally:
                probe.close()

    def retry_failed(self):
        """Allow one new initialization attempt after an explicit user retry."""
        with self._lock:
            if self._error:
                self._error = None
                self._warnings = []
                self._provider = ""
                self._status = "Not loaded"

    def close(self):
        """Release the session after outstanding inference leaves the lock."""
        with self._lock:
            self._session = None
            self._status = "Not loaded"

    def _new_session(self, provider):
        ort = _dependency("onnxruntime")

        assert self._paths is not None
        options = ort.SessionOptions()
        if provider == "CUDAExecutionProvider":
            # ORT 1.30 supports name-based placement without modifying the model.
            # Avoid CUDA ScatterND's undefined competing writes with reduction=none.
            options.add_session_config_entry(
                "session.name_based_layer_assignment", "cpu(ScatterND)"
            )
            options.add_session_config_entry(
                "session.record_ep_graph_assignment_info", "1"
            )
            options.enable_profiling = True
            health = self.cache_dir / "health"
            health.mkdir(parents=True, exist_ok=True)
            options.profile_file_prefix = str(health / uuid4().hex)
        providers = [provider]
        if provider != "CPUExecutionProvider":
            providers.append("CPUExecutionProvider")
        session = ort.InferenceSession(
            str(self._paths["inference.onnx"]),
            sess_options=options,
            providers=providers,
        )
        session.disable_fallback()
        return session

    def _decode_analysis(self, outputs, image_size, provider):
        regions, count, filtered = _decode_regions(outputs, image_size)
        return LayoutAnalysis(
            image_size=image_size,
            model_id=REPO,
            model_revision=REVISION,
            actual_device="cuda" if provider == "CUDAExecutionProvider" else "cpu",
            provider=provider,
            elapsed_ms=0,
            candidate_count=count,
            filtered_count=filtered,
            regions=regions,
        )

    def _exercise(self, inputs, image_size, provider):
        self._status = f"Initializing/testing {provider}"
        try:
            session = self._new_session(provider)
        except LayoutModelUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 - native provider initialization errors
            raise LayoutModelUnavailable(
                f"Layout {provider} initialization failed ({type(exc).__name__}). "
                "Check the ONNX Runtime installation and native libraries."
            ) from None
        try:
            if provider == "CUDAExecutionProvider":
                scatter = [
                    group.ep_name
                    for group in session.get_provider_graph_assignment_info()
                    for node in group.get_nodes()
                    if node.op_type == "ScatterND"
                ]
                # The hash-pinned artifact has one ScatterND. Fail closed if an
                # unsupported/ignored placement option leaves its safety unknown.
                if scatter != ["CPUExecutionProvider"]:
                    raise LayoutModelUnavailable(
                        "Layout ScatterND CPU placement could not be verified."
                    )
            if {x.name for x in session.get_inputs()} != {
                "image",
                "im_shape",
                "scale_factor",
            }:
                raise LayoutModelUnavailable("Layout input tensor contract changed.")
            if [x.name for x in session.get_outputs()] != OUTPUTS:
                raise LayoutModelUnavailable("Layout output names changed.")
            outputs = session.run(OUTPUTS, inputs)
            result = self._decode_analysis(outputs, image_size, provider)
        finally:
            if provider == "CUDAExecutionProvider":
                profile = Path(session.end_profiling())
                try:
                    events = json.loads(profile.read_text(encoding="utf-8"))
                finally:
                    profile.unlink(missing_ok=True)
        if provider == "CUDAExecutionProvider" and not any(
            event.get("cat") == "Node"
            and event.get("name", "").endswith("_kernel_time")
            and event.get("args", {}).get("provider") == provider
            for event in events
        ):
            raise LayoutUnavailableError("CUDA did not execute model kernels.")
        self._session, self._provider = session, provider
        return result

    def infer(self, image, page_id):
        """Run the low-level engine and adapt its result to page-indexed regions.

        Args:
            image (PIL.Image.Image): Borrowed, provider-rendered page.
            page_id (int): Original zero-based source page.

        Returns:
            PageRegions: Validated regions and actual provider provenance.

        Raises:
            LayoutModelUnavailable: Layout cannot run. This low-level method
                does not perform the conversion layer's Sol fallback.
        """
        result = self.analyze(image)
        return PageRegions(
            page_id=page_id,
            image_size=result.image_size,
            provider=result.provider,
            candidate_count=result.candidate_count,
            filtered_count=result.filtered_count,
            regions=result.regions,
            warnings=result.warnings,
        )

    def analyze(self, page_image) -> LayoutAnalysis:
        """Analyze a borrowed page image with one lazy, serialized session.

        Args:
            page_image (PIL.Image.Image): Original page image, never modified or closed.

        Returns:
            LayoutAnalysis: Verified pixel geometry, model order keys and provenance.
                Elapsed milliseconds include lock waiting, preparation and fallback.

        Raises:
            LayoutModelUnavailable: Required dependencies, artifacts or execution failed.
                Explicit cuda never falls back to CPU; auto may fall back once.
        """
        started = perf_counter()
        image = page_image
        with self._lock:
            if self._error:
                raise LayoutUnavailableError(self._error)
            try:
                if self._paths is None:
                    check_runtime_dependencies()
                    self._status = "Checking/downloading pinned layout files"
                    if self.model_dir is not None and not str(self.model_dir).strip():
                        raise LayoutModelUnavailable(
                            "Layout model directory must not be empty."
                        )
                    self._paths = model_files(
                        self.cache_dir, self.offline, model_dir=self.model_dir
                    )
                inputs = image_inputs(image)
                if self._session is not None:
                    result = None
                    try:
                        result = self._decode_analysis(
                            self._session.run(OUTPUTS, inputs),
                            image.size,
                            self._provider,
                        )
                    except Exception as exc:
                        if (
                            self._provider != "CUDAExecutionProvider"
                            or self.device != "auto"
                        ):
                            raise
                        self._warnings.append(
                            f"CUDA runtime fallback: {type(exc).__name__}"
                        )
                        self._session = None
                    # Leave the exception handler before allocating a replacement:
                    # the traceback can otherwise retain the failed native session.
                    if result is None:
                        result = self._exercise(
                            inputs, image.size, "CPUExecutionProvider"
                        )
                else:
                    result = None
                    if self.device in {"auto", "cuda"}:
                        try:
                            result = self._exercise(
                                inputs, image.size, "CUDAExecutionProvider"
                            )
                        except Exception as exc:
                            if self.device == "cuda":
                                raise
                            self._warnings.append(
                                f"CUDA unavailable: {type(exc).__name__}"
                            )
                    if result is None:
                        result = self._exercise(
                            inputs, image.size, "CPUExecutionProvider"
                        )
                result.warnings = list(self._warnings)
                self._status = f"Ready: {self._provider}" + (
                    " (CPU fallback)" if self._warnings else ""
                )
                result.elapsed_ms = (perf_counter() - started) * 1000
                return result
            except Exception as exc:  # noqa: BLE001 - sanitize backend errors at the public boundary
                self._session = None
                self._error = (
                    str(exc)
                    if isinstance(exc, LayoutUnavailableError)
                    else f"Layout inference unavailable ({type(exc).__name__}). Check pinned files and ONNX Runtime installation."
                )
                if self.device == "cuda":
                    self._error += " Explicit cuda requested; CPU fallback is disabled."
                self._status = f"Failed: {self._error}"
                raise LayoutUnavailableError(self._error) from None


_engine = None
_engine_lock = Lock()


def get_layout_engine():
    """Return the single lazy engine for this process; never load at import."""
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = LayoutEngine()
            atexit.register(_engine.close)
        return _engine


def compatible(kind, class_id):
    """Check matching compatibility without relabeling Sol's semantic type."""
    target = MAPPING[class_id]
    visual = {"Picture", "Figure", "Diagram"}
    return target == kind or (target in visual and kind in visual)


def overlap(a, b):
    """Return true rectangle IoU and containment of the smaller rectangle."""
    area_a = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    area_b = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1])
    )
    union = area_a + area_b - intersection
    return (
        intersection / union if union else 0,
        intersection / min(area_a, area_b) if min(area_a, area_b) else 0,
    )


def page_box(box, image_size, bounds):
    """Transform image pixels into the provider's top-left page frame."""
    width, height = image_size
    x0, y0, x1, y1 = bounds
    return [
        x0 + box[0] * (x1 - x0) / width,
        y0 + box[1] * (y1 - y0) / height,
        x0 + box[2] * (x1 - x0) / width,
        y0 + box[3] * (y1 - y0) / height,
    ]


def reconcile(extracted_page, regions, page_bounds):
    """Match validated Sol blocks to V3 without changing their text or types.

    Args:
        extracted_page (ExtractedPage): Sol blocks with normalized 0-to-1000 boxes.
        regions (PageRegions): Image-pixel detections; unmatched regions receive
            diagnostic issues in place.
        page_bounds (list[float]): Provider page rectangle, including its origin.

    Returns:
        tuple[list, list, list]: Page-space rectangles, block provenance, and Sol
        indices in partial reading order. Rejected matches keep Sol boxes and
        anchor order; only contiguous matched runs can follow V3 order keys.
        Ambiguous overlap components remain unsplit and unmerged.
    """
    width, height = regions.image_size
    sol = [
        [
            b.bbox[0] * width / 1000,
            b.bbox[1] * height / 1000,
            b.bbox[2] * width / 1000,
            b.bbox[3] * height / 1000,
        ]
        for b in extracted_page.blocks
    ]
    matrix = np.zeros((len(sol), len(regions.regions)))
    strong = np.zeros_like(matrix, dtype=bool)
    for i, block in enumerate(extracted_page.blocks):
        for j, region in enumerate(regions.regions):
            if region.eligible and compatible(block.block_type, region.class_id):
                matrix[i, j], containment = overlap(sol[i], region.bbox_px)
                strong[i, j] = containment >= CONTAINMENT
    split_rows = set(np.flatnonzero(strong.sum(axis=1) > 1))
    split_cols = set(np.flatnonzero(strong.sum(axis=0) > 1))
    # Propagate ambiguity through the entire strong-overlap component.
    while True:
        rows = split_rows | {
            i for i in range(len(sol)) if any(strong[i, j] for j in split_cols)
        }
        cols = split_cols | {
            j for j in range(len(regions.regions)) if any(strong[i, j] for i in rows)
        }
        if rows == split_rows and cols == split_cols:
            break
        split_rows, split_cols = rows, cols
    records, boxes, matched = [], [], {}
    for i, original in enumerate(sol):
        record = BlockLayout(
            status="sol_only",
            sol_ordinal=i,
            sol_bbox=extracted_page.blocks[i].bbox.copy(),
        )
        box = page_box(original, regions.image_size, page_bounds)
        if i in split_rows:
            record.issues.append("split_merge_overlap")
        elif matrix.shape[1] and matrix[i].max() >= IOU:
            j = int(matrix[i].argmax())
            row_scores = sorted(matrix[i], reverse=True)
            col_scores = sorted(matrix[:, j], reverse=True)
            row_margin = row_scores[0] - (row_scores[1] if len(row_scores) > 1 else 0)
            col_margin = col_scores[0] - (col_scores[1] if len(col_scores) > 1 else 0)
            if (
                j not in split_cols
                and int(np.argmax(matrix[:, j])) == i
                and row_margin > EPSILON
                and col_margin > EPSILON
                and row_margin + EPSILON >= MARGIN
                and col_margin + EPSILON >= MARGIN
            ):
                region = regions.regions[j]
                record.status, record.region_row, record.iou = (
                    "matched",
                    region.row,
                    float(matrix[i, j]),
                )
                box = page_box(region.bbox_px, regions.image_size, page_bounds)
                matched[i] = region
            else:
                record.issues.append("ambiguous_match")
        record.initial_bbox = box.copy()
        records.append(record)
        boxes.append(box)
    order = list(range(len(sol)))
    start = 0
    while start < len(order):
        if start not in matched:
            start += 1
            continue
        end = start + 1
        while end in matched:
            end += 1
        run = order[start:end]
        for i in run:
            if any(
                i != j and abs(matched[i].order_key - matched[j].order_key) <= EPSILON
                for j in run
            ):
                records[i].issues.append("ambiguous_order")
        # Preserve the run when near-equal keys would make a sort unstable.
        if not any("ambiguous_order" in records[i].issues for i in run):
            order[start:end] = sorted(run, key=lambda i: (matched[i].order_key, i))
        start = end
    if extracted_page.blank and regions.regions:
        regions.warnings.append("Sol blank page disagrees with detected regions")
    used = {r.region_row for r in records if r.status == "matched"}
    for region in regions.regions:
        if region.row not in used:
            region.issues.append("unmatched_v3")
    return boxes, records, order


def merge_lineage(target, sources):
    """Carry original source regions through destructive processor operations."""
    evidence = {}
    for block in [target, *sources]:
        if block.layout is not None:
            for source in block.layout.sources:
                evidence[source.block_id] = source
    if evidence:
        provenance = (
            target.layout.model_copy(deep=True)
            if target.layout
            else BlockLayout(status="processor")
        )
        provenance.status = "processor"
        provenance.sources = list(evidence.values())
        target.layout = provenance


def finalize_layout(document):
    """Populate derived group lineage after processors without changing geometry."""
    if document.layout is None:
        return

    def visit(block, seen):
        if str(block.id) in seen:
            return
        seen.add(str(block.id))
        children = [document.get_block(bid) for bid in block.structure or []]
        for child in children:
            visit(child, seen)
        if children and any(child.layout for child in children):
            merge_lineage(block, children)

    for page in document.pages:
        for bid in page.structure or []:
            visit(document.get_block(bid), set())


def layout_metadata(document):
    """Describe final geometry and order separately from original detections."""
    if document.layout is None:
        return None
    blocks = {}
    orders = {}
    for page in document.pages:
        orders[page.page_id] = [str(bid) for bid in page.structure or []]
        for block in page.children or []:
            if block.layout is None:
                continue
            item = block.layout.model_dump()
            item.update(
                final_bbox=block.polygon.bbox,
                final_type=str(block.block_type),
                removed=block.removed,
                ignored=block.ignore_for_output,
                final_structure=[str(bid) for bid in block.structure or []],
            )
            item["geometry_source"] = (
                "processor"
                if block.layout.status == "processor"
                or block.layout.initial_bbox != block.polygon.bbox
                else "v3_bbox"
                if block.layout.status == "matched"
                else "sol"
            )
            item["multi_page"] = len({s.page_id for s in block.layout.sources}) > 1
            blocks[str(block.id)] = item
    return {**document.layout.model_dump(), "blocks": blocks, "final_order": orders}
