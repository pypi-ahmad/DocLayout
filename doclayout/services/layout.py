"""Local PP-DocLayoutV3 inference for conversion layout guidance.

PaddleOCR owns preprocessing and contour decoding. Dependencies load lazily.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import sys
import types
from dataclasses import dataclass, field
from importlib.metadata import version
from numbers import Integral
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Any, Literal

import numpy as np
from PIL import Image

from doclayout.schema.geometry import Contour, GeometrySource, validate_contour
from doclayout.schema.polygon import PolygonBox

MODEL_ID = "PaddlePaddle/PP-DocLayoutV3_onnx"
MODEL_REVISION = "46bbdf188bb0a772c08aed74882ce7e51a8f1ea6"
# Sizes and SHA-256 from the official, immutable ONNX repository revision.
ARTIFACT_FILES = {
    "inference.onnx": (
        130502049,
        "45bf71750b00739a41fc209f132eb104a4d6b5bb29483c9078164d8b87cf28ba",
    ),
    "inference.yml": (
        1482,
        "506fcfac13b3b546ae40d7886b44126420f392adb694e3f8bb6a6286a1f90fdc",
    ),
}
CPU_PROVIDER = "CPUExecutionProvider"
CUDA_PROVIDER = "CUDAExecutionProvider"
Device = Literal["auto", "cpu", "cuda"]
logger = logging.getLogger(__name__)


class LayoutError(RuntimeError):
    """Base error for local conversion layout."""


class LayoutConfigurationError(LayoutError):
    """A supplied layout configuration is invalid."""


class LayoutPromptLimitError(LayoutError):
    """The complete layout guide cannot fit the request budget."""


class LayoutInvariantError(LayoutError):
    """A downstream processor tried to replace authoritative layout."""


class LayoutDependencyError(LayoutError):
    """The layout extra or a required native library is unavailable."""


class LayoutCacheError(LayoutError):
    """The model cache could not be accessed or populated."""


class LayoutArtifactError(LayoutCacheError):
    """An existing artifact failed integrity verification; it was not replaced."""


class LayoutDeviceError(LayoutError):
    """The explicitly requested device could not execute the model."""


class LayoutInferenceError(LayoutError):
    """Inference failed or returned an invalid result."""


class LayoutCapabilityError(LayoutInferenceError):
    """The pinned native segmentation decoding contract is unavailable."""


class LayoutGeometryError(LayoutInferenceError):
    """The runtime returned malformed contour geometry."""


LAYOUT_RUNTIME_ERRORS = (
    LayoutDependencyError,
    LayoutCacheError,
    LayoutDeviceError,
    LayoutInferenceError,
)


def layout_fallback_message(error: LayoutError) -> str:
    return layout_error_message(error).replace(
        "Layout conversion failed.", "V3 unavailable; using Sol boxes and order."
    )


def layout_error_message(error: LayoutError) -> str:
    """Safe operator guidance without paths, document data or provider payloads."""
    messages = {
        LayoutConfigurationError: "If DOCLAYOUT_ALIGNMENT_POLICY is set, supply all five valid values or unset it to retain Sol geometry. Check device auto/cpu/cuda and remove block relabeling rules.",
        LayoutDependencyError: "Install the locked layout extra in Python 3.11+ and check native runtime libraries.",
        LayoutArtifactError: "Cached layout files failed integrity verification; repair the layout cache.",
        LayoutCacheError: "Check layout cache permissions and model download availability.",
        LayoutDeviceError: "Explicit CUDA failed; fix CUDA setup or select auto/CPU.",
        LayoutPromptLimitError: "The complete page layout exceeds the 512-region or 64-KiB guide limit.",
        LayoutInvariantError: "A processor attempted to change protected layout; check processor configuration.",
        LayoutInferenceError: "Layout inference failed or returned invalid regions; check the local runtime.",
        LayoutCapabilityError: "The pinned runtime must expose native segmentation and contour decoding.",
        LayoutGeometryError: "The native decoder returned malformed geometry; check the layout runtime.",
    }
    return "Layout conversion failed. " + messages.get(
        type(error), "Check the local layout runtime."
    )


@dataclass(frozen=True, slots=True)
class LayoutRegion:
    class_id: int
    label: str
    score: float
    bbox: tuple[float, float, float, float]
    order_index: int
    contour: Contour
    geometry_source: GeometrySource

    def as_polygon_box(self) -> PolygonBox:
        """Derive four rectangle corners, not a model segmentation polygon."""
        return PolygonBox.from_bbox(list(self.bbox))


@dataclass(frozen=True, slots=True)
class LayoutPreparation:
    actual_device: str
    provider: str
    elapsed_seconds: float
    fallback_reason: str | None = None


@dataclass(frozen=True, slots=True)
class LayoutResult:
    model_id: str
    revision: str
    actual_device: str
    provider: str
    elapsed_seconds: float
    image_size: tuple[int, int]
    regions: tuple[LayoutRegion, ...]
    preparation_seconds: float = 0.0
    fallback_reason: str | None = None
    error_code: str | None = None


_import_lock = Lock()


def _dependencies(cache_dir: Path) -> tuple[Any, Any, Any, type[Exception]]:
    if sys.version_info < (3, 11):
        raise LayoutDependencyError("Local layout requires Python 3.11 or newer.")
    # PaddleX reads these once during import. Preserve explicit operator settings.
    # HF's Xet cache is separate from hf_hub_download(cache_dir=...).
    with _import_lock:
        os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(cache_dir / "paddlex"))
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        os.environ.setdefault("HF_XET_CACHE", str(cache_dir / "xet"))
        try:
            import onnxruntime
            from huggingface_hub import hf_hub_download
            from paddleocr import LayoutDetection
            from paddlex.utils.deps import DependencyError
        except PermissionError as exc:
            raise LayoutCacheError(
                "Cannot access the optional layout runtime cache."
            ) from exc
        except Exception as exc:
            raise LayoutDependencyError(
                "Cannot load the layout dependencies. Use Python 3.11+ and "
                "uv sync --extra layout; check native DLLs if already installed. "
                f"Cause: {type(exc).__name__}."
            ) from exc
    return onnxruntime, LayoutDetection, hf_hub_download, DependencyError


def _model_directory(cache_dir: Path, download: Any) -> Path:
    """Use HF's locked/atomic cache, fetching only missing pinned files."""
    from huggingface_hub.errors import LocalEntryNotFoundError

    paths = []
    try:
        for filename, (expected_size, expected_hash) in ARTIFACT_FILES.items():
            kwargs = {
                "repo_id": MODEL_ID,
                "revision": MODEL_REVISION,
                "filename": filename,
                "cache_dir": cache_dir / "hub",
                "endpoint": "https://huggingface.co",
            }
            try:
                path = Path(download(**kwargs, local_files_only=True))
            except LocalEntryNotFoundError:
                path = Path(download(**kwargs, local_files_only=False))
            with path.open("rb") as artifact:
                valid_size = path.stat().st_size == expected_size
                hasher = hashlib.sha256()
                for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
                    hasher.update(chunk)
                digest = hasher.hexdigest()
            if not valid_size or digest != expected_hash:
                raise LayoutArtifactError(
                    f"Corrupt layout artifact: {path}. Expected revision "
                    f"{MODEL_REVISION}. Remove only this corrupt cache entry "
                    "and restart to download it again."
                )
            paths.append(path)
        if paths[0].parent != paths[1].parent:
            raise LayoutArtifactError("Layout artifacts are not in one snapshot.")
        return paths[0].parent
    except LayoutError:
        raise
    except Exception as exc:
        raise LayoutCacheError(
            f"Cannot populate or read layout cache {cache_dir} "
            f"({type(exc).__name__}). Check permissions and Hub connectivity."
        ) from exc


def _invoke(model: Any, image: np.ndarray) -> Any:
    return model.predict(
        image, batch_size=1, layout_shape_mode="poly", skip_order_labels=[]
    )


def _observe_native_decoder(model: Any) -> None:
    """Observe official fallback branches without modifying package globals.

    Function copies execute the installed decoder unchanged, with only its
    rectangle factory rebound. Identity distinguishes native four-point contours
    from documented degenerate-mask fallbacks. Calls are serialized by _Runtime.
    """
    from paddlex.inference.models.layout_analysis import processors as native

    post = getattr(model.paddlex_predictor, "post_op", None)
    if version("paddlex") != "3.7.2" or type(post) is not native.LayoutAnalysisProcess:
        raise LayoutCapabilityError("Unsupported native contour decoder version/type.")
    rectangles = []

    def rectangle(box):
        value = native._rect_from_box(box)
        rectangles.append(value)
        return value

    def rebind(function, **overrides):
        return types.FunctionType(
            function.__code__,
            function.__globals__ | overrides,
            function.__name__,
            function.__defaults__,
            function.__closure__,
        )

    normalize = rebind(native._normalize_layout_polygon, _rect_from_box=rectangle)
    extract = rebind(
        native.extract_polygon_points_by_masks,
        _rect_from_box=rectangle,
        _normalize_layout_polygon=normalize,
    )
    apply = rebind(
        native.LayoutAnalysisProcess.apply, extract_polygon_points_by_masks=extract
    )

    def observed(
        self,
        boxes,
        img_size,
        threshold,
        layout_nms,
        layout_unclip_ratio,
        layout_merge_bboxes_mode,
        masks=None,
        layout_shape_mode="auto",
        polygon_points=None,
    ):
        if masks is None or layout_shape_mode != "poly" or polygon_points is not None:
            raise LayoutCapabilityError(
                "Native segmentation output is required, including empty results."
            )
        if (
            not isinstance(masks, np.ndarray)
            or masks.ndim != 3
            or masks.dtype.kind not in "biuf"
            or len(masks) != len(boxes)
            or min(masks.shape[1:]) <= 0
            or not np.isfinite(masks).all()
        ):
            raise LayoutGeometryError("Malformed segmentation output.")
        rectangles.clear()
        try:
            result = apply(
                self,
                boxes,
                img_size,
                threshold,
                layout_nms,
                layout_unclip_ratio,
                layout_merge_bboxes_mode,
                masks,
                layout_shape_mode,
                polygon_points,
            )
            for box in result:
                polygon = box.get("polygon_points")
                if polygon is None:
                    raise LayoutCapabilityError(
                        "Native decoder did not expose a contour."
                    )
                box["geometry_source"] = (
                    "rectangle_fallback"
                    if any(polygon is r for r in rectangles)
                    else "native_contour"
                )
            return result
        except (LayoutCapabilityError, LayoutGeometryError):
            raise
        except (ValueError, TypeError, IndexError, KeyError) as exc:
            raise LayoutGeometryError("Native contour decoding failed.") from exc
        finally:
            rectangles.clear()

    post.apply = types.MethodType(observed, post)


def _close(model: Any) -> None:
    if model is not None:
        try:
            model.close()
        except Exception:
            logger.debug("Layout model cleanup failed", exc_info=True)


@dataclass
class _Runtime:
    lock: Any = field(default_factory=Lock)
    model: Any = None
    ort: Any = None
    factory: Any = None
    dependency_error: type[Exception] = ImportError
    model_dir: Path | None = None
    provider: str = ""
    error: tuple[type[LayoutError], str] | None = None
    preparation_seconds: float = 0.0
    fallback_reason: str | None = None

    def preparation(self) -> LayoutPreparation:
        return LayoutPreparation(
            "cuda:0" if self.provider == CUDA_PROVIDER else "cpu",
            self.provider,
            self.preparation_seconds,
            self.fallback_reason,
        )

    def create(self, device: Literal["cpu", "cuda"]) -> None:
        """Create and exercise a real session, never trusting provider listing alone."""
        model = None
        try:
            if device == "cuda":
                self.ort.preload_dlls()
            provider = CUDA_PROVIDER if device == "cuda" else CPU_PROVIDER
            providers = [provider, CPU_PROVIDER] if device == "cuda" else [provider]
            model = self.factory(
                model_name="PP-DocLayoutV3",
                model_dir=str(self.model_dir),
                engine="onnxruntime",
                device="gpu:0" if device == "cuda" else "cpu",
                engine_config={"providers": providers},
            )
            session = model.paddlex_predictor.runner.session
            _observe_native_decoder(model)
            # ORT may silently substitute CPU during construction. During run(),
            # let this service control fallback instead of ORT rebuilding itself.
            session.disable_fallback()
            if session.get_providers()[0] != provider:
                raise LayoutDeviceError(f"ORT did not activate {provider}.")
            probe = np.full((64, 64, 3), 255, dtype=np.uint8)
            probe[24:40, 8:56] = 0
            _invoke(model, probe)
            if session.get_providers()[0] != provider:
                raise LayoutDeviceError(f"ORT stopped using {provider} during warm-up.")
        except Exception as exc:
            _close(model)
            # PaddleOCR wraps PaddleX DependencyError in RuntimeError.
            if isinstance(exc, (ImportError, self.dependency_error)) or isinstance(
                exc.__cause__, self.dependency_error
            ):
                raise LayoutDependencyError(
                    "A layout dependency is missing. Run uv sync --extra layout."
                ) from exc
            raise
        self.model, self.provider = model, provider

    def initialize(self, cache_dir: Path, device: Device) -> None:
        if self.error is not None:
            error_type, message = self.error
            raise error_type(message)
        if self.model is not None:
            return
        started = perf_counter()
        try:
            try:
                cache_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise LayoutCacheError(
                    f"Cannot create layout cache {cache_dir}."
                ) from exc
            self.ort, self.factory, download, self.dependency_error = _dependencies(
                cache_dir
            )
            self.model_dir = _model_directory(cache_dir, download)
            if device != "cpu":
                try:
                    self.create("cuda")
                    return
                except (
                    LayoutDependencyError,
                    LayoutCapabilityError,
                    LayoutGeometryError,
                ):
                    raise
                except Exception as exc:
                    if device == "cuda":
                        raise LayoutDeviceError(
                            "Explicit CUDA layout initialization/warm-up failed "
                            f"({type(exc).__name__}); CPU fallback is disabled. "
                            "Check ORT, CUDA 13.x and cuDNN 9.x."
                        ) from exc
                    logger.warning(
                        "Layout CUDA initialization/warm-up failed (%s); using CPU.",
                        type(exc).__name__,
                    )
                    # Do not expose native exception payloads or local paths.
                    self.fallback_reason = (
                        "CUDA initialization/warm-up failed "
                        f"({type(exc).__name__}); using CPU."
                    )
            try:
                self.create("cpu")
            except (LayoutDependencyError, LayoutCapabilityError, LayoutGeometryError):
                raise
            except Exception as exc:
                raise LayoutInferenceError(
                    f"Layout CPU initialization/warm-up failed ({type(exc).__name__})."
                ) from exc
        except LayoutError as exc:
            # Failed initialization is sticky too: queued page requests must not
            # each probe the same broken GPU. Restart after fixing dependencies/cache.
            self.error = type(exc), str(exc)
            raise
        finally:
            self.preparation_seconds = perf_counter() - started

    def predict(self, image: np.ndarray, device: Device) -> Any:
        try:
            return _invoke(self.model, image)
        except (LayoutCapabilityError, LayoutGeometryError):
            raise
        except Exception as exc:
            if device != "auto" or self.provider != CUDA_PROVIDER:
                raise LayoutInferenceError(
                    f"Layout inference on {self.provider} failed "
                    f"({type(exc).__name__}); no device fallback was performed."
                ) from exc
            logger.warning(
                "Layout CUDA inference failed (%s); retrying on CPU and keeping CPU.",
                type(exc).__name__,
            )
            self.fallback_reason = (
                f"CUDA page inference failed ({type(exc).__name__}); using CPU."
            )
        _close(self.model)
        self.model = None
        try:
            self.create("cpu")
        except (
            LayoutDependencyError,
            LayoutCapabilityError,
            LayoutGeometryError,
        ) as exc:
            self.error = type(exc), str(exc)
            raise
        except Exception as exc:
            error = LayoutInferenceError(
                f"Layout CPU fallback initialization failed ({type(exc).__name__})."
            )
            self.error = type(error), str(error)
            raise error from exc
        try:
            return _invoke(self.model, image)
        except (LayoutCapabilityError, LayoutGeometryError):
            raise
        except Exception as exc:
            raise LayoutInferenceError(
                f"Layout inference also failed on CPU ({type(exc).__name__})."
            ) from exc


_runtimes: dict[tuple[Device, Path], _Runtime] = {}
_runtimes_lock = Lock()


def _regions(output: Any, size: tuple[int, int]) -> tuple[LayoutRegion, ...]:
    try:
        if len(output) != 1:
            raise ValueError("Expected exactly one image result")
        regions = []
        width, height = size
        for box in output[0]["boxes"]:
            class_id, order = box["cls_id"], box["order"]
            if any(
                isinstance(x, bool) or not isinstance(x, Integral)
                for x in (class_id, order)
            ):
                raise ValueError("Class and order must be integers")
            label, score = box["label"], float(box["score"])
            x1, y1, x2, y2 = map(float, box["coordinate"])
            if (
                class_id < 0
                or not isinstance(label, str)
                or not label
                or not all(math.isfinite(x) for x in (score, x1, y1, x2, y2))
                or not 0 <= score <= 1
                or not 0 <= x1 < x2 <= width
                or not 0 <= y1 < y2 <= height
            ):
                raise ValueError("Invalid region fields or page-pixel rectangle")
            if "polygon_points" not in box or "geometry_source" not in box:
                raise LayoutCapabilityError("Native contour/provenance is missing.")
            contour = validate_contour(
                box["polygon_points"], (x1, y1, x2, y2), size, box["geometry_source"]
            )
            regions.append(
                LayoutRegion(
                    int(class_id),
                    label,
                    score,
                    (x1, y1, x2, y2),
                    int(order),
                    contour,
                    box["geometry_source"],
                )
            )
        regions.sort(key=lambda region: region.order_index)
        if [region.order_index for region in regions] != list(
            range(1, len(regions) + 1)
        ):
            raise ValueError("Expected consecutive one-based reading order")
        return tuple(regions)
    except LayoutCapabilityError:
        raise
    except Exception as exc:
        raise LayoutGeometryError(
            "Invalid PP-DocLayoutV3 contour-mode result."
        ) from exc


class LayoutService:
    """Batch-one, process-shared inference; explicit CUDA never falls back to CPU.

    Each (device, resolved cache directory) shares one locked lazy runtime. Startup
    failures persist until process restart. Normal inference failures do not poison
    a CPU session. CUDA sessions may still assign individual operators to CPU.
    """

    def __init__(self, device: Device = "auto", cache_dir: str | Path | None = None):
        if device not in ("auto", "cpu", "cuda"):
            raise ValueError("Layout device must be auto, cpu, or cuda")
        self.device = device
        self.cache_dir = Path(
            cache_dir if cache_dir is not None else Path.cwd() / ".cache" / "layout"
        )

    def _runtime(self) -> _Runtime:
        try:
            self.cache_dir = self.cache_dir.resolve()
        except OSError as exc:
            raise LayoutCacheError(
                "Cannot resolve the layout cache directory."
            ) from exc

        with _runtimes_lock:
            return _runtimes.setdefault((self.device, self.cache_dir), _Runtime())

    def prepare(self) -> LayoutPreparation:
        """Validate/cache artifacts and warm up once; reuse prediction's lock/session."""
        runtime = self._runtime()
        with runtime.lock:
            runtime.initialize(self.cache_dir, self.device)
            return runtime.preparation()

    def predict(self, image: Image.Image) -> LayoutResult:
        if not isinstance(image, Image.Image) or min(image.size) <= 0:
            raise ValueError("Layout input must be a nonempty PIL image")
        runtime = self._runtime()
        with runtime.lock:
            runtime.initialize(self.cache_dir, self.device)
            started = perf_counter()
            # NumPy inputs to Paddle's ReadImage are BGR; it converts them to RGB.
            rgb = image.convert("RGB")
            try:
                bgr = np.asarray(rgb)[:, :, ::-1].copy()
            finally:
                rgb.close()
            output = runtime.predict(bgr, self.device)
            regions = _regions(output, image.size)
            return LayoutResult(
                model_id=MODEL_ID,
                revision=MODEL_REVISION,
                actual_device="cuda:0" if runtime.provider == CUDA_PROVIDER else "cpu",
                provider=runtime.provider,
                elapsed_seconds=perf_counter() - started,
                image_size=image.size,
                regions=regions,
                preparation_seconds=runtime.preparation_seconds,
                fallback_reason=runtime.fallback_reason,
            )
