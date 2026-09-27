"""Pinned PP-DocLayoutV3 decoding and source-preserving Sol reconciliation."""

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

PIPELINE = "sol-layout-v3/v4"
REPORTING_POLICY = "initial-final-geometry-diagnostics/v1"
PRIOR_VERSION = 2
DECODE_POLICY = "paddlex-ffb64904-poly/v1"
MATCH_POLICY = "contour-family-greedy/v1"
ORDER_POLICY = "global-matched-slots/v1"
SOURCE_POLICY = "source-footprints-visibility/v1"
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
TEXT_TYPES = frozenset(
    {
        "Text",
        "SectionHeader",
        "PageHeader",
        "PageFooter",
        "Caption",
        "Footnote",
        "Bibliography",
        "ListGroup",
        "TableOfContents",
        "Code",
    }
)
FAMILIES = {
    "text": sorted(TEXT_TYPES),
    "visual": ["Diagram", "Figure", "Picture"],
    "table": ["Form", "Table"],
    "formula": ["Equation"],
}
# Provisional matching policy, not calibrated accuracy/confidence guarantees.
SCORE = 0.5
IOU = 0.5
MARGIN = 0.10
CONTAINMENT = 0.8
EPSILON = 1e-6
OUTPUTS = ["fetch_name_0", "fetch_name_1", "fetch_name_2"]


class LayoutModelUnavailable(RuntimeError):
    """The layout engine could not run; conversion records explicit Sol fallback."""


class LayoutContractError(LayoutModelUnavailable):
    """The pinned raw tensor or image-frame contract was violated."""


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
    for name in ("onnxruntime", "cv2", "huggingface_hub", "yaml", "shapely"):
        _dependency(name)


def extraction_prompt(prompt: str, analysis: LayoutAnalysis) -> str:
    """Append a complete versioned guide and measure its UTF-8 payload.

    Args:
        prompt: Packaged whole-page transcription instructions.
        analysis: Validated detections in rendered-image pixels.

    Returns:
        str: Instructions followed by compact, versioned layout data. Raw masks
        stay local; normalized coordinates are only a request representation.
    """
    from doclayout.layout_geometry import (
        polygon_parts,
        region_geometry,
        transform_points,
    )

    width, height = analysis.image_size
    frame = [0, 0, width, height]
    regions = []
    vertex_count = 0
    for region in sorted(analysis.regions, key=lambda r: (r.order_key, r.row)):
        if not region.eligible:
            continue
        geometry, source, reason = region_geometry(region, analysis.image_size)
        contours = (
            [
                [
                    [round(x, 3), round(y, 3)]
                    for x, y in transform_points(part, frame, [0, 0, 1000, 1000])
                ]
                for part in polygon_parts(geometry)
            ]
            if source == "v3_contour"
            else []
        )
        # Request rounding must not manufacture a valid-looking collapsed ring.
        if contours:
            from shapely.geometry import Polygon

            if any(
                not Polygon(part).is_valid or Polygon(part).area <= 0
                for part in contours
            ):
                contours, source, reason = [], "v3_bbox", "guide_rounding_invalid"
        vertex_count += sum(len(part) for part in contours)
        regions.append(
            {
                "id": f"r{region.row}",
                "row": region.row,
                "class_id": region.class_id,
                "label": region.label,
                "score": region.score,
                "bbox": [
                    round(value * 1000 / (width if index % 2 == 0 else height), 3)
                    for index, value in enumerate(region.bbox_px)
                ],
                "order_key": region.order_key,
                "derived_rank": region.observed_rank,
                "block_type_hint": MAPPING[region.class_id],
                "contours": contours,
                "geometry_source": source,
                "geometry_fallback": reason,
            }
        )
    prior = {
        "given_layout": {
            "version": PRIOR_VERSION,
            "coordinate_space": "full_page_normalized_0_1000",
            "geometry_type": "contour_or_aabb",
            "regions": regions,
        }
    }
    payload = json.dumps(prior, separators=(",", ":"), allow_nan=False)
    analysis.guide_bytes = len(payload.encode("utf-8"))
    analysis.guide_vertex_count = vertex_count
    return prompt.rstrip() + "\n\n" + payload


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
    for name in (
        "onnxruntime-gpu",
        "onnxruntime",
        "numpy",
        "opencv-python-headless",
        "shapely",
    ):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            pass
    manifest = {
        "pipeline": PIPELINE,
        "execution_policy": EXECUTION_POLICY,
        "fallback_policy": FALLBACK_POLICY,
        "given_layout_version": PRIOR_VERSION,
        "decode_policy": DECODE_POLICY,
        "matching_policy": MATCH_POLICY,
        "order_policy": ORDER_POLICY,
        "source_policy": SOURCE_POLICY,
        "reporting_policy": REPORTING_POLICY,
        "artifact": {"repo": REPO, "revision": REVISION, "sha256": HASHES},
        "mapping": dict(enumerate(MAPPING)),
        "compatibility_families": FAMILIES,
        "thresholds": {
            "score_gt": SCORE,
            "iou_ge": IOU,
            "ambiguity_margin_lt": MARGIN,
            "split_merge_containment_ge": CONTAINMENT,
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
    import cv2

    from doclayout.layout_geometry import mask_contour, region_geometry

    if not isinstance(outputs, (list, tuple)) or len(outputs) != len(OUTPUTS):
        raise LayoutContractError("Layout output tensor contract changed.")
    boxes, counts, masks = outputs
    if not all(isinstance(value, np.ndarray) for value in outputs):
        raise LayoutContractError("Layout output tensor contract changed.")
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
        raise LayoutContractError("Layout output tensor contract changed.")
    if len(image_size) != 2 or any(type(v) is not int or v <= 0 for v in image_size):
        raise LayoutContractError("Layout image coordinate frame is invalid.")
    width, height = image_size
    retained = boxes[boxes[:, 1] > SCORE].copy()
    retained[:, 2:6] = np.round(retained[:, 2:6])
    # Preserve the official expression, including its x_max - y_min quirk.
    max_box_w = float(np.max(retained[:, 4] - retained[:, 3])) if len(retained) else 0
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
        region = regions[-1]
        if not valid:
            region.contour_status = "unusable"
            continue
        try:
            region.contour_px, reason = mask_contour(
                masks[row], region.raw_bbox_px, image_size, max_box_w
            )
        except (cv2.error, OverflowError, FloatingPointError, MemoryError) as exc:
            # A contour-only native/allocation failure cannot discard its AABB.
            reason = f"contour_decode_{type(exc).__name__}"
        region.contour_status = "valid" if reason is None else "bbox_fallback"
        if reason is None:
            assert region.contour_px is not None
            _, source, reason = region_geometry(region, image_size)
            if source == "v3_contour":
                region.geometry_kind = "contour_with_mask"
            else:
                region.contour_status = "bbox_fallback"
            if any(
                x < 0 or x > width or y < 0 or y > height for x, y in region.contour_px
            ):
                region.issues.append("contour_outside_page_vertices")
        if reason:
            region.issues.append(reason)
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
        self._cpu_fallback_stage = None
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
                self._cpu_fallback_stage = None
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
                        self._cpu_fallback_stage = "inference"
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
                            self._cpu_fallback_stage = "startup"
                    if result is None:
                        result = self._exercise(
                            inputs, image.size, "CPUExecutionProvider"
                        )
                result.warnings = list(self._warnings)
                result.execution_providers = (
                    ["CUDAExecutionProvider", "CPUExecutionProvider"]
                    if self._provider == "CUDAExecutionProvider"
                    else ["CPUExecutionProvider"]
                )
                result.cpu_fallback_stage = self._cpu_fallback_stage
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
    if target is None:
        return False
    return any(target in family and kind in family for family in FAMILIES.values())


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
    from doclayout.layout_geometry import transform_points

    return [
        v
        for point in transform_points([box[:2], box[2:]], [0, 0, *image_size], bounds)
        for v in point
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
        indices in merged reading order. Every accepted endpoint is reserved
        once. Ambiguity is recorded, never used to veto a qualified best pair.
    """
    from doclayout.layout_geometry import (
        polygon_parts,
        region_geometry,
        transform_points,
    )

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
    geometries = {
        j: region_geometry(region, regions.image_size)
        for j, region in enumerate(regions.regions)
        if region.eligible
    }
    if geometries:
        from shapely.geometry import box as rectangle

    for i, block in enumerate(extracted_page.blocks):
        if not geometries:
            continue
        sol_polygon = rectangle(*sol[i])
        for j, region in enumerate(regions.regions):
            if region.eligible and compatible(block.block_type, region.class_id):
                geometry = geometries[j][0]
                intersection = sol_polygon.intersection(geometry).area
                union = sol_polygon.area + geometry.area - intersection
                matrix[i, j] = intersection / union if union else 0
                smaller = min(sol_polygon.area, geometry.area)
                strong[i, j] = bool(smaller and intersection / smaller >= CONTAINMENT)
    candidates = sorted(
        [(i, j) for i, j in zip(*np.where(matrix >= IOU))],
        key=lambda pair: (
            -matrix[pair],
            -regions.regions[pair[1]].score,
            regions.regions[pair[1]].row,
            pair[0],
        ),
    )
    assigned, reserved = {}, set()
    for i, j in candidates:
        if i not in assigned and j not in reserved:
            assigned[i] = j
            reserved.add(j)
    records, boxes, matched = [], [], {}
    for i, original in enumerate(sol):
        record = BlockLayout(
            status="sol_only",
            geometry_source="sol",
            sol_ordinal=i,
            sol_bbox=extracted_page.blocks[i].bbox.copy(),
        )
        box = page_box(original, regions.image_size, page_bounds)
        if strong[i].sum() > 1 or any(
            strong[:, j].sum() > 1 for j in np.flatnonzero(strong[i])
        ):
            record.issues.append("split_merge_overlap")
        if i in assigned:
            j = assigned[i]
            region = regions.regions[j]
            geometry, source, reason = geometries[j]
            record.status, record.region_row, record.iou = (
                "matched",
                region.row,
                float(matrix[i, j]),
            )
            record.geometry_source = source
            record.match_metric = (
                "contour_iou" if source == "v3_contour" else "aabb_iou"
            )
            record.layout_class_id, record.layout_label = region.class_id, region.label
            record.order_key, record.observed_rank = (
                region.order_key,
                region.observed_rank,
            )
            record.contours = (
                [
                    transform_points(part, [0, 0, width, height], page_bounds)
                    for part in polygon_parts(geometry)
                ]
                if source == "v3_contour"
                else []
            )
            if reason:
                record.issues.append(reason)
            if MAPPING[region.class_id] != extracted_page.blocks[i].block_type:
                record.issues.append("compatible_class_disagreement")
            alternatives = [
                float(matrix[i, k]) for k in range(matrix.shape[1]) if k != j
            ]
            alternatives += [
                float(matrix[k, j]) for k in range(matrix.shape[0]) if k != i
            ]
            if any(
                score >= IOU and abs(record.iou - score) <= EPSILON
                for score in alternatives
            ):
                record.issues.append("matching_score_tie")
            if any(
                score >= IOU and record.iou - score < MARGIN + EPSILON
                for score in alternatives
            ):
                record.issues.append("ambiguous_match")
            if strong[i].sum() > 1:
                record.issues.append(
                    "merged_sol_content_may_extend_beyond_assigned_region"
                )
            box = page_box(region.bbox_px, regions.image_size, page_bounds)
            matched[i] = region
        else:
            if not regions.regions:
                reason = (
                    "all_candidates_filtered"
                    if regions.candidate_count and regions.filtered_count
                    else "empty_detection_result"
                )
            elif not geometries:
                reason = "no_usable_v3_geometry"
            elif not any(
                compatible(
                    extracted_page.blocks[i].block_type, regions.regions[j].class_id
                )
                for j in geometries
            ):
                reason = "no_compatible_v3_class"
            elif any(matrix[i] >= IOU):
                reason = "qualified_region_reserved"
            else:
                reason = "overlap_below_threshold"
            record.issues.append(reason)
        record.initial_bbox = box.copy()
        records.append(record)
        boxes.append(box)
    order = list(range(len(sol)))
    for i, matched_region in matched.items():
        if any(
            i != j and abs(matched_region.order_key - other.order_key) <= EPSILON
            for j, other in matched.items()
        ):
            records[i].issues.append("ambiguous_order")
    sorted_matches = sorted(
        matched, key=lambda i: (matched[i].order_key, matched[i].row, i)
    )
    for position, index in zip(sorted(matched), sorted_matches):
        order[position] = index
    if extracted_page.blank and regions.regions:
        regions.warnings.append("Sol blank page disagrees with detected regions")
    used = {r.region_row for r in records if r.status == "matched"}
    for j, region in enumerate(regions.regions):
        if region.row not in used:
            region.issues.append("unmatched_v3")
            if not region.eligible:
                reason = "unusable_v3_geometry"
            elif not extracted_page.blocks:
                reason = "no_sol_blocks"
            elif not any(
                compatible(b.block_type, region.class_id) for b in extracted_page.blocks
            ):
                reason = "no_compatible_sol_class"
            elif any(matrix[:, j] >= IOU):
                reason = "qualified_sol_block_reserved"
            else:
                reason = "overlap_below_threshold"
            region.issues.append(reason)
    return boxes, records, order


def merge_lineage(target, sources):
    """Carry original source regions through destructive processor operations."""
    evidence = {}
    for block in [target, *sources]:
        if block.layout is not None:
            for source in block.layout.sources:
                evidence[source.block_id] = source.model_copy(deep=True)
    if evidence:
        provenance = (
            target.layout.model_copy(deep=True)
            if target.layout
            else BlockLayout(status="processor")
        )
        provenance.status = "processor"
        provenance.geometry_source = "source_footprints"
        provenance.contours = []
        provenance.region_row = None
        provenance.order_key = None
        provenance.observed_rank = None
        provenance.layout_class_id = None
        provenance.layout_label = None
        provenance.iou = None
        provenance.match_metric = None
        provenance.sources = list(evidence.values())
        target.layout = provenance


def has_layout_order(page, document):
    """Whether a page has any matched source, including grouped sources."""

    def matched(block):
        return bool(
            block.layout
            and (
                block.layout.order_key is not None
                or any(
                    s.order_key is not None and s.page_id == page.page_id
                    for s in block.layout.sources
                )
            )
        ) or any(matched(document.get_block(bid)) for bid in block.structure or [])

    return any(matched(document.get_block(bid)) for bid in page.structure or [])


def furniture_role(block):
    """Prefer matched furniture labels; otherwise retain Sol's semantic role."""
    record = block.layout
    labels = [s.layout_label for s in record.sources] if record else []
    if record and record.layout_label is not None:
        labels.append(record.layout_label)
    if any(label is not None for label in labels):
        if all(label in {"header", "header_image"} for label in labels):
            return "header"
        if all(label in {"footer", "footer_image"} for label in labels):
            return "footer"
        return None
    return {"PageHeader": "header", "PageFooter": "footer"}.get(str(block.block_type))


def visible_block(block, config=None):
    """Resolve removal, explicit suppression and furniture without mutation."""
    if block.removed or block.ignore_for_output:
        return False
    role = furniture_role(block)
    return role is None or bool((config or {}).get(f"keep_page{role}_in_output", False))


def visible_sources(block, document, config=None):
    """Walk rendered content, not historical children or invented group bounds."""
    if not visible_block(block, config):
        return []
    if block.structure and not getattr(block, "html", None):
        sources = [
            s
            for bid in block.structure
            for s in visible_sources(document.get_block(bid), document, config)
        ]
        if (
            not sources
            and block.layout
            and any(
                visible_block(document.get_block(bid), config)
                for bid in block.structure
            )
        ):
            sources = block.layout.sources
    else:
        sources = block.layout.sources if block.layout else []
    return list({s.block_id: s for s in sources}.values())


def finalize_layout(document):
    """Retain source footprints and enforce matched order after assembly."""
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
        if (
            block.layout
            and block.layout.status == "matched"
            and block.layout.initial_bbox is not None
            and block.polygon.bbox != block.layout.initial_bbox
        ):
            from doclayout.schema.polygon import PolygonBox

            block.layout.issues.append("processor_geometry_change_ignored")
            block.polygon = PolygonBox.from_bbox(block.layout.initial_bbox)
        elif (
            block.layout
            and block.layout.status == "sol_only"
            and block.layout.initial_bbox is not None
            and block.polygon.bbox != block.layout.initial_bbox
        ):
            merge_lineage(block, [])
            block.layout.issues.append("processor_derived_bounds")

    for page in document.pages:
        for bid in page.structure or []:
            visit(document.get_block(bid), set())
        ranked = {}
        for position, bid in enumerate(page.structure or []):
            block = document.get_block(bid)
            if block.removed or block.ignore_for_output:
                continue
            sources = (
                [
                    s
                    for s in block.layout.sources
                    if s.page_id == page.page_id and s.order_key is not None
                ]
                if block.layout
                else []
            )
            if sources:
                ranked[position] = min(
                    (s.order_key, s.region_row, s.sol_ordinal or 0) for s in sources
                )
        positions = sorted(ranked)
        ordered = [
            page.structure[i] for i in sorted(ranked, key=lambda i: (*ranked[i], i))
        ]
        for position, bid in zip(positions, ordered):
            page.structure[position] = bid
        # Assemblies cannot be split to interleave their source text reliably.
        for bid in ordered:
            block = document.get_block(bid)
            keys = [
                s.order_key
                for s in block.layout.sources
                if s.page_id == page.page_id and s.order_key is not None
            ]
            if any(min(keys) < key[0] < max(keys) for key in ranked.values()):
                block.layout.issues.append("assembled_source_order_interleaves")
            block.layout.issues = list(dict.fromkeys(block.layout.issues))


def layout_metadata(document, config=None):
    """Describe final geometry and order separately from original detections."""
    if document.layout is None:
        return None
    blocks = {}
    orders = {}
    final_counts: dict[int, dict] = {
        page.page_id: {
            "counts_stage": "final_visible_structure",
            "visible_blocks": 0,
            "processor_derived_blocks": 0,
            "geometry_counts": {},
        }
        for page in document.pages
    }
    seen_sources = set()
    for page in document.pages:
        orders[page.page_id] = [str(bid) for bid in page.structure or []]
        for bid in page.structure or []:
            block = document.get_block(bid)
            if not visible_block(block, config):
                continue
            sources = visible_sources(block, document, config)
            if not sources and block.structure and not getattr(block, "html", None):
                continue
            final_counts[page.page_id]["visible_blocks"] += 1
            if block.layout and block.layout.status == "processor":
                final_counts[page.page_id]["processor_derived_blocks"] += 1
            for source in sources:
                identity = (source.page_id, source.block_id)
                if identity in seen_sources or source.page_id not in final_counts:
                    continue
                seen_sources.add(identity)
                counts = final_counts[source.page_id]["geometry_counts"]
                counts[source.geometry_source] = (
                    counts.get(source.geometry_source, 0) + 1
                )
        for block in page.children or []:
            if block.layout is None:
                continue
            item = block.layout.model_dump()
            item.update(
                final_bbox=block.polygon.bbox,
                final_type=str(block.block_type),
                removed=block.removed,
                ignored=block.ignore_for_output,
                visible=visible_block(block, config),
                furniture_role=furniture_role(block),
                final_structure=[str(bid) for bid in block.structure or []],
            )
            item["geometry_source"] = block.layout.geometry_source
            item["multi_page"] = len({s.page_id for s in block.layout.sources}) > 1
            blocks[str(block.id)] = item
    return {
        **document.layout.model_dump(),
        "blocks": blocks,
        "final_order": orders,
        "final_counts": final_counts,
    }


def layout_summary(metadata):
    """Format recorded diagnostics for GUI and CLI without runtime inspection.

    Missing historical observations stay unknown. Initial counts describe Sol
    blocks; final geometry counts describe unique visible source footprints,
    attributed to their source pages, not processor envelopes or polygon parts.
    """
    audit = metadata.get("layout") or {}
    pages = audit.get("page_runtime", {})
    if not pages:
        return None

    def counts(value):
        if value is None:
            return "not recorded"
        return (
            ", ".join(f"{key}={number}" for key, number in sorted(value.items()))
            or "none"
        )

    values = list(pages.values())
    elapsed = sum(p["elapsed_ms"] for p in values)
    lines = [
        (
            f"V3: {sum(p['retained_region_count'] for p in values)} regions · "
            f"{sum(p['matched_count'] for p in values)} initial matches · "
            f"{elapsed:,.0f} ms summed page analysis (includes preparation/queue wait; not pure inference)"
        )
    ]
    for page_id, page in sorted(pages.items(), key=lambda item: int(item[0])):
        providers = page.get("execution_providers")
        execution = (
            "+".join(providers)
            if providers is not None
            else "provider set not recorded"
        )
        device = page.get("actual_device", "not recorded") or "unavailable"
        final = audit.get("final_counts", {}).get(page_id)
        if final is None:
            final = audit.get("final_counts", {}).get(str(page_id))
        lines.append(
            f"Page {int(page_id) + 1}: {device} · {page.get('provider', 'not recorded')} "
            f"({execution}) · Sol fallback stage={page.get('failure_stage', 'not recorded') or 'none'} · "
            f"CPU fallback stage={page.get('cpu_fallback_stage') or 'none recorded'} · "
            f"initial eligible={page.get('prior_region_count', 'not recorded')}, "
            f"matched={page['matched_count']}, Sol-only={page.get('sol_only_count', 'not recorded')}, "
            f"V3-only={page.get('unmatched_v3_count', 'not recorded')} · "
            f"initial geometry: {counts(page.get('geometry_counts'))} · "
            f"Sol-only reasons: {counts(page.get('sol_only_reasons'))} · "
            f"V3-only reasons: {counts(page.get('unmatched_v3_reasons'))} · "
            f"final visible blocks={final['visible_blocks'] if final else 'not recorded'}, "
            f"source footprints: {counts(final['geometry_counts'] if final else None)}"
        )
    fallback = sum(p.get("status") == "sol_fallback" for p in values)
    if fallback:
        lines.append(f"Sol fallback: {fallback} page(s)")
    if audit.get("annotations"):
        overlay = audit["annotations"]
        lines.append(
            f"Annotations: {overlay['drawn']} parts drawn, {overlay['skipped']} skipped"
        )
    return "\n\n".join(lines)
