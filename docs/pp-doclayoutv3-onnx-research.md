# PP-DocLayoutV3 ONNX: features and full decoding

Research date: 2026-09-27.

This report records internet research, upstream source inspection, and an ONNX artifact probe performed in this session. It does not claim that the local DocLayout application implements every behavior described here. No application code, conversion prompts, or model settings were changed by this research.

## Required weight repository

Implementation follow-up, 2026-09-27: the local unreleased application now uses
mask-derived contours in matching, source lineage, and annotated exports. The
[integration record](layout-v3-plan.md#completion-verification-2026-09-27-local-unreleased)
documents the pinned reference, pipeline v4, native CPU/CUDA observations, and
remaining evaluation gaps. The research below describes upstream capabilities;
it is not evidence that every upstream feature or target document type was tested.

Keep `PaddlePaddle/PP-DocLayoutV3_onnx` and use its full decode. The user explicitly requested that this repository remain selected, including in response to future requests to switch to `PaddlePaddle/PP-DocLayoutV3`.

The ONNX artifact provides classes, confidence scores, bounding boxes, instance masks, and learned reading order. A weight-repository switch is not required to access these capabilities.

The model card uses `PP-DocLayoutV3` as the framework model name with the ONNX Runtime engine. A framework model name and the Hugging Face weight repository are separate identifiers; the example does not require changing the requested weight repository. [Official ONNX model card](https://huggingface.co/PaddlePaddle/PP-DocLayoutV3_onnx)

## Model features

| Feature | Output or purpose |
|---|---|
| Region classification | One of 25 layout categories per detected region |
| Object detection | Axis-aligned bounding box and confidence |
| Instance segmentation | A separate mask for each region, supporting curved or irregular boundaries |
| Reading-order prediction | Learned ordering of document regions |

These tasks share one forward pass. The model targets scanned pages, photographs, skewed pages, curved documents, screen photographs, and lighting variation. Training scenarios include papers, books, magazines, newspapers, slides, contracts, exams, and reports. These are supported scenarios, not guarantees of accuracy on every document. [Official model card](https://huggingface.co/PaddlePaddle/PP-DocLayoutV3_onnx), [PaddleX module documentation](https://paddlepaddle.github.io/PaddleX/latest/en/module_usage/tutorials/ocr_modules/layout_analysis.html)

### All 25 categories

The following order is the class-ID mapping in the exported configuration:

| IDs | Labels |
|---|---|
| 0–4 | `abstract`, `algorithm`, `aside_text`, `chart`, `content` |
| 5–9 | `display_formula`, `doc_title`, `figure_title`, `footer`, `footer_image` |
| 10–14 | `footnote`, `formula_number`, `header`, `header_image`, `image` |
| 15–19 | `inline_formula`, `number`, `paragraph_title`, `reference`, `reference_content` |
| 20–24 | `seal`, `table`, `text`, `vertical_text`, `vision_footnote` |

`content` means table of contents; `number` means page number. Preserve the exact label mapping from [the artifact configuration](https://huggingface.co/PaddlePaddle/PP-DocLayoutV3_onnx/blob/46bbdf188bb0a772c08aed74882ce7e51a8f1ea6/inference.yml).

## Verified artifact

| Property | Observed value |
|---|---|
| Repository | `PaddlePaddle/PP-DocLayoutV3_onnx` |
| Repository revision | `46bbdf188bb0a772c08aed74882ce7e51a8f1ea6` |
| Runtime files | `inference.onnx`, `inference.yml` |
| ONNX SHA-256 | `45bf71750b00739a41fc209f132eb104a4d6b5bb29483c9078164d8b87cf28ba` |
| Approximate model size | 131 MB |
| ONNX opset | 17 |
| Weight representation | Floating-point weights; graph initializers include FLOAT, INT64, and INT32 |
| License metadata | Apache-2.0 |

The Hub's generated “quantized” relationship is not proof of INT8 weights. The table above reflects inspection of the actual exported graph. The repository contains an ONNX artifact and YAML configuration; generated Transformers snippets on its page do not establish direct `AutoModel.from_pretrained` compatibility. [Pinned repository files](https://huggingface.co/PaddlePaddle/PP-DocLayoutV3_onnx/tree/46bbdf188bb0a772c08aed74882ce7e51a8f1ea6)

### Inputs

| Input | Type and shape | Meaning |
|---|---|---|
| `image` | float32 `[B, 3, 800, 800]` | Resized RGB image batch |
| `im_shape` | float32 `[B, 2]` | Resized height and width |
| `scale_factor` | float32 `[B, 2]` | Height and width resize ratios |

Batch dimensions are dynamic in the graph. Spatial dimensions are fixed at 800 × 800. Only batch size 1 was tested in this session.

### Outputs

| Output | Type and shape | Meaning |
|---|---|---|
| `fetch_name_0` | float32 `[N, 7]` | Class, score, `xmin`, `ymin`, `xmax`, `ymax`, reading-order rank |
| `fetch_name_1` | int32 `[B]` | Candidate count for each image |
| `fetch_name_2` | int32 `[N, 200, 200]` | Corresponding binary instance masks |

`N` represents candidates concatenated across the batch. Use the per-image counts to split both boxes and masks. [Upstream output handling](https://github.com/PaddlePaddle/PaddleX/blob/ffb64904d23708863ff5b8da312a5cbd52a7f462/paddlex/inference/models/object_detection/predictor.py)

A local ONNX Runtime CPU smoke test on one synthetic white image returned:

```text
boxes:       (300, 7), float32
box_counts:  (1,), int32, value [300]
masks:       (300, 200, 200), int32
mask values: 0 and 1
order range: 0 through 299
```

These are raw candidates, not 300 accepted detections. The synthetic test validates execution and the output contract, not document accuracy.

## Full decoding pipeline

Full decoding includes operations embedded in the graph and external postprocessing.

1. Prepare the image as RGB. Resize to 800 × 800 without preserving aspect ratio, using bicubic interpolation. Scale pixels by `1/255`, convert to float32, and arrange them as NCHW.
2. Supply the image, resized dimensions, and resize ratios. For original dimensions `H × W`, the resized dimensions are `[800, 800]` and the scale factors are `[800/H, 800/W]`.
3. Collect all three outputs. Split candidates by the per-image counts and apply confidence filtering while keeping boxes, masks, and order ranks aligned.
4. Sort retained detections by the seventh box column. Preserve the original model rank separately from any displayed sequence number.
5. Decode masks into contours in original-image coordinates. Retain polygons and bounding boxes; retain raw masks when their additional geometry is needed.

Preprocessing follows the [artifact configuration](https://huggingface.co/PaddlePaddle/PP-DocLayoutV3_onnx/blob/46bbdf188bb0a772c08aed74882ce7e51a8f1ea6/inference.yml), [predictor](https://github.com/PaddlePaddle/PaddleX/blob/ffb64904d23708863ff5b8da312a5cbd52a7f462/paddlex/inference/models/object_detection/predictor.py), and [input processors](https://github.com/PaddlePaddle/PaddleX/blob/ffb64904d23708863ff5b8da312a5cbd52a7f462/paddlex/inference/models/object_detection/processors.py).

### Operations already embedded in ONNX

Inspection of the graph showed candidate selection, mask sigmoid/binarization, and reading-order ranking before its final outputs. Do not apply sigmoid again to the binary mask output. Do not interpret the final order column as raw pairwise relation logits.

Reading order is learned from pairwise precedence relationships, which are aggregated into a ranking. Replacing that ranking with top-to-bottom sorting or XY-cut discards a model capability. [Architecture description](https://arxiv.org/html/2601.21957v2)

### Mask-to-polygon decoding

The inspected PaddleX decoder crops each mask using its region box, resizes the mask crop, extracts the largest external contour, simplifies that contour, and translates it into original-image coordinates. Invalid or empty contours can fall back to rectangles.

Decoded polygons are simplified contours. They do not preserve every mask pixel, hole, or disconnected component. Raw masks preserve additional information. [Polygon decoder](https://github.com/PaddlePaddle/PaddleX/blob/ffb64904d23708863ff5b8da312a5cbd52a7f462/paddlex/inference/models/layout_analysis/processors.py)

## Decoder controls and caveats

The source observations below refer to PaddleX commit `ffb64904d23708863ff5b8da312a5cbd52a7f462`. They describe that upstream implementation, not a verified local DocLayout configuration.

| Control | Behavior |
|---|---|
| `layout_shape_mode="poly"` | Retains the simplified mask contour |
| `layout_shape_mode="quad"` | Converts geometry to a quadrilateral |
| `layout_shape_mode="rect"` | Uses rectangles and bypasses mask-based geometry |
| `layout_shape_mode="auto"` | Chooses rectangles, quadrilaterals, or polygons using geometric heuristics |
| Confidence threshold | Global or per-class thresholds; artifact configuration default is `0.5` |
| Optional NMS | Suppresses overlapping detections |
| Nested-box handling | `large` favors enclosing boxes, `small` favors contained boxes, and `union` retains both |
| Box expansion | Expands boxes using a configurable ratio |
| Additional overlap filtering | Can remove overlapping regions after restructuring |
| Skipped order labels | Excludes selected labels from displayed reading-order numbering |

These are postprocessing controls, not additional learned model heads. [Postprocessor source](https://github.com/PaddlePaddle/PaddleX/blob/ffb64904d23708863ff5b8da312a5cbd52a7f462/paddlex/inference/models/layout_analysis/processors.py)

### Threshold boundary

The inspected code uses strict `score > threshold`. Exactly `0.5` is excluded at threshold `0.5`. This layout threshold is unrelated to the project's downstream document-classification gate.

### Raw order versus displayed order

The ONNX probe returned zero-based raw ranks. Current PaddleX code sorts by those ranks, then assigns displayed order starting at 1 for eligible labels. Skipped labels receive `None`.

The inspected default skipped labels are:

```text
figure_title, vision_footnote, image, chart, table,
header, header_image, footer, footer_image, footnote, aside_text
```

The module documentation describes order as starting at zero, which differs from this wrapper's current numbering behavior. Preserve raw ranks separately to avoid losing information or confusing conventions. [Current numbering implementation](https://github.com/PaddlePaddle/PaddleX/blob/ffb64904d23708863ff5b8da312a5cbd52a7f462/paddlex/inference/models/layout_analysis/processors.py), [Module documentation](https://paddlepaddle.github.io/PaddleX/latest/en/module_usage/tutorials/ocr_modules/layout_analysis.html)

### Recommendation for preserving full output

Preserve raw rank, decoded sequence, polygon, bounding box, and mask provenance separately. Use `poly` when contour detail is required; `auto` may intentionally simplify it. Keep masks aligned with their originating candidates through filtering and sorting.

This is a research recommendation, not an implemented project change or a mandate to enable every optional filter.

## Wrapper facilities and model boundaries

The surrounding PaddleX interface supports image/PDF input handling, batching, JSON export, and annotated visualizations. These are application facilities around the model. A raw ONNX session accepts image tensors, not PDF files. [Module API documentation](https://paddlepaddle.github.io/PaddleX/latest/en/module_usage/tutorials/ocr_modules/layout_analysis.html)

PP-DocLayoutV3 identifies document structure. It does not independently transcribe text, extract table cells into HTML, recognize formulas as LaTeX, read seal text, or extract business fields. Detecting a `table` or `seal` region does not perform those recognition tasks. Separate recognition or extraction components supply them. [PaddleOCR-VL component separation](https://arxiv.org/html/2601.21957v2)

## Architecture and performance evidence

The academic name is RT-DocLayout, released in PaddleOCR as PP-DocLayoutV3. It has approximately 33 million parameters and builds on RT-DETR. The architecture combines classification, box detection, segmentation, and ordering in a shared query-based decoder. The module documentation identifies PPHGNetV2-L as the backbone. [RT-DocLayout paper](https://arxiv.org/html/2606.23344v1), [Module documentation](https://paddlepaddle.github.io/PaddleX/latest/en/module_usage/tutorials/ocr_modules/layout_analysis.html)

The RT-DocLayout paper reports 132.1 FPS on an NVIDIA A100 with batch size 32. Reported parsing scores use a downstream recognizer and are not standalone ONNX detection accuracy. These figures do not establish performance on this Windows machine or under a batch-size-1 workflow. [Benchmark conditions](https://arxiv.org/html/2606.23344v1)

## Verification limits

Verified in this session:

- Official repository metadata, revision, files, and artifact checksum.
- ONNX graph inputs, outputs, opset, and initializer types.
- One synthetic CPU inference, including mask values and reading-order range.
- Upstream preprocessing, output handling, polygon decoding, and order-numbering source.

Not verified:

- GPU execution or multi-image batching.
- Accuracy on real documents or the project's masked PDFs.
- End-to-end decoding parity between the local application and PaddleX.
- Local application use of every model feature described in this report.

The research confirms that full layout decoding is possible with `PaddlePaddle/PP-DocLayoutV3_onnx`. It does not establish that every feature is currently consumed by DocLayout.
