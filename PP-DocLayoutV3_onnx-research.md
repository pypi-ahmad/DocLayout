# PP-DocLayoutV3 ONNX: features and full decode

Research date: 2026-09-27.

`PaddlePaddle/PP-DocLayoutV3_onnx` supports 25 layout classes, bounding boxes,
instance masks, and learned reading order. Its ONNX graph includes detection
and ordering decode. Application code completes filtering, polygon extraction,
coordinate handling, and result serialization.

This report records the internet research and direct artifact inspection performed
in this session. It does not establish that the local application implements every
feature described below.

## Project constraint

Keep weights from `PaddlePaddle/PP-DocLayoutV3_onnx` and use its full decode path.
Do not switch the weights repository to `PaddlePaddle/PP-DocLayoutV3`.
The user locked this choice against future ordinary switch requests; removing the
lock requires an explicit instruction to remove it.

## Contents

- [Evidence and artifact identity](#evidence-and-artifact-identity)
- [Supported features](#supported-features)
- [ONNX input and output contract](#onnx-input-and-output-contract)
- [Full decode](#full-decode)
- [Postprocessing controls and information loss](#postprocessing-controls-and-information-loss)
- [Capabilities, limits, and deployment](#capabilities-limits-and-deployment)
- [Verification limits](#verification-limits)

## Evidence and artifact identity

The research used the official ONNX repository, PaddleX documentation and source,
the original PaddleOCR-VL-1.5 report, and the dedicated RT-DocLayout paper.
The ONNX file itself was downloaded and inspected as a graph.

| Item | Inspected value |
|---|---|
| Weights repository | `PaddlePaddle/PP-DocLayoutV3_onnx` |
| Repository revision | `46bbdf188bb0a772c08aed74882ce7e51a8f1ea6` |
| Model file | `inference.onnx` |
| Configuration | `inference.yml` |
| Model file size | 130,502,049 bytes |
| Model SHA-256 | `45bf71750b00739a41fc209f132eb104a4d6b5bb29483c9078164d8b87cf28ba` |
| ONNX opset | 17 |
| ONNX IR version | 8 |
| Floating-point initializer type | FP32 |
| License listed by repository | Apache-2.0 |
| PaddleX source revision inspected | `c50f5da858020db473a2285f089bb8c7bbd6afdc` |

The repository contains `.gitattributes`, `README.md`, `inference.onnx`, and
`inference.yml`. The inspected graph is not an INT8-quantized export, despite
quantization-related Hub metadata. Integer initializers include graph constants;
they are not evidence of quantized weights.

Sources: [official model card][model-card], [pinned repository files][files],
[inspected ONNX artifact][onnx].

## Supported features

| Feature | Output or purpose |
|---|---|
| Classification | Category and confidence for each detected region |
| Bounding boxes | Axis-aligned `[xmin, ymin, xmax, ymax]` coordinates |
| Instance segmentation | Separate binary mask for each region |
| Polygon geometry | Contours reconstructed from masks by postprocessing |
| Reading order | Learned position in the page's reading sequence |

The architecture combines an RT-DETR detector, PPHGNetV2-L backbone,
instance segmentation, and reading-order prediction. It is designed for clean
scans and photographed documents, including curved pages, skew, uneven lighting,
and screen photography. These are supported target scenarios, not guarantees of
correct predictions on every image.

Training covers Chinese and English documents such as papers, newspapers,
slides, contracts, books, and reports. The model card also carries a multilingual
tag; that does not establish OCR recognition coverage for a particular language.

Sources: [model card][model-card], [PaddleX layout analysis documentation][docs].

### All 25 classes

The IDs below follow `label_list` in the pinned configuration exactly.

| ID | Label | ID | Label | ID | Label |
|---|---|---|---|---|---|
| 0 | `abstract` | 9 | `footer_image` | 18 | `reference` |
| 1 | `algorithm` | 10 | `footnote` | 19 | `reference_content` |
| 2 | `aside_text` | 11 | `formula_number` | 20 | `seal` |
| 3 | `chart` | 12 | `header` | 21 | `table` |
| 4 | `content` | 13 | `header_image` | 22 | `text` |
| 5 | `display_formula` | 14 | `image` | 23 | `vertical_text` |
| 6 | `doc_title` | 15 | `inline_formula` | 24 | `vision_footnote` |
| 7 | `figure_title` | 16 | `number` | | |
| 8 | `footer` | 17 | `paragraph_title` | | |

Source: [official inference configuration][config].

## ONNX input and output contract

### Inputs

| Input | Type and shape | Meaning |
|---|---|---|
| `image` | float32 `[B, 3, 800, 800]` | RGB image, resized and scaled to `[0,1]` |
| `im_shape` | float32 `[B, 2]` | Resized height and width: `[800,800]` |
| `scale_factor` | float32 `[B, 2]` | `[800/original_height, 800/original_width]` |

Preprocessing uses bicubic resize with `keep_ratio: false`, then normalization
and channel-first conversion. The configured mean is zero and standard deviation
is one. Despite `norm_type: none`, PaddleX's default `is_scale=True` still divides
pixel values by 255.

The ONNX input is RGB. PaddleX's array reader expects BGR arrays and converts them
to RGB; a custom adapter must avoid accidentally converting an already-RGB array
as though it were BGR.

Sources: [configuration][config], [normalization implementation][normalize],
[image reader and batch input implementation][input-processors].

### Outputs

| Output | Type and shape | Meaning |
|---|---|---|
| `fetch_name_0` | float32 `[N,7]` | `[class_id, score, xmin, ymin, xmax, ymax, order_rank]` |
| `fetch_name_1` | int32 `[B]` | Number of candidate rows for each image |
| `fetch_name_2` | int32 `[N,200,200]` | Corresponding binary instance masks |

Static graph inspection confirms 300 selected candidates per image before
external confidence filtering. Batch outputs are flattened. The counts separate
each image's boxes and masks; the same slices must be applied to both.

Spatial input is fixed at 800 by 800. Batch dimensions are symbolic; this alone
does not prove that every batch size works on every execution provider.

Boxes are already mapped to original-image pixels inside the graph when the
inputs above are correct. Scaling those boxes again would corrupt coordinates.
Masks remain on the 200 by 200 grid and need separate spatial reconstruction.

Sources: [ONNX artifact inspected directly][onnx],
[PaddleX batch-output handling][batch-output].

## Full decode

### Decode already inside the exported graph

Graph inspection established these operations:

1. Apply sigmoid to classification logits and select the top 300 candidates.
2. Convert predicted boxes and map them to original-image coordinates.
3. Compute reading-order ranks from learned pairwise relations.
4. Gather masks corresponding to the selected candidates.
5. Apply sigmoid and a strict `> 0.5` mask threshold, then export integer masks.

The exported masks contain binary values, not mask probabilities. Raw mask
probabilities and raw pairwise reading-order logits are not exposed as outputs.
Application decoding cannot recover those discarded values from the three
exported outputs.

Source: [inspected ONNX graph][onnx].

### Processing required outside the graph

1. Split flattened outputs into images using the count tensor.
2. Filter candidates while preserving box, mask, and rank alignment.
3. Sort retained detections by the model's reading-order rank.
4. Reconstruct polygons and validate or clip final geometry.
5. Serialize categories, scores, boxes, polygons, and order information.

Full decode does not mean retaining every low-confidence candidate. It means
correctly consuming all output types while keeping filtering policy explicit.

Source: [PaddleX layout postprocessor][postprocess].

### Learned reading order

The model learns pairwise precedence scores. Sigmoid converts them into
probabilities, incoming precedence votes are summed, and ascending totals
determine the sequence. This is learned document sequencing rather than a
top-to-bottom coordinate sort.

The exported detection rows are selected by confidence; a consumer should use
their order column rather than assuming row position is reading order.
Keep the original model rank separately if a downstream interface needs a dense,
renumbered sequence after filtering.

Sources: [original technical report][original-paper], [ONNX graph][onnx],
[sorting implementation][postprocess].

### Mask-to-polygon reconstruction

The inspected PaddleX implementation:

1. Maps the detection box into the 200 by 200 mask grid and crops that mask.
2. Resizes the crop to the original-pixel box using nearest-neighbor interpolation.
3. Extracts the largest external contour and simplifies its vertices.
4. Translates contour points into original-image coordinates.
5. Applies the requested geometry mode, falling back to a rectangle when needed.

| Geometry mode | Behavior |
|---|---|
| `rect` | Discards mask geometry and keeps rectangles |
| `quad` | Converts the contour to an oriented four-point rectangle |
| `poly` | Keeps extracted polygon geometry |
| `auto` | Chooses rectangle, quadrilateral, or polygon using geometry heuristics |

A decoded polygon is already a simplified representation. Largest-external-
contour extraction can lose holes and disconnected components; vertex
simplification can lose fine boundary detail. Preserving the raw binary masks
provides the highest fidelity available from this export. Increasing output
polygon resolution cannot restore detail absent from the 200 by 200 mask.

For this project's full-decode requirement, preserve raw model rank and mask
association alongside decoded polygons. A rectangle or four-corner schema alone
cannot represent every polygon the decoder produces.

Source: [mask extraction and geometry implementation][geometry].

## Postprocessing controls and information loss

| Control | Behavior |
|---|---|
| `threshold` | Global or per-class confidence filtering; repository default is `0.5` |
| `layout_nms` | Optional suppression of overlapping detections |
| `layout_unclip_ratio` | Expands bounding boxes globally or per class |
| `layout_merge_bboxes_mode` | Keeps enclosing boxes, enclosed boxes, or both |
| `layout_shape_mode` | Selects `rect`, `quad`, `poly`, or `auto` geometry |
| `filter_overlap_boxes` | Applies additional region filtering |
| `skip_order_labels` | Controls which labels receive displayed order numbers |

Confidence comparisons in the inspected source use strict `>`.
Per-class threshold dictionaries fall back to `0.5` for unspecified classes.
Layout NMS uses IoU thresholds of `0.6` for matching classes and `0.98` for
different classes.

For merging, `large` favors enclosing boxes and `small` favors enclosed boxes.
`union` retains both; it does not calculate a geometric union.
Box expansion is separate from mask prediction and does not add predicted mask
detail.

Source: [postprocessing implementation][postprocess].

### Filtering can remove more than duplicates

With `filter_overlap_boxes=True`, current source removes `reference` regions,
regions narrower or shorter than six pixels, and some overlapping inline
formulas. It also contains category-aware overlap handling. A separate earlier
step can suppress near-page-sized `image` detections when multiple candidates
remain.

These are application policies applied after inference. They do not mean the
network lacks predictions for the affected classes. Preserve raw results or
record filtering decisions if downstream consumers need to distinguish model
output from application policy.

Source: [region filtering implementation][filtering].

### Displayed order differs from raw model rank

Current source renumbers retained ordered regions from **1** and sets
`order=None` for these eleven default labels:

```text
figure_title, vision_footnote, image, chart, table, header,
header_image, footer, footer_image, footnote, aside_text
```

Passing `skip_order_labels=[]` permits numbering all retained classes. It still
does not preserve original model rank values unless they are stored separately.

The documentation describes a zero-based `order`; the inspected source uses
one-based renumbering. Pin decoder behavior alongside the model revision and
distinguish raw rank from the final displayed order.

Sources: [order implementation][filtering], [documentation][docs].

## Capabilities, limits, and deployment

### Wrapper features

The PaddleX interface supports batched inputs, files, arrays, directories, and
URLs, plus JSON and annotated-image output. PDF page handling belongs to the
surrounding interface. The ONNX network itself consumes image tensors.

Source: [PaddleX interface documentation][docs].

### Tasks requiring downstream components

PP-DocLayoutV3 locates and categorizes regions. Text transcription, table-cell
reconstruction, formula-to-LaTeX conversion, chart interpretation, seal-text
recognition, Markdown generation, and cross-page merging require downstream
components. Recognizing a region as `table` or `seal` does not recover its contents.

Source: [PaddleOCR-VL-1.5 pipeline architecture][original-paper].

### Published performance

The dedicated paper names the model **RT-DocLayout** and explicitly maps that
name to PP-DocLayoutV3. It reports approximately **33M parameters** and
**132.1 FPS on an NVIDIA A100 with batch size 32**.

Its **94.50 OmniDocBench score** uses PaddleOCR-VL-1.5-0.9B as the downstream
recognizer. It is not standalone ONNX detection accuracy. These figures do not
establish Windows ONNX Runtime performance.

Source: [RT-DocLayout paper][dedicated-paper].

### Runtime and repository identity

The ONNX model card documents ONNX Runtime execution. Its API identifier
`model_name="PP-DocLayoutV3"` is a model-family name, distinct from the weights
repository. Explicitly loading the pinned `PaddlePaddle/PP-DocLayoutV3_onnx`
artifact preserves this project's required provenance.

Generic Hugging Face `AutoModel` snippets should not be treated as verified
instructions for this repository: the inspected repository contains no
Transformers configuration or safetensors weights.

Execution-provider support, GPU library compatibility, batch behavior, and
performance need runtime validation on the intended machine. The inspected
graph includes operators such as `GridSample`; an ONNX label alone is not proof
that every accelerator backend supports the complete graph.

Sources: [ONNX usage instructions][model-card], [repository files][files],
[ONNX graph][onnx].

## Verification limits

Verified in this research session:

- The exact repository revision, downloaded artifact size, and SHA-256.
- ONNX input/output metadata and relevant graph operations.
- Preprocessing configuration and upstream decoding source.
- Official feature descriptions and the context of published benchmarks.

Not tested in this research session:

- Document inference or end-to-end decoding on representative pages.
- GPU/provider compatibility, speed, memory usage, or batch execution.
- Accuracy, polygon fidelity, or reading-order quality on the user's documents.
- Whether the current local application preserves every output described here.

The upstream source was inspected at the pinned development revision above.
An installed PaddleX release may differ. No project code, dependencies, or model
configuration were changed during the research; this report is documentation.

[model-card]: https://huggingface.co/PaddlePaddle/PP-DocLayoutV3_onnx
[files]: https://huggingface.co/PaddlePaddle/PP-DocLayoutV3_onnx/tree/46bbdf188bb0a772c08aed74882ce7e51a8f1ea6
[onnx]: https://huggingface.co/PaddlePaddle/PP-DocLayoutV3_onnx/blob/46bbdf188bb0a772c08aed74882ce7e51a8f1ea6/inference.onnx
[config]: https://huggingface.co/PaddlePaddle/PP-DocLayoutV3_onnx/blob/46bbdf188bb0a772c08aed74882ce7e51a8f1ea6/inference.yml
[docs]: https://paddlepaddle.github.io/PaddleX/latest/en/module_usage/tutorials/ocr_modules/layout_analysis.html
[normalize]: https://github.com/PaddlePaddle/PaddleX/blob/c50f5da858020db473a2285f089bb8c7bbd6afdc/paddlex/inference/models/object_detection/predictor.py#L275
[input-processors]: https://github.com/PaddlePaddle/PaddleX/blob/c50f5da858020db473a2285f089bb8c7bbd6afdc/paddlex/inference/models/object_detection/processors.py#L35
[batch-output]: https://github.com/PaddlePaddle/PaddleX/blob/c50f5da858020db473a2285f089bb8c7bbd6afdc/paddlex/inference/models/object_detection/predictor.py#L155
[postprocess]: https://github.com/PaddlePaddle/PaddleX/blob/c50f5da858020db473a2285f089bb8c7bbd6afdc/paddlex/inference/models/layout_analysis/processors.py
[geometry]: https://github.com/PaddlePaddle/PaddleX/blob/c50f5da858020db473a2285f089bb8c7bbd6afdc/paddlex/inference/models/layout_analysis/processors.py#L183
[filtering]: https://github.com/PaddlePaddle/PaddleX/blob/c50f5da858020db473a2285f089bb8c7bbd6afdc/paddlex/inference/models/layout_analysis/processors.py#L586
[original-paper]: https://arxiv.org/html/2601.21957v1#S2.SS1
[dedicated-paper]: https://arxiv.org/html/2606.23344v1
