# Changelog

Unreleased entries describe changes in the current working tree. Version headings do not imply publication to PyPI.

## Unreleased

### Added

- Practical [configuration reference](docs/configuration.md) and
  [development guide](docs/development.md), with shared material moved out of
  other guides and replaced by links.

### Changed

- Updated documentation to match the current code and gave each topic a main
  guide. Historical validation measurements remain clearly labeled.
- Removed ten unused direct dependency declarations: `psutil`, `ftfy`,
  `jupyter`, `datasets`, `streamlit-ace`, `pytest-mock`, `apted`, `distance`,
  `lxml`, and `tabulate`. Retained dependency versions did not change; `lxml`
  remains a transitive dependency of optional document-format support.

### Removed

- Unused PDF text-layer table reconstruction, provider text utility, and image
  utility modules, plus the empty utility package initializer.
- Old frontend helpers `open_pdf`, `img_to_html`, `get_page_image`, and `page_count`.
- Provider-line interfaces `ProviderOutput`, `ProviderPageLines`,
  `get_page_lines`, and empty line storage.
- `PageGroup.merge_blocks`, its exclusive line-assignment methods/settings,
  unused `pdftext_page` cache, and unassigned deferred image loader.
- `sort_text_lines`, `Line.formatted_text`, `PolygonBox.center_distance`,
  `PolygonBox.fit_to_bounds`, `PromptData.additional_data`, and
  `Settings.DEBUG_DATA_FOLDER`.
- Unused dataset test helper, permanently skipped legacy ignore-text test,
  inactive filename/output-format markers, and unused mocker/Gemini test settings.

External extensions that use these removed interfaces must switch to current
providers and builders. Registered schema classes and configurable processors
remain available. Extraction and refinement prompt text was preserved; see
[cleanup verification](docs/gpt6-validation.md#cleanup-verification-2026-09-23).

## 2.0.0: Initial repository baseline (2026-09-23)

Package version 2.0.0 appears in the initial repository commit `038bb8c`.
This entry records that baseline without announcing a tag or package publication.

- DocLayout branding and a Streamlit document workbench with inclusive page
  selection, Markdown/raw views, HTML, estimated annotations, and copy/download/ZIP.
- GPT-6 Sol extraction and optional refinement, with GPT-6 Luna document chat
  using source-quote checks and independent verification.
- CLI, Python library, and local HTTP API, with document-format preparation
  through optional converters.
- Packaged Markdown prompts, offline/browser tests, bounded live evaluation
  fixtures, and the Windows launcher on port 8471.
- Apache-2.0 licensing, modification notices, and upstream attribution retained.

See [usage](docs/usage.md), [architecture](docs/architecture.md), and
[validation](docs/gpt6-validation.md) for behavior and verification limits.
